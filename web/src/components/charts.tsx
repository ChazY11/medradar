import { useMemo, useState } from "react";
import { useI18n, type TranslationKey } from "../i18n";
import type { Aggregations, EventType } from "../api/types";

const TYPE_ORDER: EventType[] = ["510k", "pma", "pma_supplement", "recall"];

const TYPE_COLOR: Record<EventType, string> = {
  "510k": "var(--510k)",
  pma: "var(--pma)",
  pma_supplement: "var(--pma_supplement)",
  recall: "var(--recall)",
};

export function TypeLegend({ types }: { types?: EventType[] }) {
  const { t } = useI18n();
  const visible = types ?? TYPE_ORDER;
  return (
    <div className="chart-legend">
      {visible.map((type) => (
        <span className="item" key={type}>
          <span className="swatch" style={{ background: TYPE_COLOR[type] }} aria-hidden="true" />
          {t(("type." + type) as TranslationKey)}
        </span>
      ))}
    </div>
  );
}

/** Stacked column chart of records per year, one column per year, one segment per type. */
export function YearSeries({ data, height = 190 }: { data: Aggregations["by_year"]; height?: number }) {
  const { t } = useI18n();
  const [hover, setHover] = useState<{ x: number; y: number; year: string; counts: Record<EventType, number>; total: number } | null>(null);
  const rows = useMemo(() => data.filter((row) => row.total > 0), [data]);
  const width = 720;
  const padding = { top: 8, right: 8, bottom: 22, left: 34 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;
  const max = Math.max(1, ...rows.map((row) => row.total));
  const slot = rows.length ? innerW / rows.length : innerW;
  const barW = Math.max(3, Math.min(26, slot * 0.62));
  const ticks = [0, Math.ceil(max / 2), max];
  const typeList: EventType[] = TYPE_ORDER.filter((type) => rows.some((row) => row.counts[type] > 0));

  if (!rows.length) {
    return <div className="empty-inline">{t("state.empty")}</div>;
  }
  return (
    <div className="chart chart-frame">
      <svg viewBox={"0 0 " + width + " " + height} role="img" aria-label="Records per year by event type">
        {ticks.map((tick) => {
          const y = padding.top + innerH - (tick / max) * innerH;
          return (
            <g key={tick}>
              <line className="chart-grid" x1={padding.left} x2={width - padding.right} y1={y} y2={y} />
              <text className="chart-axis" x={padding.left - 6} y={y + 3} textAnchor="end">
                {tick}
              </text>
            </g>
          );
        })}
        {rows.map((row, index) => {
          const x = padding.left + index * slot + (slot - barW) / 2;
          let cursor = padding.top + innerH;
          return (
            <g
              key={row.year}
              onMouseEnter={() => setHover({ x: x + barW / 2, y: padding.top, year: row.year, counts: row.counts, total: row.total })}
              onMouseLeave={() => setHover(null)}
            >
              <rect x={padding.left + index * slot} y={padding.top} width={slot} height={innerH} fill="transparent" />
              {typeList.map((type) => {
                const count = row.counts[type] ?? 0;
                if (!count) return null;
                const h = (count / max) * innerH;
                cursor -= h;
                return <rect key={type} x={x} y={cursor} width={barW} height={h} fill={TYPE_COLOR[type]} rx={1} />;
              })}
              {rows.length <= 26 || index % 2 === 0 ? (
                <text className="chart-axis" x={x + barW / 2} y={height - 6} textAnchor="middle">
                  {rows.length > 40 ? row.year.slice(2) : row.year}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      {hover ? (
        <div className="chart-tooltip" style={{ left: "0px", top: "-8px", position: "absolute" }}>
          {hover.year}: {hover.total} {t("common.records")}
          {typeList.map((type) =>
            hover.counts[type] ? (
              <div key={type}>
                {t(("type." + type) as TranslationKey)}: {hover.counts[type]}
              </div>
            ) : null,
          )}
        </div>
      ) : null}
      <div className="mt-8">
        <TypeLegend types={typeList} />
      </div>
    </div>
  );
}

/** Horizontal stacked bars: one row per category, segments per event type. */
export function BarBreakdown({
  rows,
  limit = 12,
  labelWidth = 170,
}: {
  rows: Aggregations["by_category"];
  limit?: number;
  labelWidth?: number;
}) {
  const { t } = useI18n();
  const visible = rows.slice(0, limit);
  const max = Math.max(1, ...visible.map((row) => row.total));
  const typeList: EventType[] = TYPE_ORDER.filter((type) => visible.some((row) => row.counts[type] > 0));
  if (!visible.length) return <div className="empty-inline">{t("state.empty")}</div>;
  return (
    <div className="bar-list">
      {visible.map((row) => (
        <div className="bar-row" key={row.id}>
          <span className="bar-label" title={row.label} style={{ maxWidth: labelWidth }}>
            {row.label}
          </span>
          <span className="bar-track" aria-hidden="true">
            {typeList.map((type) => {
              const count = row.counts[type] ?? 0;
              if (!count) return null;
              return (
                <span
                  key={type}
                  className="bar-seg"
                  style={{ width: ((count / max) * 100).toFixed(2) + "%", background: TYPE_COLOR[type] }}
                  title={t(("type." + type) as TranslationKey) + ": " + count}
                />
              );
            })}
          </span>
          <span className="bar-value">{row.total.toLocaleString()}</span>
        </div>
      ))}
      {rows.length > limit ? (
        <div className="muted tiny">
          + {rows.length - limit} more categories in the export and in the full filter result.
        </div>
      ) : null}
      <div className="mt-8">
        <TypeLegend types={typeList} />
      </div>
    </div>
  );
}

/** Compact single-value bar used in comparison matrices. */
export function MiniBar({ value, max, color = "var(--accent)" }: { value: number; max: number; color?: string }) {
  const width = max > 0 ? Math.max(value > 0 ? 2 : 0, (value / max) * 100) : 0;
  return (
    <span className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
      <span className="bar-track" style={{ width: 64, height: 7 }} aria-hidden="true">
        <span className="bar-seg" style={{ width: width + "%", background: color }} />
      </span>
      <span className="num" style={{ minWidth: 34, textAlign: "right" }}>
        {value.toLocaleString()}
      </span>
    </span>
  );
}
