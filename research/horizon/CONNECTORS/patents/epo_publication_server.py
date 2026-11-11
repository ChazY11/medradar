"""EPO European Publication Server connector.

Why this source
---------------
Every large patent API (EPO OPS, USPTO Open Data Portal, PatentsView, Lens,
Espacenet's own service) is gated behind a free-but-required API key or account,
and the keyless legacy endpoints have been retired behind a WAF. The European
Publication Server is the exception: the EPO advertises a **sitemap index** for
it in its own ``robots.txt``, and each referenced weekly sitemap is a plain gzip
XML listing every EP publication of that week with its publication reference,
application reference and IPC. Each publication's front page
(``document.html``) carries the complete INID-coded bibliographic data.

Formats actually encountered (three different layouts, all handled here)
-----------------------------------------------------------------------
* ``<td class="ci2">(71)</td><td>…</td>``  — applicant/inventor for A documents
* ``<td class="ci1">(54)</td><td>`` with ``<p lang="en|de|fr">`` children — title
* ``<span class="ci2"><a name="ABSTRACT">(57)</a></span> text`` — abstract

INID codes used
---------------
11 publication number, 12 document type, 21 application number, 22 filing date,
30 priority, 43 date of publication of the application, 45 date of grant,
51 IPC, 52 CPC, 54 title, 57 abstract, 71 applicant, 72 inventor, 73 proprietor
(granted), 74 representative, 84 designated states, 86 PCT application,
87 PCT publication.

Temporal semantics (the reason this source matters)
---------------------------------------------------
* ``source_public_at`` = the date *this document* became publicly observable:
  INID 43 for an A publication, INID 45 for a B grant. Using 43 for a B grant
  would make a 2024 grant look like a 2012 observation — an error of years.
* ``event_at`` = INID 22 filing date.
* ``observability_gap_days`` = publication − filing, per record.

Applicant is captured **as printed on the publication**, which is what makes
historical subsidiary / merger attribution possible instead of reading today's
corporate tree back into 1998.

Access posture
--------------
No key, no registration, no login. ``https://data.epo.org/robots.txt`` lists the
sitemap and asks crawlers that intend to build indexes to register with
``patentinformation@epo.org`` for a deep redirect. This connector does not crawl
or build an index: it samples a bounded number of advertised sitemaps and a
bounded number of front pages. It never requests the paths robots.txt disallows
(``/linked-data/{id,doc,data,def,representation}/``).

Licence: ``open_no_explicit_licence`` — official public patent publications,
subject to the EPO terms of use (https://www.epo.org/en/legal/terms-of-use).
We store derived bibliographic records; we do not mirror the corpus.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:  # allow standalone execution
    sys.path.insert(0, _ROOT)

from hz.http import BoundedClient, ResponseTooLarge  # noqa: E402
from hz.schema import Identifier, build_record  # noqa: E402
from hz.timeq import classify_record, now_utc  # noqa: E402

SOURCE_ID = "epo_publication_server"
KIND = "patent_publication"
LICENCE_STATUS = "open_no_explicit_licence"
LICENCE_URL = "https://www.epo.org/en/legal/terms-of-use"
SITEMAP_INDEX = "https://data.epo.org/publication-server/sitemap.xml"
ROBOTS_URL = "https://data.epo.org/robots.txt"

# IPC subclasses that are unambiguous medical-device / medical-IT artefacts.
# A61K (preparations for medical purposes) and A61P (therapeutic activity) are
# drugs, not devices, and are excluded unless a device subclass is also present.
MEDTECH_IPC: dict[str, str] = {
    "A61B": "diagnosis; surgery; identification",
    "A61M": "introducing/removing media from the body (infusion, ventilation, suction)",
    "A61H": "physical therapy apparatus",
    "A61N": "electrotherapy; magnetotherapy; radiation therapy",
    "A61G": "patient transport, accommodation, operating tables",
    "A61F": "implants; prostheses; stents; filters",
    "A61J": "medical containers; administering arrangements",
    "A61L": "sterilisation; dressings; materials",
    "A61C": "dentistry",
    "A61D": "veterinary instruments",
    "G16H": "ICT for healthcare informatics",
    "H05G": "X-ray technique",
    "A61K": "",   # drug — never counts on its own
    "A61P": "",   # therapeutic activity — never counts on its own
}
_DEVICE_SUBCLASSES = {k for k, v in MEDTECH_IPC.items() if v}

_NS_RE = re.compile(r"\{[^}]*\}")


def _ln(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return _NS_RE.sub("", tag)


def _elems(node):
    """Iterate real element children (skips comments / processing instructions)."""
    for ch in node:
        if isinstance(ch.tag, str):
            yield ch


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _norm_lines(s: str) -> str:
    """Collapse runs of blanks but KEEP line breaks (name / address boundaries)."""
    s = (s or "").replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r" *\n[ \n]*", "\n", s)
    return s.strip()


# ---------------------------------------------------------------------------
# 1. sitemap index
# ---------------------------------------------------------------------------


@dataclass
class Week:
    publication_date: str
    url: str


def fetch_sitemap_index(client: BoundedClient) -> list[Week]:
    res = client.get(SITEMAP_INDEX)
    if not res.ok:
        raise RuntimeError(f"sitemap index HTTP {res.status}")
    from lxml import etree

    root = etree.fromstring(res.body)
    weeks: list[Week] = []
    for sm in root.iter():
        if _ln(sm.tag) != "sitemap":
            continue
        loc = lastmod = None
        for child in sm:
            if _ln(child.tag) == "loc":
                loc = (child.text or "").strip()
            elif _ln(child.tag) == "lastmod":
                lastmod = (child.text or "").strip()
        if loc and lastmod and re.match(r"^\d{4}-\d{2}-\d{2}$", lastmod):
            weeks.append(Week(publication_date=lastmod, url=loc))
    weeks.sort(key=lambda w: w.publication_date)
    return weeks


# ---------------------------------------------------------------------------
# 2. weekly sitemap
# ---------------------------------------------------------------------------


@dataclass
class PubRef:
    sitemap_date: str
    country: str
    doc_number: str
    kind: str
    correction_code: str
    publication_date: str
    application_number: str | None
    filing_date: str | None
    ipc: list[str] = field(default_factory=list)
    html_url: str | None = None
    pdf_url: str | None = None

    @property
    def publication_id(self) -> str:
        return f"{self.country}{self.doc_number}{self.kind}"

    @property
    def is_grant(self) -> bool:
        return self.kind.upper().startswith("B")

    @property
    def tech_classes(self) -> list[str]:
        out: list[str] = []
        for c in self.ipc:
            sub = c[:4].upper()
            if re.match(r"^[A-H]\d\d[A-Z]$", sub) and sub not in out:
                out.append(sub)
        return out

    def is_medtech(self) -> bool:
        return any(s in _DEVICE_SUBCLASSES for s in self.tech_classes)


def _gd(parent, name: str):
    for el in parent:
        if _ln(el.tag) == name:
            return el
    return None


def _gdt(parent, name: str) -> str | None:
    el = _gd(parent, name)
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _compact_to_iso(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip()
    if len(v) == 8 and v.isdigit():
        return f"{v[0:4]}-{v[4:6]}-{v[6:8]}"
    return None


def parse_weekly_sitemap(body: bytes, sitemap_date: str) -> list[PubRef]:
    from lxml import etree

    # IPC in the sitemap is compacted without separators:
    #   'A61M0005142' -> A61M + group '0005' + subgroup '142' -> 'A61M 5/142'
    #   'C07K001622'  -> C07K + '0016' + '22'                -> 'C07K 16/22'
    #   'G06F002157'  -> G06F + '0021' + '57'                -> 'G06F 21/57'
    # i.e. exactly four group digits after the four-character subclass, then the
    # remainder is the subgroup.
    def expand_ipc(txt: str) -> list[str]:
        out: list[str] = []
        for tok in re.split(r"\s+", txt or ""):
            m = re.fullmatch(r"([A-H]\d{2}[A-Z])(\d{4})(\d+)", tok)
            if m:
                out.append(f"{m.group(1)} {int(m.group(2))}/{m.group(3)}")
            elif re.fullmatch(r"[A-H]\d{2}[A-Z]\d+/\d+", tok):
                out.append(tok)
            elif re.fullmatch(r"[A-H]\d{2}[A-Z]", tok):
                out.append(tok)
        return out

    root = etree.fromstring(body)
    refs: list[PubRef] = []
    for url_el in root.iter():
        if _ln(url_el.tag) != "url":
            continue
        locs: list[str] = []
        doc_list = None
        for child in url_el:
            if _ln(child.tag) == "loc":
                locs.append((child.text or "").strip())
            elif _ln(child.tag) == "ep-patent-document-list":
                doc_list = child
        if doc_list is None:
            continue
        for doc in doc_list:
            if _ln(doc.tag) != "ep-patent-document-ref":
                continue
            pubref = _gd(doc, "publication-reference")
            if pubref is None:
                continue
            docid = _gd(pubref, "document-id")
            if docid is None:
                continue
            number = _gdt(docid, "doc-number")
            if not number:
                continue
            appno = fdate = None
            appref = _gd(doc, "application-reference")
            if appref is not None:
                appdoc = _gd(appref, "document-id")
                if appdoc is not None:
                    appno = _gdt(appdoc, "doc-number")
                    fdate = _gdt(appdoc, "date")
            ipc: list[str] = []
            ipcel = _gd(doc, "classification-ipc")
            if ipcel is not None:
                ipc = expand_ipc(_gdt(ipcel, "text") or "")
            refs.append(
                PubRef(
                    sitemap_date=sitemap_date,
                    country=_gdt(docid, "country") or "EP",
                    doc_number=number,
                    kind=_gdt(docid, "kind") or "",
                    correction_code=_gdt(docid, "correction-code") or "",
                    publication_date=_compact_to_iso(_gdt(docid, "date")) or sitemap_date,
                    application_number=appno,
                    filing_date=_compact_to_iso(fdate),
                    ipc=ipc,
                    html_url=next((u for u in locs if u.endswith("document.html")), None),
                    pdf_url=next((u for u in locs if u.endswith("document.pdf")), None),
                )
            )
    return refs


def fetch_week(client: BoundedClient, week: Week) -> list[PubRef]:
    res = client.get(week.url)
    if not res.ok:
        raise RuntimeError(f"{week.url}: HTTP {res.status}")
    body = res.body
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return parse_weekly_sitemap(body, week.publication_date)


# ---------------------------------------------------------------------------
# 3. front page (INID)
# ---------------------------------------------------------------------------

_INID_ONLY = re.compile(r"^\((\d{2})\)$")
_INID_RE = re.compile(r"\((\d{2})\)")
_DATE_DMY = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_DATE_YMD = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_IPC_TOKEN = re.compile(r"([A-H]\d{2}[A-Z])\s*(\d+)\s*/\s*(\d+)")

_LABEL_PREFIX = re.compile(
    r"^(?:"
    r"Date of publication(?: and mention of the grant of the patent)?"
    r"|of application|Mention of the grant of the patent"
    r"|Date of filing|Application number|Applicants?|Proprietors?"
    r"|Inventors?|Representative|Patentee|Priority(?: date)?"
    r"|International Patent Classification\s*\(IPC\)"
    r"|Cooperative Patent Classification\s*\(CPC\)"
    r"|Designated Contracting States|Designated Extension States"
    r"|Designated Validation States|Bulletin"
    r"|TITLE|Title|Abstract|References cited"
    r"|International application number"
    r"|International publication number|\(?WO\)?"
    r")\s*:?\s*",
    re.I,
)


def _txt(el, br: str = "\n") -> str:
    """text_content that honours <br> as a line break."""
    parts: list[str] = []

    def walk(node) -> None:
        if node.text:
            parts.append(node.text)
        for ch in _elems(node):
            if _ln(ch.tag) == "br":
                parts.append(br)
            walk(ch)
            if ch.tail:
                parts.append(ch.tail)

    walk(el)
    return "".join(parts)


def _clean(code: str, text: str) -> str:
    t = _norm_ws(_INID_RE.sub(" ", text))
    for _ in range(2):
        t2 = _LABEL_PREFIX.sub("", t, count=1)
        if t2 == t:
            break
        t = t2
    return _norm_ws(t)


def _parse_blocks(html: bytes) -> dict[str, dict]:
    """Map INID code -> {text, items, bolds, langs} independent of layout."""
    from lxml import html as LH

    try:
        tree = LH.fromstring(html)
    except Exception:
        return {}

    out: dict[str, dict] = {}

    def rec(code: str) -> dict:
        return out.setdefault(code, {"texts": [], "items": [], "bolds": [], "langs": {}})

    def collect_langs(scope) -> dict[str, str]:
        found: dict[str, str] = {}
        for el in scope.iter():
            lang = el.get("lang") if hasattr(el, "get") else None
            if not lang:
                continue
            t = _norm_ws(_txt(el, br=" "))
            if t and lang not in found:
                found[lang] = t
        return found

    for el in tree.iter():
        if el.tag not in ("td", "th", "span", "a", "div", "p", "b"):
            continue
        m = _INID_ONLY.match(_norm_ws("".join(el.itertext())))
        if not m:
            continue
        code = m.group(1)
        r = rec(code)

        if el.tag in ("td", "th"):
            table = el.getparent()
            while table is not None and _ln(table.tag) != "table":
                table = table.getparent()
            if table is None:
                continue
            row = el.getparent()
            pieces: list[str] = []
            for cell in _elems(row):
                if cell is el:
                    continue
                pieces.append(_norm_ws(_txt(cell, br=" ")))
            sib = row.getnext()
            while sib is not None and _ln(sib.tag) == "tr":
                labels = [
                    _norm_ws("".join(c.itertext()))
                    for c in sib
                    if _ln(c.tag) in ("td", "th")
                ]
                if any(_INID_ONLY.match(s) for s in labels):
                    break
                piece = _norm_ws(" ".join(_txt(c, br=" ") for c in _elems(sib)))
                if piece:
                    pieces.append(piece)
                sib = sib.getnext()
            if not r["items"]:
                r["items"] = [_norm_lines(_txt(li, br="\n")) for li in table.iter("li")]
            if not r["bolds"]:
                r["bolds"] = [
                    _norm_ws(_txt(sp, br=" "))
                    for sp in table.iter("span")
                    if "bold" in (sp.get("class") or "").split()
                ]
            if not r["langs"]:
                r["langs"] = collect_langs(table)
            r["texts"].append(" ".join(p for p in pieces if p))
        else:
            cell = el
            while cell is not None and _ln(cell.tag) != "td":
                cell = cell.getparent()
            if cell is None:
                continue
            if not r["langs"]:
                r["langs"] = collect_langs(cell)
            r["texts"].append(_norm_ws(_txt(cell, br=" ")))

    for code, r in out.items():
        cleaned = [_clean(code, t) for t in r["texts"]]
        r["text"] = next((c for c in cleaned if c), "")
    return out


def _ipc_list(text: str) -> list[str]:
    out: list[str] = []
    for m in _IPC_TOKEN.finditer(text or ""):
        tok = f"{m.group(1)} {m.group(2)}/{m.group(3)}"
        if tok not in out:
            out.append(tok)
    return out


def _iso_date(s: str | None) -> str | None:
    if not s:
        return None
    m = _DATE_DMY.search(s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = _DATE_YMD.search(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _names_from(items: Iterable[str]) -> list[str]:
    """'SHACHAR, Yehoshua\\nSanta Monica, CA 90405 (US)' -> 'SHACHAR, Yehoshua'"""
    out: list[str] = []
    for it in items:
        it = (it or "").strip()
        if not it:
            continue
        first = it.split("\n")[0].strip()
        # if the <br> split did not happen, cut at a trailing postal address
        if "\n" not in it:
            first = re.split(r"\s+\d{3,6}\s+[A-Z]{2}", first, maxsplit=1)[0].strip()
            first = re.split(r"\s+\d{4,5}\s", first, maxsplit=1)[0].strip()
        first = re.sub(r"\s*\([A-Z]{2}\)\s*$", "", first).strip()
        if len(first) > 1:
            out.append(first)
    return out


@dataclass
class FrontPage:
    publication_number: str | None = None
    document_type: str | None = None
    date_43_application: str | None = None
    date_45_grant: str | None = None
    bulletin: str | None = None
    application_number: str | None = None
    filing_date: str | None = None
    priority_claims: list[dict] = field(default_factory=list)
    ipc: list[str] = field(default_factory=list)
    cpc: list[str] = field(default_factory=list)
    title: str | None = None
    title_all_langs: dict[str, str] = field(default_factory=dict)
    abstract: str | None = None
    applicants: list[str] = field(default_factory=list)
    inventors: list[str] = field(default_factory=list)
    proprietors: list[str] = field(default_factory=list)
    representative: str | None = None
    designated_states: list[str] = field(default_factory=list)
    pct_application: str | None = None
    pct_publication: str | None = None
    tech_classes: list[str] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    raw_chars: int = 0

    def publication_date_for(self, kind: str) -> str | None:
        """The observability clock for *this* document, chosen by kind."""
        k = (kind or "").upper()
        if k.startswith("B"):
            return self.date_45_grant or self.date_43_application
        return self.date_43_application or self.date_45_grant


def parse_front_page(html: bytes) -> FrontPage:
    fp = FrontPage(raw_chars=len(html))
    blocks = _parse_blocks(html)
    if not blocks:
        fp.parse_warnings.append("no INID table found")
        return fp

    def g(code: str) -> dict:
        return blocks.get(code) or {}

    def t(code: str) -> str | None:
        v = g(code).get("text") or ""
        return v or None

    pub = t("11")
    if pub:
        m = re.search(r"([A-Z]{2})\s*([\d\s]{3,})\s*([A-Z]\d?)", pub)
        if m:
            fp.publication_number = (
                f"{m.group(1)}{re.sub(r'[^0-9]', '', m.group(2))}{m.group(3)}"
            )
        else:
            fp.publication_number = pub
    fp.document_type = t("12")

    d43 = t("43")
    if d43:
        fp.date_43_application = _iso_date(d43)
        mb = re.search(r"Bulletin\s*([\d/]+)", d43)
        if mb:
            fp.bulletin = mb.group(1)
    d45 = t("45")
    if d45:
        fp.date_45_grant = _iso_date(d45)
        mb = re.search(r"Bulletin\s*([\d/]+)", d45)
        if mb and not fp.bulletin:
            fp.bulletin = mb.group(1)

    a21 = t("21")
    if a21:
        m = re.search(r"([\d.]{5,})", a21)
        fp.application_number = (m.group(1).rstrip(".") if m else a21) or None
    fp.filing_date = _iso_date(t("22"))

    a30 = t("30")
    if a30:
        for piece in re.split(r"\s{2,}", a30):
            m = re.match(r"(\d{1,2}\.\d{1,2}\.\d{4})\s+([A-Z]{2})\s+(\S+)", piece.strip())
            if m:
                fp.priority_claims.append(
                    {
                        "date": _iso_date(m.group(1)),
                        "country": m.group(2),
                        "number": m.group(3),
                    }
                )
        if not fp.priority_claims:
            fp.priority_claims.append({"raw": a30})

    fp.ipc = _ipc_list(t("51") or "")
    fp.cpc = _ipc_list(t("52") or "")

    t54 = g("54")
    langs = t54.get("langs") or {}
    if langs:
        fp.title_all_langs = dict(langs)
        fp.title = langs.get("en") or next(iter(langs.values()))
    else:
        raw = t54.get("text") or ""
        fp.title = _norm_ws(re.sub(r"\((?:EN|DE|FR)\)", " ", raw)) or None
    if fp.title:
        fp.title = _norm_ws(fp.title)

    ab = g("57")
    ab_langs = ab.get("langs") or {}
    if ab_langs:
        fp.abstract = ab_langs.get("en") or next(iter(ab_langs.values()))
    else:
        fp.abstract = (ab.get("text") or "")[:4000] or None

    # applicant: (71) for applications, (73) proprietors for granted documents
    for code in ("71", "73"):
        r = g(code)
        if not r:
            continue
        names = _names_from(r.get("items") or [])
        if not names:
            names = [b for b in (r.get("bolds") or []) if len(b) > 1]
        if not names and r.get("text"):
            names = _names_from([r["text"]])
        if code == "71":
            fp.applicants = names
        else:
            fp.proprietors = names

    fp.inventors = _names_from(g("72").get("items") or [])
    if not fp.inventors:
        fp.inventors = _names_from(g("72").get("bolds") or [])

    fp.representative = t("74")

    a84 = t("84")
    if a84:
        fp.designated_states = [
            s for s in re.split(r"\s+", a84) if re.fullmatch(r"[A-Z]{2}", s)
        ]
    fp.pct_application = t("86")
    fp.pct_publication = t("87")

    subs: list[str] = []
    for ipc in fp.ipc:
        sc = ipc[:4].upper()
        if re.match(r"^[A-H]\d\d[A-Z]$", sc) and sc not in subs:
            subs.append(sc)
    fp.tech_classes = subs

    if not fp.date_43_application and not fp.date_45_grant:
        fp.parse_warnings.append("no publication date (INID 43/45)")
    if not fp.filing_date:
        fp.parse_warnings.append("no filing date (INID 22)")
    if not (fp.applicants or fp.proprietors):
        fp.parse_warnings.append("no applicant/proprietor (INID 71/73)")
    if not fp.title:
        fp.parse_warnings.append("no title (INID 54)")
    if not fp.ipc:
        fp.parse_warnings.append("no IPC (INID 51)")
    return fp


def fetch_front_page(client: BoundedClient, url: str) -> FrontPage:
    res = client.get(url)
    if not res.ok:
        raise RuntimeError(f"{url}: HTTP {res.status}")
    return parse_front_page(res.body)


# ---------------------------------------------------------------------------
# 4. record assembly
# ---------------------------------------------------------------------------


def to_record(ref: PubRef, fp: FrontPage | None, fetched_at: str | None = None) -> dict:
    fetched_at = fetched_at or now_utc()

    pub_date = None
    filing = ref.filing_date
    title = None
    applicants: list[str] = []
    flags: list[str] = []
    attrs: dict = {}

    if fp is not None:
        pub_date = fp.publication_date_for(ref.kind) or ref.publication_date
        filing = fp.filing_date or ref.filing_date
        title = fp.title
        applicants = fp.applicants or fp.proprietors
        attrs.update(
            {
                "document_type": fp.document_type,
                "date_43_application": fp.date_43_application,
                "date_45_grant": fp.date_45_grant,
                "bulletin": fp.bulletin,
                "priority_claims": fp.priority_claims,
                "cpc": fp.cpc,
                "applicants": fp.applicants,
                "proprietors": fp.proprietors,
                "inventors": fp.inventors,
                "representative": fp.representative,
                "title_all_langs": fp.title_all_langs,
                "abstract": fp.abstract,
                "designated_states": fp.designated_states,
                "pct_application": fp.pct_application,
                "pct_publication": fp.pct_publication,
                "parsed_from": "inid_front_page_html",
                "parse_warnings": fp.parse_warnings,
                "raw_frontpage_bytes": fp.raw_chars,
                "ipc": fp.ipc or ref.ipc,
                "ipc_subclasses": fp.tech_classes or ref.tech_classes,
            }
        )
        if "PARSED_FROM_HTML" not in flags:
            flags.append("PARSED_FROM_HTML")
        if fp.publication_date_for(ref.kind) and ref.publication_date:
            if fp.publication_date_for(ref.kind) != ref.publication_date:
                attrs["sitemap_date_disagreement"] = {
                    "front_page": fp.publication_date_for(ref.kind),
                    "sitemap": ref.publication_date,
                }
        for w in fp.parse_warnings:
            if w.startswith("no publication date"):
                flags.append("MISSING_PUBLICATION_DATE")
            elif w.startswith("no filing date"):
                flags.append("MISSING_FILING_DATE")
            elif w.startswith("no applicant"):
                flags.append("MISSING_MANUFACTURER")
            elif w.startswith("no title"):
                flags.append("MISSING_TITLE")
            elif w.startswith("no IPC"):
                flags.append("MISSING_CLASSIFICATION")
    else:
        # sitemap-only record: publication reference is still authoritative
        pub_date = ref.publication_date
        attrs.update(
            {
                "parsed_from": "sitemap_only",
                "ipc": ref.ipc,
                "ipc_subclasses": ref.tech_classes,
                "front_page_status": "NOT_FETCHED_OR_FAILED",
            }
        )
        flags += ["MISSING_TITLE", "MISSING_MANUFACTURER", "SITEMAP_ONLY"]

    if not pub_date:
        flags.append("MISSING_PUBLICATION_DATE")
    if not filing:
        flags.append("MISSING_FILING_DATE")

    # priority date is the earliest priority claim, if any
    prio = [p.get("date") for p in attrs.get("priority_claims", []) if p.get("date")]
    if prio:
        attrs["priority_date"] = min(prio)
    elif fp is not None:
        flags.append("MISSING_PRIORITY_DATE")

    tech = [
        s for s in (attrs.get("ipc_subclasses") or ref.tech_classes)
        if s in _DEVICE_SUBCLASSES
    ]
    attrs["medtech_ipc_subclasses"] = tech
    if not tech:
        flags.append("NOT_MEDTECH_ON_FRONT_PAGE")

    attrs["clock"] = classify_record(filing, pub_date)
    attrs["kind"] = ref.kind
    attrs["application_number"] = ref.application_number
    attrs["sitemap_publication_date"] = ref.sitemap_date
    attrs["source_channel"] = "epo_publication_server_sitemap"
    attrs["fetched_via"] = ref.html_url

    identifiers = [
        Identifier(
            scheme="epo_publication_number",
            value=ref.publication_id,
            issuing_authority="EPO",
            scope="EP",
            is_primary=True,
        )
    ]
    if ref.application_number:
        identifiers.append(
            Identifier(
                scheme="epo_application_number",
                value=f"EP{ref.application_number}",
                issuing_authority="EPO",
                scope="EP",
            )
        )
    if attrs.get("pct_application"):
        m = re.search(r"(PCT/[A-Z]{2}\d{4}/\d{6})", attrs["pct_application"])
        if m:
            identifiers.append(
                Identifier(scheme="pct_application_number", value=m.group(1), issuing_authority="WIPO")
            )
        elif attrs["pct_application"]:
            identifiers.append(
                Identifier(
                    scheme="pct_application_number",
                    value=attrs["pct_application"],
                    issuing_authority="WIPO",
                    scope="unparsed",
                )
            )

    relations = []
    if ref.application_number:
        relations.append(
            {
                "type": "application_to_publication",
                "to_scheme": "epo_application_number",
                "to_value": f"EP{ref.application_number}",
                "basis": "EPO publication sitemap <application-reference> element",
                "status": "CONFIRMED",
            }
        )
    for p in attrs.get("priority_claims", []):
        if p.get("number"):
            relations.append(
                {
                    "type": "priority_claim",
                    "to_scheme": "priority_application_number",
                    "to_value": f"{p.get('country','?')}{p.get('number')}",
                    "to_date": p.get("date"),
                    "basis": "INID 30 priority claim printed on the publication",
                    "status": "CONFIRMED",
                }
            )

    return build_record(
        source_id=SOURCE_ID,
        source_record_id=ref.publication_id,
        entity_type="patent_publication",
        original_name=title or f"(no title extracted) {ref.publication_id}",
        identifiers=identifiers,
        manufacturer=applicants[0] if applicants else None,
        attributes=attrs,
        event_at=filing,
        source_public_at=pub_date,
        first_observed_at=fetched_at,
        fetched_at=fetched_at,
        source_url=ref.html_url or "",
        licence_status=LICENCE_STATUS,
        licence_note=f"EPO European Publication Server; sitemap advertised in {ROBOTS_URL}; terms {LICENCE_URL}",
        identity_status="UNKNOWN",
        evidence_status="CANDIDATE",
        quality_flags=sorted(set(flags)),
        relations=relations,
    ).to_dict()


# ---------------------------------------------------------------------------
# 5. bounded collection
# ---------------------------------------------------------------------------

DEFAULT_WEEKS = [
    "2005-06-01",
    "2010-01-13",
    "2013-05-08",
    "2016-09-07",
    "2019-03-06",
    "2021-11-10",
    "2023-03-08",
    "2024-06-05",
    "2025-01-08",
    "2026-06-03",
]


def collect(
    *,
    weeks_wanted: list[str] | None = None,
    max_weeks: int = 8,
    max_front_pages: int = 120,
    max_requests: int = 240,
    max_total_bytes: int = 90_000_000,
    out_dir: str | None = None,
    log_path: str | None = None,
    medtech_only: bool = True,
    front_page_stride: int = 1,
    week_caps: dict[str, int] | None = None,
    sparse_per_week: int = 6,
) -> dict:
    """Sample weekly sitemaps, then fetch front pages under an explicit budget.

    ``week_caps`` lets a caller spend most of the front-page budget on a couple
    of weeks (dense sampling, good for finding specific applicants) while still
    covering older weeks sparsely (good for historical depth).
    """
    weeks_wanted = weeks_wanted or DEFAULT_WEEKS
    week_caps = week_caps or {}
    client = BoundedClient(
        name="epo_publication_server",
        max_requests=max_requests,
        max_bytes_per_response=14_000_000,
        max_total_bytes=max_total_bytes,
        requests_per_second=1.5,
        max_retries=2,
        log_path=log_path,
    )
    fetched_at = now_utc()
    per_week: list[dict] = []
    records: list[dict] = []
    front_page_audit: dict[str, dict] = {}
    all_refs: list[PubRef] = []
    refs_by_week: dict[str, list[PubRef]] = {}
    sample: list[PubRef] = []
    try:
        index = fetch_sitemap_index(client)
        by_date = {w.publication_date: w for w in index}
        chosen: list[Week] = []
        for d in weeks_wanted:
            if d in by_date:
                chosen.append(by_date[d])
            else:
                later = [w for w in index if w.publication_date >= d]
                if later:
                    chosen.append(later[0])
        seen: set[str] = set()
        chosen = [
            w for w in chosen
            if not (w.publication_date in seen or seen.add(w.publication_date))
        ][:max_weeks]

        for w in chosen:
            try:
                refs = fetch_week(client, w)
            except Exception as exc:
                per_week.append({"week": w.publication_date, "url": w.url, "error": str(exc)[:200]})
                continue
            med = [r for r in refs if r.is_medtech()]
            hist: dict[str, int] = {}
            for r in med:
                for s in r.tech_classes:
                    if s in _DEVICE_SUBCLASSES:
                        hist[s] = hist.get(s, 0) + 1
            per_week.append(
                {
                    "week": w.publication_date,
                    "url": w.url,
                    "publications": len(refs),
                    "medtech": len(med),
                    "medtech_share": round(len(med) / len(refs), 4) if refs else None,
                    "medtech_ipc_histogram": dict(sorted(hist.items(), key=lambda kv: -kv[1])),
                }
            )
            all_refs.extend(med if medtech_only else refs)
            refs_by_week[w.publication_date] = med if medtech_only else refs

        # ---- bounded front-page sampling -------------------------------
        sample: list[PubRef] = []
        for wdate in sorted(refs_by_week):
            pool = sorted(refs_by_week[wdate], key=lambda r: r.publication_id)
            pool = [r for r in pool if r.html_url]
            cap = week_caps.get(wdate, sparse_per_week)
            if cap <= 0:
                continue
            if len(pool) <= cap:
                chosen_refs = pool
            else:
                step = len(pool) / cap
                chosen_refs = [pool[min(int(i * step), len(pool) - 1)] for i in range(cap)]
            sample.extend(chosen_refs)
        if front_page_stride > 1:
            sample = sample[::front_page_stride]
        sample = sample[:max_front_pages]

        for ref in sample:
            try:
                fp = fetch_front_page(client, ref.html_url)  # type: ignore[arg-type]
            except Exception as exc:
                records.append(to_record(ref, None, fetched_at))
                front_page_audit[ref.publication_id] = {"error": str(exc)[:200]}
                continue
            records.append(to_record(ref, fp, fetched_at))
            front_page_audit[ref.publication_id] = {
                "warnings": fp.parse_warnings,
                "raw_chars": fp.raw_chars,
                "applicants": fp.applicants,
                "proprietors": fp.proprietors,
                "title": fp.title,
                "date_43": fp.date_43_application,
                "date_45": fp.date_45_grant,
            }
        budget = client.budget_report()
    finally:
        client.close()

    result = {
        "source_id": SOURCE_ID,
        "generated_at": fetched_at,
        "weeks_requested": weeks_wanted,
        "weeks_used": per_week,
        "publication_refs_considered": len(all_refs),
        "front_pages_attempted": len(sample),
        "records": records,
        "front_page_audit": front_page_audit,
        "budget": budget,
        "medtech_only": medtech_only,
    }
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "COLLECT.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    return result
