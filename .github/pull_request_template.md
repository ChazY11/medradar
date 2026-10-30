## What this PR changes

## Why

<!-- Link the issue if there is one: Closes #123 -->

## Type

- [ ] Bug fix (add a regression test)
- [ ] Data correction (JSON/config only)
- [ ] New metric or analysis (update docs/METHODS.md and docs/SCHEMA.md first)
- [ ] Docs / packaging / CI

## Checklist

- [ ] `python -m medradar selftest` passes locally, offline
- [ ] No new runtime dependency in the core package (stdlib only)
- [ ] No lookahead: any feature uses only data timestamped `<= event_date`
- [ ] If a metric changed meaning, `docs/METHODS.md` and `docs/SCHEMA.md` are updated
- [ ] If data quality changed, the before/after counts are in the description
- [ ] No fabricated or hard-coded data; blocked sources return `unavailable` with a reason

## Evidence

<!-- Commands run and the numbers you saw. Screenshots welcome for UI changes. -->
