# PILOT-READY-001 / 阶段一：服务器真实状态基线

- 采集时间：2026-11-19 01:47–02:20（Asia/Shanghai），即 2026-11-18 17:47–18:20 UTC
- 采集方式：以 root 通过 SSH 登录 `VM-0-12-ubuntu`，全部为只读探测（`systemctl`、`journalctl`、
  `ss`、`df`、`free`、文件系统列举、SQLite 在线备份后离线读取）。未修改任何生产文件、未重启任何服务。
- 证据形式：本文所有数字都来自命令输出；命令与其原始输出片段在每节给出。

> 说明：本项目此前的文档多次写"生产环境不可访问"。本轮已获得服务器访问能力，以下结论全部基于实测，
> 不再使用该假设。

---

## 1. 主机与资源

| 项 | 实测值 |
| --- | --- |
| 主机名 | `VM-0-12-ubuntu` |
| 操作系统 | Ubuntu 24.04.4 LTS（Noble），内核 6.8.0-138-generic，x86_64 |
| CPU | 2 vCPU |
| 内存 | 3,724 MB，已用 1,882 MB，可用 1,841 MB |
| Swap | 1,987 MB，已用 315 MB |
| 磁盘 | `/dev/vda2` 59 GB，已用 12 GB（22%），可用 45 GB |
| 负载 | 0.29 / 0.23 / 0.09（1 分钟/5 分钟/15 分钟） |
| 运行时长 | 2 天 23 小时 |

```
$ df -h / ; free -m ; uptime
/dev/vda2        59G   12G   45G  22% /
Mem:            3724        1882         337         2        1795        1841
 02:16:50 up 2 days, 23:12,  1 user,  load average: 0.29, 0.23, 0.09
```

数据目录占用：`data/fda` 244 MB（FDA 管道）、`data/radar` 374 MB（雷达账本 + 备份 + 恢复演练副本）、
`var/backup` 1.1 GB（历史本地状态备份）。**磁盘不是当前风险**，但 `data/radar` 内备份与演练副本
（合计约 260 MB）会随保留策略线性增长，需要按 §8 观察。

---

## 2. 部署拓扑

```
/srv/medradar/
├── app/                     FDA 数据管道（git 仓库，branch feat/data-003-runtime-reliability）
├── radar/
│   ├── app -> releases/14eaf6155a966bf6c630e1268226d31a53d8b66a   （符号链接，当前发布）
│   ├── app.previous -> releases/d91d647e…                          （上一发布，回滚点）
│   ├── DEPLOYED_SHA        14eaf6155a966bf6c630e1268226d31a53d8b66a
│   └── releases/           30 个历史发布目录（按 commit SHA 命名）
├── radar-venv/             Python 3.12.3（雷达运行时）
├── .venv/                  Python 3.12.3（FDA 管道运行时）
├── data/fda/               pipeline.db 31 MB + snapshots/ + active.json
├── data/radar/             radar.db 44 MB、graph.db 65 MB、backups/、restore-drill-*/
├── data/identity/          空
├── var/                    DEPLOYED_SHA、backup/
└── backups/radar/          另一处雷达备份（2026-11-17）
```

**关键事实：`/srv/medradar` 本身不是 git 仓库。** 部署是"按 commit 复制到 releases/<sha> 再切换符号链接"
的方式，版本由 `radar/DEPLOYED_SHA` 与 `var/DEPLOYED_SHA` 记录。因此"服务器上是什么版本"必须读这两个文件，
不能假设与本地 worktree 一致。

```
$ cat /srv/medradar/radar/DEPLOYED_SHA
14eaf6155a966bf6c630e1268226d31a53d8b66a
$ cat /srv/medradar/var/DEPLOYED_SHA
sha=7415382df8d449194557a440cf9a869da3b25c59
previous_sha=bb1ef34df3c15e2b1339432abce899eebea5e1f6
branch=feat/data-003-runtime-reliability
deployed_at=2026-11-17T04:30:37+08:00
data_snapshot=fda-snapshot-20261116T032632Z-18ce4d0cbbe4
```

---

## 3. systemd 服务与定时器

