# REPRODUCIBILITY - independent replay of SCIENCE-002

**Claim tested.** The ten committed artifacts of SCIENCE-002 can be regenerated
byte-for-byte from (a) the frozen commit, (b) the cached raw sources, (c) the
documented seeds, on this machine.

**Result: all ten artifacts reproduce identically.**

## 1. Environment

| item | value |
|---|---|
| commit under review | `a3c3516fc3395117763e28dd029c214fb7d3d0ee` (PR #42 head) |
| reproduction checkout | a **separate** git worktree at the same commit, detached HEAD, no edits |
| Python | 3.12.10 (CPython), Windows |
| third-party packages needed | none for fetch/build/experiment; matplotlib 3.11.2 for figures only |
| raw sources | the openFDA ZIPs and SEC JSON cache produced by the original run, reused via a directory junction so nothing was re-downloaded |
| seeds | 20261114 (permutation and bootstrap), λ = 1.0, 2,000 permutations, 2,000 bootstrap draws, 100 placebo-feature draws |
| command | `python research/science_002/cli.py experiment --offline` |

## 2. Artifact comparison

| artifact | bytes | SHA-256 identical |
|---|---|---|
| `experiment_results.json` | 12,145 | **yes** |
| `panel.csv` | 881,431 | **yes** |
| `universe.csv` | 7,869 | **yes** |
| `entity_matches.csv` | 23,008 | **yes** |
| `entity_exclusions.csv` | 3,346 | **yes** |
| `panel_summary.json` | 1,088 | **yes** |
| `universe_summary.json` | 6,864 | **yes** |
| `source_manifest.json` | 50,024 | **yes** |
| `audit_results.json` | 2,288 | **yes** |
| `sensitivity_results.json` | 2,111 | **yes** |

Byte identity here is a strong statement: the JSON is written with sorted keys and
fixed indentation, the CSV with a fixed field order, and the experiment consumes
exactly 2,000+2,000 deterministic draws from `random.Random(20261114)`. A single
reordered row, a changed tie-handling rule or a different bootstrap draw would
change the bytes.

**Not compared byte-for-byte:** the three PNGs. Matplotlib rendering depends on the
installed library and font stack, so image bytes are not a reproducibility unit.
What *is* verified is that `figures_manifest.json` records the SHA-256 of the three
inputs (experiment payload, panel, universe) and that those inputs are the ones
reproduced above, i.e. the figures are drawn from reproducible data by fixed code.

## 3. What the audit re-ran independently (not just replayed)

| analysis | module | relationship to the frozen code |
|---|---|---|
| selection-bias rebuilds | `selection.py` | imports the frozen panel/experiment; changes only *which firms* are included |
| block permutation, quarterly rebuild, jackknife | `stats_review.py` | re-implements the statistic and the nulls; imports only AUC and the fitting routine |
| coverage, tier conflicts, establishment-field shape | `entity_audit.py` | independent of the frozen audit module |
| every reported count | `internal_consistency.py` | reads artifacts only, recomputes 35 claims |

The selection rebuild reproduces the committed payload exactly for the base scenario
(-0.033663969385031994), which is the audit's own check that its harness is faithful
before it is used to argue that the sample is wrong.

## 4. What was not reproduced

| item | why | consequence |
|---|---|---|
| the raw downloads | 330 MB; the cached bytes have committed SHA-256s in `source_manifest.json` and the four data-file hashes match the original run | none for the audit: the question was whether the *analysis* reproduces from the recorded bytes |
| the SEC/HTTP layer | no network access was used, by design | a researcher on a different day would fetch different bytes; the manifest is what makes that detectable |
| the figures' pixels | renderer-dependent | see above |
| the 2026-11 FDA snapshot itself | not re-downloaded | the study is a snapshot study; a later snapshot would legitimately differ |

## 5. Cross-machine caveat

The reproduction ran on one machine, one OS and one Python version. Two things in
the tree are platform-sensitive and were checked:

* the audit's own `figures_manifest.json` path normalisation (fixed to POSIX
  separators during SCIENCE-002, before this audit);
* CRLF/LF handling in CSV writing: `write_csv` writes `\n` explicitly, and the
  repository's `.gitattributes` governs checkout, so the bytes are stable.

The repository's CI runs the offline suite on Python 3.10, 3.11 and 3.12 and passed
on all three for the commit under review; that is a *portability* check, not a
reproduction of the artifacts.

## 6. Verdict on reproducibility

**Pass, within the stated scope.** The analysis is reproducible from the recorded
raw-byte identities; the raw sources themselves are externally mutable and are
pinned by hash rather than by availability. That is the strongest form available
for a snapshot study over public data.
