#!/usr/bin/env python3
"""Compare PR #21 deterministic rules with S-031 AI preliminary labels.

This is a descriptive disagreement audit. Neither side is a human gold standard.
No network, model weights, or bulk raw-data loading is used.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(os.environ.get('S031_OUTPUT_DIR', '/mnt/agents/output'))
WORK = Path(os.environ.get('S031_WORK_DIR', str(ROOT / 'research/s031/work')))
sys.path.insert(0, str(ROOT))
from medradar.recruitment.taxonomy import classify_rules  # noqa: E402

AI_TO_LEGACY_FAMILY = {
    'RESEARCH_DEVELOPMENT': {'CORE_R&D', 'PRODUCT_ENGINEERING'},
    'PRODUCT_ENGINEERING': {'PRODUCT_ENGINEERING', 'CORE_R&D', 'HARDWARE_SYSTEMS'},
    'SOFTWARE_ALGORITHM': {'ALGORITHM_SOFTWARE'},
    'MANUFACTURING_PROCESS': {'MANUFACTURING_PROCESS'},
    'QUALITY_REGULATORY': {'QUALITY_REGULATORY'},
    'CLINICAL_RESEARCH': {'CLINICAL_R&D'},
    'CLINICAL_APPLICATION': {'CLINICAL_R&D', 'SALES_ADMIN_OTHER', 'UNCLASSIFIED'},
    'SALES_MARKETING': {'SALES_ADMIN_OTHER'},
    'FIELD_SERVICE': {'SALES_ADMIN_OTHER', 'UNCLASSIFIED', 'PRODUCT_ENGINEERING'},
    'BUSINESS_OPERATIONS': {'SALES_ADMIN_OTHER', 'UNCLASSIFIED'},
    'LEGAL_COMPLIANCE': {'SALES_ADMIN_OTHER', 'QUALITY_REGULATORY', 'UNCLASSIFIED'},
    'UNCLASSIFIED': {'UNCLASSIFIED'},
}


def load_jsonl(path: Path):
    with path.open(encoding='utf-8') as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def compact_span(span: dict) -> dict:
    return {k: span.get(k) for k in (
        'kind', 'field', 'text', 'rule', 'target', 'phrase', 'keyword',
        'keyword_kind', 'quote', 'context'
    ) if k in span}


def main() -> int:
    records = {}
    counts = Counter()
    for r in load_jsonl(WORK / 'selected_records.jsonl'):
        co = r['company_key']
        counts[co] += 1
        records[(co, r['posting_id'])] = (counts[co], r)

    labels = {
        (x['company'], x['job_id']): x
        for x in load_jsonl(OUT / 'S031_AI_PRELABELS.jsonl')
    }
    assert len(records) == len(labels) == 100

    comparison_path = WORK / 'legacy_rule_comparison.jsonl'
    summary = {
        'study_id': 'S-031',
        'comparison_status': 'DESCRIPTIVE_DISAGREEMENT_ONLY',
        'truth_warning': (
            'PR #21 rules and S-031 AI labels are both non-gold. Counts below are '
            'not accuracy, precision, recall, F1, or error rates.'
        ),
        'n': 0,
        'rules_versions': Counter(),
        'legacy_function_counts': Counter(),
        'legacy_track_status_counts': Counter(),
        'legacy_mapped_track_counts': Counter(),
        'function_family_crosstab': Counter(),
        'function_family_disagreement_n': 0,
        'audit_candidate_counts': Counter(),
        'ai_strength_by_legacy_track_status': Counter(),
    }

    with comparison_path.open('w', encoding='utf-8') as dst:
        for key in sorted(records):
            sample_index, r = records[key]
            ai = labels[key]
            assert ai['sample_index'] == sample_index
            old = classify_rules({
                'job_title': r['job_title'],
                'job_description': r.get('job_description') or '',
            })
            cb = old.get('confidence_basis') or {}
            version = cb.get('rules_version')
            track_status = (old.get('track_evidence') or {}).get('track_status')
            candidate = (old.get('track_evidence') or {}).get('candidate') or {}
            primary = ai['role_function']['primary']
            family_ok = old['function_class'] in AI_TO_LEGACY_FAMILY.get(primary, set())
            caps = ai['technical_capabilities']
            products = ai['product_business_context']
            candidates = []
            if old.get('track_id') and not caps and products:
                candidates.append('FALSE_TECHNICAL_ATTRIBUTION_REVIEW')
            if caps and not old.get('track_id'):
                candidates.append('MISSED_TECHNICAL_CAPABILITY_REVIEW')
            if old.get('track_id') and products and not caps:
                candidates.append('PRODUCT_CAPABILITY_CONFUSION_REVIEW')
            if old.get('track_id') and ai['rd_evidence_strength'] in {
                'PRODUCT_CONTEXT_ONLY', 'NON_R&D', 'INSUFFICIENT_EVIDENCE'
            }:
                candidates.append('UNSUPPORTED_INFERENCE_REVIEW')
            if track_status == 'SUPPRESSED_BY_FUNCTION_CLASS' and ai['rd_evidence_strength'] == 'DIRECT_R&D_EVIDENCE':
                candidates.append('FUNCTION_GATE_DIRECT_RD_REVIEW')
            if not family_ok:
                candidates.append('FUNCTION_FAMILY_DISAGREEMENT')

            row = {
                'study_id': 'S-031',
                'comparison_status': 'DESCRIPTIVE_DISAGREEMENT_ONLY',
                'company': key[0],
                'sample_index': sample_index,
                'job_id': key[1],
                'job_title': r['job_title'],
                'source_url': r['source_url'],
                'collection_status': r.get('collection_status'),
                'legacy': {
                    'rules_version': version,
                    'function_class': old['function_class'],
                    'track_id': old.get('track_id'),
                    'track_status': track_status,
                    'track_candidate_id': candidate.get('track_id'),
                    'function_decision_basis': (old.get('function_evidence') or {}).get('decision_basis'),
                    'function_unclassified_reason': (old.get('function_evidence') or {}).get('unclassified_reason'),
                    'function_spans': [compact_span(x) for x in (old.get('function_evidence') or {}).get('spans', [])],
                    'track_spans': [compact_span(x) for x in (old.get('track_evidence') or {}).get('spans', [])],
                },
                'ai_preliminary': {
                    'label_status': ai['label_status'],
                    'role_function': ai['role_function'],
                    'technical_capabilities': caps,
                    'product_business_context': products,
                    'rd_evidence_strength': ai['rd_evidence_strength'],
                    'needs_human_review': ai['needs_human_review'],
                },
                'function_family_agreement_for_audit_only': family_ok,
                'audit_candidates': candidates,
                'not_an_error_label': True,
            }
            dst.write(json.dumps(row, ensure_ascii=False) + '\n')

            summary['n'] += 1
            summary['rules_versions'][version] += 1
            summary['legacy_function_counts'][old['function_class']] += 1
            summary['legacy_track_status_counts'][track_status] += 1
            if old.get('track_id'):
                summary['legacy_mapped_track_counts'][old['track_id']] += 1
            summary['function_family_crosstab'][f"{primary} -> {old['function_class']}"] += 1
            summary['function_family_disagreement_n'] += int(not family_ok)
            summary['audit_candidate_counts'].update(candidates)
            summary['ai_strength_by_legacy_track_status'][
                f"{track_status} -> {ai['rd_evidence_strength']}"
            ] += 1

    def plain(obj):
        if isinstance(obj, Counter):
            return dict(sorted(obj.items(), key=lambda kv: (-kv[1], str(kv[0]))))
        if isinstance(obj, dict):
            return {k: plain(v) for k, v in obj.items()}
        return obj

    (WORK / 'legacy_rule_comparison_summary.json').write_text(
        json.dumps(plain(summary), ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(plain(summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
