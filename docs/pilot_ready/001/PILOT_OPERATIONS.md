# PILOT-READY-001 / 阶段七：四周试验的运行机制

- 试验状态：**NOT STARTED**
- 原因：**尚未确定任何真实研发负责人参与。** 本文只准备机制，不伪造任何一周、任何一条用户反馈。
- 原则：**复用已有组件，不新建用户管理平台。**

---

## 1. 已有组件盘点（先看有什么，再决定加什么）

| 能力 | 现有组件 | 状态 | 缺口 |
| --- | --- | --- | --- |
| 稳定调度 | `medradar-radar-scheduler.service`（`--interval 300`，`Restart=always`，`NRestarts=0`） | ✅ 运行中 | 无 |
| 采集失败可观察 | `source_state.consecutive_failures`、`source_failure` 表、`journalctl`、`runtime_state.last_cycle` | ✅ 存在 | 只写日志，**无主动告警通道** |
| 关键能力健康判定 | 候选版本 `system_status`（六项检查、四态） | ✅ 已实现，**未部署** | 需接线（见 §4.1） |
| 既有健康检查覆盖雷达 | `/usr/local/bin/medradar-health` 只探 8787 | ❌ | 需扩展 |
| 周报生成 | `python -m medradar radar brief --since … --until … --output …`（实测 0.75 s） | ✅ 可手工执行 | **无定时器** |
| 原始证据存储 | `radar.db`（append-only）+ 每日在线备份（14 份）+ `restore-drill` | ✅ | 两处备份目录需统一（见 §4.3） |
| 人工审核记录 | `--review <json>` + `review_status` 字段 + 现成的 `_evidence/review_2026-11-18.json` 格式 | ✅ | 无版本化目录约定 |
| 周报版本记录 | 文件命名 `WEEKLY_BRIEF_00N.md`（`docs/v1/001` 已在用） | ✅ 够用 | 需固定到 `docs/pilot_ready/briefs/` 并纳入 git |
| 用户反馈记录 | `PILOT_FEEDBACK_TEMPLATE.csv`（`week,item,verdict,reason,action_taken,minutes_spent,participant`） | ✅ | 无参与者 |
| 独立对照事件 | `_evidence/reference_events.json` 结构 + `scripts/verify_reference_events.py` | ✅ | 需每周新建一份 |

**结论：需要的机制 90% 已经存在**，缺的是把三样东西接起来：**定时器、健康覆盖、稳定入口**，以及一个人。

---

## 2. 每周固定流程（沿用 `docs/v1/001/PILOT_PROTOCOL.md`，不重新发明）

| 时点 | 动作 | 谁 | 产物 |
| --- | --- | --- | --- |
| 周一 06:00（定时器） | 采集 + 判定 + 生成候选周报 | 系统 | `docs/pilot_ready/briefs/WEEKLY_00N.generated.md` |
| 周一 上午（≤45 min） | 人工复核：逐条打开官方链接、修正、标注 `review_status` | 运营者 | `reviews/WEEKLY_00N.review.json` |
| 周一 上午（≤30 min） | 生成给读者看的版本（取舍 + 研发关注点） | 运营者（可用 Agent 起草） | `WEEKLY_00N.md` |
| 周一 下午（≤90 min） | 独立对照检索（固定检索式，执行者不看本周周报） | 另一位同事 | `reference_events_weekN.json` |
| 周二 | 发出周报 + 反馈表 | 运营者 | — |
| 周二–周四 | 阅读 ≤30 min，逐条打分 | 参与者 | `feedback_weekN.csv` |
| 周五 | 汇总指标、记录人工工作量 | 运营者 | `metrics_weekN.json` |

**人工工作量预算**：复核 45 min + 对照 90 min + 汇总 30 min ≈ **2.75 小时/周**。
这个数字必须与参与者花的时间（≤30 min）分开记录——否则"值不值得做"会被混淆。

---

## 3. 指标（沿用已登记的假设与阈值，不在试验中途修改）

来自 `docs/v1/001/PILOT_PROTOCOL.md`，本轮**不修改、不放宽**：

- **H1**：一位 ICU / 床旁监护产品线研发负责人，每周 ≤30 分钟，能获得**至少一条此前不知道、且可据以
  行动或转发**的安全/性能信息。
- **推翻条件**（任一成立即 H1 不成立）：连续 2 周无人打开；4 周内"有价值且新" ≤1 条；
  半数以上反馈为"我已经知道"/"与我无关"；单期人工复核持续 >2 小时。

周指标：

| 指标 | 分母 | 已知限制 |
| --- | --- | --- |
| 参考事件召回率 | 本周独立参考集 | 参考集是**下界**，不是真理 |
| 正式条目精确率 | 被用户评分的条目 | 未评分的**不计入分母但必须报出** |
| 重要事件漏检数 | 本周参考集中的 CRITICAL/HIGH | "重要"由运营者判定并附理由 |
| 单期人工工时 | — | 与参与者阅读时长分开统计 |
| 条目来源分布 | 本周正式条目 | 用于发现"全是论文/全是召回"的偏斜 |

