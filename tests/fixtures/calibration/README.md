# Calibration replay fixture

This directory is the **frozen evidence** behind `docs/CALIBRATION.md`. It exists so
the calibration can be re-scored with no API key and no network:

```bash
python docs/calibration/score.py        # replays this fixture, verifies the published table
```

## Layout

| Path | What it is |
|---|---|
| `manifest.json` | provenance: model, prompt version, recording date, source file + sha1, `raw_source` |
| `filings/<id>.txt` | the 25 labelled SEC 8-K / press-release texts (public filings, verbatim) |
| `llm/responses.json` | recorded LLM judge output, one entry per filing |
| `heuristic/responses.json` | recorded keyword-baseline (`HeuristicJudge`) output, same filings |

Each entry in `responses.json`:

```jsonc
{
  "id": "cal-02",
  "headline": "Verona Pharma 8-K",              // headline the judge saw
  "fingerprint": "sha1(PROMPT_VERSION|headline|text[:24000])",  // lookup key
  "filing_sha1": "sha1(full filing text)",
  "raw": "{ ... model-style JSON verdict ... }",  // re-parsed at replay time
  "raw_source": "reconstructed_from_parsed_verdict",
  "recorded_verdict": {"direction": 1, "materiality": 0.90, "catalyst_type": "approval"}
}
```

Replay joins by `fingerprint`, never by call order, so it is idempotent and
order-independent. `medradar.llm.parse_verdict` re-derives the verdict from `raw`
on every call - this directory stores evidence, not conclusions.

## Provenance (read this before citing)

* **Recorded:** 2026-10-31（取自判定归档文件 `docs/calibration/llm_verdicts.json` 的写入时间；
  原始 LLM 调用日期未归档）。
* **Original run:** the 2026-10 calibration described in `docs/CALIBRATION.md` §1, executed
  through DSH sub-agents with the production prompt/schema (`PROMPT_VERSION = 8k-v1`).
* **`raw_source = "reconstructed_from_parsed_verdict"`:** the chat-completions **string was
  not archived** in the original run (see `docs/CALIBRATION.md` §6.7). `raw` is a minimal,
  valid model-style JSON object rebuilt from the archived parsed verdict. It is enough to
  reproduce the *scoring pipeline* end-to-end (accuracy, confusion matrices, Spearman/MAE,
  P/R/F1), but it is **not** a recording of the original response string and it is **not**
  independent validation of the endpoint.
* To upgrade this to a real recording, re-run with a key:

  ```bash
  MEDRADAR_LLM_API_KEY=... python -m medradar.calibration run \
    --judge http --filings tests/fixtures/calibration/filings \
    --labels docs/calibration/ground_truth.csv --out data/calibration/runs/http
  ```

  then export a new fixture with `python -m medradar.calibration export-fixtures` and update
  `manifest.json` with the new `recorded_at` / `raw_source`.

## Regenerating

```bash
python -m medradar.calibration export-fixtures \
  --filings tests/fixtures/calibration/filings \
  --labels docs/calibration/ground_truth.csv \
  --verdicts docs/calibration/llm_verdicts.json \
  --out tests/fixtures/calibration --suite llm \
  --model deepseek-chat --recording-date 2026-10-31 --source-note "<where this came from>"
```

Bump `medradar.llm.PROMPT_VERSION` first if the prompt/schema changed: the fingerprint
depends on it, so old recordings stop matching (by design - a prompt change invalidates a
calibration).
