# RELEASE-GATE-001 / 备份、校验与恢复演练

- 备份时间戳：`20261118T185150Z`（= 2026-11-19 02:51:50 CST）
- 位置：`/srv/medradar/release-gate/001/backup/20261118T185150Z/`（0750，属主 medradar）
- 站外副本：`D:\DEPPSKK\release-gate-001\backup\radar-20261118T185150Z.db`
- 结论：**备份可信；恢复演练实际执行并通过；切换后回滚可执行，但会丢失切换后的"首次发现时间"，见 §5.2。**

---

## 1. 备份了什么（19 个产物，135 MB）

| 产物 | 大小 | 角色 |
| --- | --- | --- |
| `radar.db` | 45,273,088 B | 账本（SQLite 在线备份 API 生成的一致快照） |
| `graph.db` | 67,727,360 B | 图谱（派生物，单独备份只为省一次重建） |
| `radar.schema.sql` | 13.6 KB | `sqlite_master` 全文，迁移前的结构存档 |
| `deployed-code.tar.gz` | 27.6 MB | 部署目录 `releases/14eaf61…` 的完整 tar |
| `identity.txt` | 552 B | `DEPLOYED_SHA`、`var/DEPLOYED_SHA`、`readlink app` |
| `systemd/*.txt`（10 个） | 各若干 | 10 个相关 unit/timer 的 `systemctl cat` 全文 |
| `service-state.txt` | 64 KB | `systemctl list-units --all` 快照 |
| `config/radar-alpha.env.keys.txt` | — | **只有变量名**与文件 sha256，**没有值** |
| `config/pipeline.env.keys.txt` | — | 同上 |
| `sources-registry.json` | 8.9 KB | 当前部署的数据源注册表 |
| `MANIFEST.json` | 4.6 KB | 每个产物的路径、字节数、sha256；加 live WAL 状态 |

清单里的关键摘要：

```
radar.db   sha256 = c7961fe1a41262641ac55821226fcd66ed9f926f0d0069bfe2ff5fe1c25a65fe
graph.db   sha256 = （见 MANIFEST.json）
live_wal   radar.db: main 45,268,992 B + wal 4,280,712 B + shm 32,768 B
           graph.db: main 67,727,360 B + wal 0 + shm 0
ledger_meta schema_version = radar-ledger-v2, created_at 2026-11-17T00:13:33Z
```

### 1.1 为什么不能用"复制主文件"的方式

生产库处于 **WAL 模式**，且在备份时刻有 4.1 MB 未 checkpoint 的 WAL。直接 `cp radar.db` 会得到一个
缺少最近 4.1 MB 事务的文件。本轮用的是 **SQLite 在线备份 API**（`sqlite3.Connection.backup`），
它把主文件与 WAL 合并成一个一致快照：

```
备份文件 45,273,088 B  >  主文件 45,268,992 B
差值 ≈ WAL 中已合并的页（净效果），并且 integrity_check = ok
```

### 1.2 明确没有备份的东西

- **认证凭据的值**（`MEDRADAR_ALPHA_HASH`、`MEDRADAR_ALPHA_SESSION_SECRET` 等）：
  只记录了变量名与文件摘要。它们不属于"数据恢复"的对象，且不应离开主机。
- Cloudflare 隧道令牌（如果有）：同上。
- FDA 管线的 `pipeline.db` 与快照：本轮的发布对象是雷达，FDA 管线是**独立服务**，
  不随本次切换改变；它有自己的 `medradar-data-backup` 每日备份。

---

## 2. 恢复演练（实际执行，不是计划）

### 2.1 演练步骤

```
1. 把备份的 radar.db / graph.db 复制到 /srv/medradar/release-gate/001/restore-drill/v2/
2. 离线只读校验：integrity_check、foreign_key_check、journal_mode、计数
3. 抽查一条已知记录（PMID 43044098）的标识、内容哈希与版本链
4. 用**生产正在跑的代码**（releases/14eaf61）在 127.0.0.1:8795 起一个只读实例服务这份恢复数据
5. 访问 health / sources / feed / taxonomy
6. 关停，确认端口释放
```

### 2.2 演练结果

```
integrity_check    : ok
foreign_key_check  : clean（0 违规）
journal_mode       : wal
page_count         : 11053
schema_version     : radar-ledger-v2
observation        : 8360        observation_version : 8360
observation_change : 8360        observation_mapping : 8360
observation_admission: 8360      observation_facet   : 17285
source_state       : 6           sync_run            : 24     source_failure: 0
distinct sources   : crossref, draeger_official, openfda_device, philips_official, pubmed
earliest/latest first_observed : 2026-11-17T00:13:36Z .. 2026-11-18T18:24:45Z
admission tiers    : HIGH 7166 / LOW 682 / NEEDS_REVIEW 395 / IRRELEVANT 117
backup sha256      : c7961fe1…a65fe
restored sha256    : c7961fe1…a65fe      ← 完全一致
```

抽查记录（逐字段核对）：

```
observation_id 95f13f13…  PMID:43044098
title          Blood Pressure Estimation for Hemodynamic Monitoring Using Reduced
               Photoplethysmography Features in Intensive Care Units …
published_at   2026-11-17 (date)
first_observed 2026-11-18T00:23:02Z
latest_version c0932fa2… / version_seq 1 / payload_bytes 4227
content_hash   ef6258b2…  （与版本行一致）
crossref 水位线 2026-11-18，最后成功 2026-11-18T12:24:29Z
```

API 读取（用生产代码服务恢复出来的数据）：

