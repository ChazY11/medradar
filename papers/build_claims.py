"""Build papers/CLAIMS.json: every quantitative claim in the paper, with its source.

The paper must not contain a number that cannot be found in a committed artifact. Each claim is
declared as (id, statement, value-as-stated-in-the-paper, source file, exact source substring), then
the substring is verified against the source. A failure means the paper or the claim is wrong.

    python papers/build_claims.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CLAIMS = [
    # ---- data and provenance
    ("D1", "regulatory lane events", "31,802", "research/STATE.json", "31802"),
    ("D2", "legal entities resolved", "9,412", "research/MISSION.md", "9,412 entities"),
    ("D3", "window start", "2016-11", "research/STATE.json", "2016-11"),
    ("D4", "device trial lane events", "2,663", "experiments/b040/REPORT.md", "2,663"),
    ("D5", "trial lane device tracks", "43", "experiments/b040/collection_manifest.json",
     '"distinct_device_tracks": 43'),
    ("D6", "trial lane companies", "46", "experiments/b040/collection_manifest.json",
     '"distinct_companies": 46'),
    # ---- detection at controlled FAR (cycle 3)
    ("M1", "naive detector sensitivity at 2 % FAR", "0.223", "research/DECISIONS.md", "0.223"),
    ("M2", "CUSUM sensitivity at 2 % FAR", "0.181", "research/DECISIONS.md", "0.181"),
    ("M3", "Bayes factor sensitivity at 2 % FAR", "0.122", "research/DECISIONS.md", "0.122"),
    ("M4", "z-score sensitivity at 2 % FAR", "0.112", "research/DECISIONS.md", "0.112"),
    # ---- cycle 2 power
    ("P1", "curated-panel ΔAP", "0.056", "experiments/cycle2_coverage/analysis.json",
     "0.05644645491148638"),
    ("P2", "entity-panel ΔAP", "0.097", "experiments/cycle2_coverage/pred_p2.json",
     "0.09738123148139934"),
    ("P3", "entity-panel MDE at 140 positives", "0.167",
     "experiments/cycle2_coverage/analysis.json", "0.16742674021055617"),
    # ---- cycle 4 co-movement
    ("C1", "co-movement cells under lane-volume null", "3 of 32", "research/DECISIONS.md", "3 of 32"),
    ("C2", "co-movement cells under track-volume null", "0 of 32", "research/DECISIONS.md", "0 of 32"),
    # ---- cycle 5 independent lane
    ("L1", "eligible cross-lane cells", "16", "experiments/b040/REPORT.md", "16 pass the floors"),
    ("L2", "largest cross-lane correlation", "0.036", "experiments/b040/REPORT.md", "0.036"),
    # ---- cycles 6/7 retraction
    ("E1", "entries that were entity appearances", "3,804", "research/DECISIONS.md", "3,804"),
    ("E2", "share of entries that were entity appearances", "79 %", "research/DECISIONS.md", "79 %"),
    ("E3", "entries after the prior-filer control", "1,010",
     "experiments/detect_v1/entries_priorfiler.json", '"entries": 1010'),
    ("E4", "ivd_immuno under the churn control", "0.0010", "research/DECISIONS.md", "0.0010"),
    ("E5", "ivd_immuno after the prior-filer control", "1.0", "research/DECISIONS.md", "p = 1.0"),
    # ---- cycle 8 split sample
    ("H1", "tracks nominated by the clean design", "3", "research/DECISIONS.md", "3 nominated"),
    ("H2", "tracks confirmed by the clean design", "0", "research/DECISIONS.md", "0 confirmed"),
    ("H3", "holdout power at 30 % wave concentration", "0.25", "research/DECISIONS.md", "0.25"),
    # ---- cycles 13/14 calibration
    ("K1", "naive ratio flags across the roster", "35 of 53", "research/DECISIONS.md", "35 of 53"),
    ("K2", "calibrated detections across the roster", "4", "research/DECISIONS.md", "supports **4**"),
    ("K3", "Olympus rate ratio", "4.17", "research/DECISIONS.md", "4.17"),
    ("K4", "Philips rate ratio", "2.03", "research/DECISIONS.md", "2.03"),
    ("K5", "largest per-company MDE", "22.93", "research/DECISIONS.md", "22.93"),
    # ---- cycle 15 rolling origin
    ("R1", "rolling-origin cells", "376", "research/DECISIONS.md", "376"),
    ("R2", "rolling-origin observations", "717", "research/DECISIONS.md", "717"),
    ("R3", "pre-registered naive increase lift", "0.49", "research/DECISIONS.md", "0.49"),
    ("R4", "corrected naive increase lift", "1.22", "research/DECISIONS.md", "1.22"),
    ("R5", "calibrated flags in the benchmark", "5 flags in 717", "research/DECISIONS.md",
     "5 flags in 717"),
    # ---- cycle 16 point in time
    ("T1", "leakage problems found", "0", "research/RESULTS/cycle16_point_in_time_2026-11-03.md",
     "0 leakage problems"),
    ("T2", "lane events used at 2020-12-31", "12,853",
     "research/RESULTS/cycle16_point_in_time_2026-11-03.md", "12,853"),
    ("T3", "stable verdicts across four as-of dates", "40",
     "research/RESULTS/cycle16_point_in_time_2026-11-03.md", "40 stable"),
    ("T4", "reversed verdicts", "2", "research/RESULTS/cycle16_point_in_time_2026-11-03.md",
     "2 reverse"),
    # ---- engineering
    ("G1", "test suite size", "854", "experiments/b027/selftest_cycle16.log", "Ran 854 tests"),
    # ---- context
    ("D7", "months in the evidence window", "119", "research/STATE.json", "119 months"),
    ("D8", "median material events per cell per month", "0.21", "research/STATE.json",
     "~0.21/month"),
    ("D9", "rolling-origin origins", "12",
     "research/RESULTS/cycle15_rolling_origin_2026-11-03.md", "12 origins"),
    ("D10", "mandated deep-case companies", "5", "research/MISSION.md",
     "Deep-case companies (5, mandated)"),
    ("D11", "device roster size", "51", "research/DECISIONS.md", "51-company device roster"),
    # ---- alert-shape classification (cycles 19-20)
    ("S1", "confirmed sustained-change precision", "0.914", "research/DECISIONS.md", "0.914"),
    ("S2", "confirmed sustained base rate", "0.696", "research/DECISIONS.md", "0.696"),
    ("S3", "confirmed balanced accuracy", "0.584", "research/DECISIONS.md", "0.584"),
    ("S4", "confirmed spike recall", "0.787", "research/DECISIONS.md", "0.787"),
    ("S5", "alert-shape discovery balanced accuracy", "0.394", "research/DECISIONS.md", "0.394"),
    ("S6", "post-hoc discovery balanced accuracy", "0.608", "research/DECISIONS.md", "0.608"),
    # ---- deployment resolution (cycle 21)
    ("U1", "quarterly deployment sensitivity of the z-score", "0.147", "research/DECISIONS.md", "0.147"),
    ("U2", "quarterly deployment z-score CI lower bound", "0.112", "research/DECISIONS.md", "0.112"),
    ("U3", "quarterly deployment z-score CI upper bound", "0.182", "research/DECISIONS.md", "0.182"),
    ("U4", "Kendall tau between quarterly and monthly rankings", "−1.0", "research/DECISIONS.md", "−1.0"),
    # ---- product integration (cycle 22)
    ("V1", "deployment false-alarm rate stated in profiles", "0.018", "research/DECISIONS.md", "**0.018**"),
    ("V2", "profile test count after the deployment block", "44", "research/RESULTS/cycle22_product_2026-11-03.md", "44 tests"),
    # ---- entity-level confirmation (cycle 23)
    ("W1", "entity-level balanced accuracy", "0.594", "research/DECISIONS.md", "0.594"),
    ("W2", "entity-level sustained precision", "0.917", "research/DECISIONS.md", "0.917"),
    ("W3", "entity-level sustained base rate", "0.705", "research/DECISIONS.md", "0.705"),
    ("W4", "entity-level ramp recall", "0.117", "research/DECISIONS.md", "0.117"),
    ("W5", "eligible entity cells", "191", "research/DECISIONS.md", "191"),
    # ---- second-domain validation (cycle 26)
    ("X1", "second-domain balanced accuracy", "0.593", "research/DECISIONS.md", "0.593"),
    ("X2", "second-domain sustained precision", "0.929", "research/DECISIONS.md", "0.929"),
    ("X3", "second-domain sustained base rate", "0.794", "research/DECISIONS.md", "0.794"),
    ("X4", "eligible hiring series in the second domain", "eight of thirteen", "research/DECISIONS.md", "Eight of thirteen"),
    # ---- market-aggregate validation (cycle 29)
    ("Y1", "market-aggregate balanced accuracy", "0.559", "research/DECISIONS.md", "0.559"),
    ("Y2", "market-aggregate sustained precision", "0.889", "research/DECISIONS.md", "0.889"),
    ("Y3", "market-aggregate ramp recall", "0.396", "research/DECISIONS.md", "0.396"),
    ("Y4", "tracks eligible at market-aggregate level", "38", "research/DECISIONS.md", "38 tracks, all eligible"),
    # ---- density experiment (cycle 30)
    ("Z1", "dense track ramp recall", "0.440", "research/DECISIONS.md", "0.440"),
    ("Z2", "sparse track ramp recall", "0.222", "research/DECISIONS.md", "0.222"),
    ("Z3", "density rank correlation", "0.882", "research/DECISIONS.md", "0.882"),
    # ---- density confirmation (cycle 31)
    ("AA1", "density-confirmation dense ramp recall", "0.444", "research/DECISIONS.md", "0.444"),
    ("AA2", "density-confirmation sparse ramp recall", "0.204", "research/DECISIONS.md", "0.204"),
    ("AA3", "density-confirmation rank correlation", "0.908", "research/DECISIONS.md", "0.908"),
    ("AA4", "density-confirmation effect ratio", "2.18", "research/DECISIONS.md", "2.18"),
    ("AA5", "ramp reporting density floor", "1.0", "research/DECISIONS.md", "1.0 event per month"),
    # ---- seasonality (cycle 41)
    ('CC1', 'January month factor', '0.891', 'experiments/b074/seasonality.json', '0.8907'),
    ('CC2', 'annual month-factor spread', '1.255', 'experiments/b074/seasonality.json', '1.2551020408163265'),
    ('CC3', 'month-of-year permutation p-value', '0.0005', 'experiments/b074/seasonality.json', '0.0004997501249375312'),
    ('CC4', 'quarter-boundary factor', '1.058', 'experiments/b074/seasonality.json', '1.0579'),
    ('CC5', 'detector alert rate on raw counts', '0.0090', 'experiments/b074/seasonality.json', '0.009017223910840932'),
    ('CC6', 'cell-months changed by seasonal adjustment', '9 of 39,151', 'research/DECISIONS.md', '9 of 39,151'),
    # ---- pipeline evaluation (cycle 34)
    ("BB1", "pipeline promoted persistence rate", "0.800", "research/DECISIONS.md", "0.800"),
    ("BB2", "pipeline unpromoted persistence rate", "0.667", "research/DECISIONS.md", "0.667"),
    ("BB3", "pipeline control persistence rate", "0.373", "research/DECISIONS.md", "0.373"),
    ("BB4", "pipeline promotion difference", "0.133", "research/DECISIONS.md", "0.133"),
]


def read_any(path: Path) -> str:
    """Read a committed artifact whatever encoding the shell wrote it in.

    Redirected PowerShell logs are UTF-16LE while Markdown and JSON are UTF-8; a claim verifier that
    assumes one encoding silently fails on the other, so decode explicitly.
    """
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", "replace")


def main() -> int:
    out = Path("papers/CLAIMS.json")
    out.parent.mkdir(exist_ok=True)
    failures = []
    records = []
    for claim_id, statement, value, source, needle in CLAIMS:
        source_path = Path(source)
        if not source_path.exists():
            failures.append((claim_id, f"missing source {source}"))
            continue
        text = read_any(source_path)
        if needle not in text:
            failures.append((claim_id, f"{needle!r} not found in {source}"))
            continue
        records.append({"id": claim_id, "statement": statement, "value": value,
                        "source": source, "source_needle": needle})
    out.write_text(json.dumps({"claims": records}, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"verified {len(records)} of {len(CLAIMS)} claims")
    for claim_id, problem in failures:
        print(f"  FAIL {claim_id}: {problem}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
