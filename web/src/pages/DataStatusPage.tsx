import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getChanges, getDataStatus } from "../api/client";
import { useAsync } from "../api/hooks";
import type { ChangeRecord, DataStatusSource } from "../api/types";
import { AsyncSection } from "../components/async";
import {
  Badge,
  Banner,
  Callout,
  Card,
  EmptyState,
  Grid,
  KeyValue,
  MetricTile,
  PageHeader,
  SectionHead,
  formatDate,
  formatDateTime,
  formatNumber,
} from "../components/ui";
import { useI18n } from "../i18n";

const CHANGE_TYPES = ["ADDED", "UPDATED", "REMOVED_CONFIRMED", "MISSING_ON_RECHECK", "UNRESOLVED"];
const SOURCE_OPTIONS = [
  ["", "All sources"],
  ["openfda_510k", "FDA 510(k)"],
  ["openfda_pma", "FDA PMA / supplements"],
  ["openfda_recall", "FDA device recalls"],
  ["openfda_classification", "FDA classification dictionary"],
];

function statusTone(status: string): "ok" | "warn" | "danger" | "neutral" | "info" {
  if (status === "NO_CHANGE") return "ok";
  if (status === "UPDATE_AVAILABLE") return "info";
  if (status === "CHECK_FAILED" || status === "SOURCE_DEGRADED") return "danger";
  return "neutral";
}

function stateTone(state: string): "info" | "warning" | "danger" | "neutral" {
  if (state === "ok") return "info";
  if (state === "update_available" || state === "unverified" || state === "partial") return "warning";
  if (state === "degraded") return "danger";
  return "neutral";
}

