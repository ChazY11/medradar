"""Freeze the literature-rarity vocabulary (Amendment 5).

A token that a device firm happens to file under its own name (applicant_df <= 3) can still be an
ordinary English word — `OVERALL`, `EFFICIENT`, `ORGANS` all pass the applicant test and all have
produced false "product links". The independent literature corpus lets us measure that directly:
how many of the 36,621 firm-anchored Europe PMC documents use the token at all?

    literature-rare(token)  iff  the token appears in at most
                                `literature_rare_max_epmc_df` documents

This is a vocabulary property of the frozen corpus computed **before** any link is formed, exactly
like a stopword list. It is a *tightening*: it can only remove candidate matches.

Output: `dataset/epmc_rare_tokens.txt` (one token per line, sorted) and
`dataset/epmc_df_meta.json` (counts, threshold, digest).
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc

EPMC_FILES = ["epmc_compact.jsonl.gz", "epmc_ext_compact.jsonl.gz"]


def build() -> dict:
    rules = pc.load_rules()
    threshold = int(rules["name_vocab"]["literature_rare_max_epmc_df"])

    df = collections.Counter()
    n_docs = 0
    n_skipped_pat = 0
    for name in EPMC_FILES:
        path = pc.DATASET / name
        if not path.exists():
            print(f"WARNING: {name} missing; vocabulary is built from what is present")
            continue
        for rec in pc.read_jsonl_gz(path):
            if str(rec.get("source") or "").upper() == "PAT":
                n_skipped_pat += 1
                continue
            n_docs += 1
            toks = set()
            for chunk in (rec.get("title"), rec.get("abstract"), rec.get("keywords")):
                if isinstance(chunk, (list, tuple)):
                    for x in chunk:
                        toks |= set(pc.token_list(str(x)))
                elif chunk:
                    toks |= set(pc.token_list(str(chunk)))
            for tok in toks:
                if len(tok) >= 3 and tok.isalpha():
                    df[tok] += 1

    rare = sorted(tok for tok, c in df.items() if c <= threshold)
    out = pc.DATASET / "epmc_rare_tokens.txt"
    out.write_text("\n".join(rare) + "\n", encoding="utf-8", newline="\n")
    meta = {
        "generated_from": [n for n in EPMC_FILES if (pc.DATASET / n).exists()],
        "documents": n_docs,
        "documents_skipped_patent": n_skipped_pat,
        "distinct_tokens": len(df),
        "threshold_max_documents": threshold,
        "share_of_documents_threshold": round(threshold / max(n_docs, 1), 6),
        "rare_tokens": len(rare),
        "ubiquitous_tokens": len(df) - len(rare),
        "examples_ubiquitous": [[t, c] for t, c in df.most_common(20)],
        "file": {"path": str(out.relative_to(pc.REPO_ROOT)).replace("\\", "/"),
                 "lines": len(rare), "sha256": pc.sha256_file(out)},
    }
    pc.write_json(pc.DATASET / "epmc_df_meta.json", meta)
    print(f"documents: {n_docs} (patent records skipped: {n_skipped_pat})")
    print(f"distinct tokens: {len(df)}; literature-rare (<= {threshold} docs): {len(rare)}")
    print(f"wrote {out} sha256={meta['file']['sha256']}")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None,
                    help="accepted for pipeline uniformity; this stage reads only the corpora")
    ap.parse_args(argv)
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
