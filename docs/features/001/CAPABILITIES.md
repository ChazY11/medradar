# 能力补齐 / Watchlists, company pages, review, export, delivery, MCP

- 版本：`94c3c23`
- 来源：`docs/research/001/TOOL_CAPABILITY_SCAN.md` 里列出的缺口
- 原则：**证据与人的判断分开存**。账本（`radar.db`）永不被网页写入，人的决定存在 `human.db`

---

## 1. 数据放在哪

| 文件 | 内容 | 谁写 |
| --- | --- | --- |
| `radar.db` | 观测、版本、判定、来源状态（append-only） | 采集管线 |
| `graph.db` | 公司×技术图谱（双时态） | 物化器 |
| **`human.db`** | 关注清单、评审决定、评审事件、审计日志、投递记录 | 网页/CLI |

`human.db` 是**可修订**的：一条判定可以从"待处理"改到"已确认"，而且每次改动都进 `review_event` 与 `audit`。
证据账本保持不可写，所以"某条记录被谁改过"这种问题不会污染证据本身。

---

## 2. 关注清单（保存筛选）

在实时雷达页顶部：填个名字 → **保存当前筛选**。之后点任意清单即可一键恢复筛选，并显示它的实时条数。

- 保存的字段有白名单，未知键会被丢弃（防止把任意 SQL 塞进筛选里）
- 计数是对账本现算的，不是缓存的
- 所有增删改都进审计日志

`GET/POST /api/radar/watchlists`、`PATCH/DELETE /api/radar/watchlists/{id}`（`?counts=1` 返回计数）

---

## 3. 公司页

导航新增 **公司**：列出税则里的每家公司、记录数、召回数、最新时间。
点进去是**这家公司最近发生了什么**：档案、按来源分布、召回清单、最近记录、技术主题、产品。

`GET /api/radar/companies`、`GET /api/radar/company/{organization_id}`

---

## 4. 评审工作流

在任意记录的证据抽屉里：**待处理 / 看过了 / 已确认 / 已排除**，可加一句备注。
导航新增 **评审队列**：按状态筛选、直接改状态、以及**审计记录**（谁、什么时候、做了什么）。

- 状态只有四个。十二个状态的队列没人维护得下去
- 每次流转写一条 `review_event`（from → to、actor、时间）
- 判定**不会**改变情报流里记录的去留，它只记录人的结论

`GET/POST /api/radar/review/{observation_id}`、`GET /api/radar/review/queue`、`GET /api/radar/audit`

---

## 5. 导出

情报流顶部 **导出这些记录（CSV）**：带你当前筛选，含判定、分级、评分、评审状态与备注。

`GET /api/radar/export?format=csv|json&scope=&source=&organization=&topic=&q=&limit=`

---

## 6. 投递

把摘要发到人已经在用的地方：

```bash
# 只打印，不外发（默认）
python -m medradar radar digest --hours 24

# 发到 Slack/任意 webhook（POST {"text": ..., "digest": ...}）
python -m medradar radar digest --webhook https://hooks.slack.com/services/...

# 发邮件（密码走环境变量，不要写进命令行）
export MEDRADAR_SMTP_PASSWORD=...
python -m medradar radar digest --smtp-host smtp.example.com --smtp-from radar@example.com \
  --smtp-to you@example.com --smtp-user radar@example.com
```

- **dry run 是默认**：没有配置渠道就不会外发
- 每次尝试（成功/失败）都写进 `human.db` 的 `delivery` 表
- 投递失败返回非零退出码，不会被吞掉

定时器示例见 `docs/features/001/DELIVERY.md`。

---

## 7. MCP 入口

`python -m medradar.mcp_server --radar-dir /path/to/radar` 起一个**只读**的 MCP 服务，
五个工具：`radar_digest`、`radar_search`、`radar_record`、`radar_company`、`radar_sources`。
配置示例见 `docs/features/001/MCP.md`。

---

## 8. 测试

| 覆盖面 | 测试数 |
| --- | --- |
| 人工侧存储 + 接口 | 7 |
| MCP 协议与工具 | 5 |
| 投递（webhook 真发一次、失败记录、dry-run） | 6 |
| 今日摘要 | 5 |
| 全量 | **1,731 passed / 4 skipped / 0 failed** |
