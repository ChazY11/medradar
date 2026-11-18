# FINAL-PREFLIGHT-001 / staging 健康监控实装

- 目标：把 RELEASE-GATE-001 设计好的探针**真正装上**并在隔离环境跑起来
- 结果：**已安装为 systemd 服务 + 定时器**，每 2 分钟运行，故障能被识别（见 `FAULT_INJECTION_RESULTS.md`）
- 生产接入：**未安装**（属于发布门禁，脚本已备好）

---

## 1. 装了什么

| 单元 | 作用 | 状态 |
| --- | --- | --- |
| `medradar-staging-web.service` | 候选版本 Web（127.0.0.1:8792，Alpha 门开启） | active |
| `medradar-staging-scheduler.service` | 候选版本采集调度（独立账本） | active |
| `medradar-staging-health.service` | 三层健康探针（oneshot） | 每次运行后 inactive，失败则 failed |
| `medradar-staging-health.timer` | 每 2 分钟触发探针 | active |

探针脚本：`/srv/medradar/release-gate/001/health/radar_health.py`
状态快照：`/var/lib/medradar-staging-health/last.json`（每次覆盖）
日志：journald（`journalctl -u medradar-staging-health.service`）

**这些是新增单元，没有修改任何生产单元。** 生产侧仍是 `medradar-radar-*` 原样。

---

## 2. 关键配置（以及为什么这么配）

### 2.1 写权限：WAL 需要目录写权限

```
ReadWritePaths=/var/lib/medradar-staging-health /srv/medradar/release-gate/001/staging/data
```

**这是故障注入发现的缺陷。** 探针以只读方式打开账本（`mode=ro`），但 SQLite 在 WAL 模式下
即使只读也需要创建/映射 `-shm` 文件；单元默认 `ProtectSystem=strict` 且没有该目录的写权限，
于是探针报 `OperationalError: unable to open database file`，把一个健康系统判成 UNHEALTHY。

修正：给探针所在的单元授予数据目录的写权限（探针本身不写业务数据）。
生产接入时同样需要 `ReadWritePaths=/srv/medradar/data/radar`。

### 2.2 不调用受门保护的 API

```
api_probe: skipped: the alpha gate protects the API and counts unauthenticated calls as
           failed credentials; liveness is verified through /healthz and the ledger is read directly
```

**这也是故障注入发现的缺陷。** 第一版探针每次运行都去请求 `/api/radar/health`，
Alpha 门把每次 401 都算成"认证失败"，几次之后回环地址被锁定，探针开始收到 **HTTP 429**，
于是一个本来健康的系统被判成 UNHEALTHY —— 而且这个锁定恰好也会挡住同一 IP 的真实用户。

修正：定时探针**不碰受门保护的 API**，只用免认证的 `/healthz` 做存活判断，数据层面直接读账本。
需要"带认证的 API 探针"时可手动加 `--api-probe user:password`，默认关闭。

### 2.3 崩溃时必须留下 UNKNOWN

探针若自身抛异常，会写一份 `state: UNKNOWN` + `probe_error` 的快照。
否则磁盘上会留着上一次的 "DEGRADED/HEALTHY"，一个坏掉的探针会被误读成"一切正常"。

### 2.4 失败要能在 systemctl 里看见

去掉了 `SuccessExitStatus=0 1 2`。现在 UNHEALTHY（exit 1）会让单元变成 `failed`，
出现在 `systemctl --failed` 里；DEGRADED（exit 0）仍是成功。
**没有通知渠道**，可观察面是：`systemctl --failed`、journal、`last.json`。

---

## 3. 三层检查（实测输出）

