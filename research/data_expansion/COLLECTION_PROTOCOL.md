# DATA-EXPANSION-001 · 采集协议（所有 Agent 必须遵守）

> 本文件是并行工作的**唯一契约**。开工前完整读一遍；与任何记忆或习惯冲突时，以本文件为准。
> Lead 负责最终合并、复核、提交与 Draft PR。**Agent 不得执行任何 git 命令。**

---

## 0. 工作目录与边界

| 项 | 值 |
|---|---|
| 唯一工作区 | `D:\DEPPSKK\worktrees\data-expansion-001` |
| 分支 | `research/data-expansion-001`（已从 `origin/main` = `b2a14c0` 建立） |
| Python | `python`（3.12，PATH 中） |

**绝对禁止：**

1. 进入或修改 `D:\DEPPSKK\medradar`（那是另一分支的检出，含未提交改动）。
2. 修改 `research/studies/`、`research/RESULTS/`、`experiments/`、`papers/`、`data/` 下任何既有文件。
3. 修改 PHOENIX-001/002/003 的任何协议、结果、数据。
4. 修改既有 `medradar/*.py`（`external_sources/` 之外）。若确实需要，先在 handoff 里提出，由 Lead 决定。
5. 执行 `git` 命令（add/commit/push/branch/checkout 全部不行）。
6. 覆盖 `data/medradar.sqlite` 或任何既有数据库。
7. 付费、注册账号、使用任何凭据/API key。
8. 绕过登录、验证码、WAF、robots 限制，或使用代理。
9. 大规模抓取：单来源单次 probe **≤ 20 个请求**，单次响应体 **≤ 8 MB**。
10. 把伪造/示例/记忆中的数据当作真实获取结果提交。

**允许：** 读官方文档网页、读仓库代码、运行 probe、写自己 scope 内的文件、跑本地测试。

---

## 1. 你会用到的既有基础设施（先读，再写）

| 模块 | 作用 | 关键 API |
|---|---|---|
| `medradar/external_sources/schema.py` | 证据记录 v1 契约 | `make_evidence(...)`、`validate_evidence(rec)`、`build_identifier(...)`、`canonical_key` |
| `medradar/external_sources/base.py` | 有界 HTTP + probe 运行器 | `run_probe(...)`、`HttpClient.get(...)`、`write_sample(...)`、`json_shape(...)`、`PROBE_STATUSES` |
| `medradar/external_sources/store.py` | 隔离 staging SQLite | `StagingStore(path)`、`upsert_evidence(rec)`、`put_raw(...)`、`stats()` |
| `medradar/external_sources/identity.py` | 企业/产品身份 | `CompanyIndex.from_config().resolve(name)`、`build_identifier`、`normalize_*` |
| `medradar/external_sources/timeq.py` | 四时钟语义 | `build_time(...)`、`lead_time_days(...)`、`implied_quality(...)` |
| `medradar/external_sources/registry.py` | 注册表合并 | `load_source_records`、`build_register` |

已通过 36 个离线单测（`tests/test_external_sources_foundation.py`）和完整 `python -m medradar selftest`（1110 通过）。**不要修改这 5 个文件**；需要新能力就写在自己的子包里。

---

## 2. 写入范围（写错文件 = 冲突）

每位 Agent 只写下面列出的路径。**其它任何路径都不要写。**

```
research/data_expansion/registry/sources/<source_id>.json      # 你的 source_id 之一
research/data_expansion/probes/<source_id>/**                   # 你的 source_id 之一
research/data_expansion/samples/<source_id>/**                  # 你的 source_id 之一
research/data_expansion/handoffs/<agent>.json                   # 你的交接文件
medradar/external_sources/<你的子包>/**                          # 连接器代码
tests/test_extsrc_<你的子包>.py                                  # 你的离线测试（单文件）
```

子包与交付：

| Agent | 子包 | source_id（见 `registry/SOURCE_ID_INDEX.json` 的 `owner` 字段） |
|---|---|---|
| `regulatory` | `external_sources/regulatory/` | owner = `regulatory` |
| `scholarly` | `external_sources/scholarly/` | owner = `scholarly` |
| `patents` | `external_sources/trade/`（含专利与贸易） | owner = `patents` |
| `procurement` | `external_sources/procurement/`（含采购/资助/招聘） | owner = `procurement` |

---

## 3. 每个数据源必须完成的四件事

### 3.1 probe（真实访问测试）

在 `research/data_expansion/probes/<source_id>/` 下产出：

- `requests.jsonl` — 由 `HttpClient` 自动写，**每一次请求（含失败）**都在里面；
- `PROBE_RESULT.json` — 由 `run_probe` 自动写出；
- `NOTES.md` — 人读说明：测了什么、结论、文档链接。

写法（唯一允许的方式）：

