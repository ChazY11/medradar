import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  getReviewToken,
  reviewCapabilities,
  reviewCase,
  reviewDecide,
  reviewImpact,
  reviewQueue,
  reviewRevoke,
  reviewSummary,
  reviewPing,
  setReviewToken,
  type ReviewCase,
  type ReviewEvidence,
  type ReviewImpact,
  type ReviewQueueItem,
  type ReviewQueueResponse,
  type ReviewSummary,
} from "../api/review";
import { getMetrics } from "../api/client";
import { useAsync } from "../api/hooks";
import { useI18n } from "../i18n";
import {
  Badge,
  Banner,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  Grid,
  KeyValue,
  LoadingBlock,
  MetricTile,
  PageHeader,
  Pagination,
  SectionHead,
  formatNumber,
} from "../components/ui";
import { MetricsStrip, VerificationBadge } from "../components/transparency";

const STATUS_OPTIONS = ["proposed", "rule_verified", "unresolved", "unmatched", "rejected", "evidence_verified", "human_reviewed"];
const RISK_OPTIONS = [
  "unmatched_string",
  "proposed_mapping",
  "corporate_relation",
  "multi_org_scope",
  "cross_org_token",
  "foreign_parent_us_operator",
  "predecessor_entity",
  "high_volume",
  "low_volume",
  "name_variant",
  "ambiguous_organization",
  "rejected_or_unresolved",
];
const EVIDENCE_TYPES = ["regulator_record", "jurisdiction_filing", "corporate_document", "third_party_report", "human_judgement", "agent_judgement"];

