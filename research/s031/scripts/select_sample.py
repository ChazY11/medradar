#!/usr/bin/env python3
"""S-031 deterministic, surface-cue stratified sampler; no old labels are read."""
from __future__ import annotations
import csv, hashlib, json, os, re, unicodedata
from collections import Counter
from pathlib import Path

SEED = 31031
COMPANIES = ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")
QUOTAS = {
    "unavailable_text": 1,
    "difficult_product_context": 2,
    "explicit_rd_title": 2,
    "software_algorithm_title": 2,
    "product_engineering_title": 2,
    "manufacturing_title": 2,
    "quality_regulatory_title": 2,
    "clinical_application_title": 2,
    "field_service_title": 1,
    "sales_marketing_title": 2,
    "business_operations_title": 1,
    "ambiguous_function_title": 1,
}
P = {
    "commercial": r"sales|marketing|commercial|account manager|business development|customer|vertrieb|销售|市场|商务|客户经理|渠道",
    "clinical": r"clinical|therapy|application|medical science|medical affairs|education|training|klinisch|临床|医学|应用专员",
    "quality": r"quality|regulatory|complaint|\bCAPA\b|qualit.t|质量|法规|注册|体系",
    "service": r"field service|service engineer|technician|servicetechnik|medizintechniker|维修|服务工程|技术服务",
    "rd": r"\bR&D\b|research|development|entwicklung|forschung|研发|研究|开发",
    "software": r"software|algorithm|\bAI\b|machine learning|data engineer|digital|软件|算法|人工智能|数据",
    "product": r"engineer|engineering|scientist|physicist|mechanical|electrical|acoustic|system architect|systemingenieur|konstruktion|produktdesign|工程师|设计师|机械|电子|电气|硬件|结构",
    "manufacturing": r"manufacturing|production|assembler|operator|process|produktion|fertigung|einrichter|linienleiter|monteur|welder|mechanic|制造|生产|工艺|操作|装配",
    "business": r"finance|procurement|buyer|purchasing|people operations|human resources|legal|counsel|payroll|treasury|customs|einkauf|财务|采购|法务|人力资源",
    "sales": r"sales|marketing|commercial|account manager|business development|vertrieb|销售|市场|商务|客户经理|渠道",
}
DIFFICULT = re.compile(r"robot|artificial intelligence|machine learning|pulsed field|\bPFA\b|neurostim|neuromodulat|cardiac rhythm|digital twin|3D imaging|机器人|人工智能|图像|算法", re.I)
RX = {k: re.compile(v, re.I) for k, v in P.items()}
ANY_FUNCTION = re.compile("|".join(f"(?:{v})" for v in P.values()), re.I)
AMBIGUOUS_TITLE = re.compile(r"^(engineer( i+)?|project manager|program manager|associate|specialist|technical specialist|projektleiter|projektmanager)$", re.I)

def hit(key: str, title: str) -> bool:
    return bool(RX[key].search(title or ""))

def rank(company: str, posting_id: str) -> str:
    return hashlib.sha256(f"{SEED}\0{company}\0{posting_id}".encode()).hexdigest()

def candidates(stratum: str, r: dict) -> bool:
    title = r.get("job_title") or ""
    desc = r.get("job_description") or ""
    complete = r.get("collection_status") == "COMPLETE" and bool(desc.strip())
    if stratum == "unavailable_text": return not complete
    if not complete: return False
    if stratum == "difficult_product_context":
        return (hit("commercial", title) or hit("clinical", title) or hit("quality", title)) and bool(DIFFICULT.search(title + "\n" + desc))
    if stratum == "explicit_rd_title": return hit("rd", title)
    if stratum == "software_algorithm_title": return hit("software", title)
    if stratum == "product_engineering_title": return hit("product", title)
    if stratum == "manufacturing_title": return hit("manufacturing", title)
    if stratum == "quality_regulatory_title": return hit("quality", title)
    if stratum == "clinical_application_title": return hit("clinical", title)
    if stratum == "field_service_title": return hit("service", title)
    if stratum == "sales_marketing_title": return hit("sales", title)
    if stratum == "business_operations_title": return hit("business", title)
    if stratum == "ambiguous_function_title":
        return bool(AMBIGUOUS_TITLE.search(title.strip())) or not ANY_FUNCTION.search(title)
    raise KeyError(stratum)

