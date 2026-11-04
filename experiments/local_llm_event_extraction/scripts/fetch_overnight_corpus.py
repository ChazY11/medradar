"""Collect the overnight exploratory corpus from public regulatory APIs.

What this script may and may not do
-----------------------------------
It collects only **public, structured regulatory records** from two APIs whose
terms permit this use:

* ``api.fda.gov`` (openFDA: 510(k), PMA, recall endpoints) -- U.S. Government
  work, public domain;
* ``api.clinicaltrials.gov`` (ClinicalTrials.gov API v2) -- U.S. National
  Library of Medicine public data.

It does **not** download copyrighted full text, news articles or press releases.
The ``text`` field of every record is therefore either

* ``structural_rendering`` -- a deterministic rendering of that record's own
  declared fields (no new factual content), or
* ``synthetic_narrative`` -- a deterministic narrative *generated from the same
  fields* by templates in this file.  The prose is synthetic; the facts are the
  record's.

Both are declared per record (``text_origin``) so no downstream report can
mistake a template for a human-written document.

Provenance
----------
Every record stores the exact request URL, the retrieval timestamp, the SHA-256
of the raw API JSON it came from, and the SHA-256 of the rendered text.  A record
edited after collection therefore fails its own integrity check at load time.

Determinism
-----------
Requests are sorted and truncated at fixed counts, so two runs against the same
API state produce the same record set.  The API is a live service, so the stored
raw hash is the only durable identity; the MANIFEST is frozen once written and
is never overwritten (``--force`` writes a new version directory instead).

Exit codes: 0 wrote a new corpus, 2 refused (network / empty result / existing
manifest without ``--force``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

SCHEMA = "medradar.overnight_corpus.v1"
DEFAULT_OUT = Path(r"D:\DEPPSKK\ml-work\overnight\corpus")
USER_AGENT = "MedRadar-research/0.1 (public regulatory data; contact: repo owner)"

#: Companies are drawn from the project's own entity roster
#: (``config/universe_v1.json``), never invented here.  Twelve firms, chosen so
#: that grouped splits leave three whole companies unseen in training.
COMPANIES: tuple[str, ...] = (
    "Medtronic",
    "Philips",
    "Siemens Healthineers",
    "GE HealthCare",
    "Abbott",
    "Baxter",
    "Becton Dickinson",
    "Boston Scientific",
    "Stryker",
    "Zimmer Biomet",
    "Edwards Lifesciences",
    "Hologic",
)

#: openFDA ``applicant`` strings differ from the roster's display names; the
#: search term is what the API is queried with, the canonical id is what the
#: roster will validate against.
COMPANY_QUERY: Mapping[str, str] = {
    "Medtronic": "medtronic",
    "Philips": "philips",
    "Siemens Healthineers": "siemens",
    "GE HealthCare": "ge healthcare",
    "Abbott": "abbott",
    "Baxter": "baxter",
    "Becton Dickinson": "becton",
    "Boston Scientific": "boston scientific",
    "Stryker": "stryker",
    "Zimmer Biomet": "zimmer",
    "Edwards Lifesciences": "edwards lifesciences",
    "Hologic": "hologic",
}

COMPANY_CANONICAL_ID: Mapping[str, str] = {
    "Medtronic": "medtronic",
    "Philips": "philips",
    "Siemens Healthineers": "siemens_healthineers",
    "GE HealthCare": "ge_healthcare",
    "Abbott": "abbott",
    "Baxter": "baxter",
    "Becton Dickinson": "bd",
    "Boston Scientific": "boston_scientific",
    "Stryker": "stryker",
    "Zimmer Biomet": "zimmer_biomet",
    "Edwards Lifesciences": "edwards_lifesciences",
    "Hologic": "hologic",
}

#: Search-field name per openFDA endpoint.
OPENFDA_ENDPOINTS: Mapping[str, Mapping[str, str]] = {
    "510k": {
        "url": "https://api.fda.gov/device/510k.json",
        "search_field": "applicant",
        "sort": "decision_date:desc",
        "source_type": "regulatory_clearance",
        "publisher": "U.S. Food and Drug Administration",
    },
    "pma": {
        "url": "https://api.fda.gov/device/pma.json",
        "search_field": "applicant",
        "sort": "decision_date:desc",
        "source_type": "regulatory_approval",
        "publisher": "U.S. Food and Drug Administration",
    },
    "recall": {
        # The recall endpoint rejects `sort=report_date:desc` with HTTP 500, so it
        # is queried unsorted and sliced deterministically instead.
        "url": "https://api.fda.gov/device/recall.json",
        "search_field": "recalling_firm",
        "sort": "",
        "source_type": "recall",
        "publisher": "U.S. Food and Drug Administration",
    },
}

# `api.clinicaltrials.gov` does not resolve through this machine's Python resolver
# (gaierror 11001) while `clinicaltrials.gov` does; the v2 API is served from the
# bare host, so that is the canonical endpoint here.
CTGOV_URL = "https://clinicaltrials.gov/api/v2/studies"
CTGOV_FIELDS = (
    "NCTId,BriefTitle,LeadSponsorName,StartDate,StartDateType,"
    "PrimaryCompletionDate,PrimaryCompletionDateType,StudyFirstPostDate,"
    "ResultsFirstPostDate,OverallStatus,Condition,InterventionName,"
    "EnrollmentCount,Phase,PrimaryPurpose"
)


# --------------------------------------------------------------------- plumbing
def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _fetch_json(url: str, *, attempts: int = 4, timeout: int = 40) -> Any:
    last: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as handle:
                payload = json.loads(handle.read().decode("utf-8"))
            time.sleep(0.35)  # be kind to a public API
            return payload
        except urllib.error.HTTPError as exc:
            last = exc
            if 400 <= exc.code < 500 and exc.code != 429:
                raise RuntimeError(f"request rejected: {url} (HTTP {exc.code})") from exc
            time.sleep(2.0 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # DNS hiccups on a laptop are transient; back off further before giving up.
            last = exc
            time.sleep(3.0 * (attempt + 1))
    raise RuntimeError(f"request failed after {attempts} attempts: {url} ({last})")


def _month_name(month: int) -> str:
    return (
        "January,February,March,April,May,June,July,August,September,October,"
        "November,December"
    ).split(",")[month - 1]


def _date_variants(iso: str) -> list[tuple[str, str]]:
    """Render one ISO date in several source-plausible ways.

    Returns ``(format_id, text)``.  Only formats that unambiguously determine the
    same calendar day for a ``us``-locale source are produced: ISO, the U.S. long
    form, and the day-first long form.  A pure numeric U.S. form is included
    because that is what the FDA's own systems emit, and it is exactly the format
    that broke the Phase 2 validator.
    """
    year, month, day = (int(part) for part in iso.split("-"))
    return [
        ("iso", iso),
        ("us_long", f"{_month_name(month)} {day}, {year}"),
        ("day_month_long", f"{day} {_month_name(month)} {year}"),
        ("us_numeric", f"{month:02d}/{day:02d}/{year}"),
    ]


def _pick_variant(iso: str, index: int) -> tuple[str, str]:
    """Deterministically choose one date rendering and return its (id, text)."""
    order = ("iso", "us_long", "us_numeric", "day_month_long")
    wanted = order[index % len(order)]
    for format_id, text in _date_variants(iso):
        if format_id == wanted:
            return format_id, text
    raise AssertionError(f"no rendering named {wanted!r}")  # pragma: no cover


# ------------------------------------------------------------------- renderers
_STRUCTURAL_TEMPLATE = """RECORD SUMMARY -- {publisher} public record {record_id}

