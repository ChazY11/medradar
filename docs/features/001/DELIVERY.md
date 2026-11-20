# 摘要投递 / Delivery

---

## 1. 命令

```bash
python -m medradar radar digest --hours 24 --limit 5 [--format text|json] [--lang zh|en]
```

不加渠道参数时是 **dry run**：只打印，不外发。

| 参数 | 作用 |
| --- | --- |
| `--webhook URL` | POST `{"text": ..., "digest": ...}`（Slack 兼容） |
| `--smtp-host/--smtp-port/--smtp-from/--smtp-to/--smtp-user` | SMTP 投递 |
| `--smtp-no-starttls` | 内网明文 SMTP |
| `--dry-run` | 强制不外发 |

密码走环境变量 `MEDRADAR_SMTP_PASSWORD`，**不要**写在命令行（会进 shell 历史和 ps）。

---

## 2. 定时器（systemd）

`/etc/systemd/system/medradar-radar-digest.service`

```ini
[Unit]
Description=MedRadar daily digest delivery
After=medradar-radar-web.service

[Service]
Type=oneshot
User=medradar
Environment=HOME=/srv/medradar
Environment=PYTHONPATH=/srv/medradar/radar/app
EnvironmentFile=-/etc/medradar/digest.env
ExecStart=/srv/medradar/radar-venv/bin/python -m medradar radar digest \
  --hours 24 --webhook ${MEDRADAR_DIGEST_WEBHOOK}
```

`/etc/systemd/system/medradar-radar-digest.timer`

```ini
[Unit]
Description=Deliver the radar digest every morning

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl daemon-reload && systemctl enable --now medradar-radar-digest.timer
```

---

## 3. 行为

- 成功/失败都写入 `human.db` 的 `delivery` 表（渠道、状态、详情）
- 任一渠道失败 → 进程退出码 **1**，systemd 会把它标成 failed，可以在 `systemctl --failed` 看到
- 文本里包含：到货数、值得看的前 N 条（含官方链接）、安全与召回、待确认数、以及数据提示
  （未来日期、被策略封禁的来源）
