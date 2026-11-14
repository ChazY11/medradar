import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { exportEventsCsvUrl, getMeta, listEvents, listOrganizations } from "../api/client";
import { useAsync } from "../api/hooks";
import { AsyncSection } from "../components/async";
import { YearSeries } from "../components/charts";
import { EventTable } from "../components/EventTable";
import { EventsFilterBar } from "../components/EventsFilterBar";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { ExportLink } from "../components/ExportLink";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination } from "../components/ui";
import { useI18n } from "../i18n";
import type { EventRecord } from "../api/types";
import { activeFilterCount, defaultFilters, parseFilters, toQueryString, type EventsFilterState } from "./eventsFilters";

export function EventsPage() {
  const { t, bi } = useI18n();
  const navigate = useNavigate();
  const params = useParams<{ eventId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const state = useMemo(() => parseFilters(searchParams.toString()), [searchParams]);
  const meta = useAsync(() => getMeta(), []);
  const organizations = useAsync(() => listOrganizations(), []);
  const query = toQueryString(state);

  const events = useAsync(
    () =>
      listEvents({
        org: state.org ? [state.org] : undefined,
        types: state.types.length ? state.types : undefined,
        from: state.from || undefined,
        to: state.to || undefined,
        category: state.category ? [state.category] : undefined,
        q: state.q || undefined,
        review: state.review || undefined,
        sort: state.sort,
        page: state.page,
        page_size: state.pageSize,
      }),
    [query],
  );

  const [drawerEvent, setDrawerEvent] = useState<string | null>(null);

  useEffect(() => {
    if (params.eventId) setDrawerEvent(params.eventId);
  }, [params.eventId]);

  const apply = (next: EventsFilterState) => setSearchParams(new URLSearchParams(toQueryString(next).replace(/^\?/, "")), { replace: false });

  const openEvent = (event: EventRecord) => {
    setDrawerEvent(event.event_id);
    const next = new URLSearchParams(searchParams);
    navigate("/events/" + encodeURIComponent(event.official_id) + (next.toString() ? "?" + next.toString() : ""));
  };

  const closeDrawer = () => {
    setDrawerEvent(null);
    navigate("/events" + query);
  };

  const exportHref = exportEventsCsvUrl({
    org: state.org ? [state.org] : undefined,
    types: state.types.length ? state.types : undefined,
    from: state.from || undefined,
    to: state.to || undefined,
    category: state.category ? [state.category] : undefined,
    q: state.q || undefined,
    review: state.review || undefined,
    sort: state.sort,
  });

  return (
    <>
      <PageHeader
        eyebrow={bi("Regulatory records", "监管记录")}
        title={t("events.title")}
        description={t("events.desc")}
        actions={<ExportLink href={exportHref} title="CSV of exactly the filtered records, one row per record, with official URLs.">{t("common.export") + " CSV"}</ExportLink>}
      />

      <div className="stack">
        <AsyncSection status={meta.status} data={meta.data} error={meta.error} reload={meta.reload} loadingLines={2}>
          {(metaData) => (
            <EventsFilterBar
              state={state}
              categories={metaData.categories}
              organizations={organizations.data?.organizations}
              onChange={apply}
              onReset={() => apply(defaultFilters())}
              resultCount={events.data?.total}
            />
          )}
        </AsyncSection>

        {activeFilterCount(state) ? (
          <div className="filter-summary">
            <span>{bi("Applied filters", "已应用筛选")}:</span>
            {state.org ? (
              <span className="filter-token">
                {organizations.data?.organizations.find((org) => org.key === state.org)?.display_name ?? state.org}
                <button type="button" aria-label="Remove organization filter" onClick={() => apply({ ...state, org: "" })}>
                  x
                </button>
              </span>
            ) : null}
            {state.types.map((type) => (
              <span className="filter-token" key={type}>
                {type}
                <button type="button" aria-label={"Remove " + type + " filter"} onClick={() => apply({ ...state, types: state.types.filter((item) => item !== type) })}>
                  x
                </button>
              </span>
            ))}
            {state.from ? <span className="filter-token">from {state.from}</span> : null}
            {state.to ? <span className="filter-token">to {state.to}</span> : null}
            {state.category ? <span className="filter-token">{state.category}</span> : null}
            {state.q ? <span className="filter-token">"{state.q}"</span> : null}
            {state.review ? <span className="filter-token">{state.review}</span> : null}
          </div>
        ) : null}

        {events.status === "error" && events.error ? (
          <ErrorState message={events.error.message} onRetry={events.reload} />
        ) : !events.data ? (
          <Card>
            <LoadingBlock lines={8} />
          </Card>
        ) : (
          <>
            <div className="grid cols-2">
              <Card
                title={bi("Records per year (filtered set)", "逐年记录数（当前筛选结果）")}
                note={bi("Counts over the filtered records, not the whole snapshot.", "统计范围为当前筛选结果，而非整个快照。")}
              >
                <YearSeries data={events.data.aggregations.by_year} />
              </Card>
              <Card title={bi("Filtered totals", "筛选结果概览")} note={bi("Counts are records; event types are never merged.", "计数单位为记录；不同事件类型不合并。")}>
                <div className="grid cols-2">
                  <div>
                    <div className="metric-label">{t("common.records")}</div>
                    <div className="metric-value">{events.data.total.toLocaleString()}</div>
                    <div className="metric-sub">
                      {bi("dated", "有日期")}: {events.data.counts.dated.toLocaleString()} / {bi("undated", "无日期")}:{" "}
                      {events.data.counts.undated.toLocaleString()}
                    </div>
                  </div>
                  <div>
                    <div className="metric-label">{bi("Unclassified", "未分类")}</div>
                    <div className="metric-value">{events.data.counts.unmapped_category.toLocaleString()}</div>
                    <div className="metric-sub">{bi("product code absent from the FDA dictionary", "产品代码不在 FDA 字典中")}</div>
                  </div>
                </div>
                <div className="divider" />
                <div className="row wrap" style={{ gap: 16 }}>
                  {events.data.counts.by_type.map((row) => (
                    <span key={row.event_type} className="row" style={{ gap: 6 }}>
                      <span className="dot" style={{ background: "var(--" + row.event_type + ")" }} aria-hidden="true" />
                      <span className="small">{t(("type." + row.event_type) as never)}</span>
                      <b className="num">{row.count.toLocaleString()}</b>
                    </span>
                  ))}
                </div>
              </Card>
            </div>

            <section className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">
                    {events.data.total.toLocaleString()} {t("common.records")}
                  </div>
                  <div className="card-note">
                    {bi(
                      "Sorted by " + (state.sort === "event_date_asc" ? "event date ascending" : state.sort === "official_id_asc" ? "official identifier" : "event date descending") + ". Every row opens the official record.",
                      "排序：" + (state.sort === "event_date_asc" ? "事件日期升序" : state.sort === "official_id_asc" ? "官方标识" : "事件日期降序") + "。每一行均可打开官方原始记录。",
                    )}
                  </div>
                </div>
                <div className="row">
                  <select className="select" value={state.sort} onChange={(event) => apply({ ...state, sort: event.target.value as EventsFilterState["sort"], page: 1 })}>
                    <option value="event_date_desc">{t("common.eventDate") + " \u2193"}</option>
                    <option value="event_date_asc">{t("common.eventDate") + " \u2191"}</option>
                    <option value="official_id_asc">{t("common.officialId")}</option>
                  </select>
                </div>
              </div>
              {events.data.items.length ? (
                <>
                  <EventTable
                    items={events.data.items}
                    sort={state.sort}
                    onSort={(sort) => apply({ ...state, sort, page: 1 })}
                    onOpen={openEvent}
                  />
                  <Pagination
                    page={events.data.page}
                    totalPages={events.data.total_pages}
                    total={events.data.total}
                    onPage={(page) => apply({ ...state, page })}
                  />
                </>
              ) : (
                <EmptyState
                  title={bi("No records match these filters", "没有符合当前筛选条件的记录")}
                  description={bi(
                    "This is a filter result, not a statement that the company had no regulatory activity. Relax the date window or clear the event-type filter, and check the coverage page for what this snapshot contains.",
                    "这是筛选结果，不代表企业没有监管活动。可放宽日期范围或清除事件类型筛选，并在“数据来源与覆盖”页面核对该快照包含的数据范围。",
                  )}
                  actions={
                    <button type="button" className="btn" onClick={() => apply(defaultFilters())}>
                      {t("common.reset")}
                    </button>
                  }
                />
              )}
            </section>

            <div className="callout">
              {bi(
                "Snapshot " + events.data.snapshot.id + " collected " + events.data.snapshot.collected_at + ". Also useful: ",
                "快照 " + events.data.snapshot.id + "，采集于 " + events.data.snapshot.collected_at + "。相关页面：",
              )}
              <Link className="link" to="/compare">
                {t("nav.compare")}
              </Link>
              {" / "}
              <Link className="link" to="/sources">
                {t("nav.sources")}
              </Link>
            </div>
          </>
        )}
      </div>

      {drawerEvent ? <EvidenceDrawer eventId={drawerEvent} onClose={closeDrawer} /> : null}
    </>
  );
}