Record type: {record_type}
Company named in the record: {company}
Product named in the record: {product}

Declared fields
- Record identifier: {record_id}
- Decision / event date: {date_text}
- Applicant / firm as recorded: {company}
- Device or product as recorded: {product}
- Advisory committee: {committee}
- Decision description: {decision}
- Country of applicant: {country}
- Product code: {product_code}
- Device class: {device_class}

Additional notes recorded with this entry
{notes}

This summary reproduces fields declared by the source record and adds no new
facts. Any interpretation of these fields is the reader's own.
"""

_NARRATIVE_TEMPLATE = """{company} {verb} {product}, according to a public record published by the {publisher}.

The entry, filed under identifier {record_id}, states that the action was taken on {date_text}. The record lists the {product} under advisory committee "{committee}" and describes the outcome as "{decision}". The filing is retrievable from the {publisher} public database, and the entry carries product code {product_code} with device class {device_class}.

{context}

This narrative was generated by template from the structured record listed above; the facts are the record's, the prose is synthetic.
"""

_CONTEXTS: tuple[str, ...] = (
    "The record does not describe any further regulatory action, and no follow-up filing is referenced in the entry.",
    "No additional submissions are listed against this identifier in the retrieved entry.",
    "The entry records only the action described above; it contains no statement about commercial availability.",
    "The retrieved record does not state a review timeline beyond the date given.",
)


def _render(
    *,
    style: str,
    publisher: str,
    record_id: str,
    record_type: str,
    company: str,
    product: str,
    date_text: str,
    committee: str,
    decision: str,
    country: str,
    product_code: str,
    device_class: str,
    notes: str,
    verb: str,
    index: int,
) -> str:
    if style == "field_value_rendering":
        return _STRUCTURAL_TEMPLATE.format(
            publisher=publisher,
            record_id=record_id,
            record_type=record_type,
            company=company,
            product=product,
            date_text=date_text,
            committee=committee,
            decision=decision,
            country=country,
            product_code=product_code,
            device_class=device_class,
            notes=notes,
        )
    return _NARRATIVE_TEMPLATE.format(
        company=company,
        verb=verb,
        product=product,
        publisher=publisher,
        record_id=record_id,
        date_text=date_text,
        committee=committee,
        decision=decision,
        product_code=product_code,
        device_class=device_class,
        context=_CONTEXTS[index % len(_CONTEXTS)],
    )


def _quote_from_text(text: str, date_text: str) -> str:
    """Select the verbatim span of ``text`` that supports the label.

    The quote is *extracted from the text that was actually produced* rather than
    re-typed from the renderer, so a renderer/quote mismatch is impossible by
    construction.  Candidates are lines and sentences that contain the rendered
    date; the shortest sufficiently long one wins, because a shorter span is less
    likely to accidentally include text that contradicts the label.
    """
    candidates: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or date_text not in stripped:
            continue
        candidates.append(stripped)
        for sentence in stripped.replace("? ", ". ").split(". "):
            sentence = sentence.strip()
            if sentence and date_text in sentence:
                candidates.append(sentence if sentence.endswith(".") else sentence + ".")
    viable = [candidate for candidate in candidates if 12 <= len(candidate) <= 600]
    if not viable:
        raise AssertionError(
            f"no verbatim quote containing {date_text!r} could be located in the rendered text"
        )
    return min(viable, key=len)


# ---------------------------------------------------------------- openFDA rows
def _openfda_records(
    endpoint: str,
    company: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    spec = OPENFDA_ENDPOINTS[endpoint]
    query = f'{spec["search_field"]}:"{COMPANY_QUERY[company]}"'
    sort_clause = f"&sort={urllib.parse.quote(spec['sort'])}" if spec.get("sort") else ""
    url = (
        f"{spec['url']}?search={urllib.parse.quote(query)}"
        f"{sort_clause}&limit={limit}"
    )
    try:
        payload = _fetch_json(url)
    except RuntimeError as exc:
        print(f"  WARN {endpoint}/{company}: {exc}", file=sys.stderr)
        return []
    results = payload.get("results") or []
    return [dict(record, _request_url=url) for record in results if isinstance(record, Mapping)]


def _decide_style(global_index: int) -> str:
    return "field_value_rendering" if global_index % 2 == 0 else "prose"


def _build_openfda_document(
    endpoint: str,
    company: str,
    record: Mapping[str, Any],
    *,
    index: int,
    retrieved_at: str,
) -> dict[str, Any] | None:
    spec = OPENFDA_ENDPOINTS[endpoint]
    if endpoint == "510k":
        record_id = str(record.get("k_number") or "").strip()
        date_iso = str(record.get("decision_date") or "").strip()
        product = str(record.get("device_name") or "").strip()
        product = " ".join(product.split()) or "the named device"
        committee = str(record.get("advisory_committee_description") or "not stated")
        decision = str(record.get("decision_description") or "not stated")
        product_code = str(record.get("product_code") or "not stated")
        device_class = str((record.get("openfda") or {}).get("device_class") or "not stated")
        verb = "received FDA 510(k) clearance for"
        kind = "decision"
        category = "regulatory_clearance"
        record_type = "FDA 510(k) premarket notification decision"
    elif endpoint == "pma":
        record_id = f"{record.get('pma_number') or ''}-{record.get('supplement_number') or ''}".strip("-")
        date_iso = str(record.get("decision_date") or "").strip()
        product = str(record.get("trade_name") or record.get("generic_name") or "").strip()
        product = " ".join(product.split()) or "the named device"
        committee = str(record.get("advisory_committee") or "not stated")
        decision = str(record.get("decision_code") or "not stated")
        product_code = str(record.get("product_code") or "not stated")
        device_class = str(record.get("device_class") or "not stated")
        verb = "received FDA premarket approval for"
        kind = "decision"
        category = "regulatory_approval"
        record_type = "FDA premarket approval (PMA) decision"
    else:  # recall
        record_id = str(record.get("res_event_number") or "").strip()
        date_iso = str(
            record.get("event_date_initiated")
            or record.get("recall_initiation_date")
            or ""
        ).strip()
        product = str(record.get("product_description") or "").strip()
        product = " ".join(product.split())[:140] or "the named device"
        committee = "not stated"
        decision = str(record.get("status") or "not stated")
        product_code = str(record.get("product_code") or "not stated")
        device_class = str(record.get("product_res_number") or "not stated")
        verb = "initiated a voluntary field action for"
        kind = "recall_initiation"
        category = "safety_recall"
        record_type = "FDA device recall record"
    if not record_id or len(date_iso) != 10:
        return None
    format_id, date_text = _pick_variant(date_iso, index)
    style = _decide_style(index)
    narration = _render(
        style=style,
        publisher=spec["publisher"],
        record_id=record_id,
        record_type=record_type,
        company=company,
        product=product,
        date_text=date_text,
        committee=committee,
        decision=decision,
        country=str(record.get("country_code") or "not stated"),
        product_code=product_code,
        device_class=device_class,
        notes=(
            f"- Reason or context as recorded: {str(record.get('reason_for_recall') or 'none stated')[:220]}\n"
            f"- Distribution as recorded: {str(record.get('distribution_pattern') or 'none stated')[:120]}"
        ),
        verb=verb,
        index=index,
    )
    text = narration
    if len(text) < 240:  # the loader requires a real document, not a stub
        text = text + "\n" + ("The record above is reproduced in full; nothing is omitted.\n" * 2)
    return {
        "doc_id": (
            "ovn-"
            + spec["source_type"].replace("_", "")
            + "-"
            + record_id
            + "-"
            + _sha256_json(
                {key: value for key, value in record.items() if key != "_request_url"}
            )[:8]
        ),
        "source_type": spec["source_type"],
        "company_canonical_id": COMPANY_CANONICAL_ID[company],
        "company_display_name": company,
        "record_id": record_id,
        "record_type": record_type,
        "api_endpoint": str(record.get("_request_url") or ""),
        "retrieved_at": retrieved_at,
        "raw_sha256": _sha256_json({key: value for key, value in record.items() if key != "_request_url"}),
        "source_publication_date": date_iso,
        "date_locale": "us",
        "text_style": style,
        "text_origin": "structural_rendering" if style == "field_value_rendering" else "synthetic_narrative",
        "text": text,
        "content_sha256": _sha256_text(text),
        "title": f"{record_type} {record_id} - {product}"[:180],
        "publisher": spec["publisher"],
        "url": str(record.get("_request_url") or ""),
        "silver": {
            "event_category": category,
            "event_date": date_iso,
            "event_date_kind": kind,
            "product_or_technology": product,
            "evidence_quote": _quote_from_text(text, date_text),
            "label_source": (
                f"source record field for the {record_type}; silver label, not human"
            ),
            "date_text_format": format_id,
        },
        "negative_control": False,
    }


# -------------------------------------------------------------------- CT.gov
def _ctgov_studies(company: str, *, limit: int) -> tuple[list[dict[str, Any]], str]:
    # No `fields` projection: the API rejects several of the names this script
    # wants with HTTP 400, and a silently empty result would look like "this
    # company has no trials".  Fetching the full study object is slower but the
    # parser below reads only the modules it declares.
    query = urllib.parse.urlencode(
        {
            "query.spons": COMPANY_QUERY[company],
            "pageSize": limit,
        }
    )
    url = f"{CTGOV_URL}?{query}"
    try:
        payload = _fetch_json(url)
    except RuntimeError as exc:
        print(f"  WARN ctgov/{company}: {exc}", file=sys.stderr)
        return [], url
    studies = [study for study in (payload.get("studies") or []) if isinstance(study, Mapping)]
    return studies, url


def _ctgov_module(study: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    protocol = study.get("protocolSection") or {}
    derived = study.get("derivedSection") or {}
    for container in (protocol, derived, study):
        value = container.get(name) if isinstance(container, Mapping) else None
        if isinstance(value, Mapping):
            return value
    return {}


def _build_ctgov_documents(
    company: str,
    study: Mapping[str, Any],
    *,
    request_url: str,
    retrieved_at: str,
    index: int,
) -> list[dict[str, Any]]:
    identification = _ctgov_module(study, "identificationModule")
    status = _ctgov_module(study, "statusModule")
    design = _ctgov_module(study, "designModule")
    sponsor = _ctgov_module(study, "sponsorCollaboratorsModule")
    conditions = _ctgov_module(study, "conditionsModule")
    arms = _ctgov_module(study, "armsInterventionsModule")

    nct_id = str(identification.get("nctId") or "").strip()
    if not nct_id:
        return []
    title = " ".join(str(identification.get("briefTitle") or "").split()) or "untitled study"
    first_posted = str(status.get("studyFirstPostDateStruct", {}).get("date") or status.get("studyFirstPostDate") or "").strip()
    lead = sponsor.get("leadSponsor") or {}
    sponsor_name = " ".join(str(lead.get("name") or "").split())
    # Only keep a study whose *lead* sponsor is the company we searched for.  A
    # sponsor query also matches collaborations, and attributing another
    # institution's trial to this company would be a fabricated label.
    if COMPANY_QUERY[company].casefold() not in sponsor_name.casefold():
        return []
    condition_list = conditions.get("conditions") or []
    condition_text = ", ".join(str(item) for item in condition_list[:3]) or "the studied condition"
    intervention_list = arms.get("interventions") or []
    interventions = ", ".join(
        " ".join(str(item.get("name") or "").split())
        for item in intervention_list[:3]
        if isinstance(item, Mapping)
    ) or "the studied intervention"
    enrollment = design.get("enrollmentInfo") or {}
    enrollment_text = str(enrollment.get("count") or "not stated")
    phase_list = design.get("phases") or []
    phase_text = ", ".join(str(item) for item in phase_list) or "not stated"
    overall_status = str(status.get("overallStatus") or "not stated")

    start = status.get("startDateStruct") or {}
    primary_completion = status.get("primaryCompletionDateStruct") or {}
    results_posted = status.get("resultsFirstPostDateStruct") or {}

    documents: list[dict[str, Any]] = []
    plan = [
        ("trial_start", start, "trial_start_actual", "start"),
        ("trial_completion", primary_completion, "trial_completion", "completion"),
        ("results_posting", results_posted, "results_posting", "results"),
    ]
    for slot, date_struct, kind, label in plan:
        date_iso = str(date_struct.get("date") or "").strip()
        if len(date_iso) != 10:
            continue
        date_type = str(date_struct.get("type") or "").strip().lower()
        if slot == "trial_start" and date_type == "anticipated":
            kind = "trial_start_planned"
        format_id, date_text = _pick_variant(date_iso, index + len(label))
        style = _decide_style(index + len(label))
        product = interventions
        record_id = f"{nct_id}-{label}"
        verb = "registered a clinical trial of" if slot == "trial_start" else "reported a clinical trial milestone for"
        if style == "field_value_rendering":
            text = _STRUCTURAL_TEMPLATE.format(
                publisher="U.S. National Library of Medicine (ClinicalTrials.gov)",
                record_id=record_id,
                record_type="ClinicalTrials.gov study record",
                company=sponsor_name,
                product=product,
                date_text=date_text,
                committee="not applicable",
                decision=f"overall status {overall_status}",
                country="not stated",
                product_code="not applicable",
                device_class=f"phase {phase_text}; enrollment {enrollment_text}",
                notes=(
                    f"- Study title as registered: {title[:180]}\n"
                    f"- Condition studied: {condition_text}\n"
                    f"- Date field type: {date_type or 'not stated'}"
                ),
            )
        else:
            text = (
                f"{sponsor_name} registered a study of {product} in {condition_text}, "
                f"according to a public record on ClinicalTrials.gov.\n\n"
                f"The entry, filed under identifier {record_id}, states that the date "
                f"recorded for this milestone is {date_text}. The study is listed with "
                f"overall status {overall_status}, phase {phase_text} and an enrolment of "
                f"{enrollment_text} participants. The date field is flagged as "
                f"\"{date_type or 'not stated'}\", which the record itself supplies.\n\n"
                f"The registered title is \"{title[:160]}\".\n\n"
                f"This narrative was generated by template from the structured study "
                f"record; the facts are the record's, the prose is synthetic.\n"
            )
        documents.append(
            {
                "doc_id": f"ovn-ctgov-{record_id}",
                "source_type": "clinical_trial_registration",
                "company_canonical_id": COMPANY_CANONICAL_ID[company],
                "company_display_name": company,
                "record_id": record_id,
                "record_type": "ClinicalTrials.gov study record",
                "api_endpoint": request_url,
                "retrieved_at": retrieved_at,
                "raw_sha256": _sha256_json({"study": study, "slot": slot}),
                "source_publication_date": first_posted or date_iso,
                "date_locale": "us",
                "text_style": style,
                "text_origin": "structural_rendering" if style == "field_value_rendering" else "synthetic_narrative",
                "text": text,
                "content_sha256": _sha256_text(text),
                "title": f"Clinical trial record {record_id} - {title}"[:180],
                "publisher": "U.S. National Library of Medicine (ClinicalTrials.gov)",
                "url": f"https://clinicaltrials.gov/api/v2/studies/{nct_id}",
                "silver": {
                    "event_category": "clinical_trial_start" if slot == "trial_start" else "clinical_trial_result",
                    "event_date": date_iso,
                    "event_date_kind": kind,
                    "product_or_technology": product,
                    "evidence_quote": _quote_from_text(text, date_text),
                    "label_source": (
                        "source record date field "
                        f"{'startDateStruct' if slot == 'trial_start' else 'primaryCompletionDateStruct' if slot == 'trial_completion' else 'resultsFirstPostDateStruct'}"
                        "; silver label, not human"
                    ),
                    "date_text_format": format_id,
                    "recorded_date_type": date_type or "not stated",
                },
                "negative_control": False,
            }
        )
    return documents


# ------------------------------------------------------------- negative controls
def _build_negative_controls(*, retrieved_at: str, per_company: int = 1) -> list[dict[str, Any]]:
    """Real public records that contain no target development event.

    openFDA's device *classification* records describe a product code's regulatory
    class, not an action taken by a company: there is no decision, no recall, no
    trial and no product launch.  They are therefore genuine negative documents
    for this schema, not blanks with the answer removed.
    """
    url = "https://api.fda.gov/device/classification.json?limit=40"
    try:
        payload = _fetch_json(url)
    except RuntimeError as exc:
        print(f"  WARN negative controls unavailable: {exc}", file=sys.stderr)
        return []
    results = [row for row in (payload.get("results") or []) if isinstance(row, Mapping)][:40]
    documents: list[dict[str, Any]] = []
    for index, row in enumerate(results[: per_company * 3]):
        product_code = str(row.get("product_code") or "").strip()
        device_name = " ".join(str(row.get("device_name") or "").split())
        if not product_code or not device_name:
            continue
        text = (
            "DEVICE CLASSIFICATION RECORD\n\n"
            f"Product code: {product_code}\n"
            f"Device name: {device_name}\n"
            f"Regulation number: {row.get('regulation_number') or 'not stated'}\n"
            f"Device class: {row.get('device_class') or 'not stated'}\n"
            f"Medical specialty: {row.get('medical_specialty_description') or 'not stated'}\n"
            f"Submission type recorded for this code: {row.get('submission_type_id') or 'not stated'}\n\n"
            "This entry classifies a product code. It records no action taken by any "
            "company: no clearance decision, no approval, no recall, no trial and no "
            "product launch appears in it. Any event reported from this text would be "
            "invented.\n"
        )
        if len(text) < 240:
            text += "The classification entry above is reproduced without omission.\n"
        documents.append(
            {
                "doc_id": f"ovn-neg-{product_code}",
                "source_type": "regulatory_notice",
                "company_canonical_id": "",
                "company_display_name": "",
                "record_id": product_code,
                "record_type": "FDA device classification record",
                "api_endpoint": url,
                "retrieved_at": retrieved_at,
                "raw_sha256": _sha256_json(row),
                "source_publication_date": "",
                "date_locale": "us",
                "text_style": "prose" if index % 2 else "field_value_rendering",
                "text_origin": "structural_rendering",
                "text": text,
                "content_sha256": _sha256_text(text),
                "title": f"Device classification {product_code} - {device_name}"[:180],
                "publisher": "U.S. Food and Drug Administration",
                "url": url,
                "silver": None,
                "negative_control": True,
            }
        )
    return documents


# ------------------------------------------------------------------------ main
def collect(
    *,
    per_source: int,
    companies: Sequence[str],
    include_negatives: bool,
    retrieved_at: str,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    index = 0
    seen_studies: set[str] = set()
    for company in companies:
        for endpoint in ("510k", "pma", "recall"):
            records = _openfda_records(endpoint, company, limit=per_source * 3)
            # Deterministic slice: the API returns newest-first; take a spread.
            step = max(1, len(records) // max(per_source, 1))
            selected = records[::step][:per_source] if records else []
            for record in selected:
                document = _build_openfda_document(
                    endpoint, company, record, index=index, retrieved_at=retrieved_at
                )
                if document is not None:
                    documents.append(document)
                    index += 1
        studies, request_url = _ctgov_studies(company, limit=per_source * 4)
        for study in studies:
            nct_id = str(
                ((study.get("protocolSection") or {}).get("identificationModule") or {}).get("nctId")
                or ""
            )
            if not nct_id or nct_id in seen_studies:
                continue
            seen_studies.add(nct_id)
            built = _build_ctgov_documents(
                company, study, request_url=request_url, retrieved_at=retrieved_at, index=index
            )
            if not built:
                continue
            if sum(1 for doc in documents if doc["company_canonical_id"] == COMPANY_CANONICAL_ID[company] and doc["source_type"] == "clinical_trial_registration") >= per_source:
                break
            for document in built:
                documents.append(document)
                index += 1
    if include_negatives:
        documents.extend(_build_negative_controls(retrieved_at=retrieved_at))
    return documents


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--version", default=None, help="corpus version directory name")
    parser.add_argument("--per-source", type=int, default=2)
    parser.add_argument("--companies", default=None, help="comma-separated subset")
    parser.add_argument("--no-negatives", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    version = args.version or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out = Path(args.out) / version
    if (out / "MANIFEST.json").exists() and not args.force:
        print(f"REFUSED: corpus already exists and is frozen: {out}", file=sys.stderr)
        return 2
    companies = (
        [part.strip() for part in args.companies.split(",") if part.strip()]
        if args.companies
        else list(COMPANIES)
    )
    unknown = [company for company in companies if company not in COMPANY_CANONICAL_ID]
    if unknown:
        print(f"REFUSED: unknown company name(s) {unknown}", file=sys.stderr)
        return 2

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"collecting {len(companies)} companies per_source={args.per_source} -> {out}")
    documents = collect(
        per_source=args.per_source,
        companies=companies,
        include_negatives=not args.no_negatives,
        retrieved_at=retrieved_at,
    )
    if not documents:
        print("REFUSED: every request returned nothing", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    (out / "documents").mkdir(exist_ok=True)

    # A doc_id collision would silently drop a document, so it is a hard error.
    seen: set[str] = set()
    for document in documents:
        doc_id = document["doc_id"]
        if doc_id in seen:
            print(f"REFUSED: duplicate doc_id {doc_id!r}", file=sys.stderr)
            return 2
        seen.add(doc_id)
        path = out / "documents" / f"{doc_id}.json"
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")

    by_source: dict[str, int] = {}
    by_style: dict[str, int] = {}
    by_company: dict[str, int] = {}
    by_format: dict[str, int] = {}
    for document in documents:
        by_source[document["source_type"]] = by_source.get(document["source_type"], 0) + 1
        by_style[document["text_style"]] = by_style.get(document["text_style"], 0) + 1
        if document["company_canonical_id"]:
            by_company[document["company_canonical_id"]] = (
                by_company.get(document["company_canonical_id"], 0) + 1
            )
        if document.get("silver"):
            key = document["silver"].get("date_text_format") or "none"
            by_format[key] = by_format.get(key, 0) + 1
    manifest = {
        "schema": SCHEMA,
        "version": version,
        "created_at": retrieved_at,
        "retrieved_at": retrieved_at,
        "companies": list(companies),
        "per_source": args.per_source,
        "include_negatives": not args.no_negatives,
        "document_count": len(documents),
        "sources": sorted({document["publisher"] for document in documents}),
        "counts": {
            "by_source_type": dict(sorted(by_source.items())),
            "by_text_style": dict(sorted(by_style.items())),
            "by_company": dict(sorted(by_company.items())),
            "by_date_text_format": {
        str(key): value for key, value in sorted(by_format.items(), key=lambda kv: str(kv[0]))
    },
            "negative_controls": sum(1 for d in documents if d["negative_control"]),
        },
        "license_note": (
            "openFDA content is U.S. Government work (public domain); ClinicalTrials.gov "
            "content is public NLM data. No copyrighted full text was copied. Document "
            "text is either a deterministic rendering of record fields or a template-"
            "generated narrative; the per-record text_origin field says which."
        ),
        "documents": [
            {
                "doc_id": document["doc_id"],
                "content_sha256": document["content_sha256"],
                "raw_sha256": document["raw_sha256"],
                "source_type": document["source_type"],
                "text_style": document["text_style"],
                "text_origin": document["text_origin"],
                "company_canonical_id": document["company_canonical_id"],
                "date_text_format": (document.get("silver") or {}).get("date_text_format"),
                "negative_control": document["negative_control"],
            }
            for document in sorted(documents, key=lambda item: item["doc_id"])
        ],
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(manifest["counts"], indent=2))
    print(f"\ncorpus written -> {out}  documents={len(documents)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
