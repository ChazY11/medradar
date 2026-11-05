# S-031 acceptance criteria v2

Created: 2026-11-05. Scope: independent hiring-capability study only; v1 remains the legacy programme verifier.

1. PR #21 head, base and dependency are recorded; `main` and frozen artifacts are unchanged by S-031.
2. The final sample contains exactly 100 distinct source posting identities, 20 per company where data permit; any shortfall is explicit. Every row carries company, source job id, title, URL, exact raw JSONL record SHA-256, selection reason and data-gap field.
3. Sample selection is deterministic under seed 31031, stratified for difficult functions and product-context controls, and reproducible from committed PR #21 JSONL without network access.
4. The ontology separates role function, technical capability, product/business context and R&D evidence strength; primary and secondary functions are distinct.
5. There is one AI prelabel per sampled job, with all required fields, closed evidence-strength values and `preliminary_label_source=AI_PRELIMINARY_LABEL` only.
6. Every evidence quote is verbatim locatable in the cited raw title or description after NFC/whitespace normalisation; no quote is manufactured.
7. No output is called HUMAN_GOLD, EXPERT_CONFIRMED or SCIENTIFICALLY_VALIDATED; no Precision/Recall/F1/accuracy claim is made from these preliminary labels.
8. The audit independently recomputes 994 raw rows, 994 distinct opaque posting ids and 983 conservative deduplicated clusters for the final Medtronic snapshot, and explains the separate 992 earlier snapshot/denominator. Ambiguous duplicate clusters remain flagged.
9. At least 15 case studies contain real evidence, old-rule output, independent prelabel, disagreement mechanism, missing evidence and a human-review decision.
10. H1/H2/H3 each have supporting cases, counterexamples or qualifications, current evidentiary limits and a future falsification method.
11. Eight requested deliverables exist under `/mnt/agents/output/`, are readable by a non-programmer, and name material data gaps rather than filling them.
12. Lightweight scripts have deterministic offline tests; the final verifier exits 0 and every run is logged under `verifier/runs/`.

Verification command: `python3 verifier/v2/verify.py`.
