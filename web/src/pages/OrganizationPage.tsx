import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { exportEventsCsvUrl, exportOrganizationMdUrl, getMeta, getOrganization, listOrganizationEvents } from "../api/client";
import { useAsync } from "../api/hooks";
import { AsyncSection } from "../components/async";
import { BarBreakdown, YearSeries } from "../components/charts";
import { EventTable } from "../components/EventTable";
import { EventsFilterBar } from "../components/EventsFilterBar";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { ExportLink } from "../components/ExportLink";
import {
  Badge,
  Banner,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  KeyValue,
  LoadingBlock,
  MetricTile,
  PageHeader,
  Pagination,
  SectionHead,
  Tabs,
  formatDate,
  formatDateTime,
} from "../components/ui";
import { useI18n } from "../i18n";
import type { EventRecord } from "../api/types";
import { defaultFilters, parseFilters, toQueryString, type EventsFilterState } from "./eventsFilters";
import { OrgTransparency, VerificationBadge } from "../components/transparency";

export function OrganizationPage() {
  const { key = "" } = useParams<{ key: string }>();
  const { t, bi } = useI18n();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") ?? "overview";
  const profile = useAsync(() => getOrganization(key), [key]);
  const meta = useAsync(() => getMeta(), []);
  const [drawerEvent, setDrawerEvent] = useState<string | null>(null);

  const setTab = (next: string) => {
    const params = new URLSearchParams(searchParams);
    if (next === "overview") params.delete("tab");
    else params.set("tab", next);
    setSearchParams(params);
  };

  if (profile.status === "error" && profile.error) {
    return (
      <>
        <PageHeader eyebrow={t("org.title")} title={key} />
        <Card>
          <ErrorState message={profile.error.message} hint={profile.error.code === "organization_not_found" ? "This organization is not in the snapshot registry." : undefined} onRetry={profile.reload} />
          <div className="mt-12">
            <Link className="link" to="/organizations">
              {bi("Back to all organizations", "返回企业列表")}
            </Link>
          </div>
        </Card>
      </>
    );
  }

  return (
    <AsyncSection status={profile.status} data={profile.data} error={profile.error} reload={profile.reload} loadingLines={10}>
      {(data) => (
        <>
          <PageHeader
            eyebrow={bi("Organization", "企业") + " - " + data.organization_type.replace(/_/g, " ")}
            title={data.display_name_zh && meta.data && document.documentElement.lang === "zh-CN" ? data.display_name_zh : data.display_name}
            description={data.description}
            actions={
              <>
                <Link className="btn" to={"/compare?orgs=" + data.key}>
                  {bi("Add to comparison", "加入对比")}
                </Link>
                <ExportLink href={exportOrganizationMdUrl(data.key)} title="Markdown intelligence brief with counts, coverage and official record links.">
                  {bi("Export brief", "导出简报")}
                </ExportLink>
              </>
            }
          />

          <div className="stack">
            <div className="row wrap" style={{ gap: 8 }}>
              {data.legal_name && data.legal_name !== data.display_name ? (
                <span className="small muted">
                  {bi("Legal name", "法定名称")}: <span className="mono">{data.legal_name}</span>
                </span>
              ) : null}
              {data.ticker ? (
                <Badge tone="outline">
                  {data.ticker}
                  {data.exchange ? " - " + data.exchange : ""}
                </Badge>
              ) : null}
              {data.country ? <Badge tone="outline">{data.country_name ?? data.country}</Badge> : null}
              {data.registry.review_status === "pending_review" ? (
                <Badge tone="warn">{t("common.pendingReview")}</Badge>
              ) : (
                <Badge tone="neutral">{t("common.curated")}</Badge>
              )}
              <FreshnessBadge state={data.freshness.state} ageDays={data.freshness.age_days} threshold={data.freshness.threshold_days} />
            </div>

            <div className="grid cols-4">
              <MetricTile label={bi("Attributed records", "已归属记录")} value={data.counts.records.toLocaleString()} sub={bi("exact applicant match", "精确申请人匹配")} accent />
              <MetricTile label="510(k)" value={(data.counts.by_type.find((row) => row.event_type === "510k")?.count ?? 0).toLocaleString()} sub={bi("clearances", "上市前通知批准")} />
              <MetricTile
                label={bi("PMA decisions", "PMA 批准")}
                value={((data.counts.by_type.find((row) => row.event_type === "pma")?.count ?? 0) + (data.counts.by_type.find((row) => row.event_type === "pma_supplement")?.count ?? 0)).toLocaleString()}
                sub={bi(
                  (data.counts.by_type.find((row) => row.event_type === "pma")?.count ?? 0) + " original, " + (data.counts.by_type.find((row) => row.event_type === "pma_supplement")?.count ?? 0) + " supplement",
                  "原始 " + (data.counts.by_type.find((row) => row.event_type === "pma")?.count ?? 0) + "，补充 " + (data.counts.by_type.find((row) => row.event_type === "pma_supplement")?.count ?? 0),
                )}
              />
              <MetricTile label={bi("Recalls", "召回")} value={(data.counts.by_type.find((row) => row.event_type === "recall")?.count ?? 0).toLocaleString()} sub={bi("safety actions, not launches", "安全行动，非产品发布")} />
            </div>

            <OrgTransparency verification={data.verification} ownership={data.ownership} />

            <Tabs
              active={tab}
              onChange={setTab}
              items={[
                { id: "overview", label: t("org.tab.overview") },
                { id: "events", label: t("org.tab.events"), count: data.counts.records },
                { id: "attribution", label: t("org.tab.attribution"), count: data.attribution.accepted_spellings + data.attribution.pending_review_spellings },
              ]}
            />

            {tab === "overview" ? (
              <>
                <div className="grid cols-2">
                  <Card title={bi("Attribution and identity", "身份与归属")} note={bi("How this organization's records were matched. Decisions are auditable, not inferred at request time.", "该企业记录的匹配方式；归属决策可复核，而非请求时临时推断。")}>
                    <KeyValue
                      rows={[
                        { label: bi("Curated applicant spellings", "已复核申请人写法"), value: data.attribution.accepted_spellings },
                        {
                          label: bi("Pending human review", "待人工复核"),
                          value: data.attribution.pending_review_spellings ? <Badge tone="warn">{data.attribution.pending_review_spellings}</Badge> : 0,
                        },
                        { label: bi("Rejected similar names", "已排除的近似名称"), value: data.attribution.rejected_spellings.length },
                        {
                          label: bi("Records in scope but not attributed", "范围内但未归属的记录"),
                          value: data.attribution.unattributed_in_scope ? <Badge tone="warn">{data.attribution.unattributed_in_scope}</Badge> : 0,
                        },
                        {
                          label: bi("Ownership", "股权/母子公司关系"),
                          value: (
                            <span className="small">
                              {bi(
                                (data.ownership.verified_relation_count ?? 0) + " verified relation(s), " + (data.ownership.unresolved_relation_count ?? 0) + " unresolved. Counts use current-group attribution.",
                                (data.ownership.verified_relation_count ?? 0) + " 个已核验关系，" + (data.ownership.unresolved_relation_count ?? 0) + " 个未解决。计数采用当前集团口径。",
                              )}
                            </span>
                          ),
                        },
                      ]}
                    />
                    <div className="mt-12">
                      <Link className="link small" to={"/organizations/" + data.key + "?tab=attribution"}>
                        {bi("Open attribution detail", "查看归属详情")} {"\u2192"}
                      </Link>
                    </div>
                  </Card>

                  <Card title={bi("Coverage by source", "各来源覆盖")} note={bi("Different sources start at different dates. A missing source is a coverage difference, not zero activity.", "不同来源的起始时间不同；某来源缺失属于覆盖差异，不等同于没有活动。")}>
                    <div className="table-wrap">
                      <table className="data">
                        <thead>
                          <tr>
                            <th scope="col">{t("common.source")}</th>
                            <th scope="col" className="num">{t("common.records")}</th>
                            <th scope="col">{bi("Event dates", "事件日期")}</th>
                            <th scope="col">{bi("Published time", "公开时间")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.coverage.sources.map((source) => (
                            <tr key={source.source_id}>
                              <td>
                                <div className="cell-primary">{source.name}</div>
                                <div className="cell-sub mono">{source.source_id}</div>
                              </td>
                              <td className="num">{source.records.toLocaleString()}</td>
                              <td className="small muted nowrap">
                                {formatDate(source.min_event_date)} {"\u2192"} {formatDate(source.max_event_date)}
                              </td>
                              <td className="small">
                                {source.published_field_available ? <Badge tone="ok">{bi("yes", "有")}</Badge> : <Badge tone="neutral">{bi("not published", "未提供")}</Badge>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="card-footer">
                      {bi("Coverage window", "覆盖窗口")}: {formatDate(data.coverage.window.from)} {"\u2192"} {formatDate(data.coverage.window.to)}.{" "}
                      {bi("First observed", "首次采集")}: {formatDateTime(data.coverage.sources.find((row) => row.first_observed_at)?.first_observed_at ?? null)}
                    </div>
                  </Card>
                </div>

                {data.data_quality_notes.length ? (
                  <Card title={bi("Data quality notes for this organization", "该企业的数据质量说明")}>
                    <div className="stack" style={{ gap: 8 }}>
                      {data.data_quality_notes.map((note, index) => (
                        <Banner key={index} tone="neutral">
                          {note}
                        </Banner>
                      ))}
                    </div>
                  </Card>
                ) : null}

                <div className="grid cols-2">
                  <Card title={bi("Records per year by event type", "逐年记录数（按类型）")} note={bi("Years without attributed records are simply absent; they are not zero-activity claims.", "没有已归属记录的年份直接缺省，不代表该年没有活动。")}>
                    <YearSeries data={data.aggregations.by_year} />
                  </Card>
                  <Card title={bi("Records by FDA medical specialty", "按 FDA 医学专科分类")} note={bi("Category comes from the FDA classification dictionary by product code.", "类别由产品代码经 FDA 分类字典映射得到。")}>
                    <BarBreakdown rows={data.aggregations.by_category} limit={10} />
                  </Card>
                </div>

                <Card
                  title={bi("Recent records", "最近记录")}
                  note={bi("Latest 10 by event date. Click a row to open its official evidence.", "按事件日期排序的最新 10 条；点击可打开官方证据。")}
                  flush
                  actions={
                    <button type="button" className="link small" onClick={() => setTab("events")}>
                      {bi("All records", "全部记录")} {"\u2192"}
                    </button>
                  }
                >
                  {data.recent_events.length ? (
                    <EventTable items={data.recent_events} showOrganization={false} compact onOpen={(event) => setDrawerEvent(event.official_id)} />
                  ) : (
                    <EmptyState
                      title={bi("No attributed records in this snapshot", "本快照中没有已归属记录")}
                      description={bi(
                        "This is a coverage statement. The organization is tracked, but its applicant spellings returned no records from the collected sources, or none could be attributed.",
                        "这是一个覆盖范围说明。该企业已在名单中，但其申请人写法在所采集来源中未返回记录，或未能完成归属。",
                      )}
                    />
                  )}
                </Card>

                {data.aggregations.by_class.length ? (
                  <Card title={bi("Device class distribution", "器械等级分布")} note={bi("Class 3 is not a measure of innovation; it is a regulatory risk classification.", "3 类并不代表更具创新性，它只是监管风险分级。")}>
                    <BarBreakdown
                      rows={data.aggregations.by_class
                        .filter((row) => row.count > 0)
                        .map((row) => ({
                          id: row.device_class,
                          label: row.device_class === "unknown" ? bi("Class unknown", "等级未知") : "Class " + row.device_class,
                          counts: { "510k": 0, pma: 0, pma_supplement: 0, recall: row.count },
                          total: row.count,
                        }))}
                      limit={4}
                    />
                  </Card>
                ) : null}
              </>
            ) : null}

            {tab === "events" ? (
              <OrganizationEventsTab
                orgKey={data.key}
                displayName={data.display_name}
                categories={meta.data?.categories ?? []}
                onOpen={setDrawerEvent}
                onNavigateToEvent={(event) => navigate("/events/" + encodeURIComponent(event.event_id))}
              />
            ) : null}

            {tab === "attribution" ? (
              <Card title={bi("Attribution detail", "归属详情")} note={data.registry.attribution_note}>
                <SectionHead title={bi("Accepted applicant spellings", "已接受的申请人写法")} note={bi("Exact strings from the reviewed registry, with the number of records each returned.", "来自复核登记表的精确字符串，以及各自对应的记录数。")} />
                {data.attribution.examples.length ? (
                  <div className="table-wrap">
                    <table className="data">
                      <thead>
                        <tr>
                          <th scope="col">{bi("Applicant spelling (verbatim)", "申请人写法（原始）")}</th>
                          <th scope="col">{bi("Basis", "依据")}</th>
                          <th scope="col">{t("common.review")}</th>
                          <th scope="col" className="num">{t("common.records")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.attribution.examples.map((row) => (
                          <tr key={row.applicant_name}>
                            <td className="mono small">{row.applicant_name}</td>
                            <td className="small">{row.basis}</td>
                            <td>
                    <VerificationBadge
                      status={row.status ?? (row.review === "pending_review" ? "proposed" : "rule_verified")}
                      labelEn={row.status_label_en}
                      labelZh={row.status_label_zh}
                      compact
                    />
                  </td>
                            <td className="num">{row.record_count.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState title={bi("No accepted spellings", "没有已接受的写法")} />
                )}

                {data.attribution.rejected_spellings.length ? (
                  <>
                    <div className="divider" />
                    <SectionHead title={bi("Rejected similar names", "已排除的近似名称")} note={bi("These strings look similar but belong to a different business, so their records are never counted here.", "这些字符串看似相近但属于不同业务，其记录不会计入本企业。")} />
                    <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
                      {data.attribution.rejected_spellings.map((row) => (
                        <li key={row.applicant_name}>
                          <span className="mono">{row.applicant_name}</span> - {row.reason}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}

                <div className="divider" />
                <Callout>
                  {bi(
                    data.attribution.unattributed_in_scope + " record(s) were retrieved inside this organization's search scope but could not be attributed to any tracked organization. They are listed in the attribution audit on the sources page and are not counted as this organization's activity.",
                    data.attribution.unattributed_in_scope + " 条记录在该企业的搜索范围内被检索到，但无法归属到任何收录企业。它们列在“数据来源与覆盖”页面的归属审计中，不计入本企业活动。",
                  )}
                </Callout>
                <div className="mt-12">
                  <Link className="link small" to="/sources">
                    {bi("Open the attribution audit", "打开归属审计")} {"\u2192"}
                  </Link>
                </div>
              </Card>
            ) : null}

            <Callout>
              {bi(
                "Every number on this page is a count of regulatory records attributed by exact applicant spelling in snapshot " + data.snapshot.id + " (collected " + data.snapshot.collected_at + ").",
                "本页每个数字都是快照 " + data.snapshot.id + "（采集于 " + data.snapshot.collected_at + "）中按申请人精确字符串归属的监管记录计数。",
              )}
            </Callout>
          </div>

          {drawerEvent ? <EvidenceDrawer eventId={drawerEvent} onClose={() => setDrawerEvent(null)} /> : null}
        </>
      )}
    </AsyncSection>
  );
}

function OrganizationEventsTab({
  orgKey,
  displayName,
  categories,
  onOpen,
}: {
  orgKey: string;
  displayName: string;
  categories: { id: string; label: string }[];
  onOpen: (id: string) => void;
  onNavigateToEvent: (event: EventRecord) => void;
}) {
  const { t, bi } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const state = useMemo(() => ({ ...defaultFilters(), ...parseFilters(searchParams.toString()), org: orgKey }), [searchParams, orgKey]);
  const query = toQueryString(state);
  const events = useAsync(
    () =>
      listOrganizationEvents(orgKey, {
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
    [query, orgKey],
  );

  useEffect(() => {
    return () => undefined;
  }, []);

  const apply = (next: EventsFilterState) => setSearchParams(new URLSearchParams(toQueryString({ ...next, org: "" }).replace(/^\?/, "")));

  const exportHref = exportEventsCsvUrl({
    org: [orgKey],
    types: state.types.length ? state.types : undefined,
    from: state.from || undefined,
    to: state.to || undefined,
    category: state.category ? [state.category] : undefined,
    q: state.q || undefined,
    review: state.review || undefined,
    sort: state.sort,
  });

  return (
    <div className="stack">
      <EventsFilterBar state={state} categories={categories} onChange={apply} onReset={() => apply({ ...defaultFilters(), org: orgKey })} showOrganization={false} resultCount={events.data?.total} />
      <div className="row between">
        <div className="filter-summary">
          <b>{displayName}</b> - <span className="count">{events.data?.total ?? 0}</span> {t("common.records")}
        </div>
        <ExportLink href={exportHref}>{t("common.export") + " CSV"}</ExportLink>
      </div>
      <Card flush>
        {events.status === "error" && events.error ? (
          <ErrorState message={events.error.message} onRetry={events.reload} />
        ) : !events.data ? (
          <div className="card-body">
            <LoadingBlock lines={8} />
          </div>
        ) : events.data.items.length ? (
          <>
            <EventTable items={events.data.items} sort={state.sort} onSort={(sort) => apply({ ...state, sort, page: 1 })} onOpen={(event) => onOpen(event.event_id)} showOrganization={false} />
            <Pagination page={events.data.page} totalPages={events.data.total_pages} total={events.data.total} onPage={(page) => apply({ ...state, page })} />
          </>
        ) : (
          <EmptyState
            title={bi("No records match these filters", "没有符合当前筛选条件的记录")}
            description={bi("Relax the filters to see this organization's records in the snapshot.", "放宽筛选条件以查看该企业在本快照中的记录。")}
          />
        )}
      </Card>
    </div>
  );
}
