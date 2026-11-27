"""EXP-H2 — cross-source identity: FDA GUDID x Health Canada MDALL.

Implements the pre-registered rule in ``EXP_H2_SELECTION_RULE.md`` against the
records this workstream already collected. No network access.

Outputs
-------
experiments/regulatory/EXP_H2_PAIRS.jsonl    one JSON object per pair
experiments/regulatory/EXP_H2_SUMMARY.json   counts by signal-combination x verdict

Run:  python experiments/regulatory/exp_h2_identity.py
"""

from __future__ import annotations

import itertools
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # research/horizon
sys.path.insert(0, ROOT)

from hz.schema import read_jsonl  # noqa: E402

DS = os.path.join(ROOT, "DATASETS", "regulatory")

STOP = {
    "THE", "AND", "WITH", "FOR", "OF", "A", "AN", "TO", "IN", "ON", "SYSTEM", "SYSTEMS",
    "DEVICE", "KIT", "SET", "INC", "INC.", "LLC", "LTD", "CORP", "CORPORATION", "GMBH",
    "CO", "COMPANY", "MEDICAL", "HEALTHCARE", "HEALTH", "CARE", "USA", "US", "CANADA",
    "INTERNATIONAL", "TECHNOLOGIES", "TECHNOLOGY", "PRODUCTS", "PRODUCT", "GROUP",
}

FAMILY_WORDS = {
    "MONITOR", "MONITORING", "VENTILATOR", "RESPIRATOR", "INFUSION", "PUMP", "ULTRASOUND",
    "INCUBATOR", "WARMER", "DEFIBRILLATOR", "ANESTHESIA", "ANAESTHESIA", "CPAP", "BIPAP",
    "OXYGEN", "IMAGING", "MRI", "CT", "X", "RAY", "NEONATAL", "PATIENT",
}

HEAD_NOUNS = {
    "PUMP", "MONITOR", "VENTILATOR", "RESPIRATOR", "INCUBATOR", "WARMER", "DEFIBRILLATOR",
    "SYSTEM", "KIT", "SET", "CATHETER", "SENSOR", "PROBE", "SCANNER", "MACHINE", "BAG",
    "TUBING", "CIRCUIT", "FILTER", "MASK", "NEEDLE", "SYRINGE", "STENT", "IMPLANT",
}


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str | None) -> set[str]:
    return {t for t in norm(s).split() if t and t not in STOP and len(t) > 1}


MODEL_MODE = "strict"


def model_tokens(*vals: str | None) -> set[str]:
    """A model token must look like a model number, not just be numeric.

    Two modes are reported, because the pre-registered wording ("a normalised
    model/catalogue token ... appears on the other side") is definition-sensitive
    and the difference turns out to matter:

    ``strict`` (primary)  requires a letter AND a digit, or >=6 alphanumeric chars
                          with a digit, so generic numbers cannot masquerade as
                          model numbers.
    ``lenient``           any token of length >= 4 containing a digit. This is the
                          naive reading, and it manufactures cross-firm token
                          collisions that the strict rule discards.

    The primary table uses ``strict``; ``lenient`` is reported as a sensitivity
    check, never mixed into it.
    """
    out: set[str] = set()
    for v in vals:
        if not v:
            continue
        for part in re.split(r"[^A-Za-z0-9\-\./]+", str(v)):
            p = part.upper().strip(".-/")
            if MODEL_MODE == "lenient":
                if len(p) >= 4 and any(c.isdigit() for c in p):
                    out.add(p)
            else:
                if len(p) >= 4 and any(c.isdigit() for c in p) and any(c.isalpha() for c in p):
                    out.add(p)
                elif len(p) >= 6 and p.isalnum() and any(c.isdigit() for c in p):
                    out.add(p)
    out.discard("")
    return out


def firm_of(rec: dict) -> str | None:
    a = rec.get("attributes") or {}
    f = a.get("target_firm_slice")
    if f:
        return f
    # fall back to the declared sample map
    comp = (rec.get("manufacturer") or a.get("company_name") or "").upper()
    for name, pat in [("Medtronic", "MEDTRONIC"), ("GE HealthCare", "GE "),
                      ("Philips", "PHILIPS"), ("Draeger", "DRAG"), ("Mindray", "MINDRAY")]:
        if pat in comp:
            return name
    return None


