import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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
  type FeedScope,
  type IntelDetail,
  type IntelEvent,
} from "../api/radar";
import { AsyncSection } from "../components/async";
import { DailyDigest } from "../components/DailyDigest";
import { ReviewPanel } from "../components/ReviewPanel";
import { WatchlistBar } from "../components/WatchlistBar";
import { exportUrl } from "../api/human";
import { cleanTitle } from "../lib/text";
import {
  Badge,
  Banner,
  Card,
  EmptyState,
  KeyValue,
  PageHeader,
  Pagination,
  Tabs,
  formatDate,
  formatDateTime,
  formatNumber,
  precisionLabel,
} from "../components/ui";

const LAST_VISIT_KEY = "medradar.radar.lastVisit";
const PAGE_SIZE = 20;
const CHANGE_STATES = ["NEW", "UPDATED", "REMOVED_OR_UNAVAILABLE", "FETCH_FAILED"] as const;
const CONFIRMATIONS: Confirmation[] = ["CONFIRMED", "CANDIDATE", "TOPIC_RELATED"];
const PHASES = ["INITIAL_DISCOVERY", "INCREMENTAL_DISCOVERY", "HISTORICAL_BACKFILL"] as const;

const ADMISSION_LABELS: Record<string, { en: string; zh: string; tone: "ok" | "warn" | "info" | "neutral" }> = {
  HIGH_RELEVANCE: { en: "Relevant", zh: "相关情报", tone: "ok" },
  NEEDS_REVIEW: { en: "Needs review", zh: "有待核实", tone: "warn" },
  LOW_RELEVANCE: { en: "Low relevance", zh: "低相关", tone: "neutral" },
  IRRELEVANT: { en: "Out of scope", zh: "不属于本范围", tone: "neutral" },
};

