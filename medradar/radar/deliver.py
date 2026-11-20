"""Send the daily digest somewhere a person will actually see it.

The capability scan in docs/research/001 found that every mature platform delivers into the
tool the reader already uses (email, Slack, webhook) rather than waiting to be visited. This
module is the smallest honest version of that: build the text, POST it to a webhook or send it
by SMTP, and record the attempt in the human store so "we sent yesterday's digest" is a fact
rather than a memory.

Two rules:

* **dry run is the default.** Nothing leaves the machine until a channel is configured explicitly.
* **a failed delivery is recorded, not swallowed.** The caller gets a non-zero exit code and the
  delivery table keeps the error.
"""
from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any, Mapping


def render_text(payload: Mapping[str, Any], *, lang: str = "zh") -> str:
    """A plain-text digest: counts, the top items, safety, what waits, and the caveats."""
    totals = payload.get("totals") or {}
    zh = lang != "en"
    lines: list[str] = []
    title = "MedRadar 今日摘要" if zh else "MedRadar daily digest"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")
    if payload.get("empty") or not totals.get("arrived"):
        lines.append("过去 24 小时没有新记录。" if zh else "No new records in the last 24 hours.")
        return "\n".join(lines)
    if zh:
        lines.append("过去 %s 小时新增 %d 条，其中 %d 条值得看，%d 条被判为与监护技术无关。" % (
            (payload.get("window") or {}).get("hours", 24), totals.get("arrived", 0),
            totals.get("feed", 0), totals.get("excluded", 0)))
    else:
        lines.append("%d record(s) arrived in the last %s hours; %d are worth a look, %d were "
                     "excluded as unrelated." % (totals.get("arrived", 0),
                                                 (payload.get("window") or {}).get("hours", 24),
                                                 totals.get("feed", 0), totals.get("excluded", 0)))
    lines.append("")
    items = payload.get("items") or []
    if items:
        lines.append("值得看：" if zh else "Worth a look:")
        for index, item in enumerate(items, 1):
            lines.append("%d. %s" % (index, item.get("title") or item.get("observation_id")))
            meta = "   %s" % (item.get("source") or "")
            stated = item.get("published_at") or item.get("event_at")
            if stated:
                meta += " · %s" % ("来源日期 " + stated if zh else "stated " + stated)
            if item.get("duplicates", 1) > 1:
                meta += (" · 已合并 %d 条" % item["duplicates"]) if zh else (
                    " · %d merged" % item["duplicates"])
            lines.append(meta)
            if item.get("source_url"):
                lines.append("   " + str(item["source_url"]))
        lines.append("")
    safety = payload.get("safety") or []
    lines.append("安全与召回：" if zh else "Safety and recalls:")
    if safety:
        for item in safety:
            lines.append("- %s" % (item.get("title") or "")[:100])
    else:
        lines.append("今天没有新的召回或安全通报。" if zh else "No new recall or safety notice today.")
    lines.append("")
    review = payload.get("review") or {}
    if review.get("count"):
        lines.append(("等你确认：%d 条" if zh else "Waiting for you: %d") % review["count"])
    for warning in payload.get("warnings") or []:
        code = warning.get("code")
        if code == "future_dated":
            lines.append(("注：%d 条来源日期在未来一周以上，已排在最后。" if zh else
                          "Note: %d record(s) state a future date and are sorted last.") % warning.get("count", 0))
        elif code == "blocked_sources":
            lines.append(("被策略封禁（不是故障）：%s" if zh else "Blocked by policy (not failing): %s")
                         % "、".join(warning.get("sources") or []))
    return "\n".join(lines)


def send_webhook(url: str, text: str, payload: Mapping[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    """POST a Slack-compatible body. The raw digest travels too, so nothing is lost in the text."""
    body = json.dumps({"text": text, "digest": payload}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": True, "status": response.status}
    except urllib.error.HTTPError as error:
        return {"ok": False, "status": error.code, "error": str(error)}
    except Exception as error:  # noqa: BLE001 - the caller records the failure
        return {"ok": False, "status": None, "error": f"{type(error).__name__}: {error}"}


def send_smtp(*, host: str, port: int, subject: str, text: str,
              sender: str, recipients: list[str], username: str | None = None,
              password: str | None = None, starttls: bool = True, timeout: float = 20.0) -> dict[str, Any]:
    if not recipients:
        return {"ok": False, "error": "no recipients configured"}
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(text)
    try:
        with smtplib.SMTP(host, port, timeout=timeout) as client:
            client.ehlo()
            if starttls:
                client.starttls()
                client.ehlo()
            if username and password:
                client.login(username, password)
            client.send_message(message)
        return {"ok": True, "recipients": len(recipients)}
    except Exception as error:  # noqa: BLE001 - the caller records the failure
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def deliver(payload: Mapping[str, Any], *, human, channels: Mapping[str, Any],
            lang: str = "zh", dry_run: bool = True) -> dict[str, Any]:
    """Send the digest through the configured channels and record every attempt."""
    text = render_text(payload, lang=lang)
    results: list[dict[str, Any]] = []
    webhook_url = str(channels.get("webhook") or "").strip()
    smtp_cfg = channels.get("smtp") or {}
    if dry_run or (not webhook_url and not smtp_cfg):
        human.record_delivery("dry-run", "skipped", {
            "reason": "dry run" if dry_run else "no channel configured",
            "characters": len(text),
        })
        return {"dry_run": True, "channel": "none", "text": text, "results": results}
    if webhook_url:
        outcome = send_webhook(webhook_url, text, payload)
        human.record_delivery("webhook", "ok" if outcome.get("ok") else "failed", outcome)
        results.append({"channel": "webhook", **outcome})
    if smtp_cfg:
        outcome = send_smtp(
            host=str(smtp_cfg.get("host") or ""), port=int(smtp_cfg.get("port") or 587),
            subject=str(smtp_cfg.get("subject") or "MedRadar daily digest"), text=text,
            sender=str(smtp_cfg.get("sender") or ""),
            recipients=list(smtp_cfg.get("recipients") or []),
            username=smtp_cfg.get("username"), password=smtp_cfg.get("password"),
            starttls=bool(smtp_cfg.get("starttls", True)),
        )
        human.record_delivery("smtp", "ok" if outcome.get("ok") else "failed", outcome)
        results.append({"channel": "smtp", **outcome})
    return {"dry_run": False, "results": results, "text": text}