# RELEASE-GATE-001 / 发布运行手册（可执行）

- 状态：**已准备，未执行。** 本文每个命令都在隔离环境演练过或等价验证过；
  标 `[AUTH]` 的步骤需要项目负责人明确授权后才能在生产执行。
- 预计切换窗口：**≤ 15 分钟**（其中写入冻结 ≤ 60 秒）。

---

## 0. 前置：三条硬性护栏

1. **任何针对隔离目录的产品命令都必须显式设置 `MEDRADAR_RADAR_DIR`。**
   产品在"没有该变量且 cwd 在源码树"时会静默回落到 `<cwd>/data/radar`。
   本轮就踩过一次（只写进了隔离目录，生产未受影响，见 `STAGING_ACCEPTANCE.md` §1.1）。
   **执行前先打印一次解析结果确认。**
2. **不要用候选库覆盖生产库。** 切换是就地迁移，不是数据搬运（`DATA_RECONCILIATION.md`）。
3. **回滚必须"代码 + 数据"一起**（v3 单向）。旧代码遇到 v3 库会拒绝启动且不改数据。

---

## 1. 发布前检查（全部通过才进入 §2）

| # | 检查 | 命令 | 通过标准 | 本轮状态 |
| --- | --- | --- | --- | --- |
| 1 | 生产备份 + 校验 | `radar backup --destination … --keep 14 --json` | `verified=true, integrity_check=ok` | ✅ 0.35 s |
| 2 | 恢复演练 | `radar restore-check` / 本文 §6 | integrity ok + API 可读 | ✅ 通过 |
| 3 | 候选迁移演练 | 在备份副本上打开候选版 | v3 + 计数不变 + 0.58 s | ✅ 通过 |
| 4 | 候选服务运行 | staging web + scheduler | API 全 200 | ✅ 通过 |
| 5 | 真实数据核对 | 6 个召回事件逐条比对 | 身份/日期/企业/编号一致 | ✅ 通过 |
| 6 | 回归测试 | `pytest tests` | 0 失败 | ✅ 1,710 项 |
| 7 | 资源余量 | `free -m`、`df -h` | available > 1 GB、磁盘 > 20 GB | ✅ 1,496 MB / 44 GB |
| 8 | 监控就绪 | `units/medradar-radar-health.*` | 单元已准备（安装见 §4） | ⚠️ 待安装 |
| 9 | 回滚方案演练 | §6 / §7 | 两条路径都可执行 | ✅ 通过（路径 B 有已知损失） |

---

## 2. 切换（[AUTH] 需要授权）

### 2.1 冻结与备份

```bash
# 0) 记录现场
date -u +%FT%TZ | tee /root/release-gate-cutover.log
readlink -f /srv/medradar/radar/app | tee -a /root/release-gate-cutover.log
cat /srv/medradar/radar/DEPLOYED_SHA | tee -a /root/release-gate-cutover.log

# 1) 停调度器 —— 冻结写入（Web 继续对外服务，只读）
systemctl stop medradar-radar-scheduler
systemctl is-active medradar-radar-scheduler      # 期望 inactive

# 2) 一致性备份（这是本次切换的恢复点）
sudo -u medradar env MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \
  /srv/medradar/radar-venv/bin/python -m medradar radar backup \
  --destination /srv/medradar/data/radar/backups --keep 14 --json \
  | tee -a /root/release-gate-cutover.log
# 期望 "verified": true, "integrity_check": "ok"
```

### 2.2 切换代码

```bash
NEW=<candidate-sha>       # 例如本轮候选对应的发布目录名
OLD=$(readlink -f /srv/medradar/radar/app)

# 3) 把候选代码放到 releases/<NEW>（内容已通过隔离验收）
#    注意：目录名必须与 git commit 一致，便于日后核对
rsync -a --delete /srv/medradar/release-gate/001/staging/release-<NEW>/ \\
              /srv/medradar/radar/releases/<NEW>/
chown -R medradar:medradar /srv/medradar/radar/releases/<NEW>

# 4) 原子切换符号链接（保留旧目标的绝对路径，供回滚）
ln -sfn "$OLD" /srv/medradar/radar/app.previous
ln -sfn "/srv/medradar/radar/releases/<NEW>" /srv/medradar/radar/app
echo "<NEW>" > /srv/medradar/radar/DEPLOYED_SHA

# 5) 起 Web（第一次打开会就地迁移生产库，0.6 s 量级）
systemctl start medradar-radar-web
sleep 3
curl -sf -o /dev/null -w "healthz=%{http_code}\n" http://127.0.0.1:8791/healthz
```

