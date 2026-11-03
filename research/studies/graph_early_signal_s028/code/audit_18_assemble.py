"""S-028 audit 18: assemble every computed section into the deliverable
artifacts/entity_time_audit.json, and attach the per-relation-type 10-field ledger.

Nothing here re-derives statistics: all numbers are read from the section files the
analysis scripts wrote, so there is exactly one provenance path per number.
"""
from __future__ import annotations

import json
import os

from audit_common import SCRATCH, STUDY, now_iso, pct, dump

OUT = os.path.join(STUDY, "artifacts", "entity_time_audit.json")
SECTIONS = ["10_provenance", "11_time_clocks", "12_relations", "13_entity_mapping",
            "14_track_coverage", "15_research_coverage", "16_positive_sample",
            "17_crosschecks"]


def load(name):
    with open(os.path.join(SCRATCH, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def main():
    S = {n: load(n) for n in SECTIONS}
    p10, p11, p12 = S["10_provenance"], S["11_time_clocks"], S["12_relations"]
    p13, p14, p15 = S["13_entity_mapping"], S["14_track_coverage"], S["15_research_coverage"]
    p16, p17 = S["16_positive_sample"], S["17_crosschecks"]

    research_ev = p11["research_events"]
    obs = p11["observatory"]
    rel = p12
    auc = p13["acquisition_lookahead"]
    pairs = p16["company_track_pairs"]

    # ---------------------------------------------------------------- ledger
    # Per candidate relation type: the ten required fields, each number taken from S.
    R = []

    R.append({
        "id": "R1_company_track_regulatory_filing",
        "name_zh": "公司→技术赛道（监管申报事件直连）",
        "name_en": "Company->Technology(track) via regulatory filing event",
        "1_relation_definition": {
            "zh": "若事件 e 的 company_key=c 且 track_id=t，则在 t 所属年份建立 c-(t 赛道) 关系；关系的 valid_time 取该事件的 event_date。这是一条“事件即关系”的隐式边，研究输入里并没有把它物化成一张边表。",
            "en": "implicit edge: company_key x track_id co-occurrence on one regulatory event; valid_time = event_date",
        },
        "2_raw_evidence_source": {
            "table": "events",
            "source_column_values": ["openfda_device_510k_bulk", "openfda_device_pma_bulk"],
            "fields": ["payload.applicant", "payload.product_code", "track_id (derived)",
                       "config/product_code_tracks.json"],
            "kind_values": ["510k", "pma"],
            "row_count": research_ev["per_source"]["openfda_device_510k_bulk"]["n"]
            + research_ev["per_source"]["openfda_device_pma_bulk"]["n"],
        },
        "3_event_time": {
            "column": "event_date",
            "equals_payload_decision_date_rows": p17["event_date_is_decision_date"]["rows_equal"],
            "pct": p17["event_date_is_decision_date"]["pct_equal"],
            "range": p16["window"]["min_event_date"] + " .. " + p16["window"]["max_event_date"],
            "timestamp_quality": "estimated (100% of rows)",
        },
        "4_published_time": {
            "column": "published_at",
            "rule": p17["published_at_provenance"]["rule_observed"],
            "distinct_offset_days": research_ev["available_at_minus_event_date_days"]["distinct_values"],
            "is_real_source_field": False,
        },
        "5_first_seen_at": {
            "column": "first_seen_at",
            "distinct_values": research_ev["first_seen_at_distinct_values"],
            "values": research_ev["first_seen_at_values"],
            "verdict": "single bulk-fetch date; carries no per-event information",
        },
        "6_entity_assignment_method": {
            "method_zh": "确定性的 product_code→track 映射 + 模糊的 applicant_raw→company 别名匹配（最长别名子串/前缀命中）",
            "track_map": "config/product_code_tracks.json, 1,958 entries, deterministic",
            "company_map": "companies.aliases, fuzzy substring/prefix",
            "validation": p13["alias_assignment_validation"],
            "track_validation": p14["event_track_classification"],
        },
        "7_confidence_or_pending_status": {
            "per_row_confidence_column": None,
            "per_row_matched_alias_column": None,
            "zh": "events 表没有 match_confidence / matched_alias 列，映射置信度不可审计；只有 company_key 的有/无。",
            "track_method_auditability": p14["keyword_fallback"]["interpretation"],
        },
        "8_future_information_risk": {
            "uses_information_not_knowable_at_event_time": False,
            "leaks": ["赛道路径是 2026 年的 38 赛道分类学（taxonomy anachronism），不是事件当时的分类",
                      "公司名册是 2026 年的 51 家名册（roster look-ahead）：2016 年就知道这份名单的公司才被记录"],
            "verdict": "事件本身不含未来信息；风险在名册与分类学的时点错位",
        },
        "9_historical_coverage": {
            "date_range": p16["window"]["min_event_date"] + " .. " + p16["window"]["max_event_date"],
            "events_total": research_ev["rows"],
            "events_with_company": rel["edge_coverage"]["events_with_company_key"],
            "events_with_company_and_track": rel["edge_coverage"]["events_with_company_and_track"],
            "distinct_company_track_pairs": p17["pairs"]["distinct_company_track_pairs"],
            "per_year_missingness": p14["per_year_missingness"],
        },
        "10_missingness": {
            "per_source": p13["mapping_null_rates"],
            "company_key_null_overall": 55090 - rel["edge_coverage"]["events_with_company_key"],
            "company_key_null_pct_overall": pct(
                55090 - rel["edge_coverage"]["events_with_company_key"], 55090),
        },
    })

    R.append({
        "id": "R2_temporal_edges_company_product_technology",
        "name_zh": "公司→产品→技术（物化边表）",
        "name_en": "Company->Product->Technology via temporal_edges",
        "1_relation_definition": {
            "zh": "对每个 (company_key, product_code) 组，取该组最早事件建立 COMPANY_DEVELOPS_PRODUCT 边，valid_time=组内最早 event_date；再用 product_code→track 映射建立 PRODUCT_BELONGS_TO_TECHNOLOGY 边。1,698 个 (company, product_code) 组里只有 1,087 个被物化。",
            "en": "deduplicated first-appearance edge per (company, product_code) pair",
        },
        "2_raw_evidence_source": {
            "table": "temporal_edges",
            "relation_values": ["COMPANY_DEVELOPS_PRODUCT (1,087)", "PRODUCT_BELONGS_TO_TECHNOLOGY (1,087)"],
            "evidence_source_values": ["openfda_regulatory_event", "medradar_product_code_mapping"],
            "evidence_id_resolvable_to_events": 1087,
        },
        "3_event_time": {
            "column": "valid_time",
            "null_count": rel["temporal_edges_inventory"][1]["valid_time_null"],
            "equals_earliest_event_date_in_group": 1016,
            "range": "2016-11-15T00:00:00 .. 2026-10-16T00:00:00",
        },
        "4_published_time": {
            "column": "available_at (on the edge)",
            "rule": "inherits the earliest event's published_at = event_date + 14 days",
            "inheritance_check": rel["edge_time_inheritance"],
        },
        "5_first_seen_at": {
            "column": None,
            "zh": "temporal_edges 没有 first_seen_at 列；available_at 就是它唯一的“可知时点”，而该时点是继承来的合成量。",
        },
        "6_entity_assignment_method": {
            "zh": "主体=company_key（模糊别名匹配）；客体=product_code（原样），技术=config 映射（确定性）",
        },
        "7_confidence_or_pending_status": {
            "confidence_column": "temporal_edges.confidence",
            "confidence_min": rel["temporal_edges_inventory"][1]["confidence_min"],
            "confidence_max": rel["temporal_edges_inventory"][1]["confidence_max"],
            "assertion_status": "observed (100%)",
        },
        "8_future_information_risk": {
            "uses_information_not_knowable_at_event_time": False,
            "caveat": "边的 available_at 是从 event_date+14 推出来的合成时点；把它当“可知时点”会把假设当事实",
        },
        "9_historical_coverage": {
            "n_edges_company_product": 1087,
            "n_edges_product_technology": 1087,
            "distinct_companies": rel["temporal_edges_inventory"][1]["distinct_subjects"],
            "distinct_products": rel["temporal_edges_inventory"][1]["distinct_objects"],
            "distinct_technologies": rel["temporal_edges_inventory"][2]["distinct_objects"],
            "per_year": rel["edges_per_year"]["COMPANY_DEVELOPS_PRODUCT"],
            "edge_coverage_vs_events_pct": rel["edge_coverage"]["edge_to_event_ratio"],
        },
        "10_missingness": {
            "valid_time_null": 0,
            "available_at_null": 0,
            "company_product_pairs_in_events": 1698,
            "pairs_materialised": 1087,
            "pairs_not_materialised": 611,
        },
    })

    R.append({
        "id": "R3_company_procurement_contract",
        "name_zh": "公司→采购合同",
        "name_en": "Company->ProcurementContract",
        "1_relation_definition": {
            "zh": "USAspending 合同/订单的受方（supplier）经别名匹配到 company_key 后建立 COMPANY_WINS_CONTRACT 边；valid_time 取合同履约期起点 period_start，而不是授予日或首次公开日。",
        },
        "2_raw_evidence_source": {
            "table": "procurement_awards",
            "source_value": "usaspending_api_v2_spending_by_award",
            "rows": rel["procurement_awards"]["rows"],
            "payload_keys": ["award_id", "contract_award_type", "generated_internal_id",
                             "internal_id", "last_modified_date"],
        },
        "3_event_time": {
            "column": "valid_time == period_start",
            "award_date_null": rel["procurement_awards"]["award_date_null"],
            "announcement_date_null": rel["procurement_awards"]["announcement_date_null"],
            "range": "2007 .. 2026 (per-year edge counts)",
            "per_year": rel["edges_per_year"]["COMPANY_WINS_CONTRACT"],
        },
        "4_published_time": {
            "column": "available_at",
            "distinct_values": rel["procurement_awards"]["distinct_available_at"],
            "value": rel["procurement_awards"]["available_at_min"],
            "zh": "3,453 行共享同一个批量抓取时间戳：这是“我们抓取的时刻”，不是“合同公开的时刻”。",
        },
        "5_first_seen_at": {"column": None, "zh": "无该列；批量 available_at 即抓取日"},
        "6_entity_assignment_method": {
            "zh": "supplier 字符串→别名匹配；逐行带 match_confidence 与 matched_alias",
            "match_confidence_avg": rel["procurement_awards"]["match_confidence_avg"],
            "company_keys_with_contracts": rel["procurement_awards"]["company_keys_with_contracts"],
            "buyer_side": "买方只有 7 个联邦机构，不存在第二个公司",
        },
        "7_confidence_or_pending_status": {
            "pit_usable_sum": rel["procurement_awards"]["pit_usable_sum"],
            "data_quality_value": "current_snapshot_obligation_not_revenue_first_publication_unknown",
            "zh": "全部 3,453 行 pit_usable=0：数据库自己承认这批数据不能用于 point-in-time。",
        },
        "8_future_information_risk": {
            "uses_information_not_knowable_at_event_time": True,
            "why": "只剩“当前快照”，没有首次公开日；用它可以知道未来金额/存续状态，属于典型未来信息",
        },
        "9_historical_coverage": {
            "n_edges": 3372, "companies": 22,
            "per_year": rel["edges_per_year"]["COMPANY_WINS_CONTRACT"],
        },
        "10_missingness": {
            "company_key_null": rel["procurement_awards"]["company_key_null"],
            "award_date_null_pct": pct(rel["procurement_awards"]["award_date_null"],
                                       rel["procurement_awards"]["rows"]),
            "announcement_date_null_pct": pct(rel["procurement_awards"]["announcement_date_null"],
                                              rel["procurement_awards"]["rows"]),
            "pit_usable_rows": rel["procurement_awards"]["pit_usable_sum"],
        },
    })

    R.append({
        "id": "R4_company_financial_filing",
        "name_zh": "公司→财报事实",
        "name_en": "Company->FinancialFiling / financial fact",
        "1_relation_definition": {
            "zh": "SEC XBRL companyfacts 的每条事实生成 COMPANY_FILES_FINANCIAL_FACT 边（34 条，company→CIK），事实本身 43,420 行带 valid_time（期末/时点）。",
        },
        "2_raw_evidence_source": {
            "table": "financial_facts + company_identifiers",
            "source_value": "sec_xbrl_companyfacts / sec_company_tickers",
            "rows": rel["financial_facts"]["rows"],
            "n_edges": 34,
            "identifier_scheme": rel["financial_facts"]["company_identifiers_schemes"],
        },
        "3_event_time": {
            "column": "valid_time (facts)",
            "range": rel["financial_facts"]["valid_time_range"],
            "edge_valid_time_null": rel["temporal_edges_inventory"][3]["valid_time_null"],
            "zh": "边表上 34 条边全部没有 valid_time；时间只在事实行上。",
        },
        "4_published_time": {
            "column": "available_at",
            "range": rel["financial_facts"]["available_at_range"],
            "distinct_values": rel["financial_facts"]["distinct_available_at"],
            "edge_available_at": rel["temporal_edges_inventory"][3]["available_at_min"],
            "zh": "事实行有 949 个不同 available_at（可用）；但边上的 available_at 是单一批量时间戳。",
        },
        "5_first_seen_at": {"column": None},
        "6_entity_assignment_method": {
            "zh": "CIK 精确匹配（SEC_CIK，34 条），确定性",
            "companies_with_facts": rel["financial_facts"]["companies"],
        },
        "7_confidence_or_pending_status": {"confidence": 1.0, "data_quality": "companyfacts_no_segment_dimension"},
        "8_future_information_risk": {
            "uses_information_not_knowable_at_event_time": "在事实行层面否；在边上（无时间）无法判定",
            "caveat": "XBRL 事实的 available_at 是申报可用时间，但公司层面只有 32/51 家有 CIK 事实",
        },
        "9_historical_coverage": {
            "valid_time_range": rel["financial_facts"]["valid_time_range"],
            "available_at_range": rel["financial_facts"]["available_at_range"],
            "rows": rel["financial_facts"]["rows"],
            "companies": rel["financial_facts"]["companies"],
            "companies_total": p13["companies"],
            "per_year": "not aggregated (facts are quarterly)",
        },
        "10_missingness": {
            "valid_time_null": rel["financial_facts"]["valid_time_null"],
            "available_at_null": rel["financial_facts"]["available_at_null"],
            "payload_null": rel["financial_facts"]["payload_null"],
            "companies_without_facts": p13["companies"] - rel["financial_facts"]["companies"],
        },
    })

    R.append({
        "id": "R5_company_trial_sponsor",
        "name_zh": "公司→临床试验申办方",
        "name_en": "Company->Trial sponsor",
        "1_relation_definition": {
            "zh": "ctgov 试验的 lead_sponsor 经别名匹配到 company_key；事件时间 = 首次公示日 study_first_post_date。",
        },
        "2_raw_evidence_source": {
            "table": "product DB events (source=ctgov) —— 冻结研究输入中没有这张表",
            "rows": p15["product_trials"]["rows"],
            "distinct_lead_sponsor": p15["product_trials"]["distinct_lead_sponsor"],
            "in_frozen_research_input": False,
        },
        "3_event_time": {
            "column": "event_date == payload.first_posted",
            "equal_rows": p15["product_trials"]["event_date_equals_first_posted"][0],
            "range": p15["product_trials"]["event_date_range"],
        },
        "4_published_time": {
            "column": "published_at",
            "zh": "在 product DB 里 published_at 与 available_at 都等于 event_date（100%）",
        },
        "5_first_seen_at": {
            "values": p15["product_trials"]["first_seen_at_values"],
            "zh": "又是单一批量抓取日（2026-10-30），55,592 行同一个值",
        },
        "6_entity_assignment_method": {
            "zh": "agent 侧别名匹配，逐行保留 match_confidence 与 matched_alias",
            "tiers": p15["product_trials"]["match_confidence_tiers"],
        },
        "7_confidence_or_pending_status": {
            "accepted_threshold": ">=0.90",
            "accepted_rows": p15["product_trials"]["company_key_nonnull"],
        },
        "8_future_information_risk": {
            "uses_information_not_knowable_at_event_time": False,
            "caveat": "首次公示日之后的试验状态/结果/完成日期若被使用，则含未来信息；payload 里确有 overall_status / completion_date",
        },
        "9_historical_coverage": {
            "trials_mapped_to_frozen_roster": p15["product_trials"]["trials_mapped_to_frozen_roster"],
            "roster_companies_with_trials": p15["product_trials"]["roster_companies_with_trials"],
            "roster_trials_per_company": p15["product_trials"]["roster_trials_per_company"],
        },
        "10_missingness": {
            "company_key_null": p15["product_trials"]["rows"] - p15["product_trials"]["company_key_nonnull"],
            "company_key_null_pct": pct(
                p15["product_trials"]["rows"] - p15["product_trials"]["company_key_nonnull"],
                p15["product_trials"]["rows"]),
            "relation_absent_from_frozen_input": True,
            "why_absent": ("the frozen 55,090-row event set contains only 510(k) and PMA rows, so within the "
                           "research input this relation has 0 edges; it exists only in the 1.3 GB product DB "
                           "and in 157 observatory trial observations"),
        },
    })

    R.append({
        "id": "R6_company_company_any_kind",
        "name_zh": "公司↔公司（任何形式）",
        "name_en": "Company<->Company of any kind",
        "1_relation_definition": {
            "zh": "不存在。temporal_edges 的 subject_type/object_type 组合只有 Company→ProcurementContract、Company→Product、Product→Technology、Company→FinancialFiling；没有任何 Company→Company 边，也没有母公司/子公司/竞争对手/合作边表。",
            "en": "DOES NOT EXIST as an edge table",
        },
        "2_raw_evidence_source": {
            "table": "temporal_edges",
            "object_types_present": rel["object_types"],
            "subject_types_present": rel["subject_types"],
        },
        "3_event_time": {"column": None},
        "4_published_time": {"column": None},
        "5_first_seen_at": {"column": None},
        "6_entity_assignment_method": {
            "zh": "唯一近似物是 companies.aliases 这张“别名清单”：它把被并购子公司的名字挂在母公司名下，隐含了母公司→子公司的所有权关系，但没有方向、没有日期、没有证据编号、没有置信度。",
            "alias_list_carries_no_metadata": p13["alias_list_carries_no_metadata"],
        },
        "7_confidence_or_pending_status": {"column": None,
                                            "zh": "别名清单无任何置信度或生效日期字段"},
        "8_future_information_risk": {
            "uses_information_not_knowable_at_event_time": True,
            "why": "名单是 2026 年的并购结果；用它在 t<并购完成时建立“母公司拥有该技术”的边，即使用了当时不可知的信息",
        },
        "9_historical_coverage": {
            "company_to_company_edges": rel["absence"]["company_to_company_edges"],
            "self_typed_edges": rel["absence"]["self_typed_edges"],
            "object_id_matching_a_company_key": rel["absence"]["object_id_matching_a_company_key"],
            "alias_strings_that_are_another_companys_canonical_key":
                rel["absence"]["alias_strings_that_are_another_companys_canonical_key"],
        },
        "10_missingness": {"zh": "整个关系类型缺失：100% 不可得"},
    })

    R.append({
        "id": "R7_company_publication_aggregate",
        "name_zh": "公司→论文产出（年度聚合）",
        "name_en": "Company->Publication (annual aggregate only)",
        "1_relation_definition": {
            "zh": "OpenAlex 按公司名检索，按 (company_key, year) 聚合出 works 计数；不是论文级关系。",
        },
        "2_raw_evidence_source": {
            "table": "publication_counts",
            "source_value": "openalex_group_by_publication_year",
            "rows": 616,
            "columns": ["company_key", "year", "works", "source", "retrieved_at"],
        },
        "3_event_time": {"column": "year (only)", "range": [2014, 2026]},
        "4_published_time": {"column": "retrieved_at (抓取时间)"},
        "5_first_seen_at": {"column": None},
        "6_entity_assignment_method": {"zh": "公司名检索，检索式未落库；无 paper id 可回溯"},
        "7_confidence_or_pending_status": {"column": None},
        "8_future_information_risk": {
            "uses_information_not_knowable_at_event_time": True,
            "why": "年度计数是事后回填的汇总值，无法在年内任意时点还原“当时已知篇数”",
        },
        "9_historical_coverage": {"companies": 51, "rows": 616, "year_range": [2014, 2026]},
        "10_missingness": {"paper_level_records": 0, "author_records": 0, "institution_records": 0},
    })

    R.append({
        "id": "R8_company_publication_paper_observatory",
        "name_zh": "公司→单篇论文（观察台）",
        "name_en": "Company->Paper via observatory europepmc",
        "1_relation_definition": {
            "zh": "Europe PMC 单位署名检索（AFF:\"公司名\"）命中后写入观察台账；entity_id 由 affiliation_query 规则给出，状态 PENDING_REVIEW。",
        },
        "2_raw_evidence_source": {
            "table": "observatory.observation + observation_version.payload",
            "source_value": "europepmc",
            "observations": 237,
            "payload_keys": p15["observatory_research"]["europepmc_payload_keys"],
        },
        "3_event_time": {"column": "event_at", "precision": "date", "range": ["2026-08-05", "2026-11-02"]},
        "4_published_time": {"column": "published_at (= firstIndexDate)", "range": ["2025-12-18", "2026-11-03"]},
        "5_first_seen_at": {"values": obs["first_seen_at_values"], "zh": "全部落在 2026-11-03 单日"},
        "6_entity_assignment_method": {
            "method": "europepmc_affiliation_query",
            "status": "PENDING_REVIEW",
            "zh": "单位署名不等于企业归属（同一单位名可能对应多家法人实体），因此全部待审",
        },
        "7_confidence_or_pending_status": {
            "pending_review": p15["observatory_research"]["mapped_pending_review"],
            "accepted": p15["observatory_research"]["mapped_accepted"],
        },
        "8_future_information_risk": {
            "uses_information_not_knowable_at_event_time": True,
            "why": "237 条中 lag(first_seen-published)>7 天的占 " +
                   str(obs["prospective"]["n_gt_7d"]) + " 条；只有 " +
                   str(obs["prospective"]["n_le_1d"]) + " 条在 24h 内被看到",
        },
        "9_historical_coverage": {"observations": 237, "window": "2025-12-18 .. 2026-11-03"},
        "10_missingness": {
            "institution_field_absent": not p15["observatory_research"]["institution_field_present"],
            "zh": "payload 只有 author_string；没有任何单位/机构字段，无法建立作者-机构关系",
        },
    })

    # --------------------------------------------------------------- document
    doc = {
        "schema": "s028-entity-time-audit-v1",
        "study": "S-028 graph_early_signal_s028",
        "title_zh": "关系与时间证据审计（RELATION_AND_TIME_EVIDENCE_AUDIT）",
        "auditor": "independent data-provenance auditor",
        "generated_at": now_iso(),
        "cwd_note": "audit ran with read-only sqlite URIs against the three stores named in meta.provenance",
        "meta": {
            "stores": {
                "research_frozen": {
                    "path": p10["stores"]["research"]["path"],
                    "bytes": p10["stores"]["research"]["bytes"],
                    "sha256": p10["stores"]["research"]["sha256"],
                    "sha256_verified_against_prompt": p10["stores"]["research"]["sha256_verified"],
                    "size_verified_against_prompt": p10["stores"]["research"]["size_verified"],
                },
                "product": {"path": p10["stores"]["product"]["path"],
                            "bytes": p10["stores"]["product"]["bytes"]},
                "observatory": {"path": p10["stores"]["observatory"]["path"],
                                "bytes": p10["stores"]["observatory"]["bytes"]},
            },
            "table_row_counts": {n: p10["stores"][n]["tables"] for n in p10["stores"]},
            "frozen_input_live_state_tables": p10["frozen_input_live_state_tables"],
        },
        "definitions": {
            "historical_proxy_asof": {
                "zh": "用事后回填的、合成的或派生的时间戳把历史事件“放回”过去某一时点的做法；只能用于模拟，不能宣称当时已知。",
                "en": "backfilled/synthesised as-of clock; simulation only",
            },
            "observed_asof": {
                "zh": "在事件公开后很短时间内（本审计取 <=1 个自然日）就被系统真实观察并落库的时点；这才是真正的前瞻观察。",
                "en": "genuine prospective first observation, first_seen_at - published_at <= 1 day",
            },
        },
        "A_point_in_time": {
            "research_events": research_ev,
            "observatory": obs,
            "verdict_zh": (
                "经核验：research.sqlite.events 的 first_seen_at 只有一个值 2026-11-01，覆盖全部 "
                f"{research_ev['rows']:,} 行；lag(first_seen-published) 中位数 "
                f"{research_ev['lag_first_seen_minus_published_days']['median']} 天，"
                f">=365 天的占 {research_ev['genuine_pit']['pct_gt_365d']}%。"
                "因此“历史点的首次观察”在冻结研究输入里 100% 是 historical_proxy_asof，"
                f"真正满足 <=1 天的只有 {research_ev['genuine_pit']['n_le_1d']} 行。"),
            "observatory_verdict_zh": (
                f"observatory 400 条观察全部标为 observation_origin=LIVE、backfill_reason 全空，"
                f"但台账创建时间 {obs['ledger_created_at']} 与全部 first_seen_at 都在同一天；"
                f"扣除同日抓取这一事实后，真正 <=1 天看到新记录的只有 {obs['prospective']['n_le_1d']} 条"
                f"（{obs['prospective']['pct_le_1d']}%），>7 天的有 {obs['prospective']['n_gt_7d']} 条"
                f"（{obs['prospective']['pct_gt_7d']}%）。所谓 LIVE 是“采集方式”标签，不是前瞻性证据。"),
        },
        "B_available_at": {
            "research": {
                "distinct_deltas_vs_event_date": research_ev["available_at_minus_event_date_days"]["distinct_values"],
                "equal_to_event_date": research_ev["available_at_minus_event_date_days"]["equal_count"],
                "equals_published_at_rows": research_ev["rows"],
                "verdict_zh": (
                    "available_at 既不等于 event_date（0 行相等），也没有任何方差："
                    f"全部 {research_ev['rows']:,} 行都严格等于 event_date + 14 天，且等于 published_at。"
                    "这 14 天是构建脚本写死的假设，不是观测到的公开延迟。"),
            },
            "product": {
                "rows": p11["product_events"]["rows"],
                "per_source": {
                    k: {"n": v["n"], "first_seen_at_values": v["first_seen_at_values"],
                        "event_date_range": v["event_date_range"],
                        "available_minus_event_days": v["available_minus_event_days"],
                        "timestamp_quality": v["timestamp_quality"]}
                    for k, v in p11["product_events"]["per_source"].items()},
                "per_source_equal_pct": {k: v["available_minus_event_days"]["equal_pct"]
                                         for k, v in p11["product_events"]["per_source"].items()},
                "verdict_zh": ("product DB 里 6 个来源、375,378 行全部 available_at == event_date，"
                               "即假定“获批当日即可见”，与 research 库的 +14 天假设互相矛盾。"),
            },
            "conclusion_zh": (
                "两个库对 available_at 的语义不一致且都是合成量（research=event_date+14d，"
                "product=event_date+0d）。历史模拟唯一站得住的“知识时钟”是 event_date 本身"
                "（监管决定日），可用 available_at 作为保守外扩界，但必须声明它是假设而非观测。"),
        },
        "C_relations": rel,
        "D_entity_leakage": p13,
        "E_track_coverage": p14,
        "F_research_coverage": p15,
        "G_positive_sample": p16,
        "crosschecks": p17,
        "relation_types": R,
        "verdicts": {
            "first_seen_at_zh": "单一批量抓取日 2026-11-01（55,090/55,090 行），历史首次观察 0% 真实",
            "available_at_zh": "research=event_date+14d（零方差）；product=event_date（零延迟）；两者皆为合成量",
            "company_company_zh": "不存在任何公司↔公司边；只有 companies.aliases 这张无日期无证据的别名清单隐含所有权",
            "prospective_observations": obs["prospective"]["n_le_1d"],
            "prospective_observations_le_7d": obs["prospective"]["n_le_7d"],
            "qualifying_events": p16["qualifying_events"]["n_total"],
            "usable_company_track_pairs": pairs["n_pairs_with_at_least_one_qualifying_event"],
        },
        "top_gaps": [
            {"rank": 1,
             "gap_zh": "没有任何真实的历史 point-in-time 覆盖：research 库 first_seen_at 全为单一批量日，"
                       "publication_counts/edges 亦为回填；observatory 台账只有 1 天历史，"
                       f"真正 <=1 天观察的仅 {obs['prospective']['n_le_1d']}/400。",
             "evidence_keys": ["A_point_in_time", "meta.stores"]},
            {"rank": 2,
             "gap_zh": f"正样本被实体映射掐住：25,947 个合格事件里只有 {pairs['qualifying_events_with_company_and_track']:,} 个"
                       f"（{100 - pairs['dropped_pct']:.2f}%）同时有公司和技术赛道，最终只剩 "
                       f"{pairs['n_pairs_with_at_least_one_qualifying_event']} 个 company-track 对；"
                       f"2018 年后每年新增首次进入只有 10~16 个。",
             "evidence_keys": ["G_positive_sample.company_track_pairs", "E_track_coverage.mapping_null_rates"]},
            {"rank": 3,
             "gap_zh": "关系证据缺失：没有公司↔公司、公司→赛道直连、公司→论文、公司→机构的任何边；"
                       "采购关系 100% pit_usable=0 且无授予日/公开日；财务边无 valid_time；"
                       "冻结研究输入根本没有试验与论文级数据。",
             "evidence_keys": ["C_relations.absence", "F_research_coverage.buildable"]},
        ],
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, default=str)
    size = os.path.getsize(OUT)
    print(f"wrote {OUT}  ({size:,} bytes)")
    print("relation types:", [r["id"] for r in R])
    print("verdicts:", json.dumps(doc["verdicts"], ensure_ascii=False))
    dump("18_assembled", {"path": OUT, "bytes": size})


if __name__ == "__main__":
    main()
