#!/usr/bin/env python3
"""Independently recompute PR #21 Medtronic snapshot and denominator audits.

Streams the 994-row JSONL; stores only small grouping metadata. No network.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'experiments/innovation_signals_observatory/results/2026-11-04'
JOBS = BASE / 'jobs_medtronic.jsonl'
WORK = Path(os.environ.get('S031_WORK_DIR', str(ROOT / 'research/s031/work')))
sys.path.insert(0, str(ROOT))
from medradar.recruitment.taxonomy import classify_rules  # noqa: E402
from medradar.recruitment.records import content_hash  # noqa: E402

spec = importlib.util.spec_from_file_location(
    'pr21_diagnose', ROOT / 'experiments/innovation_signals_observatory/sources/diagnose_track_coverage.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PROBES = module.PROBES


def rows():
    with JOBS.open(encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            if line.strip():
                yield line_no, json.loads(line)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    result = {
        'study_id': 'S-031',
        'source': str(JOBS.relative_to(ROOT)),
        'source_sha256': sha256_file(JOBS),
        'method': 'independent streaming recomputation; not copied from PR #21 summary counts',
        'identity': {},
        'content_hash_audit': {},
        'classification': {},
        'description_only_definitions': {},
        'robotics_and_probe_audit': {},
        'conservative_deduplication': {},
        'earlier_992_denominator': {
            'status': 'DOCUMENTED_BUT_SOURCE_FILE_NOT_AVAILABLE_FOR_INDEPENDENT_HASH_VERIFICATION',
            'documented_raw_rows': 994,
            'documented_unique_posting_ids': 992,
            'documented_dropped_same_id_rows': 2,
            'documented_sha256': '165dce8e8c6b8127ba445d3a668117d614ad47193daf74b250d8b67c51f80217',
            'source_document': 'experiments/innovation_signals_observatory/docs/EVIDENCE_REPORT.zh-CN.md §2.1–2.2',
            'current_branch_history_check': (
                'The two Git versions of jobs_medtronic.jsonl visible on this branch contain '
                '994 distinct ids each (SHA cff61741… and 2ca362ee…). Neither is the documented '
                '165dce8e… file. Therefore 992 is an earlier documented denominator, not a count '
                'to mix into the current 994-unique-id snapshot.'
            ),
        },
    }

    ids = set()
    raw_rows = 0
    hash_rule_present = Counter()
    content_matches = Counter()
    function_counts = Counter()
    track_status_counts = Counter()
    gate_audit = Counter()
    track_counts = Counter()
    rule_strength = Counter()
    title_hit = Counter()
    title_non_generic_hit = Counter()
    robot_title_n = 0
    probe_mentions = Counter()
    probe_assigned = Counter()
    same_content = defaultdict(list)
    same_title_desc = defaultdict(list)

    for line_no, r in rows():
        raw_rows += 1
        ids.add(r['posting_id'])
        hash_rule_present['hash_rule_version' in r] += 1
        recomputed = content_hash(
            title=r.get('job_title'), location=r.get('job_location'),
            description=r.get('job_description')
        )
        content_matches[recomputed == r.get('content_sha256')] += 1
        title = r.get('job_title') or ''
        desc = r.get('job_description') or ''
        if re.search(r'robot', title, re.I):
            robot_title_n += 1
        old = classify_rules({'job_title': title, 'job_description': desc})
        function_counts[old['function_class']] += 1
        te = old.get('track_evidence') or {}
        track_status_counts[te.get('track_status')] += 1
        if te.get('track_status') == 'SUPPRESSED_BY_FUNCTION_CLASS':
            candidate = te.get('candidate') or {}
            if candidate:
                gate_audit['any_specific_candidate'] += 1
            if candidate and (
                candidate.get('title_specific_keywords')
                or len(candidate.get('description_specific_keywords') or []) >= 2
                or candidate.get('frontier_hits', 0) >= 1
            ):
                gate_audit['would_pass_same_track_threshold_without_function_gate'] += 1
        assigned = old.get('track_id')
        text = title + '\n' + desc
        for track, patterns in PROBES.items():
            if re.search('|'.join(patterns), text, re.I):
                probe_mentions[track] += 1
                if assigned == track:
                    probe_assigned[track] += 1
        if assigned:
            track_counts[assigned] += 1
            rule_strength[(old.get('confidence_basis') or {}).get('track', {}).get('rule_strength')] += 1
            assigned_spans = [s for s in te.get('spans', []) if s.get('target') == assigned]
            if any(s.get('field') == 'job_title' for s in assigned_spans):
                title_hit[assigned] += 1
            if any(s.get('field') == 'job_title' and not s.get('generic') for s in assigned_spans):
                title_non_generic_hit[assigned] += 1

        # Metadata only: no full descriptions retained in memory.
        loc = r.get('job_location') or ''
        req = ((r.get('raw') or {}).get('jobReqId') or (r.get('raw') or {}).get('jobreqid'))
        meta = {
            'posting_id': r['posting_id'], 'job_title': title,
            'job_location': loc, 'requisition_id': req,
            'source_url': r.get('source_url'), 'source_jsonl_line': line_no,
        }
        same_content[r.get('content_sha256')].append(meta)
        td_key = hashlib.sha256(
            (re.sub(r'\s+', ' ', title).strip() + '\0' + re.sub(r'\s+', ' ', desc).strip()).encode()
        ).hexdigest()
        same_title_desc[td_key].append(meta)

    result['identity'] = {
        'raw_rows': raw_rows, 'distinct_posting_ids': len(ids),
        'same_posting_id_duplicate_rows': raw_rows - len(ids),
        'title_robot_substring_rows': robot_title_n,
        'title_robotic_or_robotics_only_rows_note': (
            'The broader title probe is /robot/i. Restricting to robotic|robotics misses '
            'titles such as “Technical Consultant- Robot assisted surgery”.'
        ),
    }
    result['content_hash_audit'] = {
        'stored_hash_matches_current_records_content_hash': content_matches[True],
        'stored_hash_mismatches': content_matches[False],
        'hash_rule_version_field_present': hash_rule_present[True],
        'hash_rule_version_field_absent': hash_rule_present[False],
        'limitation': (
            'A matching recomputation supports consistency with the current rule, but the absent '
            'hash_rule_version field remains a real provenance gap and is not retroactively repaired.'
        ),
    }
    result['classification'] = {
        'rules_version': 'recruitment_taxonomy_rules_2026-11-04b',
        'function_counts': dict(sorted(function_counts.items())),
        'track_status_counts': dict(sorted(track_status_counts.items())),
        'mapped_track_counts': dict(sorted(track_counts.items())),
        'mapped_rule_strength_counts': dict(sorted(rule_strength.items())),
        'function_gate_audit': {
            **dict(sorted(gate_audit.items())),
            'interpretation': (
                '168 is the subset that would pass the existing track threshold if the function '
                'gate were removed; 275 merely have a best specific candidate. Neither count is '
                'a verified false-positive count without semantic review.'
            ),
        },
    }
    mapped_n = sum(track_counts.values())
    any_title_n = sum(title_hit.values())
    non_generic_title_n = sum(title_non_generic_hit.values())
    result['description_only_definitions'] = {
        'mapped_postings': mapped_n,
        'assigned_track_has_any_title_keyword': any_title_n,
        'description_only_any_title_keyword_definition': mapped_n - any_title_n,
        'assigned_track_has_non_generic_title_keyword': non_generic_title_n,
        'description_only_non_generic_title_keyword_definition': mapped_n - non_generic_title_n,
        'interpretation': (
            '47 and 54 are different measurements, not interchangeable error metrics. The first '
            'counts generic title words such as software as title evidence; the second does not.'
        ),
    }
    result['robotics_and_probe_audit'] = {
        track: {
            'plain_language_mentions': probe_mentions[track],
            'assigned_to_same_track': probe_assigned[track],
            'probe_patterns': PROBES[track],
        }
        for track in PROBES
    }

    exact_clusters = []
    exact_excess = 0
    for group in same_content.values():
        if len(group) > 1:
            exact_excess += len(group) - 1
            exact_clusters.append({
                'kind': 'SAME_TITLE_LOCATION_DESCRIPTION',
                'size': len(group), 'ambiguity': (
                    'Different opaque ids may be duplicate republications or simultaneous hires '
                    'for multiple people. Conservative collapse is a counting choice, not a fact '
                    'that only one vacancy existed.'
                ),
                'members': group,
            })

    multi_clusters = []
    multi_excess = 0
    for group in same_title_desc.values():
        # First collapse exact title+location+description copies, then inspect cities.
        unique_exact = {}
        for m in group:
            unique_exact[(m['job_title'], m['job_location'], m['posting_id'])] = m
        # Groups with exact copies need city-distinct representatives.
        by_location = {}
        for m in group:
            by_location.setdefault((m['job_title'], m['job_location']), m)
        representatives = list(by_location.values())
        if len(representatives) > 1 and len(group) > 1:
            multi_excess += len(representatives) - 1
            multi_clusters.append({
                'kind': 'SAME_TITLE_DESCRIPTION_MULTIPLE_CITIES',
                'size_after_exact_copy_collapse': len(representatives),
                'ambiguity': (
                    'One multi-city vacancy and several city-specific vacancies are both plausible. '
                    'Different requisition numbers do not resolve that organizational question.'
                ),
                'members': representatives,
            })

    result['conservative_deduplication'] = {
        'starting_distinct_posting_ids': len(ids),
        'same_content_cluster_count': len(exact_clusters),
        'same_content_rows_collapsed': exact_excess,
        'multi_city_cluster_count': len(multi_clusters),
        'multi_city_rows_collapsed_after_exact_copy_collapse': multi_excess,
        'total_rows_collapsed': exact_excess + multi_excess,
        'conservative_cluster_count': len(ids) - exact_excess - multi_excess,
        'expected_reconciliation': '994 - 6 - 5 = 983',
        'exact_clusters': exact_clusters,
        'multi_city_clusters': multi_clusters,
        'warning': (
            '983 is a conservative analytical cluster count under an explicit ambiguity-preserving '
            'rule, not a verified count of unique human vacancies or new hiring demand.'
        ),
    }

    assert raw_rows == len(ids) == 994
    assert content_matches[True] == 994 and content_matches[False] == 0
    assert hash_rule_present[False] == 994
    assert robot_title_n == 20
    assert probe_mentions['surgical_robotics'] == 80
    assert probe_assigned['surgical_robotics'] == 0
    assert mapped_n == 61 and mapped_n - any_title_n == 47 and mapped_n - non_generic_title_n == 54
    assert gate_audit['any_specific_candidate'] == 275
    assert gate_audit['would_pass_same_track_threshold_without_function_gate'] == 168
    assert len(exact_clusters) == 5 and exact_excess == 6
    assert len(multi_clusters) == 3 and multi_excess == 5
    assert result['conservative_deduplication']['conservative_cluster_count'] == 983

    path = WORK / 'pr21_count_audit.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'conservative_deduplication'}}, ensure_ascii=False, indent=2))
    print('conservative_deduplication', {k: v for k, v in result['conservative_deduplication'].items() if not k.endswith('clusters')})
    print('wrote', path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
