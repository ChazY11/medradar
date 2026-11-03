"""Deterministic, evidence-grounded AI Research Analyst engine.

MedRadar 2.0's analyst is **not** an LLM: it never calls the network, needs no
API key, and does not generate free-form text from a language model. A question
is normalised (full-width punctuation and common traditional characters are
folded), parsed into a small closed set of intents with deterministic regex /
token rules, executed against :mod:`medradar.product.store`, and answered in
Chinese whose numbers all come from **that call's** query results. Every concrete
company / track statement carries traceable ``event_id`` values returned by
``evidence_search`` (or ``claim_evidence``); when a slice has no records the
engine says so instead of inventing numbers.

Supported intents
-----------------
``company_track_trend``
    one company + one track (or a multi-track radar domain)
``company_compare``
    2–5 companies, optionally narrowed to one track
``track_company_leaders``
    one track / domain, per-company activity versus the prior window
``track_acceleration``
    curated radar tracks ranked by observed change versus the prior window
``company_overview``
    one company: headline, main tracks, milestones
``evidence_lookup``
    explicit record lookup ("最近一次…PMA", "2024 年…记录")
``needs_clarification`` / ``out_of_scope``
    honest non-answers with clickable follow-up questions

The module deliberately owns no measurement: every number is read from
``store``; the only curated data here are entity aliases and intent keywords.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from functools import lru_cache
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import catalog, entities, store

# --------------------------------------------------------------------- constants
MODE = "deterministic"
MODE_ZH = (
    "确定性证据检索引擎（无 LLM、无 API Key）：问题先被解析为结构化意图，"
    "再直接查询数据库，所有数字均来自本次查询，结论可逐条回溯到事件记录。"
)
MAX_QUESTION = 300
DEFAULT_YEARS = 5
EVIDENCE_LIMIT = 8

#: A per-company increase is only labelled a *statistical signal* when the
#: Poisson-style z score reaches this threshold (same formula as the store's
#: ``track_companies``) and both windows together hold enough records.
SIGNAL_Z = 2.0
SIGNAL_MIN_TOTAL = 10

INTENT_LABELS: dict[str, str] = {
    "company_track_trend": "企业×赛道趋势",
    "company_compare": "多企业横向比较",
    "track_company_leaders": "赛道企业活跃度",
    "track_acceleration": "技术赛道加速扫描",
    "company_overview": "企业画像",
    "evidence_lookup": "证据检索",
    "needs_clarification": "需要澄清",
    "out_of_scope": "超出数据边界",
}

KIND_LABELS: dict[str, str] = {
    "510k": "FDA 510(k)",
    "pma": "FDA PMA",
    "device_recall": "器械召回",
    "trial": "临床试验注册",
    "8k_catalyst": "8-K 公司事件",
    "drug_approval": "药品批准",
}

_FEATURED_ALIASES: dict[str, list[str]] = {
    "medtronic": ["美敦力", "美敦力公司", "Medtronic", "MDT"],
    "ge_healthcare": [
        "GE 医疗",
        "GE医疗",
        "通用电气医疗",
        "GE HealthCare",
        "GE Healthcare",
        "GEHC",
        "GE Medical",
        "GE",
    ],
    "philips": ["飞利浦", "飞利浦医疗", "Philips", "PHG"],
    "draeger": ["德尔格", "德尔格医疗", "Dräger", "Draeger", "Drager", "DRW3"],
    "mindray": ["迈瑞医疗", "迈瑞", "Mindray", "300760"],
}

#: Chinese / English synonyms for track ids. Curated product vocabulary only —
#: every id below exists in the store's ``tracks`` table.
_CURATED_TRACK_KEYWORDS: dict[str, list[str]] = {
    "patient_monitoring": ["患者监护", "病人监护", "床旁监护", "监护仪", "生命体征", "patient monitoring", "monitoring"],
    "imaging_mr_ct": ["医学影像", "影像", "磁共振", "核磁", "mri", "mr", "ct", "x光", "x-ray", "medical imaging"],
    "imaging_us": ["超声", "超声波", "超声诊断", "ultrasound", "sonography"],
    "respiratory": ["呼吸", "呼吸支持", "呼吸机", "通气", "麻醉", "呼吸与麻醉", "ventilation", "respiratory", "anesthesia"],
    "medical_ai": ["医疗ai", "人工智能", "ai医疗", "医疗软件", "samd", "medical ai"],
    "cardiac_rhythm": ["心脏节律", "心律", "起搏", "icd", "cardiac rhythm", "pacing"],
    "coronary": ["冠脉", "冠状动脉", "coronary"],
    "structural_heart": ["结构性心脏病", "结构心", "tavr", "structural heart"],
    "heart_failure": ["心衰", "机械循环", "heart failure"],
    "ep_pfa": ["电生理", "消融", "pfa", "electrophysiology", "ablation"],
    "peripheral_vascular": ["外周血管", "peripheral vascular"],
    "surgical_robotics": ["手术机器人", "机器人手术", "surgical robotics", "robotic surgery"],
    "surgical_energy": ["手术能量", "能量器械", "surgical energy"],
    "endoscopy": ["内窥镜", "内镜", "endoscopy"],
    "general_surgery": ["普外", "手术耗材", "general surgery"],
    "ivd_immuno": ["免疫诊断", "immunoassay"],
    "ivd_molecular": ["分子诊断", "molecular diagnostics"],
    "ivd_poct": ["床旁检验", "即时检验", "poct", "point of care"],
    "ortho_joint": ["关节", "骨科植入", "orthopedic joints"],
    "spine": ["脊柱", "spine"],
    "trauma": ["创伤骨科", "trauma"],
    "diabetes_cgm": ["糖尿病", "cgm", "连续血糖"],
    "insulin_delivery": ["胰岛素", "insulin"],
    "dialysis": ["透析", "血液净化", "dialysis"],
    "neurostimulation": ["神经调控", "neurostimulation"],
    "neurovascular": ["神经介入", "neurovascular"],
    "ophthalmology": ["眼科", "ophthalmology"],
    "wound_care": ["伤口", "敷料", "wound care"],
    "infection_control": ["感染控制", "消毒", "infection control"],
    "wearable_remote": ["可穿戴", "远程监测", "wearable"],
}

#: Synonyms for the eight curated radar domains. Single-track domains are folded
#: into that track; multi-track domains are aggregated across their member tracks.
_CURATED_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "patient_monitoring": ["患者监护", "病人监护", "生命体征监护", "监护"],
    "medical_imaging": ["医学影像", "医学成像", "放射影像", "影像科"],
    "ultrasound": ["超声", "超声波", "超声影像"],
    "respiratory": ["呼吸与通气", "呼吸支持", "通气", "呼吸治疗"],
    "ivd": ["体外诊断", "ivd"],
    "medical_ai": ["医疗 ai", "医疗人工智能", "人工智能", "医疗软件", "samd"],
    "cardiovascular": ["心血管", "心血管器械", "心脏", "心脏介入", "cardiovascular"],
    "surgical": ["外科", "外科技术", "手术", "手术技术", "surgical"],
}

#: What the deterministic parser understands as a "record lookup" question.
_RECORD_RE = re.compile(
    r"最近一次|最近|最新|记录|列出|列举|检索|查找|逐条|具体(?:是|哪)|哪一次|哪一条"
)
_STRONG_RECORD_RE = re.compile(r"最近一次|最新|列出|列举|检索|查找|逐条|哪一次|哪一条|具体(?:是|哪)")
_TREND_WORDS_RE = re.compile(r"趋势|变化|走势|增长|下降|增加|减少|表现")
_COMPARE_RE = re.compile(r"对比|比较|区别|差异|不同|相比|vs\.?|compare|versus")
_ACCEL_RE = re.compile(r"加速|增长最快|哪些(?:领域|赛道|方向)|最快(?:的)?(?:领域|赛道)|明显(?:增加|增长|加速)|领跑")
_LATEST_RE = re.compile(r"最近一次|最新|最近")

_TIME_RANGE_RE = re.compile(
    r"(?<!\d)((?:19|20)\d{2})\s*年?\s*(?:-|–|—|~|～|至|到)\s*((?:19|20)\d{2})\s*年?"
)
_TIME_SINCE_RE = re.compile(r"(?:自\s*)?((?:19|20)\d{2})\s*年\s*(?:以来|起|至今)")
_TIME_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*年")
_TIME_LAST_RE = re.compile(r"(?:过去|近|最近|前)\s*([零一二两三四五六七八九十\d]{1,2})\s*年")

_METRIC_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("pma", re.compile(r"(?<![a-z])pma(?![a-z])|上市前批准|premarket approval")),
    ("510k", re.compile(r"510\s*\(?k\)?|五幺零|上市前通知")),
    ("recalls", re.compile(r"召回|recall")),
    ("trials", re.compile(r"临床试验|试验注册|trial")),
    ("corporate", re.compile(r"8-k|8k|公司事件")),
    ("approvals", re.compile(r"公开审批|审批|批准|许可|获批|approval|clearance")),
]

#: Hard data-boundary rules: questions the store cannot answer honestly.
_SCOPE_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("strategy", "企业内部战略 / 研发投入", re.compile(r"战略|策略|内部规划|规划|布局|组织架构|研发|r&d|roadmap|路线图")),
    ("finance", "营收 / 销售 / 利润等财务数据", re.compile(r"营收|营业收入|收入|销售额|销售收|利润|毛利|净利|财报|财务|业绩|股价|市值|revenue|sales|profit|earnings")),
    ("market_share", "市场份额 / 市场规模", re.compile(r"市场份额|市占率|市场占有率|市场地位|市场规模|market share|market size|市场.{0,4}份额|占(?:多少|几成)份额|份额")),
    ("global", "美国以外的全球监管活动", re.compile(r"全球|海外|欧洲|欧盟|日本|韩国|nmpa|ce认证|ce 认证|中国|国内")),
    ("causal", "因果解释", re.compile(r"为什么|為何|为何|原因|导致|因为|归因|因果|(?<![a-z])why(?![a-z])")),
    ("prediction", "经过验证的未来预测", re.compile(r"预测|预计|预估|将会|未来|前景|forecast|predict|会不会|能否|明年|后年")),
    ("innovation_rank", "创新能力排名", re.compile(r"创新能力|创新排名|最创新|研发能力|技术实力|哪家最强|谁最强|排名第一|最强的企业")),
    ("internal", "内部 / 非公开信息", re.compile(r"内部数据|非公开|商业秘密|内部消息")),
]

_TRADITIONAL_MAP = str.maketrans(
    {
        "爾": "尔", "醫": "医", "療": "疗", "學": "学", "監": "监", "護": "护",
        "飛": "飞", "邁": "迈", "體": "体", "徵": "征", "動": "动", "術": "术",
        "機": "机", "診": "诊", "斷": "断", "創": "创", "圍": "围", "與": "与",
        "對": "对", "較": "较", "別": "别", "顯": "显", "領": "领", "導": "导",
        "軟": "软", "應": "应", "預": "预", "測": "测", "頻": "频", "際": "际",
        "價": "价", "產": "产", "業": "业", "獲": "获", "證": "证", "類": "类",
        "間": "间", "開": "开", "關": "关", "審": "审", "記": "记", "錄": "录",
        "據": "据", "數": "数", "計": "计", "藥": "药", "為": "为", "麼": "么",
        "嗎": "吗", "歐": "欧", "亞": "亚", "區": "区", "場": "场", "營": "营",
        "銷": "销", "額": "额", "潤": "润", "趨": "趋", "勢": "势", "擴": "扩",
        "張": "张", "併": "并", "購": "购", "戰": "战", "競": "竞", "爭": "争",
        "優": "优", "點": "点", "號": "号", "條": "条", "灣": "湾", "韓": "韩",
        "億": "亿", "萬": "万", "帶": "带", "術": "术", "據": "据", "選": "选",
    }
)

_CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_BASE_LIMITATIONS = [
    "us_only",
    "record_not_product",
    "track_mapping",
    "not_prediction",
]
_ENTITY_LIMITATIONS = ("draeger", "mindray")


# ----------------------------------------------------------------- normalisation
def _normalize(question: str) -> tuple[str, list[int]]:
    """NFKC + traditional-character fold + whitespace collapse, with an index map.

    ``index[i]`` is the offset in the *original* question of normalised char ``i``
    so every matched span can be reported as raw text from the user's question.
    """
    chars: list[str] = []
    index: list[int] = []
    for original_index, char in enumerate(question):
        folded = unicodedata.normalize("NFKC", char).translate(_TRADITIONAL_MAP)
        for out in folded:
            chars.append(out)
            index.append(original_index)
    text: list[str] = []
    positions: list[int] = []
    previous_space = False
    for char, position in zip(chars, index):
        if char.isspace():
            if previous_space:
                continue
            text.append(" ")
            positions.append(position)
            previous_space = True
        else:
            text.append(char)
            positions.append(position)
            previous_space = False
    return "".join(text), positions


def _compact(question: str) -> tuple[str, list[int]]:
    """Lower-cased alphanumeric-only view used for entity span matching."""
    chars: list[str] = []
    index: list[int] = []
    for original_index, char in enumerate(question):
        folded = unicodedata.normalize("NFKC", char).translate(_TRADITIONAL_MAP)
        for out in folded:
            if out.isspace() or not out.isalnum():
                continue
            chars.append(out.lower())
            index.append(original_index)
    return "".join(chars), index


def _alias_key(alias: str) -> str:
    chars: list[str] = []
    for char in unicodedata.normalize("NFKC", str(alias)).translate(_TRADITIONAL_MAP):
        if char.isalnum():
            chars.append(char.lower())
    return "".join(chars)


def _raw_span(question: str, index: Sequence[int], start: int, end: int) -> dict[str, Any] | None:
    if end <= start or start < 0 or end > len(index):
        return None
    first = index[start]
    last = index[end - 1] + 1
    return {"start": first, "end": last, "text": question[first:last]}


def _is_ascii_word(char: str) -> bool:
    return bool(char) and char.isascii() and char.isalnum()


def _boundary_ok(text: str, start: int, end: int, needle: str) -> bool:
    # Short pure-ASCII aliases (``ge``, ``ct``, ``ai`` …) must be standalone
    # tokens; longer names and CJK phrases may match inside a longer run.
    if not needle.isascii() or len(needle) >= 6:
        return True
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return not (_is_ascii_word(before) or _is_ascii_word(after))


# ------------------------------------------------------------------ alias tables
@lru_cache(maxsize=1)
def _company_alias_table() -> tuple[dict[str, Any], ...]:
    entries: dict[str, dict[str, Any]] = {}

    def add(key: str, alias: str) -> None:
        match_key = _alias_key(alias)
        if not match_key or match_key in entries:
            return
        meta = entities.company_meta(key) or {}
        entries[match_key] = {
            "kind": "company",
            "key": key,
            "name_zh": str(meta.get("name_zh") or meta.get("name_en") or key),
            "name_en": str(meta.get("name_en") or key),
            "alias": str(alias),
            "match_key": match_key,
        }

    # Featured firms first: their curated Chinese / English / ticker aliases win
    # any collision, then every roster company gets its roster names.
    for key, aliases in _FEATURED_ALIASES.items():
        for alias in aliases:
            add(key, alias)
    for key, meta in entities.roster().items():
        for alias in (meta.get("name_zh"), meta.get("name_en"), meta.get("ticker")):
            if alias:
                add(key, str(alias))
    return tuple(sorted(entries.values(), key=lambda item: (-len(item["match_key"]), item["match_key"])))


@lru_cache(maxsize=1)
def _track_alias_table() -> tuple[dict[str, Any], ...]:
    entries: dict[str, dict[str, Any]] = {}
    tracks = store.track_rows()

    def add(
        kind: str,
        scope_id: str,
        label_zh: str,
        name_zh: str,
        track_ids: Sequence[str],
        alias: str,
    ) -> None:
        match_key = _alias_key(alias)
        if not match_key or match_key in entries:
            return
        entries[match_key] = {
            "kind": kind,
            "id": scope_id,
            "label_zh": label_zh,
            "name_zh": name_zh,
            "track_ids": list(track_ids),
            "alias": str(alias),
            "match_key": match_key,
        }

    # Domains are added first so their (human-facing) labels win over the raw
    # track names when both aliases target the same single track.
    for domain in catalog.RADAR_DOMAINS:
        members = [track for track in domain["tracks"] if track in tracks]
        if not members:
            continue
        if len(members) == 1:
            kind, scope_id = "track", members[0]
            name_zh = str(tracks[members[0]].get("name_zh") or members[0])
        else:
            kind, scope_id = "domain", domain["id"]
            name_zh = domain["label_zh"]
        label = domain["label_zh"]
        aliases = [domain["label_zh"], domain.get("label_en"), *_CURATED_DOMAIN_KEYWORDS.get(domain["id"], [])]
        for alias in aliases:
            if alias:
                add(kind, scope_id, label, name_zh, members, str(alias))

    for track_id in sorted(tracks):
        if track_id.startswith("t_"):
            # Drug-modality tracks are intentionally out of the device analyst's
            # entity vocabulary (their names collide with device tracks).
            continue
        meta = tracks[track_id]
        base_name = re.split(r"[（(]", str(meta.get("name_zh") or track_id))[0].strip()
        for alias in [base_name, meta.get("name_en"), *_CURATED_TRACK_KEYWORDS.get(track_id, [])]:
            if alias:
                add("track", track_id, base_name or track_id, str(meta.get("name_zh") or track_id), [track_id], str(alias))
    return tuple(sorted(entries.values(), key=lambda item: (-len(item["match_key"]), item["match_key"])))


def _find_aliases(
    question: str,
    match_text: str,
    match_index: Sequence[int],
    table: Sequence[Mapping[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    consumed = bytearray(len(match_text))
    found: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for entry in table:
        needle = str(entry["match_key"])
        position = match_text.find(needle)
        while position != -1:
            end = position + len(needle)
            if not any(consumed[position:end]) and _boundary_ok(match_text, position, end, needle):
                for index in range(position, end):
                    consumed[index] = 1
                span = _raw_span(question, match_index, position, end)
                if span:
                    found.append((dict(entry), span))
                break
            position = match_text.find(needle, position + 1)
    return found


# ------------------------------------------------------------------------ parsing
def _cn_to_int(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if len(raw) == 1 and raw in _CN_DIGITS:
        return _CN_DIGITS[raw]
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def _parse_companies(question: str, match_text: str, match_index: Sequence[int]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for entry, span in _find_aliases(question, match_text, match_index, _company_alias_table()):
        key = entry["key"]
        current = best.get(key)
        if current is None or span["start"] < current["span"]["start"]:
            best[key] = {
                "key": key,
                "name_zh": entry["name_zh"],
                "name_en": entry["name_en"],
                "matched": span["text"],
                "span": span,
            }
    return sorted(best.values(), key=lambda item: (item["span"]["start"], item["key"]))


def _parse_tracks(question: str, match_text: str, match_index: Sequence[int]) -> list[dict[str, Any]]:
    best: dict[tuple[str, ...], dict[str, Any]] = {}
    for entry, span in _find_aliases(question, match_text, match_index, _track_alias_table()):
        scope_key = tuple(entry["track_ids"])
        current = best.get(scope_key)
        if current is None or span["start"] < current["span"]["start"]:
            best[scope_key] = {
                "id": entry["id"],
                "kind": entry["kind"],
                "label_zh": entry["label_zh"],
                "name_zh": entry["name_zh"],
                "track_ids": list(entry["track_ids"]),
                "matched": span["text"],
                "span": span,
            }
    return sorted(best.values(), key=lambda item: (item["span"]["start"], item["id"]))


def _parse_time(question: str, norm: str, norm_index: Sequence[int]) -> dict[str, Any]:
    edge = store.data_edge()

    def build(kind: str, years: int | None, start: str | None, end: str | None, match: re.Match[str] | None) -> dict[str, Any]:
        span = _raw_span(question, norm_index, match.start(), match.end()) if match else None
        if start is None or end is None:
            start, end = store.resolve_window(years or DEFAULT_YEARS)
        return {
            "kind": kind,
            "years": years,
            "start": start,
            "end": end,
            "matched": span["text"] if span else "",
            "span": span,
        }

    match = _TIME_RANGE_RE.search(norm)
    if match:
        first, second = int(match.group(1)), int(match.group(2))
        start_year, end_year = min(first, second), max(first, second)
        start_date = f"{start_year:04d}-01-01"
        end_date = f"{end_year:04d}-12-31"
        years = max(1, min(50, round((date.fromisoformat(end_date) - date.fromisoformat(start_date)).days / 365.25)))
        return build("range", years, start_date, end_date, match)

    match = _TIME_SINCE_RE.search(norm)
    if match:
        start_year = int(match.group(1))
        start_date = f"{start_year:04d}-01-01"
        years = max(1, min(50, round((date.fromisoformat(edge) - date.fromisoformat(start_date)).days / 365.25)))
        return build("since", years, start_date, edge, match)

    match = _TIME_YEAR_RE.search(norm)
    if match:
        year = int(match.group(1))
        start_date = f"{year:04d}-01-01"
        end_date = f"{year:04d}-12-31"
        return build("year", 1, start_date, end_date, match)

    match = _TIME_LAST_RE.search(norm)
    if match:
        years = _cn_to_int(match.group(1))
        if years is None:
            return build("default", DEFAULT_YEARS, None, None, None)
        years = max(1, min(50, years))
        return build("years", years, None, None, match)

    return build("default", DEFAULT_YEARS, None, None, None)


def _find_metric(norm_lower: str, norm_index: Sequence[int], question: str) -> tuple[str, dict[str, Any] | None]:
    for metric, pattern in _METRIC_RULES:
        match = pattern.search(norm_lower)
        if match:
            return metric, _raw_span(question, norm_index, match.start(), match.end())
    return "approvals", None


def _record_lookup_match(norm_lower: str, metric_explicit: bool) -> re.Match[str] | None:
    """Decide whether a question asks for records rather than a trend.

    ``记录`` alone is not enough: "记录趋势" is a trend question. Strong verbs
    ("最近一次", "列出", "检索") always win, a plain ``记录`` wins unless the
    question also asks about a trend, and an explicit metric plus ``最近`` is
    treated as a record lookup ("最近一次…PMA 是什么").
    """
    strong = _STRONG_RECORD_RE.search(norm_lower)
    if strong:
        return strong
    has_record = "记录" in norm_lower
    trend = _TREND_WORDS_RE.search(norm_lower)
    if has_record and not trend:
        return _RECORD_RE.search(norm_lower)
    if metric_explicit and re.search(r"最近|具体", norm_lower):
        return re.search(r"最近|具体", norm_lower)
    return None


def _prepare(question: str) -> tuple[str, list[int], str, list[int]]:
    norm, norm_index = _normalize(question)
    match_text, match_index = _compact(question)
    return norm, norm_index, match_text, match_index


def _build_parsed(question: str) -> dict[str, Any]:
    norm, norm_index, match_text, match_index = _prepare(question)
    norm_lower = norm.lower()
    companies = _parse_companies(question, match_text, match_index)
    tracks = _parse_tracks(question, match_text, match_index)
    metric, metric_span = _find_metric(norm_lower, norm_index, question)
    time_info = _parse_time(question, norm, norm_index)
    edge = store.data_edge()

    compare_match = _COMPARE_RE.search(norm_lower)
    acceleration_match = _ACCEL_RE.search(norm_lower)
    metric_explicit = metric_span is not None
    record_match = _record_lookup_match(norm_lower, metric_explicit)
    latest_match = _LATEST_RE.search(norm_lower)

    spans: list[dict[str, Any]] = []
    for item in companies:
        spans.append({"kind": "company", **item["span"]})
    for item in tracks:
        spans.append({"kind": "track", **item["span"]})
    if time_info["span"]:
        spans.append({"kind": "time", **time_info["span"]})
    if metric_span:
        spans.append({"kind": "metric", **metric_span})
    for kind, match in (
        ("compare", compare_match),
        ("acceleration", acceleration_match),
        ("record_lookup", record_match),
    ):
        if match:
            span = _raw_span(question, norm_index, match.start(), match.end())
            if span:
                spans.append({"kind": kind, **span})
    spans.sort(key=lambda item: (item["start"], item["end"], item["kind"]))

    start = time_info["start"]
    end = time_info["end"]
    prior_start, prior_end = store.previous_window(start, end)
    return {
        "companies": [
            {key: item[key] for key in ("key", "name_zh", "name_en", "matched", "span")}
            for item in companies
        ],
        "tracks": [
            {key: item[key] for key in ("id", "kind", "label_zh", "name_zh", "track_ids", "matched", "span")}
            for item in tracks
        ],
        # Convenience flat views for the UI (the rich objects above carry names
        # and raw matched spans; these are the same values as plain lists).
        "company_keys": [item["key"] for item in companies],
        "track_ids": [track for scope in tracks for track in scope["track_ids"]],
        "years": time_info["years"],
        "metric": metric,
        "metric_source": "explicit" if metric_span else "default",
        "metric_label_zh": catalog.METRICS[metric]["label_zh"],
        "window": {
            "start": start,
            "end": end,
            "prior_start": prior_start,
            "prior_end": prior_end,
            "data_edge": edge,
        },
        "time": {"kind": time_info["kind"], "matched": time_info["matched"], "span": time_info["span"]},
        "compare": bool(compare_match),
        "acceleration": bool(acceleration_match),
        "record_lookup": bool(record_match),
        "latest": bool(latest_match),
        "spans": spans,
    }


# ------------------------------------------------------------------- limitations
def _limitation_texts(keys: Iterable[str]) -> list[str]:
    out: list[str] = []
    for key in keys:
        text = catalog.LIMITATIONS.get(str(key))
        if text and text not in out:
            out.append(text)
    return out


def _entity_limitations(company_keys: Iterable[str]) -> list[str]:
    if any(key in _ENTITY_LIMITATIONS for key in company_keys):
        return ["entity_mapping"]
    return []


# --------------------------------------------------------------- text formatting
def _fmt_pct(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "无对照"
    return f"{value:+.{digits}%}"


def _metric_phrase(metric: str) -> str:
    """Readable metric noun phrase that never doubles the word "记录"."""
    label = catalog.METRICS[metric]["label_zh"]
    if label.endswith(("记录", "事件", "注册")):
        return label
    if label and label[0].isascii():
        return f"{label} 记录"
    return f"{label}记录"


def _counted(count: int | str, metric: str) -> str:
    """``"12 条公开审批/许可记录"`` with a space before ASCII metric labels."""
    phrase = _metric_phrase(metric)
    gap = " " if phrase and phrase[0].isascii() else ""
    return f"{count} 条{gap}{phrase}"


def _fmt_share(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _fmt_delta_pct(delta: int | float | None, pct: float | None) -> str:
    number = 0 if delta is None else int(delta)
    return f"{number:+d}（{_fmt_pct(pct)}）"


def _poisson_z(recent: int, prior: int) -> float | None:
    denominator = (recent + prior) ** 0.5
    if denominator <= 0:
        return None
    return round((recent - prior) / denominator, 3)


def _share(recent: int, total: int | None) -> float | None:
    if not total:
        return None
    return recent / total


def _period_text(window: Mapping[str, Any]) -> str:
    return f"{window['start']} 至 {window['end']}（对照窗口 {window['prior_start']} 至 {window['prior_end']}）"


def _scope_label(scope: Mapping[str, Any]) -> str:
    return str(scope.get("label_zh") or scope.get("name_zh") or scope.get("id"))


def _inline_name(name: str) -> str:
    """Names that start with ASCII (``GE 医疗``) need a leading space in prose."""
    text = str(name)
    return f" {text}" if text and text[0].isascii() else text


def _section(
    title_zh: str,
    body_zh: str,
    columns: Sequence[str] | None = None,
    rows: Sequence[Sequence[Any]] | None = None,
    bullets: Sequence[str] | None = None,
) -> dict[str, Any]:
    section: dict[str, Any] = {
        "title_zh": title_zh,
        "body_zh": body_zh,
        "bullets": [str(item) for item in (bullets or [])],
    }
    if columns:
        section["table"] = {
            "columns": [str(column) for column in columns],
            "rows": [[str(cell) for cell in row] for row in (rows or [])],
        }
    return section


def _method_limitation_sections(
    limitation_keys: Iterable[str],
    method_body: str,
    method_bullets: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    texts = _limitation_texts(limitation_keys)
    return [
        _section("方法与口径", method_body, bullets=method_bullets),
        _section("局限", "以下数据口径限制适用于本回答：", bullets=texts),
    ]


def _event_evidence(
    items: Iterable[Mapping[str, Any]],
    why: Callable[[Mapping[str, Any]], str],
    limit: int = EVIDENCE_LIMIT,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        event_id = item.get("event_id")
        if not event_id or event_id in seen:
            continue
        seen.add(str(event_id))
        out.append(
            {
                "event_id": str(event_id),
                "event_date": item.get("event_date"),
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "company_name_zh": item.get("company_name_zh") or "",
                "track_name_zh": item.get("track_name_zh") or "",
                "why_zh": why(item),
            }
        )
        if len(out) >= limit:
            break
    return out


def _kind_counts(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        kind = str(item.get("kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _kind_counts_text(items: Sequence[Mapping[str, Any]]) -> str:
    counts = _kind_counts(items)
    return "、".join(f"{KIND_LABELS.get(kind, kind)} {count} 条" for kind, count in sorted(counts.items()))


def _response(
    question: str,
    status: str,
    intent_type: str,
    parsed: Mapping[str, Any],
    answer_zh: str,
    sections: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    limitations: Sequence[str],
    followups: Sequence[str],
    computation_zh: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "question": question,
        "mode": MODE,
        "mode_zh": MODE_ZH,
        "intent": {
            "type": intent_type,
            "label_zh": INTENT_LABELS.get(intent_type, intent_type),
            "parsed": dict(parsed),
        },
        "answer_zh": answer_zh,
        "sections": [dict(section) for section in sections],
        "evidence": [dict(item) for item in evidence],
        "limitations": list(limitations),
        "followups": list(followups),
        "computation_zh": computation_zh,
    }


def _rolling_years(parsed: Mapping[str, Any]) -> tuple[int, bool]:
    """Integer rolling window for intents whose store API only takes ``years``.

    Returns ``(years, approximated)``. When the question carried an explicit
    calendar window that does not end at the dataset edge, the nearest rolling
    window is used and the approximation is disclosed in the answer.
    """
    time_kind = str(parsed["time"]["kind"])
    if time_kind in ("range", "since", "year"):
        start = date.fromisoformat(parsed["window"]["start"])
        edge = date.fromisoformat(str(parsed["window"]["data_edge"]))
        years = max(1, min(50, round((edge - start).days / 365.25)))
        return years, True
    return max(1, int(parsed["years"] or DEFAULT_YEARS)), False


# ---------------------------------------------------------------- intent helpers
def _window_approximation_note(years: int) -> str:
    start, end = store.resolve_window(years)
    return (
        f"该意图的存储层接口只支持“最近 N 年滚动窗口”，无法精确对齐任意日历区间；"
        f"问题中的明示年份已折算为近 {years} 年（实际窗口 {start} 至 {end}），数字请按实际窗口理解。"
    )


def _clamp_scopes(parsed: Mapping[str, Any], limit: int = 1) -> list[dict[str, Any]]:
    return [dict(scope) for scope in parsed["tracks"][:limit]]


def _scope_track_ids(scope: Mapping[str, Any]) -> list[str]:
    return list(scope.get("track_ids") or [])


def _track_name_for(track_id: str) -> str:
    return str(store.track_meta(track_id).get("name_zh") or track_id)


def _lookup_scope_evidence(
    companies: Sequence[str],
    track_ids: Sequence[str],
    metric: str,
    window: Mapping[str, Any],
    why: Callable[[Mapping[str, Any]], str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for track_id in track_ids:
        result = store.evidence_search(
            companies=tuple(companies),
            track=track_id,
            metric=metric,
            start=window["start"],
            end=window["end"],
            limit=EVIDENCE_LIMIT,
        )
        items.extend(result["items"])
    items.sort(key=lambda item: (item.get("event_date") or "", item.get("event_id") or ""), reverse=True)
    return _event_evidence(items, why)


# ------------------------------------------------- company_track_trend implementation
def _trend_sentence(
    name: str,
    label: str,
    recent: int,
    prior: int,
    pct: float | None,
    industry_recent: int,
    industry_prior: int,
    industry_pct: float | None,
    share_recent: float | None,
    share_prior: float | None,
    first_approval: str | None,
    new_in_window: bool,
) -> str:
    if recent == 0 and prior == 0:
        return ""
    if recent == prior:
        return (
            f"{name}在{label}赛道的公开审批记录本期与上期均为 {recent} 条，观察不到记录数变化；"
            f"同期该赛道全行业由 {industry_prior} 条变为 {industry_recent} 条（{_fmt_pct(industry_pct)}）。"
        )
    if prior == 0 and recent > 0:
        return (
            f"{name}在{label}赛道的公开审批记录本期出现 {recent} 条、上期为 0 条，"
            f"这是数据覆盖期内该企业在该赛道首次观察到审批活动（首条记录 {first_approval or '未知'}），"
            "无法据此判断长期趋势。"
        )
    verb = "增至" if recent > prior else "降至"
    share_part = (
        f"其在本赛道的记录份额由 {_fmt_share(share_prior)} 变为 {_fmt_share(share_recent)}"
        if share_recent is not None and share_prior is not None
        and recent + prior >= SIGNAL_MIN_TOTAL
        else "两期样本较少，份额变化仅供参考"
    )
    return (
        f"{name}在{label}赛道的公开审批记录由 {prior} 条{verb} {recent} 条（{_fmt_pct(pct)}）；"
        f"同期该赛道全行业由 {industry_prior} 条变为 {industry_recent} 条（{_fmt_pct(industry_pct)}），"
        f"{share_part}。"
    )


def _intent_company_track_trend(question: str, parsed: Mapping[str, Any]) -> dict[str, Any]:
    company = parsed["companies"][0]
    key = str(company["key"])
    name = str(company["name_zh"])
    scope = _clamp_scopes(parsed)[0]
    label = _scope_label(scope)
    track_ids = _scope_track_ids(scope)
    metric = "approvals"
    metric_label = catalog.METRICS[metric]["label_zh"]
    explicit_window = str(parsed["time"]["kind"]) in ("range", "since", "year")

    claims: list[dict[str, Any]] = []
    if explicit_window:
        requested = dict(start=parsed["window"]["start"], end=parsed["window"]["end"], years=int(parsed["years"]))
        table = store.company_track_table(key, metric, requested["start"], requested["end"])
        rows = list(table["rows"])
        total_recent, total_prior = int(table["total_recent"]), int(table["total_prior"])
        query_description = (
            f"store.company_track_table('{key}', 'approvals', '{requested['start']}', '{requested['end']}')"
        )
    else:
        claims_payload = store.company_claims(key, int(parsed["years"] or DEFAULT_YEARS))
        table = claims_payload["track_table"]
        requested = dict(start=table["window"]["start"], end=table["window"]["end"], years=int(parsed["years"]))
        rows = list(table["rows"])
        claims = [claim for claim in claims_payload["claims"] if claim["track"] in set(track_ids)]
        total_recent = int(table["total_recent"])
        total_prior = int(table["total_prior"])
        query_description = f"store.company_claims('{key}', {requested['years']})"
    analysis = table["analysis_window"]
    window = {
        "start": analysis["start"],
        "end": analysis["end"],
        "prior_start": analysis["prior_start"],
        "prior_end": analysis["prior_end"],
        "years": requested["years"],
        "basis": "complete_quarters",
        "requested_start": requested["start"],
        "requested_end": requested["end"],
        "completeness": analysis,
    }

    selected = [row for row in rows if row.get("track") in set(track_ids)]
    recent = sum(int(row["recent"]) for row in selected)
    prior = sum(int(row["prior"]) for row in selected)
    industry_recent = sum(int(row.get("industry_recent") or 0) for row in selected)
    industry_prior = sum(int(row.get("industry_prior") or 0) for row in selected)
    missing_tracks = [track for track in track_ids if track not in {row.get("track") for row in selected}]
    for track_id in missing_tracks:
        industry_recent += int(
            store.evidence_search(
                track=track_id,
                metric=metric,
                start=window["start"],
                end=window["end"],
                limit=1,
            )["total"]
        )
        industry_prior += int(
            store.evidence_search(
                track=track_id,
                metric=metric,
                start=window["prior_start"],
                end=window["prior_end"],
                limit=1,
            )["total"]
        )
    delta = recent - prior
    pct = (delta / prior) if prior else None
    industry_delta = industry_recent - industry_prior
    industry_pct = (industry_delta / industry_prior) if industry_prior else None
    share_recent = _share(recent, total_recent)
    share_prior = _share(prior, total_prior)
    share_change = (
        share_recent - share_prior
        if share_recent is not None and share_prior is not None
        else None
    )
    z = selected[0].get("z") if len(selected) == 1 else _poisson_z(recent, prior)
    if z is not None and (recent < 3 or prior < 3):
        method_extra_note = "本期或上期记录数少于 3 条，z 分数不稳定，仅作参考。"
    else:
        method_extra_note = ""
    firsts = [row.get("first_approval") for row in selected if row.get("first_approval")]
    first_approval = min(firsts) if firsts else None
    new_in_window = any(bool(row.get("new_in_window")) for row in selected)

    # evidence: same company / track / metric / window as the table numbers
    evidence_items: list[dict[str, Any]] = []
    for track_id in track_ids:
        result = store.evidence_search(
            companies=(key,),
            track=track_id,
            metric=metric,
            start=window["start"],
            end=window["end"],
            limit=3,
        )
        evidence_items.extend(result["items"])
    if not evidence_items:
        for track_id in track_ids:
            result = store.evidence_search(
                companies=(key,),
                track=track_id,
                metric=metric,
                start=window["prior_start"],
                end=window["prior_end"],
                limit=2,
            )
            evidence_items.extend(result["items"])

    def why(item: Mapping[str, Any]) -> str:
        date_text = item.get("event_date") or "未知日期"
        return (
            f"该记录（{date_text}，{KIND_LABELS.get(str(item.get('kind')), item.get('kind') or '公开记录')}）"
            f"是{name}在{item.get('track_name_zh') or label}赛道的公开审批记录，"
            "用于支撑表格中的本期/上期记录计数。"
        )

    evidence = _event_evidence(evidence_items, why)

    extra_keys: list[str] = []
    if recent + prior == 0 or new_in_window:
        extra_keys.append("coverage_change")
    limitation_keys = list(_BASE_LIMITATIONS) + extra_keys + _entity_limitations([key])
    limitations = _limitation_texts(limitation_keys)

    if recent + prior == 0:
        answer = (
            f"在 {_period_text(window)} 内，{name}在{label}赛道的公开审批记录为 0 条，"
            "现有证据不足以作出该判断。"
            "可以尝试放宽时间窗、去掉赛道限制，或改看召回/临床试验等其他指标。"
        )
        conclusion_body = answer
    else:
        if claims:
            conclusion_body = claims[0]["statement_zh"]
            if claims[0]["metrics"]["recent"] + claims[0]["metrics"]["prior"] < SIGNAL_MIN_TOTAL:
                conclusion_body += " 两期合计记录数较少，只能作为可逐条核查的观察记录，不足以判断趋势。"
            conclusion_body += " 以上为观察到的记录条数变化，不是因果结论或未来预测。"
        else:
            conclusion_body = _trend_sentence(
                name,
                label,
                recent,
                prior,
                pct,
                industry_recent,
                industry_prior,
                industry_pct,
                share_recent,
                share_prior,
                first_approval,
                new_in_window,
            )
            if recent + prior < SIGNAL_MIN_TOTAL:
                conclusion_body += " 两期合计记录数较少，只能作为可逐条核查的观察记录，不足以判断趋势。"
            conclusion_body += " 以上为观察到的记录条数变化，不是因果结论或未来预测。"
        answer = conclusion_body

    data_rows: list[list[str]] = [
        [f"{metric_label}（记录数）", str(recent), str(prior), _fmt_delta_pct(delta, pct), f"{industry_prior} → {industry_recent}（{_fmt_pct(industry_pct)}）"],
        ["本赛道记录份额（占企业已映射赛道审批记录）", _fmt_share(share_recent), _fmt_share(share_prior), (f"{share_change:+.1%}" if share_change is not None else "—"), "—"],
        ["企业已映射赛道审批记录（条）", str(total_recent), str(total_prior), _fmt_delta_pct(total_recent - total_prior, ((total_recent - total_prior) / total_prior) if total_prior else None), "—"],
    ]
    if len(selected) > 1:
        for row in sorted(selected, key=lambda item: -int(item["recent"])):
            data_rows.append(
                [
                    f"其中：{row.get('name_zh') or _track_name_for(str(row.get('track')))}",
                    str(row["recent"]),
                    str(row["prior"]),
                    _fmt_delta_pct(row["recent"] - row["prior"], row.get("pct_change")),
                    f"{row.get('industry_prior')} → {row.get('industry_recent')}（{_fmt_pct(row.get('industry_pct_change'))}）",
                ]
            )

    method_bullets = list(catalog.METRICS[metric].get("caveats") or [])
    method_bullets.append("对照窗口为紧邻的等长历史窗口；这是描述性比较，不做因果推断。")
    if method_extra_note:
        method_bullets.append(method_extra_note)
    sections = [
        _section("结论", conclusion_body),
        _section(
            "数据",
            f"统计口径：{window['start']} 至 {window['end']}；对照窗口 {window['prior_start']} 至 {window['prior_end']}。"
            f"指标为{metric_label}（记录条数，不是产品数）。",
            columns=["指标", "本期", "上期", "变化", "全行业对照"],
            rows=data_rows,
        ),
    ]
    sections.extend(
        _method_limitation_sections(
            limitation_keys,
            f"查询：{query_description}；再按赛道过滤/汇总。"
            f"份额 = 该赛道本期记录 / 企业本期已映射到技术赛道的审批记录（未映射记录不计入分母）；"
            f"全行业对照为同一窗口、同一指标下该赛道全部企业的记录条数。"
            f"证据参数：companies=('{key}',), track={track_ids}, metric='approvals', "
            f"start='{window['start']}', end='{window['end']}'。"
            f"（z 分数 = (本期-上期)/√(本期+上期)，仅作统计探测参考，不是预测。）",
            method_bullets,
        )
    )
    followups = [
        f"把{label}的时间窗换成近 3 年再看一次",
        f"对比{name}与其他企业在该赛道的公开活动",
        f"查看{label}赛道最近一次公开记录",
    ]
    computation_zh = (
        f"解析出企业 {name}（{key}）与技术赛道 {label}（{track_ids}），时间窗 {window['start']} 至 {window['end']}。"
        f"主查询：{query_description}。份额与全行业对照均来自同一次查询返回的字段（或缺失赛道时补查 "
        "store.evidence_search 的 COUNT）；证据列表来自同一企业/赛道/窗口的 store.evidence_search，"
        "逐条 event_id 可在证据浏览器打开。所有数字均为公开记录条数，不含未映射赛道的记录。"
    )
    return _response(
        question,
        "answered",
        "company_track_trend",
        parsed,
        answer,
        sections,
        evidence,
        limitations,
        followups,
        computation_zh,
    )


# ------------------------------------------------------- company_compare implementation
def _intent_company_compare(question: str, parsed: Mapping[str, Any]) -> dict[str, Any]:
    companies = [item for item in parsed["companies"]][:5]
    keys = tuple(str(item["key"]) for item in companies)
    metric = str(parsed["metric"] or "approvals")
    metric_label = catalog.METRICS[metric]["label_zh"]
    years, approximated = _rolling_years(parsed)
    scopes = _clamp_scopes(parsed)
    scope = scopes[0] if scopes else None
    track_ids = _scope_track_ids(scope) if scope else []
    label = _scope_label(scope) if scope else "全部赛道"

    result = store.company_compare(keys, metric=metric, years=years, granularity="year")
    analysis = result["analysis_window"]
    window = {
        "start": analysis["analysis_start"],
        "end": analysis["analysis_end"],
        "prior_start": analysis["prior_start"],
        "prior_end": analysis["prior_end"],
        "requested_start": result["window"]["start"],
        "requested_end": result["window"]["end"],
        "basis": "complete_quarters",
        "periods": analysis["periods"],
    }
    company_rows = list(result["companies"])
    warnings = list(result["warnings"])
    track_table = list(result["track_table"])
    target_rows = [row for row in track_table if row.get("track") in set(track_ids)]

    def company_summary(row: Mapping[str, Any]) -> dict[str, Any]:
        current = next(item for item in company_rows if item["key"] == row["key"])
        return {
            "key": current["key"],
            "name_zh": current["name_zh"],
            "total": int(current["total"]),
            "prior_total": int(current["prior_total"]),
            "total_mapped": int(current.get("total_mapped") or 0),
            "mapping_coverage": current.get("mapping_coverage"),
            "pct_change": ((current["total"] - current["prior_total"]) / current["prior_total"]) if current["prior_total"] else None,
            "pma_share": current["pathway"]["pma_share"],
            "pma_original": current["pathway"].get("pma_original"),
            "pma_supplement": current["pathway"].get("pma_supplement"),
            "track_n": 0,
            "track_share": None,
            "track_lq": None,
            "track_lq_status": None,
        }

    summaries = {row["key"]: company_summary(row) for row in company_rows}
    for track_row in target_rows:
        for matched in track_row.get("companies") or []:
            summary = summaries.get(str(matched["key"]))
            if summary is None:
                continue
            summary["track_n"] += int(matched["n"])
            summary["track_share"] = matched.get("share")
            summary["track_lq"] = matched.get("location_quotient")
            summary["track_lq_status"] = matched.get("lq_status")
    extra_limitation_keys = ["no_global_rank"] + (["recall_not_tech"] if metric == "recalls" else [])
    limitation_keys = list(_BASE_LIMITATIONS) + extra_limitation_keys + _entity_limitations(keys)
    limitations = _limitation_texts(limitation_keys)
    if not any(summary["total"] or summary["prior_total"] for summary in summaries.values()):
        answer = f"近 {years} 年窗口内所选企业都没有{_metric_phrase(metric)}，现有证据不足以作出该判断。"
        sections = [
            _section("结论", answer),
            _section("数据", f"窗口 {window['start']} 至 {window['end']}；指标 {metric_label}。", columns=["企业", "本期记录", "上期记录"], rows=[[summary["name_zh"], summary["total"], summary["prior_total"]] for summary in summaries.values()]),
        ]
        sections.extend(_method_limitation_sections(limitation_keys, f"查询：store.company_compare({keys}, metric='{metric}', years={years})。"))
        return _response(question, "answered", "company_compare", parsed, answer, sections, [], limitations, ["换成近 10 年再看一次", "查看某家企业的完整画像"], f"查询 store.company_compare，窗口内无记录。")

    totals_text = "、".join(
        f"{summary['name_zh']} {summary['total']} 条"
        for summary in sorted(summaries.values(), key=lambda item: item["total"], reverse=True)
    )
    sentence_parts = [
        f"近 {years} 年完整季度窗口（{window['start']} 至 {window['end']}；请求窗口 {window['requested_start']} 至 {window['requested_end']} 的起止不完整季度不计入比较），{totals_text}，"
        f"指标为{metric_label}。"
    ]
    if scope and target_rows:
        ranked = sorted(
            (item for item in summaries.values() if item["track_n"] >= 0),
            key=lambda item: item["track_n"],
            reverse=True,
        )
        if any(item["track_n"] for item in ranked):
            leader = ranked[0]
            track_total = sum(item["track_n"] for item in ranked)
            runner_ups = "、".join(
                f"{item['name_zh']} {item['track_n']} 条"
                for item in ranked[1:4]
                if item["track_n"]
            )
            sentence_parts.append(
                f"在{label}赛道，本期记录最多的是{_inline_name(leader['name_zh'])}（{leader['track_n']} 条"
                f"，占所选企业该赛道合计 {track_total} 条的 {(leader['track_n'] / track_total):.0%}）"
                + (f"，其次是{runner_ups}" if runner_ups else "")
                + "；该比较只反映公开记录结构，不能说明创新能力或市场地位。"
            )
    sentence_parts.append(
        "企业间差异同时受产品组合、PMA/510(k) 监管路径结构与数据覆盖起始时间影响，"
        "因此这里不给出“谁更创新/更强”的排名。"
    )
    if warnings:
        sentence_parts.append(
            "同时需要注意："
            + "；".join(str(warning["text_zh"]).rstrip("。") for warning in warnings[:2])
            + "。"
        )
    answer = "".join(sentence_parts)

    columns = ["企业", f"本期{metric_label}", "上期", "变化", "本期份额（占企业自身记录）", "赛道映射覆盖", "PMA 原始 / 补充"]
    data_rows: list[list[str]] = []
    for summary in sorted(summaries.values(), key=lambda item: item["total"], reverse=True):
        row = [
            summary["name_zh"],
            str(summary["total"]),
            str(summary["prior_total"]),
            _fmt_delta_pct(summary["total"] - summary["prior_total"], summary["pct_change"]),
            _fmt_share(summary["track_share"] if scope else _share(summary["total"], sum(item["total"] for item in summaries.values()))),
            _fmt_share(summary["mapping_coverage"]),
            f"{summary['pma_original'] or 0} / {summary['pma_supplement'] or 0}",
        ]
        data_rows.append(row)
    sections = [
        _section("结论", answer),
        _section(
            "数据",
            f"统计窗口 {window['start']} 至 {window['end']}（{window['periods']} 个完整自然季度）；"
            f"对照窗口 {window['prior_start']} 至 {window['prior_end']}；"
            f"指标为{metric_label}（记录条数，不是产品数）。"
            + ("份额列为所选赛道内的记录占比。" if scope else "份额列为所选企业合计内占比。"),
            columns=columns,
            rows=data_rows,
        ),
    ]
    if track_table:
        display_rows = target_rows if target_rows else track_table[:6]
        table_columns = ["赛道", "领域", "全行业本期"] + [summary["name_zh"] for summary in summaries.values()]
        table_rows: list[list[str]] = []
        for row in display_rows[:8]:
            values = [str(row.get("name_zh") or row.get("track")), str(row.get("domain") or "—"), str(row.get("industry_total") or 0)]
            for summary in summaries.values():
                matched = next((item for item in row.get("companies") or [] if item["key"] == summary["key"]), None)
                values.append(str(int(matched["n"])) if matched else "0")
            table_rows.append(values)
        sections.append(
            _section(
                "赛道分布" if not scope else f"{label}赛道分布",
                "同一时间窗内各赛道的记录条数；location quotient（专业化指数）见跟随提示。"
                if not scope
                else f"所选企业在{label}赛道的本期记录条数（同一时间窗、同一指标）。",
                columns=table_columns,
                rows=table_rows,
            )
        )
    sections.extend(
        _method_limitation_sections(
            limitation_keys,
            f"查询：store.company_compare({keys}, metric='{metric}', years={years}, granularity='year')。"
            f"赛道分布来自返回的 track_table；份额 = 该企业该赛道已映射记录 / 该企业已映射记录；"
            f"LQ 仅在企业与行业分母样本足够时给出，否则为“不适用”；全行业列为同一窗口该赛道的已映射记录数。"
            + (f" {_window_approximation_note(years)}" if approximated else ""),
            [*(f"可比性提示：{note}" for note in result.get("notes") or []), *(warning["text_zh"] for warning in warnings)],
        )
    )

    # evidence: per company, target track first, fall back to the company overall
    evidence_items: list[dict[str, Any]] = []
    for key in keys:
        if track_ids:
            for track_id in track_ids:
                evidence_items.extend(
                    store.evidence_search(
                        companies=(key,),
                        track=track_id,
                        metric=metric,
                        start=window["start"],
                        end=window["end"],
                        limit=2,
                    )["items"]
                )
        if not any(item.get("company_key") == key for item in evidence_items):
            evidence_items.extend(
                store.evidence_search(
                    companies=(key,),
                    metric=metric,
                    start=window["start"],
                    end=window["end"],
                    limit=1,
                )["items"]
            )

    def why(item: Mapping[str, Any]) -> str:
        return (
            f"该记录（{item.get('event_date') or '未知日期'}，{item.get('company_name_zh') or ''}）"
            f"属于{item.get('track_name_zh') or '未映射赛道'}，用于支撑比较表中该企业本期记录计数。"
        )

    evidence = _event_evidence(evidence_items, why, limit=10)
    followups = [
        "只看其中一家企业的赛道趋势",
        "换成 510(k) 或 PMA 指标再比较一次",
        "查看这些企业的赛道分布明细",
    ]
    computation_zh = (
        f"解析出 {len(keys)} 家企业 {keys}，时间窗近 {years} 年，指标 {metric}。"
        f"主查询：store.company_compare 返回企业总量、PMA/510(k) 路径结构、track_table 与可比性 warnings；"
        f"赛道单元格与份额来自 track_table；证据来自各企业同窗口的 store.evidence_search。"
        f"不计算、也不展示创新能力或市场份额排名。"
    )
    return _response(
        question,
        "answered",
        "company_compare",
        parsed,
        answer,
        sections,
        evidence,
        limitations,
        followups,
        computation_zh,
    )


# --------------------------------------------- track_company_leaders implementation
def _intent_track_company_leaders(question: str, parsed: Mapping[str, Any]) -> dict[str, Any]:
    scope = _clamp_scopes(parsed)[0]
    label = _scope_label(scope)
    track_ids = _scope_track_ids(scope)
    metric = str(parsed["metric"] or "approvals")
    metric_label = catalog.METRICS[metric]["label_zh"]
    years, approximated = _rolling_years(parsed)

    per_track: list[dict[str, Any]] = [store.track_companies(track_id, metric, years) for track_id in track_ids]
    window = dict(per_track[0]["window"]) if per_track else {}
    merged: dict[str, dict[str, Any]] = {}
    for track_result in per_track:
        for row in track_result["companies"]:
            entry = merged.setdefault(
                str(row["company"]),
                {"company": str(row["company"]), "name_zh": row.get("name_zh") or str(row["company"]), "recent": 0, "prior": 0, "first": [], "last": [], "by_track": {}},
            )
            entry["recent"] += int(row["recent"])
            entry["prior"] += int(row["prior"])
            if row.get("first"):
                entry["first"].append(row["first"])
            if row.get("last"):
                entry["last"].append(row["last"])
            entry["by_track"][str(track_result["track"]["id"])] = {"recent": int(row["recent"]), "prior": int(row["prior"])}
    total_recent = sum(int(result["total_recent"]) for result in per_track)
    total_prior = sum(int(result["total_prior"]) for result in per_track)
    delta = total_recent - total_prior
    pct = (delta / total_prior) if total_prior else None
    companies = list(merged.values())
    for entry in companies:
        entry["delta"] = entry["recent"] - entry["prior"]
        entry["pct_change"] = (entry["delta"] / entry["prior"]) if entry["prior"] else None
        entry["share"] = _share(entry["recent"], total_recent)
        entry["z"] = _poisson_z(entry["recent"], entry["prior"])
        entry["signal"] = bool(
            entry["z"] is not None
            and entry["z"] >= SIGNAL_Z
            and (entry["recent"] + entry["prior"]) >= SIGNAL_MIN_TOTAL
            and entry["delta"] > 0
        )
        entry["first"] = min(entry["first"]) if entry["first"] else None
        entry["last"] = max(entry["last"]) if entry["last"] else None
    companies.sort(key=lambda item: (-item["recent"], item["name_zh"]))
    increasers = [entry for entry in companies if entry["delta"] > 0]
    signals = [entry for entry in increasers if entry["signal"]]

    extra_limitation_keys = ["no_global_rank"] + (["recall_not_tech"] if metric == "recalls" else [])
    limitation_keys = (
        list(_BASE_LIMITATIONS)
        + extra_limitation_keys
        + _entity_limitations([entry["company"] for entry in companies])
    )
    limitations = _limitation_texts(limitation_keys)
    if total_recent + total_prior == 0:
        answer = (
            f"在 {_period_text(window)} 内，{label}赛道没有{_metric_phrase(metric)}，现有证据不足以作出该判断。"
            "可以换一个时间窗或换一个赛道再试。"
        )
        sections = [
            _section("结论", answer),
            _section("数据", f"窗口 {window.get('start')} 至 {window.get('end')}；赛道 {label}；指标 {metric_label}。", columns=["指标", "数值"], rows=[["本期记录", "0"], ["上期记录", "0"]]),
        ]
        sections.extend(_method_limitation_sections(limitation_keys, f"查询：store.track_companies({track_ids}, '{metric}', {years})。"))
        return _response(question, "answered", "track_company_leaders", parsed, answer, sections, [], limitations, ["换成近 10 年再看一次", "查看该赛道的公开记录"], f"查询 store.track_companies，窗口内无记录。")

    top_text = "、".join(
        f"{entry['name_zh']} {entry['recent']} 条"
        for entry in companies[:3]
        if entry["recent"] > 0
    )
    answer = (
        f"近 {years} 年（{window['start']} 至 {window['end']}），{label}赛道共 {_counted(total_recent, metric)}，"
        f"上期 {total_prior} 条（{_fmt_pct(pct)}）。"
        f"本期记录数高于上期的企业有 {len(increasers)} 家；其中 {len(signals)} 家达到统计探测阈值"
        f"（z≥{SIGNAL_Z:g} 且两期合计≥{SIGNAL_MIN_TOTAL} 条），其余只是观察到的增加，样本量不足以称为信号。"
        + (f"本期记录最多的是 {top_text}。" if top_text else "")
    )

    data_rows: list[list[str]] = []
    for entry in companies[:10]:
        if entry["signal"]:
            verdict = "增加（统计信号）"
        elif entry["delta"] > 0:
            verdict = "增加（仅观察）"
        elif entry["delta"] < 0:
            verdict = "减少"
        else:
            verdict = "持平"
        data_rows.append(
            [
                entry["name_zh"],
                str(entry["recent"]),
                str(entry["prior"]),
                f"{entry['delta']:+d}",
                _fmt_pct(entry["pct_change"]),
                _fmt_share(entry["share"]),
                "—" if entry["z"] is None else f"{entry['z']:.2f}",
                verdict,
            ]
        )
    sections = [
        _section("结论", answer),
        _section(
            "数据",
            f"统计窗口 {window['start']} 至 {window['end']}；对照窗口 {window['prior_start']} 至 {window['prior_end']}；"
            f"指标为{metric_label}（记录条数）。"
            + ("多赛道领域已按成员赛道合并计数，z 用合并后计数按同一公式重算。" if len(track_ids) > 1 else ""),
            columns=["企业", "本期", "上期", "变化", "变化率", "本期份额", "z", "判断"],
            rows=data_rows,
        ),
    ]
    sections.extend(
        _method_limitation_sections(
            limitation_keys,
            f"查询：store.track_companies({track_ids}, metric='{metric}', years={years})，"
            "逐赛道返回企业本期/上期记录数、份额与 z。"
            "z =（本期-上期）/√(本期+上期)，仅用于区分“观察到的增加”与“统计探测信号”，不代表因果或预测。"
            + (f" {_window_approximation_note(years)}" if approximated else ""),
            [
                "“增加”只说明公开记录条数变多；记录条数受申报节奏与数据覆盖影响。",
                "统计信号阈值（z≥2 且两期合计≥10 条）是本产品的展示规则，不是行业标准。",
            ],
        )
    )
    evidence_items: list[dict[str, Any]] = []
    for track_id in track_ids:
        evidence_items.extend(
            store.evidence_search(
                track=track_id,
                metric=metric,
                start=window["start"],
                end=window["end"],
                limit=3,
            )["items"]
        )
    if increasers:
        evidence_items.extend(
            store.evidence_search(
                companies=(increasers[0]["company"],),
                track=track_ids[0],
                metric=metric,
                start=window["start"],
                end=window["end"],
                limit=2,
            )["items"]
        )

    def why(item: Mapping[str, Any]) -> str:
        return (
            f"该记录（{item.get('event_date') or '未知日期'}，{item.get('company_name_zh') or ''}）"
            f"是{label}赛道本期的{_metric_phrase(metric)}，用于支撑赛道总量与领先企业的计数。"
        )

    evidence = _event_evidence(evidence_items, why)
    followups = [
        f"查看{label}赛道各企业的逐年走势",
        "换一个赛道再比较一次",
        "只看有统计信号的记录明细",
    ]
    computation_zh = (
        f"解析出技术赛道 {label}（{track_ids}），时间窗近 {years} 年。"
        f"主查询：store.track_companies 逐赛道返回企业本期/上期计数后合并；份额分母为该赛道本期总记录数；"
        f"z 为合并计数的泊松近似分数。证据来自同赛道的 store.evidence_search。"
        "不包含任何未映射到赛道或未映射到企业的记录。"
    )
    return _response(question, "answered", "track_company_leaders", parsed, answer, sections, evidence, limitations, followups, computation_zh)


# ------------------------------------------------ track_acceleration implementation
def _intent_track_acceleration(question: str, parsed: Mapping[str, Any]) -> dict[str, Any]:
    years, approximated = _rolling_years(parsed)
    metric = "approvals"
    metric_label = catalog.METRICS[metric]["label_zh"]
    payload = store.tracks_acceleration(years)
    window = dict(payload["window"])
    rows = list(payload["tracks"])
    accelerating = [row for row in rows if int(row["delta"]) > 0]
    accelerating.sort(key=lambda row: (-(row.get("pct_change") or 0), -int(row["recent"])))
    ranked = accelerating[:8]
    flagged = [row for row in ranked if (row.get("signal") or {}).get("flagged")]
    focus_scope = _clamp_scopes(parsed)
    focus_track = str(focus_scope[0]["id"]) if focus_scope else None
    limitation_keys = list(_BASE_LIMITATIONS) + ["coverage_change", "no_global_rank"]
    limitations = _limitation_texts(limitation_keys)

    if not ranked:
        answer = (
            f"在 {window['start']} 至 {window['end']} 相对 {window['prior_start']} 至 {window['prior_end']} 的对照中，"
            "没有任何 curated 赛道出现公开审批记录增加，因此没有可报告的加速赛道。"
        )
        sections = [
            _section("结论", answer),
            _section("数据", f"窗口 {window['start']} 至 {window['end']}；指标 {metric_label}。", columns=["指标", "数值"], rows=[["出现记录增加的赛道数", "0"]]),
        ]
        sections.extend(_method_limitation_sections(limitation_keys, f"查询：store.tracks_acceleration({years})。"))
        return _response(question, "answered", "track_acceleration", parsed, answer, sections, [], limitations, ["换成近 5 年再看一次", "查看患者监护赛道的企业构成"], f"查询 store.tracks_acceleration({years})。")

    top = ranked[0]
    flagged_names = "、".join(str(row["name_zh"]) for row in flagged[:3])
    focus_text = ""
    if focus_track:
        focused = next((row for row in rows if row["track"] == focus_track), None)
        if focused is not None:
            focus_text = (
                f"其中您提到的{focused['name_zh']}本期 {focused['recent']} 条、上期 {focused['prior']} 条"
                f"（{_fmt_pct(focused.get('pct_change'))}），在全部赛道中按变化率排名第 "
                f"{[row['track'] for row in rows].index(focus_track) + 1}。"
            )
    answer = (
        f"近 {years} 年（{window['start']} 至 {window['end']}），curated 技术赛道中有 {len(accelerating)} 个的公开审批记录数高于上期。"
        f"变化率最高的是{top['name_zh']}：本期 {top['recent']} 条、上期 {top['prior']} 条（{_fmt_pct(top.get('pct_change'))}）。"
        f"其中 {len(flagged)} 个赛道同时带有季度统计探测信号（|z|≥2.5 且当季≥5 条）"
        + (f"，分别是 {flagged_names}。" if flagged_names else "，其余只是观察到的计数变化。")
        + focus_text
        + " 记录条数变化可能来自数据覆盖、申报节奏或分类口径，不是未来预测。"
    )

    table_rows: list[list[str]] = []
    for row in ranked:
        signal = row.get("signal") or {}
        signal_text = (
            f"|z|={abs(float(signal.get('z')))}（{'已标记' if signal.get('flagged') else '未达阈值'}）"
            if signal
            else "基线不足"
        )
        verdict = "加速（有统计信号）" if signal.get("flagged") else "加速（仅观察）"
        table_rows.append(
            [
                str(row["name_zh"]),
                str(row.get("domain_label_zh") or "—"),
                str(row["recent"]),
                str(row["prior"]),
                f"{int(row['delta']):+d}",
                _fmt_pct(row.get("pct_change")),
                signal_text,
                verdict,
            ]
        )
    sections = [
        _section("结论", answer),
        _section(
            "数据",
            f"统计窗口 {window['start']} 至 {window['end']}；对照窗口 {window['prior_start']} 至 {window['prior_end']}；"
            f"指标为{metric_label}（记录条数）。表中按变化率排序，只列出记录数增加的赛道。",
            columns=["赛道", "领域", "本期", "上期", "变化", "变化率", "统计信号", "判断"],
            rows=table_rows,
        ),
    ]
    sections.extend(
        _method_limitation_sections(
            limitation_keys,
            f"查询：store.tracks_acceleration({years})，返回每个 curated 赛道的本期/上期记录数、变化率与季度 z 分数；"
            "“判断”列把观察到的计数变化与统计探测信号分开。"
            + (f" {_window_approximation_note(years)}" if approximated else ""),
            [
                "统计探测只说明记录数偏离历史基线，不证明存在真实技术变化，也不是预测。",
                "不同数据源的历史起点不同，跨期总量上升可能部分来自数据覆盖扩大。",
            ],
        )
    )
    evidence_items: list[dict[str, Any]] = []
    for row in ranked[:2]:
        evidence_items.extend(
            store.evidence_search(
                track=str(row["track"]),
                metric=metric,
                start=window["start"],
                end=window["end"],
                limit=3,
            )["items"]
        )

    def why(item: Mapping[str, Any]) -> str:
        return (
            f"该记录（{item.get('event_date') or '未知日期'}，{item.get('track_name_zh') or ''}）"
            f"是本期{_metric_phrase(metric)}，用于支撑加速表中该赛道的记录计数。"
        )

    evidence = _event_evidence(evidence_items, why)
    followups = [
        "换成近 5 年的窗口再看一次",
        f"查看{top['name_zh']}赛道的企业构成",
        "查看有统计信号赛道的记录明细",
    ]
    computation_zh = (
        f"解析为赛道加速扫描，时间窗近 {years} 年，指标 {metric}。"
        f"主查询：store.tracks_acceleration({years}) 对 curated 赛道比较本期与紧邻等长历史窗口的审批记录数，"
        "并用完整季度的 z 分数给出统计探测信号；证据来自变化率最高赛道的 store.evidence_search。"
        "结果只描述已观察到的变化与探测信号，不构成预测。"
    )
    return _response(question, "answered", "track_acceleration", parsed, answer, sections, evidence, limitations, followups, computation_zh)


# -------------------------------------------------- company_overview implementation
def _claim_evidence_items(
    key: str,
    claim: Mapping[str, Any],
    limit: int = 2,
) -> list[dict[str, Any]]:
    params = claim["evidence_params"]
    recent = store.evidence_search(
        companies=(key,),
        track=str(params["track"]),
        metric=str(params["metric"]),
        start=str(params["recent_start"]),
        end=str(params["recent_end"]),
        limit=limit,
    )["items"]
    if recent:
        return recent
    return store.evidence_search(
        companies=(key,),
        track=str(params["track"]),
        metric=str(params["metric"]),
        start=str(params["prior_start"]),
        end=str(params["prior_end"]),
        limit=limit,
    )["items"]


def _intent_company_overview(question: str, parsed: Mapping[str, Any]) -> dict[str, Any]:
    company = parsed["companies"][0]
    key = str(company["key"])
    name = str(company["name_zh"])
    years, approximated = _rolling_years(parsed)
    profile = store.company_profile(key, years)
    window = dict(profile["window"])
    headline = profile["headline"]
    track_rows = list(profile["tracks"]["rows"])
    claims = list(profile["claims"])[:3]
    milestones = list(profile["milestones"])
    limitation_keys = list(_BASE_LIMITATIONS) + ["coverage_change"] + _entity_limitations([key])
    limitations = _limitation_texts(limitation_keys)

    if claims:
        conclusion = claims[0]["statement_zh"]
    else:
        conclusion = (
            f"{name}在近 {years} 年的公开审批记录为 {headline['approvals_window']} 条，"
            f"上期 {headline['approvals_prior']} 条（{_fmt_pct(headline['pct_change'])}），"
            "窗口内没有满足保守规则的赛道级结论，这里只展示企业级汇总。"
        )
    conclusion += (
        f" 企业公开记录覆盖 {headline['tracks_active']} 条技术赛道，"
        f"全部历史审批记录 {headline['approvals_all_time']} 条，首条记录 {headline['first_event'] or '未知'}。"
        " 以上为记录条数的描述性汇总，不是经营表现或未来预测。"
    )

    data_rows = [
        ["全部事件记录", str(headline["events_all_time"])],
        ["全部 510(k)+PMA 记录", str(headline["approvals_all_time"])],
        [f"近 {years} 年审批记录", str(headline["approvals_window"])],
        ["上期审批记录", str(headline["approvals_prior"])],
        ["变化", _fmt_delta_pct(headline["delta"], headline["pct_change"])],
        ["覆盖技术赛道数", str(headline["tracks_active"])],
        ["全部 PMA 记录", str((headline.get("pathway_mix_counts") or {}).get("pma", "0"))],
        ["全部 510(k) 记录", str((headline.get("pathway_mix_counts") or {}).get("510k", "0"))],
        ["首条记录日期", str(headline["first_event"] or "—")],
        ["最新记录日期", str(headline["last_event"] or "—")],
    ]
    sections = [
        _section("结论", conclusion),
        _section(
            "数据",
            f"企业画像统计窗口 {window['start']} 至 {window['end']}；指标为公开审批记录（510(k)+PMA 条数）。",
            columns=["指标", "数值"],
            rows=data_rows,
        ),
    ]
    if track_rows:
        track_table_rows: list[list[str]] = []
        for row in sorted(track_rows, key=lambda item: -int(item["recent"]))[:5]:
            track_table_rows.append(
                [
                    str(row.get("name_zh") or row.get("track")),
                    str(row["recent"]),
                    str(row["prior"]),
                    _fmt_delta_pct(row["recent"] - row["prior"], row.get("pct_change")),
                    str(row.get("industry_recent") or 0),
                    str(row.get("first_approval") or "—"),
                ]
            )
        sections.append(
            _section(
                "主要赛道",
                "按本期公开审批记录数排序的前 5 条赛道；全行业列为同一窗口该赛道的全部企业记录数。",
                columns=["赛道", "本期", "上期", "变化", "全行业本期", "首次进入"],
                rows=track_table_rows,
            )
        )
    if milestones:
        milestone_bullets = [
            f"{milestone.get('label_zh') or '里程碑'}：{milestone.get('event_date') or '未知日期'}"
            + (f"（{milestone.get('track_name_zh')}）" if milestone.get("track_name_zh") and milestone.get("track_name_zh") != "未映射赛道" else "")
            for milestone in milestones[:6]
        ]
        sections.append(_section("里程碑", "来自企业公开记录的首次事件；逐条可在证据浏览器核对。", bullets=milestone_bullets))
    sections.extend(
        _method_limitation_sections(
            limitation_keys,
            f"查询：store.company_profile('{key}', {years})，返回企业级 headline、赛道表、claims、里程碑与来源覆盖；"
            "结论句优先引用其 claims 的确定性陈述。"
            + (f" {_window_approximation_note(years)}" if approximated else ""),
            [f"数据来源覆盖：{row.get('label_zh')}（{row.get('coverage_zh')}）" for row in profile.get("coverage") or []][:4],
        )
    )

    evidence_items: list[dict[str, Any]] = []
    for claim in claims:
        evidence_items.extend(_claim_evidence_items(key, claim))
    for milestone in milestones[:3]:
        if milestone.get("event_id"):
            evidence_items.append(dict(milestone))
    if not evidence_items:
        evidence_items.extend(list(profile.get("recent_events") or [])[:6])

    def why(item: Mapping[str, Any]) -> str:
        if item.get("kind") == "track_first" or item.get("derived"):
            return f"该条为企业里程碑“{item.get('label_zh')}”（{item.get('event_date')}）的派生记录。"
        return (
            f"该记录（{item.get('event_date') or '未知日期'}，{KIND_LABELS.get(str(item.get('kind')), item.get('kind') or '公开记录')}）"
            f"是{name}的公开记录，用于支撑企业画像中的赛道/里程碑陈述。"
        )

    evidence = _event_evidence(evidence_items, why)
    top_track = str(track_rows[0].get("name_zh") or "") if track_rows else "主要"
    followups = [
        f"只看{name}在{top_track}赛道的趋势",
        f"对比{name}与其他重点企业",
        f"查看{name}最近一年的公开记录",
    ]
    computation_zh = (
        f"解析出企业 {name}（{key}），时间窗近 {years} 年。主查询：store.company_profile('{key}', {years})，"
        "headline/赛道表/claims/里程碑均来自该调用的返回字段；证据来自 claims 对应窗口的 store.evidence_search"
        "及带 event_id 的里程碑记录。不对企业做跨企业排名，也不推断经营表现。"
    )
    return _response(question, "answered", "company_overview", parsed, answer_zh=conclusion, sections=sections, evidence=evidence, limitations=limitations, followups=followups, computation_zh=computation_zh)


# ---------------------------------------------------- evidence_lookup implementation
def _intent_evidence_lookup(question: str, parsed: Mapping[str, Any]) -> dict[str, Any]:
    companies = [str(item["key"]) for item in parsed["companies"]]
    scopes = _clamp_scopes(parsed, limit=3)
    track_ids = [track for scope in scopes for track in _scope_track_ids(scope)]
    metric = str(parsed["metric"] or "approvals")
    metric_label = catalog.METRICS[metric]["label_zh"]
    explicit_window = str(parsed["time"]["kind"]) in ("range", "since", "year", "years")
    if explicit_window:
        start, end = parsed["window"]["start"], parsed["window"]["end"]
        window_text = f"{start} 至 {end}"
    else:
        start, end = None, None
        window_text = "全部历史（未限定时间窗）"
    latest = bool(parsed.get("latest"))

    def query(metric_filter: str | None, limit: int = EVIDENCE_LIMIT) -> dict[str, Any]:
        return store.evidence_search(
            companies=tuple(companies),
            track=None,
            metric=metric_filter,
            start=start,
            end=end,
            limit=limit,
        )

    if track_ids:
        items: list[dict[str, Any]] = []
        total = 0
        for track_id in track_ids:
            result = store.evidence_search(
                companies=tuple(companies),
                track=track_id,
                metric=metric,
                start=start,
                end=end,
                limit=EVIDENCE_LIMIT,
            )
            total += int(result["total"])
            items.extend(result["items"])
        items.sort(key=lambda item: (item.get("event_date") or "", item.get("event_id") or ""), reverse=True)
    else:
        result = query(metric)
        total = int(result["total"])
        items = list(result["items"])

    limitation_keys = list(_BASE_LIMITATIONS) + (["recall_not_tech"] if metric == "recalls" else []) + _entity_limitations(companies)
    limitations = _limitation_texts(limitation_keys)
    scope_text = "、".join(_scope_label(scope) for scope in scopes) if scopes else "全部赛道"
    window_clause = f"在 {window_text} 内" if explicit_window else "在全部历史记录中"
    scope_clause = f"{scope_text}范围内"
    if total == 0:
        fallback_items: list[dict[str, Any]] = []
        fallback_total = 0
        if track_ids:
            for track_id in track_ids:
                result = store.evidence_search(
                    companies=tuple(companies),
                    track=track_id,
                    metric=None,
                    start=start,
                    end=end,
                    limit=12,
                )
                fallback_total += int(result["total"])
                fallback_items.extend(result["items"])
        else:
            result = store.evidence_search(companies=tuple(companies), metric=None, start=start, end=end, limit=12)
            fallback_total = int(result["total"])
            fallback_items = list(result["items"])
        fallback_items.sort(key=lambda item: (item.get("event_date") or "", item.get("event_id") or ""), reverse=True)
        if fallback_total:
            kinds_text = _kind_counts_text(fallback_items) if fallback_total <= len(fallback_items) else ""
            answer = (
                f"现有证据不足以作出该判断：{window_clause}、{scope_clause}、{metric_label}条件下没有检索到任何记录。"
                f"同一时间窗与该赛道内另有 {fallback_total} 条其他类型的公开记录"
                + (f"（{kinds_text}）" if kinds_text else "")
                + f"；这些记录不属于{metric_label}指标，只用于说明该切片并非没有数据，不构成{metric_label}结论。"
            )
            data_rows = [
                [
                    str(item.get("event_date") or ""),
                    KIND_LABELS.get(str(item.get("kind")), str(item.get("kind") or "")),
                    str(item.get("company_name_zh") or ""),
                    str(item.get("track_name_zh") or ""),
                    str(item.get("title") or "无标题记录").replace("\n", " ").replace("\r", " ")[:60],
                ]
                for item in fallback_items[:EVIDENCE_LIMIT]
            ]
            sections = [
                _section("结论", answer),
                _section(
                    "数据",
                    f"时间窗 {window_text}；企业 {companies or ['全部']}；赛道 {scope_text}；"
                    f"目标指标 {metric_label}：0 条。下表为同一时间窗/赛道的其他类型记录（非{metric_label}）。",
                    columns=["日期", "类型", "企业", "赛道", "标题"],
                    rows=data_rows,
                ),
            ]
            fallback_keys = list(limitation_keys)
            if any(item.get("kind") == "device_recall" for item in fallback_items):
                fallback_keys.append("recall_not_tech")
            fallback_texts = _limitation_texts(fallback_keys)
            sections.extend(
                _method_limitation_sections(
                    fallback_keys,
                    f"查询：store.evidence_search(companies={tuple(companies)}, track={track_ids or None}, "
                    f"metric='{metric}', start={start!r}, end={end!r})，目标指标命中 0 条；"
                    "随后用 metric=None 复合同一过滤条件，取得该切片的其他类型记录。",
                    ["目标指标为 0 时，产品不会用其他类型记录替代结论。"],
                )
            )

            def fallback_why(item: Mapping[str, Any]) -> str:
                return (
                    f"该记录类型为{KIND_LABELS.get(str(item.get('kind')), item.get('kind') or '其他')}，"
                    f"不属于所问的{metric_label}指标；仅用于说明该时间窗/赛道并非没有数据。"
                )

            return _response(
                question,
                "answered",
                "evidence_lookup",
                parsed,
                answer,
                sections,
                _event_evidence(fallback_items, fallback_why),
                fallback_texts,
                ["去掉赛道限制，查看该企业全部记录", "换一个时间窗再查一次", "改查召回或临床试验等指标"],
                f"目标查询命中 0 条；改用 metric=None 复合同一过滤条件取得其他类型记录，并在回答中明确区分指标口径。",
            )
        answer = (
            f"现有证据不足以作出该判断：{window_clause}、{scope_clause}、{metric_label}条件下没有检索到任何记录，"
            "数据库中没有可用于回答该问题的证据。可以放宽时间窗、去掉赛道限制，或改查召回/临床试验等指标。"
        )
        sections = [
            _section("结论", answer),
            _section("数据", f"时间窗 {window_text}；企业 {companies or ['全部']}；赛道 {scope_text}；指标 {metric_label}：0 条。", columns=["指标", "数值"], rows=[["命中记录数", "0"]]),
        ]
        sections.extend(
            _method_limitation_sections(
                limitation_keys,
                f"查询：store.evidence_search(companies={tuple(companies)}, track={track_ids or None}, "
                f"metric='{metric}', start={start!r}, end={end!r})，返回 total=0。",
            )
        )
        return _response(
            question,
            "answered",
            "evidence_lookup",
            parsed,
            answer,
            sections,
            [],
            limitations,
            ["换成近 10 年再看一次", "去掉赛道限制再查一次", "改查召回或临床试验等指标"],
            "目标切片查询命中 0 条记录，因此返回空证据而不是任何推断。",
        )

    latest_item = items[0] if items else None
    if latest_item:
        answer = (
            f"{window_clause}、{scope_clause}，共检索到 {_counted(total, metric)}。"
            + (
                f"最近一次是 {latest_item.get('event_date')} 的《{latest_item.get('title') or '无标题记录'}》"
                f"（{latest_item.get('company_name_zh') or '未映射企业'}，{latest_item.get('track_name_zh') or '未映射赛道'}）。"
                if latest
                else f"最新一条是 {latest_item.get('event_date')} 的《{latest_item.get('title') or '无标题记录'}》。"
            )
            + " 下表按事件日期倒序列出前几条原始记录，均可在证据浏览器逐条核对。"
        )
    else:  # pragma: no cover - defensive
        answer = f"{window_clause}、{scope_clause}检索到 {_counted(total, metric)}。"

    data_rows = [
        [
            str(item.get("event_date") or ""),
            KIND_LABELS.get(str(item.get("kind")), str(item.get("kind") or "")),
            str(item.get("company_name_zh") or ""),
            str(item.get("track_name_zh") or ""),
            str(item.get("title") or "无标题记录").replace("\n", " ").replace("\r", " ")[:60],
        ]
        for item in items[:EVIDENCE_LIMIT]
    ]
    sections = [
        _section("结论", answer),
        _section(
            "数据",
            f"时间窗 {window_text}；企业 {companies or ['全部']}；赛道 {scope_text}；指标 {metric_label}。"
            f"共 {total} 条，下表展示最近 {len(data_rows)} 条。",
            columns=["日期", "类型", "企业", "赛道", "标题"],
            rows=data_rows,
        ),
        _section(
            "方法与口径",
            f"查询：store.evidence_search(companies={tuple(companies)}, track={track_ids or None}, metric='{metric}', "
            f"start={start!r}, end={end!r}, limit={EVIDENCE_LIMIT})；结果按事件日期倒序。"
            f"{metric_label}只统计对应 kind 的公开记录条数，一条记录不等于一个产品。",
            bullets=list(catalog.METRICS[metric].get("caveats") or []),
        ),
        _section("局限", "以下数据口径限制适用于本回答：", bullets=limitations),
    ]

    def why(item: Mapping[str, Any]) -> str:
        return (
            f"该记录（{item.get('event_date') or '未知日期'}，{KIND_LABELS.get(str(item.get('kind')), item.get('kind') or '公开记录')}）"
            f"是本次查询命中的原始记录，用于支撑“共 {total} 条”的计数与上方明细。"
        )

    followups = [
        "把时间范围缩小到最近一年",
        "只看 PMA 或 510(k) 中的一种",
        "打开证据浏览器查看完整记录",
    ]
    computation_zh = (
        f"解析出企业 {companies or ['全部']}、赛道 {scope_text}、指标 {metric}、时间窗 {window_text}。"
        f"主查询：store.evidence_search（company/track/metric/start/end 过滤，按日期倒序）返回 total 与 items；"
        "证据列表与数据表均直接来自该查询的 event_id 与字段。目标指标 0 条时改为同条件 metric=None 复合并明确标注非目标指标。"
    )
    return _response(question, "answered", "evidence_lookup", parsed, answer, sections, _event_evidence(items, why), limitations, followups, computation_zh)


# --------------------------------------------------------- clarification / scope
def _clarification_response(question: str, parsed: Mapping[str, Any]) -> dict[str, Any]:
    options = [
        catalog.ANALYST_EXAMPLES[0],
        catalog.ANALYST_EXAMPLES[1],
        catalog.ANALYST_EXAMPLES[4],
        catalog.ANALYST_EXAMPLES[5],
    ]
    answer = (
        "我还没有从问题中识别到可以分析的企业或技术赛道，因此无法执行确定性查询。"
        "请补充企业名称（如美敦力、GE 医疗、飞利浦、德尔格、迈瑞）或技术赛道"
        "（如患者监护、医学影像、超声、呼吸、体外诊断、医疗 AI、心血管、外科），"
        "也可以直接选择一个示例问题。"
    )
    sections = [
        _section("结论", answer),
        _section(
            "数据",
            "未执行数据查询：问题中没有可解析的企业或技术赛道。下表是本次解析命中的实体数量（不是数据库计数）。",
            columns=["解析项", "命中数量"],
            rows=[["企业", "0"], ["技术赛道", "0"], ["时间窗", "未指定"]],
        ),
        _section("可以点击的问题", "下面任一问题都能被确定性引擎直接回答：", bullets=options),
        _section(
            "方法与口径",
            "本助手把问题解析为企业、技术赛道、时间窗与指标四类结构化要素，再查询数据库；"
            "缺少企业或赛道时不会猜测，而是返回可点击的示例选项。",
        ),
        _section("局限", "以下数据口径限制适用于本回答：", bullets=_limitation_texts(["us_only", "track_mapping", "not_prediction"])),
    ]
    return _response(
        question,
        "needs_clarification",
        "needs_clarification",
        parsed,
        answer,
        sections,
        [],
        _limitation_texts(["us_only", "track_mapping", "not_prediction"]),
        options,
        "未识别到企业或赛道 → 返回 needs_clarification 与示例问题，不执行任何推断。",
    )


def _scope_response(question: str, parsed: Mapping[str, Any], violations: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    reasons = "、".join(item["reason_zh"] for item in violations)
    answer = (
        f"这个问题超出了当前数据的可回答范围：{reasons}。"
        "本产品只基于公开记录（美国 FDA 510(k)/PMA/召回、ClinicalTrials.gov 注册、SEC 8-K 语料）做描述性检索，"
        "数据库中没有企业内部经营数据、全球注册数据或经过验证的因果/预测模型，因此不能给出该问题的答案。"
        "我可以回答企业×赛道的公开活动趋势、多企业横向比较、赛道加速扫描与逐条证据检索。"
    )
    can_answer = list(catalog.ANALYST_CAPABILITIES["can_zh"])[:4]
    cannot_answer = list(catalog.ANALYST_CAPABILITIES["cannot_zh"])
    sections = [
        _section("结论", answer),
        _section(
            "数据",
            "未执行数据查询：该问题需要的字段（内部经营、市场规模、全球注册、因果或前瞻信息）在当前数据库中不存在。"
            "本回答不包含任何由数据生成的数字。",
            columns=["数据边界", "当前状态"],
            rows=[["美国 FDA 公开记录", "可用"], ["企业内部经营数据", "无"], ["全球监管数据", "无"], ["经过验证的预测模型", "无"]],
        ),
        _section("我能回答什么", "下面这些类型的问题可以直接回答：", bullets=can_answer),
        _section(
            "方法与口径",
            "本助手是确定性证据检索引擎：只有一个只读数据库（美国 FDA 公开记录 + 部分全球试验注册）与固定的统计规则，"
            "没有大模型、没有内部数据、没有预测模型。回答只描述已观察到的记录与统计探测信号。",
            bullets=cannot_answer,
        ),
        _section("局限", "以下数据口径限制适用于本回答：", bullets=_limitation_texts(["us_only", "no_global_rank", "not_prediction"])),
    ]
    options = [
        catalog.ANALYST_EXAMPLES[0],
        catalog.ANALYST_EXAMPLES[1],
        catalog.ANALYST_EXAMPLES[2],
        catalog.ANALYST_EXAMPLES[7],
    ]
    return _response(
        question,
        "out_of_scope",
        "out_of_scope",
        parsed,
        answer,
        sections,
        [],
        _limitation_texts(["us_only", "no_global_rank", "not_prediction"]),
        options,
        "命中数据边界规则（" + reasons + "）→ 返回 out_of_scope 与可回答方向，不编造数据。",
    )


def _scope_violations(norm_lower: str, parsed: Mapping[str, Any]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    matched_codes: set[str] = set()
    for code, reason, pattern in _SCOPE_RULES:
        if pattern.search(norm_lower) and code not in matched_codes:
            matched_codes.add(code)
            violations.append({"code": code, "reason_zh": reason})
    if str(parsed["time"]["kind"]) in ("range", "since", "year"):
        edge_year = int(str(parsed["window"]["data_edge"])[:4])
        requested = int(str(parsed["window"]["end"])[:4])
        if requested > edge_year and "prediction" not in matched_codes:
            violations.append({"code": "prediction", "reason_zh": "超出数据截止日的未来年份"})
    return violations


# -------------------------------------------------------------------- dispatch
def _select_intent(parsed: Mapping[str, Any]) -> str:
    companies = parsed["companies"]
    tracks = parsed["tracks"]
    if not companies and not tracks:
        if parsed["acceleration"]:
            return "track_acceleration"
        return "needs_clarification"
    if len(companies) >= 2:
        return "company_compare"
    if parsed["record_lookup"]:
        return "evidence_lookup"
    if parsed["acceleration"]:
        return "track_acceleration"
    if not companies:
        return "track_company_leaders"
    if tracks:
        return "company_track_trend"
    return "company_overview"


def parse_question(question: str) -> dict[str, Any]:
    """Parse a question into the structured intent payload (no store query)."""
    text = str(question or "").strip()
    if not text:
        raise ValueError("question is required")
    return _build_parsed(text)


def answer(question: str) -> dict[str, Any]:
    """Answer one question deterministically, following the web contract."""
    text = str(question or "").strip()
    if not text:
        raise ValueError("question is required")
    if len(text) > MAX_QUESTION:
        raise ValueError(f"question is too long (max {MAX_QUESTION} characters)")

    parsed = _build_parsed(text)
    norm_lower = _normalize(text)[0].lower()
    violations = _scope_violations(norm_lower, parsed)
    if violations:
        return _scope_response(text, parsed, violations)

    intent_type = _select_intent(parsed)
    if intent_type == "needs_clarification":
        return _clarification_response(text, parsed)
    try:
        if intent_type == "company_track_trend":
            return _intent_company_track_trend(text, parsed)
        if intent_type == "company_compare":
            return _intent_company_compare(text, parsed)
        if intent_type == "track_company_leaders":
            return _intent_track_company_leaders(text, parsed)
        if intent_type == "track_acceleration":
            return _intent_track_acceleration(text, parsed)
        if intent_type == "company_overview":
            return _intent_company_overview(text, parsed)
        if intent_type == "evidence_lookup":
            return _intent_evidence_lookup(text, parsed)
    except KeyError as error:  # unknown company/track from the store roster
        return _clarification_response(text, parsed) | {
            "answer_zh": f"查询所需的企业或赛道不在当前数据名册中（{error}），请换一个示例问题。"
        }
    # pragma: no cover - defensive: all intents are dispatched above
    return _clarification_response(text, parsed)


__all__ = ["MODE", "MODE_ZH", "INTENT_LABELS", "answer", "parse_question"]
