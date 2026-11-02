# Promotions

**These are promotion decisions, not findings.** A promotion records that an alert's change persisted under
the confirmed two-month rule (D-043, replicated D-048) and that a named human accepted it. Findings live in
`README.md`; this file is append-only and each row names its signer. Rows marked `PENDING_SIGNOFF` have
complete evidence but no signature, which is the state an autonomous session must leave them in: the
programme can prepare a promotion but cannot sign one for a human (D-054).

**Reviewer checklist before signing.** A signer must have inspected, at minimum: (1) the alert row with its
track, quarter, event count, baseline mean and z; (2) the two confirmation quarters used to classify the
change as sustained; (3) the profile's contradictory-evidence findings for that company; (4) the measured
false-alarm rate and sensitivity of the deployed detector at quarterly resolution (0.0179 and 0.147); and (5)
an independent piece of evidence for the same technical area from independent_corroboration. A promotion
signed without (5) is a rate change, not a technology change, and must be labelled as such.

| id | company | track | alert_quarter | shape | relative_post_rate | policy_version | verdict | signer | signed_at_utc | justification |
|---|---|---|---|---|---|---|---|---|---|---|
| medtronic:insulin_delivery:2025-Q3 | medtronic | insulin_delivery | 2025-Q3 | ramp | 6.0 | promotion_policy_v1 | PENDING_SIGNOFF | — | — | — |
