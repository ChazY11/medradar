# USER_TEST_TASKS

Three tasks a professional user must be able to complete in the private alpha, plus the feedback
record template.

> **Status: internally simulated, not externally validated.** The three tasks below were executed
> by the delivery team against the real product (`scripts/alpha_smoke.py`, 16/16 checks) and in a
> real browser (16/16 E2E checks). **No external alpha participant has been recruited or tested.**
> This file must not be read as evidence of external user validation.

## Task 1 - understand one competitor

As an analyst tracking Medtronic:

1. Search "Medtronic" and open the organization page.
2. State what FDA activity the snapshot covers for it (sources, date window) and what it does not.
3. Find how much of that activity rests on independently verified attribution.
4. Filter to the most recent recall records and open one.
5. Reach the official FDA page for that record.

**Done when** the user can quote: the date window, the number of attributed records, the curated
share, and the official URL - without help.

**Measured in this release:** reachable in 5 clicks; page shows window 1977-10-28..2026-10-30,
17,473 records, curated share 24.1% (this organization is above the portfolio median), official link
on every record.

## Task 2 - compare two companies without being misled

1. Compare Medtronic and GE HealthCare.
2. Confirm both sides use the same window and the same event types.
3. Read the comparability verdict and the warnings.
4. Switch the ownership basis to "original registrant only" and explain what changed.
5. Export the report and confirm it says the same thing as the screen.

**Done when** the user can explain why "10,000 records vs 3,000 records" is not an innovation or
market-share statement, and why GE HealthCare drops to 0 records under the original-registrant basis.

**Measured in this release:** window 2021-01-01..2025-12-31; Medtronic 3,426 records (20.7% curated),
GE HealthCare 493 (100% curated, all pre-spin-off); four warnings raised including verification
asymmetry; Markdown export 7,430 bytes with the same numbers.

## Task 3 - find and correct one wrong attribution

As an internal reviewer:

1. Open the review queue, sorted by records affected.
2. Open a case: "Abbott Vascular-Cardiac Therapies dba Guidant Corporation" (17 records, retrieved
   under both Abbott and Boston Scientific scopes, currently unattributed).
3. Read the original FDA records that depend on it.
4. Record the decision: attribute to Abbott with evidence and a reason.
5. Confirm the query results updated.
6. Confirm no other organization's count moved.
7. Withdraw the decision and confirm the previous state returns and the history keeps both entries.

**Done when** all seven steps succeed and the reviewer can show the "1 changed / 58 unchanged"
impact statement.

**Measured in this release:** PASS in the smoke test and the browser suite; abbot changes
8,737 -> 8,754 records (+17), 58 other organizations unchanged, history preserved across a
withdrawal. This is the flagship workflow of PRODUCT-002.

## Feedback record template

Copy one row per participant. Do not fill this in for people who did not actually participate.

```
participant_id:            (pseudonymous, e.g. P-01)
date:
role:                      (regulatory analyst / competitive intelligence / consultant / other)
organization_type:         (manufacturer / consultancy / investor / academic / other)
device_domain:
consent_to_quote:          (yes / no)
installed_without_help:    (yes / no - if no, what blocked)
task_1_completed:          (yes / no)   time:
task_2_completed:          (yes / no)   time:
task_3_completed:          (yes / no)   time:
metric_that_confused:      (attributed share / rule-verified / curated / precision / retrieval / none)
trust_statement_they_used: (quote what they said they would tell a colleague)
wrong_answer_they_gave:    (any place the product let them form a wrong belief)
blocking_defect:
severity:                  (P0 blocks the task / P1 distorts a judgement / P2 friction)
willing_to_use_weekly:     (yes / maybe / no) and why
```

## Synthesis rules (when real participants exist)

* Report the number of participants and the number who completed each task; never report a task as
  "validated" from a demo by the delivery team.
* Report every wrong belief a participant formed, including ones caused by wording.
* Any P0 defect blocks the next alpha round.
* Compare against the internal baseline (16/16) and say plainly if external users did worse.
