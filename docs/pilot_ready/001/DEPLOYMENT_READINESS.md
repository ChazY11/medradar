# PILOT-READY-001 / 阶段六：真实部署候选的隔离验收

- 验收对象：候选分支 `pilot/pilot-ready-001`（基线 `a6da0f4a` + 6 处改动）
- 验收环境：**生产服务器上的隔离目录**，与正式服务完全并存、互不共享数据目录与端口
- 验收时间：2026-11-19 02:12–02:30 CST

> 边界：本阶段**没有**替换任何生产文件、没有重启任何正式服务、没有改任何 systemd 单元。
> 生产切换是单独的 Release Gate，见 §7。

---

## 1. 隔离环境

| 项 | 值 |
| --- | --- |
| 代码 | `/srv/medradar/pilot001-audit/code`（本地导出包，`EXPORT_MANIFEST.txt` 记录了 commit 与 6 处改动） |
| 虚拟环境 | `/srv/medradar/pilot001-audit/venv`（Python 3.12.3，pytest 9.2.0、httpx、fastapi、uvicorn） |
| 账本副本 A（基线） | `data-before/radar.db + graph.db`（生产库在线备份） |
| 账本副本 B（候选） | `data-after/radar.db + graph.db`（同一份备份的独立副本） |
| 监听 | API 冒烟测试用 **127.0.0.1:8799**（仅回环，测完即退出） |
| 运行身份 | `medradar` 用户 |
| 资源 | 未设 cgroup 上限；实测峰值 RSS 187.6 MB，远低于生产单元的 640 MB |

正式服务在此期间保持运行，未受任何影响（验收结束后 `systemctl is-active` 全部仍为 active）。

---

## 2. 测试执行结果

### 2.1 雷达专项（服务器上的隔离 venv，候选代码）

```text
tests/test_radar_api.py tests/test_radar_integrity.py tests/test_radar_intelligence.py
tests/test_radar_pipeline.py tests/test_radar_relevance.py tests/test_radar_watermark.py
tests/test_radar_advance_convergence.py tests/test_radar_health_verdict.py
→ 111 passed, 0 failed
```

### 2.2 全量套件（本机，候选分支）

```text
pytest tests → 1,702 collected, 1,698 passed, 4 skipped, 0 failed, exit 0
```

（首次在服务器上跑时出现 1 个失败：`test_the_evaluator_and_the_product_use_the_same_window`，
原因是导出包漏了 `scripts/` 目录。补上后通过；这是**打包**问题，不是代码问题。）

---

## 3. 修复前后对比（同一台 2 vCPU / 3.7 GB 生产主机）

| 指标 | 基线（已部署 `14eaf61`） | 候选（`a6da0f4` + 修复） | 说明 |
| --- | --- | --- | --- |
| `advance()` 批次 | 22 | 22 | 该库判定版本一致时，两者都不需要重判 |
| `advance()` 耗时 | **2.23 s** | **12.49 s** | 候选的一次性成本：v3 迁移 + 8,358 条判定补齐。稳态后再跑是 1 批（本机实测 0.27 s） |
| `converged` / `status` | `true` / 无字段 | `true` / `CONVERGED`，附 `backlog.total=0` | 从"只能看布尔值"到"能看到为什么" |
| 账本体积 | 45,268,992 B（45.3 MB） | **75,124,736 B（75.1 MB）** | **+66%**，见 §4 |
| 进程峰值 RSS | 186.9 MB | 187.6 MB | +0.7 MB，可忽略 |
| `/api/radar/health` 冷查询 | — | 1,497 ms | 首次调用要算一致性 + 资源 + 全量来源 |
| `/api/radar/health` 命中缓存 | — | **2.1 ms** | 15 s TTL（既有设计） |
| `/api/radar/sources` | — | 35.6 ms（中位） | |
| `/api/radar/feed?limit=20` | — | **92.7 ms**（中位，5 次） | 30 天窗口，`total=33` |
| `/api/radar/taxonomy` | — | 1.8 ms | |
| 周报生成 | — | **0.75 s**，峰值 RSS 64 MB | 7 天窗口，8,358 条账本 |
| 错误率 | — | **0**（所有端点 200；套件 0 失败） | |

