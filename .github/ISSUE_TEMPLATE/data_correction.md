---
name: Data correction
about: A company alias, track mapping, or event label is wrong
title: "[data] "
labels: data
---

Data quality is the project's main value, so corrections are the most welcome contribution.

## What is wrong

- [ ] Company / subsidiary alias (`config/companies_*.json`)
- [ ] Track mapping (`config/product_code_tracks.json`)
- [ ] Event classification (`kind` / `track_id`)
- [ ] Missing event (source exists, MedRadar missed it)

## The record

- Raw applicant / sponsor / firm string:
- Source URL (FDA / SEC / CT.gov):
- Event date:
- Product code (if device):

## What the correct value should be

- Correct parent company:
- Correct track (Chinese name is fine):
- Correct event type:
- Reasoning / evidence link:

## How you verified

- [ ] Checked the original source page
- [ ] Checked the parent company's official subsidiary list
- [ ] Ran `python -m medradar collect --sources ...` and the alias still misses