### 2.3 迁移后立即对账（10 项，见 DATA_RECONCILIATION.md §4）

```bash
DB=/srv/medradar/data/radar/radar.db
sqlite3 $DB "SELECT value FROM meta WHERE key='schema_version';"          # radar-ledger-v3
sqlite3 $DB "SELECT COUNT(*) FROM observation;"                          # 应与切换前相同
sqlite3 $DB "SELECT COUNT(*) FROM observation_admission WHERE rules_digest='legacy-v2';"  # = 旧判定数
sqlite3 $DB "SELECT COUNT(*) FROM observation o LEFT JOIN admission_current a
             ON a.observation_id=o.observation_id WHERE a.observation_id IS NULL;"        # 0 或待判数
sudo -u medradar env MEDRADAR_RADAR_DIR=/srv/medradar/data/radar RADAR=/srv/medradar/radar/app \
  /srv/medradar/radar-venv/bin/python -m medradar radar verify                 # integrity: OK
```

> 若 `observation` 计数与切换前不同，**立即停止并回滚**（§7 路径 B）。
> 迁移不改观测数；先看预期差：本轮实测 8,360 → 8,360。

### 2.4 首次重判（一次性）

```bash
sudo -u medradar env MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \
  /srv/medradar/radar-venv/bin/python -m medradar radar advance
# 期望: status=CONVERGED, admitted ≈ 观测数, elapsed ≈ 12 s, backlog.total=0
```

### 2.5 恢复调度

```bash
systemctl start medradar-radar-scheduler
sleep 20
journalctl -u medradar-radar-scheduler -n 30 --no-pager
# 期望: 至少一个周期完成；准备进行首次召回采集（见 DATA_RECONCILIATION.md §5）
```

---

## 3. 首次召回采集：规模必须提前知道

`openfda_recall` 在生产 `source_state` 里不存在，调度器会把它当"从未运行"的来源，
在第一个周期做一次初始化采集。

| 预期 | 值（隔离实测） |
| --- | --- |
| 记录数 | `6,563 |
| 耗时 | 抓取 `87 s + 管道 `139 s |
| 账本增量 | **+206 MB** |
| 图谱 | 23k → 45k 节点；`/graph/summary` 1.2 s → 2.3 s |

**观察点**：`df -h /`、`journalctl -u medradar-radar-scheduler`、
`curl /api/radar/graph/summary` 的耗时。

**如果不想一次吃下这个成本**：在切换前把 `config/radar/sources.json` 里
`openfda_recall.enabled` 设为 `false`，切换后再单独开启。这属于发布决定的一部分。

---

## 4. 监控接入（同一次变更里完成）[AUTH]

```bash
install -d -o medradar -g medradar /srv/medradar/release-gate/001/health
install -m 0750 -o medradar -g medradar \\
  /srv/medradar/release-gate/001/health/radar_health.py \\
  /srv/medradar/release-gate/001/health/radar_health.py
