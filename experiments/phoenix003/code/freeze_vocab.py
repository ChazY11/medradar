"""Freeze the name vocabulary used by the distinctive-token rule.

Three components, all computed from the read-only store and committed:

* part A — a hand-written stoplist of generic device/English words, frozen in
  ``FROZEN_RULES.json``;
* part B — the **generic device vocabulary**, computed from the static product-code catalogue
  (``product_codes``). A token is generic when it occurs in the device name or definition of
  at least ``generic_vocabulary_min_product_code_df`` product codes;
* part C — **brand tokens** (the five core firms) and the **regulatory name document
  frequency** of every remaining token across all 177,948 regulatory device names, used only
  to band a token as high / medium / low specificity.

Parts B and C use vocabulary, dates and names only — never a link, a milestone label or an
outcome. The output is deterministic and its digest is recorded in the results manifest.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc


def build(db_path: str) -> dict:
    rules = pc.load_rules()
    lineage = pc.load_lineage()
    min_df = int(rules["name_vocab"]["generic_vocabulary_min_product_code_df"])
    hi = int(rules["name_vocab"]["specificity_high_max_df"])
    mid = int(rules["name_vocab"]["specificity_medium_max_df"])
    con = pc.connect_db(db_path)
    cur = con.cursor()

    # ---- part B: generic device vocabulary from the static product-code catalogue
    df = collections.Counter()
    n_codes = 0
    for r in cur.execute("select device_name, definition from product_codes"):
        n_codes += 1
        # NOTE: f-string, not " ".join(single_string) — join on a str would interleave spaces
        # between characters and silently empty the vocabulary (bug caught before first use).
        text = f"{r['device_name'] or ''} {r['definition'] or ''}"
        for tok in set(pc.token_list(text)):
            if len(tok) >= 3 and tok.isalpha():
                df[tok] += 1
    generic = sorted(tok for tok, c in df.items() if c >= min_df)

    # ---- part C: regulatory device-name document frequency + brand tokens
    brand = set()
    for firm, spec in lineage["brand_tokens"].items():
        brand.update(t.upper() for t in spec.get("any_token", []))

    name_df = collections.Counter()
    applicant_df = collections.Counter()
    n_names = 0
    q = """
      select json_extract(payload,'$.device_name') as dn,
             json_extract(payload,'$.trade_name')  as tn,
             json_extract(payload,'$.generic_name') as gn,
             applicant_raw
      from events where kind in ('510k','pma')
    """
    for r in cur.execute(q):
        name = r["dn"] or r["tn"] or r["gn"] or ""
        if not name:
            continue
        n_names += 1
        toks = {t for t in pc.token_list(name) if len(t) >= 3 and t.isalpha()}
        for tok in toks:
            name_df[tok] += 1
        applicant = pc.normalise_text(r["applicant_raw"] or "")
        if applicant:
            for tok in toks:
                # count distinct applicants per token via a per-applicant seen set below
                pass
    # second pass for applicant document frequency (needs a set per token)
    applicants_of = collections.defaultdict(set)
    for r in cur.execute(q):
        name = r["dn"] or r["tn"] or r["gn"] or ""
        applicant = pc.normalise_text(r["applicant_raw"] or "")
        if not name or not applicant:
            continue
        toks = {t for t in pc.token_list(name) if len(t) >= 3 and t.isalpha()}
        for tok in toks:
            applicants_of[tok].add(applicant)
    applicant_df = collections.Counter({t: len(s) for t, s in applicants_of.items()})
    con.close()

    def band(token: str) -> str:
        """Specificity by *applicant* document frequency: how many distinct applicants use the
        token in a device name. A token used by one applicant cannot discriminate between
        firms; a token used by many applicants discriminates nothing about the product either.
        This replaced a name-frequency band after the first linker output showed that a
        product-line name repeated across one firm's own supplements (MICRA) looked
        "low-specificity" under name frequency, which is the wrong quantity (Amendment 2)."""
        c = applicant_df.get(token, 0)
        if c == 0:
            return "unseen"
        if c <= 1:
            return "high"
        if c <= mid:
            return "medium"
        return "low"

    payload = {
        "vocab_version": 2,
        "generated_from": "medradar.sqlite:product_codes + events(510k,pma) names",
        "product_codes_rows": n_codes,
        "regulatory_name_rows": n_names,
        "df_threshold": min_df,
        "generic_vocabulary": generic,
        "generic_vocabulary_size": len(generic),
        "brand_tokens": sorted(brand),
        "specificity_bands": {"metric": "distinct_applicants_using_token_in_a_device_name",
                              "high_max": 1, "medium_max": mid},
        "top_generic_df": [[tok, c] for tok, c in df.most_common(30)],
        "top_name_df": [[tok, c] for tok, c in name_df.most_common(40)],
        "applicant_df": dict(sorted(applicant_df.items())),
        "band_rule": {"high_max_applicants": 1, "medium_max_applicants": mid},
    }
    out = pc.DATASET / "frozen_vocab.json"
    pc.write_json(out, payload)
    (pc.DATASET / "name_stoplist_extra.txt").write_text(
        "\n".join(generic) + "\n", encoding="utf-8", newline="\n")
    digest = pc.sha256_file(out)
    print(f"product codes read: {n_codes}")
    print(f"regulatory names read: {n_names}")
    print(f"generic vocabulary (df >= {min_df}): {len(generic)} tokens")
    print(f"brand tokens excluded from distinctiveness: {sorted(brand)}")
    print(f"distinct name tokens: {len(name_df)}; applicant df computed: {len(applicant_df)}; bands: "
          f"high={sum(1 for t in name_df if band(t)=='high')} "
          f"medium={sum(1 for t in name_df if band(t)=='medium')} "
          f"low={sum(1 for t in name_df if band(t)=='low')}")
    print(f"wrote {out} sha256={digest}")
    return {"sha256": digest, "generic_vocabulary_size": len(generic)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/medradar.sqlite")
    args = ap.parse_args(argv)
    build(args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
