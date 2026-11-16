import { useEffect, useMemo, useState } from "react";
import { useAsync } from "../api/hooks";
import { useI18n } from "../i18n";
import {
  getFeed,
  getFeedFacets,
  getIntelligence,
  getNotices,
  getRadarHealth,
  type Confirmation,
  type FeedQuery,
  type IntelDetail,
  type IntelEvent,
} from "../api/radar";
import { AsyncSection } from "../components/async";
import {
  Badge,
  Banner,
  Card,
  EmptyState,
  KeyValue,
  PageHeader,
  Pagination,
  formatDate,
  formatDateTime,
  formatNumber,
} from "../components/ui";

const LAST_VISIT_KEY = "medradar.radar.lastVisit";
const PAGE_SIZE = 20;
const CHANGE_STATES = ["NEW", "UPDATED", "REMOVED_OR_UNAVAILABLE", "FETCH_FAILED"] as const;
const CONFIRMATIONS: Confirmation[] = ["CONFIRMED", "CANDIDATE", "TOPIC_RELATED"];
const PHASES = ["INITIAL_DISCOVERY", "INCREMENTAL_DISCOVERY", "HISTORICAL_BACKFILL"] as const;

function confirmationTone(value: Confirmation): "ok" | "warn" | "info" | "neutral" {
  if (value === "CONFIRMED") return "ok";
  if (value === "CANDIDATE") return "warn";
  if (value === "TOPIC_RELATED") return "info";
  return "neutral";
}

function changeTone(state: string): "ok" | "warn" | "danger" | "neutral" | "info" {
  if (state === "NEW") return "ok";
  if (state === "UPDATED") return "info";
  if (state === "REMOVED_OR_UNAVAILABLE") return "warn";
  if (state === "FETCH_FAILED") return "danger";
  return "neutral";
}