```
state: DEGRADED
  avail port        ok   127.0.0.1:8792
  avail healthz     ok   200 in 35.7 ms
  avail api_probe   ok   skipped (alpha gate)
  avail spa_index   ok   …/release-b6f4506…/web/dist/index.html
  product ledger_integrity  PASS
  product ledger_writable   UNKNOWN  (read-only connection; the writer proves it)
  product recall_channel    PASS     recall channel present with 6563 records
  product brief_generation  PASS     generated in 1.29 s
  pipeline critical_sources     PASS   every monitored source checked inside its cadence
  pipeline watermark_legal      WARN   a watermark leads the UTC date by 1 day (inside grace)
  pipeline scheduler_heartbeat  PASS   35.8 s since the last cycle (budget 64,800 s)
  pipeline acquisition_progress PASS
```

DEGRADED 的唯一原因是**真实存在的水位线领先 1 天**（crossref/pubmed），
不是探针噪声。这条在 `HEALTH_MONITORING.md`（RELEASE-GATE-001）里已解释并分级。

---

## 4. 与目标服务的对应关系

| 监测对象 | 怎么监测 | 实测 |
| --- | --- | --- |
| Radar 生产目标（8791）的候选配置 | 单元模板里参数化；staging 用 8792 验证 | 同一份脚本，只改 `--port/--radar-dir` |
| Staging 独立服务 | `medradar-staging-*` | 7 种故障全部命中 |
| API | `/healthz`（免认证）+ 账本直读 | 门被正确识别为"受保护"而非故障 |
| 数据库 | `ledger_writable` / `ledger_integrity` / 打开失败 | F2 命中 |
| Ledger | 同上 + 结构完整性 | 常态 PASS |
| Admission | `admission_current` 覆盖 + 历史 | 常态 PASS |
| 召回来源 | `recall_channel`（记录数 > 0） | staging 6,563 条 PASS；生产 0 条 → **FAIL**（真实缺口） |
| 增量调度 | `scheduler_heartbeat` | F5 命中 |
| 水位线 | `watermark_legal` | F3 命中 |
| 服务端错误 | 单元失败 + journal | F1/F2 命中 |
| 长期未运行 | `critical_sources` 的"从未检查/超过 3× cadence" | 逻辑在，回归测试覆盖 |
| 任务失败 | `consecutive_failures ≥ 3` | F4 命中 |

---

## 5. 生产接入步骤（已备好，未执行）

```bash
# [AUTH] 需要发布授权
install -d -o medradar -g medradar /srv/medradar/release-gate/001/health
install -m 0750 -o medradar -g medradar \
  /srv/medradar/release-gate/001/health/radar_health.py /srv/medradar/release-gate/001/health/
# 单元文件：docs/release_gate/001/units/medradar-radar-health.{service,timer}
# 关键行：Environment=MEDRADAR_CODE_ROOT=/srv/medradar/radar/app
#          --radar-dir /srv/medradar/data/radar --port 8791
#          ReadWritePaths=/var/lib/medradar-radar-health /srv/medradar/data/radar
systemctl daemon-reload
systemctl enable --now medradar-radar-health.timer
systemctl start medradar-radar-health.service
cat /var/lib/medradar-radar-health/last.json
```

**不会**影响独立 FDA 管线（不同单元、不同目录、不共享端口）；
**不会**与旧服务争用端口（探针不监听）；**不会**产生第二个写入者（探针只读 + 写自己的状态文件）；
**不会**暴露内部健康端点（`/healthz` 本来就是公开的存活探针，且不含数据）。

---

## 6. 明确未完成的部分

| 项 | 状态 |
| --- | --- |
| 外部通知渠道（邮件/IM/webhook） | **未配置**。不声称具备主动告警能力。故障只在 `systemctl --failed`、journal、`last.json` 里可见。 |
| 生产单元安装 | **未安装**（发布门禁项） |
| 日志保留策略 | 未改 journald 配置（系统级决策，建议 `SystemMaxUse=1G`） |
| 服务器重启后的行为 | **未测**（不许重启生产机）。单元配置了 `After=` 与 `Wants=`，但这是配置推断，不是实测。 |
