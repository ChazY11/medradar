import { Link, useNavigate } from "react-router-dom";
import { getMeta, listEvents, listOrganizations } from "../api/client";
import { useAsync } from "../api/hooks";
import { AsyncSection } from "../components/async";
import { TypeLegend, YearSeries } from "../components/charts";
import { EventTable } from "../components/EventTable";
import { Badge, Banner, Callout, Card, EmptyState, EventTypeBadge, FreshnessBadge, Grid, LoadingBlock, MetricTile, PageHeader, SectionHead, formatDate } from "../components/ui";
import { MetricsStrip } from "../components/transparency";
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
        eyebrow={bi("MedRadar · Medical technology intelligence", "MedRadar · 医疗技术情报")}
        title={bi("Start a research task", "开始一项研究任务")}
        description={bi(
          "Turn traceable FDA device records into a defensible competitive brief: define a question, read the evidence, compare on one rule, verify the official record, and export the brief.",
          "把可追溯的 FDA 器械记录转化为可接受事实核查的竞争情报简报：定义问题、阅读证据、按同一口径比较、核验官方记录，并导出简报。",
        )}
        actions={
          <>
            <Link className="btn primary" to="/brief">
              {bi("Build an intelligence brief", "生成情报简报")}
            </Link>
            <Link className="btn" to="/compare">
              {bi("Compare organizations", "企业对比")}
            </Link>
            <Link className="btn ghost" to="/events">
              {bi("Event browser", "事件浏览器")}
            </Link>
          </>
        }
      />

      <div className="stack">
        <section className="grid cols-3">
          <Card>
            <div className="strong">{bi("Research a company", "研究一家企业")}</div>
            <p className="small muted mt-8" style={{ lineHeight: 1.55 }}>
              {bi(
                "Pick a company and a window. The brief shows pathway mix, official product-code families, PMA families, recent records and evidence-backed findings.",
                "选择企业与时间窗口。简报展示监管路径构成、官方产品代码家族、PMA 家族、近期记录与有证据支持的发现。",
              )}
            </p>
            <div className="mt-12">
              <Link className="link" to="/brief?mode=company&org=medtronic&years=5">
                {bi("Brief Medtronic for 2021–2025", "生成美敦力 2021–2025 简报")} {"\u2192"}
              </Link>
            </div>
          </Card>
          <Card>
            <div className="strong">{bi("Compare competitors", "比较竞争对手")}</div>
            <p className="small muted mt-8" style={{ lineHeight: 1.55 }}>
              {bi(
                "One window, one counting rule. Every difference is explainable down to the records, and the brief states where coverage or verification differs.",
                "同一窗口、同一统计口径。每项差异都可解释到具体记录，并明确说明覆盖或核验程度的差异。",
              )}
            </p>
            <div className="mt-12">
              <Link className="link" to="/brief?mode=compare&orgs=ge_healthcare,philips&years=5">
                {bi("GE HealthCare vs Philips", "GE HealthCare 对比 Philips")} {"\u2192"}
              </Link>
            </div>
          </Card>
          <Card>
            <div className="strong">{bi("Investigate a device family", "调查器械家族")}</div>
            <p className="small muted mt-8" style={{ lineHeight: 1.55 }}>
              {bi(
                "Follow one official PMA number: original approval, every supplement, official recalls linked by K number, and candidate relations kept separate.",
                "沿一个官方 PMA 编号追查：原始批准、全部补充申请、通过 K 号码关联的官方召回，并与候选关系严格区分。",
              )}
            </p>
            <div className="mt-12">
              <Link className="link" to="/brief?mode=device&device=P980016">
                {bi("Investigate PMA P980016", "调查 PMA P980016")} {"\u2192"}
              </Link>
            </div>
          </Card>
        </section>
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
                <details className="card">
                  <summary className="card-header" style={{ cursor: "pointer" }}>
                    <div>
                      <div className="card-title">{bi("How much of this data is verified?", "这些数据有多少经过核验？")}</div>
                      <div className="card-note">
                        {bi(
                          "Four different questions, four different numbers. Attributed share is not accuracy, and 99% attributed does not mean 99% correct.",
                          "四个不同的问题、四个不同的数字。已归属比例不是准确率；99% 已归属并不意味着 99% 正确。",
                        )}
                      </div>
                    </div>
                  </summary>
                  <div className="card-body">
                    <MetricsStrip />
                  </div>
                </details>
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
                <TypeLegend />
                {data.global_aggregations ? <YearSeries data={data.global_aggregations.by_year} /> : <LoadingBlock lines={2} />}
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
