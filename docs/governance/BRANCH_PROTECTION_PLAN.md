# Branch protection plan — `main`

**Status: NOT APPLIED.** Phase-2 hardening (licence inventory/content scan, freeze
format 2 with an audited rebalance log, the rule-change audit, the state-bump
tool) is implemented on `governance/phase2-hardening`; this plan is still only a
plan — no protection has been configured.

This document is a plan for the repository owner
(`ChazY11`). No GitHub setting has been changed, no API call was made, and the
repository currently has **no branch protection** on `main`.

This is a **solo-maintainer** repository. The plan is designed so that the
machine gates become effective without pretending a second reviewer exists:
required approving reviews stay at **zero**, and the owner keeps an explicit,
audited emergency bypass.

---

## 1. What is proposed (classic branch protection rule)

Apply to branch name pattern: **`main`**

| Setting | Value | Why this value for one maintainer |
| --- | --- | --- |
| Require a pull request before merging | **ON** | Forces every change through the governance workflow and leaves a reviewable diff. The owner opens their own PRs; this is a checkpoint, not a second opinion. |
| Required approving reviews | **0** | There is no second maintainer. A non-zero value can only be satisfied by the owner approving their own work (GitHub does not count self-approval) — it would block every merge or be bypassed silently. |
| Dismiss stale pull request approvals | **OFF** | No approvals to dismiss. |
| Require review from Code Owners | **OFF** | `CODEOWNERS` is routing only (see that file). Turning this on would require an approval that cannot exist. |
| Require conversation resolution before merging | **ON** (recommended) | A one-person workflow still benefits from "every comment is answered or resolved"; costs nothing when there are no comments. Optional if it becomes friction. |
| Require status checks to pass before merging | **ON** | This is the actual enforcement. The checks are the governance gates plus the existing `ci` workflow. |
| Required status checks (exact names) | `governance / state`, `governance / views`, `governance / frozen`, `governance / licence`, `governance / links`, `governance / rule-audit`, and the `ci` jobs: `py3.10 offline suite + wheel smoke`, `py3.11 offline suite + wheel smoke`, `py3.12 offline suite + wheel smoke`, `offline data stats (fixture mini DB)`, `windows data-files + demo` | Machine gates, all satisfiable by the owner. If a required check name changes (job renamed), merges block until this list is updated — that is a deliberate alarm, not an accident. |
| Require branches to be up to date before merging | **OFF** | With ~20 open draft PRs, "strict" forces a rebase-and-rerun on every `main` movement for no scientific gain; the merge commit itself is still a git object and `main` still runs `ci` on push. **Revisit when a second maintainer or an auto-merge pipeline exists.** |
| Require linear history | **OFF** | The repository deliberately uses merge commits (`Merge pull request #11 ...`); linear history would forbid the established flow. |
| Require signed commits | **OFF** | Not part of this change; can be added later without affecting the gates. |
| Include administrators / "Do not allow bypassing the above settings" | **OFF** (administrators are allowed to bypass) | The owner is the only admin. This is the **emergency bypass**: it keeps the repository usable if the governance workflow itself is broken. Every bypass is recorded in the repository audit log ("Bypassed rule violations") — the bypass is auditable, not invisible. |
| Allow force pushes | **OFF** | Protects published history and the recorded `PROJECT_STATE.yaml` / `FROZEN.yaml` digests. A force push to `main` would make every digest claim unverifiable. |
| Allow deletions | **OFF** | Prevents an accidental (or scripted) deletion of `main`. |
| Lock branch | **OFF** | Normal PR flow must remain possible. |

> **GitHub UI note.** GitHub has two implementations: classic *Branch protection
> rules* and the newer *Rulesets*. Both can express the settings above. Use
> **Settings → Branches → Add branch protection rule** for the classic flow
> below, or **Settings → Rules → New ruleset → Target `main`** with the same
> values and `Repository admin` in the bypass list. Do **not** use both at once
> for the same branch — pick one, record the choice here, and delete the other.

> **Where the checks come from.** The five `governance` checks run on **pull
> requests** (`.github/workflows/governance.yml` is a merge gate; it deliberately
> does not run on pushes to `main`, because the state file describes the PR's base
> `main` and a post-merge run would be red by design until the next PR updates the
> state). The `ci` checks run on both pull requests and `main` pushes. So the
> required-check picker only offers the `governance` names on a PR run — open a
> trivial PR after merging this change to make them selectable.

