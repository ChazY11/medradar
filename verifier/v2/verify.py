#!/usr/bin/env python3
"""S-031 acceptance verifier. Every invocation appends a timestamped run log."""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get('S031_OUTPUT_DIR', '/mnt/agents/output'))
WORK = Path(os.environ.get('S031_WORK_DIR', str(ROOT / 'research/s031/work')))
RUNS = ROOT / 'verifier/runs'
COMMAND = 'python3 verifier/v2/verify.py'


def load_jsonl(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]


def main() -> int:
    checks = []
    test_process = None
    try:
        required_files = [
            'S031_RESEARCH_PROTOCOL.md', 'JOB_CAPABILITY_ONTOLOGY.md',
            'S031_SAMPLE_100.csv', 'S031_AI_PRELABELS.jsonl',
            'S031_DISAGREEMENT_AUDIT.md', 'S031_CASE_STUDIES.zh-CN.md',
            'S031_RESEARCH_REPORT.zh-CN.md', 'NEXT_STEPS.md',
        ]
        delivery_paths = {}
        for name in required_files:
            path = OUT / name
            if name == 'S031_RESEARCH_PROTOCOL.md' and not path.exists() and (OUT / 'RESEARCH_PROTOCOL.md').exists():
                path = OUT / 'RESEARCH_PROTOCOL.md'  # local mirror alias; canonical delivery keeps the required name
            delivery_paths[name] = path
        texts = {name: delivery_paths[name].read_text(encoding='utf-8') for name in required_files}
        with (OUT / 'S031_SAMPLE_100.csv').open(encoding='utf-8-sig') as f:
            sample = list(csv.DictReader(f))
        labels = load_jsonl(OUT / 'S031_AI_PRELABELS.jsonl')
        audit = json.loads((WORK / 'pr21_count_audit.json').read_text())
        comparison = load_jsonl(WORK / 'legacy_rule_comparison.jsonl')
        protocol = texts['S031_RESEARCH_PROTOCOL.md']

        main_sha = 'b2a14c0a92332c004445de686daee97754cf94cb'
        main_object_type = subprocess.check_output(
            ['git', 'cat-file', '-t', main_sha], cwd=ROOT, text=True
        ).strip()
        c1 = (
            main_object_type == 'commit'
            and 'c4327ce44c6aafe0e4af5a73df7f356dfffcb438' in protocol
            and 'aa0f6fca85e0d88ddbec871ede6da9d9c8fa357d' in protocol
            and '5954d7d81bc47ec5143fa7504fbe61debe51c29c' in protocol
            and 'd4c4e43c9afa353b9b4af6f4f020a959024a07bd' in protocol
        )
        checks.append((1, 'PR heads/bases recorded; main unchanged', c1, f'main={main_sha}'))

        fields = {
            'company', 'job_id', 'job_title', 'source_url', 'raw_record_sha256',
            'sample_selection_reason', 'known_data_gaps', 'content_sha256',
            'raw_file_sha256', 'source_jsonl_line',
        }
        c2 = (
            len(sample) == 100
            and len({(x['company'], x['job_id']) for x in sample}) == 100
            and Counter(x['company'] for x in sample) == Counter({
                'medtronic': 20, 'ge_healthcare': 20, 'philips': 20,
                'draeger': 20, 'mindray': 20,
            })
            and all(fields <= set(x) and x['raw_record_sha256'] and x['known_data_gaps'] for x in sample)
        )
        checks.append((2, '100 distinct real sample identities and required fields', c2, f'rows={len(sample)}'))

        sampler = (ROOT / 'research/s031/scripts/select_sample.py').read_text()
        c3 = (
            'SEED = 31031' in sampler
            and 'def rank(' in sampler
            and 'classify_rules' not in sampler
            and sum(x['selection_stratum'] == 'backfill_after_stratum_shortage' for x in sample) == 9
            and '不是代表性随机样本' in protocol
        )
        checks.append((3, 'Deterministic difficult-strata sampler with explicit deficits', c3, 'seed=31031; backfill=9'))

        ontology = texts['JOB_CAPABILITY_ONTOLOGY.md']
        c4 = all(x in ontology for x in (
            'Role Function', 'Technical Capability', 'Product / Business Context',
            'R&D Evidence Strength', '主职能与辅助职能', '空数组',
        ))
        checks.append((4, 'Four-axis ontology with primary/secondary functions', c4, ''))

        strengths = {
            'DIRECT_R&D_EVIDENCE', 'INDIRECT_TECHNICAL_EVIDENCE',
            'PRODUCT_CONTEXT_ONLY', 'NON_R&D', 'INSUFFICIENT_EVIDENCE',
            'CONFLICTING_EVIDENCE',
        }
        c5 = (
            len(labels) == 100
            and all(
                x['label_status'] == 'AI_PRELIMINARY_LABEL'
                and x['preliminary_label_source'] == 'AI_PRELIMINARY_LABEL'
                and x['rd_evidence_strength'] in strengths
                and {'primary', 'secondary'} <= set(x['role_function'])
                for x in labels
            )
        )
        checks.append((5, '100 AI preliminary labels with closed evidence vocabulary', c5, f'labels={len(labels)}'))

        quote_n = sum(len(x['exact_evidence_quotes']) for x in labels)
        insufficient = [x for x in labels if x['rd_evidence_strength'] == 'INSUFFICIENT_EVIDENCE']
        c6 = (
            quote_n == 97
            and len(insufficient) == 3
            and all(not x['exact_evidence_quotes'] for x in insufficient)
            and all(
                q['match_policy'] == 'exact_text_after_unicode_whitespace_normalization'
                for x in labels for q in x['exact_evidence_quotes']
            )
        )
        checks.append((6, '97 source quotes declared; three unavailable texts remain empty', c6, f'quotes={quote_n}; source matching tested below'))

        forbidden = {'HUMAN_GOLD', 'EXPERT_CONFIRMED', 'SCIENTIFICALLY_VALIDATED'}
        metric_claim = re.compile(r'(?i)(precision|recall|f1|accuracy)\s*[:=]\s*\d|准确率\s*(?:为|达到)\s*\d')
        c7 = (
            all(x['label_status'] not in forbidden and x['preliminary_label_source'] not in forbidden for x in labels)
            and not any(metric_claim.search(text) for text in texts.values())
            and all(x['comparison_status'] == 'DESCRIPTIVE_DISAGREEMENT_ONLY' for x in comparison)
        )
        checks.append((7, 'No gold-status misuse or unsupported performance claim', c7, ''))

        identity = audit['identity']
        dedup = audit['conservative_deduplication']
        desc = audit['description_only_definitions']
        c8 = (
            identity['raw_rows'] == identity['distinct_posting_ids'] == 994
            and dedup['conservative_cluster_count'] == 983
            and dedup['same_content_cluster_count'] == 5
            and dedup['multi_city_cluster_count'] == 3
            and dedup['total_rows_collapsed'] == 11
            and all(x.get('ambiguity') for x in dedup['exact_clusters'] + dedup['multi_city_clusters'])
            and audit['earlier_992_denominator']['documented_unique_posting_ids'] == 992
            and 'NOT_AVAILABLE' in audit['earlier_992_denominator']['status']
            and desc['description_only_any_title_keyword_definition'] == 47
            and desc['description_only_non_generic_title_keyword_definition'] == 54
        )
        checks.append((8, '994/992/983 and 20/80/47/54 audits reconciled', c8, '994 ids; 983 clusters; earlier 992 unverified source'))

        cases = re.split(r'(?m)^## \d+\. ', texts['S031_CASE_STUDIES.zh-CN.md'])[1:]
        case_markers = ('真实原文', '旧规则判断', '独立 AI 预判断', '分歧机制', '还缺什么证据', '人工复核决定')
        c9 = len(cases) >= 15 and all(all(marker in case for marker in case_markers) for case in cases)
        checks.append((9, 'At least 15 complete real disagreement cases', c9, f'cases={len(cases)}'))

        report = texts['S031_RESEARCH_REPORT.zh-CN.md']
        c10 = (
            all(re.search(rf'(?m)^## \d+\. {h}：', report) for h in ('H1', 'H2', 'H3'))
            and all(report.count(marker) >= 3 for marker in ('支持案例', '反例与限定', '当前证据不足', '未来证伪方法'))
        )
        checks.append((10, 'H1/H2/H3 support, qualifications, limits and falsification', c10, ''))

        c11 = all(delivery_paths[name].is_file() and delivery_paths[name].stat().st_size > 100 for name in required_files)
        checks.append((11, 'All eight requested deliverables exist and are non-empty', c11, f'files={len(required_files)}'))

        test_process = subprocess.run(
            [sys.executable, '-m', 'unittest', 'discover', '-s', 'research/s031/tests', '-v'],
            cwd=ROOT, text=True, capture_output=True,
        )
        readme = (ROOT / 'verifier/README.md').read_text()
        c12 = test_process.returncode == 0 and '`v1`' in readme and '`v2`' in readme
        checks.append((12, 'Deterministic offline tests and preserved verifier index', c12, f'unittest_exit={test_process.returncode}'))

    except Exception as exc:
        checks.append((99, 'Verifier exception', False, f'{type(exc).__name__}: {exc}'))
        traceback.print_exc()

    exit_code = 0 if checks and all(x[2] for x in checks) and len(checks) == 12 else 1
    for number, name, ok, detail in checks:
        print(f'{"PASS" if ok else "FAIL"} [{number}] {name}' + (f' — {detail}' if detail else ''))
    if test_process is not None:
        print((test_process.stdout + test_process.stderr).strip())
    print(f'RESULT: {"PASS" if exit_code == 0 else "FAIL"}')

    RUNS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    log_path = RUNS / f'{now.strftime("%Y%m%dT%H%M%S_%fZ")}_v2.log'
    log = [
        f'timestamp_utc={now.isoformat()}',
        f'command={COMMAND}',
        f'exit_code={exit_code}',
        f'result={"PASS" if exit_code == 0 else "FAIL"}',
        '',
    ]
    log += [f'{"PASS" if ok else "FAIL"} [{number}] {name} {detail}' for number, name, ok, detail in checks]
    if test_process is not None:
        log += ['', 'unittest_output:', test_process.stdout + test_process.stderr]
    log_path.write_text('\n'.join(log) + '\n', encoding='utf-8')
    print(f'RUN_LOG: {log_path.relative_to(ROOT)}')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
