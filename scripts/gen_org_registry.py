"""Generate medradar/product/identity/organizations.json.

The registry is the single source of truth for *which applicant names belong to which
tracked organization*. It is deliberately a static, reviewable file: a mapping decision is a
governance artefact, not an inference the API makes at request time.

Base layer: the repository roster (config/companies_device.json) which was curated for the
research pipeline. Extra layer: organizations absent from that roster (Draeger, Mindray, plus
six additional non-US manufacturers used to test search generalisation). Extra spells are
ported from the reviewed alias set produced on the PRODUCT/2.0 branch (PR #12) where
available, and are marked pending_review here.

Run:  python scripts/gen_org_registry.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "companies_device.json"
OUT = ROOT / "medradar" / "product" / "identity" / "organizations.json"

# Basis for an applicant spelling. "brand" is the honest default for a curated roster alias:
# the string identifies the company's commercial activity without asserting a legal form.
SUBSIDIARY_SPELLINGS = {
    "COVIDIEN", "COVIDIEN LP", "MEDTRONIC MINIMED", "MEDTRONIC SOFAMOR DANEK",
    "MEDTRONIC VASCULAR", "MEDTRONIC NEUROMODULATION", "MEDTRONIC CRYOCATH", "MEDTRONIC XOMED",
    "ST JUDE MEDICAL", "ST JUDE MEDICAL CARDIOLOGY", "GUILDANT", "GUIDANT", "BIOMET",
    "BIOMET MICROFIXATION", "C R BARD", "BARD ACCESS SYSTEMS", "BD BARD", "SMITHS MEDICAL",
    "NUVASIVE", "VARIAN MEDICAL SYSTEMS", "AESCULAP", "FUJIFILM SONOSITE", "TOSHIBA MEDICAL",
    "NOBEL BIOCARE", "ORMCO", "COOPERVISION", "COOPER SURGICAL", "MERIT MEDICAL SYSTEMS",
    "PENTAX MEDICAL", "MINDRAY DS USA, INC.", "ADVANCED BIONICS", "COCHLEAR AMERICAS",
    "ELEKTA INSTRUMENT", "NIHON KOHDEN AMERICA", "MAQUET", "GETINGE USA", "SYSMEX AMERICA",
    "SHENZHEN MINDRAY BIO-MEDICAL ELECTRONICS CO., LTD.", "SHENZHEN MINDRAY BIOMEDICAL ELECTRONICS CO., LTD.",
    "MINDRAY BIO-MEDICAL ELECTRONICS CO., LTD.", "MINDRAY NORTH AMERICA",
    "DRAEGER MEDICAL SYSTEMS, INC.", "DRAEGER MEDICAL, INC.", "DRAEGER MEDICAL GMBH",
    "DRAEGER MEDICAL B.V.", "DRAEGER MEDICAL INFANT CARE, INC.", "DRAEGER, INC.",
    "DRAGER, INC.", "DRAGER MEDICAL GMBH", "DRAGER MEDICAL B.V.", "NATIONAL DRAEGER, INC.",
    "SHANGHAI DRAEGER MEDICAL INSTRUMENT CO., LTD.", "DRAGER MEDIZINTECHNIK GMBH",
    "DRAEGER MEDICAL AG & CO. KG", "DRAEGER MEDICAL AG & CO. KGAA", "DRAGER MEDICAL AG & CO. KGAA",
    "DRAEGERWERK AG", "DRAEGERWERK AG & CO KGAA", "DRAGERWERK AG", "DRAGERWERK AG & CO KGAA",
    "DRAEGER MEDICAL SYTEMS, INC.", "DRAEGET MEDICAL AG & CO. KGAA",
    "INSTITUT STRAUMANN", "STRAUMANN", "PHONAK", "SONOVA",
}
HISTORICAL_SPELLINGS = {
    "TYCO HEALTHCARE", "GUIDANT", "GUILDANT", "SMITHS MEDICAL", "TOSHIBA MEDICAL",
    "DRAEGERWERK AG", "DRAEGERWERK AG & CO KGAA", "DRAGERWERK AG", "DRAGERWERK AG & CO KGAA",
    "NATIONAL DRAEGER, INC.", "DRAEGET MEDICAL AG & CO. KGAA", "VARIAN MEDICAL SYSTEMS",
}

# Enriched entries. Everything here is company identity metadata maintained by MedRadar and
# NOT derived from FDA records. Record-derived facts must never live in this file.
FEATURED = {
    "medtronic": {
        "legal_name": "Medtronic plc",
        "ticker": "MDT",
        "exchange": "NYSE",
        "country": "IE",
        "country_name": "Ireland",
        "organization_type": "public_company",
        "description": (
            "Medtronic plc is headquartered in Dublin, Ireland and reports its medical device "
            "activity across cardiovascular, neuromodulation, surgical and diabetes businesses. "
            "FDA records for those businesses appear under a set of Medtronic legal names, and "
            "under Covidien and Tyco Healthcare applicant names for products that joined the "
            "company through the 2015 acquisition."
        ),
        "review_status": "curated",
        "metadata_source": "MedRadar organization registry (company public identity); not derived from FDA records",
        "brands": ["Medtronic", "Covidien", "MiniMed"],
        "extra_accept": [
            ("MEDTRONIC", "brand", "curated"),
            ("MEDTRONIC MINIMED", "subsidiary", "curated"),
            ("MEDTRONIC SOFAMOR DANEK", "subsidiary", "curated"),
            ("MEDTRONIC VASCULAR", "subsidiary", "curated"),
            ("MEDTRONIC NEUROMODULATION", "subsidiary", "curated"),
            ("MEDTRONIC CRYOCATH", "subsidiary", "curated"),
            ("MEDTRONIC XOMED", "subsidiary", "curated"),
            ("MEDTRONIC PUERTO RICO", "subsidiary", "curated"),
            ("MEDTRONIC BAKKEN", "subsidiary", "curated"),
            ("COVIDIEN", "subsidiary", "curated"),
            ("COVIDIEN LP", "subsidiary", "curated"),
            ("TYCO HEALTHCARE", "historical_name", "curated"),
        ],
        "reject": [
            ("MEDTRONIC ENGINEERING AND INNOVATION CENTER", "reviewed 2026-11-15: internal R&D site, no separate FDA applicant role in the collected scope"),
        ],
        "ownership_note": (
            "Covidien and Tyco Healthcare spellings are treated as Medtronic applicants because the "
            "business was acquired in 2015. Historical ownership before that date is recorded as a "
            "declared relation, not re-derived per record."
        ),
    },
    "ge_healthcare": {
        "legal_name": "GE HealthCare Technologies Inc.",
        "ticker": "GEHC",
        "exchange": "Nasdaq",
        "country": "US",
        "country_name": "United States",
        "organization_type": "public_company",
        "description": (
            "GE HealthCare Technologies Inc. is headquartered in Chicago, United States and became "
            "an independent company in January 2023. Its FDA records appear mainly under GE Medical "
            "Systems and GE Healthcare applicant names, including records dated before the spin-off."
        ),
        "review_status": "curated",
        "metadata_source": "MedRadar organization registry (company public identity); not derived from FDA records",
        "brands": ["GE HealthCare", "GE Medical Systems"],
        "extra_accept": [
            ("GE HEALTHCARE", "brand", "curated"),
            ("GE MEDICAL SYSTEMS", "subsidiary", "curated"),
            ("GE HEALTHCARE GLOBAL", "subsidiary", "curated"),
            ("GE MEDICAL", "brand", "curated"),
            ("GE MEDICAL SYSTEMS INFORMATION TECHNOLOGIES", "subsidiary", "curated"),
        ],
        "reject": [],
        "ownership_note": (
            "Records before January 2023 were filed while the business was part of General Electric. "
            "They are attributed to GE HealthCare because the product business moved with the spin-off; "
            "the parent relationship is declared, not inferred per record."
        ),
    },
    "philips": {
        "legal_name": "Koninklijke Philips N.V.",
        "ticker": "PHG",
        "exchange": "NYSE (also PHIA on Euronext Amsterdam)",
        "country": "NL",
        "country_name": "Netherlands",
        "organization_type": "public_company",
        "description": (
            "Koninklijke Philips N.V. is headquartered in Amsterdam, Netherlands. Its US medical "
            "device activity appears under Philips North America, Philips Medical Systems and "
            "related applicant names, alongside Philips Healthcare."
        ),
        "review_status": "curated",
        "metadata_source": "MedRadar organization registry (company public identity); not derived from FDA records",
        "brands": ["Philips", "Philips Healthcare"],
        "extra_accept": [
            ("PHILIPS", "brand", "curated"),
            ("PHILIPS HEALTHCARE", "brand", "curated"),
            ("PHILIPS MEDICAL SYSTEMS", "subsidiary", "curated"),
            ("PHILIPS NORTH AMERICA", "subsidiary", "curated"),
            ("PHILIPS ULTRASOUND", "subsidiary", "curated"),
            ("PHILIPS IMAGE GUIDED THERAPY", "subsidiary", "curated"),
            ("PHILIPS ELECTRONICS NORTH AMERICA", "subsidiary", "curated"),
        ],
        "reject": [],
        "ownership_note": "Applicant names are US operating entities of the Philips group; the group relation is declared, not inferred.",
    },
    "draeger": {
        "legal_name": "Draegerwerk AG & Co. KGaA",
        "ticker": "DRW3",
        "exchange": "XETRA",
        "country": "DE",
        "country_name": "Germany",
        "organization_type": "public_company",
        "description": (
            "Draegerwerk AG & Co. KGaA is headquartered in Luebeck, Germany and supplies anaesthesia, "
            "ventilation and patient monitoring equipment. FDA records appear under several Draeger "
            "or Drager legal-name spellings; both spellings are kept because they are distinct strings "
            "in the source data."
        ),
        "review_status": "pending_review",
        "metadata_source": "MedRadar organization registry (company public identity); attribution list ported from the reviewed PRODUCT/2.0 alias set (PR #12)",
        "brands": ["Draeger", "Drager"],
        "acl": [
            ("Draeger Medical, Inc.", "subsidiary", "pending_review"),
            ("Draeger Medical Systems, Inc.", "subsidiary", "pending_review"),
            ("Draeger Medical Sytems, Inc.", "subsidiary", "pending_review"),
            ("Draeger Medical AG & Co. KG", "subsidiary", "pending_review"),
            ("Draeger Medical AG & Co. Kgaa", "subsidiary", "pending_review"),
            ("Draegerwerk AG & CO Kgaa", "legal_name", "pending_review"),
            ("Draegerwerk Ag & Co. Kgaa", "legal_name", "pending_review"),
            ("Draeget Medical AG & Co. Kgaa", "legal_name", "pending_review"),
            ("Draeger Medical GmbH", "subsidiary", "pending_review"),
            ("Draeger Medical B.V.", "subsidiary", "pending_review"),
            ("Draeger Medical Infant Care, Inc.", "subsidiary", "pending_review"),
            ("Draeger, Inc.", "subsidiary", "pending_review"),
            ("Draegerwerk AG", "historical_name", "pending_review"),
            ("Drager, Inc.", "subsidiary", "pending_review"),
            ("Drager Medizintechnik GmbH", "subsidiary", "pending_review"),
            ("Drager Medical AG & Co. Kgaa", "subsidiary", "pending_review"),
            ("Dragerwerk AG", "historical_name", "pending_review"),
            ("Dragerwerk AG & CO Kgaa", "legal_name", "pending_review"),
            ("Drager Medical GmbH", "subsidiary", "pending_review"),
            ("Drager Medical B.V.", "subsidiary", "pending_review"),
            ("National Draeger, Inc.", "historical_name", "pending_review"),
            ("Shanghai Draeger Medical Instrument Co., Ltd.", "subsidiary", "pending_review"),
        ],
        "reject": [
            ("Drager Safety", "reviewed: safety division gas-detection products are not the medical business"),
        ],
        "ownership_note": "Subsidiary spellings are the Dräger group's US operating entities; the group relation is pending human review, not inferred per record.",
    },
    "mindray": {
        "legal_name": "Shenzhen Mindray Bio-Medical Electronics Co., Ltd.",
        "ticker": "300760",
        "exchange": "SZSE",
        "country": "CN",
        "country_name": "China",
        "organization_type": "public_company",
        "description": (
            "Shenzhen Mindray Bio-Medical Electronics Co., Ltd. is headquartered in Shenzhen, China "
            "and manufactures patient monitoring, ultrasound and in-vitro diagnostics equipment. Its "
            "FDA records appear under Shenzhen Mindray legal names and Mindray DS USA operating names."
        ),
        "review_status": "pending_review",
        "metadata_source": "MedRadar organization registry (company public identity); attribution list ported from the reviewed PRODUCT/2.0 alias set (PR #12)",
        "brands": ["Mindray"],
        "acl": [
            ("Shenzhen Mindray Bio-Medical Electronics Co., Ltd.", "legal_name", "pending_review"),
            ("Shenzhen Mindray Bio-Meidcal Electronics Co., Ltd.", "legal_name", "pending_review"),
            ("Shenzhen Mindray Biomedical Electronics Co., Ltd.", "legal_name", "pending_review"),
            ("Shenzhen Mindray Bio-Medical Electronics Co.", "legal_name", "pending_review"),
            ("Mindray Bio-Medical Electronics Co., Ltd.", "legal_name", "pending_review"),
            ("Mindray DS USA, Inc.", "subsidiary", "pending_review"),
            ("Mindray DS USA, Inc. dba Mindray North America", "subsidiary", "pending_review"),
            ("Mindray DS USA, Inc. d.b.a. Mindray North America", "subsidiary", "pending_review"),
            ("Mindray DS USA, Inc., dba Datascope Patient Monitoring", "subsidiary", "pending_review"),
            ("Mindray North America", "subsidiary", "pending_review"),
        ],
        "reject": [],
        "ownership_note": "Mindray DS USA is the group's US operating entity; the group relation is pending human review.",
    },
}

# Extra organizations absent from the research roster. Included to prove that search and
# comparison generalise beyond the five acceptance-sample firms. Attribution is pending review.
EXTRA = [
    {
        "key": "nihon_kohden",
        "display_name": "Nihon Kohden",
        "display_name_zh": "日本光电",
        "legal_name": "Nihon Kohden Corporation",
        "ticker": "6849",
        "exchange": "TSE",
        "country": "JP",
        "country_name": "Japan",
        "description": "Nihon Kohden Corporation is headquartered in Tokyo, Japan and makes patient monitors, electroencephalographs and defibrillators. US FDA records appear under Nihon Kohden America and Nihon Kohden Corporation applicant names.",
        "accept": [("Nihon Kohden America, Inc.", "subsidiary"), ("Nihon Kohden America", "subsidiary"),
                   ("Nihon Kohden Corporation", "legal_name"), ("Nihon Kohden Corp.", "legal_name"),
                   ("Nihon Kohden", "brand")],
    },
    {
        "key": "getinge",
        "display_name": "Getinge",
        "display_name_zh": "洁定",
        "legal_name": "Getinge AB",
        "ticker": "GETI-B",
        "exchange": "Nasdaq Stockholm",
        "country": "SE",
        "country_name": "Sweden",
        "description": "Getinge AB is headquartered in Gothenburg, Sweden and supplies sterilisation, surgical and intensive-care equipment. FDA records appear under Getinge and Maquet applicant names.",
        "accept": [("Getinge", "brand"), ("Getinge USA", "subsidiary"), ("Getinge USA, Inc.", "subsidiary"),
                   ("Maquet", "subsidiary"), ("Maquet Cardiovascular", "subsidiary"),
                   ("Getinge Sterilization", "subsidiary"), ("Getinge Deutschland GmbH", "subsidiary")],
    },
    {
        "key": "elekta",
        "display_name": "Elekta",
        "display_name_zh": "医科达",
        "legal_name": "Elekta AB",
        "ticker": "EKTA-B",
        "exchange": "Nasdaq Stockholm",
        "country": "SE",
        "country_name": "Sweden",
        "description": "Elekta AB is headquartered in Stockholm, Sweden and develops radiotherapy and radiosurgery systems. FDA records appear under Elekta Instrument and Elekta Limited applicant names.",
        "accept": [("Elekta", "brand"), ("Elekta Instrument AB", "subsidiary"),
                   ("Elekta Instrument", "subsidiary"), ("Elekta Limited", "subsidiary"),
                   ("Elekta Ltd", "subsidiary"), ("Elekta AB", "legal_name")],
    },
    {
        "key": "cochlear",
        "display_name": "Cochlear",
        "display_name_zh": "科利耳",
        "legal_name": "Cochlear Limited",
        "ticker": "COH",
        "exchange": "ASX",
        "country": "AU",
        "country_name": "Australia",
        "description": "Cochlear Limited is headquartered in Sydney, Australia and makes cochlear implants and bone-conduction hearing systems. FDA records appear under Cochlear Americas and Cochlear Limited applicant names.",
        "accept": [("Cochlear", "brand"), ("Cochlear Americas", "subsidiary"),
                   ("Cochlear Limited", "legal_name"), ("Cochlear Ltd", "legal_name"),
                   ("Cochlear Bone Anchored Solutions", "subsidiary")],
    },
    {
        "key": "sonova",
        "display_name": "Sonova",
        "display_name_zh": "索诺瓦",
        "legal_name": "Sonova Holding AG",
        "ticker": "SOON",
        "exchange": "SIX Swiss Exchange",
        "country": "CH",
        "country_name": "Switzerland",
        "description": "Sonova Holding AG is headquartered in Staefa, Switzerland and makes hearing instruments and cochlear implants. FDA records appear under Sonova, Advanced Bionics and Phonak applicant names.",
        "accept": [("Sonova", "brand"), ("Sonova AG", "legal_name"),
                   ("Advanced Bionics", "subsidiary"), ("Advanced Bionics LLC", "subsidiary"),
                   ("Phonak", "subsidiary"), ("Phonak LLC", "subsidiary")],
    },
    {
        "key": "straumann",
        "display_name": "Straumann",
        "display_name_zh": "士卓曼",
        "legal_name": "Institut Straumann AG",
        "ticker": "STMN",
        "exchange": "SIX Swiss Exchange",
        "country": "CH",
        "country_name": "Switzerland",
        "description": "Institut Straumann AG is headquartered in Basel, Switzerland and supplies dental implants and restorative dentistry products. FDA records appear under Institut Straumann and Straumann applicant names.",
        "accept": [("Institut Straumann AG", "legal_name"), ("Institut Straumann", "legal_name"),
                   ("Straumann", "brand"), ("Straumann USA", "subsidiary"),
                   ("Straumann USA LLC", "subsidiary")],
    },
]


def spelling_basis(value: str) -> str:
    upper = value.strip().upper()
    if upper in SUBSIDIARY_SPELLINGS:
        return "subsidiary"
    if upper in HISTORICAL_SPELLINGS:
        return "historical_name"
    return "brand"


def build_roster() -> list[dict]:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    entries: list[dict] = []
    for company in data["companies"]:
        key = company["key"]
        featured = FEATURED.get(key)
        accept = []
        if featured and featured.get("extra_accept"):
            for value, basis, review in featured["extra_accept"]:
                accept.append({"value": value, "basis": basis, "review": review, "source": "registry_curated"})
        if not featured or not featured.get("acl"):
            for alias in company.get("aliases") or []:
                upper = alias.strip().upper()
                if any(item["value"].upper() == upper for item in accept):
                    continue
                accept.append({
                    "value": alias,
                    "basis": spelling_basis(alias),
                    "review": "curated",
                    "source": "config/companies_device.json (research roster)",
                })
        reject = []
        if featured:
            for value, reason in featured.get("reject") or []:
                reject.append({"value": value, "reason": reason})
        entries.append({
            "key": key,
            "display_name": featured_display(featured, company, "en"),
            "display_name_zh": featured_display(featured, company, "zh"),
            "legal_name": (featured or {}).get("legal_name"),
            "ticker": (featured or {}).get("ticker") or (company.get("ticker") or None),
            "exchange": (featured or {}).get("exchange"),
            "country": (featured or {}).get("country"),
            "country_name": (featured or {}).get("country_name"),
            "organization_type": "public_company" if (company.get("ticker") or (featured or {}).get("ticker")) else "unknown",
            "featured": key in FEATURED,
            "description": (featured or {}).get("description") or company.get("name_en", key),
            "brands": (featured or {}).get("brands") or [company.get("name_en", key)],
            "registry_review": (featured or {}).get("review_status") or "curated",
            "metadata_source": (featured or {}).get("metadata_source") or "config/companies_device.json (research roster)",
            "accept_exact": accept,
            "reject_exact": reject,
            "ownership_note": (featured or {}).get("ownership_note")
            or "No parent/subsidiary relation is asserted for this organization in this release.",
            "search_tokens": tokens_for(key, accept),
        })
    return entries


def featured_display(featured: dict | None, company: dict, lang: str) -> str:
    if featured and lang == "zh" and company.get("name_zh"):
        return company["name_zh"]
    return company.get("name_zh" if lang == "zh" else "name_en") or company["key"]


def build_featured_offroster() -> list[dict]:
    """Featured organizations that are not in the research roster (Draeger, Mindray).

    Their applicant-spelling lists come from the reviewed PRODUCT/2.0 alias work (PR #12) and
    are recorded here as pending human review, because a human has not signed this file off.
    """
    entries = []
    roster_keys = {c["key"] for c in json.loads(CONFIG.read_text(encoding="utf-8"))["companies"]}
    for key, featured in FEATURED.items():
        if key in roster_keys:
            continue
        accept = [
            {"value": value, "basis": basis, "review": review, "source": "product_2.0_reviewed_alias_set"}
            for value, basis, review in featured.get("acl") or []
        ]
        entries.append({
            "key": key,
            "display_name": featured["brands"][0],
            "display_name_zh": {"draeger": "德尔格", "mindray": "迈瑞"}.get(key),
            "legal_name": featured["legal_name"],
            "ticker": featured["ticker"],
            "exchange": featured["exchange"],
            "country": featured["country"],
            "country_name": featured["country_name"],
            "organization_type": featured["organization_type"],
            "featured": True,
            "description": featured["description"],
            "brands": featured["brands"],
            "registry_review": featured["review_status"],
            "metadata_source": featured["metadata_source"],
            "accept_exact": accept,
            "reject_exact": [{"value": value, "reason": reason} for value, reason in featured.get("reject") or []],
            "ownership_note": featured["ownership_note"],
            "search_tokens": tokens_for(key, accept),
        })
    return entries


def build_extra() -> list[dict]:
    entries = []
    for org in EXTRA:
        accept = [
            {"value": value, "basis": basis, "review": "pending_review", "source": "registry_agent_proposed"}
            for value, basis in org["accept"]
        ]
        entries.append({
            "key": org["key"],
            "display_name": org["display_name"],
            "display_name_zh": org.get("display_name_zh"),
            "legal_name": org["legal_name"],
            "ticker": org.get("ticker"),
            "exchange": org.get("exchange"),
            "country": org["country"],
            "country_name": org["country_name"],
            "organization_type": "public_company",
            "featured": False,
            "description": org["description"],
            "brands": [org["display_name"]],
            "registry_review": "pending_review",
            "metadata_source": "MedRadar organization registry (agent-proposed, pending human review)",
            "accept_exact": accept,
            "reject_exact": [],
            "ownership_note": "No parent/subsidiary relation is asserted for this organization in this release.",
            "search_tokens": tokens_for(org["key"], accept),
        })
    return entries


def tokens_for(key: str, accept: list[dict]) -> list[str]:
    """Search tokens are the *collection* queries. They are intentionally broader than the
    accept list: the point is to retrieve every spelling the FDA stores, then attribute
    exactly. Tokens are de-duplicated, uppercase, and capped."""
    tokens: list[str] = []
    for item in accept:
        value = " ".join(item["value"].upper().replace(".", " ").replace(",", " ").split())
        if not value or value in tokens:
            continue
        tokens.append(value)
    # A short distinctive brand token broadens the sweep for unseen spellings.
    brand = {
        "medtronic": ["MEDTRONIC"],
        "ge_healthcare": ["GE MEDICAL", "GE HEALTHCARE"],
        "philips": ["PHILIPS"],
        "draeger": ["DRAGER", "DRAEGER"],
        "mindray": ["MINDRAY"],
        "johnson_johnson_medtech": ["JOHNSON & JOHNSON", "ETHICON", "DEPUY"],
        "bd": ["BECTON DICKINSON", "C R BARD", "BD BARD"],
        "bbraun": ["B BRAUN", "AESCULAP"],
        "wl_gore": ["GORE"],
        "fresenius_medical_care": ["FRESENIUS"],
        "canon_medical": ["CANON MEDICAL", "TOSHIBA MEDICAL"],
        "fujifilm": ["FUJIFILM"],
        "envista": ["ENVISTA", "NOBEL BIOCARE"],
        "zimmer_biomet": ["ZIMMER", "BIOMET"],
        "smith_nephew": ["SMITH & NEPHEW"],
    }.get(key)
    for token in brand or []:
        if token not in tokens:
            tokens.append(token)
    return tokens[:26]


def main() -> None:
    entries = build_roster() + build_featured_offroster() + build_extra()
    payload = {
        "schema": "medradar.organizations.v1",
        "updated_at": "2026-11-15",
        "notes": (
            "Identities, brands and applicant-spelling decisions for the MedRadar workbench. "
            "Record-derived facts (counts, dates) never live here. review status: 'curated' means "
            "the spelling comes from the reviewed research roster; 'pending_review' means MedRadar "
            "proposed it and a human has not signed it off, and the product must label it as provisional."
        ),
        "matching_rule": (
            "Exact applicant-name match after casefold + whitespace collapse; the verbatim source "
            "string is preserved for evidence. No fuzzy, prefix or substring matching for attribution."
        ),
        "organization_count": len(entries),
        "organizations": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(entries)} organizations")


if __name__ == "__main__":
    main()
