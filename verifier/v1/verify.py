#!/usr/bin/env python3
"""Repository-level acceptance checks; run from the MedRadar source root."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
failures: list[str] = []

def require(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)

corpus = (ROOT / 'medradar/corpus.py').read_text(encoding='utf-8')
for category in ('clinical_hold', 'refuse_to_file', 'pre_submission'):
    require(f'"{category}"' in corpus, f'missing event category: {category}')
require('"clinical hold": "clinical_hold"' in corpus, 'clinical hold is not independently classified')
require('"refuse to file": "refuse_to_file"' in corpus, 'refuse to file is not independently classified')

cases = (ROOT / 'medradar/cases.py').read_text(encoding='utf-8')
require('pre_submission' in cases, 'case engine lacks pre-submission handling')
require('audit' in cases.lower() and 'extreme' in cases.lower(), 'case study lacks extreme-return audit')

frontier_path = ROOT / 'medradar/frontier.py'
require(frontier_path.is_file(), 'frontier module is missing')
frontier = frontier_path.read_text(encoding='utf-8')
require('DEVICE_FILING_RE' in frontier and 'non_device_filing' in frontier,
        'frontier feed does not exclude non-device filings')
require('non_device_trial' in frontier and 'device_intervention_text' in frontier,
        'frontier feed does not exclude non-device trials')
adcom = ROOT / 'medradar/adcom.py'
require(adcom.is_file(), 'FDA advisory-committee collector is missing')

replay = (ROOT / 'medradar/replay.py').read_text(encoding='utf-8')
require('QUALITY_ALLOWED = ("datetime", "date")' in replay,
        'replay accepts timestamps other than observed date/datetime')
available_sql = replay.split('def _available_sql', 1)[-1].split('\ndef ', 1)[0]
require('event_date' not in available_sql and 'signal_date' not in available_sql,
        'replay availability SQL still falls back to a decision/signal date')
analyze = (ROOT / 'medradar/analyze.py').read_text(encoding='utf-8')
require('trading_timestamp_ok' in analyze and 'def tradeable' in analyze,
        'metrics signal layer lacks the shared public-timestamp gate')
clinical = (ROOT / 'medradar/clinical.py').read_text(encoding='utf-8')
for token in ('InterventionType', 'DEVICE_INTERVENTION_TYPES', 'device_intervention_text',
              'match_frontier_text'):
    require(token in clinical, f'device-trial classification missing {token}')
util = (ROOT / 'medradar/util.py').read_text(encoding='utf-8')
require('datetime.fromisoformat' in util, 'ISO public datetimes are not supported by date parsing')

tracks = json.loads((ROOT / 'config/tracks_device.json').read_text(encoding='utf-8'))
text = json.dumps(tracks, ensure_ascii=False)
for token in ('life_support', 'ivd', 'brain_computer', 'domain'):
    require(token in text, f'device taxonomy missing {token}')

init = (ROOT / 'medradar/__init__.py').read_text(encoding='utf-8')
pyproject = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
require('0.3.0' in init and 'version = "0.3.0"' in pyproject, 'version is not consistently 0.3.0')

print(json.dumps({'status': 'ok' if not failures else 'failed', 'failures': failures}, ensure_ascii=False, indent=2))
sys.exit(1 if failures else 0)