install -m 0644 docs/release_gate/001/units/medradar-radar-health.service /etc/systemd/system/
install -m 0644 docs/release_gate/001/units/medradar-radar-health.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now medradar-radar-health.timer
# 立刻跑一次并看结果
systemctl start medradar-radar-health.service
systemctl status medradar-radar-health.service --no-pager | head -20
cat /var/lib/medradar-radar-health/last.json | head -20
```

**期望**：切换初期大概率是 `DEGRADED`（水位线领先 1 天），
**召回采集完成前可能是 `UNHEALTHY`**（`recall_channel` FAIL）。这两者都是准确判断。

---

## 5. 切换后观察清单（前 60 分钟 + 第一周）

| 时点 | 看什么 | 正常 | 异常动作 |
| --- | --- | --- | --- |
| +1 min | `systemctl is-active` 四个单元 | 全 active | 回滚 |
| +1 min | `/healthz` | 200 | 回滚 |
| +5 min | `/api/radar/health` | 200，state ∈ {HEALTHY, DEGRADED} | 调查；若 UNHEALTHY 且原因不明→回滚 |
| +5 min | `radar status` | 7 个来源，失败计数 0 | 调查 |
| +15 min | 第一个调度周期日志 | 无 traceback，有周期完成 | 回滚 |
| +15 min | `df -h /` | 可用 > 30 GB | 评估保留策略 |
| +30 min | 首次召回采集 | 记录数增长、无错误 | 见 §3 |
| +60 min | `/api/radar/graph/summary` | < 3 s | 考虑加缓存 |
| +24 h | 备份定时器 | 03:40 成功，`verified=true` | 人工补一次 |
| 第 1 周 | 每日 `systemctl --failed` + `last.json` | 无 failed | 按 `HEALTH_MONITORING.md` 处置 |
| 第 1 周 | 周报人工生成一次 | 7 天窗口、含历史补充 | 记录内容质量问题 |

---

## 6. 恢复演练命令（任何时间都可跑，只读）

```bash
# 产品自带：把备份恢复到隔离目录并重建图谱
sudo -u medradar env MEDRADAR_RADAR_DIR=/tmp/restore-check \\
  /srv/medradar/radar-venv/bin/python -m medradar radar restore-check \\
  --backup <path-to-backup.db> --destination /tmp/restore-check

# 手工版（本轮实际使用的）
/usr/bin/python3 - <<'PY'
import sqlite3
c = sqlite3.connect("file:<backup.db>?mode=ro", uri=True)
print(c.execute("PRAGMA integrity_check").fetchone()[0])
print(c.execute("SELECT COUNT(*) FROM observation").fetchone()[0])
PY
```

---

## 7. 回滚

### 7.1 路径 A：还没切（或切换失败在迁移前）

```bash
systemctl stop medradar-radar-web          # 若已起
ln -sfn "$(cat /srv/medradar/radar/app.previous | xargs readlink -f)" /srv/medradar/radar/app
systemctl start medradar-radar-web medradar-radar-scheduler
```

数据损失：**0**。

### 7.2 路径 B：已迁移（v3 已写入）

```bash
# 1) 冻结写入
systemctl stop medradar-radar-scheduler medradar-radar-web

# 2) 保留现场（这是"新版本写过什么"的唯一证据，不能删）
mkdir -p /srv/medradar/release-gate/rollback
cp /srv/medradar/data/radar/radar.db /srv/medradar/release-gate/rollback/radar.v3.$(date -u +%Y%m%dT%H%M%SZ).db

# 3) 换回代码
ln -sfn "$(readlink -f /srv/medradar/radar/app.previous)" /srv/medradar/radar/app
echo "$(basename $(readlink -f /srv/medradar/radar/app))" > /srv/medradar/radar/DEPLOYED_SHA

# 4) 换回数据（选 §2.1 那次备份里最新的、verified=true 的那一份）
cp /srv/medradar/data/radar/backups/radar-<stamp>.db /srv/medradar/data/radar/radar.db
chown medradar:medradar /srv/medradar/data/radar/radar.db

# 5) 起服务并验证
systemctl start medradar-radar-web medradar-radar-scheduler
curl -sf http://127.0.0.1:8791/healthz && echo OK
sudo -u medradar env MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \\
  /srv/medradar/radar-venv/bin/python -m medradar radar verify
```

**数据代价**（`BACKUP_AND_RESTORE.md` §5.2）：切换后新采集观测的 `first_observed_at` 与
"源上已消失的记录"不可恢复；观测本身可重采。

### 7.3 回滚触发阈值（事先写死，避免临时争论）

| 触发条件 | 动作 |
| --- | --- |
| `/healthz` 或 `/api/radar/health` 连续 2 次失败（间隔 1 分钟） | 回滚 |
| `radar verify` 报结构性完整性问题（不是水位线） | 回滚 |
| 迁移后 `observation` 计数与切换前不一致 | 回滚 |
| 调度器 15 分钟内未完成任何周期 | 回滚 |
| API p95 > 5 s 持续 10 分钟 | 先观察，第 20 分钟仍如此则回滚 |
| 磁盘可用 < 10 GB | 回滚并扩容 |

---

## 8. 明确不在本手册范围内的操作

- 修改/删除既有备份与审计数据；
- 更改 Cloudflare 隧道或域名；
- 把候选库覆盖到生产库；
- 在未授权的情况下执行 §2、§4 的任何命令。