```python
from pathlib import Path
from medradar.external_sources import base

ROOT = Path(r"D:\DEPPSKK\worktrees\data-expansion-001\research\data_expansion")

def probe(client, directory):
    probes = []
    r = client.get("https://api.example.org/search", params={"q": "stent", "limit": 2})
    probes.append({
        "name": "search_smoke",
        "url": r.url,
        "status": r.status,
        "ok": r.ok,
        "bytes": len(r.body),
        "elapsed_ms": r.elapsed_ms,
        "error": r.error,
        "structure": base.json_shape(r.json()) if r.ok else None,
        "sample": base.write_sample(directory / "samples", "search.json", r.body) if r.ok else None,
    })
    status = "VERIFIED_API" if any(p["ok"] for p in probes) else "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id="<source_id>",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p["ok"]],
        notes="一句话结论",
    )

outcome = base.run_probe("<source_id>", ROOT, probe, budget=12, min_interval=1.0)
```

规则：
- `budget` 建议 6–15；`min_interval` ≥ 0.6s（多数官方 API 允许更快，但礼貌优先）。
- 401/403 且文档显示需要 key → `REQUIRES_REGISTRATION`；402/价格页 → `PAID_ONLY`；
  robots/ToS 明确禁止 → `BLOCKED_BY_POLICY`；文档说没有机器接口且页面无法解析 → `UNAVAILABLE`。
- **不能**因为“浏览器能打开”就写 `VERIFIED_*`。必须有程序请求返回 2xx + 真实记录。
- 失败也要留证：`requests.jsonl` 里的错误行 + NOTES 说明。

### 3.2 sample（真实样本）

`research/data_expansion/samples/<source_id>/` 下保存**真实**响应切片：

- 用 `base.write_sample(...)`，单文件 ≤ 512 KB（超出自动截断并在描述里标注 `truncated: true`）；
- 附 `SAMPLES.json`：每个文件的 `sha256_full`、`total_bytes`、`stored_bytes`、请求 URL、抓取时间；
- 样本必须来自真实响应，**不可手工编写**。

### 3.3 connector（可复用连接器）

只有 `VERIFIED_API` / `VERIFIED_BULK_DOWNLOAD` / `VERIFIED_PUBLIC_QUERY` 的来源才写连接器。

放置：`medradar/external_sources/<子包>/<source_id>.py`

每个连接器必须提供：

```python
SOURCE_ID = "openalex"
KIND = "publication"          # schema.EVIDENCE_KINDS 之一
LICENCE_STATUS = "open_licence"

def collect(client, *, limit: int = 50) -> list[dict]:
    """取回 ≤ limit 条真实记录并返回 schema.make_evidence(...) 列表。"""

def to_evidence(raw_item, *, fetched_at) -> dict:
    """单条原始记录 -> 证据记录。"""
```

硬性要求：
- 只用 `client.get(...)`（有界、有日志），不直接用 `requests`/`urllib`；
- 分页有上限（`limit` / `max_pages`），不得无界循环；
- 无状态、可重跑、幂等（同一 `source_record_id` 得到同一 `evidence_id`）；
- 时间字段必须走 `timeq.build_time`：`event_at`（事件发生日）与 `source_public_at`（**首次公开可见日**）分开；
- 单位/字段缺失写 `null`，**不猜**；
- 企业匹配只用 `identity.CompanyIndex.resolve(...)`，`candidate` 不得升级为确认。

### 3.4 register record（文档层记录）

`research/data_expansion/registry/sources/<source_id>.json`，**严格**使用下列字段（缺一不可，
未知写 `"UNKNOWN"`）：

```json
{
  "source_id": "openalex",
  "source_name": "OpenAlex",
  "official_url": "https://docs.openalex.org/",
  "country_or_region": "GLOBAL",
  "domain": "C",
  "category": "scholarly_literature",
  "official_or_commercial": "official",
  "api_available": "YES",
  "bulk_download_available": "PARTIAL",
  "authentication": "none",
  "free_tier": "free, no key required; polite pool via mailto",
  "rate_limits": "10 req/s, 100k/day (documented)",
  "licence": "CC0 1.0 (data), API terms of use",
  "redistribution_allowed": "YES",
  "update_frequency": "daily",
  "historical_coverage": "works from 1800s; entity disambiguation improves after 2000",
  "entity_identifiers": ["OpenAlex ID", "ORCID", "ROR", "DOI", "ISSN"],
  "timestamp_fields": ["publication_date", "created_date", "updated_date"],
  "known_limitations": ["no point-in-time snapshot: created_date is not a knowledge clock"],
  "connection_status": "NOT_TESTED",
  "research_value": "为什么对 MedRadar 有用，2-3 句，写清能补哪个缺口",
  "evidence_urls": ["https://docs.openalex.org/"],
  "verified_at": "2026-11-09",
  "cost_notes": "免费；商业 SLA 不提供",
  "probe_priority": "P0"
}
```

