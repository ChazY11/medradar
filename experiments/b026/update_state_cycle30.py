"""Update STATE, BACKLOG, claims for cycle 30 (density experiment, failed pre-registered bar)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")
CLAIMS = Path("papers/CLAIMS.json")
BUILD = Path("papers/build_claims.py")

TASK_DONE = """  - id: B-063
    layer: detect
    priority: P1
    title: Controlled density experiment (thin dense track series)
    status: done
    owner: lead
    depends_on: [B-062]
    acceptance: >
      Binomial thinning of the 38 dense track series at factors 1,2,5,10,20, then identical injection,
      detector and classifier. Ramp recall 0.440 -> 0.415 -> 0.300 -> 0.318 -> 0.222 as density falls
      twentyfold; Spearman rho 0.882 (passes its floor) but strict monotonicity failed on a 0.018 inversion
      and dense/sparse intervals overlapped by 0.023. Verdict as pre-registered: NOT SUPPORTED. Recorded as a
      strength of the pre-registration and a defect of its brittleness; scaling stays suggestive.


"""

TASK_NEW = """  - id: B-064
    layer: detect
    priority: P1
    title: Confirmation of the density scaling with a robust criterion and fresh draws
    status: todo
    owner: lead
    depends_on: [B-063]
    acceptance: >
      Pre-register a criterion in terms of rank correlation (>=0.8) AND dense-to-sparse effect size (dense ramp
      recall >= 2x sparse) with no strict-monotonicity clause, then confirm on FRESH seeds and a FRESH thinning
      draw. If it confirms, the scaling may be reported as an experimentally established density dependence; if
      not, it is closed as suggestive only.


"""

EXTRA = [
    ("Z1", "dense track ramp recall", "0.440", "research/DECISIONS.md", "0.440"),
    ("Z2", "sparse track ramp recall", "0.222", "research/DECISIONS.md", "0.222"),
    ("Z3", "density rank correlation", "0.882", "research/DECISIONS.md", "0.882"),
]


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-03T17:40:00+08:00"
    state["phase"] = "density_experiment_failed_its_bar"
    state["cycle"] = 32
    state["last_completed_cycle"] = {
        "cycle": 30,
        "name": "controlled_density_experiment",
        "branch": "research/change-detection-v1",
        "report": "experiments/b026/density_experiment.json",
        "summary": "research/RESULTS/cycle30_density_2026-11-03.md",
        "verdict": ("controlled thinning test did NOT clear its pre-declared bar: ramp recall fell 0.440 -> "
                    "0.222 as density fell twentyfold with rank correlation 0.882, but strict monotonicity "
                    "broke by 0.018 and dense/sparse intervals overlapped by 0.023. Scaling stays suggestive; "
                    "the brittle criterion is recorded as a defect of the pre-registration"),
    }
    state["detection_layer"]["density_experiment"] = {
        "artifact": "experiments/b026/density_experiment.json",
        "decision": "research/DECISIONS.md D-058 (pre-registration), D-059 (outcome)",
        "design": "binomial thinning of 38 dense track series at factors 1,2,5,10,20",
        "ramp_recall": {"1": 0.440, "2": 0.415, "5": 0.300, "10": 0.318, "20": 0.222},
        "spearman_rho": 0.882,
        "precision_range": [0.885, 0.927],
        "monotone": False,
        "intervals_disjoint": False,
        "verdict": "NOT SUPPORTED as pre-registered",
        "reading": ("effect size halves with density and rank correlation is 0.88, but two of three gates fail "
                    "narrowly; scaling stays suggestive, not established"),
        "preregistration_defect": ("strict monotonicity across five noisy point estimates is brittle; a rank-"
                                   "correlation plus effect-size criterion is the right test (B-064)"),
    }
    state["established_findings"] = state["established_findings"] + [
        "DETECT: the controlled density experiment FAILED its pre-declared bar (strict monotonicity broke by "
        "0.018; intervals overlapped by 0.023) even though ramp recall halved with density and rho = 0.882 - the "
        "scaling remains suggestive, not established",
        "METHOD: a pre-registration can be too brittle - requiring strict monotonicity from five noisy point "
        "estimates voids a large, consistent effect on a 0.018 wobble; the criterion, not the data, was the "
        "problem and is recorded as such",
    ]
    state["next_actions"] = [
        "B-064: robust-criterion confirmation of the density scaling on fresh seeds and a fresh thinning draw",
        "keep the paper's density claim marked suggestive until B-064 reports",
        "wire the audit into the round-end routine",
        "consider a second paper focused on the measurement rules",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-063" not in text:
        text = text.rstrip("\n") + "\n\n" + TASK_DONE
    if "id: B-064" not in text:
        text = text.rstrip("\n") + "\n\n" + TASK_NEW
        print("B-063 and B-064 appended")
    BACKLOG.write_text(text, encoding="utf-8", newline="\n")

    payload = json.loads(CLAIMS.read_text(encoding="utf-8"))
    by_id = {claim["id"]: claim for claim in payload["claims"]}
    for claim_id, statement, value, source, needle in EXTRA:
        by_id[claim_id] = {"id": claim_id, "statement": statement, "value": value,
                           "source": source, "source_needle": needle}
    payload["claims"] = [by_id[key] for key in sorted(by_id)]
    CLAIMS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8", newline="\n")

    build_text = BUILD.read_text(encoding="utf-8")
    if '"Z1"' not in build_text:
        block = "\n".join(
            f'    ("{claim_id}", "{statement}", "{value}", "{source}", "{needle}"),'
            for claim_id, statement, value, source, needle in EXTRA)
        anchor = [line for line in build_text.splitlines() if '"Y4"' in line][0]
        build_text = build_text.replace(
            anchor, anchor + "\n    # ---- density experiment (cycle 30)\n" + block, 1)
        BUILD.write_text(build_text, encoding="utf-8", newline="\n")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"],
          "claims:", len(payload["claims"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