---

## 2. Exact UI steps for the owner

1. Open `https://github.com/ChazY11/medradar/settings/branches`.
2. Click **Add branch protection rule** (or **Add classic branch protection rule**).
3. **Branch name pattern:** `main`.
4. Tick **Require a pull request before merging**. Leave *Required approvals* at
   **0**. Leave **Dismiss stale pull request approvals** and **Require review
   from Code Owners** unticked.
5. Tick **Require status checks to pass before merging**. In the check picker,
   add the six `governance / ...` jobs and the `ci` jobs listed in the table
   above. Leave **Require branches to be up to date before merging** unticked.
6. Optionally tick **Require conversation resolution before merging**.
7. Leave **Require linear history**, **Require signed commits**, **Lock branch**
   unticked.
8. Tick **Do not allow bypassing the above settings** → **NO** (leave unticked,
   so administrators keep the emergency bypass). If the UI shows **Include
   administrators** separately, leave it unticked as well.
9. Leave **Allow force pushes** and **Allow deletions** unticked.
10. Click **Create** / **Save changes**.
11. Record the applied date and any deviations from this plan in
    `docs/governance/GOVERNANCE.md` (a one-line change in a governance PR).

**Precondition (updated for Phase 2):** the hardened `governance` workflow must have
run at least once on a PR after this branch merges (the rule-audit and base-ref
jobs need `fetch-depth: 0`, which the workflow now requests). The licence and freeze
gates now have the inventory/rebalance controls the Phase-1 review asked for, and
`tools/governance/bump_state.py` exists, so the activation blockers from that
review are resolved **on this branch** — they become true for `main` only after
the branch merges.

The original precondition also applies: the `governance` workflow must have run at least once on a PR
in the last seven days, otherwise GitHub's check picker does not offer the
`governance / ...` names (GitHub only lists recently observed checks). Merge the
Phase-0 governance PR first, open a trivial PR, let `governance` run, then apply
the settings.

---

## 3. Why this is safe for a single-person workflow

- **No unreviewable gate.** Every required check is a deterministic script the
  owner can run locally before pushing (`docs/governance/GOVERNANCE.md` lists the
  commands). Nothing depends on a second human.
- **The owner is not locked out.** Admin bypass remains enabled; if a gate is
  wrong or GitHub is degraded, the owner can still merge, and the audit log
  records it. The bypass is a documented escape hatch, not a policy hole.
- **History cannot be rewritten or deleted.** Force pushes and deletions are
  blocked, which is what makes `PROJECT_STATE.yaml`'s recorded head and
  `FROZEN.yaml`'s digests meaningful.
- **No churn from strict up-to-date.** Draft PRs do not need rebasing on every
  `main` commit; `main` itself still runs `ci` on push.
- **Failure is visible.** A renamed job or a broken gate blocks merges with a
  named check, instead of silently stopping enforcement.

## 4. Emergency procedure (owner bypass)

1. Prefer fixing the gate: a governance failure is normally a real finding
   (stale view, changed frozen file, unclassified data source).
2. If the check itself is broken: merge the fix as a normal PR if possible.
3. Only if merging is impossible, use the admin bypass, and in the PR body state
   (a) why, (b) which check was bypassed, (c) the follow-up commit/issue that
   restores the gate. The bypass appears in the repository audit log.
4. A bypass must never be used to land a scientific claim that would otherwise
   fail a gate; that is the one case where the answer is "do not merge".

## 5. What this plan does NOT do

- It does not create independent scientific review. There is still one
  maintainer and one pair of eyes; the gates check *form, provenance and
  consistency*, not correctness of a scientific claim.
- It does not apply itself, and this document must not be treated as proof that
  protection exists. Verify in **Settings → Branches** before relying on it.
- It does not change `ci`. The existing `ci` workflow is already the required
  behavioural test suite; governance adds consistency gates around it.
- It does not stop the owner from editing `PROJECT_STATE.yaml` incorrectly — it
  stops the *repository* from accepting that edit silently, because the checks
  fail until the state is true again.

## 6. When a second maintainer exists

Revisit, in this order: required approvals → **1**; **Require review from Code
Owners** → ON; **Require branches to be up to date** → ON; **Do not allow
bypassing** → ON (owner loses the emergency bypass); then remove the
solo-maintainer rationale from this file. Until then, do not turn these on: a
merge-blocking setting nobody can satisfy is worse than no setting.