- `api_available` / `bulk_download_available` / `redistribution_allowed` 只能是
  `"YES" | "NO" | "PARTIAL" | "UNKNOWN"`。
- `connection_status` 只能写 `"NOT_TESTED"`（probe 结果由合并工具覆盖，**不要手写 VERIFIED_***）。
- `evidence_urls` 必须是**你实际打开过的官方文档/条款页**，不是搜索结果页。
- 所有判断都要有依据：`known_limitations` 里写清楚“为什么”。

---

## 4. 时间语义（本任务最容易出错的地方）

| 字段 | 含义 | 常见错误 |
|---|---|---|
| `event_at` | 事件发生日（批准日、授予日、发货日） | 用抓取日冒充 |
| `source_public_at` | **该记录首次对公众可见的日期** | 专利用申请日、论文用投稿日 |
| `first_observed_at` | MedRadar 第一次观测到它（= fetch 时钟） | 回填时伪造成历史观测 |
| `fetched_at` | 本次抓取时间 | — |

强制规则：

1. 专利：`source_public_at` = **公开日（publication date）**，不是申请日/优先权日。
2. 论文：`source_public_at` = 首次在线发表日期（`firstPublicationDate`/`published-online`），
   不是期刊期号日、不是 `created_date`。
3. 临床试验：`source_public_at` = `studyFirstPostDate`（首次登记公开日）。
4. 采购：`source_public_at` = 公告发布日；中标/合同另记 `event_at`。
5. 只有月/年精度时，`quality` 必须降为 `coarse`，并且不得用于提前量结论。
6. `first_observed_at` 一律等于 `fetched_at`（除非源本身提供了可验证的观测历史）。

**“申请日期 ≠ 公众可见日期”。** 把未公开的专利申请当作历史早期信号是本任务明令禁止的错误。

---

## 5. 身份关联规则

- 优先顺序：官方统一标识符 > 产品型号+制造商一致 > 公司注册关系 > 多字段联合 > 语义候选。
- 五家目标企业：**Medtronic、GE HealthCare、Philips、Dräger、Mindray**（别名表已内置）。
- `exact_alias` / `multi_field` / `official_id` 才算确认关联；`candidate` 必须单独统计。
- 若某来源无法按企业检索（例如只能按关键词），**如实写明无法关联五家企业**，
  并用独立样本验证接口；不得用关键词命中冒充企业关联。
- 聚合平台重复发布的同一条原始记录 = 1 条证据，不是 2 条。用 `canonical_key` 去重。

---

## 6. 代码质量与测试

- Python 3.10+ 语法，`from __future__ import annotations`，类型标注齐全。
- 网络代码只在被测函数里，**模块 import 不发起请求**。
- 每个子包至少一个 `tests/test_extsrc_<子包>.py`（`unittest`），覆盖：
  - 归一化函数（纯函数，无网络）；
  - `to_evidence` 用**内置的小样本 dict**（不是抓来的大文件）；
  - `validate_evidence(...)` 返回空列表；
  - 时间语义断言（`event_at` ≠ `source_public_at` 的关键案例）。
- 不允许测试依赖网络。跑 `python -m medradar selftest` 必须仍然全绿。
- 不要新增第三方依赖（只用标准库 + 仓库已用的 `requests` 之外的都不要加；
  连接器内部用 `client.get`，不直接依赖 `requests`）。

---

## 7. 交接文件（收尾必写）

`research/data_expansion/handoffs/<agent>.json`：

```json
{
  "agent": "regulatory",
  "finished_at": "2026-11-09T12:00:00Z",
  "sources_assigned": 22,
  "sources_probed": 18,
  "connection_status_counts": {"VERIFIED_API": 7, "REQUIRES_REGISTRATION": 3},
  "connectors": ["external_sources/regulatory/accessgudid.py"],
  "real_records_collected": 143,
  "blocked": [{"source_id": "...", "reason": "..."}],
  "notable_findings": ["一句话，实证的", "..."],
  "open_questions": ["..."],
  "tests": {"file": "tests/test_extsrc_regulatory.py", "passed": 12, "failed": 0},
  "selftest": "pass"
}
```

---

## 8. 完成判据（Definition of Done）

一个 source 算“完成”，当且仅当：

- [ ] `registry/sources/<id>.json` 存在且字段齐全、URL 真实；
- [ ] `probes/<id>/PROBE_RESULT.json` + `requests.jsonl` 存在（`NOT_TESTED` 的除外）；
- [ ] 若状态是 `VERIFIED_*`：有真实 sample + `SAMPLES.json` + 连接器 + 离线测试；
- [ ] 若失败：NOTES 写明阻断原因与可用的合法替代方案；
- [ ] 时间语义与身份关联符合第 4、5 节；
- [ ] 未越界写文件，未运行 git。

**负面结果同样是交付物。** 不要为了凑“已验证”数量而降低标准。