const ADMISSION_CATEGORY_ZH: Record<string, string> = {
  monitoring_technology_evaluation: "监护设备/算法性能研究",
  device_or_algorithm_needs_confirmation: "设备或算法线索，待确认",
  plausible_monitoring_technology: "可能相关，待确认",
  clinical_study_without_device_focus: "临床研究，未研究监护技术",
  clinical_prediction_model: "临床预测/风险模型",
  health_it_interoperability: "医疗信息化互操作",
  no_monitoring_technology: "未涉及监护技术",
  non_human_subject: "研究对象非人类患者",
  non_medical_domain: "非医疗监护领域",
  editorial_or_letter: "评论/通讯，非研究",
  regulatory_record: "监管记录（FDA）",
  vendor_statement: "厂商官方声明",
  primary_record_unmapped: "官方记录，未归入受监测主题",
  monitoring_technology_review: "监护技术综述",
  vendor_statement_monitoring: "厂商官方监护产品声明",
  regulatory_monitoring_device: "监管记录：受监测的监护设备",
  regulatory_other_device: "监管记录：非监护设备",
  official_statement_not_monitoring: "官方声明：不属于监护技术",
  clinical_application_of_monitoring: "临床使用监护技术，未研究技术本身",
  behaviour_or_workflow_monitoring: "行为/流程监测，非患者生理监测",
  measurement_without_technology_focus: "提及测量指标，未研究监护技术",
  security_architecture: "安全架构，非监护测量技术",
  methods_benchmark_on_monitoring_data: "基于监护数据的算法方法学研究",
  medical_not_monitoring: "医学内容，不涉及监护技术",
  bibliographic_notice: "书目通知（更正/撤稿）",
  no_monitoring_signal: "未发现监护技术信号",
  unclassified_record_type: "未分类记录类型",
};

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
  const [scope, setScope] = useState<FeedScope>("latest");
  const [filters, setFilters] = useState<FeedQuery>({});
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

  // The feed must paint before the status card. Health is expensive on a cold cache and used to
  // sit in the same request burst; it now starts only after the first page of intelligence is in.
  const [healthEnabled, setHealthEnabled] = useState(false);
  const health = useAsync(
    () => (healthEnabled ? getRadarHealth() : new Promise<never>(() => {})),
    [healthEnabled],
  );
  const facets = useAsync(() => getFeedFacets(), []);
  const feed = useAsync(
    () => getFeed({ ...filters, scope, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [JSON.stringify(filters), page, scope],
  );
  const notices = useAsync(() => getNotices(lastVisit), [lastVisit]);

  useEffect(() => {
    if (feed.status === "ready") setHealthEnabled(true);
  }, [feed.status]);

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

      <div className="radar-page">
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

      <DailyDigest />

      <div className="row wrap" style={{ gap: 12, marginBottom: 12, alignItems: "center" }}>
        <WatchlistBar
          filters={filters as Record<string, unknown>}
          onApply={(filter) => setFilters(filter as typeof filters)}
        />
        <a
          className="btn sm"
          href={exportUrl({ format: "csv", scope: filters.scope ?? "latest", source: filters.source,
                             organization: filters.organization, topic: filters.topic, q: filters.q, limit: 1000 })}
          download
        >
          {bi("Export these records (CSV)", "导出这些记录（CSV）")}
        </a>
      </div>

      <div className="radar-status">
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
                    {payload.ai?.state === "disabled"
                      ? bi("AI enrichment: not enabled", "AI 增强：本轮未启用")
                      : `${bi("AI backlog", "AI 队列")}: ${formatNumber(payload.backlog.backlog)}`}
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
      </div>

      <div className="radar-filters">
      <Card
        title={bi("Filters", "筛选")}
        note={bi("Filter by company, technology topic, source, dates and relation confidence.", "按企业、技术主题、来源、日期与关联置信度筛选。")}
        actions={
          activeFilterCount ? (
            <button type="button" className="btn sm" onClick={() => { setScope("latest"); setFilters({}); setPage(0); }}>
              {bi("Clear", "清除")} ({activeFilterCount})
            </button>
          ) : null
        }
      >
        <details className="filter-details" open>
          <summary>{bi("Show filters", "展开筛选条件")}</summary>
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
                    value={filters.order ?? (scope === "latest" ? "published" : "observed")}
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
        </details>
      </Card>
      </div>

      <div className="radar-feed">
      <Card
        title={bi("What counts as new", "什么算「新」")}
        note={bi(
          "Newly published means the source states a public date inside the window. Newly observed means MedRadar first saw it inside the window, even if the document is old. Only qualified monitoring-technology records reach these views.",
          "「最新发现」指来源声明的公开时间落在窗口内；「最新观察」指 MedRadar 在窗口内首次看到，即使文档本身很旧。只有通过准入的监护技术记录会进入这些视图。",
        )}
      >
        <Tabs
          items={[
            { id: "latest", label: bi("Newly published", "最新发现"), count: feed.data?.views?.latest },
            { id: "observed", label: bi("Newly observed", "最新观察"), count: feed.data?.views?.observed },
            { id: "archive", label: bi("Archive", "历史资料库"), count: feed.data?.views?.archive },
            { id: "review", label: bi("Needs review", "待核实"), count: feed.data?.views?.review },
          ]}
          active={scope}
          onChange={(next) => {
            setScope(next as FeedScope);
            setPage(0);
          }}
        />
        <div className="small muted" style={{ marginTop: 8 }}>
          {scope === "latest"
            ? bi("Published by the source in the last 30 days.", "来源在最近 30 天内公开的记录。")
            : scope === "observed"
              ? bi("First seen by MedRadar in the last 30 days; the document itself may be older.", "MedRadar 最近 30 天首次看到；文档本身可能较早。")
              : scope === "archive"
                ? bi("Every qualified record, including history imported at first load.", "所有通过准入的记录，包括首次导入的历史资料。")
                : bi("Records the rules are unsure about. They are not in the default feed.", "规则无法确定、暂不进入默认情报流的记录。")}
        </div>
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
                title={
                  scope === "latest"
                    ? bi("No new technology movement yet", "暂未发现新的技术动向")
                    : scope === "review"
                      ? bi("Nothing is waiting for review", "暂无待核实记录")
                      : bi("No observation matches", "没有匹配的观察")
                }
                description={
                  scope === "latest"
                    ? bi(
                        "No qualified monitoring-technology record was published by a monitored source in the last 30 days. This is a real result about the sources, not a broken page. Older qualified evidence is still in the archive.",
                        "最近 30 天内，受监测来源没有公开新的合格监护技术记录。这是关于来源的真实结果，不是页面故障。更早的合格证据仍在历史资料库中。",
                      )
                    : bi(
                        "This is an evidence statement about the filters and the monitored sources, not a claim that nothing exists. Clear the filters or wait for a scheduled check.",
                        "这是关于筛选条件与已监测来源的证据陈述，并不代表现实中不存在。请清除筛选，或等待下一次计划检查。",
                      )
                }
                actions={
                  scope === "latest" && (payload.views?.archive ?? 0) > 0 ? (
                    <button type="button" className="btn sm touch" onClick={() => setScope("archive")}>
                      {bi(`Browse the archive (${payload.views?.archive})`, `查看历史资料库（${payload.views?.archive}）`)}
                    </button>
                  ) : undefined
                }
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
      </div>

      {selected ? <IntelligenceDrawer observationId={selected} onClose={() => setSelected(null)} /> : null}
      </div>
    </>
  );
}