def gaps(r: dict, company: str) -> str:
    out = []
    if r.get("collection_status") != "COMPLETE" or not (r.get("job_description") or "").strip():
        out.append("description_unavailable")
    if not r.get("source_posted_at"): out.append("source_date_unavailable")
    if not r.get("legal_entity"): out.append("employing_legal_entity_not_published")
    if company != "medtronic": out.append("company_corpus_is_bounded_80_not_full_population")
    return ";".join(out) if out else "none_observed_in_saved_record"

def main() -> None:
    root = Path(__file__).resolve().parents[3]
    src = root / "experiments/innovation_signals_observatory/results/2026-11-04"
    work = Path(os.environ.get("S031_WORK_DIR", str(root / "research/s031/work")))
    out = Path(os.environ.get("S031_OUTPUT_DIR", "/mnt/agents/output"))
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    selected, summary = [], {"seed": SEED, "quotas": QUOTAS, "companies": {}, "sampling_frame": "PR21 saved 2026-11-04 JSONL; stratified difficulty sample, NOT representative random sample"}
    for company in COMPANIES:
        path = src / f"jobs_{company}.jsonl"
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = []
        with path.open("rb") as handle:
            for line_no, raw in enumerate(handle, 1):
                r = json.loads(raw)
                r["_line_no"] = line_no
                r["_raw_record_sha256"] = hashlib.sha256(raw.rstrip(b"\r\n")).hexdigest()
                r["_raw_file_sha256"] = file_hash
                rows.append(r)
        chosen, used, unmet = [], set(), {}
        for stratum, quota in QUOTAS.items():
            pool = [r for r in rows if r["posting_id"] not in used and candidates(stratum, r)]
            pool.sort(key=lambda r: rank(company, r["posting_id"]))
            take = pool[:quota]
            if len(take) < quota: unmet[stratum] = quota - len(take)
            for r in take:
                used.add(r["posting_id"]); chosen.append((stratum, r, False))
        if len(chosen) < 20:
            pool = [r for r in rows if r["posting_id"] not in used]
            pool.sort(key=lambda r: rank(company, r["posting_id"]))
            for r in pool[:20-len(chosen)]:
                used.add(r["posting_id"]); chosen.append(("backfill_after_stratum_shortage", r, True))
        assert len(chosen) == 20, (company, len(chosen))
        summary["companies"][company] = {"frame_rows": len(rows), "selected": len(chosen), "unmet_quotas": unmet, "raw_file_sha256": file_hash}
        for stratum, r, backfill in chosen:
            selected.append({
                "company": company, "job_id": r["posting_id"], "job_title": r.get("job_title") or "",
                "source_url": r.get("source_url") or "", "raw_record_sha256": r["_raw_record_sha256"],
                "content_sha256": r.get("content_sha256") or "", "raw_file_sha256": file_hash,
                "source_jsonl_line": r["_line_no"], "selection_stratum": stratum,
                "sample_selection_reason": ("deterministic backfill after declared stratum shortage" if backfill else f"surface-cue stratum={stratum}; SHA256 rank seed={SEED}"),
                "known_data_gaps": gaps(r, company), "collection_status": r.get("collection_status") or "",
                "source_posted_at": r.get("source_posted_at") or "", "_record": r,
            })
    fields = [k for k in selected[0] if k != "_record"]
    with (out / "S031_SAMPLE_100.csv").open("w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows({k:r[k] for k in fields} for r in selected)
    with (work / "selected_records.jsonl").open("w", encoding="utf-8") as h:
        for r in selected:
            rec = dict(r["_record"]); rec["s031_selection"] = {k:r[k] for k in fields}
            h.write(json.dumps(rec, ensure_ascii=False) + "\n")
    summary["selected_strata"] = dict(Counter(r["selection_stratum"] for r in selected))
    (work / "selection_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for company in COMPANIES:
        subset = [r for r in selected if r["company"] == company]
        with (work / f"review_{company}.md").open("w", encoding="utf-8") as h:
            for i, r in enumerate(subset, 1):
                rec = r["_record"]
                h.write(f"\n## {company} #{i} | {r['job_id']} | {r['job_title']}\n\n")
                h.write(f"STRATUM: {r['selection_stratum']}\nSTATUS: {r['collection_status']}\nURL: {r['source_url']}\n\n")
                h.write((rec.get("job_description") or "[NO DESCRIPTION]") + "\n")
    print(json.dumps({"selected": len(selected), "strata": summary["selected_strata"], "unmet": {c:v["unmet_quotas"] for c,v in summary["companies"].items()}}, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