```
/healthz              200   1 s 内就绪
/api/radar/health     200   1.371 s   state=ok   observations=8360
/api/radar/sources    200   0.041 s
/api/radar/feed       200   0.092 s   total=18
/api/radar/taxonomy   200   0.002 s
关停干净，127.0.0.1:8795 监听数归零
```

### 2.3 站外副本

同一份 `radar.db` 已复制到 `D:\DEPPSKK\release-gate-001\backup\`，
本地重新计算 sha256 = `c7961fe1…a65fe`，与清单一致，本地 `PRAGMA integrity_check = ok`，
观测数 8,360。

也就是说：**这台服务器整盘损坏时，账本仍有第二份可用的、被校验过的副本。**

---

## 3. 备份里最容易出问题的部分：systemd 与配置

- 10 个 unit/timer 的**全文**已存档。恢复时可以直接 `systemctl cat > /etc/systemd/system/…` 还原，
  不需要凭记忆重建。
- 环境文件**只存了变量名**。这是刻意的：把 `MEDRADAR_ALPHA_HASH` 复制进一个 tar 再放进仓库，
  等于把口令散播到无法追踪的地方。恢复时的正确做法是"由持有凭据的人重新生成"，而不是"从备份里解出来"。
  这一点在 `RELEASE_RUNBOOK.md` §6 的回滚清单里写明。

---

## 4. 迁移带来的一个新约束

v2 → v3 是**单向**的：旧代码（`14eaf61`）遇到 v3 库会在 `_ensure_schema` 里直接抛错
（`unsupported radar ledger schema`），**且不会修改任何数据**。所以：

> 一旦新版本写过一次，就不能只回滚代码 —— 必须同时换回 v2 数据。

这条约束决定了下面两条回滚路径的差别。

---

## 5. 两条回滚路径

### 5.1 路径 A：切换**前**回滚（零数据损失）

适用：候选服务已起、生产还没切。

```
- 停止候选进程（staging web / staging scheduler）
- 生产服务完全没有被触碰，仍在跑 14eaf61 + v2 库
- 数据损失：0
```

这是本轮的默认状态：生产从未被切换，所以现在随时可以"回滚"，成本为零。

### 5.2 路径 B：切换**后**回滚（有明确的、可量化的损失）

适用：新版本已经写过 v3 库，必须退回旧代码。

```
1. 先停止写者：systemctl stop medradar-radar-scheduler      ← 冻结写入
2. 保留现场：cp data/radar/radar.db  →  release-gate/rollback/radar.v3.<ts>.db
             （这一份是"新版本写过什么"的唯一证据，不能删）
3. 换回旧代码：ln -sfn releases/14eaf61… radar/app
4. 换回旧数据：cp <切换前备份>/radar.db  →  data/radar/radar.db
5. 启动：systemctl start medradar-radar-web ；再 start scheduler
6. 验证：radar verify（期望 integrity ok）、/healthz、/api/radar/health
```

**这一步会丢什么，必须说清楚：**

| 会丢 | 是否可恢复 | 说明 |
| --- | --- | --- |
| 切换后新采集的观测本身 | **可以**（重新采集即可） | 数据源还在，水位线允许重查；但 `first_observed_at` 会变成重采时间 |
| 切换后的 **首次发现时间** | **不可以** | 这是账本的核心语义（"我们什么时候知道的"），旧备份里没有 |
| 切换后源上已消失的记录 | **不可以** | 如果源在窗口内删除了记录，重采拿不到 |
| v3 的 8,360 条新判定 | **可以**（重新 `advance` 生成） | 判定是派生投影，旧备份里保留的是 v2 判定 |
| 切换后写入的 AI 队列任务 | 可以重建 | 队列是工作状态，不是证据 |

**量化**：按实测采集速率（正常节奏约 131 条/天；一次强制全量周期 1,330 条），
1 小时的切换后窗口通常新增 **< 10 条**观测。所以路径 B 的典型损失是"几条记录的首次发现时间"，
不是"整批数据"。

**如果连这点损失都不能接受**，正确做法不是"更小心地回滚"，而是**在切换前把窗口缩短**：
先冻结写者、确认 backlog 为 0、再切换，把"切换后到回滚"的窗口压到分钟级。
这套流程写在 `RELEASE_RUNBOOK.md` §3。

### 5.3 一条不要做的事

**不要**用"几小时前的候选数据库"去覆盖仍在写入的生产库。候选副本与生产之间必然有漂移
（本轮实测：备份后 25 分钟内漂移为 0 行，但那是因为调度器刚好没到点，不是机制保证）。
切换时必须按 `DATA_RECONCILIATION.md` 的流程处理这段差异。

---

## 6. 恢复能力的边界（诚实说明）

| 场景 | 能否恢复 | 依据 |
| --- | --- | --- |
| 账本文件损坏/误删 | ✅ 用备份恢复，已验证 | §2 |
| 迁移中途崩溃 | ✅ 本轮已修（`e4aaff6`），实测可恢复 | `MIGRATION_TEST.md` §4 |
| 代码回滚（未迁移） | ✅ 换符号链接即可，**无需动数据** | §5.1 |
| 代码回滚（已迁移） | ⚠️ 可执行，但会丢"切换后的首次发现时间" | §5.2 |
| 整盘损坏 | ✅ 站外副本存在（本机），但**只到本轮为止**；后续需要定期同步 | §2.3 |
| 凭据丢失 | ❌ 备份不含凭据值；必须重新生成 | §3 |

最后一条不是缺陷，是设计：把口令放进备份，会让"一份备份泄露"变成"全部认证失效"。
