"""STEP 2 — independent attribution audit of the committed Target-A anchors.

For every one of the 268 committed anchors the raw applicant string is re-tokenised and
re-resolved with the verifier's own brand-token resolver; the audit looks specifically for

  (a) an acquired-company applicant attributed before its acquisition (parenthetical re-branding,
      'now a part of', Cowen/Novadaq/etc.),
  (b) two different firms' brand tokens colliding on one applicant string,
  (c) a GE / BOSTON qualifier false positive (GENERAL+MEDICAL, BOSTON+MEDICAL, bare GE, ...).

Run:  python experiments/phoenix003/verify/verify_attribution.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc

OUT = Path(__file__).resolve().parent / "out_attribution.json"

# analyst-knowledge acquisition dates, used ONLY to flag a possible lineage violation; all are
# labelled as analyst knowledge in the report and none is read from the store.
ACQUISITIONS = {
    "COVIDIEN": ("medtronic", "2015-01-26"),
    "SPECTRANETICS": ("philips", "2017-08-09"),
    "VOLCANO": ("philips", "2015-02-17"),
    "NOVADAQ": ("stryker", "2017-09-01"),
    "BIOMET": ("zimmer_biomet", "2015-07-01"),
    "HOWMEDICA": ("stryker", "1998-12-01"),
    "GAMBRO": ("baxter", "2013-09-01"),
    "DATASCOPE": ("mindray", "2008-06-01"),
    "ST. JUDE": ("abbott", "2017-01-04"),
    "ST JUDE": ("abbott", "2017-01-04"),
    "CR BARD": ("bd", "2017-12-29"),
    "BARD": ("bd", "2017-12-29"),
    "GIVEN IMAGING": ("medtronic", "2014-02-01"),
    "BELLCO": ("medtronic", "2016-01-01"),
    "WIPRO": ("ge_healthcare", None),
    "QUINTON": ("baxter", "2012-01-01"),
}


def main():
    anchors = vc.committed_anchors()
    lineage = vc.load_json(vc.DATASET / "firm_lineage.json")
    resolver = vc.Resolver()
    firm_brand = {f: set(spec["any_token"]) for f, spec in lineage["brand_tokens"].items()}
    brand_owner = collections.defaultdict(set)
    for f, toks in firm_brand.items():
        for t in toks:
            brand_owner[t].add(f)

    print("=" * 78)
    print(f"ENTITY ATTRIBUTION AUDIT — {len(anchors)} committed anchors")
    print("=" * 78)
    problems = {"resolver_mismatch": [], "multi_brand": [], "acquired_before": [],
                "parenthetical": [], "suspect_generic": []}

    by_firm = collections.defaultdict(list)
    for a in anchors:
        by_firm[a["firm"]].append(a)

    # ---- 15 deterministic spot checks: round-robin over the 13 firms, first/second anchor by id
    picked = []
    firms_sorted = sorted(by_firm)
    idx = 0
    while len(picked) < 15:
        f = firms_sorted[idx % len(firms_sorted)]
        pool = sorted(by_firm[f], key=lambda a: a["anchor_id"])
        if pool:
            picked.append(pool[(idx // len(firms_sorted)) % len(pool)])
        idx += 1
        if idx > 200:
            break
    seen = set()
    picked = [a for a in picked if not (a["anchor_id"] in seen or seen.add(a["anchor_id"]))]
    print("\n15 deterministic spot checks (round-robin over firms):")
    for a in picked:
        appl = a["applicant_raw"]
        firm, matched = resolver.resolve(appl)
        toks = set(vc.tokens(appl))
        others = sorted({f for t, fs in brand_owner.items() if t in toks for f in fs} - {a["firm"]})
        verdict = "OK" if (firm == a["firm"] and not others) else "REVIEW"
        print(f"  {a['firm']:22s} {a['milestone_key']:10s} {a['anchor_date']}  applicant={appl!r}")
        print(f"      resolver={firm} matched={matched}  other_brand_tokens={others}  -> {verdict}")

    # ---- full-set automated checks
    for a in anchors:
        appl = a["applicant_raw"]
        firm, matched = resolver.resolve(appl)
        toks = set(vc.tokens(appl))
        owners = {f for t in toks for f in brand_owner.get(t, set())}
        if firm != a["firm"]:
            problems["resolver_mismatch"].append(
                {"anchor": a["milestone_key"], "firm": a["firm"], "applicant": appl,
                 "resolver_firm": firm})
        others = sorted(owners - {a["firm"]})
        if others:
            problems["multi_brand"].append(
                {"anchor": a["milestone_key"], "firm": a["firm"], "applicant": appl,
                 "other_firms": others, "resolver_firm": firm})
        if "(" in appl and ")" in appl:
            problems["parenthetical"].append(
                {"anchor": a["milestone_key"], "firm": a["firm"], "applicant": appl,
                 "date": a["anchor_date"]})
        for name, (owner, close) in ACQUISITIONS.items():
            if name in vc.norm(appl):
                if owner == a["firm"] and close and a["anchor_date"] < close:
                    problems["acquired_before"].append(
                        {"anchor": a["milestone_key"], "firm": a["firm"], "applicant": appl,
                         "date": a["anchor_date"], "note": f"{name} acquired {close} by {owner}"})
                break
        # GE / BOSTON qualifier false positives: a brand token whose qualifier is a generic word
        n = vc.norm(appl)
        if a["firm"] == "ge_healthcare" and "GENERAL" in toks and not any(
                q in toks for q in ("ELECTRIC", "ELECTRICAL", "HEALTHCARE")):
            problems["suspect_generic"].append(
                {"anchor": a["milestone_key"], "firm": a["firm"], "applicant": appl,
                 "reason": "GENERAL + non-GE qualifier (MEDICAL/OEC/...)"})
        if a["firm"] == "boston_scientific" and "BOSTON" in toks and "SCIENTIFIC" not in toks:
            problems["suspect_generic"].append(
                {"anchor": a["milestone_key"], "firm": a["firm"], "applicant": appl,
                 "reason": "BOSTON without SCIENTIFIC"})

    print("\n--- automated findings over all 268 anchors ---")
    print(f"resolver mismatch vs committed firm     : {len(problems['resolver_mismatch'])}")
    for p in problems["resolver_mismatch"]:
        print("   ", p)
    print(f"applicants carrying >1 firm's brand token: {len(problems['multi_brand'])}")
    for p in problems["multi_brand"]:
        print("   ", p)
    print(f"qualified GE / BOSTON edge cases        : {len(problems['suspect_generic'])}")
    for p in problems["suspect_generic"]:
        print("   ", p)
    print(f"parenthetical re-brand applicant strings: {len(problems['parenthetical'])}")
    for p in problems["parenthetical"]:
        print("   ", p)
    print(f"acquired-company applicant dated pre-close: {len(problems['acquired_before'])}")
    for p in problems["acquired_before"]:
        print("   ", p)

    # per-firm unique applicants, so every anchor's raw string is inspectable
    print(f"\n--- unique applicant strings per firm (all {len(anchors)} anchors) ---")
    for f in sorted(by_firm):
        cnt = collections.Counter(a["applicant_raw"] for a in by_firm[f])
        print(f"  [{f}] {len(by_firm[f])} anchors, {len(cnt)} distinct applicants")
        for appl, c in sorted(cnt.items(), key=lambda kv: -kv[1]):
            print(f"      {c:3d}x  {appl!r}")

    # describe the specific risky classes
    risky = []
    for a in anchors:
        appl = a["applicant_raw"]
        toks = set(vc.tokens(appl))
        if any(k in vc.norm(appl) for k in ("NOW A PART", "A PART OF", "FORMERLY", "DIVISION",
                                            "DIV.", "SUBSIDIARY", "ACQUIRED")):
            risky.append({"anchor": a["milestone_key"], "firm": a["firm"], "applicant": appl,
                          "date": a["anchor_date"], "tokens": sorted(toks)})
    print(f"\n--- applicant strings that self-declare an acquisition/corporate change ({len(risky)}) ---")
    for r in risky:
        print("   ", r)
    payload = {
        "anchors_total": len(anchors),
        "spot_checks": [{"firm": a["firm"], "milestone_key": a["milestone_key"],
                         "applicant": a["applicant_raw"]} for a in picked],
        "problems": problems,
        "risky_applicants": risky,
        "per_firm_unique_applicants": {f: dict(collections.Counter(a["applicant_raw"] for a in by_firm[f]))
                                       for f in by_firm},
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
