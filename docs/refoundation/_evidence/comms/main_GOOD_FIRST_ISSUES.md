# Good first issues

These are deliberately small, verifiable, and useful. Each one names the files, the reproduce
command, and the completion condition. Claim one by opening an issue that references it.

Data corrections are the highest-value contribution for this project — the dictionaries are the
moat, not the code.

---

## 1. Add 10 missing Chinese product names (top-600 gap)

**Why:** `config/product_catalog_zh.json` covers the 600 highest-volume product codes (85.5% of
device events). Any code outside it falls back to English.

**Files:** `config/product_catalog_zh.json`

**Reproduce:**
```bash
python -m medradar products --limit 5
# pick a product code whose device_name_zh is still English
```

**Done when:** 10 codes that appear in the report have an accurate Chinese `name_zh` and one-sentence
`definition_zh`, and `python -m medradar selftest` still passes.

---

## 2. Correct a company alias that hides a subsidiary

**Why:** openFDA stores applicant names as typed. Missing subsidiaries make a major look inactive.

**Files:** `config/companies_device.json`

**Reproduce:**
```bash
python -m medradar collect --sources device --months 24 --db data/check.sqlite
python -m medradar status --db data/check.sqlite
```

**Done when:** the subsidiary string resolves (verify with a 5-line Python snippet using
`load_companies("device").resolve("<raw name>")`) and the event count for that parent increases.

---

## 3. Fix an obviously wrong product-family mapping

**Why:** family assignment is keyword-based; 255 codes are unclassified on purpose and a few are
wrong.

**Files:** `config/product_families.json`, `medradar/families.py`

**Reproduce:**
```bash
python -m medradar products --limit 25
```

**Done when:** the code is reassigned (or explicitly left `unclassified`) with a one-line reason in
the family `note`, and the coverage report still shows ≥80% classified events.

---

## 4. Translate one report chapter title and its table headers to English

**Why:** the English one-pager is thin; a full English report is a common request.

**Files:** `medradar/report.py` (English renderer)

**Done when:** `out/report_en.md` for that chapter reads naturally to a native speaker and contains
no CJK characters outside proper nouns.

---

## 5. Add a regression test for a bug you found

**Why:** the project has 274 offline tests and every fixed bug gets one.

**Files:** `tests/test_<module>.py`

**Done when:** the test fails on the previous commit, passes now, and runs without network access.

---

## 6. Document one modelling assumption you disagree with

**Why:** `docs/ASSUMPTIONS.md` is the trust contract; it should be challenged.

**Files:** `docs/ASSUMPTIONS.md`

**Done when:** the assumption has a status (`modelled` / `not modelled` / `impossible with free data`),
a concrete impact estimate, and a pointer to the code that implements it (or the issue that should).

---

## 7. Add a data-source adapter for a public feed we do not use yet

**Candidates:** FDA advisory-committee calendar, FDA recalls RSS, USPTO PatentsView.

**Files:** `medradar/collect_<name>.py` + `tests/test_<name>.py` + README source table

**Rules:** public and free, rate-limited, cached, and it must write only to the `events` table.

**Done when:** the collector is idempotent, has an offline fixture test, and the README documents its
latency honestly.

---

## 8. Reproduce the calibration on your machine and report drift

**Why:** the calibration currently replays recorded responses; a real endpoint run is the missing
piece.

**Reproduce:**
```bash
export MEDRADAR_LLM_API_KEY=...
python -m medradar.calibration run --judge http --out data/calibration/live
```

**Done when:** you open an issue with the produced `metrics.json`, the model name, and any metric
that differs from `docs/CALIBRATION.md` by more than 0.02.
