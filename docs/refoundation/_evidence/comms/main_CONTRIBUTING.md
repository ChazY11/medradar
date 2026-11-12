# Contributing to MedRadar

Thanks for helping. The most valuable contributions are **not** code — they are the curated
knowledge files that make the data trustworthy.

## Highest-impact contributions

### 1. Company / subsidiary aliases (`config/companies_*.json`)

openFDA stores applicant names as typed. If a major's subsidiary is missing, its clearances vanish
from the radar. Add the alias, then verify:

```bash
python -m medradar collect --sources device --months 24 --db data/check.sqlite
python -m medradar status --db data/check.sqlite
```

Rules: aliases must be **distinctive**. Never add a bare token such as `JOHNSON` or `GENERAL` — it
matches hundreds of unrelated applicants. Prefer the shortest string that cannot collide.

### 2. Track dictionary (`config/tracks_*.json`)

Each track needs a Chinese name, an English name, and English keywords matched against openFDA
`device_name` / `definition` text. Keep keywords specific; longest match wins.

### 3. Track mapping corrections (`config/product_code_tracks.json`)

Generated from openFDA classification by keyword matching; wrong mappings are expected. Override by
editing the mapping and re-running `collect`.

## Code contributions

```bash
python -m unittest discover -s tests -t .   # must pass offline
python -m medradar selftest
```

* Standard library only. The core must run on a bare Python 3.10+ with no pip install.
* Collectors only write the `events` table; analysis, report and trading must not need changes.
* Every new metric updates `docs/METHODS.md` **and** `docs/SCHEMA.md` first.
* No lookahead: any feature must use only data timestamped `<= event_date`.
* Never invent data. If a source is blocked (e.g. NMPA WAF), return `unavailable` and say why.

## Reporting data problems

Open an issue with: the raw applicant string, the FDA detail URL, and what the correct parent company
is. Those three lines are enough to fix the registry.