| 单元 | 状态 | 作用 | 监听 |
| --- | --- | --- | --- |
| `medradar-radar-scheduler.service` | active (running) | 连续采集调度器（`radar watch --interval 300 --no-ai`） | 无 |
| `medradar-radar-web.service` | active (running) | 雷达只读 Web + API | 127.0.0.1:8791 |
| `medradar-radar-tunnel.service` | active (running) | Cloudflare Quick Tunnel（仅出站） | — |
| `medradar-web.service` | active (running) | 旧工作台（FastAPI + 构建 UI） | 127.0.0.1:8787 |
| `medradar-health.timer` | active (waiting，每 5 分钟) | 健康检查脚本 | — |
| `medradar-data-update.timer` | active (waiting，每小时) | FDA 快照增量检查 | — |
| `medradar-radar-backup.timer` | active（每日 03:40 本地） | 雷达账本在线备份 | — |
| `medradar-data-backup.timer` | active | FDA 状态备份 | — |
| `medradar-backup.timer` | active | 本地状态备份 | — |

失败单元数：`failed_units=0`。

进程实测：

```
 375145 medradar  /srv/medradar/.venv/bin/python -m medradar.product.web --host 127.0.0.1 --port 8787
 436935 medradar  /usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8791
 681920 medradar  /srv/medradar/radar-venv/bin/python -m medradar.product.web --host 127.0.0.1 --port 8791 …
 681928 medradar  /srv/medradar/radar-venv/bin/python -m medradar radar watch --interval 300 --no-ai
```

cgroup 实测：调度器 RSS 39 MB（上限 640 MB、high 384 MB），CPU 累计 41 s，重启次数 0；
雷达 Web RSS 466 MB（MemoryMax 768 MB），重启次数 0。

---

## 4. 版本矩阵（实测，不允许推断）

| 环境 | Commit SHA | 分支 | 数据库版本 | 功能状态（实测） |
| --- | --- | --- | --- | --- |
| **main** | `b2a14c03` | `main` | 不含产品代码 | **不包含雷达产品**；main 上没有 `medradar/radar/`、没有 `docs/v1`。产品从未合并到 main。 |
| **本地开发（本轮起点）** | `4c6686f4` | `research/s028-temporal-graph-early-signal` | 无运行库 | 检出的是研究分支，**不是**产品分支；工作区仅 1 个 CSV 有改动。 |
| **服务器 · 雷达** | `14eaf615` | `feat/radar-001-live-intelligence-graph` | `radar-ledger-v2`（8358 条观测） | 运行中。**不含** FIRST PRINCIPLES-001 的水位线修复，**不含**召回通道，**不含** admission v3。 |
| **服务器 · FDA 管道** | `7415382d` | `feat/data-003-runtime-reliability` | 快照 `fda-snapshot-20261117T055525Z` | 运行中；最近一次增量检查 2026-11-19 01:08 返回 `NO_CHANGE`。 |
| **候选发布（本轮）** | `a6da0f4a` + 6 处工作区改动 | `pilot/pilot-ready-001`（自 `v1/001` 拉出） | 迁移到 `radar-ledger-v3` | 已通过 1,702 项测试与隔离验收，**未部署**。 |

### 4.1 本轮必须回答的那个问题：服务器到底跑的是哪个版本？

**服务器跑的是 QUALITY-001（`14eaf61`），不是 PR #54、不是 REFOUNDATION-004、不是
FIRST PRINCIPLES-001、也不是 V1-001。**

证据链：

```
$ cd /srv/medradar && git rev-parse HEAD
fatal: not a git repository            # 部署根目录本身没有 git

$ cat /srv/medradar/radar/DEPLOYED_SHA
14eaf6155a966bf6c630e1268226d31a53d8b66a
$ readlink -f /srv/medradar/radar/app
/srv/medradar/radar/releases/14eaf6155a966bf6c630e1268226d31a53d8b66a
```

本地分支关系（`git merge-base --is-ancestor`）：

```
14eaf61  → 是 6f4d079（FIRST PRINCIPLES-001 的水位线修复）的祖先
6f4d079  → 是 a6da0f4（V1-001）的祖先
```

即：**服务器位于链条上的第一个点，后面三层修复都没有上线。** 这解释了 §6 与
`CONTINUOUS_OPERATION.md` 中观察到的若干现象。

### 4.2 数据库版本（实测，不是推断）

