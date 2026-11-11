# Recovered evidence from the git object database

Commands used (read-only; no refs changed):

```
git fsck --no-reflogs --unreachable --dangling
git cat-file --batch-all-objects --batch-check='%(objectname) %(objecttype) %(objectsize)'
git cat-file blob <sha>
```

The 135 unreachable blobs of this repository include three EXP-H2 session
scratch scripts, dumped here verbatim:

| blob | size | content |
|---|---|---|
| `eea3b8b7b192a3641cf6d037604f5a3c728d5ee2` | 601 B | reads `EXP_H2_SUMMARY.json` and `EXP_H2_PAIRS.jsonl`, prints `finding` keys, verdicts, `hard_negative_rules_attempted`, pair count and a sample row |
| `d23bdd49d09550e5d06b61f33a17e6698eb41ae3` | 596 B | reads the summary, prints `per_signal_sufficiency`, `signal_sufficiency_table`, verdicts and the finding counters |
| `f354ee3cfef56155040ba90c4e478bc64698dea8` | 469 B | text-patches `exp_h2_identity.py`: `hard, hn_rules = add_hard_negatives(...)` and adds the `"hard_negative_rules_attempted": hn_rules` summary key |

They are working-tree helpers from the final session: the patch script proves the
committed summary key `hard_negative_rules_attempted` was added late, and the two
inspectors read that final summary shape.

No earlier implementation of `exp_h2_identity.py` was found. A scan of all 5,565
blobs of at most 3 MB (reachable and unreachable) for `EXP-H2`, `EXP_H2`,
`signal_sufficiency`, `by_construction_rule`, `HN2_same_model_token`,
`HN4_subsidiary`, and a second scan for `pair_id` / `signal_set` / `build_pairs` /
`hard_negative` inside H2/EXP content, returned exactly one H2 implementation
blob: `d09ffd540be83f5d3d7cf278c3210eb1a923121c` (23,022 bytes), which is the
committed script. The largest unreachable blob is 52,540,515 bytes (unrelated);
no unreachable blob occupies the 600–750 KB range that an earlier 712-row pair
file would occupy.

`scan_objects.py` and `scan2.py` are the scan programs used; rerun them from the
repository root for reproducibility.
