"""Summarise the track-hypothesis primary tests for the Lead's reports."""
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "hypotheses" / "track" / "results" / "primary_tests.json"
d = json.loads(P.read_text(encoding="utf-8"))
print(json.dumps(d, indent=2, ensure_ascii=False)[:7000])
