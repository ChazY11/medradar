import { useState } from "react";
import { useAsync } from "../api/hooks";
import { createWatchlist, deleteWatchlist, getWatchlists, type Watchlist } from "../api/human";
import { useI18n } from "../i18n";

/** Save the filter you are looking at, and jump back to it later. */
export function WatchlistBar({
  filters,
  onApply,
}: {
  filters: Record<string, unknown>;
  onApply: (filter: Record<string, unknown>) => void;
}) {
  const { bi } = useI18n();
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const lists = useAsync(() => getWatchlists(true), []);

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    setError(null);
    try {
      await createWatchlist(trimmed, filters);
      setName("");
      lists.reload();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item: Watchlist) => {
    try {
      await deleteWatchlist(item.id);
      lists.reload();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    }
  };

  return (
    <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
      <span className="small muted">{bi("Watchlists", "我的关注")}</span>
      {(lists.data?.items ?? []).map((item) => (
        <span key={item.id} className="chip" style={{ display: "inline-flex", gap: 6 }}>
          <button
            type="button"
            className="linklike"
            style={{ background: "none", border: 0, padding: 0, cursor: "pointer", font: "inherit" }}
            onClick={() => onApply(item.filter)}
            title={JSON.stringify(item.filter)}
          >
            {item.name}
            {typeof item.count === "number" ? <span className="small muted"> ({item.count})</span> : null}
          </button>
          <button
            type="button"
            aria-label={bi("Delete", "删除") + " " + item.name}
            onClick={() => remove(item)}
            style={{ background: "none", border: 0, cursor: "pointer", color: "inherit" }}
          >
            x
          </button>
        </span>
      ))}
      <input
        className="input"
        style={{ maxWidth: 180 }}
        placeholder={bi("Name this view", "给这组筛选起个名")}
        value={name}
        onChange={(event) => setName(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") save();
        }}
      />
      <button type="button" className="btn sm" disabled={!name.trim() || saving} onClick={save}>
        {saving ? bi("Saving", "保存中") : bi("Save current filters", "保存当前筛选")}
      </button>
      {error ? <span className="small" style={{ color: "var(--danger, #b00)" }}>{error}</span> : null}
    </div>
  );
}