export function LiveIntelligencePage() {
  const { bi } = useI18n();
  const [filters, setFilters] = useState<FeedQuery>({ order: "observed" });
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [lastVisit] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(LAST_VISIT_KEY);
    } catch {
      return null;
    }
  });
  const [noticeOpen, setNoticeOpen] = useState(true);

  const health = useAsync(() => getRadarHealth(), []);
  const facets = useAsync(() => getFeedFacets(), []);
  const feed = useAsync(
    () => getFeed({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [JSON.stringify(filters), page],
  );
  const notices = useAsync(() => getNotices(lastVisit), [lastVisit]);

  useEffect(() => {
    // Record the visit *after* the notice fetch has been requested, so the next visit
    // reports what arrived since this one.
    const stamp = new Date().toISOString();
    try {
      window.localStorage.setItem(LAST_VISIT_KEY, stamp);
    } catch {
      // localStorage can be unavailable; the in-site indicator degrades to "unknown".
    }
  }, []);

  const blocked = useMemo(
    () => (health.data?.sources ?? []).filter((source) => source.access_state === "BLOCKED"),
    [health.data],
  );

  const patch = (next: Partial<FeedQuery>) => {
    setFilters((previous) => {
      const merged: FeedQuery = { ...previous, ...next };
      for (const key of Object.keys(merged) as (keyof FeedQuery)[]) {
        if (merged[key] === "" || merged[key] === undefined) delete merged[key];
      }
      return merged;
    });
    setPage(0);
  };

  const activeFilterCount = Object.keys(filters).filter((key) => key !== "order").length;

  return (
    <>
      <PageHeader
        eyebrow={bi("Live intelligence", "实时情报")}
        title={bi("Live Intelligence Feed", "实时情报流")}
        description={bi(
          "Newly observed public records about ICU patient-monitoring technology. Every card shows what was found, where it came from, and the two dates that matter: when the source published it and when MedRadar first observed it.",
          "关于 ICU 患者监护技术的最新公开记录。每张卡片都说明：发现了什么、来源是什么、以及两个关键日期——来源何时公开，MedRadar 何时首次观察到。",
        )}
      />

      {health.data?.available === false ? (
        <Banner tone="warning" title={bi("Monitoring has not started", "监测尚未启动")}>
          {bi(
            "No radar ledger exists on this deployment. Run `python -m medradar radar run` to perform a real source check. This page never displays invented intelligence.",
            "本部署尚无雷达账本。请运行 `python -m medradar radar run` 执行一次真实来源检查。本页面不会展示虚构情报。",
          )}
        </Banner>
      ) : null}

      {noticeOpen && notices.data && notices.data.new_count > 0 ? (
        <Banner tone="info" title={bi("New since your last visit", "自上次访问以来的新情报")}>
          <div className="row between wrap" style={{ gap: 12 }}>
            <span>
              {bi(
                `${notices.data.new_count} new observation(s) were recorded since ${lastVisit ? formatDateTime(lastVisit) : "the previous visit"}.`,
                `自 ${lastVisit ? formatDateTime(lastVisit) : "上次访问"} 以来新增 ${notices.data.new_count} 条观察。`,
              )}
            </span>
            <button type="button" className="btn sm" onClick={() => setNoticeOpen(false)}>
              {bi("Dismiss", "关闭")}
            </button>
          </div>
        </Banner>
      ) : null}

      <Card
        title={bi("Source status", "来源状态")}
        note={bi(
          "A source that is blocked by its operator is shown here as blocked, never as 'nothing found'.",
          "被来源方拒绝程序访问的来源会显示为 blocked，绝不会显示为『没有发现』。",
        )}
      >
        <AsyncSection status={health.status} data={health.data} error={health.error} reload={health.reload} loadingLines={3}>
          {(payload) => (
            <>
              <div className="row wrap" style={{ gap: 8 }}>
                {(payload.sources ?? []).map((source) => (
                  <span key={source.source_id} className="chip" aria-pressed={false} title={source.access_reason ?? source.label}>
                    <span
                      className="dot"
                      style={{
                        background:
                          source.access_state === "BLOCKED"
                            ? "var(--warn)"
                            : source.status === "OK"
                              ? "var(--ok)"
                              : source.status === "NEVER_RUN"
                                ? "var(--text-3)"
                                : "var(--danger)",
                      }}
                    />
                    {source.label}
                    <span className="small muted" style={{ marginLeft: 6 }}>
                      {source.access_state === "BLOCKED"
                        ? bi("access restricted", "访问受限")
                        : source.last_checked_at
                          ? formatDate(source.last_checked_at)
                          : bi("never checked", "从未检查")}
                    </span>
                  </span>
                ))}
                {payload.backlog ? (
                  <span className="chip" aria-pressed={false}>
                    {bi("AI backlog", "AI 积压")}: {formatNumber(payload.backlog.backlog)}
                  </span>
                ) : null}
                {payload.resources ? (
                  <span className="chip" aria-pressed={false}>
                    {bi("Memory available", "可用内存")}:{" "}
                    {payload.resources.available_mb ? `${payload.resources.available_mb} MB` : "unknown"}
                  </span>
                ) : null}
              </div>
              {blocked.length ? (
                <div className="mt-8 small muted">
                  {blocked
                    .map((source) => `${source.label}: ${source.access_reason ?? source.access_state}`)
                    .join(" · ")}
                </div>
              ) : null}
            </>
          )}
        </AsyncSection>
      </Card>

      <Card
        title={bi("Filters", "筛选")}
        note={bi("Filter by company, technology topic, source, dates and relation confidence.", "按企业、技术主题、来源、日期与关联置信度筛选。")}
        actions={
          activeFilterCount ? (
            <button type="button" className="btn sm" onClick={() => { setFilters({ order: "observed" }); setPage(0); }}>
              {bi("Clear", "清除")} ({activeFilterCount})
            </button>
          ) : null
        }
      >
        <AsyncSection status={facets.status} data={facets.data} error={facets.error} reload={facets.reload} loadingLines={3}>
          {(payload) => (
            <div className="filter-bar" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="small muted">{bi("Company", "企业")}</span>
                {(payload.organizations ?? []).map((org) => (
                  <button
                    key={org.organization_id}
                    type="button"
                    className="chip"
                    aria-pressed={filters.organization === org.organization_id}
                    onClick={() =>
                      patch({ organization: filters.organization === org.organization_id ? undefined : org.organization_id })
                    }
                  >
                    {org.display_name} <span className="small muted">({org.n})</span>
                  </button>
                ))}
              </div>
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="small muted">{bi("Technology topic", "技术主题")}</span>
                {(payload.topics ?? []).slice(0, 18).map((topic) => (
                  <button
                    key={topic.topic_id}
                    type="button"
                    className="chip"
                    aria-pressed={filters.topic === topic.topic_id}
                    onClick={() => patch({ topic: filters.topic === topic.topic_id ? undefined : topic.topic_id })}
                    title={topic.topic_id}
                  >
                    {topic.label_en} <span className="small muted">({topic.n})</span>
                  </button>
                ))}
              </div>
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="small muted">{bi("Change", "变更类型")}</span>
                {CHANGE_STATES.map((state) => (
                  <button
                    key={state}
                    type="button"
                    className="chip"
                    aria-pressed={filters.change_state === state}
                    onClick={() => patch({ change_state: filters.change_state === state ? undefined : state })}
                  >
                    {state}
                  </button>
                ))}
              </div>
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="small muted">{bi("Relation confidence", "关联置信度")}</span>
                {CONFIRMATIONS.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className="chip"
                    aria-pressed={filters.confirmation === value}
                    onClick={() => patch({ confirmation: filters.confirmation === value ? undefined : value })}
                  >
                    {value}
                  </button>
                ))}
              </div>
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="small muted">{bi("Source", "来源")}</span>
                {(payload.sources ?? []).map((source) => (
                  <button
                    key={source.source}
                    type="button"
                    className="chip"
                    aria-pressed={filters.source === source.source}
                    onClick={() => patch({ source: filters.source === source.source ? undefined : source.source })}
                  >
                    {source.source} <span className="small muted">({source.n})</span>
                  </button>
                ))}
              </div>
              <div className="row wrap" style={{ gap: 12 }}>
                <label className="small muted">
                  {bi("Published from", "公开日期自")}
                  <input
                    type="date"
                    className="input"
                    value={filters.published_from ?? ""}
                    onChange={(event) => patch({ published_from: event.target.value || undefined })}
                  />
                </label>
                <label className="small muted">
                  {bi("Published to", "公开日期至")}
                  <input
                    type="date"
                    className="input"
                    value={filters.published_to ?? ""}
                    onChange={(event) => patch({ published_to: event.target.value || undefined })}
                  />
                </label>
                <label className="small muted">
                  {bi("First observed from", "首次发现自")}
                  <input
                    type="date"
                    className="input"
                    value={(filters.observed_from ?? "").slice(0, 10)}
                    onChange={(event) => patch({ observed_from: event.target.value || undefined })}
                  />
                </label>
                <label className="small muted">
                  {bi("First observed to", "首次发现至")}
                  <input
                    type="date"
                    className="input"
                    value={(filters.observed_to ?? "").slice(0, 10)}
                    onChange={(event) => patch({ observed_to: event.target.value || undefined })}
                  />
                </label>
                <label className="small muted">
                  {bi("Discovery phase", "发现阶段")}
                  <select
                    className="input"
                    value={filters.phase ?? ""}
                    onChange={(event) => patch({ phase: event.target.value || undefined })}
                  >
                    <option value="">{bi("all", "全部")}</option>
                    {PHASES.map((phase) => (
                      <option key={phase} value={phase}>
                        {phase}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="small muted">
                  {bi("Sort", "排序")}
                  <select
                    className="input"
                    value={filters.order ?? "observed"}
                    onChange={(event) => patch({ order: event.target.value as FeedQuery["order"] })}
                  >
                    <option value="observed">{bi("First observed", "首次发现")}</option>
                    <option value="published">{bi("Published", "公开时间")}</option>
                    <option value="event">{bi("Event date", "事件日期")}</option>
                  </select>
                </label>
                <label className="small muted">
                  {bi("Search title / id", "搜索标题/编号")}
                  <input
                    className="input"
                    value={filters.q ?? ""}
                    onChange={(event) => patch({ q: event.target.value || undefined })}
                    placeholder={bi("e.g. oximetry, K240001", "例如 oximetry、K240001")}
                  />
                </label>
              </div>
            </div>
          )}
        </AsyncSection>
      </Card>

      <AsyncSection status={feed.status} data={feed.data} error={feed.error} reload={feed.reload} loadingLines={6}>
        {(payload) => (
          <>
            <div className="row between" style={{ margin: "6px 0 10px" }}>
              <span className="small muted">
                {bi(`${payload.total} observation(s) match these filters.`, `共 ${payload.total} 条观察符合当前筛选。`)}
              </span>
              <span className="small muted">{payload.note}</span>
            </div>

            {payload.items.length === 0 ? (
              <EmptyState
                title={bi("No observation matches", "没有匹配的观察")}
                description={bi(
                  "This is an evidence statement about the filters and the monitored sources, not a claim that nothing exists. Clear the filters or wait for a scheduled check.",
                  "这是关于筛选条件与已监测来源的证据陈述，并不代表现实中不存在。请清除筛选，或等待下一次计划检查。",
                )}
              />
            ) : (
              <div className="grid" style={{ gridTemplateColumns: "1fr", gap: 12 }}>
                {payload.items.map((item) => (
                  <FeedCard key={item.observation_id} item={item} onOpen={() => setSelected(item.observation_id)} />
                ))}
              </div>
            )}

            <Pagination
              page={payload.page}
              totalPages={Math.max(1, Math.ceil(payload.total / Math.max(1, payload.page_size)))}
              total={payload.total}
              onPage={(next) => setPage(next - 1)}
            />
          </>
        )}
      </AsyncSection>

      {selected ? <IntelligenceDrawer observationId={selected} onClose={() => setSelected(null)} /> : null}
    </>
  );
}

function FeedCard({ item, onOpen }: { item: IntelEvent; onOpen: () => void }) {
  const { bi } = useI18n();
  return (
    <article className="card" style={{ padding: 16 }}>
      <div className="row between wrap" style={{ gap: 8 }}>
        <div className="row wrap" style={{ gap: 6 }}>
          <Badge tone={changeTone(item.change_state)}>{item.change_state}</Badge>
          <Badge tone="outline">{item.source}</Badge>
          <Badge tone="neutral">{item.record_type}</Badge>
          {item.discovery_phase === "INITIAL_DISCOVERY" ? (
            <Badge
              tone="warn"
              title={bi(
                "This record was already public when the source was first enabled. It is not new today.",
                "该记录在来源首次启用时就已经公开，并非今天的新事件。",
              )}
            >
              {bi("initial discovery", "初次发现")}
            </Badge>
          ) : null}
          {item.discovery_phase === "HISTORICAL_BACKFILL" ? (
            <Badge tone="warn">{bi("historical backfill", "历史回填")}</Badge>
          ) : null}
        </div>
        <button type="button" className="btn sm" onClick={onOpen}>
          {bi("Evidence", "证据")}
        </button>
      </div>

      <h3 style={{ margin: "10px 0 6px", fontSize: 15, lineHeight: 1.45 }}>
        {item.source_url ? (
          <a href={item.source_url} target="_blank" rel="noreferrer noopener">
            {item.title}
          </a>
        ) : (
          item.title
        )}
      </h3>

      <div className="row wrap small muted" style={{ gap: 14 }}>
        <span>
          {bi("Published", "公开")}: {item.source_published_at ? formatDateTime(item.source_published_at) : bi("not published by source", "来源未公布")}
        </span>
        <span>
          {bi("Event date", "事件日期")}: {item.event_date ? formatDate(item.event_date) : "—"}
        </span>
        <span>
          {bi("First observed", "首次发现")}: {formatDateTime(item.first_observed_at)}
        </span>
        {item.official_identifier ? <span className="mono small">{item.official_identifier}</span> : null}
      </div>

      {item.organization_candidates.length || item.technology_topics.length ? (
        <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
          {item.organization_candidates.map((org) => (
            <Badge key={org.organization_id + org.confirmation} tone={confirmationTone(org.confirmation)} title={org.method}>
              {org.display_name} · {org.confirmation}
            </Badge>
          ))}
          {item.technology_topics.map((topic) => (
            <Badge key={topic.topic_id + topic.confirmation} tone={confirmationTone(topic.confirmation)} title={topic.method}>
              {topic.label_en} · {topic.confirmation}
            </Badge>
          ))}
          {item.product_candidates.map((product) => (
            <Badge key={product.product_key} tone={confirmationTone(product.confirmation)}>
              {product.product_key.split(":")[0].replace(/-/g, " ")} · {product.confirmation}
            </Badge>
          ))}
        </div>
      ) : (
        <div className="small muted mt-8">
          {bi(
            "No organisation or technology rule matched this record. It is stored unmapped, not discarded.",
            "没有企业或技术规则命中该记录。它按未映射状态保存，而不是被丢弃。",
          )}
        </div>
      )}

      {item.latest_version_changed_fields.length ? (
        <div className="small muted mt-8">
          {bi("Changed fields", "变更字段")}: {item.latest_version_changed_fields.join(", ")}
        </div>
      ) : null}
    </article>
  );
}

function IntelligenceDrawer({ observationId, onClose }: { observationId: string; onClose: () => void }) {
  const { bi } = useI18n();
  const detail = useAsync(() => getIntelligence(observationId), [observationId]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={bi("Intelligence evidence", "情报证据")}>
        <div className="drawer-head">
          <div>
            <div className="eyebrow">{bi("Evidence trail", "证据链")}</div>
            <div className="mono small" style={{ marginTop: 4 }}>{observationId}</div>
          </div>
          <button type="button" className="btn sm" onClick={onClose}>Esc</button>
        </div>
        <div className="drawer-body">
          <AsyncSection status={detail.status} data={detail.data} error={detail.error} reload={detail.reload} loadingLines={8}>
            {(payload: IntelDetail) => (
              <>
                <div className="drawer-section">
                  <div className="row wrap" style={{ gap: 6 }}>
                    <Badge tone={changeTone(payload.change_state)}>{payload.change_state}</Badge>
                    <Badge tone="outline">{payload.source}</Badge>
                    <Badge tone="neutral">v{payload.version}</Badge>
                  </div>
                  <div className="mt-8" style={{ fontWeight: 620, lineHeight: 1.45 }}>{payload.title}</div>
                  {payload.source_url ? (
                    <a className="small" href={payload.source_url} target="_blank" rel="noreferrer noopener">
                      {bi("Open the original record", "打开原始记录")}
                    </a>
                  ) : null}
                </div>

                <div className="drawer-section">
                  <KeyValue
                    rows={[
                      { label: bi("Official identifier", "官方标识"), value: payload.official_identifier ?? "—" },
                      { label: bi("Record type", "记录类型"), value: payload.record_type },
                      { label: bi("Published at", "公开时间"), value: payload.source_published_at ? formatDateTime(payload.source_published_at) : bi("not stated by source", "来源未说明") },
                      { label: bi("Event date", "事件日期"), value: payload.event_date ? `${payload.event_date} (${payload.event_date_precision})` : "—" },
                      { label: bi("First observed", "首次发现"), value: formatDateTime(payload.first_observed_at) },
                      { label: bi("Last checked", "最近检查"), value: payload.last_checked_at ? formatDateTime(payload.last_checked_at) : "—" },
                      { label: bi("Discovery phase", "发现阶段"), value: payload.discovery_phase },
                      { label: bi("Content hash", "内容哈希"), value: <span className="mono small">{payload.content_hash.slice(0, 20)}…</span> },
                    ]}
                  />
                </div>

                <div className="drawer-section">
                  <h3>{bi("Version history", "版本历史")}</h3>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>v</th>
                          <th>{bi("Captured", "采集时间")}</th>
                          <th>{bi("State", "状态")}</th>
                          <th>{bi("Changed fields", "变更字段")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {payload.versions.map((version) => (
                          <tr key={version.version_id}>
                            <td>{version.version_seq}</td>
                            <td>{formatDateTime(version.captured_at)}</td>
                            <td>{version.change_state}</td>
                            <td className="small">{version.changed_fields.join(", ") || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="drawer-section">
                  <h3>{bi("Change events", "变更事件")}</h3>
                  <ul className="small">
                    {payload.changes.map((change, index) => (
                      <li key={index}>
                        {formatDateTime(change.observed_at)} · {change.change_state}
                        {change.changed_fields.length ? ` · ${change.changed_fields.join(", ")}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="drawer-section">
                  <h3>{bi("Model proposals", "模型提议")}</h3>
                  {payload.ai_candidates.length === 0 ? (
                    <div className="small muted">
                      {bi(
                        "No model proposal exists for this record. The rule layer alone produced every relation shown.",
                        "该记录没有模型提议。所示全部关系均由规则层产生。",
                      )}
                    </div>
                  ) : (
                    <ul className="small">
                      {payload.ai_candidates.map((candidate, index) => (
                        <li key={index}>
                          {candidate.validation_state} · {candidate.model_id} ({candidate.model_version})
                          <span className="muted"> · {formatDateTime(candidate.created_at)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </AsyncSection>
        </div>
      </aside>
    </>
  );
}