function FeedCard({ item, onOpen }: { item: IntelEvent; onOpen: () => void }) {
  const { bi, lang } = useI18n();
  return (
    <article className="card" style={{ padding: 16 }}>
      <div className="row between wrap" style={{ gap: 8 }}>
        <div className="row wrap" style={{ gap: 6 }}>
          <Badge tone={changeTone(item.change_state)}>{item.change_state}</Badge>
          <Badge tone="outline">{item.source}</Badge>
          <Badge tone="neutral">{item.record_type}</Badge>
          {item.admission ? (
            <Badge
              tone={ADMISSION_LABELS[item.admission.tier]?.tone ?? "neutral"}
              title={(item.admission.reasons ?? []).join(" · ")}
            >
              {bi(ADMISSION_LABELS[item.admission.tier]?.en ?? item.admission.tier,
                  ADMISSION_LABELS[item.admission.tier]?.zh ?? item.admission.tier)}
            </Badge>
          ) : null}
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
        <button type="button" className="btn sm touch" onClick={onOpen}>
          {bi("Evidence", "证据")}
        </button>
      </div>

      <h3 className="feed-title">
        {item.source_url ? (
          <a href={item.source_url} target="_blank" rel="noreferrer noopener">
            {cleanTitle(item.title)}
          </a>
        ) : (
          cleanTitle(item.title)
        )}
      </h3>

      <div className="feed-meta">
        <span>
          {bi("Published", "来源公开")}: {item.source_published_at ? formatDateTime(item.source_published_at, item.source_published_at_precision) : bi("not published by source", "来源未公布")}
        </span>
        <span>
          {bi("First observed", "MedRadar 首次发现")}: {formatDateTime(item.first_observed_at)}
        </span>
        {item.event_date ? (
          <span>
            {bi("Event date", "事件日期")}: {formatDate(item.event_date, item.event_date_precision)}
          </span>
        ) : null}
        {item.official_identifier ? <span className="mono small">{item.official_identifier}</span> : null}
      </div>

      {item.admission?.dimensions ? (
        <div className="row wrap small" style={{ gap: 6, marginTop: 8 }} title={bi(
          "The judgement is split into independent dimensions; the tier alone never carries all of them.",
          "判断被拆分为独立维度；单一等级不再承载全部含义。",
        )}>
          <span className="badge">{bi("source", "来源")} · {item.admission.dimensions.source_authenticity}</span>
          <span className="badge">{bi("domain", "领域")} · {item.admission.dimensions.medical_domain}</span>
          <span className="badge">{bi("relevance", "相关性")} · {item.admission.dimensions.monitoring_relevance}</span>
          <span className="badge">{bi("confidence", "置信度")} · {item.admission.dimensions.confidence}</span>
          {item.admission.dimensions.freshness ? (
            <span className="badge">{bi("date", "日期")} · {precisionLabel(item.admission.dimensions.freshness === "UNKNOWN" ? "unknown" : "date", lang)}</span>
          ) : null}
        </div>
      ) : null}

      {item.organization_candidates.length || item.technology_topics.length ? (
        <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
          {item.organization_candidates.map((org) => (
            <Link
              key={org.organization_id + org.confirmation}
              to={`/organizations/${encodeURIComponent(org.organization_id)}`}
              className={`badge ${confirmationTone(org.confirmation)}`}
              title={org.method}
            >
              {org.label_zh ?? org.display_name} · {org.confirmation}
            </Link>
          ))}
          {item.technology_topics.map((topic) => (
            <Link
              key={topic.topic_id + topic.confirmation}
              to={`/radar/technology-map`}
              className={`badge ${confirmationTone(topic.confirmation)}`}
              title={topic.method}
            >
              {bi(topic.label_en, topic.label_zh ?? topic.label_en)} · {topic.confirmation}
            </Link>
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

      <div className="feed-actions">
        {item.source_url ? (
          <a className="btn sm touch" href={item.source_url} target="_blank" rel="noreferrer noopener">
            {bi("Open official source", "打开官方来源")}
          </a>
        ) : null}
      </div>

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
                  <div className="mt-8" style={{ fontWeight: 620, lineHeight: 1.45 }}>{cleanTitle(payload.title)}</div>
                  {payload.source_url ? (
                    <a className="small" href={payload.source_url} target="_blank" rel="noreferrer noopener">
                      {bi("Open the original record", "打开原始记录")}
                    </a>
                  ) : null}
                  <ReviewPanel observationId={observationId} />
                </div>

                <div className="drawer-section">
                  <h3>{bi("Why this record is here", "为什么这条记录会出现")}</h3>
                  {payload.admission ? (
                    <>
                      <div className="row wrap" style={{ gap: 6 }}>
                        <Badge tone={ADMISSION_LABELS[payload.admission.tier]?.tone ?? "neutral"}>
                          {bi(ADMISSION_LABELS[payload.admission.tier]?.en ?? payload.admission.tier,
                              ADMISSION_LABELS[payload.admission.tier]?.zh ?? payload.admission.tier)}
                        </Badge>
                        <Badge tone="outline">
                          {bi(ADMISSION_CATEGORY_ZH[payload.admission.category] ?? payload.admission.category,
                              ADMISSION_CATEGORY_ZH[payload.admission.category] ?? payload.admission.category)}
                        </Badge>
                      </div>
                      <ul className="small" style={{ marginTop: 8 }}>
                        {payload.admission.reasons.map((reason, index) => (
                          <li key={index}>{bi(reason, reason)}</li>
                        ))}
                      </ul>
                      <div className="small muted">
                        {bi(
                          `Qualification score ${payload.admission.score}. A record is only in the default feed when the title itself is about a monitoring device or monitoring algorithm and evaluates it.`,
                          `准入评分 ${payload.admission.score}。只有标题本身研究监护设备或监护算法、并对其做出评估的记录，才进入默认情报流。`,
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="small muted">
                      {bi("No qualification decision is recorded for this observation yet.",
                          "该观察尚无准入判断记录。")}
                    </div>
                  )}
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