function RecordSummary({ row }: { row: ChangeRecord }) {
  const { bi } = useI18n();
  const fields = useMemo(() => Object.entries(row.changed_fields ?? {}), [row.changed_fields]);
  const officialUrl =
    (row.evidence?.official_url as string | undefined) ??
    (row.record?.official_url as string | undefined) ??
    null;
  return (
    <details className="change-row">
      <summary>
        <span className="mono small">{row.official_record_id || row.event_id}</span>{" "}
        <Badge tone={row.change_type === "ADDED" ? "ok" : row.change_type === "UPDATED" ? "info" : "warn"}>
          {row.change_type}
        </Badge>{" "}
        {row.record?.event_type ? <span className="small muted">{row.record.event_type}</span> : null}
      </summary>
      <div className="change-body">
        <KeyValue
          rows={[
            { label: bi("Source", "来源"), value: <span className="mono small">{row.source_id}</span> },
            { label: bi("Detected by MedRadar", "MedRadar 发现时间"), value: formatDateTime(row.detected_at) },
            {
              label: bi("Official endpoint version", "官方接口版本"),
              value: row.source_updated_at ? formatDate(row.source_updated_at) : "-",
            },
            {
              label: bi("Regulatory event date", "监管事件日期"),
              value: row.event_date ? formatDate(row.event_date) : <span className="muted">{bi("not stated", "来源未提供")}</span>,
            },
            { label: bi("Applicant at change time", "变化时申请人"), value: row.applicant_name || "-" },
            {
              label: bi("Snapshots", "快照"),
              value: (
                <span className="mono tiny">
                  {row.previous_snapshot_id || "-"} {"\u2192"} {row.candidate_snapshot_id}
                </span>
              ),
            },
          ]}
        />
        {fields.length ? (
          <>
            <SectionHead title={bi("Changed fields", "变化字段")} note={bi("Previous value -> current value. Long values are bounded for display.", "旧值 -> 新值；过长内容仅为展示做了截断。")} />
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">{bi("Field", "字段")}</th>
                    <th scope="col">{bi("Previous", "旧值")}</th>
                    <th scope="col">{bi("Current", "新值")}</th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map(([field, values]) => (
                    <tr key={field}>
                      <td className="mono small">{field}</td>
                      <td className="small">{String(values.previous ?? "-")}</td>
                      <td className="small">{String(values.current ?? "-")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="small muted mt-8">
            {bi(
              "No changed content fields are stored for this change type. The linked record is the evidence.",
              "该类变化没有可展示的内容字段差异；链接的官方记录即为证据。",
            )}
          </div>
        )}
        {officialUrl ? (
          <div className="mt-12">
            <a className="link small" href={officialUrl} target="_blank" rel="noopener noreferrer">
              {bi("Open official FDA record", "打开 FDA 官方记录")}
            </a>
          </div>
        ) : null}
      </div>
    </details>
  );
}

function SourceTable({ sources }: { sources: DataStatusSource[] }) {
  const { bi } = useI18n();
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th scope="col">{bi("Source", "数据源")}</th>
            <th scope="col">{bi("Monitor state", "监控状态")}</th>
            <th scope="col">{bi("Official version", "官方版本")}</th>
            <th scope="col">{bi("Last checked", "最近检查")}</th>
            <th scope="col">{bi("Last successful sync", "最近成功同步")}</th>
            <th scope="col" className="num">{bi("Added", "新增")}</th>
            <th scope="col" className="num">{bi("Updated", "修订")}</th>
            <th scope="col" className="num">{bi("Removed / missing", "确认移除/待复核")}</th>
            <th scope="col">{bi("Declared frequency", "官方声明频率")}</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.source_id}>
              <td>
                <div className="cell-primary">{source.source_name}</div>
                <div className="cell-sub mono">{source.source_id}</div>
                <div className="cell-sub">{source.note}</div>
              </td>
              <td>
                <Badge tone={statusTone(source.status)}>{source.status}</Badge>
                {source.update_available ? (
                  <div className="cell-sub">
                    <Badge tone="warn">{bi("update pending", "等待同步")}</Badge>
                  </div>
                ) : null}
                {source.consecutive_failures ? (
                  <div className="cell-sub danger-text">{source.consecutive_failures} {bi("consecutive failures", "次连续失败")}</div>
                ) : null}
                {source.message ? <div className="cell-sub">{source.message}</div> : null}
                {source.last_full_reconciliation_at ? (
                  <div className="cell-sub">
                    {bi("Full reconcile", "完整核对")}: {formatDateTime(source.last_full_reconciliation_at)}
                    {source.reconciliation_mode ? " · " + source.reconciliation_mode : ""}
                  </div>
                ) : null}
              </td>
              <td>
                <div className="mono small">{source.official_last_updated ?? "-"}</div>
                <div className="cell-sub">
                  {source.freshness_age_days !== null
                    ? source.freshness_age_days + " " + bi("days since official version", "天前官方版本")
                    : bi("unknown", "未知")}
                </div>
                <div className="cell-sub">{source.official_total !== null ? formatNumber(source.official_total) + " " + bi("official records", "官方记录") : ""}</div>
                {source.last_success_official_last_updated &&
                source.last_success_official_last_updated !== source.official_last_updated ? (
                  <div className="cell-sub">
                    {bi("last synced", "最近同步版本")}: {source.last_success_official_last_updated}
                  </div>
                ) : null}
              </td>
              <td className="small">{source.last_checked_at ? formatDateTime(source.last_checked_at) : "-"}</td>
              <td className="small">{source.last_success_sync_at ? formatDateTime(source.last_success_sync_at) : "-"}</td>
              <td className="num">{source.added_since_previous ?? "-"}</td>
              <td className="num">{source.updated_since_previous ?? "-"}</td>
              <td className="num">
                {source.removed_confirmed_since_previous ?? "-"} / {source.missing_on_recheck_since_previous ?? "-"}
              </td>
              <td className="small">
                {source.declared_frequency}
                <div className="cell-sub">{bi("MedRadar checks every", "MedRadar 每")} {source.check_interval_hours}h</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DataStatusPage() {
  const { t, bi } = useI18n();
  const status = useAsync(() => getDataStatus(), []);
  const [source, setSource] = useState("");
  const [type, setType] = useState("");
  const [org, setOrg] = useState("");
  const [nonce, setNonce] = useState(0);
  const changes = useAsync(() => getChanges({ source, type, org, limit: 50 }), [source, type, org, nonce]);

  return (
    <>
      <PageHeader
        eyebrow={bi("Data lifecycle", "数据生命周期")}
        title={t("dataStatus.title")}
        description={t("dataStatus.desc")}
        actions={
          <button type="button" className="btn" onClick={() => { status.reload(); changes.reload(); }}>
            {bi("Refresh", "刷新")}
          </button>
        }
      />

      <div className="stack">
        <AsyncSection status={status.status} data={status.data} error={status.error} reload={status.reload} loadingLines={8}>
          {(data) => (
            <>
              <Banner
                tone={data.configured ? stateTone(data.state) : "warning"}
                title={
                  data.configured
                    ? bi("Continuously Monitored / Automatically Synchronized", "持续监控 / 自动同步")
                    : bi("Continuous pipeline is not configured on this deployment", "此部署尚未启用持续数据管道")
                }
              >
                {data.message}
              </Banner>

              {data.dataset_error ? (
                <Banner tone="danger" title={bi("Active snapshot is not readable by the product", "当前快照无法被产品读取")}>
                  {data.dataset_error}
                </Banner>
              ) : null}

              {!data.terminology.real_time_claim ? (
                <Callout>
                  {bi(
                    "This page does not claim real-time data. MedRadar can only observe records after FDA publishes them, and it publishes a new snapshot only after a complete scoped collection and validation. Discovery time is not a regulatory event date.",
                    "本页不使用“实时数据”表述。MedRadar 只能在 FDA 公开记录后观察到它，并且只有在完整范围采集与验证通过后才发布新快照。发现时间不是监管事件日期。",
                  )}
                </Callout>
              ) : null}

              <Grid cols={4}>
                <MetricTile
                  label={bi("Active data snapshot", "当前数据快照")}
                  value={data.snapshot?.id?.replace("fda-snapshot-", "") ?? "-"}
                  sub={data.snapshot?.collected_at ? formatDateTime(data.snapshot.collected_at) : bi("no snapshot", "无快照")}
                  accent
                />
                <MetricTile
                  label={bi("Last successful sync", "最近成功同步")}
                  value={data.synchronization.last_successful_sync ? formatDate(data.synchronization.last_successful_sync) : "-"}
                  sub={data.synchronization.last_successful_sync ? formatDateTime(data.synchronization.last_successful_sync) : bi("not recorded", "未记录")}
                />
                <MetricTile
                  label={bi("Last check attempt", "最近检查时间")}
                  value={data.synchronization.last_check_attempt ? formatDate(data.synchronization.last_check_attempt) : "-"}
                  sub={data.configured ? bi("per-source state below", "下方为各来源状态") : bi("pipeline not configured", "管道未配置")}
                />
                <MetricTile
                  label={bi("Changes in active snapshot", "当前快照变化")}
                  value={formatNumber(Object.values(data.change_counts).reduce((sum, value) => sum + value, 0))}
                  sub={Object.entries(data.change_counts).map(([key, value]) => key + ": " + value).join(" · ") || bi("none recorded", "无记录")}
                />
              </Grid>

              {data.health ? (
                <Card
                  title={bi("Operational health, separated by question", "分层的运行健康状态")}
                  note={bi(
                    "Web liveness, data readability, synchronization health and source freshness are different facts. A live process is not a successful sync.",
                    "Web 进程存活、数据可读、同步健康和来源新鲜度是不同事实；进程存活不代表同步成功。",
                  )}
                >
                  <div className="grid cols-3">
                    <div>
                      <div className="cell-sub">{bi("Data health", "数据健康")}</div>
                      <Badge tone={data.health.data.state === "available" ? "ok" : "warn"}>{data.health.data.state}</Badge>
                      {data.health.data.using_fallback ? (
                        <div className="cell-sub danger-text">{bi("serving the previous validated snapshot", "正在使用上一个已验证快照")}</div>
                      ) : null}
                    </div>
                    <div>
                      <div className="cell-sub">{bi("Sync health", "同步健康")}</div>
                      <Badge tone={data.health.sync.state === "ok" ? "ok" : data.health.sync.state === "unknown" ? "neutral" : "warn"}>
                        {data.health.sync.state}
                      </Badge>
                      <div className="cell-sub">
                        {bi("latest run", "最近运行")}: {String(data.health.sync.latest_run_status ?? "-")}
                      </div>
                    </div>
                    <div>
                      <div className="cell-sub">{bi("Source freshness", "来源新鲜度")}</div>
                      <Badge tone={data.health.freshness.state === "current" ? "ok" : "warn"}>{data.health.freshness.state}</Badge>
                      <div className="cell-sub">
                        {bi("official version", "官方版本")}: {String(data.health.freshness.latest_official_version ?? "-")}
                      </div>
                    </div>
                  </div>
                </Card>
              ) : null}

              <Card
                title={bi("Source monitoring state", "数据源监控状态")}
                note={bi("A failed check never means no change. The previous active snapshot remains in service until a candidate passes validation.", "检查失败不等于没有变化；候选快照通过验证前，旧活动快照继续提供服务。")}
                flush
              >
                <SourceTable sources={data.sources} />
              </Card>

              <Card title={bi("Snapshot and official versions", "快照与官方版本")} note={bi("The snapshot is immutable. The active pointer is switched only after validation.", "快照不可变；只有验证通过后才会切换活动指针。")}>
                <div className="grid cols-2">
                  <div>
                    <KeyValue
                      rows={[
                        { label: bi("Snapshot id", "快照 ID"), value: <span className="mono small">{data.snapshot?.id ?? "-"}</span> },
                        { label: bi("Schema", "结构版本"), value: <span className="mono small">{data.snapshot?.schema ?? "-"}</span> },
                        { label: bi("Collected at", "采集完成时间"), value: formatDateTime(data.snapshot?.collected_at) },
                        { label: bi("Published at", "发布时间"), value: formatDateTime(data.snapshot?.published_at) },
                        { label: bi("Previous snapshot", "上一快照"), value: <span className="mono small">{data.snapshot?.previous_snapshot_id ?? "-"}</span> },
                        { label: bi("Content hash", "内容哈希"), value: <span className="mono tiny">{data.snapshot?.content_hash ?? "-"}</span> },
                      ]}
                    />
                  </div>
                  <div>
                    <div className="card-note mb-8">{bi("Official source version represented by the snapshot", "本快照对应的官方数据源版本")}</div>
                    <div className="table-wrap">
                      <table className="data">
                        <thead>
                          <tr>
                            <th scope="col">{bi("Source", "来源")}</th>
                            <th scope="col">{bi("Official last updated", "官方最后更新")}</th>
                            <th scope="col" className="num">{bi("Official total", "官方总数")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(Object.entries(data.snapshot?.source_versions ?? {}) as [string, { official_last_updated: string | null; official_total: number | null }][]).map(([key, value]) => (
                            <tr key={key}>
                              <td className="mono small">{key}</td>
                              <td className="small">{value.official_last_updated ?? bi("unknown", "未知")}</td>
                              <td className="num">{value.official_total !== null && value.official_total !== undefined ? formatNumber(value.official_total) : "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
                <div className="divider" />
                <div className="grid cols-2">
                  <div>
                    <SectionHead title={bi("Latency, stated precisely", "延迟说明")} note={data.latency.statement} />
                    <KeyValue
                      rows={[
                        { label: bi("Official endpoint version", "官方接口版本"), value: data.latency.official_source_version ?? "-" },
                        { label: bi("Last check by MedRadar", "MedRadar 最近检查"), value: data.latency.last_checked_by_medradar ? formatDateTime(data.latency.last_checked_by_medradar) : "-" },
                        { label: bi("Last successful sync", "最近成功同步"), value: data.latency.last_successful_sync ? formatDateTime(data.latency.last_successful_sync) : "-" },
                        { label: bi("Sync lag after official version", "官方版本后同步间隔"), value: data.latency.sync_lag_hours !== null ? data.latency.sync_lag_hours + " h" : "-" },
                      ]}
                    />
                  </div>
                  <div>
                    <SectionHead title={bi("Four times kept separate", "四类时间严格区分")} note={bi("Defined by the pipeline, not inferred per screen.", "由管道统一定义，而不是逐屏推测。")} />
                    <div className="stack-sm">
                      {(data.snapshot?.time_semantics ?? []).map((row) => (
                        <div key={row.field} className="small">
                          <span className="mono">{row.field}</span> — {row.meaning}
                        </div>
                      ))}
                      {!(data.snapshot?.time_semantics ?? []).length ? (
                        <div className="small muted">
                          {bi("This legacy snapshot does not carry the DATA-001 time vocabulary. Its records use the snapshot collection time as first observed.", "该旧快照不包含 DATA-001 的时间词汇；记录以快照采集时间作为首次观察时间。")}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </Card>

              <Card
                title={bi("Last publication: what changed", "上次发布：发生了什么变化")}
                note={bi("A change is a change in an official source record detected by MedRadar. It is not by itself a new regulatory event.", "变化是 MedRadar 检测到的官方记录差异，本身不等于新的监管事件。")}
              >
                {data.change_feed.length ? (
                  <div className="change-list">
                    {data.change_feed.map((row) => (
                      <RecordSummary key={row.change_id} row={row} />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title={bi("No published change records", "尚无已发布变化记录")}
                    description={
                      data.configured
                        ? bi("The pipeline has not published a change set yet, or the last publication had no content changes.", "管道尚未发布变化集，或上次发布没有内容变化。")
                        : bi("The pipeline is not configured on this deployment.", "此部署尚未配置数据管道。")
                    }
                  />
                )}
                {data.change_feed.length ? (
                  <div className="small muted mt-12">
                    <Link className="link" to="/sources">{bi("See the full source and coverage audit", "查看完整来源与覆盖审计")}</Link>
                  </div>
                ) : null}
              </Card>

              <Card
                title={bi("Change feed", "变化列表")}
                note={bi("Filter the published ledger. Every row points to the official record and the snapshots in which the change was detected.", "筛选已发布台账；每行都指向官方记录和检测到变化的快照。")}
              >
                <div className="filter-bar">
                  <label className="field">
                    <span className="field-label">{bi("Source", "来源")}</span>
                    <select className="select" value={source} onChange={(event) => setSource(event.target.value)}>
                      {SOURCE_OPTIONS.map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">{bi("Change type", "变化类型")}</span>
                    <select className="select" value={type} onChange={(event) => setType(event.target.value)}>
                      <option value="">{bi("All types", "全部类型")}</option>
                      {CHANGE_TYPES.map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">{bi("Organization key", "企业标识")}</span>
                    <input className="input" value={org} onChange={(event) => setOrg(event.target.value)} placeholder="medtronic" />
                  </label>
                  <button type="button" className="btn" onClick={() => setNonce((value) => value + 1)}>
                    {bi("Apply filters", "应用筛选")}
                  </button>
                </div>
                <AsyncSection status={changes.status} data={changes.data} error={changes.error} reload={changes.reload} loadingLines={6}>
                  {(payload) => (
                    <>
                      {!payload.configured ? (
                        <div className="small muted">{payload.message}</div>
                      ) : (
                        <>
                          <div className="small muted mb-8">
                            {formatNumber(payload.total)} {bi("published change rows", "条已发布变化")}
                          </div>
                          <div className="change-list">
                            {payload.items.map((row) => <RecordSummary key={row.change_id} row={row} />)}
                          </div>
                          {!payload.items.length ? (
                            <EmptyState title={bi("No changes match these filters", "没有符合筛选的变化")} />
                          ) : null}
                        </>
                      )}
                    </>
                  )}
                </AsyncSection>
              </Card>
            </>
          )}
        </AsyncSection>
      </div>
    </>
  );
}
