from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
import unicodedata
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(os.environ.get('S031_OUTPUT_DIR', '/mnt/agents/output'))
WORK = Path(os.environ.get('S031_WORK_DIR', str(ROOT / 'research/s031/work')))
BASE = ROOT / 'experiments/innovation_signals_observatory/results/2026-11-04'


def load_jsonl(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]


def ws(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text or '')).strip()


class S031Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (OUT / 'S031_SAMPLE_100.csv').open(encoding='utf-8-sig') as f:
            cls.sample = list(csv.DictReader(f))
        cls.labels = load_jsonl(OUT / 'S031_AI_PRELABELS.jsonl')
        cls.comparison = load_jsonl(WORK / 'legacy_rule_comparison.jsonl')
        cls.audit = json.loads((WORK / 'pr21_count_audit.json').read_text())

    def test_01_fixed_seed_rank(self):
        path = ROOT / 'research/s031/scripts/select_sample.py'
        spec = importlib.util.spec_from_file_location('s031_sampler', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.SEED, 31031)
        self.assertEqual(
            module.rank('medtronic', 'example-posting'),
            'fa09292a8602c07ecf03f439530666b08a779d1137fa78d03bdb66b5d79156e4',
        )
        self.assertNotIn('classify_rules', path.read_text())

    def test_02_sample_identities_and_source_hashes(self):
        self.assertEqual(len(self.sample), 100)
        self.assertEqual(len({(x['company'], x['job_id']) for x in self.sample}), 100)
        self.assertEqual(
            Counter(x['company'] for x in self.sample),
            Counter({'medtronic': 20, 'ge_healthcare': 20, 'philips': 20, 'draeger': 20, 'mindray': 20}),
        )
        required = {
            'company', 'job_id', 'job_title', 'source_url', 'raw_record_sha256',
            'content_sha256', 'raw_file_sha256', 'source_jsonl_line',
            'selection_stratum', 'sample_selection_reason', 'known_data_gaps',
            'collection_status', 'source_posted_at',
        }
        by_file = {}
        for row in self.sample:
            self.assertTrue(required <= set(row))
            by_file.setdefault(row['company'], {})[int(row['source_jsonl_line'])] = row
        for company, wanted in by_file.items():
            path = BASE / f'jobs_{company}.jsonl'
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), next(iter(wanted.values()))['raw_file_sha256'])
            seen = set()
            with path.open('rb') as f:
                for line_no, raw in enumerate(f, 1):
                    if line_no not in wanted:
                        continue
                    row = wanted[line_no]
                    source = json.loads(raw)
                    self.assertEqual(source['posting_id'], row['job_id'])
                    self.assertEqual(source.get('content_sha256') or '', row['content_sha256'])
                    self.assertEqual(hashlib.sha256(raw.rstrip(b'\r\n')).hexdigest(), row['raw_record_sha256'])
                    seen.add(line_no)
            self.assertEqual(seen, set(wanted))

    def test_03_prelabels_schema_and_closed_vocabularies(self):
        self.assertEqual(len(self.labels), 100)
        self.assertEqual(len({(x['company'], x['job_id']) for x in self.labels}), 100)
        strengths = {
            'DIRECT_R&D_EVIDENCE', 'INDIRECT_TECHNICAL_EVIDENCE',
            'PRODUCT_CONTEXT_ONLY', 'NON_R&D', 'INSUFFICIENT_EVIDENCE',
            'CONFLICTING_EVIDENCE',
        }
        for x in self.labels:
            self.assertEqual(x['label_status'], 'AI_PRELIMINARY_LABEL')
            self.assertEqual(x['preliminary_label_source'], 'AI_PRELIMINARY_LABEL')
            self.assertIn(x['rd_evidence_strength'], strengths)
            self.assertIn('primary', x['role_function'])
            self.assertIn('secondary', x['role_function'])
            self.assertIsInstance(x['technical_capabilities'], list)
            self.assertIsInstance(x['product_business_context'], list)
            self.assertIsInstance(x['needs_human_review'], bool)
            for field in ('support_explanation', 'alternative_explanation', 'missing_information', 'human_review_reason'):
                self.assertTrue(x[field].strip())
            self.assertNotIn(x['label_status'], {'HUMAN_GOLD', 'EXPERT_CONFIRMED', 'SCIENTIFICALLY_VALIDATED'})

    def test_04_every_quote_is_verbatim_in_frozen_source(self):
        wanted = {(x['company'], x['job_id']): x for x in self.labels}
        found = set()
        for company in {x['company'] for x in self.labels}:
            with (BASE / f'jobs_{company}.jsonl').open(encoding='utf-8') as f:
                for line in f:
                    r = json.loads(line)
                    key = (company, r['posting_id'])
                    if key not in wanted:
                        continue
                    found.add(key)
                    text = ws((r.get('job_title') or '') + '\n' + (r.get('job_description') or ''))
                    for quote in wanted[key]['exact_evidence_quotes']:
                        self.assertIn(ws(quote['quote']), text, key)
                        self.assertEqual(
                            quote['match_policy'],
                            'exact_text_after_unicode_whitespace_normalization',
                        )
        self.assertEqual(found, set(wanted))
        unavailable = [x for x in self.labels if x['rd_evidence_strength'] == 'INSUFFICIENT_EVIDENCE']
        self.assertEqual(len(unavailable), 3)
        for x in unavailable:
            self.assertEqual(x['exact_evidence_quotes'], [])
            self.assertEqual(x['role_function']['primary'], 'UNCLASSIFIED')

    def test_05_comparison_is_descriptive_not_truth(self):
        self.assertEqual(len(self.comparison), 100)
        self.assertEqual(
            {x['legacy']['rules_version'] for x in self.comparison},
            {'recruitment_taxonomy_rules_2026-11-04b'},
        )
        for x in self.comparison:
            self.assertEqual(x['comparison_status'], 'DESCRIPTIVE_DISAGREEMENT_ONLY')
            self.assertTrue(x['not_an_error_label'])
            self.assertEqual(x['ai_preliminary']['label_status'], 'AI_PRELIMINARY_LABEL')
        summary = json.loads((WORK / 'legacy_rule_comparison_summary.json').read_text())
        self.assertEqual(summary['n'], 100)
        self.assertEqual(summary['legacy_track_status_counts']['MAPPED'], 3)
        self.assertEqual(summary['audit_candidate_counts']['FUNCTION_GATE_DIRECT_RD_REVIEW'], 12)

    def test_06_pr21_count_audit(self):
        identity = self.audit['identity']
        self.assertEqual(identity['raw_rows'], 994)
        self.assertEqual(identity['distinct_posting_ids'], 994)
        self.assertEqual(identity['same_posting_id_duplicate_rows'], 0)
        self.assertEqual(identity['title_robot_substring_rows'], 20)
        dedup = self.audit['conservative_deduplication']
        self.assertEqual(dedup['same_content_cluster_count'], 5)
        self.assertEqual(dedup['multi_city_cluster_count'], 3)
        self.assertEqual(dedup['total_rows_collapsed'], 11)
        self.assertEqual(dedup['conservative_cluster_count'], 983)
        self.assertTrue(all(x.get('ambiguity') for x in dedup['exact_clusters'] + dedup['multi_city_clusters']))
        desc = self.audit['description_only_definitions']
        self.assertEqual(desc['description_only_any_title_keyword_definition'], 47)
        self.assertEqual(desc['description_only_non_generic_title_keyword_definition'], 54)
        self.assertEqual(self.audit['robotics_and_probe_audit']['surgical_robotics']['plain_language_mentions'], 80)
        self.assertEqual(self.audit['robotics_and_probe_audit']['surgical_robotics']['assigned_to_same_track'], 0)
        self.assertEqual(self.audit['content_hash_audit']['hash_rule_version_field_absent'], 994)
        self.assertEqual(self.audit['classification']['function_gate_audit']['would_pass_same_track_threshold_without_function_gate'], 168)

    def test_07_case_studies_complete(self):
        text = (OUT / 'S031_CASE_STUDIES.zh-CN.md').read_text()
        sections = re.split(r'(?m)^## \d+\. ', text)[1:]
        self.assertEqual(len(sections), 24)
        for section in sections:
            for marker in ('**真实原文**', '**旧规则判断**', '**独立 AI 预判断**', '**分歧机制**', '**还缺什么证据**', '**人工复核决定**'):
                self.assertIn(marker, section)
            self.assertIn('原始 JSONL 第', section)

    def test_08_hypotheses_and_deliverables(self):
        report = (OUT / 'S031_RESEARCH_REPORT.zh-CN.md').read_text()
        for h in ('H1', 'H2', 'H3'):
            self.assertIn(f'## {"7" if h == "H1" else "8" if h == "H2" else "9"}. {h}', report)
        for marker in ('支持案例', '反例与限定', '当前证据不足', '未来证伪方法'):
            self.assertGreaterEqual(report.count(marker), 3)
        names = {
            'S031_RESEARCH_PROTOCOL.md', 'JOB_CAPABILITY_ONTOLOGY.md',
            'S031_SAMPLE_100.csv', 'S031_AI_PRELABELS.jsonl',
            'S031_DISAGREEMENT_AUDIT.md', 'S031_CASE_STUDIES.zh-CN.md',
            'S031_RESEARCH_REPORT.zh-CN.md', 'NEXT_STEPS.md',
        }
        for name in names:
            path = OUT / name
            if name == 'S031_RESEARCH_PROTOCOL.md' and not path.exists() and (OUT / 'RESEARCH_PROTOCOL.md').exists():
                path = OUT / 'RESEARCH_PROTOCOL.md'
            self.assertTrue(path.is_file(), name)
            self.assertGreater(path.stat().st_size, 100, name)


if __name__ == '__main__':
    unittest.main()