```
$ sqlite3 只读副本: SELECT * FROM meta
{'key': 'schema_version', 'value': 'radar-ledger-v2'}
{'key': 'created_at',     'value': '2026-11-17T00:13:33+00:00'}
表清单: ai_candidate, graph_materialization, meta, observation, observation_admission,
        observation_change, observation_facet, observation_identifier, observation_mapping,
        observation_status_history, observation_version, processing_queue, runtime_state,
        source_failure, source_state, sync_checkpoint, sync_run
```

没有 `admission_current`、没有 `admission_workqueue`——这两个表在 REFOUNDATION-004
（`68e0e0b`）才出现。**数据库版本与代码版本一致，都是 v2。**

候选版本会把该库迁移到 `radar-ledger-v3`（新增两表、重建 admission 历史），实测账本体积由
45.3 MB 增至 75.1 MB（+66%），见 `DEPLOYMENT_READINESS.md` §4。

---

## 5. 数据、备份与回滚能力

### 5.1 数据库位置

| 库 | 路径 | 体积 | 说明 |
| --- | --- | --- | --- |
| 雷达账本 | `/srv/medradar/data/radar/radar.db` | 44 MB（+4.1 MB WAL） | 观测、版本、变化、判定、游标全部在此 |
| 雷达图谱 | `/srv/medradar/data/radar/graph.db` | 65 MB | **派生物**，可由账本重建 |
| FDA 管道 | `/srv/medradar/data/fda/pipeline.db` | 31 MB | 旧工作台快照管道 |
| 冻结快照 | `/srv/medradar/data/fda/snapshots/*` | 9 个快照 | 原子发布单元 |

### 5.2 备份实测（已验证可读、可校验，未做恢复覆盖）

```
$ ls -la /srv/medradar/data/radar/backups/
radar-20261117T004423026.db / .json
radar-20261117T004515609.db / .json
radar-20261117T194210856.db / .json     ← 最新
$ 只读打开最新备份: PRAGMA integrity_check = ok ； observation = 8283
$ 清单文件字段: verified=true, integrity_check=ok, backup_sha256=b72cf95f…, counts 与源库一致
```

备份清单里明确写了：`graph.db` 是派生投影，故意不备份，可用 `radar rebuild-graph` 重建。
这一点是正确的设计，本轮实测确认 `graph.db` 确有 15,537 节点 / 4,792 边，可从账本重建。

恢复演练副本已存在两套（`restore-drill-20261117T004422Z`、`restore-drill-20261117T004515Z`），
说明历史上做过恢复演练。

### 5.3 回滚能力

- 雷达服务回滚点：`/srv/medradar/radar/app.previous -> releases/d91d647e…`，切换符号链接 + 重启单元即可。
- FDA 管道回滚点：`/srv/medradar/var/DEPLOYED_SHA.pre-data003`（`1bdb1c34`，分支
  `feat/product-003-device-intelligence`）+ `var/backup/data002-pre/` 下的 unit 文件与包快照。
- 备份保留：雷达 14 份（`--keep 14`），本地状态与 FDA 各 1 日一份。

### 5.4 权限（不含任何密钥内容）

- 服务以 `medradar` 用户运行，unit 均启用 `ProtectSystem=strict`、`ProtectHome=yes`、
  `NoNewPrivileges=yes`，仅对 `/srv/medradar/data` 开 `ReadWritePaths`。
- `/etc/medradar/radar-alpha.env`、`pipeline.env` 为 `root:medradar 0640`。本轮只读取了**变量名**，未读取值：
  `MEDRADAR_ALPHA_GATE / MEDRADAR_ALPHA_USER / MEDRADAR_ALPHA_HASH / MEDRADAR_ALPHA_TRUST_PROXY /
  MEDRADAR_ALPHA_SESSION_SECRET`，以及 `MEDRADAR_PIPELINE_RESOURCE_GUARD / MIN_AVAILABLE_MB /
  MIN_SWAP_FREE_MB / MAX_PSI_SOME / MIN_DISK_FREE_MB`。
- `radar-venv/` 属主为 root，服务以 medradar 读取，属"运行时不可被服务自身修改"的正确设置。
- 无公网 SSH 密钥、无 Token、无 Cookie 出现在本文。

---

## 6. 公网访问与实际可用性

