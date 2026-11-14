import { Link, useNavigate } from "react-router-dom";
import { getMeta, listEvents, listOrganizations } from "../api/client";
import type { EventRecord } from "../api/types";
import { useAsync } from "../api/hooks";
import { AsyncSection } from "../components/async";
import { TypeLegend, YearSeries } from "../components/charts";
import { EventTable } from "../components/EventTable";
import { Badge, Banner, Callout, Card, EmptyState, EventTypeBadge, FreshnessBadge, Grid, LoadingBlock, MetricTile, PageHeader, SectionHead, formatDate } from "../components/ui";
import { useI18n } from "../i18n";

export function OverviewPage() {
  const { t, bi } = useI18n();
  const navigate = useNavigate();
  const meta = useAsync(() => getMeta(), []);
  const organizations = useAsync(() => listOrganizations(), []);
  const latest = useAsync(() => listEvents({ page_size: 12, sort: "event_date_desc" }), []);

  return (
    <>
      <PageHeader
        eyebrow="MedRadar - Product 001"
        title={t("overview.title")}
        description={t("overview.desc")}
        actions={
          <>
            <Link className="btn primary" to="/events">
              {bi("Open event browser", "打开事件浏览器")}
            </Link>
            <Link className="btn" to="/compare">
              {bi("Compare organizations", "企业对比")}
            </Link>
          </>
        }
      />

      <div className="stack">
        <AsyncSection status={meta.status} data={meta.data} error={meta.error} reload={meta.reload} loadingLines={2}>
          {(data) => (
            <>
              {data.freshness.state === "stale" ? (
                <Banner tone="warning" title={bi("This snapshot is older than the freshness threshold", "该快照已超过新鲜度阈值")}>
                  {bi(
                    "Collected " + data.snapshot.collected_at + ", " + (data.freshness.age_days ?? "?") + " days ago. Regenerate with python scripts/product_collect.py before relying on it.",
                    "采集于 " + data.snapshot.collected_at + "，距今 " + (data.freshness.age_days ?? "?") + " 天。如需依赖该数据，请先运行 python scripts/product_collect.py 重新采集。",
                  )}
                </Banner>
              ) : null}

              <section>
                <SectionHead
                  title={t("overview.coverage")}
                  note={bi(
                    "Every number links back to the openFDA records and the collection manifest.",
                    "每个数字都可回溯到 openFDA 原始记录和采集清单。",
                  )}
                  actions={<FreshnessBadge state={data.freshness.state} ageDays={data.freshness.age_days} threshold={data.freshness.threshold_days} />}
                />
                <Grid cols={6}>
                  <MetricTile label={bi("Tracked organizations", "收录企业")} value={data.coverage.tracked_organizations} sub={bi("with a reviewed identity entry", "均有身份登记与归属规则")} />
                  <MetricTile label={bi("Attributed records", "已归属记录")} value={data.coverage.attributed_records.toLocaleString()} sub={bi("counted as company activity", "计入企业活动")} accent />
                  <MetricTile label={bi("All collected records", "采集记录总数")} value={data.coverage.total_records.toLocaleString()} sub={bi("including unattributed records", "包含未归属记录")} />
                  <MetricTile label={bi("Sources", "数据来源")} value={data.sources.filter((source) => source.collected).length} sub={bi("openFDA device endpoints", "openFDA 器械端点")} />
                  <MetricTile
                    label={bi("Event date range", "事件日期范围")}
                    value={<span style={{ fontSize: 15, fontWeight: 600 }}>{formatDate(data.coverage.earliest_event_date)}</span>}
                    sub={bi("to ", "至 ") + formatDate(data.coverage.latest_event_date)}
                  />
                  <MetricTile
                    label={bi("Snapshot collected", "快照采集时间")}
                    value={<span style={{ fontSize: 15, fontWeight: 600 }}>{data.snapshot.collected_at.slice(0, 10)}</span>}
                    sub={bi("source last updated " + (data.snapshot.openfda_last_updated ?? "unknown"), "来源最后更新 " + (data.snapshot.openfda_last_updated ?? "未知"))}
                  />
                </Grid>
              </section>

              <section>
                <SectionHead title={t("overview.startHere")} />
                <Grid cols={3}>
                  <Card>
                    <div className="strong">{bi("1. Search an organization", "1. 搜索一家企业")}</div>
                    <p className="small muted mt-8" style={{ lineHeight: 1.55 }}>
                      {bi(
                        "Search by English name, known brand, ticker or verified applicant spelling. Results are organizations, not raw FDA applicant strings.",
                        "按英文名称、已知品牌、股票代码或已验证的申请人名称搜索。搜索结果是收录企业，而非原始 FDA 申请人字符串。",
                      )}
                    </p>
                    <div className="mt-12">
                      <Link className="link" to="/organizations">
                        {bi("Browse all tracked organizations", "浏览全部收录企业")} {"\u2192"}
                      </Link>
                    </div>
                  </Card>
                  <Card>
                    <div className="strong">{bi("2. Read the regulatory record", "2. 查看监管记录")}</div>
                    <p className="small muted mt-8" style={{ lineHeight: 1.55 }}>
                      {bi(
                        "Event browser across 510(k), PMA and recalls with date, category and attribution filters. Every row opens its official FDA record.",
                        "在 510(k)、PMA 与召回记录中按日期、类别与归属状态筛选；每一行都可打开对应的 FDA 官方记录。",
                      )}
                    </p>
                    <div className="mt-12">
                      <Link className="link" to="/events">
                        {bi("Open the event browser", "打开事件浏览器")} {"\u2192"}
                      </Link>
                    </div>
                  </Card>
                  <Card>
                    <div className="strong">{bi("3. Compare two organizations", "3. 对比两家企业")}</div>
                    <p className="small muted mt-8" style={{ lineHeight: 1.55 }}>
                      {bi(
                        "One window, one counting rule, explicit coverage warnings, and a Markdown report you can attach to an internal note.",
                        "同一时间窗口、同一统计口径、明确的覆盖差异提示，并可导出可直接引用的 Markdown 报告。",
                      )}
                    </p>
                    <div className="mt-12">
                      <Link className="link" to="/compare?orgs=medtronic,ge_healthcare">
                        {bi("Compare Medtronic and GE HealthCare", "对比美敦力与 GE 医疗")} {"\u2192"}
                      </Link>
                    </div>
                  </Card>
                </Grid>
              </section>

              <div className="grid cols-2">
                <Card
                  title={t("overview.featured")}
                  note={bi("Featured organizations in this snapshot, ordered by attributed records.", "本快照的重点企业，按已归属记录数排序。")}
                  flush
                  actions={<Link className="link small" to="/organizations">{t("common.all")} {"\u2192"}</Link>}
                >
                  <AsyncSection status={organizations.status} data={organizations.data} error={organizations.error} reload={organizations.reload} loadingLines={6}>
                    {(payload) => {
                      const rows = payload.organizations
                        .filter((org) => org.featured)
                        .sort((a, b) => b.event_count - a.event_count)
                        .slice(0, 8);
                      if (!rows.length) return <EmptyState title={t("state.empty")} />;
                      return (
                        <div className="table-wrap">
                          <table className="data">
                            <thead>
                              <tr>
                                <th scope="col">{t("common.organization")}</th>
                                <th scope="col" className="num">{t("common.records")}</th>
                                <th scope="col">{bi("Event dates", "事件日期")}</th>
                                <th scope="col">{t("common.review")}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rows.map((org) => (
                                <tr key={org.key} className="clickable" onClick={() => navigate("/organizations/" + org.key)} tabIndex={0} onKeyDown={(event) => event.key === "Enter" && navigate("/organizations/" + org.key)}>
                                  <td>
                                    <div className="cell-primary">{org.display_name}</div>
                                    <div className="cell-sub">{org.ticker ? org.ticker + " - " : ""}{org.legal_name ?? ""}</div>
                                  </td>
                                  <td className="num">{org.event_count.toLocaleString()}</td>
                                  <td className="small muted nowrap">{org.event_range.from ?? "-"} {"\u2192"} {org.event_range.to ?? "-"}</td>
                                  <td>{org.attribution_review === "pending_review" ? <Badge tone="warn">{t("review.pending_review")}</Badge> : <Badge tone="neutral">{t("review.curated")}</Badge>}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    }}
                  </AsyncSection>
                </Card>

                <Card
                  title={t("overview.latest")}
                  note={bi("Latest records by event date, with first-observed time available in the evidence panel.", "按事件日期排序的最新记录；首次采集时间可在证据面板查看。")}
                  flush
                  actions={<Link className="link small" to="/events">{t("common.all")} {"\u2192"}</Link>}
                >
                  <AsyncSection status={latest.status} data={latest.data} error={latest.error} reload={latest.reload} loadingLines={6}>
                    {(payload) => <EventTable items={payload.items.slice(0, 8)} onOpen={(event) => navigate("/events/" + encodeURIComponent(event.official_id))} compact />}
                  </AsyncSection>
                </Card>
              </div>

              <Card title={t("overview.methodology")}>
                <div className="grid cols-2">
                  <div>
                    <div className="row wrap" style={{ gap: 6 }}>
                      <EventTypeBadge type="510k" />
                      <EventTypeBadge type="pma" />
                      <EventTypeBadge type="pma_supplement" />
                      <EventTypeBadge type="recall" />
                    </div>
                    <p className="small muted mt-8" style={{ lineHeight: 1.6 }}>
                      {bi(
                        "Event types are never merged. A PMA supplement is a change to an approved device, not a new device. A recall is a safety action, not a product launch. A count of records is not a measure of innovation.",
                        "不同事件类型从不合并统计。PMA 补充批准是对已批准器械的变更，不是新器械；召回是安全行动，不是产品发布。记录数并不等同于创新能力。",
                      )}
                    </p>
                  </div>
                  <div>
                    <div className="callout">
                      {bi(
                        "Four times are kept separate: event date (when it happened), source publication date (only when the source states it), first observed by MedRadar (snapshot collection time), and available-at (the conservative lower bound).",
                        "四类时间严格区分：事件日期（事件发生时间）、来源公开时间（仅当来源明确给出）、MedRadar 首次采集时间（快照采集时间），以及可用于分析的时间（保守下界）。",
                      )}
                      <div className="mt-8">
                        <Link className="link small" to="/sources">
                          {bi("Read the full data contract and limits", "查看完整数据契约与限制")} {"\u2192"}
                        </Link>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="divider" />
                <SectionHead title={bi("Records per year across the whole snapshot", "全快照逐年记录数")} note={bi("Attributed records only.", "仅统计已归属记录。")} />
                {latest.data ? <TypeLegend /> : <LoadingBlock lines={2} />}
                {latest.data ? <YearSeries data={aggregationsFromEvents(latest.data.items)} /> : null}
              </Card>

              <Callout>
                {bi(
                  "Data scope: " + data.coverage.tracked_organizations + " tracked organizations, " + data.coverage.total_records.toLocaleString() + " collected records, snapshot " + data.snapshot.id + ". Sources and their limits are listed on the Sources & coverage page.",
                  "数据范围：" + data.coverage.tracked_organizations + " 家收录企业，" + data.coverage.total_records.toLocaleString() + " 条采集记录，快照 " + data.snapshot.id + "。数据来源及其限制见“数据来源与覆盖”页面。",
                )}
              </Callout>
            </>
          )}
        </AsyncSection>
      </div>
    </>
  );
}

function aggregationsFromEvents(items: EventRecord[]) {
  const byYear = new Map<string, { year: string; counts: Record<string, number>; total: number }>();
  for (const item of items) {
    if (!item.event_date) continue;
    const year = item.event_date.slice(0, 4);
    const row = byYear.get(year) ?? { year, counts: { "510k": 0, pma: 0, pma_supplement: 0, recall: 0 }, total: 0 };
    row.counts[item.event_type] = (row.counts[item.event_type] ?? 0) + 1;
    row.total += 1;
    byYear.set(year, row);
  }
  return [...byYear.values()].sort((a, b) => a.year.localeCompare(b.year));
}
