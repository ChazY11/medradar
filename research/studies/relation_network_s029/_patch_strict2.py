import pathlib
p=pathlib.Path("code/s029_07_claims.py"); s=p.read_text(encoding="utf-8")
# remove the late (post-write) normalisation block
late='''    for c2 in claim_rows:
        c2.setdefault("observation_system",
                      "THIS_STUDY_COLLECTION" if c2.get("time_basis") == "ACTUAL_OBSERVATION"
                      else "NONE")
        # STRICT standard (adopted from the independent temporal audit): a claim counts as a
        # genuine observed-as-of record ONLY if its first_seen_at is an observation recorded by
        # the MedRadar Live Observatory ledger. This study's collection wall clock is not that:
        # it is a backfill fetch of an already-published record. Recorded separately so no
        # downstream analysis can silently use the weaker definition.
        c2["strict_observed_asof"] = False

'''
assert late in s
s=s.replace(late,"")
# insert the normalisation BEFORE persistence, right after de-duplication
anchor='''    write_jsonl(DATA_DIR / "entities.jsonl", ent_rows)'''
early='''    # STRICT standard (adopted from the independent temporal audit): a claim counts as a genuine
    # observed-as-of record ONLY if its first_seen_at was recorded by the MedRadar Live Observatory
    # ledger. This study's collection wall clock is not that — it is a backfill fetch of an
    # already-published record. The lenient label (published within 7 days of our own fetch) is kept
    # in time_basis for transparency but never used for a point-in-time claim.
    for c2 in claim_rows:
        c2.setdefault("observation_system",
                      "THIS_STUDY_COLLECTION" if c2.get("time_basis") == "ACTUAL_OBSERVATION"
                      else "NONE")
        c2["strict_observed_asof"] = False

''' + anchor
assert anchor in s
s=s.replace(anchor, early, 1)
p.write_text(s,encoding="utf-8")
import ast; ast.parse(s); print("patched: strict field written before persistence")