```
$ journalctl -u medradar-radar-tunnel | grep trycloudflare | tail -1
https://silly-facing-deferred-radar.trycloudflare.com
$ curl -o /dev/null -w '%{http_code} %{time_total}s' https://silly-facing-deferred-radar.trycloudflare.com/
401 0.53s
$ curl https://…/api/radar/health
Authentication required     (401)
$ curl http://127.0.0.1:8791/healthz
200 {"status":"ok","service":"medradar-radar-alpha"}
$ curl -o /dev/null -w '%{http_code}' http://127.0.0.1:8791/api/radar/health
401
```

访问控制是**应用内中间件**（`medradar/radar/alpha_gate.py`），而不是仅靠反代规则：

- HTTP Basic over TLS，口令以 PBKDF2-SHA256 存储；
- 路由白名单：仅 `/radar*` 页面、`/api/radar/*`、`/api/meta` 与构建产物；其余返回 **404 而不是 403**；
- 只允许 GET/HEAD；
- 同一来源连续失败会锁定窗口；
- `/healthz` 免认证（只报存活，不碰数据库）。

因此："公网可访问"是**有认证门**的，401 不是故障。真正的风险在别处：**Quick Tunnel 的域名是临时的**，
cloudflared 重启或隧道重连可能换域名（见 `PILOT_OPERATIONS.md` §5）。

---

## 7. 健康检查与日志（可观测性现状）

现存健康检查脚本 `/usr/local/bin/medradar-health` 由 `medradar-health.timer` 每 5 分钟执行，但它检查的是：

```
APP="http://127.0.0.1:8787"           # 旧工作台
curl … "$APP/api/health"
curl … "$APP/api/devices/quality"
```

**它完全不检查雷达服务（8791）、不检查调度器、不检查水位线。** 这是本轮之前的一个真实盲区：
即使雷达采集全线停止，`medradar-health` 仍会报绿，因为旧工作台还活着。候选版本新增的
`system_status` 分级判定补上了这一块（见 `RELIABILITY_FIXES.md` P0-02），但**单元/定时器一侧的接线
尚未部署**——这是部署方案的一部分（`DEPLOYMENT_READINESS.md` §5）。

日志现状（调度器，最近 6 个周期）：

```
2026-11-19T01:44:37 [scheduler] cycle 303: IDLE new=0 updated=0 ai=None
2026-11-19T01:39:37 [graph] materialized 0 observation(s): 0 new assertion(s), 0 duplicate(s), 0 error(s)
```

最近一次 FDA 管道运行（2026-11-19 01:08:26）退出码 0：

```
"status": "NO_CHANGE",
"message": "no healthy source has an available update",
"failed_sources": [], "problems": []
```

---

## 8. 本轮基线中已经确认的缺口（不是推测）

| 编号 | 缺口 | 证据 | 影响 |
| --- | --- | --- | --- |
| B1 | 服务器代码落后三个修复层（水位线不可用修复、admission v3、召回通道） | §4.1 祖先关系 | 见 `CONTINUOUS_OPERATION.md`：某类来源可能空转 |
| B2 | 生产库仍是 v2，没有 `admission_current` | §4.2 | 无法在不迁移的情况下获得可重判的判定投影 |
| B3 | `medradar-health` 只探 8787，不探 8791/调度器 | §7 | 雷达静默故障不会触发既有健康检查 |
| B4 | 公网入口是 Quick Tunnel 临时域名 | §6 | 四周试验期间域名可能变化，用户链接失效 |
| B5 | 雷达 Web RSS 466 MB / MemoryMax 768 MB，2 vCPU 共用 | §3 | 余量约 300 MB，重查询或缓存增长会逼近上限 |
| B6 | 备份与恢复演练副本合计约 260 MB 且随保留策略增长 | §1 | 长期运行需观察磁盘 |
| B7 | `data/radar` 内同时存在两处备份（`data/radar/backups` 与 `/srv/medradar/backups/radar`） | §2 | 保留策略不一致，恢复时选错文件的风险 |

---

## 9. 这一节的结论

服务器**确实在长期运行**，且运行的是一个真实的、有认证门的、有备份和回滚点的部署。
但它运行的是 **QUALITY-001（`14eaf61`）**，而不是本轮候选版本；数据库是 v2；
现有健康检查不覆盖雷达与调度器。

因此："服务器在跑"与"服务器在跑我们验收过的版本"是两件不同的事。前者的证据在本文；
后者的证据在 `DEPLOYMENT_READINESS.md`，状态是 **NOT DEPLOYED**。
