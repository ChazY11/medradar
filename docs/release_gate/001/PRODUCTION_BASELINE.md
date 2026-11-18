# RELEASE-GATE-001 / 生产基线（重新核实，不继承上一轮结论）

- 采集时间：2026-11-19 02:45–03:20 CST（2026-11-18 18:45–19:20 UTC）
- 方法：以 root 通过 SSH 直连 `VM-0-12-ubuntu`，全部只读探测；唯一的写入发生在
  `/srv/medradar/release-gate/001/`（本轮新建的隔离区），生产数据目录只被读取。
- 本轮不沿用上一轮报告的任何结论：下面每一条都是重新测的。

---

## 1. 结论先行

| 问题 | 实测答案 | 怎么证明的 |
| --- | --- | --- |
| 生产跑的是哪个版本？ | `14eaf615`（QUALITY-001） | 部署目录 1,759 个受版本控制的文件**逐字节**与 commit `14eaf61` 一致（sha256 清单比对，0 缺失 0 差异） |
| 是靠 `DEPLOYED_SHA` 文件判断的吗？ | **不是**。它只是旁证 | 见 §3：内容指纹 + 实际 import 路径 + 进程 cwd 三路互证 |
| 数据库是什么版本？ | `radar-ledger-v2` | `meta.schema_version`，且 `observation_admission` 没有 `admission_seq` 列（v2 的特征） |
| 数据量 | 8,360 条观测 | 备份副本离线计数 |
| 和 V1 候选的 `15,156 条差在哪？ | 差在**召回通道**（6,563 条）与后续增量 | 见 §5 |
| 候选版本包含哪些修复？ | REF-004 + FP-001 + V1-001 + PILOT-READY-001 + 本轮 3 个修复，共 17 个提交 | `git merge-base --is-ancestor` 逐个核验 |
| 候选版本包含"时间精度修复"吗？ | **原本不包含**，本轮补上 | 见 §6 |

---

## 2. 运行环境

| 项 | 实测 |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS，内核 6.8.0-138-generic，x86_64 |
| CPU / 内存 / 磁盘 | 2 vCPU / 3,724 MB（可用 1,835 MB）/ 59 GB（已用 12 GB，22%） |
| Python | `/srv/medradar/radar-venv/bin/python` = 3.12.3（指向 `/usr/bin/python3.12`）；FDA 管线用 `/srv/medradar/.venv`，同为 3.12.3 |
| 端口 | 127.0.0.1:8791（雷达 Web）、127.0.0.1:8787（旧工作台）、127.0.0.1:8080（caddy）、127.0.0.1:20241（cloudflared 指标）、0.0.0.0:22（sshd） |
| 运行账户 | 服务以 `medradar` 运行；`radar-venv` 属主 root（服务只能读，不能改自己的运行时） |
| 反向代理 | `dsh-auth-caddy`（127.0.0.1:8080）；公网入口是 Cloudflare Quick Tunnel → 8791 |
| 访问控制 | 应用内中间件 `medradar/radar/alpha_gate.py`：HTTP Basic（PBKDF2-SHA256）、路由白名单、仅 GET/HEAD、失败锁定、`/healthz` 免认证 |

进程与 unit（实测）：

```
681920  /srv/medradar/radar-venv/bin/python -m medradar.product.web --host 127.0.0.1 --port 8791 …
681928  /srv/medradar/radar-venv/bin/python -m medradar radar watch --interval 300 --no-ai
436935  /usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8791
375145  /srv/medradar/.venv/bin/python -m medradar.product.web --host 127.0.0.1 --port 8787
1951    /usr/lib/dsh-auth/caddy run --config /run/dsh-auth-caddy/Caddyfile
```

unit/timer：`medradar-radar-web`、`medradar-radar-scheduler`、`medradar-radar-tunnel`、
`medradar-web`、`medradar-health`（+timer 5 分钟）、`medradar-radar-backup`（+timer 每日 03:40）、
`medradar-data-update`（+timer 每小时）、`medradar-data-backup`、`medradar-backup`。
失败单元 0。

日志：全部走 journald（`journalctl -u …`），无独立日志文件；保留策略由 systemd/journald 默认管理。
**没有对雷达服务的定时健康检查**（现有的 `medradar-health` 只探 8787）。

---

## 3. 版本核实：三路互证

### 3.1 内容指纹（决定性证据）

在本地把 `14eaf61` 的完整树导出并对 1,759 个文件逐个算 sha256；在服务器对部署目录做同样的事；
逐行比对：

```
identical: 1759
missing:   0
mismatched: 0
```

部署目录 = `/srv/medradar/radar/releases/14eaf6155a966bf6c630e1268226d31a53d8b66a`
（`/srv/medradar/radar/app` 是指向它的符号链接）。

### 3.2 实际 import 路径

venv 里有一个 editable 安装的占位（`__editable__.medradar-0.5.0.pth`），理论上可能遮蔽部署目录。
用 unit 完全相同的命令实测解析结果：

```
medradar: …/releases/14eaf6155a966bf6c630e1268226d31a53d8b66a/medradar/__init__.py
engine:   …/releases/14eaf61…/medradar/radar/engine.py
health:   …/releases/14eaf61…/medradar/radar/health.py
```

### 3.3 进程工作目录

`/proc/681920/cwd` 与 `/proc/681928/cwd` 都指向同一个 release 目录。

**三路一致 → 生产运行的就是 `14eaf61`，不是 `var/DEPLOYED_SHA` 声称的"大概"，
也不是上一轮报告里的任何其他版本。**

> 说明：`/srv/medradar` 本身不是 git 仓库；版本只能由 `radar/DEPLOYED_SHA` +
> `releases/<sha>` 目录名 + 内容指纹共同确定。只读文本文件是不够的——这正是本轮重做的原因。

---

## 4. 数据状态（只读）

| 项 | 值 |
| --- | --- |
| schema_version | `radar-ledger-v2`（created_at 2026-11-17T00:13:33Z） |
| 观测 / 版本 / 变化 / 映射 / 判定 | 8,360 / 8,360 / 8,360 / 8,360 / 8,360 |
| facet / identifier | 17,285 / 1,660 |
| 来源分布 | openfda_device 6,938 · crossref 1,112 · pubmed 274 · draeger 31 · philips 5 · **openfda_recall 0** |
| 判定 tier | HIGH 7,166 · LOW 682 · NEEDS_REVIEW 395 · IRRELEVANT 117 |
| 数据库大小 / WAL | 45,268,992 B + 4,280,712 B WAL |
| 图谱 | graph.db 67.7 MB，23,146 节点 / 17,802 边 |
| 完整性 | `PRAGMA integrity_check = ok`，外键 0 违规 |
| 最近一次成功采集 | 2026-11-18T19:11:25Z（本轮强制周期）；调度器常规周期 18:24:46Z |
| 水位线 | openfda_device `2026-11-09` · crossref `2026-11-19` · pubmed `2026-11-19` · philips `2026-11-16T07:30Z` · draeger `2026-11-09T12:41Z` |

**生产上出现的真实异常（本轮新发现）**：`crossref` 与 `pubmed` 的水位线是 `2026-11-19`，
比 UTC 当天（2026-11-18）**领先 1 天**。它是 2026-11-18T18:24–19:11 之间的正常采集写进去的。
部署中的适配器**不做任何钳制**（钳制在 `6f4d079` 才引入），因此线上会直接拿它当下界。
详见 `HEALTH_MONITORING.md` §4。

---

## 5. 8,360 与 15,156 的差异

| 组成 | 生产 8,360 | V1 简报 15,156 | 差异原因 |
| --- | --- | --- | --- |
| openfda_device | 6,938 | 6,936 | 同源同窗，±2 条为不同时刻 |
| **openfda_recall** | **0** | **6,563** | 召回通道在 `300a864`（V1-001）才加入；生产是 `14eaf61`，**没有这个适配器** |
| pubmed | 274 | 484 | V1 账本多跑了几轮 |
| crossref | 1,112 | 1,137 | 同上 |
| draeger / philips | 31 / 5 | 31 / 5 | 相同 |

结论：**差异几乎全部来自召回通道**。这也解释了为什么"服务器上的产品"看不到任何安全事件：
它根本没有采集这条通道。

本轮在隔离环境补做了一次真实回填后，账本变成 16,253 条（8,360 + 6,563 召回 + 1,330 增量），
与 V1 简报的量级一致（见 `STAGING_ACCEPTANCE.md`）。

### 5.1 哪些数据来自历史回填

回填的 6,563 条召回**全部**标记为 `observation_origin = BACKFILLED`、
`discovery_phase = HISTORICAL_BACKFILL`，并带有显式 `backfill_reason`：

```
RELEASE-GATE-001 staging: the deployed ledger never collected the recall channel
```

其公开日期跨度是 **2003-03-05 .. 2026-11-05**——这是 23 年的 FDA 召回历史，不是"本周新闻"。
产品必须靠 `published_at` 而不是 `first_observed_at` 判断新颖度，否则会把 2003 年的事情当成新事件。

### 5.2 哪些数据需要重新分类

v2 的 8,360 条判定用的是 `radar-admission-2026.11.3`；候选版用的是
`radar-assessment-2026.11.21`。迁移会把旧判定作为**历史**保留（`rules_digest='legacy-v2'`），
然后由 `advance()` 追加新判定。所以"重新分类"不是覆盖，而是并存——老判定的证据永远留着。

### 5.3 哪些只存在于隔离环境

本轮所有新增数据（6,563 条召回回填、1,330 条强制周期增量、v3 判定）**只存在于**
`/srv/medradar/release-gate/001/staging/data`，生产库一行未写（§7 有证据）。

---

## 6. 候选版本完整性（Phase 2.1）

`HEAD = f2f70dd248587e4691e58e0bcebe4f05572bc745`，分支 `pilot/pilot-ready-001`，
相对生产 `14eaf61` 共 **17 个提交**。

祖先关系（`git merge-base --is-ancestor`，全部为真）：
`14eaf61` → `380aa37`（REFOUNDATION-004）→ `6f4d079`（FIRST PRINCIPLES-001）→
`a6da0f4`（V1-001）→ `388c115`（PILOT-READY-001）→ `848a926` → `e4aaff6` → `f2f70dd`。

| 要求 | 是否包含 | 证据 |
| --- | --- | --- |
| REFOUNDATION-004（admission v3） | ✅ | `68e0e0b`、`cba4d13` 可达 |
| FIRST PRINCIPLES-001（水位线不可用修复） | ✅ | `6f4d079` 可达 |
| V1-001（召回通道 + 简报） | ✅ | `300a864`、`0d6a5bd` 可达 |
| PILOT-READY-001（advance 收敛、健康分级） | ✅ | `388c115` 可达 |
| **时间精度修复** | ❌ **原本没有** | `git diff 14eaf61 HEAD -- medradar/radar/records.py` 无 `PRECISION` 相关行 |
| 本轮新增 | ✅ | `848a926` 月精度、`e4aaff6` 迁移可恢复、`f2f70dd` 水位线严重度 |

**这是一条必须如实写下的更正：** 上一轮与任务书都假设候选版本包含"时间精度修复"，实测它没有。
本轮把它补上了（§6.1），否则"日期精度正确"这条验收无法成立。

### 6.1 本轮补的三个修复（都是发布阻塞级或必修级）

| 提交 | 问题 | 为什么必须在上线前修 |
| --- | --- | --- |
| `848a926` | `YYYY-MM` 被标成 `year` | 读者被骗（以为来源只说年份）；更重要的是新鲜度按"该日期最早可能时刻"计龄，11 月的记录被当成 1 月，压低重要性评级。生产有 308 条受影响。 |
| `e4aaff6` | v2→v3 迁移在"版本号已提升、旧行未复制"之间被打断就**永久丢判定** | 实测可复现：8,360 条判定变成 0 条可读，旧数据还躺在孤儿表里，之后每次打开都认为已经是 v3。迁移必须在中断后可恢复。 |
| `f2f70dd` | 任何未来水位线都判 CRITICAL | 生产此刻就有 1 天领先的水位线。上线第一分钟就会 UNHEALTHY，从而训练运维忽略警报。按领先天数分级后，1 天=警告、超过宽限=失败（2027-02 那类仍失败）。 |

---

## 7. 生产未被修改的证据

| 检查 | 结果 |
| --- | --- |
| `readlink -f /srv/medradar/radar/app` | 仍是 `releases/14eaf61…` |
| `/srv/medradar/radar/DEPLOYED_SHA` | 仍是 `14eaf6155a966bf6c630e1268226d31a53d8b66a` |
| `/srv/medradar/data/radar/radar.db` mtime | `2026-11-19 00:49:36`（早于本轮开始时刻 02:45） |
| 四个生产服务 | 全部 `active`，`NRestarts=0` |
| 生产库行数 vs 备份 | 观测/版本/变化/映射/判定 **delta 全为 0** |
| `/etc/medradar/*.env` | mtime 未变；本轮只读取变量名，未读取值 |
| 备份、审计数据 | 未删除、未移动 |

本轮所有产出都在 `/srv/medradar/release-gate/001/`（新建，属主 `medradar:medradar`，权限 750）。

---

## 8. 基线中确认的缺口（与发布决定直接相关）

| # | 缺口 | 影响 |
| --- | --- | --- |
| G1 | 生产无召回通道（0 条） | 安全事件这条核心承诺在线上不存在 |
| G2 | 水位线领先 UTC 1 天且无人钳制 | 部署版每次查询都可能少覆盖 1 天；无人报告 |
| G3 | `medradar-health` 不探 8791、不看调度器 | 雷达静默故障不会触发任何检查 |
| G4 | 无周报定时器 | "每周一份"只能手工 |
| G5 | 公网入口是 Quick Tunnel 临时域名 | 重启可能换域名 |
| G6 | 迁移单向，且原实现不可恢复 | 见 `MIGRATION_TEST.md`（本轮已修） |
| G7 | 两处雷达备份（`data/radar/backups` 与 `/srv/medradar/backups/radar`） | 恢复时可能选错 |
