import { useState } from "react";
import { useAsync } from "../api/hooks";
import { getAudit, getReviewQueue, setReview, type ReviewState } from "../api/human";
import { useI18n } from "../i18n";
import { Badge, Card, EmptyState, PageHeader } from "../components/ui";
import { AsyncSection } from "../components/async";

const STATES: ReviewState[] = ["NEW", "REVIEWING", "CONFIRMED", "DISMISSED"];
const STATE_ZH: Record<ReviewState, string> = {
  NEW: "待处理",
  REVIEWING: "看过了",
  CONFIRMED: "已确认",
  DISMISSED: "已排除",
};

/** What a person decided, and what is still waiting for one. */
export function ReviewQueuePage() {
  const { bi } = useI18n();
  const [status, setStatus] = useState<string | undefined>(undefined);
  const queue = useAsync(() => getReviewQueue(status), [status]);
  const audit = useAsync(() => getAudit(30), []);

  const move = async (observationId: string, next: ReviewState) => {
    await setReview(observationId, { status: next });
    queue.reload();
    audit.reload();
  };

  return (
    <>
      <PageHeader
        eyebrow={bi("Human judgement", "人工判定")}
        title={bi("Review queue", "评审队列")}
        description={bi(
          "Records you have looked at, and records still waiting. A decision here never modifies the evidence ledger; it is recorded beside it, with who did it and when.",
          "你看过的记录，和还在等你的记录。这里的判定不会改动证据账本，它单独记录在旁，并留下谁、什么时候。",
        )}
      />
      <Card
        title={bi("Queue", "队列")}
        note={bi("Filter by state. Counts come from the review store, not from the feed.", "按状态筛选；计数来自评审存储，不是情报流。")}
        actions={
          <div className="row wrap" style={{ gap: 6 }}>
            <button type="button" className="chip" aria-pressed={!status} onClick={() => setStatus(undefined)}>
              {bi("All", "全部")}
            </button>
            {STATES.map((state) => (
              <button
                key={state}
                type="button"
                className="chip"
                aria-pressed={status === state}
                onClick={() => setStatus(state)}
              >
                {bi(state, STATE_ZH[state])}
                {queue.data?.stats?.by_status?.[state] ? (
                  <span className="small muted"> ({queue.data.stats.by_status[state]})</span>
                ) : null}
              </button>
            ))}
          </div>
        }
      >
        <AsyncSection status={queue.status} data={queue.data} error={queue.error} reload={queue.reload}>
          {(payload) =>
            payload.items.length === 0 ? (
              <EmptyState
                title={bi("Nothing in this state", "这个状态下没有记录")}
                description={bi(
                  "Open a record in the live radar and mark it; it will appear here.",
                  "在实时雷达里打开一条记录并做判定，它就会出现在这里。",
                )}
              />
            ) : (
              <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
                {payload.items.map((row) => (
                  <li key={row.observation_id} style={{ marginBottom: 10 }}>
                    <div className="row wrap" style={{ gap: 6, alignItems: "baseline" }}>
                      <Badge tone={row.status === "CONFIRMED" ? "ok" : row.status === "DISMISSED" ? "neutral" : "warn"}>
                        {bi(row.status, STATE_ZH[row.status])}
                      </Badge>
                      <a href={row.source_url || undefined} target="_blank" rel="noreferrer noopener">
                        {row.title || row.observation_id}
                      </a>
                    </div>
                    <div className="small muted">
                      {row.source || ""} · {row.updated_at?.slice(0, 16).replace("T", " ")}{" "}
                      {row.note ? "· " + row.note : ""}
                    </div>
                    <div className="row wrap" style={{ gap: 6, marginTop: 4 }}>
                      {STATES.filter((state) => state !== row.status).map((state) => (
                        <button
                          key={state}
                          type="button"
                          className="chip"
                          onClick={() => move(row.observation_id, state)}
                        >
                          {bi("Mark " + state, "标为" + STATE_ZH[state])}
                        </button>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
        </AsyncSection>
      </Card>

      <Card title={bi("Audit trail", "审计记录")} note={bi("Every write the human side performed.", "人工侧执行的每一次写入。")}>
        <AsyncSection status={audit.status} data={audit.data} error={audit.error} reload={audit.reload} loadingLines={3}>
          {(payload) => (
            <table className="table">
              <thead>
                <tr>
                  <th>{bi("When", "时间")}</th>
                  <th>{bi("What", "动作")}</th>
                  <th>{bi("Target", "对象")}</th>
                </tr>
              </thead>
              <tbody>
                {payload.items.map((row) => (
                  <tr key={row.seq}>
                    <td className="small muted">{row.at.slice(0, 16).replace("T", " ")}</td>
                    <td className="small">{row.action}</td>
                    <td className="small muted mono">{row.target || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </AsyncSection>
      </Card>
    </>
  );
}