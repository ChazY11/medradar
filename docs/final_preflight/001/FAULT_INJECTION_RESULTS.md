# FINAL-PREFLIGHT-001 / 故障注入结果

- 对象：已安装的 staging 监控（`medradar-staging-health.service` + timer）
- 方法：人为制造 7 种故障，每种植入后**运行一次探针**，读取 `last.json`、单元结果与恢复后的状态
- 结果：**6 种故障全部被识别；"来源安静无新增"正确地没有被判为故障。**
- 附带收获：注入过程本身暴露了监控的 2 个缺陷（见 §4），已修复

---

## 1. 七种故障与判定

| # | 故障 | 怎么造 | 监控判定 | 命中证据 | 恢复后 |
| --- | --- | --- | --- | --- | --- |
| F1 | 服务停止 | `systemctl stop medradar-staging-web` | **UNHEALTHY** | `port`、`healthz` FAIL | DEGRADED |
| F2 | 数据库不可读 | `chmod 000 radar.db`（服务仍在跑） | **UNHEALTHY** | `ledger_open: FAIL`（OperationalError） | DEGRADED |
| F3 | 异常未来水位线 | pubmed 水位线设为 `2027-02` | **UNHEALTHY** | `watermark_legal: FAIL/CRITICAL`，`max_lead_days` | DEGRADED |
| F4 | 核心来源持续失败 | `consecutive_failures=3` on pubmed | **UNHEALTHY** | `critical_sources: FAIL`，reason "3 consecutive failed checks" | DEGRADED |
| F5 | 调度器停摆 | `last_cycle.finished_at` 改为 2026-11-01 | **UNHEALTHY** | `scheduler_heartbeat: FAIL`，1,542,857 s vs 预算 64,800 s | DEGRADED |
| F6 | 来源正常但无新增 | 真实 `radar run --source openfda_device` → NO_NEW_RECORDS | **DEGRADED（未升级）** | 只有既有的 watermark WARN，没有新告警 | 不适用（本就不该报故障） |
| F7 | 监控单元重启 | `systemctl restart medradar-staging-health.timer` | 正常 | 下一次运行成功，无需人工干预 | 不适用 |

### 1.1 判定结果原文（关键三条）

F4（确定性运行，直接调单元）：

```
state: UNHEALTHY
  pipeline critical_sources FAIL | {'sources': [{'source_id': 'pubmed', 'status': 'FAILED',
      'consecutive_failures': 3, 'critical': True, 'reason': '3 consecutive failed checks'}]}
```

F5：

```
state: UNHEALTHY
  scheduler_heartbeat FAIL | {'seconds_since_cycle': 1542857.4, 'budget_seconds': 64800.0,
      'last_cycle': {'finished_at': '2026-11-01T00:00:00Z', 'status': 'OK'}}
```

F6（不得误报）：

```
state: DEGRADED      ← 与故障前相同的状态，没有因为"没有新数据"而升级
pipeline: watermark_legal WARN（这是既有的真实问题），其余 PASS
```

---

## 2. 检测延迟

| 项 | 值 |
| --- | --- |
| 探针单次运行耗时 | 1.7–1.8 s（含账本读取与周报生成检查） |
| 定时器周期 | 2 分钟 |
| **最坏检测延迟** | **≈ 2 分钟 + 1.8 s**（定时器下次触发） |
| 按需检测 | 立即（手动 `systemctl start medradar-staging-health.service`） |
| 故障恢复后的状态更新 | 下一个周期（≤2 分钟） |

注意：`ledger_writable` 在探针的只读连接上是 UNKNOWN（设计如此）；
真正不可写时写进程会停，进而心跳超时 → UNHEALTHY。这条因果链没有在本轮单独注入（属于生产行为）。

---

## 3. 误报检查

| 情形 | 是否误报 |
| --- | --- |
| 来源连续多天没有新内容 | 否 —— F6 证明不升级 |
| 只读连接无法测写入 | 否 —— 报 UNKNOWN，不报 FAIL |
| Alpha 门返回 401 | 否 —— 认定为"受保护"，且不再调用（见 §4.1） |
| 水位线领先 1 天（源时区） | 否 —— WARN/DEGRADED，不是 UNHEALTHY |

**唯一的常态告警**是 watermark WARN，而它对应一个**真实存在**的数据问题
（crossref/pubmed 水位线是 2026-11-19，比 UTC 晚一天）。这不是噪声。

---

## 4. 故障注入暴露的两个监控缺陷（已修）

### 4.1 探针把自己锁死了

第一版探针每轮都请求 `/api/radar/health`。Alpha 门把每次 401 计为认证失败，
几轮之后回环地址被锁定，探针收到 **HTTP 429**，于是报告 UNHEALTHY ——
一个健康系统被判故障，而且这个锁定同样会挡住同 IP 的真实用户。

修复：定时探针不再调用受门保护的 API；用 `/healthz`（免认证）+ 账本直读。
带认证的 API 探针改为手动可选（`--api-probe user:password`）。

### 4.2 WAL 只读打开也需要目录写权限

第二版探针在单元里以 `ProtectSystem=strict` 运行且没有数据目录的写权限，
SQLite 在 WAL 模式下即使 `mode=ro` 也需要创建 `-shm`，于是报
"unable to open database file"，健康系统被判 UNHEALTHY。

修复：单元加 `ReadWritePaths=<data dir>`（探针不写业务数据，只为 SQLite 的共享内存文件）。

### 4.3 探针崩溃会留下陈旧结论

如果探针自身抛异常，磁盘上会保留上一次的结论，看起来像"一切正常"。
修复：崩溃时写 `state: UNKNOWN` + `probe_error`，并返回 2。

---

## 5. 未能测试的项

| 项 | 原因 |
| --- | --- |
| 服务器重启后的依赖行为 | 未授权重启生产机；隔离机重启也超出本轮范围。单元的 `After=/Wants=` 只是配置，不是实测。 |
| 真实网络分区 | 需要切断服务器出网，风险过高 |
| 通知渠道端到端 | 未配置通知渠道（明确标注未完成） |
| 生产环境上的同一套探针 | 生产监控安装属于发布门禁，未执行 |

---

## 6. 结论

- 监控**真的装上了**（systemd 服务 + 2 分钟定时器），不是只写了单元文件。
- 6 类故障全部被识别为 UNHEALTHY，且诊断信息能指出具体原因。
- "没有新数据"没有被误判为故障。
- 故障注入本身修掉了 3 个监控缺陷——这正是它存在的理由。
- **监控不再是发布阻塞**，但生产接入仍需在执行切换时完成（门禁项 C2）。
