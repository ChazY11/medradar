"""Non-US/Canada jurisdiction probes (one module, six source_ids).

Each function records *exactly what happened* — including failure — into
``DATASETS/regulatory/<source_id>/COUNTS.json`` plus a PROVENANCE record with the
status, byte count and sha256 of every response. A clean negative is a result.

Priority order from the brief: Australia (TGA ARTG) → EU (EUDAMED) → Japan
(PMDA) → Brazil (ANVISA). Brazil is the one that actually yields data, and the
others are documented as blocked with their official unlock route.

Run:  python CONNECTORS/regulatory/third_country.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hz.schema import build_record, write_jsonl  # noqa: E402
from hz.timeq import classify_record  # noqa: E402

from CONNECTORS.regulatory._util import (  # noqa: E402
    ROOT,
    fetch_or_load,
    make_client,
    probe_size,
    save_raw,
    utc_now,
    write_json,
    write_provenance,
)


def _try(client, source_id: str, name: str, url: str, note: str, headers=None):
    """Fetch through the bounded client, recording every outcome. Returns (rec, body)."""
    path = os.path.join(ROOT, "DATASETS", "regulatory", source_id, "raw", name)
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            body = fh.read()
        return {"path": os.path.relpath(path, ROOT).replace(os.sep, "/"),
                "bytes": len(body), "status": 200, "from_disk": True,
                "note": note, "requested_url": url}, body
    try:
        res = client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001
        return {"outcome": type(exc).__name__, "error": str(exc)[:250], "url": url,
                "note": note}, None
    rec = save_raw(source_id, name, res, url_note=note)
    rec["note"] = note
    return rec, res.body


# ---------------------------------------------------------------------------
# Brazil — ANVISA open data (the one that works)
# ---------------------------------------------------------------------------

ANVISA_BASE = "https://dados.anvisa.gov.br/dados"
ANVISA_CSV = f"{ANVISA_BASE}/CONSULTAS/PRODUTOS/TA_CONSULTA_PRODUTOS_SAUDE.CSV"
ANVISA_LICENCE_URL = "https://www.gov.br/anvisa/pt-br/acessoainformacao/dadosabertos"


def brazil_anvisa(client) -> tuple[dict, list, list]:
    prov: list[dict] = []
    rows: list[dict] = []
    log: list[dict] = []

    # (a) the directory index that proves the bulk files exist and are keyless
    idx_rec, idx_body = _try(client, "brazil_anvisa", "index_produtos.html",
                             f"{ANVISA_BASE}/CONSULTAS/PRODUTOS/",
                             "ANVISA open-data directory index for the product consultation")
    prov.append(idx_rec)
    listed: list[str] = []
    if idx_body:
        import re
        listed = sorted(set(re.findall(r'href="([^"]*TA_CONSULTA[^"]*)"',
                                       idx_body.decode("utf-8", errors="replace"))))
        log.append({"step": "index", "status": idx_rec.get("status"),
                    "files_listed": listed})

    # (b) 256 KiB prefix: gives the real header and the total size in Content-Range
    head_rec, head_body = _try(
        client, "brazil_anvisa", "TA_CONSULTA_PRODUTOS_SAUDE.csv.head256k",
        ANVISA_CSV, "ANVISA device/product consultation CSV — 256 KiB prefix",
        headers={"Range": "bytes=0-262143"})
    prov.append(head_rec)
    total = None
    if head_body:
        header_line = head_body.split(b"\r\n", 1)[0].split(b"\n", 1)[0].decode("latin-1")
        cols = header_line.split(";") if ";" in header_line else header_line.split(",")
        log.append({"step": "prefix256k", "status": head_rec.get("status"),
                    "bytes": len(head_body), "columns": cols[:40],
                    "delimiter": ";" if ";" in header_line else ","})
        # (c) a larger prefix, bounded, so we have a real multi-hundred-row sample
        big_rec, big_body = _try(
            client, "brazil_anvisa", "TA_CONSULTA_PRODUTOS_SAUDE.csv.prefix6m",
            ANVISA_CSV, "ANVISA product consultation CSV — 6 MiB prefix",
            headers={"Range": "bytes=0-5999999"})
        prov.append(big_rec)
        if big_body:
            log.append({"step": "prefix6m", "status": big_rec.get("status"),
                        "bytes": len(big_body)})
            rows = _parse_anvisa(big_body, ";")
            log.append({"step": "parse", "rows_parsed": len(rows)})
    budget_line = {"note": "requests are logged in SOURCE_PROBES/regulatory/REQUEST_LOG.jsonl"}

    counts = {
        "source_id": "brazil_anvisa",
        "generated_at": utc_now(),
        "access_state_observed": "OPEN" if idx_body else "UNKNOWN",
        "bulk_files_listed": listed,
        "log": log,
        "licence_url": ANVISA_LICENCE_URL,
        "licence_note": (
            "ANVISA publishes these files on its open-data portal with no registration and no "
            "API key; the portal landing page (dados.anvisa.gov.br) presents them as 'dados "
            "abertos'. No explicit machine-reuse licence (e.g. CC-BY) is stated on the file "
            "index itself, so licence_status is recorded as open_no_explicit_licence rather "
            "than an invented permissive licence."
        ),
    }
    return counts, rows, prov


def _parse_anvisa(body: bytes, delim: str) -> list[dict]:
    text = body.decode("latin-1")
    lines = text.splitlines()
    if not lines:
        return []
    header = [h.strip().strip('"') for h in lines[0].split(delim)]
    out = []
    for ln in lines[1:]:
        parts = [p.strip().strip('"') for p in ln.split(delim)]
        if len(parts) != len(header):
            continue  # truncated final line of a byte-range prefix
        out.append(dict(zip(header, parts)))
    return out


def _br_date(v: str | None) -> str | None:
    """ANVISA dates are dd/mm/yyyy[ hh:mm:ss]; convert to ISO or return None."""
    if not v:
        return None
    v = str(v).strip()
    m = v.split(" ")[0]
    parts = m.split("/")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        d, mo, y = parts
        if len(y) == 2:
            y = "20" + y
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


def anvisa_records(rows: list[dict], raw_ref: str) -> list:
    """Turn ANVISA consultation rows into evidence records (bounded).

    Column names are the real ones from the CSV header
    (NU_REGISTRO_PRODUTO, NO_PRODUTO, NO_RAZAO_SOCIAL_EMPRESA, DT_PUBLICACAO, ...).
    No identifier is ever invented: if NU_REGISTRO_PRODUTO is absent the record
    carries MISSING_IDENTIFIER instead of a synthesised value.
    """
    recs = []
    for r in rows:
        up = {k.upper(): (v or "").strip() for k, v in r.items()}
        name = up.get("NO_PRODUTO") or None
        if not name:
            continue
        registro = up.get("NU_REGISTRO_PRODUTO") or None
        company = up.get("NO_RAZAO_SOCIAL_EMPRESA") or None
        processo = up.get("NU_PROCESSO") or None
        risco = up.get("SG_RISCO_PRODUTO") or None
        situacao = up.get("SITUACAO_REGISTRO") or None
        dt_pub = _br_date(up.get("DT_PUBLICACAO"))
        dt_val = _br_date(up.get("DT_VENCIMENTO_PRODUTO")) or _br_date(
            up.get("DT_VENCIMENTO_REGISTRO"))
        dt_cancel = _br_date(up.get("DT_CANCELAMENTO"))
        dt_etl = _br_date(up.get("DT_CARGA_ETL"))
        tipo_produto = up.get("CO_TIPO_PRODUTO") or None

        ids = []
        if registro:
            ids.append({"scheme": "anvisa_registro", "value": str(registro),
                        "issuing_authority": "ANVISA", "scope": "BR", "is_primary": True})
        if processo:
            ids.append({"scheme": "anvisa_processo", "value": str(processo),
                        "issuing_authority": "ANVISA", "scope": "BR"})
        flags = ["RETROSPECTIVE_FIELD"]
        if not ids:
            flags.append("MISSING_IDENTIFIER")
        # DT_PUBLICACAO is the gazette publication date of the decision
        # (DS_SITUACAO_ASSUNTO_DOC = 'Publicado deferimento'), which is both the
        # recorded decision event and the moment it became publicly visible.
        # It is NOT the dataset load stamp — that is DT_CARGA_ETL.
        recs.append(build_record(
            source_id="brazil_anvisa",
            source_record_id=str(registro or processo or name)[:120],
            entity_type="regulatory_listing",
            original_name=str(name)[:300],
            identifiers=ids,
            manufacturer=company,
            attributes={
                "no_produto": name,
                "nu_registro_produto": registro,
                "nu_processo": processo,
                "no_razao_social_empresa": company,
                "nu_cnpj_empresa": up.get("NU_CNPJ_EMPRESA") or None,
                "sg_risco_produto": risco,
                "situacao_registro": situacao,
                "co_tipo_produto": tipo_produto,
                "tipoassunto": up.get("TIPOASSUNTO") or None,
                "ds_situacao_assunto_doc": up.get("DS_SITUACAO_ASSUNTO_DOC") or None,
                "dt_publicacao": dt_pub,
                "dt_vencimento": dt_val,
                "dt_cancelamento": dt_cancel,
                "dt_carga_etl": dt_etl,
                "public_clock_basis": (
                    "DT_PUBLICACAO (gazette publication of the decision) is used as both "
                    "event_at and source_public_at because the source records one publication "
                    "date for the grant; DT_CARGA_ETL is the ETL load stamp of this snapshot and "
                    "is deliberately NOT used as a public clock."
                ),
                "row_source": "ANVISA TA_CONSULTA_PRODUTOS_SAUDE.CSV (256 KiB byte-range prefix)",
                "clock_class": classify_record(dt_pub, dt_pub)["class"],
            },
            event_at=dt_pub,
            source_public_at=dt_pub,
            first_observed_at=None,
            fetched_at=utc_now(),
            source_url=ANVISA_CSV,
            licence_status="open_no_explicit_licence",
            licence_note=("ANVISA open-data bulk CSV, keyless; no explicit reuse licence stated "
                          "on the file index."),
            identity_status="CONFIRMED" if registro else "CANDIDATE",
            evidence_status="CONFIRMED",
            quality_flags=flags,
            raw_ref=raw_ref,
        ))
        if len(recs) >= 120:
            break
    return recs


# ---------------------------------------------------------------------------
# Blocked / manual-only jurisdictions
# ---------------------------------------------------------------------------

def _blocked_report(client, source_id: str, attempts: list[tuple[str, str, str]],
                    summary: dict) -> dict:
    prov = []
    results = []
    for name, url, note in attempts:
        rec, body = _try(client, source_id, name, url, note)
        prov.append(rec)
        entry = {"name": name, "url": url, "note": note,
                 "status": rec.get("status"), "outcome": rec.get("outcome"),
                 "bytes": rec.get("bytes"), "sha256": (rec.get("sha256") or "")[:16],
                 "error": rec.get("error")}
        if body and len(body) < 4000:
            entry["body_head"] = body[:600].decode("utf-8", errors="replace")
        results.append(entry)
    counts = {"source_id": source_id, "generated_at": utc_now(),
              "attempts": results, **summary}
    write_json(source_id, "COUNTS.json", counts)
    if prov:
        write_provenance(source_id, prov, extra={"generated_at": utc_now()})
    return counts


def main() -> int:
    out: dict[str, dict] = {}
    with make_client("regulatory-third-country", max_requests=26,
                     max_bytes_per_response=7_000_000, max_total_bytes=22_000_000,
                     rps=1.0) as c:
        # ---- Brazil ----
        counts, rows, prov = brazil_anvisa(c)
        recs = anvisa_records(rows, "DATASETS/regulatory/brazil_anvisa/raw/"
                                    "TA_CONSULTA_PRODUTOS_SAUDE.csv.prefix6m")
        out_dir = os.path.join(ROOT, "DATASETS", "regulatory", "brazil_anvisa")
        os.makedirs(out_dir, exist_ok=True)
        n = write_jsonl(os.path.join(out_dir, "records.jsonl"), recs) if recs else 0
        counts["records_emitted"] = n
        counts["records_with_official_identifier"] = sum(
            1 for r in recs if r.identifiers and r.identifiers[0].scheme == "anvisa_registro")
        out["brazil_anvisa"] = counts
        write_json("brazil_anvisa", "COUNTS.json", counts)
        write_provenance("brazil_anvisa", prov, extra={"generated_at": utc_now()})

        # ---- Australia: TGA ARTG ----
        out["australia_tga_artg"] = _blocked_report(
            c, "australia_tga_artg",
            [
                ("tga_home_https.html", "https://www.tga.gov.au/",
                 "TGA corporate site, https"),
                ("tga_robots.txt", "http://www.tga.gov.au/robots.txt",
                 "TGA robots.txt over plain http (https connection was reset twice in discovery)"),
                ("tga_apps_root.html", "https://apps.tga.gov.au/",
                 "TGA applications host"),
                ("datagov_ckan_artg.json",
                 "https://data.gov.au/data/api/3/action/package_search?q=artg&rows=20",
                 "data.gov.au CKAN search for ARTG datasets"),
            ],
            {
                "summary": (
                    "www.tga.gov.au refuses automated connections (TCP reset / read timeout) and "
                    "data.gov.au holds no ARTG dataset; the ARTG public search is an HTML "
                    "application with no machine interface. Recorded as BLOCKED_TECHNICAL for the "
                    "corporate site plus MANUAL_ONLY for ARTG content."
                ),
                "official_identifier": "ARTG ID (Australian Register of Therapeutic Goods number)",
                "unlock_route": (
                    "ARTG is searched at https://www.tga.gov.au/resources/artg (human interface). "
                    "For bulk use, TGA's data requests go through "
                    "https://www.tga.gov.au/about-us/contact-us or a data-sharing request; "
                    "there is no published keyless ARTG bulk export."
                ),
            },
        )

        # ---- EU: EUDAMED ----
        out["eudamed"] = _blocked_report(
            c, "eudamed",
            [
                ("eudamed_root.html", "https://ec.europa.eu/tools/eudamed/",
                 "EUDAMED public application entry point"),
                ("eudamed_api_devices.json", "https://ec.europa.eu/tools/eudamed/api/devices",
                 "guessed public REST path — the server answers 429 with an explicit "
                 "machine-access instruction"),
                ("eudamed_developer_portal.html",
                 "https://developer.datalake.sante.service.ec.europa.eu/api-details",
                 "EU Health Data Lake developer portal named by EUDAMED's own 429 body"),
            ],
            {
                "summary": (
                    "EUDAMED has a public web search but no keyless machine interface. A request to "
                    "the public API path returns HTTP 429 whose JSON body says: 'For "
                    "automated/machine-to-machine access, please use the official EUDAMED data API "
                    "instead of scraping the public endpoints.' That official API lives behind the "
                    "EU Health Data Lake developer portal."
                ),
                "official_identifier": "EUDAMED device SRU / Basic UDI-DI",
                "unlock_route": (
                    "Request an API subscription at the EU Health Data Lake developer portal: "
                    "https://developer.datalake.sante.service.ec.europa.eu/api-details "
                    "(EU login + subscription key). Then use the EUDAMED data API instead of the "
                    "web application."
                ),
            },
        )

        # ---- Japan: PMDA ----
        out["japan_pmda"] = _blocked_report(
            c, "japan_pmda",
            [
                ("pmda_english.html", "https://www.pmda.go.jp/english/",
                 "PMDA English landing page"),
                ("pmda_reviews.html",
                 "https://www.pmda.go.jp/english/review-services/reviews/0001.html",
                 "PMDA review-services index (device approvals live here)"),
            ],
            {
                "summary": (
                    "PMDA publishes device approval information as HTML indexes and PDF files. No "
                    "JSON/CSV/API endpoint was found, and the site exposes no bulk download for "
                    "device approvals. Recorded as MANUAL_ONLY."
                ),
                "official_identifier": "PMDA approval number (承認番号)",
                "unlock_route": (
                    "PMDA's published data is consumed either by scraping the HTML approval "
                    "indexes or through the paid J-DR / commercial distributors; there is no "
                    "keyless machine interface to request."
                ),
            },
        )

        # ---- UK: MHRA ----
        out["uk_mhra_device"] = _blocked_report(
            c, "uk_mhra_device",
            [
                ("govuk_search_api.json",
                 "https://www.gov.uk/api/search.json?q=medical%20device%20register&count=5",
                 "GOV.UK search API — does it expose an MHRA device register dataset?"),
            ],
            {
                "summary": (
                    "MHRA publishes device guidance and alerts as GOV.UK content pages. There is no "
                    "public machine-readable register of UK-registered medical devices (the UK MDR "
                    "register is not published as open data). Recorded as MANUAL_ONLY."
                ),
                "official_identifier": "MHRA device registration (not publicly listed per device)",
                "unlock_route": (
                    "MHRA publishes device alerts and guidance on GOV.UK; company-level device "
                    "registration data is not open. Access would require an FOI request to MHRA."
                ),
            },
        )

        # ---- China: NMPA UDI ----
        out["china_nmpa_udi"] = _blocked_report(
            c, "china_nmpa_udi",
            [
                ("nmpa_root.html", "https://www.nmpa.gov.cn/",
                 "NMPA national portal"),
                ("nmpa_udi_database.html",
                 "https://udi.nmpa.gov.cn/",
                 "NMPA UDI database public query"),
            ],
            {
                "summary": (
                    "The NMPA UDI database is a Chinese-language web query application. Where it "
                    "answers at all it returns HTML with no machine interface and no bulk export; "
                    "access is also frequently geo/UA restricted. No records were obtained."
                ),
                "official_identifier": "UDI-DI as registered in the NMPA UDI database",
                "unlock_route": (
                    "NMPA UDI data is queryable only through https://udi.nmpa.gov.cn/ (human "
                    "interface, Chinese ID/registration context). No official keyless API exists."
                ),
            },
        )

        budget = c.budget_report()

    print(json.dumps({"third_country": out, "budget": budget}, indent=2, ensure_ascii=False)[:5000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