**结论**：候选版本没有引入可测量的性能退化（RSS +0.7 MB、feed 92.7 ms）；
唯一显著的成本是**一次性存储增长 +66%**，原因是 v3 引入 `admission_current`
（8,358 行当前判定）并重建了 append-only 的判定历史。

---

## 4. 数据库完整性与迁移

### 4.1 迁移做了什么

打开 v2 库时自动执行：

1. `observation_admission` 重命名为 `_v2`，按 v3 结构重建（新增 `decision / dimensions /
   rules_digest / evidence_key / judged_version_id`）；
2. 旧行以 `INSERT OR IGNORE` 逐行搬入新表（`ALTER TABLE … RENAME` + 重建，不是原地加列）；
3. 建 `admission_current`（可重建的当前判定投影）与 `admission_workqueue`；
4. `PRAGMA integrity_check` 与计数对比在备份服务里做（见下文），迁移函数本身不删数据。

### 4.2 验收时的完整性检查

```text
迁移后：observation 8,358 → 8,358（不变）
        observation_version 8,358 → 8,358（不变）
        observation_change   8,358 → 8,358（不变）
        observation_admission 8,358 → 8,358 + 8,358（原 8,358 条 v2 判定保留 + 8,358 条 v3 重判）
        admission_current                → 16,716（两个 admission_version 各 8,358）
        health: ledger_integrity = PASS，consistency.counts 与迁移前一致
```

**没有一行观测、版本或变化记录被改写。** 判定历史是追加，不是覆盖（有触发器强制）。

### 4.3 迁移回滚

v3 迁移是**单向**的：旧代码（`14eaf61`）无法读 v3 库。因此回滚方案必须是"回滚代码 + 回滚数据"，
不能只回滚代码。这一点在 §7 的回滚步骤里显式写出。

---

## 5. 健康状态异常注入验证

在服务器隔离环境执行 `tests/test_radar_health_verdict.py`（12 项，全部通过）。注入方式与断言：

| 注入 | 断言结果 |
| --- | --- |
| `pubmed` 连续 3 次采集失败 | `UNHEALTHY`，`critical_sources=FAIL/CRITICAL`，点名 pubmed |
| `pubmed` 单次失败 | `DEGRADED` |
| 调度器心跳停在 8 天前 | `UNHEALTHY`，`scheduler_heartbeat=FAIL` |
| Crossref 水位线置为 `2027-02` | `UNHEALTHY`，`watermark_legal=FAIL/CRITICAL`，且 `consistency.ok=false` |
| 边缘来源（Philips）水位线置为 `2027-02` | `DEGRADED`（不是 UNHEALTHY，分级生效） |
| 版本链断裂 | `UNHEALTHY`，`ledger_integrity=FAIL` |
| 全部来源 40 天无新增（但持续成功） | **仍 `HEALTHY`**，只有 `acquisition_progress` 的 MINOR 提示 |
| 空部署 | `UNKNOWN` |
| 只读连接 | `ledger_writable=UNKNOWN`，顶层仍 `HEALTHY` |

**"重要来源真的故障时不再显示一切正常"这一条，通过。**

---

## 6. API 冒烟与公网关键路径

### 6.1 回环冒烟（隔离数据，候选代码）

```json
{"state": "HEALTHY", "legacy_state": "ok",
 "reasons": [{"id": "ledger_writable", "status": "UNKNOWN", "severity": "CRITICAL"}]}
/api/radar/health  200  中位 2.1 ms
/api/radar/sources 200  中位 35.6 ms   count=6
/api/radar/feed    200  中位 92.7 ms   total=33
/api/radar/taxonomy 200 中位 1.8 ms
```

### 6.2 公网入口实测（生产，只读）

```text
GET https://silly-facing-deferred-radar.trycloudflare.com/            → 401  0.53 s
GET …/api/radar/health                                                → 401  "Authentication required"
GET http://127.0.0.1:8791/healthz                                     → 200  {"status":"ok",…}
GET http://127.0.0.1:8791/api/radar/health                            → 401
```