**新增一条本轮建议的指标（不改 H1）**：`自动候选 → 人工保留` 的比例。
本周实测是 17 → 3（保留率 18%），这是衡量自动筛选精度的直接数字，也是判断"能不能自动化"的依据。

---

## 4. 启动前必须完成的三件事

### 4.1 健康检查覆盖雷达（阻塞项）

现状：`/usr/local/bin/medradar-health` 只检查 8787（旧工作台）。雷达与调度器完全不在覆盖范围内。

最小改动（不新增平台）：在现有脚本里加两行探测，并复用新的 `radar status --json`：

```bash
# 雷达存活（无认证，只报存活）
code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:8791/healthz")
[ "$code" = "200" ] || { crit=1; add "radar_http:$code"; }

# 雷达健康判定（读写连接才能真正测可写性）
state=$(sudo -u medradar env MEDRADAR_RADAR_DIR=/srv/medradar/data/radar         PYTHONPATH=/srv/medradar/radar/app         /srv/medradar/radar-venv/bin/python -m medradar radar status --json 2>/dev/null         | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])')
[ "$state" = "HEALTHY" ] || { warn=1; add "radar_state:$state"; }
```

> 注意：`radar status` 会以读写方式打开账本以实测可写性。这**不会**写入业务数据
> （`BEGIN IMMEDIATE` 后立即 `ROLLBACK`），但会短暂持有写锁。放在 5 分钟粒度的定时器里可接受。

### 4.2 周报定时器（阻塞项）

```ini
# /etc/systemd/system/medradar-radar-brief.service
[Unit]
Description=MedRadar candidate weekly brief (read-only generation)
After=medradar-radar-scheduler.service
[Service]
Type=oneshot
User=medradar
WorkingDirectory=/srv/medradar/radar/app
Environment=MEDRADAR_RADAR_DIR=/srv/medradar/data/radar
ExecStart=/srv/medradar/radar-venv/bin/python -m medradar radar brief \
  --since %H --until %H --output /srv/medradar/data/radar/briefs/WEEKLY_%Y%m%d.generated.md
```

```ini
# /etc/systemd/system/medradar-radar-brief.timer
[Unit]
Description=Generate the candidate weekly brief every Monday 06:00 local
[Timer]
OnCalendar=Mon 06:00
Persistent=true
[Install]
WantedBy=timers.target
```

（`%H/%Y%m%d` 在 `ExecStart` 里不会被 systemd 展开——落地时需要一个小包装脚本计算日期。
这里保留原样是为了说明**契约**：产物必须是"按周命名、可追溯、落到固定目录"的文件。）

### 4.3 备份目录统一（阻塞项）

现有两处雷达备份：`/srv/medradar/data/radar/backups`（由 `medradar-radar-backup` 管理，保留 14 份）
与 `/srv/medradar/backups/radar`（2026-11-17 遗留，未纳入保留策略）。
恢复时必须只有一个正确答案。建议：保留前者，把后者改名归档或删除（**需要授权**）。

---

## 5. 已知的运行风险（四周跨度上真正会造成麻烦的）

| # | 风险 | 对四周试验的影响 | 缓解 |
| --- | --- | --- | --- |
| P1 | **公网入口是 Cloudflare Quick Tunnel 临时域名** | 隧道重连可能换域名，用户收藏的链接失效；这正是"连续 2 周无人打开"的最可能原因（而不是用户不感兴趣） | 试验前换成命名隧道或自有域名；若做不到，每周发信时附新链接并核对 |
| P2 | 部署版本没有召回通道 | 周报里将**没有安全事件**，产品最核心的承诺缺失 | 切换候选版本并回填一次（见 DEPLOYMENT_READINESS §9 R6） |
| P3 | 自动筛选精确率不足（17→3） | 若不人工筛选，读者第一眼看到的是胎儿 ECG、滑坡监测 | 保持"人工取舍"这一步；同时把精确率记为改进目标 |
| P4 | "更新/撤下"路径生产覆盖率为零 | 若第一周发生真实状态变化，是对系统的一次真实检验，也可能是第一次暴露缺陷 | 在 metrics 里专门记录"本周是否出现 UPDATED/REMOVED" |
| P5 | 无主动告警通道 | 失败只有日志，靠人看 | 试验期由运营者每日花 2 分钟看 `radar status` + `journalctl`；不为此新建告警平台 |
| P6 | 参与者只有 1 人时结论只是个案 | 不能表述为"用户研究" | 在最终报告里明确样本量 |

---

## 6. 试验状态的诚实定义

- 现在：**NOT STARTED**。没有参与者、没有第 1 周、没有一条反馈。
- 启动条件：§4 三项完成 + 至少 1 位真实研发负责人确认参与 + 一个稳定可复制的入口链接。
- 启动后：每周一份 `WEEKLY_00N.md` + 一份 `review` + 一份 `reference_events` + 一份 `feedback CSV`；
  全部进 git，形成可追溯的版本链。
- **不得**在没有参与者的情况下填写任何 `feedback_weekN.csv`、不得写"用户认为…"、
  不得把 Agent 的自评当作反馈。
