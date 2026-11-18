# RELEASE-GATE-001 / 健康状态与监控

- 候选实现：`release-gate/001/health/radar_health.py`（三层探针）
- 候选单元：`docs/release_gate/001/units/medradar-radar-health.{service,timer}`（**未安装**）
- 结论：**三层监控已实现并在真实服务器上实测**；生产接入属于发布门禁项；**外部告警渠道未配置**，
  不声称具备主动告警能力。

---

## 1. 为什么不能只探 HTTP 200

现有 `/usr/local/bin/medradar-health` 每 5 分钟跑一次，但它只检查 `127.0.0.1:8787`（旧工作台）
的 `/api/health` 与 `/api/devices/quality`。**它完全不看雷达（8791）与调度器。**

也就是说：即使雷达的采集全线停止、召回通道从未采集过一条记录、水位线停在三个月前，
现有检查仍然全绿。这是本轮要把监控作为一个**发布门禁项**而不是"以后再说"的原因。

---

## 2. 三层设计

### 第一层：服务可用性（外部视角）

| 检查 | 方法 | 失败含义 |
| --- | --- | --- |
| `port` | `socket.create_connection(127.0.0.1:8791)` | 进程没了/没监听 |
| `healthz` | `GET /healthz`（免认证） | 监听在但不健康 |
| `api_health` / `api_feed` | `GET /api/radar/*` | 401 被**正确识别为"门禁保护"**而不是故障 |
| `spa_index` | `web/dist/index.html` 存在 | 前端产物缺失 |

关于 401：Alpha 门在回环上同样生效（设计如此）。探针把 401 记为"可达但需凭据"，
然后**直接读账本**来做第二、三层判断——不去要口令。

### 第二层：数据管线（产品自己的 `system_status`）

| 检查 | 回答的问题 | 失败严重度 |
| --- | --- | --- |
| `critical_sources` | 产品离不开的来源是否在被采集（失败≥3、从未检查、超过 3× cadence 未检查） | CRITICAL |
| `watermark_legal` | 水位线是否合法、是否有成功运行背书 | 核心来源 CRITICAL（超过宽限）/ MAJOR |
| `scheduler_heartbeat` | 调度器还活着吗 | CRITICAL |
| `acquirement_progress` | 采集是否在推进 | MINOR（**不降级**） |

设计要点：**"来源没有新记录"不是故障**。安静超过 12 个自身 cadence 只产生 MINOR 提示并点名来源；
真正判故障的是"没被检查""检查失败""调度器停了"。

### 第三层：产品可信度

| 检查 | 回答的问题 | 失败严重度 |
| --- | --- | --- |
| `ledger_integrity` | 历史是否自相矛盾 | CRITICAL |
| `ledger_writable` | 库还能写吗（读写句柄实测） | CRITICAL |
| `recall_channel` | 召回通道是否存在并有数据 | CRITICAL |
| `brief_generation` | 周报还能不能生成 | CRITICAL |

`recall_channel` 与 `brief_generation` 是探针在 `system_status` 之外**额外加的**，
所以整体判定必须**重新聚合**，不能直接沿用 `system_status` 的结论。
这一点本轮踩到了：第一版探针把这两项追加到列表里，却仍用产品的 `state` 作为总体结论，
结果**生产数据在"召回通道缺失"的情况下被判成 DEGRADED 而不是 UNHEALTHY**。
修正后的聚合逻辑：任何 CRITICAL 的 FAIL → UNHEALTHY。

---

## 3. 四态与触发条件

| 状态 | 触发条件 |
| --- | --- |
| **HEALTHY** | 第一层全部 ok；产品判定 HEALTHY；没有 CRITICAL/MAJOR 级告警 |
| **DEGRADED** | 有 FAIL（非 CRITICAL）、或有 MAJOR 级 WARN（例如 1 天以内的水位线领先）、或产品自身 DEGRADED |
| **UNHEALTHY** | 第一层任一失败；或任一 CRITICAL 检查 FAIL（库不可写、结构损坏、核心来源失败、召回通道缺失、周报生成失败、心跳超时） |
| **UNKNOWN** | 证据不足（从未成功检查、账本为空） |

退出码：HEALTHY/DEGRADED → 0；UNHEALTHY → 1；UNKNOWN → 2。
无论哪种，都会把 JSON 快照写到 `--state-file`，所以即使没人看 journal，**故障也是可观察的**。

---

## 4. 实测：生产数据现在是什么状态

用候选代码对**生产数据的迁移副本**做只读评估（生产库本身未被打开写入），
第一层则对着**正在运行的生产服务**（8791）：

```
STATE: UNHEALTHY
  avail    port            ok      127.0.0.1:8791
  avail    healthz         ok      200 in 37.0 ms
  avail    api_health      ok      401 (alpha gate protects the API; the ledger is read directly)
  avail    api_feed        ok      401 (alpha gate)
  avail    spa_index       ok      /srv/medradar/radar/app/web/dist/index.html
  pipeline critical_sources PASS   Every monitored source was checked inside its declared cadence.
  pipeline watermark_legal  WARN   A watermark leads the UTC date by 1 day(s), inside the 1-day grace …
  pipeline scheduler_heartbeat PASS
  pipeline acquisition_progress PASS
  product  ledger_integrity PASS
  product  ledger_writable  UNKNOWN (read-only probe)
  product  recall_channel   FAIL   the recall channel has never collected a record
  product  brief_generation PASS   generated in 0.4 s
```

