# MedRadar 数据契约（Data Contract v1）

`medradar analyze` 把 SQLite 里的事实表算成 **一个 JSON 文件**（默认 `out/metrics.json`）。
下游的看板、中文报告、模拟交易全部只读这个文件 + 事件表，互不耦合。

> 规则：**任何字段的语义改动都必须先改这份文档再改代码**。这是四个人并行开发不打架的前提。

## 1. `out/metrics.json` 顶层

```jsonc
{
  "meta": {
    "generated_at": "2026-10-31T02:10:00Z",   // UTC ISO
    "db": "data/medradar.sqlite",
    "window":  {"start": "2024-11-01", "end": "2026-10-31", "quarters": 8},
    "baseline":{"start": "2021-11-01", "end": "2024-10-31", "quarters": 20},
    "counts": {...},                          // 事件表各 kind 的条数
    "data_status": {                          // 哪些数据源真的加载了
      "device": "ok", "drug": "ok", "trials": "ok",
      "nmpa": "unavailable|demo|loaded", "prices": "ok|partial|missing"
    },
    "request_stats": {"requests": 123, "cache_hits": 900}
  },
  "device": {...},
  "drug": {...},
  "cn_gap": [...],
  "signals": [...],
  "alerts": {...},
  "trading": {...}                            // 可选，只有跑 trade 时才有
}
```

## 2. `device`

```jsonc
{
  "tracks": [{
    "track_id": "ep_pfa",
    "name_zh": "电生理与脉冲场消融",
    "name_en": "Electrophysiology / PFA",
    "recent": 42,                 // 窗口内事件数
    "recent_per_q": 5.25,         // 每季度速率
    "baseline_per_q": 1.10,       // 基线每季度速率
    "thi": 4.8,                   // 热度指数 = 收缩后近期速率 / 基线速率
    "prob_up": 0.997,             // P(真实速率 > 基线速率)
    "ci": [3.1, 6.9],             // thi 的 95% 后验区间
    "major_share_recent": 0.55,   // 大厂在窗口内占比
    "major_share_base": 0.40,
    "new_entrants_12m": 7,        // 12个月内首次进入该赛道的公司数
    "recalls_recent": 1
  }],
  "companies": [{
    "key": "medtronic", "name_zh": "美敦力", "ticker": "MDT",
    "recent": 18, "recent_per_q": 2.25, "baseline_per_q": 2.05,
    "thi": 1.1, "prob_up": 0.58, "ci": [0.7, 1.5],
    "top_tracks": [["spine", 0.22], ["cardiac_rhythm", 0.18]],
    "novelty_12m": 3,             // 12个月内首次出现的产品码个数
    "recalls_recent": 2
  }],
  "migration": [{                 // 结构迁移，按 |delta| 降序
    "key": "intuitive_surgical", "name_zh": "直觉外科", "track_id": "surgical_robotics",
    "track_zh": "手术机器人", "share_recent": 0.35, "share_base": 0.12,
    "delta": 0.23, "js": 0.11
  }],
  "firstseen": [{                 // 首次出现清单（近 90 天）
    "event_date": "2026-10-20", "key": "medtronic", "name_zh": "美敦力",
    "track_id": "ep_pfa", "track_zh": "电生理与脉冲场消融",
    "product_code": "OAD", "device_name": "Pulsed Field Ablation System",
    "title": "…", "event_id": "…"
  }],
  "recalls": [{                   // 召回聚集
    "key": "philips", "name_zh": "飞利浦", "recent": 3,
    "baseline_per_q": 0.5, "reason_top": "Software"
  }]
}
```

## 3. `drug`

```jsonc
{
  "approvals": [{                 // NDA/BLA 原始批准
    "key": "lilly", "name_zh": "礼来", "ticker": "LLY",
    "recent": 5, "recent_per_q": 0.63, "baseline_per_q": 0.40,
    "thi": 1.6, "prob_up": 0.84, "nme_recent": 2
  }],
  "areas": [{ "track_id": "t_cardiometabolic", "name_zh": "心血管代谢（含GLP-1）",
              "recent": 31, "thi": 1.9, "prob_up": 0.95 }],
  "trials": [{                    // 试验启动
    "key": "lilly", "name_zh": "礼来",
    "starts_recent": 24, "recent_per_q": 3.0, "baseline_per_q": 2.1,
    "phase_mix": {"PHASE1": 0.4, "PHASE2": 0.3, "PHASE3": 0.3},
    "thi": 1.4
  }]
}
```

## 4. `cn_gap`（中国空白度）

美国某赛道近 24 个月事件数 vs 已加载的中国注册证数，按赛道对齐：

```jsonc
[{
  "track_id": "ep_pfa", "name_zh": "电生理与脉冲场消融",
  "us_recent": 42, "cn_count": 0,
  "us_share": 0.08, "cn_share": 0.00,
  "gap_index": 0.08,              // us_share - cn_share，>0 表示美国领先/国内空白
  "cn_data_status": "unavailable" // unavailable | demo | loaded
}]
```

**诚实原则**：没有中国数据时 `cn_count`/`cn_share` 为 `null`，`cn_data_status="unavailable"`，
报告里必须写明"中国空白度不可用（NMPA 数据未加载）"，**不允许**用 0 冒充真实空白。

## 5. `signals`（喂给模拟交易）

```jsonc
[{
  "signal_id": "9f2…",
  "event_id": "…",
  "signal_date": "2026-10-21",   // 最早可公开获知的日期（用于避免前视偏差）
  "company_key": "medtronic", "ticker": "MDT", "name_zh": "美敦力",
  "kind": "device_new_track|device_novel_code|drug_approval|trial_start|recall_cluster",
  "direction": 1,                 // +1 做多候选 / -1 做空候选
  "score": 0.72,                  // 0..1 置信度
  "track_id": "ep_pfa",
  "reason_zh": "首次进入脉冲场消融赛道"
}]
```

## 6. SQLite 事实表（采集层契约）

所有采集器只写 `events` 表，字段固定：

| 字段 | 说明 |
|---|---|
| `event_id` | 确定性哈希，重复采集幂等 |
| `source` | `openfda_device_510k` / `openfda_device_pma` / `openfda_device_recall` / `openfda_drug_drugsfda` / `ctgov` / `nmpa` |
| `kind` | `510k` / `pma` / `device_recall` / `drug_approval` / `trial` / `nmpa_registration` |
| `event_date` | **最早公开可获知日期**（决策日/批准日/试验首次登记日），用于避免前视偏差 |
| `as_of` | 该数据的采集日期（point-in-time 标记） |
| `company_key` | 由 `CompanyRegistry.resolve()` 得出，未匹配为 `NULL` |
| `applicant_raw` | 原始公司名（永远保留，方便人工复核漏检） |
| `track_id` | 由 `TrackRegistry` 得出 |
| `product_code` | 器械产品码；药品为 NULL |
| `title` / `summary` | 人读摘要（中文报告直接用） |
| `payload` | 原始 JSON（截断），用于复核 |

`kind` 取值同时决定 `signals` 生成规则，新增 kind 必须同步更新 §5。