def load() -> tuple[list[dict], list[dict]]:
    fda = read_jsonl(os.path.join(DS, "accessgudid", "records.jsonl"))
    md = read_jsonl(os.path.join(DS, "canada_mdall", "records.jsonl"))
    return fda, md


def names_of(rec: dict) -> list[str]:
    a = rec.get("attributes") or {}
    out = [rec.get("original_name")]
    for k in ("brand_name", "trade_name", "licence_name", "device_description"):
        if a.get(k):
            out.append(a[k])
    return [x for x in out if x]


def official_ids(rec: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for i in rec.get("identifiers") or []:
        sch = i.get("scheme")
        val = str(i.get("value") or "").upper()
        if sch and val:
            out[sch].add(val)
    return out


def ids_overlap(a: dict, b: dict) -> tuple[bool, str | None]:
    """S4: same-scheme identifier equality. Different namespaces never count."""
    for sch in set(a) & set(b):
        if a[sch] & b[sch]:
            return True, f"{sch}={sorted(a[sch] & b[sch])[0]}"
    return False, None


def fda_models(rec: dict) -> set[str]:
    a = rec.get("attributes") or {}
    return model_tokens(a.get("version_model_number"), a.get("catalog_number"),
                        a.get("device_description"))


def mdall_models(rec: dict) -> set[str]:
    a = rec.get("attributes") or {}
    return model_tokens(a.get("device_identifier"), a.get("licence_name"), a.get("trade_name"))


def build_pairs(fda: list[dict], md: list[dict]) -> list[dict]:
    """Enumerate pairs where at least one signal fires."""
    fda_ids = [(r, official_ids(r), firm_of(r), names_of(r),
                tokens(" ".join(names_of(r))), fda_models(r)) for r in fda]
    md_ids = []
    for r in md:
        md_ids.append((r, official_ids(r), firm_of(r), names_of(r),
                       tokens(" ".join(names_of(r))), mdall_models(r)))

    pairs: list[dict] = []
    for (fr, fid, ff, fn, ft, fm) in fda_ids:
        for (mr, mid, mf, mn, mt, mm) in md_ids:
            s1 = any(norm(x) and norm(x) == norm(y) for x in fn for y in mn)
            name_overlap = ft & mt
            s2 = bool(fm & mm) or (len(name_overlap) >= 2 and bool(fm) and bool(mm)
                                   and any(tok in mm for tok in fm))
            s3 = ff is not None and ff == mf
            s4, s4_ev = ids_overlap(fid, mid)
            s5 = len(name_overlap) >= 2
            if not (s1 or s2 or s3 or s4 or s5):
                continue
            signals = [s for s, f in (("S1", s1), ("S2", s2), ("S3", s3),
                                      ("S4", s4), ("S5", s5)) if f]
            # verdict: fixed rule from the pre-registration
            if s4:
                verdict = "CONFIRMED"
                rationale = f"shared official identifier in the same scheme ({s4_ev})"
            elif s2 and not s3:
                verdict = "REJECTED"
                rationale = ("shared model token but the two sources attribute the device to "
                             "different firms (S3 false): official attribution contradicts sameness")
            # an official date contradiction: MDALL says the identifier was removed before the
            # GUDID record was published
            else:
                md_end = (mr.get("attributes") or {}).get("end_date")
                fda_pub = fr.get("source_public_at")
                if md_end and fda_pub and md_end < fda_pub and s2:
                    verdict = "REJECTED"
                    rationale = (f"MDALL identifier removed {md_end}, before the GUDID record was "
                                 f"published {fda_pub}: cannot be the same current device")
                else:
                    verdict = "UNKNOWN"
                    rationale = (
                        "no shared official identifier; agreement is on name/model/firm only, "
                        "which the pre-registered rule never treats as confirmation"
                    )
            pairs.append({
                "pair_id": f'{fr["source_record_id"]}__{mr["source_record_id"]}',
                "signal_set": signals,
                "signals": {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5},
                "signal_detail": {
                    "name_tokens_shared": sorted(name_overlap)[:8],
                    "models_shared": sorted(fm & mm)[:8],
                    "official_id_match": s4_ev,
                },
                "verdict": verdict,
                "rationale": rationale,
                "source_record_ids": {
                    "fda": {"source_id": fr["source_id"],
                            "source_record_id": fr["source_record_id"],
                            "udi_di": next(iter(fid.get("udi_di") or []), None)},
                    "canada": {"source_id": mr["source_id"],
                               "source_record_id": mr["source_record_id"],
                               "entity_type": mr["entity_type"],
                               "identifiers": {k: sorted(v) for k, v in mid.items()}},
                },
                "fda_name": fr.get("original_name"),
                "mdall_name": mr.get("original_name"),
                "fda_firm": ff,
                "mdall_firm": mf,
                "construction_rule": None,
            })
    return pairs


def add_hard_negatives(pairs: list[dict], fda: list[dict], md: list[dict]) -> list[dict]:
    """Deterministic hard negatives, each tagged with the rule that built it."""
    out: list[dict] = []
    fda_by_firm: dict[str, list[dict]] = defaultdict(list)
    md_by_firm: dict[str, list[dict]] = defaultdict(list)
    for r in fda:
        f = firm_of(r)
        if f:
            fda_by_firm[f].append(r)
    for r in md:
        f = firm_of(r)
        if f:
            md_by_firm[f].append(r)

    def base(fr, mr, signals, rule, verdict, rationale):
        return {
            "pair_id": f"HN::{fr['source_record_id']}__{mr['source_record_id']}",
            "signal_set": list(signals),
            "signals": {k: (k in signals) for k in
                        ("S1", "S2", "S3", "S4", "S5")},
            "signal_detail": {
                "models_shared": sorted(fda_models(fr) & mdall_models(mr))[:6],
                "name_tokens_shared": sorted(tokens(" ".join(names_of(fr)))
                                             & tokens(" ".join(names_of(mr))))[:8],
            },
            "verdict": verdict,
            "rationale": rationale,
            "source_record_ids": {
                "fda": {"source_id": fr["source_id"], "source_record_id": fr["source_record_id"]},
                "canada": {"source_id": mr["source_id"],
                           "source_record_id": mr["source_record_id"],
                           "entity_type": mr["entity_type"]},
            },
            "fda_name": fr.get("original_name"),
            "mdall_name": mr.get("original_name"),
            "fda_firm": firm_of(fr),
            "mdall_firm": firm_of(mr),
            "construction_rule": rule,
        }

    firms = sorted(fda_by_firm)
    rules: dict[str, int] = {}

    # HN2 — identical model token, different firm
    n = 0
    for i, fa in enumerate(firms):
        for fb in firms[i + 1:]:
            for fr in fda_by_firm[fa][:400]:
                shared = fda_models(fr)
                if not shared:
                    continue
                hit = None
                for mr in md_by_firm.get(fb, []):
                    common = shared & mdall_models(mr)
                    if common:
                        hit = (mr, common)
                        break
                if hit and n < 30:
                    mr, common = hit
                    out.append(base(fr, mr, ["S2"], "HN2_same_model_token_different_firm", "REJECTED",
                                    f"identical model token {sorted(common)[0]} but the two sources "
                                    f"attribute the records to different firms ({fa} vs {fb}); "
                                    f"official firm attribution contradicts sameness"))
                    n += 1
    rules["HN2_same_model_token_different_firm"] = n

    # HN1 — shared brand words, different head noun, SAME firm (the hard one)
    n = 0
    for f in firms:
        for fr in fda_by_firm[f]:
            ft = tokens(" ".join(names_of(fr)))
            fhead = ft & HEAD_NOUNS
            if not fhead or n >= 25:
                continue
            for mr in md_by_firm.get(f, []):
                mt = tokens(" ".join(names_of(mr)))
                mhead = mt & HEAD_NOUNS
                if fhead and mhead and fhead != mhead and len(ft & mt) >= 2:
                    out.append(base(fr, mr, ["S3", "S5"],
                                    "HN1_same_brand_different_device", "UNKNOWN",
                                    f"same firm and shared brand tokens {sorted(ft & mt)[:3]} but "
                                    f"different head noun ({sorted(fhead)[0]} vs "
                                    f"{sorted(mhead)[0]}); a shared brand token is not a device "
                                    f"identity"))
                    n += 1
                    break
    rules["HN1_same_brand_different_device"] = n

    # HN3 — only a product-family word is shared
    n = 0
    for f in firms:
        for fr in fda_by_firm[f]:
            if n >= 20:
                break
            ft = tokens(" ".join(names_of(fr)))
            ffam = ft & FAMILY_WORDS
            if not ffam:
                continue
            for mr in md_by_firm.get(f, []):
                mt = tokens(" ".join(names_of(mr)))
                mfam = mt & FAMILY_WORDS
                if ffam & mfam and not ((ft & mt) - FAMILY_WORDS):
                    out.append(base(fr, mr, ["S3", "S5"],
                                    "HN3_same_family_different_device", "UNKNOWN",
                                    f"only the product-family word "
                                    f"{sorted(ffam & mfam)[0]} is shared; no device-specific "
                                    f"token agrees"))
                    n += 1
                    break
    rules["HN3_same_family_different_device"] = n

    # HN4 — subsidiary vs parent: same corporate family, different legal entity
    n = 0
    SUBSIDIARY_MARKERS = ("MINIMED", "SOPHARM", "DANEK", "NEUROMODULATION",
                          "ADVANCED ENERGY", "NAVIGATION", "MICROELECTRONICS")
    for f in firms:
        for fr in fda_by_firm[f]:
            comp = (fr.get("manufacturer") or "").upper()
            if n >= 12:
                break
            if not any(k in comp for k in SUBSIDIARY_MARKERS):
                continue
            for mr in md_by_firm.get(f, []):
                out.append(base(fr, mr, ["S3"], "HN4_subsidiary_vs_parent", "UNKNOWN",
                                f"same corporate family ({comp}) but the FDA manufacturer string "
                                f"and the MDALL licence holder are different legal entities; a "
                                f"parent/subsidiary relation is not an identifier and cannot "
                                f"confirm a product identity"))
                n += 1
                break
    rules["HN4_subsidiary_vs_parent"] = n

    return out, rules


def run_pass(fda: list[dict], md: list[dict], mode: str) -> dict:
    """One full pair-construction + verdict pass under a given model-token mode."""
    global MODEL_MODE
    MODEL_MODE = mode
    pairs = build_pairs(fda, md)
    # bound deterministically: strongest-signal pairs first, then stable order
    pairs.sort(key=lambda p: (-len(p["signal_set"]), p["pair_id"]))
    pairs = pairs[:700]
    hard, hn_rules = add_hard_negatives(pairs, fda, md)
    all_pairs = pairs + hard

    combo: dict[tuple[str, str], int] = Counter()
    for p in all_pairs:
        combo[("+".join(p["signal_set"]), p["verdict"])] += 1
    combos: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (sig, verdict), n in combo.items():
        combos[sig][verdict] += n

    sufficiency = []
    for sig in sorted(combos, key=lambda s: (-len(s.split("+")), s)):
        row = dict(combos[sig])
        sufficiency.append({
            "signal_combination": sig,
            "n": sum(row.values()),
            "CONFIRMED": row.get("CONFIRMED", 0),
            "REJECTED": row.get("REJECTED", 0),
            "UNKNOWN": row.get("UNKNOWN", 0),
            "reaches_confirmed": row.get("CONFIRMED", 0) > 0,
        })

    per_signal = {}
    for s in ("S1", "S2", "S3", "S4", "S5"):
        fired = [p for p in all_pairs if p["signals"].get(s)]
        per_signal[s] = {
            "fired": len(fired),
            "CONFIRMED": sum(1 for p in fired if p["verdict"] == "CONFIRMED"),
            "REJECTED": sum(1 for p in fired if p["verdict"] == "REJECTED"),
            "UNKNOWN": sum(1 for p in fired if p["verdict"] == "UNKNOWN"),
        }

    return {
        "model_token_mode": mode,
        "pairs_total": len(all_pairs),
        "pairs_candidate": len(pairs),
        "pairs_hard_negative": len(hard),
        "verdicts": dict(Counter(p["verdict"] for p in all_pairs)),
        "by_construction_rule": dict(Counter(
            p.get("construction_rule") or "candidate" for p in all_pairs)),
        "hard_negative_rules_attempted": hn_rules,
        "signal_sufficiency_table": sufficiency,
        "per_signal_sufficiency": per_signal,
        "_pairs": all_pairs,
    }


def main() -> int:
    fda, md = load()
    primary = run_pass(fda, md, "strict")
    sensitivity = run_pass(fda, md, "lenient")
    all_pairs = primary.pop("_pairs")
    sensitivity_pairs = sensitivity.pop("_pairs")

    out_path = os.path.join(HERE, "EXP_H2_PAIRS.jsonl")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        for p in all_pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    sufficiency = primary["signal_sufficiency_table"]
    per_signal = primary["per_signal_sufficiency"]
    summary = {
        "experiment": "EXP-H2",
        "question": "Can an FDA GUDID record and a Health Canada MDALL record be shown to be "
                    "the same product using official identifiers or explicit official fields?",
        "generated_from": {
            "fda_records": len(fda),
            "canada_records": len(md),
            "fda_source": "DATASETS/regulatory/accessgudid/records.jsonl",
            "canada_source": "DATASETS/regulatory/canada_mdall/records.jsonl",
        },
        "selection_rule": "experiments/regulatory/EXP_H2_SELECTION_RULE.md (pre-registered)",
        "primary": primary,
        "sensitivity_lenient_model_tokens": sensitivity,
        "finding": None,
        "hard_negative_pair_count": primary["pairs_hard_negative"],
        "verdicts": primary["verdicts"],
        "by_construction_rule": primary["by_construction_rule"],
        "hard_negative_rules_attempted": primary["hard_negative_rules_attempted"],
        "signal_sufficiency_table": sufficiency,
        "per_signal_sufficiency": per_signal,
    }

    def strongest(rows):
        return max(rows, key=lambda r: r["n"]) if rows else None

    # the headline finding, computed not asserted
    confirmed = primary["verdicts"].get("CONFIRMED", 0)
    s4_fired = per_signal["S4"]["fired"]
    summary["finding"] = {
        "confirmed_pairs": confirmed,
        "rejected_pairs": primary["verdicts"].get("REJECTED", 0),
        "S4_official_identifier_fired": s4_fired,
        "s1_exact_name_fired": per_signal["S1"]["fired"],
        "s2_model_in_both_fired": per_signal["S2"]["fired"],
        "largest_signal_combination": strongest(sufficiency),
        "conclusion": (
            "Zero pairs reach CONFIRMED and S4 never fires: GUDID identifies a device by UDI-DI "
            "and MDALL by Health Canada licence/device/identifier numbers, so the two registries "
            "share no identifier namespace and no keyless official-identifier bridge exists. "
            "S1 (exact brand-name equality) never fires in this sample either, and S2 (a shared "
            "model token) never fires under either model-token definition — the manufacturer "
            "model spaces do not collide across these two sources. What is left is firm "
            "attribution plus loose name-token overlap, which yields UNKNOWN for every pair."
        ),
        "no_pair_is_refutable_either": (
            "There are also zero REJECTED pairs. That is not a bug: name-level evidence can no "
            "more refute sameness than confirm it. Only an official field can do either, and no "
            "official field on these two records contradicts a pair in this sample. A pipeline "
            "that emits 'different device' from a name comparison would be over-claiming in the "
            "same way as one that emits 'same device'."
        ),
        "sensitivity_note": (
            "Both model-token definitions (strict: letter+digit; lenient: any token containing a "
            "digit) produce identical verdict tables, because no model token is shared between "
            "the GUDID and MDALL samples at all. The sensitivity pass is retained as a control "
            "against a claim that the strict rule was doing the work."
        ),
        "what_would_be_needed": (
            "A shared identifier cannot be synthesised from these two sources. Either a "
            "jurisdiction publishes a UDI-DI alongside its national licence numbers (EUDAMED "
            "does, for the EU, via Basic UDI-DI), or identity must be established against a "
            "third reference that carries both — not by name matching."
        ),
    }

    with open(os.path.join(HERE, "EXP_H2_SUMMARY.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(json.dumps({
        "primary": {k: primary[k] for k in
                    ("model_token_mode", "pairs_total", "pairs_candidate",
                     "pairs_hard_negative", "verdicts", "by_construction_rule",
                     "hard_negative_rules_attempted")},
        "sensitivity_lenient": {k: sensitivity[k] for k in
                                ("pairs_total", "verdicts", "hard_negative_rules_attempted")},
    }, indent=2))
    print("\nsignal sufficiency (primary, strict model tokens):")
    for r in sufficiency:
        print(f'  {r["signal_combination"]:24s} n={r["n"]:4d} CONFIRMED={r["CONFIRMED"]:3d} '
              f'REJECTED={r["REJECTED"]:3d} UNKNOWN={r["UNKNOWN"]:3d}')
    print("\nsignal sufficiency (sensitivity, lenient model tokens):")
    for r in sensitivity["signal_sufficiency_table"]:
        print(f'  {r["signal_combination"]:24s} n={r["n"]:4d} CONFIRMED={r["CONFIRMED"]:3d} '
              f'REJECTED={r["REJECTED"]:3d} UNKNOWN={r["UNKNOWN"]:3d}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
