import type { CSSProperties, ReactNode } from "react";
import { useEffect, useId, useState } from "react";
import { useI18n, type TranslationKey } from "../i18n";
import type { EventType } from "../api/types";

/* ------------------------------------------------------------------ page header */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h1 className="page-title">{title}</h1>
        {description ? <p className="page-desc">{description}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

/* ------------------------------------------------------------------ card */
export function Card({
  title,
  note,
  actions,
  children,
  flush = false,
  footer,
}: {
  title?: ReactNode;
  note?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  footer?: ReactNode;
}) {
  return (
    <section className="card">
      {title || note || actions ? (
        <div className="card-header">
          <div>
            {title ? <div className="card-title">{title}</div> : null}
            {note ? <div className="card-note">{note}</div> : null}
          </div>
          {actions ? <div className="row">{actions}</div> : null}
        </div>
      ) : null}
      <div className={flush ? "card-body flush" : "card-body"}>{children}</div>
      {footer ? <div className="card-footer">{footer}</div> : null}
    </section>
  );
}

export function SectionHead({ title, note, actions }: { title: ReactNode; note?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="section-head">
      <div className="row" style={{ gap: 10 }}>
        <div className="section-title">{title}</div>
        {note ? <div className="card-note">{note}</div> : null}
      </div>
      {actions ? <div className="row">{actions}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ metric */
export function MetricTile({
  label,
  value,
  sub,
  accent = false,
  compact = false,
  title,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: boolean;
  compact?: boolean;
  title?: string;
}) {
  return (
    <div className={accent ? "metric accent" : "metric"} title={title}>
      <div className="metric-label">{label}</div>
      <div className={compact ? "metric-value sm" : "metric-value"}>{value}</div>
      {sub ? <div className="metric-sub">{sub}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ badges */
export function Badge({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "danger" | "info" | "outline";
  title?: string;
}) {
  return (
    <span className={"badge " + tone} title={title}>
      {children}
    </span>
  );
}

const TYPE_COLOR: Record<EventType, string> = {
  "510k": "var(--510k)",
  pma: "var(--pma)",
  pma_supplement: "var(--pma_supplement)",
  recall: "var(--recall)",
};

export function EventTypeBadge({ type, short = false }: { type: EventType; short?: boolean }) {
  const { t } = useI18n();
  const labelKey = ("type." + type) as TranslationKey;
  const label = t(labelKey);
  const display = short && type === "pma_supplement" ? "PMA sup." : label;
  return (
    <span className="type-badge" title={label}>
      <span className="type-dot" style={{ background: TYPE_COLOR[type] ?? "var(--text-3)" }} aria-hidden="true" />
      {display}
    </span>
  );
}

export function ReviewBadge({ review, compact = false }: { review: string | null; compact?: boolean }) {
  const { t } = useI18n();
  if (!review) return <span className="muted small">{t("review.rejected")}</span>;
  if (review === "pending_review") {
    return (
      <Badge tone="warn" title="This applicant spelling was proposed by MedRadar from an observed FDA spelling and has not been signed off by a human reviewer. Treat the count as provisional.">
        {compact ? "provisional" : t("review.pending_review")}
      </Badge>
    );
  }
  if (compact) return <span className="muted tiny" title="Attribution reviewed against the curated registry.">{t("review.curated")}</span>;
  return <Badge tone="neutral">{t("review.curated")}</Badge>;
}

export function TimeQualityBadge({ quality }: { quality: string }) {
  const { t } = useI18n();
  if (quality === "date_from_source") return <Badge tone="neutral">{t("time.date_from_source")}</Badge>;
  if (quality === "date_derived_from_source") return <Badge tone="warn">{t("time.date_derived_from_source")}</Badge>;
  return <Badge tone="danger">{t("time.unknown")}</Badge>;
}

export function FreshnessBadge({ state, ageDays, threshold }: { state: string; ageDays: number | null; threshold: number }) {
  const { t } = useI18n();
  if (state === "fresh") {
    return (
      <Badge tone="ok" title={"Snapshot is younger than " + threshold + " days."}>
        {t("snapshot.fresh")}
        {ageDays !== null ? " - " + ageDays + "d" : ""}
      </Badge>
    );
  }
  if (state === "stale") {
    return (
      <Badge tone="warn" title={"Snapshot is older than " + threshold + " days; refresh the collection before relying on it."}>
        {t("snapshot.stale")}
        {ageDays !== null ? " - " + ageDays + "d" : ""}
      </Badge>
    );
  }
  return <Badge tone="neutral">{t("state.notAvailable")}</Badge>;
}

/* ------------------------------------------------------------------ definition */
export function DefinitionLabel({ text, definition }: { text: string; definition: string }) {
  return (
    <span className="def" title={definition}>
      {text}
    </span>
  );
}

/* ------------------------------------------------------------------ banner */
export function Banner({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warning" | "danger" | "neutral";
  title?: ReactNode;
  children?: ReactNode;
}) {
  const mark = tone === "danger" ? "!" : tone === "warning" ? "!" : "i";
  return (
    <div className={"banner " + tone} role={tone === "warning" || tone === "danger" ? "alert" : undefined}>
      <span className="banner-icon" aria-hidden="true">
        {mark}
      </span>
      <div>
        {title ? <div className="banner-title">{title}</div> : null}
        {children}
      </div>
    </div>
  );
}

export function Callout({ children, accent = false }: { children: ReactNode; accent?: boolean }) {
  return <div className={accent ? "callout accent" : "callout"}>{children}</div>;
}

/* ------------------------------------------------------------------ states */
export function LoadingBlock({ lines = 3, height }: { lines?: number; height?: number }) {
  const { t } = useI18n();
  if (height) return <div className="skeleton skeleton-block" style={{ height }} aria-label={t("state.loading")} />;
  return (
    <div aria-label={t("state.loading")}>
      {Array.from({ length: lines }).map((_, index) => (
        <div
          key={index}
          className={"skeleton skeleton-line" + (index % 2 === 0 ? "" : " w60")}
          style={{ width: index % 3 === 0 ? "100%" : index % 3 === 1 ? "62%" : "78%" }}
        />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry, hint }: { message: string; onRetry?: () => void; hint?: string }) {
  const { t } = useI18n();
  return (
    <div className="state-block" role="alert">
      <div className="state-title">{t("state.error")}</div>
      <div className="state-desc">{message}</div>
      {hint ? <div className="state-desc muted">{hint}</div> : null}
      {onRetry ? (
        <div className="row">
          <button type="button" className="btn" onClick={onRetry}>
            {t("state.retry")}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="state-block">
      <div className="state-title">{title}</div>
      {description ? <div className="state-desc">{description}</div> : null}
      {actions ? <div className="row">{actions}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ tabs */
export function Tabs({
  items,
  active,
  onChange,
}: {
  items: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={active === item.id}
          className={active === item.id ? "active" : undefined}
          onClick={() => onChange(item.id)}
        >
          {item.label}
          {typeof item.count === "number" ? <span className="muted"> ({item.count})</span> : null}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ pagination */
export function Pagination({
  page,
  totalPages,
  total,
  onPage,
}: {
  page: number;
  totalPages: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const { t } = useI18n();
  return (
    <nav className="pagination" aria-label="Pagination">
      <div>
        {total.toLocaleString()} {t("common.records")} - {t("common.page")} {page} {t("common.of")} {totalPages}
      </div>
      <div className="pages">
        <button type="button" className="btn sm" disabled={page <= 1} onClick={() => onPage(1)}>
          {"<<"}
        </button>
        <button type="button" className="btn sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          {"<"}
        </button>
        <button type="button" className="btn sm" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
          {">"}
        </button>
        <button type="button" className="btn sm" disabled={page >= totalPages} onClick={() => onPage(totalPages)}>
          {">>"}
        </button>
      </div>
    </nav>
  );
}

/* ------------------------------------------------------------------ tooltip */
export function InfoTip({ children, text }: { children: ReactNode; text: string }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span
      style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 4 }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={0}
      aria-describedby={open ? id : undefined}
    >
      {children}
      {open ? (
        <span
          id={id}
          role="tooltip"
          style={{
            position: "absolute",
            bottom: "130%",
            left: 0,
            zIndex: 60,
            width: 260,
            background: "#0d1526",
            color: "#fff",
            fontSize: 11,
            lineHeight: 1.45,
            padding: "6px 8px",
            borderRadius: 5,
            fontWeight: 400,
            textTransform: "none",
            letterSpacing: 0,
          }}
        >
          {text}
        </span>
      ) : null}
    </span>
  );
}

/* ------------------------------------------------------------------ layout helpers */
export function Grid({ children, cols = 4, style }: { children: ReactNode; cols?: 2 | 3 | 4 | 5 | 6; style?: CSSProperties }) {
  return (
    <div className={"grid cols-" + cols} style={style}>
      {children}
    </div>
  );
}

export function KeyValue({ rows }: { rows: { label: ReactNode; value: ReactNode }[] }) {
  return (
    <dl className="kv">
      {rows.map((row, index) => (
        <div key={index} style={{ display: "contents" }}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Formats an ISO date/datetime for display; returns a dash for missing values. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const short = value.slice(0, 10);
  return short;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    date.getUTCFullYear() +
    "-" +
    pad(date.getUTCMonth() + 1) +
    "-" +
    pad(date.getUTCDate()) +
    " " +
    pad(date.getUTCHours()) +
    ":" +
    pad(date.getUTCMinutes()) +
    " UTC"
  );
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString();
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "-";
  return (value * 100).toFixed(digits) + "%";
}

/** Keeps html lang in sync with the chosen language for assistive technology. */
export function useDocumentLanguage() {
  const { lang } = useI18n();
  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);
}