两个真实发现：

1. **召回通道 0 条** → 产品最核心的安全承诺在线上不存在。这一条只有第三层能看见。
2. **crossref 与 pubmed 的水位线是 `2026-11-19`，比 UTC 今天（11-18）领先 1 天。**

### 4.1 关于那 1 天的领先：为什么是 WARN 而不是 FAIL

- 它是 2026-11-18T18:24–19:11 的真实采集写进去的（PubMed 的 edat 可以领先 UTC 一天）。
- 候选版的适配器会把未来水位线**钳制到今天**再作为查询下界，所以代价是"少一点重叠"，不是"停止发现"。
- 部署版的适配器**完全不钳制**（钳制在 `6f4d079` 才引入），所以同样的数据在**今天的生产上**是真问题：
  它会让 PubMed 从 11-19 起查，11-18 当天晚些时候才出现的记录会被跳过。

因此本轮把判定按**领先幅度**分级：≤1 天 = WARN（DEGRADED），>1 天 = FAIL（核心来源则 UNHEALTHY）。
2027-02 那类缺陷仍然是 UNHEALTHY（有测试固定）。

---

## 5. 实测：故障注入（不是"理论上会报"）

| 步骤 | 结果 |
| --- | --- |
| 探针 1：staging 正常 | `DEGRADED`（唯一原因是水位线 WARN） |
| 探针 2：`pkill -f "port 8792"` 后再探 | **`UNHEALTHY`**，`port/healthz/api_health/api_feed` 全部 FAIL，详细到 `URLError: Connection refused` |
| 探针 3：重启后 | `healthz=200`，回到 `DEGRADED` |

证据文件：`release-gate/001/out/staging-verdict.json`、`production-data-verdict.json`。

---

## 6. 候选 systemd 配置（未安装）

`units/medradar-radar-health.service`：oneshot、`User=medradar`、`ProtectSystem=strict`、
只允许写 `/var/lib/medradar-radar-health`、`SuccessExitStatus=0 1 2`（让 UNHEALTHY 以 failed 出现在
`systemctl --failed` 里，而不是被当成服务错误反复重启）。

`units/medradar-radar-health.timer`：`OnBootSec=2min`、`OnUnitActiveSec=5min`、`Persistent=true`。

> 为什么是 oneshot + timer 而不是常驻守护进程：探针每次运行完就退出，没有状态需要保留；
> 用 systemd 的失败状态作为"可观察的故障记录"，比再写一个告警服务更简单、也更不容易被忽略。

**这些单元没有安装。** 安装属于发布门禁（见 §8）。

---

## 7. 日志与保留

| 项 | 现状 | 建议 |
| --- | --- | --- |
| 服务日志 | journald（`medradar-radar-web`、`-scheduler`、`-tunnel`） | 无需改动；`journalctl -u … --since` 即可 |
| 探针状态 | `/var/lib/medradar-radar-health/last.json`（每次覆盖） | 保留最近一次快照；历史趋势由 journald 承担 |
| 访问日志 | uvicorn 输出到 journal（公网门禁会记录认证失败） | 无需改动 |
| 保留策略 | 系统默认（`/etc/systemd/journald.conf` 未定制） | 建议显式设置 `SystemMaxUse=1G`，避免长期运行挤占磁盘 |

最后一行是**建议，不是本轮改动**：改 journald 配置会影响整机所有服务，属于系统级决策。

---

## 8. 通知渠道：明确的"没有"

- 本轮**没有**配置任何邮件/Slack/webhook/短信告警。
- 现有可观察面：`systemctl --failed`、journald、`/var/lib/medradar-radar-health/last.json`、
  `/healthz`、`radar status`。
- **不得**把"有健康检查"说成"有主动告警"。运维必须**主动看**，否则故障只是被记录了，没有被通知。

把通知渠道接上，是发布之后的第一优先事项，而不是发布前的阻塞项——前提是有人按 `RELEASE_RUNBOOK.md`
§5 的观察清单每天看一次。

---

## 9. 发布门禁要求

监控接入必须在切换的**同一次变更**里完成，否则新版本会进入"能跑但没人盯"的状态：

1. 安装 `medradar-radar-health.service` + `.timer`（需要授权：新增 systemd 单元）；
2. 把 `radar_health.py` 放到 `/srv/medradar/release-gate/001/health/`（稳定路径，不随发布目录变化）；
3. 首次运行后确认 `systemctl --failed` 里出现的是预期状态（切换初期大概率是 DEGRADED，
   因为水位线领先 1 天）；
4. 在 `medradar-radar-health.timer` 生效后观察 3 个周期，确认没有抖动。