结论：**公网入口有认证门（应用内中间件，PBKDF2 + 路由白名单 + 仅 GET/HEAD + 失败锁定）**，
401 是设计行为而非故障。

### 6.3 浏览器级验证：**NOT VERIFIED**

没有用真实浏览器走完 SPA 关键路径。原因：入口是 HTTP Basic 认证，**本轮不代用户输入凭据**，
也不从 `/etc/medradar/radar-alpha.env` 读取口令去自动登录。这属于"需要用户在场"的动作。
建议在试验开始前由拥有凭据的人完成一次人工走查（清单见 §8）。

---

## 7. 部署方案与回滚（需要用户授权的 Release Gate）

### 7.1 前置条件（缺一不可）

1. 用户书面授权"允许切换雷达服务到新版本"；
2. 生产库在切换前完成一次**在线备份并校验**（`radar backup`，验证 `integrity_check=ok`）；
3. 回滚决策人、切换窗口、观察期（建议 60 分钟）确认；
4. 具备 Basic 凭据的人在场，用于切换后的人工走查。

### 7.2 部署步骤（可执行，未执行）

```bash
# 0) 记录当前状态
readlink -f /srv/medradar/radar/app > /tmp/pre-switch-app.txt
cat /srv/medradar/radar/DEPLOYED_SHA

# 1) 备份（在线一致性备份 + 校验 + 保留 14 份）
sudo -u medradar env MEDRADAR_RADAR_DIR=/srv/medradar/data/radar   /srv/medradar/radar-venv/bin/python -m medradar radar backup   --destination /srv/medradar/data/radar/backups --keep 14 --json

# 2) 在副本上预演迁移（不碰生产）
cp /srv/medradar/data/radar/radar.db /tmp/pilot001/rehearsal.db
sudo -u medradar env PYTHONPATH=<new-release> MEDRADAR_RADAR_DIR=/tmp/pilot001   /srv/medradar/radar-venv/bin/python -m medradar radar verify --json   # 期望 integrity OK

# 3) 发布新版本目录（按 sha 命名，与现有约定一致）
#    把候选代码同步到 /srv/medradar/radar/releases/<new-sha>/，chown medradar:medradar

# 4) 切换符号链接（可逆）
ln -sfn /srv/medradar/radar/releases/<old-sha> /srv/medradar/radar/app.previous
ln -sfn /srv/medradar/radar/releases/<new-sha> /srv/medradar/radar/app
echo "<new-sha>" > /srv/medradar/radar/DEPLOYED_SHA

# 5) 重启两个单元（调度器先，Web 后）
systemctl restart medradar-radar-scheduler
systemctl restart medradar-radar-web

# 6) 验证
systemctl is-active medradar-radar-scheduler medradar-radar-web medradar-radar-tunnel
curl -sf http://127.0.0.1:8791/healthz
sudo -u medradar env PYTHONPATH=/srv/medradar/radar/app   MEDRADAR_RADAR_DIR=/srv/medradar/data/radar   /srv/medradar/radar-venv/bin/python -m medradar radar verify --json     # 期望 ok=true
sudo -u medradar env … radar status --json                                # 期望 state=HEALTHY
journalctl -u medradar-radar-scheduler -n 40 --no-pager
```

> 注：切换后第一次 `advance()` 会执行 v3 迁移并重判 8,358 条。按隔离实测，
> 在 2 vCPU 上约 **12.5 秒**、账本体积 **+66%**。这一步必须在观察期内完成并确认。

### 7.3 回滚步骤（对应 §4.3 的单向迁移）

```bash
systemctl stop medradar-radar-scheduler medradar-radar-web
ln -sfn /srv/medradar/radar/releases/<old-sha> /srv/medradar/radar/app
echo "<old-sha>" > /srv/medradar/radar/DEPLOYED_SHA
# 关键：代码回滚必须同时回滚数据库，否则旧代码读不了 v3 库
cp /srv/medradar/data/radar/radar.db  /tmp/radar.db.failed-v3     # 保留现场
cp <切换前备份>/radar-*.db            /srv/medradar/data/radar/radar.db
chown medradar:medradar /srv/medradar/data/radar/radar.db
systemctl start medradar-radar-web medradar-radar-scheduler
curl -sf http://127.0.0.1:8791/healthz
```

