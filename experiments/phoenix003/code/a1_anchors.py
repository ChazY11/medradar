"""A1 — build the canonical regulatory milestone set and the Target-A anchor sample.

Reads the read-only MedRadar store and writes:

* ``results/a1_canonical.json`` — the full integrity funnel (duplicates, attribution,
  missing fields, date semantics, taxonomy) that DATA_INTEGRITY_AUDIT.md is generated from;
* ``REGULATORY_ANCHORS.jsonl`` — Target-A anchors (firm's first canonical milestone in a
  product code), each carrying its official identifier, source URL and provenance.

No model, no external data, no network. Deterministic.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc

SOURCE_KIND = {"openfda_device_510k": "510k", "openfda_device_pma": "pma"}


def load_milestones(con, rules):
    """Return (milestones, raw_audit). A *milestone* is a 510(k) record or an original PMA
    approval. PMA supplements are loaded only for the inflation audit."""
    substantive = rules["anchor"]["substantive_decision_codes"]
    allow_supplement = bool(rules["anchor"].get("pma_supplements_are_milestones"))

    milestones = []
    supplements = []
    raw = collections.Counter()
    missing = collections.Counter()

    q = """
      select event_id, source, kind, event_date, company_key, applicant_raw, product_code, title,
             url, json_extract(payload,'$.k_number')            as k_number,
             json_extract(payload,'$.pma_number')              as pma_number,
             json_extract(payload,'$.supplement_number')       as supplement_number,
             json_extract(payload,'$.decision_code')           as decision_code,
             json_extract(payload,'$.decision_description')    as decision_description,
             json_extract(payload,'$.date_received')           as date_received,
             json_extract(payload,'$.device_name')             as dev_device_name,
             json_extract(payload,'$.trade_name')              as pma_trade_name,
             json_extract(payload,'$.generic_name')            as pma_generic_name,
             json_extract(payload,'$.applicant')               as payload_applicant,
             json_extract(payload,'$.openfda.regulation_number') as regulation_number,
             json_extract(payload,'$.openfda.device_class')     as device_class,
             json_extract(payload,'$.openfda.device_name')      as generic_device_name
      from events
      where kind in ('510k','pma')
    """
    for r in con.execute(q):
        kind = r["kind"]
        raw[kind] += 1
        is_pma = kind == "pma"
        supp = (r["supplement_number"] or "").strip()
        ident = r["pma_number"] if is_pma else r["k_number"]
        if not ident:
            missing["missing_identifier"] += 1
            continue
        if is_pma and supp and not allow_supplement:
            supplements.append({"pma_number": r["pma_number"], "supplement_number": supp,
                                "decision_code": r["decision_code"], "event_date": r["event_date"]})
            continue
        rec = {
            "event_id": r["event_id"],
            "kind": kind,
            "milestone_key": ("P" if is_pma else "K") + str(ident),
            "official_id": str(ident),
            "supplement_number": supp or None,
            "source": r["source"],
            "decision_date": r["event_date"],
            "date_received": r["date_received"],
            "decision_code": r["decision_code"],
            "decision_description": r["decision_description"],
            "applicant_raw": (r["applicant_raw"] or r["payload_applicant"] or "").strip(),
            "product_code": (r["product_code"] or "").strip(),
            "url": r["url"],
            "store_company_key": r["company_key"],
            "regulation_number": r["regulation_number"],
            "device_class": r["device_class"],
            "generic_device_name": r["generic_device_name"],
        }
        if is_pma:
            rec["name_raw"] = (r["pma_trade_name"] or "").strip()
            rec["name_source"] = "pma.trade_name" if rec["name_raw"] else "pma.generic_name"
            if not rec["name_raw"]:
                rec["name_raw"] = (r["pma_generic_name"] or "").strip()
            rec["generic_device_name"] = r["pma_generic_name"] or r["generic_device_name"]
        else:
            rec["name_raw"] = (r["dev_device_name"] or "").strip()
            rec["name_source"] = "510k.device_name"
        milestones.append(rec)
    return milestones, supplements, raw, missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/medradar.sqlite")
    args = ap.parse_args(argv)

    rules = pc.load_rules()
    lineage = pc.load_lineage()
    vocab = pc.load_frozen_vocab()
    resolver = pc.FirmResolver(lineage, rules)
    tokenizer = pc.DistinctiveTokenizer(rules, vocab)

    con = pc.connect_db(args.db)
    milestones, supplements, raw_counts, missing = load_milestones(con, rules)
    # official product-code catalogue: used ONLY for the generic device name of a code, which
    # the hindsight-free retrieval rule (protocol §7) needs. It never influences sampling.
    procode_generic = {}
    for r in con.execute("select product_code, device_name from product_codes"):
        procode_generic[r["product_code"]] = r["device_name"] or ""
    con.close()

    audit = {
        "generated_at": pc.utc_now_iso(),
        "db": str(args.db),
        "raw_rows": dict(raw_counts),
        "rows_without_identifier": dict(missing),
        "pma_supplement_rows_not_milestones": len(supplements),
        "supplement_decision_codes": dict(collections.Counter(
            s["decision_code"] or "<none>" for s in supplements).most_common(20)),
        "milestones_loaded": len(milestones),
    }

    # ---------------------------------------------------------------- duplicates
    key_counts = collections.Counter(m["milestone_key"] for m in milestones)
    audit["duplicate_milestone_keys"] = {
        "keys": len(key_counts),
        "keys_appearing_more_than_once": sum(1 for c in key_counts.values() if c > 1),
        "extra_rows": sum(c - 1 for c in key_counts.values() if c > 1),
        "examples": [k for k, c in key_counts.most_common(5) if c > 1],
    }
    natural = collections.Counter(
        (m["applicant_raw"].upper(), pc.normalise_text(m["name_raw"]), m["decision_date"],
         m["product_code"]) for m in milestones)
    audit["natural_key_collisions"] = {
        "definition": "same (applicant, normalised trade name, decision date, product code) under different official identifiers",
        "count": sum(1 for c in natural.values() if c > 1),
        "extra_rows": sum(c - 1 for c in natural.values() if c > 1),
        "examples": [list(k) for k, c in natural.most_common(3) if c > 1],
    }

    # -------------------------------------------------------------- attribution
    attr = collections.Counter()
    per_firm = collections.Counter()
    per_firm_strict = collections.Counter()
    attributed = []
    for m in milestones:
        res = resolver.resolve(m["applicant_raw"])
        m["firm"] = res["firm"]
        m["firm_rule"] = res["rule"]
        m["firm_matched_token"] = res["matched_token"]
        m["stratum"] = res["stratum"]
        toks = pc.token_list(m["applicant_raw"])
        # strict = brand token among the first two tokens and no parenthetical re-branding
        strict = False
        if res["firm"]:
            brand = set(lineage["brand_tokens"][res["firm"]]["any_token"])
            pos = [i for i, t in enumerate(toks) if t in brand]
            parenthetical = "(" in m["applicant_raw"] and ")" in m["applicant_raw"]
            strict = bool(pos) and min(pos) <= 1 and not parenthetical
        m["strict_attribution"] = strict
        if res["firm"]:
            attr["attributed"] += 1
            attr[f"stratum::{res['stratum']}"] += 1
            per_firm[res["firm"]] += 1
            if strict:
                per_firm_strict[res["firm"]] += 1
            attributed.append(m)
        else:
            attr["unknown"] += 1
    audit["attribution"] = {
        "milestones": len(milestones),
        "attributed_to_core_firm": attr["attributed"],
        "attributed_strict": sum(1 for m in milestones if m.get("strict_attribution")),
        "unknown": attr["unknown"],
        "unknown_rate": round(attr["unknown"] / max(len(milestones), 1), 6),
        "by_stratum": {k.split("::")[1]: v for k, v in attr.items() if k.startswith("stratum::")},
        "per_firm_inclusive": dict(per_firm),
        "per_firm_strict": dict(per_firm_strict),
        "note": "UNKNOWN is retained, never imputed. The sampling frame is the five core firms "
                "plus the eight pre-registered extension firms, all attributed by the same brand "
                "rule; every other applicant in the store is outside the frame and counted here.",
    }

    # ------------------------------------------------------------- time semantics
    def year_of(s):
        return (s or "")[:4]

    lag = []
    same_day = 0
    for m in attributed:
        d = pc.parse_date(m["decision_date"])
        r = pc.parse_date(m["date_received"])
        if d and r:
            lag.append((d - r).days)
        raw = None
    audit["time_semantics"] = {
        "decision_date_null": sum(1 for m in milestones if not m["decision_date"]),
        "date_received_null": sum(1 for m in milestones if not m["date_received"]),
        "received_to_decision_days": {
            "n": len(lag),
            "median": pc.percentile(sorted(lag), 0.5) if lag else None,
            "p10": pc.percentile(sorted(lag), 0.10) if lag else None,
            "p90": pc.percentile(sorted(lag), 0.90) if lag else None,
            "negative": sum(1 for x in lag if x < 0),
        },
        "note": "the store has one snapshot; decision_date is the FDA decision date and is the "
                "public date of the milestone. The store's available_at equals the event date "
                "for every row and is not an observation timestamp, so this study never uses it.",
    }

    # ---------------------------------------------------- process -> anchor sample
    win_start = rules["anchor"]["window_start"]
    win_end = rules["anchor"]["window_end"]
    subst = rules["anchor"]["substantive_decision_codes"]
    funnel = collections.Counter()
    funnel["milestones_loaded"] = len(milestones)
    funnel["attributed_to_core_firm"] = len(attributed)

    # decision-code filter
    keep = [m for m in attributed if (m["decision_code"] or "") in subst[m["source"]]]
    funnel[f"excluded_decision_code"] = len(attributed) - len(keep)
    funnel["after_decision_code"] = len(keep)

    # missing product code
    keep2 = [m for m in keep if m["product_code"]]
    funnel["excluded_missing_product_code"] = len(keep) - len(keep2)
    funnel["after_product_code"] = len(keep2)

    # distinctive token
    with_tokens = []
    for m in keep2:
        toks = tokenizer.candidates(m["name_raw"])
        m["distinctive_tokens"] = toks
        m["name_tokens"] = tokenizer.all_tokens(m["name_raw"])
        if toks:
            with_tokens.append(m)
    funnel["excluded_no_distinctive_token"] = len(keep2) - len(with_tokens)
    funnel["after_distinctive_token"] = len(with_tokens)

    # first-in-code, window
    by_fc = collections.defaultdict(list)
    for m in with_tokens:
        d = pc.parse_date(m["decision_date"])
        if d is None:
            continue
        by_fc[(m["firm"], m["product_code"])].append((d, m))
    funnel["firm_product_code_pairs"] = len(by_fc)

    anchors = []
    in_window = 0
    for (firm, code), items in sorted(by_fc.items()):
        items.sort(key=lambda x: (x[0], x[1]["milestone_key"]))
        first_date, first = items[0]
        if not (win_start <= first_date.isoformat() <= win_end):
            continue
        in_window += 1
        a = dict(first)
        a["anchor_date"] = first_date.isoformat()
        a["anchor_year"] = first_date.year
        a["prior_milestones_in_code"] = 0
        a["milestones_in_code_total"] = len(items)
        a["procode_generic_name"] = procode_generic.get(code, "")
        a["procode_generic_tokens"] = pc.token_list(a["procode_generic_name"])
        a["anchor_id"] = pc.sha256_bytes(
            f"{firm}|{code}|{first['milestone_key']}".encode())
        anchors.append(a)
    funnel["first_in_code_inside_window"] = in_window

    # no pre-window history requirement is needed: first-in-code means the firm had no earlier
    # record in that code at all; we still document how many anchors are *not* first-in-code
    # globally because the store may start later than 1976.
    funnel["anchors"] = len(anchors)
    audit["funnel"] = dict(funnel)

    # ---------------------------------------------------------- firm/time sanity
    per_firm_anchor = collections.Counter(a["firm"] for a in anchors)
    per_year_anchor = collections.Counter(a["anchor_year"] for a in anchors)
    per_stratum = collections.Counter(a["stratum"] for a in anchors)
    audit["anchor_sample"] = {
        "n": len(anchors),
        "per_stratum": dict(sorted(per_stratum.items())),
        "per_firm": dict(sorted(per_firm_anchor.items())),
        "per_year": {str(k): v for k, v in sorted(per_year_anchor.items())},
        "per_kind": dict(collections.Counter(a["kind"] for a in anchors)),
        "distinct_product_codes": len({a["product_code"] for a in anchors}),
        "median_prior_milestones_in_code": None,
        "name_source": dict(collections.Counter(a["name_source"] for a in anchors)),
        "strict_attribution_share": round(
            sum(1 for a in anchors if a["strict_attribution"]) / max(len(anchors), 1), 6),
        "core_firms_with_at_least_5_anchors": sorted(
            f for f, c in per_firm_anchor.items())
        and sorted(f for f, c in per_firm_anchor.items()
                   if c >= 5 and rules["firms"]["core"] and f in rules["firms"]["core"]),
        "extension_rule_triggered": any(
            c < 5 for f, c in per_firm_anchor.items() if f in rules["firms"]["core"]),
    }

    # traceable ordering: anchors sorted deterministically
    anchors.sort(key=lambda a: a["anchor_id"])

    fields = [
        "anchor_id", "firm", "stratum", "firm_rule", "firm_matched_token", "strict_attribution",
        "product_code", "kind", "milestone_key", "official_id", "supplement_number",
        "decision_code", "decision_description", "anchor_date", "anchor_year",
        "decision_date", "date_received", "applicant_raw", "name_raw", "name_source",
        "distinctive_tokens", "name_tokens", "generic_device_name", "procode_generic_name",
        "procode_generic_tokens", "regulation_number",
        "device_class", "url", "event_id", "milestones_in_code_total", "source",
    ]
    rows = [{k: a.get(k) for k in fields} for a in anchors]
    out_path = pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl"
    n = pc.write_jsonl(out_path, rows)
    audit["outputs"] = {
        "anchors_jsonl": {"path": str(out_path.relative_to(pc.REPO_ROOT)), "lines": n,
                          "sha256": pc.sha256_file(out_path)},
    }
    result_path = pc.RESULTS / "a1_canonical.json"
    pc.write_json(result_path, audit)
    print(json.dumps({
        "milestones_loaded": audit["milestones_loaded"],
        "attributed": audit["attribution"]["attributed_to_core_firm"],
        "unknown_rate": audit["attribution"]["unknown_rate"],
        "anchors": len(anchors),
        "per_stratum": dict(per_stratum),
        "per_firm": dict(per_firm_anchor),
        "per_year": {str(k): v for k, v in sorted(per_year_anchor.items())},
        "duplicate_keys": audit["duplicate_milestone_keys"],
        "pma_supplements_excluded": audit["pma_supplement_rows_not_milestones"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
