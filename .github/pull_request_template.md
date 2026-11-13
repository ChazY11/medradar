<!--
MedRadar pull request template — replacement draft (Phase 0 governance MVP).

This repository is maintained by ONE person (solo maintainer). The template is
deliberately a checklist of evidence and claims, not a request for a second
opinion: branch protection is planned without mandatory approving reviews.
Keep the sections even when a section says "none" — "none" is a claim too.
-->

# Pull request

## 1. Classification

- [ ] Bug fix (behaviour corrected; regression test included)
- [ ] Documentation only (no code, no state claim)
- [ ] Research artifact (new result, retraction, frozen input, or study record)
- [ ] Governance / infrastructure
- [ ] Release or version bump

**Summary (one paragraph, plain language):**

**Paths changed (what a reviewer would have to read):**

## 2. Capability claim

What capability does this PR claim, and at what status?

- [ ] No new capability is claimed (docs/refactor only)
- [ ] `working` — has an evidence path and, where applicable, an offline test
- [ ] `draft` — implemented but explicitly not relied on yet
- [ ] `retired` — records a capability that was withdrawn (name the decision)

If `PROJECT_STATE.yaml` changes, name the capability/study entry id here:
**Entry id(s):** `...` · **Evidence path(s):** `...`

## 3. Evidence for every number

Any number in this PR — description, docs, generated views, paper text — needs a
committed artifact and a command that reproduces it. "I ran it" is not evidence.

| Number | Value | Artifact path | Command |
| --- | --- | --- | --- |
| | | | |

- [ ] No number is asserted without an artifact
- [ ] Null results are reported as null **with** the minimum detectable effect
- [ ] "Not run" is stated as "not run", not left implied
- [ ] Generated views were regenerated (`gen_views.py`), never hand-edited

## 4. Gates (paste the exit codes)

- [ ] `python tools/governance/check_state.py` → `0`
- [ ] `python tools/governance/gen_views.py --check` → `0`
- [ ] `python tools/governance/check_frozen.py` → `0`
- [ ] `python tools/governance/check_licence.py` → `0`
- [ ] `python tools/governance/check_links.py` → `0`
- [ ] `python -m pytest -q` → `0` (or explain below why it was not run)
- [ ] If `tests/` changed: `python tools/governance/record_tests.py` was run and
      the new `pytest_count.json` is committed in this PR

Exit codes / notes:
```text

```

## 5. Not claimed

What does this PR explicitly NOT establish? (Scope limits, unmeasured effects,
survivorship, resolution limits, single-domain results, ...)

- [ ] The PR description names at least one thing that is not claimed, or states
      "nothing beyond the artifact above is claimed".

## 6. Freeze checklist

- [ ] No file listed in `docs/governance/FROZEN.yaml` changed bytes
- [ ] No file was added to or removed from a frozen study directory
- [ ] Frozen forecast sets were not edited
- [ ] If a freeze changed: this PR **is** the dedicated re-baseline commit, with
      the reason and the authorising decision id stated above

## 7. Base vs ancestry check

- [ ] This PR targets `main`, not a stale integration or ancestor branch
- [ ] `git merge-base --is-ancestor origin/main HEAD` succeeds
- [ ] `git diff --stat origin/main...HEAD` contains only intended paths
- [ ] The branch was rebased/merged from current `main`, not from an old base
- [ ] `PROJECT_STATE.yaml` still describes `main` (its `main.head` matches
      `origin/main`), not this branch