function TokenGate({ onReady }: { onReady: () => void }) {
  const { bi } = useI18n();
  const [value, setValue] = useState(getReviewToken() ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setReviewToken(value.trim());
    try {
      await reviewPing();
      onReady();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setReviewToken(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title={bi("Identity review is an internal workspace", "身份复核是内部工作区")}
      note={bi(
        "It can change what the product counts, so it only runs as a loopback-bound service and requires a token. Nothing on the public site can write an attribution.",
        "它可以改变产品的统计结果，因此只作为仅绑定本机的服务运行，并需要令牌。公开站点上的任何页面都不能写入归属。",
      )}
    >
      <Banner tone="info" title={bi("Start the review service", "启动复核服务")}>
        <code className="mono">python -m medradar.product.review serve --port 8788</code>
        <div className="small" style={{ marginTop: 6 }}>
          {bi("The command prints the token file path; open ", "该命令会打印令牌文件路径；请打开 ")}
          <code className="mono">http://127.0.0.1:8788/review</code>
          {bi(" and paste the token below.", " 并在下方粘贴令牌。")}
        </div>
      </Banner>
      <label className="field" style={{ marginTop: 12 }}>
        <span className="field-label">{bi("Review token", "复核令牌")}</span>
        <input
          className="input mono"
          type="password"
          value={value}
          autoComplete="off"
          onChange={(event) => setValue(event.target.value)}
          placeholder={bi("paste the token from data/identity/review.token", "粘贴 data/identity/review.token 中的令牌")}
          onKeyDown={(event) => {
            if (event.key === "Enter") void submit();
          }}
        />
      </label>
      {error ? <Banner tone="danger" title={bi("Token rejected", "令牌被拒绝")}>{error}</Banner> : null}
      <div className="row" style={{ marginTop: 10 }}>
        <button type="button" className="btn primary" disabled={!value.trim() || busy} onClick={() => void submit()}>
          {busy ? bi("Checking...", "校验中...") : bi("Unlock the workspace", "进入工作区")}
        </button>
        <Link to="/sources" className="link small">
          {bi("How attribution review works", "归属复核如何运作")}
        </Link>
      </div>
    </Card>
  );
}

export function ReviewPage() {
  const { bi, t } = useI18n();
  const [unlocked, setUnlocked] = useState(false);
  const [status, setStatus] = useState("");
  const [org, setOrg] = useState("");
  const [risk, setRisk] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("records_desc");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ping = useAsync(() => reviewPing(), [reloadKey]);
  useEffect(() => {
    if (ping.data?.ok) setUnlocked(true);
  }, [ping.data]);

  const queue = useAsync<ReviewQueueResponse>(
    () => reviewQueue({ status, org, risk, q: query, sort, page, pageSize: 25 }),
    [unlocked, status, org, risk, query, sort, page, reloadKey],
  );
  const summary = useAsync<ReviewSummary>(() => reviewSummary(), [unlocked, reloadKey]);
  const impact = useAsync<ReviewImpact>(() => reviewImpact(), [unlocked, reloadKey]);
  const caseState = useAsync<ReviewCase | null>(
    () => (selected ? reviewCase(selected) : Promise.resolve(null)),
    [selected, reloadKey],
  );
  const metrics = useAsync(() => getMetrics(), []);

  const refresh = () => setReloadKey((value) => value + 1);
  const rows = queue.data?.items ?? [];

  if (!unlocked) {
    return (
      <>
        <PageHeader
          eyebrow={bi("Internal tool", "内部工具")}
          title={bi("Identity review workspace", "身份复核工作台")}
          description={bi(
            "Review applicant mappings, record evidence and decisions, and see exactly which organizations change.",
            "复核申请人映射，记录证据与判定，并查看哪些企业因此发生变化。",
          )}
        />
        <div className="stack">
          {ping.status === "loading" ? <LoadingBlock lines={3} /> : null}
          <TokenGate onReady={() => { setUnlocked(true); refresh(); }} />
          {ping.error ? (
            <Banner tone="warning" title={bi("Review service not reachable on this origin", "当前来源无法访问复核服务")}>
              {ping.error.message}
            </Banner>
          ) : null}
        </div>
      </>
    );
  }

  const orgsWithVerified = metrics.data?.levels.organization;

  return (
    <>
      <PageHeader
        eyebrow={bi("Internal tool", "内部工具")}
        title={bi("Identity review workspace", "身份复核工作台")}
        description={bi(
          "Every decision is appended to an auditable ledger. A decision changes the public counts only for the applicant string you touch.",
          "每个判定都会追加到可审计的决策记录中；判定只影响你处理的那一个申请人名称对应的公开计数。",
        )}
        actions={
          <div className="row">
            <a className="btn sm" href="/api/review/export" download>
              {bi("Export decisions", "导出判定记录")}
            </a>
            <button type="button" className="btn sm" onClick={refresh}>
              {t("state.retry")}
            </button>
          </div>
        }
      />

      <div className="stack">
        {message ? <Banner tone="info" title={bi("Last action", "最近操作")}>{message}</Banner> : null}

        <Grid cols={4}>
          <MetricTile
            label={bi("Strings awaiting review", "待复核写法")}
            value={formatNumber(summary.data?.awaiting_review_strings ?? 0)}
            sub={bi("of " + formatNumber(summary.data?.queue_strings ?? 0) + " observed applicant strings", "共观察到 " + formatNumber(summary.data?.queue_strings ?? 0) + " 个申请人写法")}
          />
          <MetricTile
            label={bi("Records affected by the queue", "队列涉及记录")}
            value={formatNumber(summary.data?.awaiting_review_records ?? 0)}
            sub={bi("attributed records whose mapping is not yet verified", "归属尚未核验的记录")}
          />
          <MetricTile
            label={bi("Decisions recorded", "已记录判定")}
            value={formatNumber(summary.data?.ledger.decision_count ?? 0)}
            sub={bi(
              (summary.data?.ledger.human_reviewed_count ?? 0) + " human-reviewed, " + (summary.data?.ledger.agent_recorded_count ?? 0) + " recorded by an agent",
              (summary.data?.ledger.human_reviewed_count ?? 0) + " 个人工复核，" + (summary.data?.ledger.agent_recorded_count ?? 0) + " 个由代理记录",
            )}
          />
          <MetricTile
            label={bi("Ledger", "决策台账")}
            value={<span className="mono small">{summary.data?.ledger.db_path ?? "-"}</span>}
            sub={bi("append-only; corrections are new decisions", "只可追加；更正以新判定记录")}
          />
        </Grid>

        {metrics.data ? <MetricsStrip data={metrics.data} compact /> : null}

        {impact.data ? (
          <Banner tone={impact.data.changed_organizations.length ? "info" : "neutral"} title={bi("Effect of the recorded decisions", "已记录判定的影响")}>
            {impact.data.statement}
            <div className="small" style={{ marginTop: 4 }}>
              {impact.data.changed_organizations.length === 0
                ? bi("No organization count has changed yet.", "尚无企业计数变化。")
                : impact.data.changed_organizations
                    .map((row) => row.organization_key + ": " + row.records_before + " -> " + row.records_after + " (" + (row.records_delta > 0 ? "+" : "") + row.records_delta + ")")
                    .join("; ")}
              {" - "}
              {bi(impact.data.unchanged_organizations + " organizations unchanged.", impact.data.unchanged_organizations + " 家企业计数未变。")}
            </div>
          </Banner>
        ) : null}

        <Card
          title={bi("Review queue", "复核队列")}
          note={bi("Ordered by the number of records that depend on each mapping. Verified mappings are hidden unless you ask for them.", "按依赖该映射的记录数排序。已验证的映射默认隐藏。")}
        >
          <div className="row wrap" style={{ gap: 10, alignItems: "flex-end" }}>
            <label className="field">
              <span className="field-label">{bi("Status", "状态")}</span>
              <select className="select" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
                <option value="">{bi("all", "全部")}</option>
                {STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">{bi("Risk flag", "风险类型")}</span>
              <select className="select" value={risk} onChange={(event) => { setRisk(event.target.value); setPage(1); }}>
                <option value="">{bi("all", "全部")}</option>
                {RISK_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">{bi("Organization", "企业")}</span>
              <input className="input" value={org} placeholder="medtronic" onChange={(event) => { setOrg(event.target.value); setPage(1); }} />
            </label>
            <label className="field" style={{ minWidth: 220, flex: 1 }}>
              <span className="field-label">{bi("Applicant string", "申请人名称")}</span>
              <input className="input" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
            </label>
            <label className="field">
              <span className="field-label">{bi("Sort", "排序")}</span>
              <select className="select" value={sort} onChange={(event) => setSort(event.target.value)}>
                <option value="records_desc">{bi("records (high to low)", "记录数（从高到低）")}</option>
                <option value="records_asc">{bi("records (low to high)", "记录数（从低到高）")}</option>
                <option value="risk_desc">{bi("risk flags", "风险标记数")}</option>
                <option value="name_asc">{bi("applicant name", "申请人名称")}</option>
              </select>
            </label>
          </div>

          {queue.error ? <ErrorState message={queue.error.message} onRetry={refresh} /> : null}
          {!queue.data && queue.status === "loading" ? <LoadingBlock lines={5} /> : null}

          {queue.data ? (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col" className="num">{bi("Records", "记录数")}</th>
                    <th scope="col">{bi("Applicant string (verbatim)", "申请人名称（原文）")}</th>
                    <th scope="col">{bi("Current mapping", "当前映射")}</th>
                    <th scope="col">{bi("Status", "状态")}</th>
                    <th scope="col">{bi("Risk flags", "风险标记")}</th>
                    <th scope="col">{bi("Scope", "检索范围")}</th>
                    <th scope="col" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row: ReviewQueueItem) => (
                    <tr key={row.applicant_name} className={selected === row.applicant_name ? "selected" : undefined}>
                      <td className="num mono">{formatNumber(row.record_count)}</td>
                      <td className="mono small">{row.applicant_name}</td>
                      <td className="small">{row.organization_key ?? <span className="muted">{bi("not attributed", "未归属")}</span>}</td>
                      <td><VerificationBadge status={row.status === "unmatched" ? "unattributed" : row.status} compact /></td>
                      <td className="small">{row.risk_flags.map((flag) => <span key={flag.code} className="chip tiny" title={flag.meaning}>{flag.code}</span>)}</td>
                      <td className="small muted">{(row.collection_scope || []).join(", ") || "-"}</td>
                      <td>
                        <button type="button" className="btn sm" onClick={() => setSelected(row.applicant_name)}>
                          {bi("Review", "复核")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length === 0 ? <EmptyState title={bi("No applicant strings match these filters", "没有符合筛选条件的申请人名称")} /> : null}
              <Pagination page={queue.data.page} totalPages={queue.data.total_pages} total={queue.data.total} onPage={setPage} />
            </>
          ) : null}
        </Card>

        {selected ? (
          <CasePanel
            key={selected}
            data={caseState.data ?? null}
            loading={caseState.status === "loading" && !caseState.data}
            error={caseState.error?.message ?? null}
            busy={busy}
            onClose={() => setSelected(null)}
            onSubmit={async (body) => {
              setBusy(true);
              try {
                await reviewDecide({ applicant_name: selected, ...body });
                setMessage(bi("Decision recorded for ", "已记录判定：") + selected);
                refresh();
              } catch (caught) {
                setMessage(caught instanceof Error ? caught.message : String(caught));
              } finally {
                setBusy(false);
              }
            }}
            onRevoke={async (uid, reviewer, note) => {
              setBusy(true);
              try {
                await reviewRevoke(uid, { reviewer, note });
                setMessage(bi("Decision withdrawn (append-only): ", "已撤回判定（只可追加）：") + uid.slice(0, 8));
                refresh();
              } catch (caught) {
                setMessage(caught instanceof Error ? caught.message : String(caught));
              } finally {
                setBusy(false);
              }
            }}
          />
        ) : null}

        {orgsWithVerified ? (
          <Callout>
            {bi(
              "Organization-level view: " +
                orgsWithVerified.organizations_with_zero_verified_records +
                " of " +
                orgsWithVerified.organizations_with_records +
                " organizations with records have no evidence-verified record at all; median curated share is " +
                (orgsWithVerified.median_curated_share === null ? "UNKNOWN" : Math.round(orgsWithVerified.median_curated_share * 1000) / 10 + "%") +
                ".",
              "企业层面：" +
                orgsWithVerified.organizations_with_records +
                " 家有记录的企业中，有 " +
                orgsWithVerified.organizations_with_zero_verified_records +
                " 家完全没有经证据核验的记录；已核验比例中位数为 " +
                (orgsWithVerified.median_curated_share === null ? "未知" : Math.round(orgsWithVerified.median_curated_share * 1000) / 10 + "%") +
                "。",
            )}
          </Callout>
        ) : null}
      </div>
    </>
  );
}

function CasePanel({
  data,
  loading,
  error,
  busy,
  onClose,
  onSubmit,
  onRevoke,
}: {
  data: ReviewCase | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  onClose: () => void;
  onSubmit: (body: {
    action: string;
    status: string;
    organization_key?: string | null;
    basis?: string | null;
    evidence_type?: string | null;
    evidence?: ReviewEvidence[];
    note?: string | null;
    reviewer: string;
  }) => Promise<void>;
  onRevoke: (uid: string, reviewer: string, note: string) => Promise<void>;
}) {
  const { bi, t } = useI18n();
  const capabilities = useAsync(() => reviewCapabilities(), []);
  const [action, setAction] = useState("approve");
  const [decisionStatus, setDecisionStatus] = useState("evidence_verified");
  const [organizationKey, setOrganizationKey] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [evidenceType, setEvidenceType] = useState("regulator_record");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [evidenceTitle, setEvidenceTitle] = useState("");
  const [evidenceQuote, setEvidenceQuote] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!data) return;
    setOrganizationKey(data.current.organization_key ?? data.candidate_organizations[0]?.organization_key ?? "");
    const first = data.sample_records[0];
    setEvidenceUrl(first?.official_url ?? "");
    setEvidenceTitle(first ? first.official_id + " - openFDA record naming the applicant" : "");
    setEvidenceQuote(first ? "applicant: " + data.applicant_name : "");
  }, [data]);

  const evidence = useMemo<ReviewEvidence[]>(() => {
    if (!evidenceUrl.trim()) return [];
    return [
      {
        evidence_type: evidenceType,
        url: evidenceUrl.trim(),
        title: evidenceTitle.trim() || null,
        quote: evidenceQuote.trim() || null,
        accessed_at: new Date().toISOString().slice(0, 10),
        source_id: evidenceType === "regulator_record" ? "openfda_device" : null,
        note: note.trim() || null,
      },
    ];
  }, [evidenceType, evidenceUrl, evidenceTitle, evidenceQuote, note]);

  if (loading) return <LoadingBlock lines={6} />;
  if (error) return <ErrorState message={error} />;
  if (!data) return null;

  const submit = () =>
    void onSubmit({
      action,
      status: action === "reject" ? "rejected" : action === "unresolved" ? "unresolved" : decisionStatus,
      organization_key: action === "reject" || action === "unresolved" ? null : organizationKey,
      basis: action === "reject" ? null : "name_identity_v1",
      evidence_type: evidenceType,
      evidence,
      note: note.trim() || null,
      reviewer: reviewer.trim(),
    });

  return (
    <Card
      title={bi("Review case", "复核案件")}
      note={bi("Verbatim applicant string and the evidence that depends on it. A decision never edits history: it appends.", "申请人名称原文，以及依赖它的证据。判定不修改历史，只追加记录。")}
      actions={<button type="button" className="btn sm" onClick={onClose}>{t("common.close")}</button>}
    >
      <div className="stack">
        <KeyValue
          rows={[
            { label: t("common.applicant"), value: <span className="mono">{data.applicant_name}</span> },
            { label: bi("Records", "记录数"), value: <strong>{formatNumber(data.record_count)}</strong> },
            { label: bi("Collection scope", "检索范围"), value: data.collection_scope.join(", ") || "-" },
            {
              label: bi("Current mapping", "当前映射"),
              value: (
                <span className="row" style={{ gap: 8 }}>
                  <span>{data.current.organization_display ?? bi("not attributed", "未归属")}</span>
                  <VerificationBadge status={data.current.status} />
                  {data.current.rule ? <Badge tone="outline">{data.current.rule}</Badge> : null}
                </span>
              ),
            },
            { label: bi("Why it was proposed", "提议依据"), value: <span className="small">{data.current.rule_detail ?? "-"}</span> },
            {
              label: bi("By source", "按来源"),
              value: Object.entries(data.by_source ?? {}).map(([key, value]) => key + " " + value).join(", ") || "-",
            },
          ]}
        />

        <SectionHead title={bi("Risk flags (hypotheses, not conclusions)", "风险标记（仅为假设，非结论）")} />
        <ul className="small">
          {data.risk_flags.length === 0 ? <li className="muted">{bi("No flag raised.", "未触发标记。")}</li> : null}
          {data.risk_flags.map((flag) => (
            <li key={flag.code}>
              <strong>{flag.code}</strong>: {flag.meaning}
            </li>
          ))}
        </ul>

        {data.candidate_organizations.length ? (
          <>
            <SectionHead title={bi("Candidate organizations", "候选企业")} />
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">{bi("Organization", "企业")}</th>
                  <th scope="col">{bi("Matched token", "匹配词")}</th>
                  <th scope="col" className="num">{bi("Records", "记录数")}</th>
                  <th scope="col">{bi("In scope", "在检索范围")}</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {data.candidate_organizations.map((candidate) => (
                  <tr key={candidate.organization_key}>
                    <td>{candidate.display_name}</td>
                    <td className="small mono">{candidate.matched_tokens.join(", ")}</td>
                    <td className="num mono">{formatNumber(candidate.records)}</td>
                    <td>{candidate.in_collection_scope ? bi("yes", "是") : bi("no", "否")}</td>
                    <td>
                      <button type="button" className="btn sm" onClick={() => { setAction("reassign"); setOrganizationKey(candidate.organization_key); }}>
                        {bi("Use this organization", "指定该企业")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}

        <SectionHead title={bi("Original FDA records that depend on this mapping", "依赖该映射的原始 FDA 记录")} />
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">{t("common.officialId")}</th>
              <th scope="col">{t("common.type")}</th>
              <th scope="col">{t("common.eventDate")}</th>
              <th scope="col">{bi("Device", "器械")}</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {data.sample_records.map((record) => (
              <tr key={record.event_id}>
                <td className="mono small">{record.official_id}</td>
                <td className="small">{record.event_type}</td>
                <td className="mono small">{record.event_date ?? "-"}</td>
                <td className="small">{(record.device_name ?? "-").slice(0, 70)}</td>
                <td>
                  <a className="link small" href={record.official_url} target="_blank" rel="noreferrer">
                    {t("common.openRecord")}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {data.ownership_relations.length ? (
          <>
            <SectionHead title={bi("Ownership relations mentioning this spelling", "涉及该写法的所有权关系")} />
            <ul className="small">
              {data.ownership_relations.map((relation) => (
                <li key={relation.relation_id}>
                  <strong>{relation.relation_id}</strong> {relation.entity} ({relation.relation_type}, {relation.status}
                  {relation.effective_from ? ", from " + relation.effective_from : ""})
                  {relation.historical_owner_before ? " - before: " + relation.historical_owner_before : ""}
                </li>
              ))}
            </ul>
          </>
        ) : null}

        <SectionHead title={bi("Record a decision", "记录判定")} note={bi("Evidence is required for evidence-verified.", "证据核验必须提供证据。")} />
        <Banner tone="info" title={bi("Human review is not available in this release", "本版本不提供人工复核状态")}>
          {bi(
            "The service records the server-derived actor kind (agent) and refuses human_reviewed, because it cannot verify that the operator is a human. A decision is evidence-verified with recorded evidence, or unresolved. The actor kind is not something a client may declare.",
            "本服务只记录服务端判定的操作者类别（agent），并拒绝 human_reviewed，因为无法验证操作者是否为人类。判定要么附证据成为“证据核验”，要么标记为“无法判断”。操作者类别不能由客户端声明。",
          )}
          {capabilities.data ? <div className="small muted" style={{ marginTop: 4 }}>{capabilities.data.human_review_reason}</div> : null}
        </Banner>
        <div className="row wrap" style={{ gap: 10, alignItems: "flex-end" }}>
          <label className="field">
            <span className="field-label">{bi("Action", "操作")}</span>
            <select className="select" value={action} onChange={(event) => setAction(event.target.value)}>
              <option value="approve">{bi("approve mapping", "批准映射")}</option>
              <option value="reassign">{bi("reassign to another organization", "改派到其他企业")}</option>
              <option value="reject">{bi("reject mapping", "驳回映射")}</option>
              <option value="unresolved">{bi("mark unresolved", "标记无法判断")}</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">{bi("Resulting status", "结果状态")}</span>
            <select className="select" value={decisionStatus} onChange={(event) => setDecisionStatus(event.target.value)} disabled={action === "reject" || action === "unresolved"}>
              <option value="rule_verified">rule_verified</option>
              <option value="evidence_verified">evidence_verified</option>
            </select>
          </label>
          <label className="field" style={{ minWidth: 220 }}>
            <span className="field-label">{bi("Organization", "企业")}</span>
            <input className="input mono" value={organizationKey} onChange={(event) => setOrganizationKey(event.target.value)} disabled={action === "reject" || action === "unresolved"} />
          </label>
          <label className="field">
            <span className="field-label">{bi("Reviewer", "复核者")}</span>
            <input className="input" value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="name" />
          </label>
        </div>

        <div className="row wrap" style={{ gap: 10, alignItems: "flex-end" }}>
          <label className="field">
            <span className="field-label">{bi("Evidence type", "证据类型")}</span>
            <select className="select" value={evidenceType} onChange={(event) => setEvidenceType(event.target.value)}>
              {EVIDENCE_TYPES.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label className="field" style={{ minWidth: 320, flex: 1 }}>
            <span className="field-label">{bi("Evidence URL", "证据链接")}</span>
            <input className="input mono" value={evidenceUrl} onChange={(event) => setEvidenceUrl(event.target.value)} />
          </label>
          <label className="field" style={{ minWidth: 220, flex: 1 }}>
            <span className="field-label">{bi("Evidence title", "证据标题")}</span>
            <input className="input" value={evidenceTitle} onChange={(event) => setEvidenceTitle(event.target.value)} />
          </label>
        </div>
        <label className="field">
          <span className="field-label">{bi("Evidence quote / reason", "证据引用/理由")}</span>
          <textarea className="input" rows={2} value={evidenceQuote} onChange={(event) => setEvidenceQuote(event.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">{bi("Decision note (kept in the ledger)", "判定说明（写入决策台账）")}</span>
          <textarea className="input" rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <div className="row">
          <button
            type="button"
            className="btn primary"
            disabled={busy || !reviewer.trim() || ((action === "approve" || action === "reassign") && !organizationKey.trim())}
            onClick={submit}
          >
            {busy ? bi("Saving...", "保存中...") : bi("Append decision", "追加判定")}
          </button>
          <span className="muted small">{bi("This does not overwrite history; the previous state stays in the ledger.", "此操作不会覆盖历史；上一状态仍保留在台账中。")}</span>
        </div>

        <SectionHead title={bi("Decision history", "判定历史")} note={bi("Newest last. Withdrawn decisions stay visible.", "最新的在最后。已撤回的判定仍然可见。")} />
        {data.history.length === 0 ? (
          <div className="muted small">{bi("No decision recorded for this string yet.", "该名称尚无判定记录。")}</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">{bi("When", "时间")}</th>
                <th scope="col">{bi("Action", "操作")}</th>
                <th scope="col">{bi("Status", "状态")}</th>
                <th scope="col">{bi("Organization", "企业")}</th>
                <th scope="col">{bi("Reviewer", "复核者")}</th>
                <th scope="col">{bi("Note", "说明")}</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {data.history.map((entry) => (
                <tr key={entry.decision_uid} className={entry.revoked ? "muted" : undefined}>
                  <td className="mono tiny">{entry.created_at}</td>
                  <td className="small">{entry.action}</td>
                  <td className="small">{entry.status}</td>
                  <td className="small">{entry.organization_key ?? "-"}</td>
                  <td className="small">
                    {entry.reviewer} ({entry.authority_kind ?? entry.reviewer_kind}
                    {entry.status_downgraded ? " - claim downgraded" : ""})
                  </td>
                  <td className="small">{(entry.note ?? "").slice(0, 80)}</td>
                  <td>
                    {entry.action !== "revoke" && !entry.revoked ? (
                      <button
                        type="button"
                        className="btn sm"
                        disabled={busy}
                        onClick={() => void onRevoke(entry.decision_uid, reviewer.trim() || entry.reviewer, note.trim() || "withdrawn")}
                      >
                        {bi("Withdraw", "撤回")}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}
