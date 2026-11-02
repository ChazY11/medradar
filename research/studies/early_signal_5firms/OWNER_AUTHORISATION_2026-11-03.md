# OWNER AUTHORISATION — 2026-11-03: AI adjudication as the study's final labels, human sign-off waived

**Given by:** the project owner, in session (DeepSeek Harness, 2026-11-03, Asia/Shanghai).
**Scope:** `early_signal_5firms` **Target B** (the 69-packet technology-shift labels) and its downstream analysis.
**Not in scope:** the separate promotion policy (`medradar/intelligence/promotion.py`), whose named-human sign-off is a
safety gate for operational technology-change claims and is **unchanged** by this authorisation.

## The instruction, in the owner's words

> "我希望这批 AI 标签直接作为本研究的最终裁决，并且修改人工签字，不需要人工签字了，然后你继续推进"
>
> (I want this batch of AI labels to serve directly as the study's final adjudication, and change the human
> signature requirement — no human signature is needed — then continue.)

## What this changes

1. **The labelling authority for Target B moves** from "a named human reviewer" to the owner-authorised external AI
   review delivered 2026-11-03 (`external_ai_review_2026-11-03/`, reviewer field
   `Codex AI (not a human reviewer)`). Its 69 labels become the study's **final labels**.
2. **The human sign-off gate is waived** for this study by owner instruction. `ADJUDICATION_HUMAN_V1.json` will not
   exist and is no longer expected. The `HUMAN_REVIEW_WORKSHEET.csv` human columns stay empty — they are not filled
   retroactively, because the labels are not human work and must never be presented as such.
3. **A new tier is created:** `FINAL_ADJUDICATION_AI_OWNER_AUTHORISED`. It is *final for this study* but remains
   `human_truth = false`. Every downstream artifact must carry both facts.

## What this does NOT change — the evidentiary consequence

The study's Target B result must be **reported as AI-adjudicated, owner-authorised, not human gold standard**. It may
be used to conclude this study (including a negative conclusion), it may be cited with its provenance, and it may
support the programme's descriptive claims; it may **not** be described as expert/human adjudication, and it may not
be pooled with human-labelled benchmark sets elsewhere in the repository. The external review's other caveats remain
binding: it had read the earlier labels (not blind), and its uncertainty grades are qualitative, not calibrated
probabilities.

## Provenance

- AI review delivery: `research/studies/early_signal_5firms/external_ai_review_2026-11-03/` (59 MB PDF bundle pinned by
  `SHA256SUMS.txt`, not committed; public FDA/CT.gov URLs retained per packet).
- Reviewed commit: `969fd0cc4fea040cbdb7a518f3c300b9122980b5`.
- Ingested as a non-human tier in D-078 / S-034 / R168; promoted to the study's final adjudication here:
  **D-079 / S-035 / R172–R175**.