> `graph.db` 不需要回滚：它是 `radar.db` 的派生投影，可用 `radar rebuild-graph` 重建。
> 备份清单里已经写明这一点，本轮实测确认可行。

### 7.4 明确需要授权的操作

| 操作 | 是否已执行 | 需要谁授权 |
| --- | --- | --- |
| 部署候选版本到 `/srv/medradar/radar/releases` | **否** | 用户（生产发布授权） |
| 切换 `app` 符号链接与 `DEPLOYED_SHA` | **否** | 用户 |
| 重启 `medradar-radar-*` 单元 | **否** | 用户 |
| 在生产库上执行 v3 迁移 | **否** | 用户（且必须先备份） |
| 修改/新增 systemd 单元（健康检查、周报定时器） | **否** | 用户 |
| 读取或使用 Basic 凭据 | **未做** | 用户本人 |
| 只读检查、隔离副本上的测试、在线备份 | **是** | 本次已授权范围内 |

---

## 8. 切换后的人工走查清单（需要有凭据的人）

1. 用 Basic 凭据打开公网首页，确认 SPA 加载、四个页面可切换；
2. 打开 `/api/radar/health`，确认 `state` 与 `legacy_state` 同时存在且一致；
3. 在 feed 中随机点开 3 条，确认原始链接可打开；
4. 确认 `/healthz` 在**无凭据**情况下返回 200；
5. 观察 60 分钟：调度器至少完成 1 个周期，`journalctl` 中无 traceback；
6. 确认 `medradar-health` 的覆盖范围已扩展到 8791（见 §9）。

---

## 9. 部署时**必须同时做**的三件配套事

只切代码不接线，等于把新能力关在盒子里：

| 配套项 | 现状 | 需要的动作 |
| --- | --- | --- |
| 健康检查覆盖雷达 | `/usr/local/bin/medradar-health` 只探 8787 | 在脚本中增加对 `http://127.0.0.1:8791/healthz` 与 `radar status` 的检查，或新增独立单元 |
| 周报定时生成 | 无 | 新增 timer（建议每周一 06:00 本地），产物落到 `docs/pilot_ready/briefs/WEEKLY_<date>.md` |
| 备份保留与两处备份统一 | `data/radar/backups`（14 份）与 `/srv/medradar/backups/radar`（未纳入保留策略） | 二选一，避免恢复时选错文件 |

---

## 10. 风险登记（部署前必须已知）

| # | 风险 | 等级 | 缓解 |
| --- | --- | --- | --- |
| R1 | v3 迁移单向，回滚必须回滚数据 | **高** | §7.3 的备份优先流程；切换窗口内保留现场 |
| R2 | 账本体积 +66% | 中 | 磁盘 45 GB 可用，短期无压力；保留策略需与增长匹配 |
| R3 | 首次 `advance()` 在 2 vCPU 上约 12.5 s（本次环境） | 低 | 迁移在启动后自动发生，不阻塞 HTTP |
| R4 | 健康端点的冷查询 1.5 s | 中 | 已有 15 s TTL；若定时器高频调用需注意 |
| R5 | Quick Tunnel 域名可能变化 | 中 | 见 `PILOT_OPERATIONS.md` §5 |
| R6 | 生产库没有召回通道数据，切换后需回填一次 | 中 | 回填必须标 `BACKFILLED` 并写理由；回填后简报才能出现安全事件 |
| R7 | 人工走查未完成（无凭据） | 中 | §8 清单，由用户完成 |

---

## 11. 本阶段结论

**隔离验收通过**：候选版本在真实服务器、真实规模副本、独立 venv、独立端口上，
通过了 111 项雷达专项测试与 1,702 项全量测试，完成了 v3 迁移、收敛验证、健康异常注入与 API 冒烟，
性能无退化，唯一的实质成本是**一次性存储增长 66%**。

**但"通过隔离验收"不等于"已部署"。** 生产切换是 Release Gate，需要 §7.4 的授权；
其中 **R1（单向迁移）** 是最需要在授权前被明确接受的一条。
