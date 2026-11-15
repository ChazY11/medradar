import type { TimelineItem } from "../api/devices";
import { useI18n } from "../i18n";
import { Badge, formatDate } from "./ui";

const KIND_STYLE: Record<string, { color: string; label: string }> = {
  "510k": { color: "var(--510k)", label: "510(k)" },
  pma: { color: "var(--pma)", label: "PMA" },
  pma_supplement: { color: "var(--pma_supplement)", label: "PMA supplement" },
  recall: { color: "var(--recall)", label: "Recall" },
};

/**
 * Regulatory timeline.
 *
 * Event date and first-observed date are shown separately, and the ordering is explicitly presented
 * as chronological evidence rather than causation: a supplement that precedes a recall does not
 * explain it.
 */
export function DeviceTimeline({ items }: { items: TimelineItem[] }) {
  const { bi } = useI18n();
  if (!items.length) {
    return <div className="muted small">{bi("No dated records for this device.", "该器械暂无带日期的记录。")}</div>;
  }
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="small muted">
        {bi(
          "Chronological order only. A later supplement, recall or approval is not evidence that an earlier event caused it.",
          "仅按时间排序。较晚的补充批准、召回或批准并不证明更早的事件导致了它。",
        )}
      </div>
      <ol className="device-timeline">
        {items.map((item) => {
          const style = KIND_STYLE[item.kind] ?? { color: "var(--text-3)", label: item.kind };
          return (
            <li key={item.event_id + item.kind + item.official_id} className="device-timeline-item">
              <span className="device-timeline-dot" style={{ background: style.color }} aria-hidden="true" />
              <div className="device-timeline-body">
                <div className="row wrap" style={{ gap: 8, alignItems: "baseline" }}>
                  <span className="mono small">{formatDate(item.date)}</span>
                  <Badge tone="outline">{item.kind_label || style.label}</Badge>
                  <a className="mono small" href={item.official_url} target="_blank" rel="noreferrer">
                    {item.official_id}
                  </a>
                  {item.relation_status === "confirmed" ? (
                    <span className="tiny muted">{bi("confirmed by official field", "由官方字段确认")}</span>
                  ) : null}
                </div>
                {item.detail ? <div className="small">{item.detail}</div> : null}
                <div className="tiny muted">
                  {bi("event date: ", "事件日期：")}
                  {item.event_date ?? bi("unknown", "未知")} - {bi("first observed by MedRadar: ", "MedRadar 首次采集：")}
                  {formatDate(item.first_observed_at)} ({item.date_note})
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
