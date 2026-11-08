"""B — match the frozen external corpora against the Target-A anchors.

The linker is deliberately mechanical: it never asks a model anything. For every anchor it
scans the anchor firm's own evidence records inside the pre-registered window and applies
the tier rules of protocol §6.1.

Tiers produced here:

* ``VERIFIED_L1`` — the evidence record cites an NCT identifier that is itself present in the
  CT.gov corpus, belongs to the same firm, and carries the same distinctive token;
* ``VERIFIED_L2`` — same firm and exact whole-token identity of a distinctive milestone token
  in the evidence record, published before the milestone;
* ``CANDIDATE_L3`` — no distinctive token identity, but a generic-vocabulary token of the
  milestone name matches (the "keyword" tier);
* ``AMBIGUOUS_L4`` — a distinctive token matches but the record's firm or public date cannot
  be resolved;
* ``REJECTED_L5`` — a token matches but a hard condition fails (record is dated on/after the
  milestone, or the token binds to a different firm).

Outputs ``results/b_links.json`` (per-anchor summary + corpus coverage) and
``EVIDENCE_LINKS.jsonl`` (link-level audit trail).
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc

NCT_RE = re.compile(r"NCT\d{8}")
MAX_LINKS_PER_ANCHOR = 100

CTGOV_FILES = ["ctgov_compact.jsonl.gz", "ctgov_ext_compact.jsonl.gz"]
EPMC_FILES = ["epmc_compact.jsonl.gz", "epmc_ext_compact.jsonl.gz"]


def _text_tokens(*chunks) -> set[str]:
    out = set()
    for c in chunks:
        if isinstance(c, (list, tuple, set)):
            for x in c:
                out |= set(pc.token_list(str(x)))
        elif c:
            out |= set(pc.token_list(str(c)))
    return out


def _firms_of(record: dict) -> list[str]:
    raw = record.get("source_firm") or ""
    return [f for f in str(raw).split("+") if f]


def load_ctgov(resolver) -> tuple[list[dict], dict]:
    records = []
    stats = collections.Counter()
    for name in CTGOV_FILES:
        path = pc.DATASET / name
        if not path.exists():
            stats[f"missing::{name}"] += 1
            continue
        n = 0
        for rec in pc.read_jsonl_gz(path):
            n += 1
            firms = _firms_of(rec)
            iv = rec.get("interventions") or []
            iv_names = [x.get("name") or "" for x in iv if isinstance(x, dict)]
            title = rec.get("brief_title") or ""
            official = rec.get("official_title") or ""
            cond = rec.get("conditions") or []
            sponsor_fields = [rec.get("lead_sponsor") or ""] + list(rec.get("collaborators") or [])
            # firm must be resolvable from the record itself (protocol §6.1)
            firm_ok = set()
            for s in sponsor_fields:
                r = resolver.resolve(str(s))
                if r["firm"]:
                    firm_ok.add(r["firm"])
            for f in firms:
                if f in firm_ok:
                    stats["records_firm_verified"] += 1
                else:
                    stats["records_firm_unverified"] += 1
            records.append({
                "source": "ctgov",
                "id": rec.get("nct_id"),
                "firms": firms,
                "firm_verified": firm_ok,
                "title": title,
                "text_raw": " ".join([title, official] + iv_names + [str(c) for c in cond]),
                "name_tokens": _text_tokens(title, iv_names),
                "title_tokens": _text_tokens(title, iv_names),
                "all_tokens": _text_tokens(title, official, iv_names, cond, rec.get("acronym"),
                                          sponsor_fields),
                "date": rec.get("first_posted"),
                "date_sens": rec.get("last_update_posted"),
                "date_basis": "first_posted" if rec.get("first_posted") else "none",
                "lead_sponsor": rec.get("lead_sponsor"),
                "file": name,
            })
            stats["records"] += 1
        stats[f"file::{name}"] = n
    return records, dict(stats)


def load_epmc(resolver) -> tuple[list[dict], dict]:
    records = []
    stats = collections.Counter()
    for name in EPMC_FILES:
        path = pc.DATASET / name
        if not path.exists():
            stats[f"missing::{name}"] += 1
            continue
        n = 0
        for rec in pc.read_jsonl_gz(path):
            n += 1
            firms = _firms_of(rec)
            affs = rec.get("firm_affiliations") or []
            firm_ok = set()
            for a in affs:
                r = resolver.resolve(str(a))
                if r["firm"]:
                    firm_ok.add(r["firm"])
            title = rec.get("title") or ""
            abstract = rec.get("abstract") or ""
            keywords = rec.get("keywords") or []
            mesh = rec.get("mesh_terms") or []
            records.append({
                "source": "epmc",
                "id": rec.get("pmid") or rec.get("doi") or rec.get("id"),
                "firms": firms,
                "firm_verified": firm_ok,
                "title": title,
                "abstract": abstract,
                "text_raw": " ".join([title, abstract, " ".join(str(k) for k in keywords)]),
                "name_tokens": _text_tokens(title),
                "title_tokens": _text_tokens(title),
                "abstract_tokens": _text_tokens(abstract),
                "all_tokens": _text_tokens(title, abstract, keywords, mesh),
                "date": rec.get("first_publication_date"),
                "date_sens": rec.get("first_index_date") or rec.get("electronic_publication_date"),
                "date_basis": rec.get("date_basis"),
                "nct_ids": sorted(set(NCT_RE.findall(title + " " + abstract))),
                "pmid": rec.get("pmid"),
                "doi": rec.get("doi"),
                "journal": rec.get("journal_title"),
                "file": name,
            })
            stats["records"] += 1
            if not firm_ok:
                stats["records_firm_unverified"] += 1
        stats[f"file::{name}"] = n
    return records, dict(stats)


def build_index(records: list[dict], key: str = "name_tokens"):
    index = collections.defaultdict(list)
    for i, r in enumerate(records):
        for tok in r[key]:
            index[tok].append(i)
    return index


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/medradar.sqlite")
    ap.add_argument("--limit", type=int, default=0, help="debug: only the first N anchors")
    args = ap.parse_args(argv)

    rules = pc.load_rules()
    lineage = pc.load_lineage()
    vocab = pc.load_frozen_vocab()
    resolver = pc.FirmResolver(lineage, rules)
    tokenizer = pc.DistinctiveTokenizer(rules, vocab)

    anchors = [json.loads(line) for line in
               open(pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl", encoding="utf-8")]
    if args.limit:
        anchors = anchors[: args.limit]
    anchors.sort(key=lambda a: a["anchor_id"])

    ctgov, ctgov_stats = load_ctgov(resolver)
    epmc, epmc_stats = load_epmc(resolver)
    print(f"ctgov records: {len(ctgov)}  epmc records: {len(epmc)}")

    # per-firm views restricted to records whose firm is verified from the record itself
    by_firm_ct = collections.defaultdict(list)
    by_firm_ep = collections.defaultdict(list)
    for i, r in enumerate(ctgov):
        for f in r["firms"]:
            if f in r["firm_verified"]:
                by_firm_ct[f].append(i)
    for i, r in enumerate(epmc):
        for f in r["firms"]:
            if f in r["firm_verified"]:
                by_firm_ep[f].append(i)

    # NCT ids that belong to the firm's own registered trials (for the L1 chain)
    firm_ncts = collections.defaultdict(set)
    ct_index = build_index(ctgov, "name_tokens")
    for f, idxs in by_firm_ct.items():
        for i in idxs:
            firm_ncts[f].add(ctgov[i]["id"])

    ep_index = build_index(epmc, "all_tokens")

    window_years = rules["evidence"]["window_years_before_anchor"]
    max_links = min(int(rules["evidence"]["max_evidence_per_anchor"]), MAX_LINKS_PER_ANCHOR)

    link_rows = []
    anchor_summaries = []
    tier_counts = collections.Counter()

    for a in anchors:
        firm = a["firm"]
        adate = pc.parse_date(a["anchor_date"])
        if adate is None:
            continue
        w_start = pc.years_before(adate, window_years)
        tokens = [t for t in a["distinctive_tokens"]]
        bands = {t: tokenizer.band(t) for t in tokens}
        link_rows_anchor = []

        # ---------------- candidate pool: any firm-verified record in the window
        pool = []
        for f, idxs in ((firm, by_firm_ct.get(firm, [])),):
            for i in idxs:
                pool.append(("ctgov", i))
        for i in by_firm_ep.get(firm, []):
            pool.append(("epmc", i))

        in_window = 0
        for src, i in pool:
            rec = ctgov[i] if src == "ctgov" else epmc[i]
            d = pc.parse_date(rec["date"])
            if d is None:
                continue
            if w_start <= d < adate:
                in_window += 1

        # ---------------- distinctive-token matches
        matched = []
        for tok in tokens:
            for i in ct_index.get(tok, []):
                matched.append(("ctgov", i, tok, "name_tokens"))
            for i in ep_index.get(tok, []):
                matched.append(("epmc", i, tok, "all_tokens"))

        best_tier = None
        best_lead = None
        best_specific = None
        per_anchor_tiers = collections.Counter()
        seen = set()
        for src, i, tok, field in matched:
            rec = ctgov[i] if src == "ctgov" else epmc[i]
            if firm not in rec["firms"]:
                continue
            key = (src, rec["id"], tok)
            if key in seen:
                continue
            seen.add(key)
            d = pc.parse_date(rec["date"])
            firm_verified = firm in rec["firm_verified"]
            tier = None
            reason = None
            if d is None:
                tier, reason = "AMBIGUOUS_L4", "public_date_unresolved"
            elif not firm_verified:
                tier, reason = "AMBIGUOUS_L4", "firm_not_verifiable_from_record"
            elif d >= adate:
                tier, reason = "REJECTED_L5", "evidence_not_before_milestone"
            else:
                # L1: identifier chain through an NCT id present in the firm's own trial set
                nct_hit = None
                if src == "epmc":
                    for nct in rec.get("nct_ids", []):
                        if nct in firm_ncts.get(firm, set()):
                            # the trial must itself carry the token
                            for ti in ct_index.get(tok, []):
                                if ctgov[ti]["id"] == nct and firm in ctgov[ti]["firms"]:
                                    nct_hit = nct
                                    break
                        if nct_hit:
                            break
                if nct_hit:
                    tier, reason = "VERIFIED_L1", f"nct_chain:{nct_hit}"
                elif d >= w_start:
                    tier = "VERIFIED_L2"
                    reason = f"token:{tok}"
                else:
                    tier, reason = "REJECTED_L5", "outside_5y_window"
            lead = (adate - d).days if d else None
            per_anchor_tiers[tier] += 1
            link_rows_anchor.append({
                "anchor_id": a["anchor_id"],
                "firm": firm,
                "stratum": a["stratum"],
                "product_code": a["product_code"],
                "anchor_date": a["anchor_date"],
                "milestone_key": a["milestone_key"],
                "milestone_name": a["name_raw"],
                "evidence_source": src,
                "evidence_id": rec["id"],
                "evidence_date": pc.iso(d),
                "evidence_date_sensitivity": rec.get("date_sens"),
                "evidence_date_basis": rec.get("date_basis"),
                "evidence_title": (rec.get("title") or "")[:400],
                "evidence_journal": rec.get("journal"),
                "evidence_url_id": rec.get("doi") or rec.get("pmid") or rec.get("id"),
                "matched_token": tok,
                "token_band": bands.get(tok),
                "token_applicant_df": tokenizer.applicant_df_of(tok),
                "product_specific": tokenizer.is_product_specific(tok),
                "match_field": field,
                "firm_verified": firm_verified,
                "tier": tier,
                "reason": reason,
                "lead_days": lead,
            })
            if tier in ("VERIFIED_L1", "VERIFIED_L2"):
                if tokenizer.is_product_specific(tok):
                    best_specific = True
                if best_tier is None or (tier == "VERIFIED_L1" and best_tier != "VERIFIED_L1"):
                    best_tier = tier
                if lead is not None and (best_lead is None or lead > best_lead):
                    best_lead = lead

        # ---------------- keyword tier (L3) for anchors with no verified link
        if best_tier is None:
            # generic vocabulary tokens of the milestone name
            generic_tokens = [t for t in a["name_tokens"]
                              if t in tokenizer.generic or t in tokenizer.stop_a]
            for tok in generic_tokens[:6]:
                for i in ep_index.get(tok, [])[:5]:
                    rec = epmc[i]
                    if firm not in rec["firms"] or firm not in rec["firm_verified"]:
                        continue
                    d = pc.parse_date(rec["date"])
                    if d is None or not (w_start <= d < adate):
                        continue
                    link_rows_anchor.append({
                        "anchor_id": a["anchor_id"], "firm": firm, "stratum": a["stratum"],
                        "product_code": a["product_code"], "anchor_date": a["anchor_date"],
                        "milestone_key": a["milestone_key"], "milestone_name": a["name_raw"],
                        "evidence_source": "epmc", "evidence_id": rec["id"],
                        "evidence_date": pc.iso(d),
                        "evidence_date_sensitivity": rec.get("date_sens"),
                        "evidence_date_basis": rec.get("date_basis"),
                        "evidence_title": (rec.get("title") or "")[:400],
                        "evidence_journal": rec.get("journal"),
                        "evidence_url_id": rec.get("doi") or rec.get("pmid"),
                        "matched_token": tok, "token_band": "generic",
                        "token_applicant_df": tokenizer.applicant_df_of(tok),
                        "product_specific": False,
                        "match_field": "all_tokens", "firm_verified": True,
                        "tier": "CANDIDATE_L3", "reason": f"generic_token:{tok}",
                        "lead_days": (adate - d).days,
                    })
                    per_anchor_tiers["CANDIDATE_L3"] += 1
                    break
                if per_anchor_tiers["CANDIDATE_L3"]:
                    break

        link_rows_anchor.sort(key=lambda r: (r["tier"], r["evidence_date"] or ""))
        link_rows.extend(link_rows_anchor[:max_links])
        for t in ("VERIFIED_L1", "VERIFIED_L2", "CANDIDATE_L3", "AMBIGUOUS_L4", "REJECTED_L5"):
            tier_counts[t] += per_anchor_tiers.get(t, 0)

        anchor_summaries.append({
            "anchor_id": a["anchor_id"],
            "firm": firm,
            "stratum": a["stratum"],
            "product_code": a["product_code"],
            "milestone_key": a["milestone_key"],
            "anchor_date": a["anchor_date"],
            "anchor_year": a["anchor_year"],
            "milestone_name": a["name_raw"],
            "distinctive_tokens": tokens,
            "token_bands": bands,
            "evidence_in_window": in_window,
            "tier_counts": dict(per_anchor_tiers),
            "best_tier": best_tier,
            "lead_days_max": best_lead,
            "has_verified_link": best_tier in ("VERIFIED_L1", "VERIFIED_L2"),
            "has_product_specific_link": bool(best_specific),
        })

    summary = {
        "generated_at": pc.utc_now_iso(),
        "anchors": len(anchor_summaries),
        "corpus": {
            "ctgov_records": len(ctgov),
            "ctgov_stats": ctgov_stats,
            "epmc_records": len(epmc),
            "epmc_stats": epmc_stats,
            "files_present": {
                "ctgov": [n for n in CTGOV_FILES if (pc.DATASET / n).exists()],
                "epmc": [n for n in EPMC_FILES if (pc.DATASET / n).exists()],
            },
        },
        "tier_counts": dict(tier_counts),
        "anchors_with_verified_link": sum(1 for s in anchor_summaries if s["has_verified_link"]),
        "anchors_with_product_specific_link": sum(
            1 for s in anchor_summaries if s["has_product_specific_link"]),
        "anchors_with_no_candidate": sum(
            1 for s in anchor_summaries if not s["tier_counts"]),
        "per_stratum": {
            st: {
                "anchors": sum(1 for s in anchor_summaries if s["stratum"] == st),
                "verified": sum(1 for s in anchor_summaries
                                if s["stratum"] == st and s["has_verified_link"]),
                "verified_product_specific": sum(
                    1 for s in anchor_summaries
                    if s["stratum"] == st and s["has_product_specific_link"]),
            } for st in sorted({s["stratum"] for s in anchor_summaries})
        },
        "anchor_summaries": anchor_summaries,
    }

    n = pc.write_jsonl(pc.EXPERIMENT_DIR / "EVIDENCE_LINKS.jsonl", link_rows)
    summary["link_rows"] = n
    out = pc.RESULTS / "b_links.json"
    pc.write_json(out, summary)
    print(json.dumps({k: summary[k] for k in
                      ("anchors", "tier_counts", "anchors_with_verified_link",
                       "anchors_with_product_specific_link",
                       "anchors_with_no_candidate", "per_stratum", "link_rows")},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
