"""The one place a reason code becomes a sentence.

Every page and every export shows the same gaps, so they must not each keep their own copy: measured
at the first audit, the export table had drifted and was missing four codes that the pages explained
(section_absent_from_document, paper_not_in_index, device_index_absent,
no_registered_brand_shares_these_terms). A downloaded file that says only `paper_not_in_index` with
no sentence is worse than the page it came from.

The rule this table enforces: a code is never shown without a sentence, and the sentence says what
is missing and, where it helps, whose fault it is - ours (never collected), the publisher's (did not
publish the text), or the data's (the name is too generic to identify anything).
"""

from __future__ import annotations

GAP_TEXT: dict[str, str] = {
    # --- the device register and its filings
    "device_not_in_udi_register": "这个标识不在设备注册表里（K 号、DI、DUNS、型号、品牌、公司都试过了）",
    "no_clearance_linked_to_this_device": "注册表没有把任何批文关联到这台设备",
    "no_readable_summary_for_any_clearance": "批文存在，但存储的文本读不出内容",
    "document_not_published_by_fda": "FDA 没有公布这份文件的正文",
    "document_present_but_unreadable": "文件在，但正文不可读",
    "section_absent_from_document": "这份文件里没有这一章节——不是我们没提取，是原文就没有",
    # --- field experience
    "product_code_not_swept": "这台设备的产品码还没有扫过失效记录（是我们的进度，不是它没有失效）",
    "device_has_no_product_code": "这台设备在注册表里没有产品码，无法确定该扫哪个类别",
    "no_failure_in_swept_window": "已扫过的窗口里没有这台设备的失效记录",
    # --- patents
    "patent_bulk_tables_absent": "专利表还没有导入过数据",
    "patent_source_needs_credential": "专利源需要凭据（EPO 账号审核中）",
    "patent_assignee_not_fetched": "专利库里还没有这家受让人的记录——是还没抓过，不是它没有专利",
    "no_patent_for_this_assignee": "专利表里没有匹配到这个受让人",
    "patent_only_searched_not_recorded": "专利库里有按这个名字搜到、但申请人字段并非本公司的记录；"
                                         "这类不算本公司的专利，所以这里不展示",
    # --- trials
    "trials_table_absent": "试验表还没有导入过数据",
    "no_trial_for_this_sponsor": "试验库里没有匹配到这个申办方",
    # --- papers
    "paper_index_absent": "论文索引还没有构建",
    "no_paper_mentions_this_device": "已入库的论文里没有提到这个名称",
    "only_generic_words_in_this_name": "这个名称里只有通用词（如 spinal、system），无法定位到具体论文",
    "paper_not_in_index": "这篇论文不在索引里（只收录已归档全文，摘要和付费墙后的正文不在内）",
    "no_registered_brand_shares_these_terms": "没有任何已注册品牌名共用这篇论文的识别性词",
    # --- companies
    "company_not_in_register": "设备注册表里没有匹配到这家公司",
    "company_not_in_technology_map": "这家公司不在科技地图覆盖的范围内"
                                     "（图谱目前只覆盖 Philips / GE / Dräger）",
    "no_brand_for_this_company": "这家公司名下没有任何登记了品牌的设备",
    # --- the graph
    "technology_map_unavailable": "科技地图快照还没有生成，或图谱库为空",
    "no_topic_evidence": "图谱里还没有任何主题证据",
    # --- deployment
    "device_index_absent": "这台部署没有设备库",
    "product_classification_absent": "产品码分类表还没有导入（运行 tools/product_classes.py）",
    "no_classified_product_code": "这家公司的产品码都还没分类，无法归入技术领域",
    # --- should never appear
    "no_data": "这一项没有数据，而且没有记录原因（不该发生）",
}

__all__ = ["GAP_TEXT"]
