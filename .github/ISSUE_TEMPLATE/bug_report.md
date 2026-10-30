---
name: Bug report
about: Something is broken or a documented behaviour is not honoured
title: "[bug] "
labels: bug
---

## What happened

## What you expected

## Reproduce

```bash
# exact commands, including flags and the DB you used
```

## Environment

- OS:
- Python version:
- MedRadar commit:
- Data source(s) involved (openFDA / EDGAR / CT.gov / NMPA / Yahoo):

## Evidence

- Error output (full traceback if any):
- `python -m medradar status` output:
- If it is a data issue: the raw source URL and the offending record id.

## Did you check

- [ ] `python -m medradar selftest` passes
- [ ] `python -m medradar doctor` (once available) or `status` looks normal
- [ ] This is not an upstream data outage (openFDA/EDGAR return errors)
