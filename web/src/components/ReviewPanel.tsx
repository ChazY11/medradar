import { useState } from "react";
import { useAsync } from "../api/hooks";
import { getReview, setReview, type ReviewState } from "../api/human";
import { useI18n } from "../i18n";

const STATES: ReviewState[] = ["NEW", "REVIEWING", "CONFIRMED", "DISMISSED"];

const STATE_ZH: Record<ReviewState, string> = {
  NEW: "待处理",
  REVIEWING: "看过了",
  CONFIRMED: "已确认",
  DISMISSED: "已排除",
};

/** Record what a person concluded about one record. Writes the side store, never the ledger. */
export function ReviewPanel({ observationId }: { observationId: string }) {
  const { bi } = useI18n();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const review = useAsync(() => getReview(observationId), [observationId]);

  const apply = async (status?: ReviewState) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await setReview(observationId, {
        ...(status ? { status } : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
      });
      setNote("");
      review.reload();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setBusy(false);
    }
  };

  const current = review.data?.review?.status;
  return (
    <section style={{ marginTop: 16 }}>
      <h3 className="h4">{bi("Your judgement", "你的判定")}</h3>
      <div className="row wrap" style={{ gap: 6, marginBottom: 8 }}>
        {STATES.map((state) => (
          <button
            key={state}
            type="button"
            className="chip"
            aria-pressed={current === state}
            disabled={busy}
            onClick={() => apply(state)}
          >
            {bi(state, STATE_ZH[state])}
          </button>
        ))}
      </div>
      <div className="row" style={{ gap: 6 }}>
        <input
          className="input"
          placeholder={bi("Add a note and press Enter", "写一句备注，回车保存")}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") apply();
          }}
        />
        <button type="button" className="btn sm" disabled={busy || !note.trim()} onClick={() => apply()}>
          {bi("Save note", "保存备注")}
        </button>
      </div>
      {review.data?.review ? (
        <p className="small muted" style={{ marginBottom: 0 }}>
          {bi("Current", "当前")}: {bi(review.data.review.status, STATE_ZH[review.data.review.status])}
          {review.data.review.note ? " · " + review.data.review.note : ""}
          {review.data.review.updated_at ? " · " + review.data.review.updated_at.slice(0, 16).replace("T", " ") : ""}
        </p>
      ) : null}
      {review.data?.history?.length ? (
        <details style={{ marginTop: 6 }}>
          <summary className="small muted">
            {bi("History", "历史")} ({review.data.history.length})
          </summary>
          <ul className="small muted" style={{ margin: "6px 0 0 0" }}>
            {review.data.history.slice(0, 8).map((event) => (
              <li key={event.seq}>
                {event.at.slice(0, 16).replace("T", " ")} · {event.from_status || "-"} → {event.to_status || "-"}
                {event.note ? " · " + event.note : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {error ? <p className="small" style={{ color: "var(--danger, #b00)" }}>{error}</p> : null}
    </section>
  );
}