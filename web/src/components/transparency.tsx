import { Link } from "react-router-dom";
import { getMetrics } from "../api/client";
import { useAsync } from "../api/hooks";
import type {
  CompareResponse,
  MetricDefinition,
  MetricsResponse,
  OrganizationVerification,
  OrganizationOwnership,
  VerificationStatus,
} from "../api/types";
import { useI18n } from "../i18n";
import { Badge, Banner, Card, Grid, LoadingBlock, MetricTile, SectionHead, formatNumber, formatPercent } from "./ui";

/* ------------------------------------------------------------------ status vocabulary */

const STATUS_TONE: Record<string, "ok" | "info" | "warn" | "danger" | "neutral" | "outline"> = {
  human_reviewed: "ok",
  evidence_verified: "ok",
  rule_verified: "info",
  proposed: "warn",
  unresolved: "warn",
  rejected: "danger",
  unattributed: "neutral",
};

export function VerificationBadge({
  status,
  labelEn,
  labelZh,
  compact = false,
  title,
}: {
  status?: VerificationStatus | string | null;
  labelEn?: string;
  labelZh?: string;
  compact?: boolean;
  title?: string;
}) {
  const { lang } = useI18n();
  if (!status) return <span className="muted small">-</span>;
  const label = (lang === "zh" ? labelZh : labelEn) ?? status.replace(/_/g, " ");
  const tone = STATUS_TONE[status] ?? "neutral";
  const explanation =
    title ??
    {
      proposed: "Provisional: no rule and no independent evidence. Counts that depend on this mapping are working assumptions.",
      rule_verified: "A deterministic, reproducible name rule justifies this mapping. A rule is not a reviewer.",
      evidence_verified: "An independent documentary source is recorded for this mapping (not necessarily by a human).",
      human_reviewed: "A named human reviewer made this decision.",
      rejected: "Reviewed and rejected: the string belongs to a different entity.",
      unresolved: "Reviewed but not determinable from the recorded evidence.",
      unattributed: "No attribution exists for this string.",
    }[status as string] ?? "";
  return (
    <span title={explanation}>
      <Badge tone={tone}>{compact ? label.split(" ")[0] : label}</Badge>
    </span>
  );
}

export function StatusLegend() {
  const { lang, bi } = useI18n();
  const state = useAsync(() => getMetrics(), []);
  if (!state.data) return state.error ? <div className="muted small">{state.error.message}</div> : <LoadingBlock lines={3} />;
  const rows = state.data.status_vocabulary ?? [];
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">{bi("Status", "状态")}</th>
          <th scope="col">{bi("What it claims", "含义")}</th>
          <th scope="col" className="num">
            {bi("Records", "记录数")}
          </th>
          <th scope="col">{bi("Counts as curated?", "是否计入已核验")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.status}>
            <td>
              <VerificationBadge status={row.status} labelEn={row.label_en} labelZh={row.label_zh} />
            </td>
            <td className="small">
              {row.meaning_en}
              {lang === "zh" ? "" : ""}
            </td>
            <td className="num mono">{formatNumber(row.count)}</td>
            <td className="small">
              {row.curated ? (
                <Badge tone="ok">{bi("yes", "是")}</Badge>
              ) : row.rule_verified ? (
                <Badge tone="info">{bi("no - rule only", "否（仅规则）")}</Badge>
              ) : (
                <span className="muted">{bi("no", "否")}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ------------------------------------------------------------------ metrics strip */

function definitionOf(definitions: MetricDefinition[] | undefined, id: string, lang: string): { name: string; text: string; isNot: string } {
  const found = (definitions ?? []).find((item) => item.id === id);
  if (!found) return { name: id, text: "", isNot: "" };
  return {
    name: lang === "zh" ? found.name_zh : found.name_en,
    text: lang === "zh" ? found.definition_zh : found.definition_en,
    isNot: found.is_not,
  };
}

export function MetricsStrip({ data, compact = false }: { data?: MetricsResponse; compact?: boolean }) {
  const { lang, bi } = useI18n();
  const fetched = useAsync(() => (data ? Promise.resolve(data) : getMetrics()), [data]);
  const metrics = data ?? fetched.data;
  if (!metrics) return fetched.error ? <div className="muted small">{fetched.error.message}</div> : <LoadingBlock lines={2} />;

  const record = metrics.levels.record;
  const organization = metrics.levels.organization;
  const precision = metrics.estimated_attribution_precision;
  const retrieval = metrics.retrieval_coverage;
  const attributed = definitionOf(metrics.definitions, "attributed_share", lang);
  const rule = definitionOf(metrics.definitions, "rule_verified_share", lang);
  const curated = definitionOf(metrics.definitions, "curated_share", lang);
  const precisionDef = definitionOf(metrics.definitions, "estimated_attribution_precision", lang);
  const retrievalDef = definitionOf(metrics.definitions, "retrieval_coverage", lang);

  const unknown = <span className="metric-unknown">{bi("UNKNOWN", "未知")}</span>;

  return (
    <>
      <Grid cols={compact ? 3 : 5}>
        <MetricTile
          label={attributed.name}
          value={formatPercent(record.attributed_share)}
          sub={bi(
            formatNumber(record.attributed_records) + " of " + formatNumber(record.collected_records) + " collected records",
            "已采集 " + formatNumber(record.collected_records) + " 条中的 " + formatNumber(record.attributed_records) + " 条",
          )}
          title={attributed.text + " " + attributed.isNot}
        />
        <MetricTile
          label={rule.name}
          value={formatPercent(record.rule_verified_share)}
          sub={bi(
            formatNumber(record.rule_verified_records) + " records rest on a deterministic rule",
            formatNumber(record.rule_verified_records) + " 条依赖确定性规则",
          )}
          title={rule.text + " " + rule.isNot}
        />
        <MetricTile
          label={curated.name}
          value={formatPercent(record.curated_share)}
          accent
          sub={bi(
            formatNumber(record.verified_records) + " records have an independent source or a human decision",
            formatNumber(record.verified_records) + " 条有独立来源或人工决策",
          )}
          title={curated.text + " " + curated.isNot}
        />
        <MetricTile
          label={precisionDef.name}
          value={precision.state === "unknown" ? unknown : formatPercent(precision.estimate)}
          sub={
            precision.state === "unknown"
              ? bi("no completed independent sample", "尚无已完成的独立抽样复核")
              : bi(
                  (precision.decidable_sample_size ?? 0) +
                    " of " +
                    precision.sample_size +
                    " sampled cases decide it; reviewer: " +
                    (precision.reviewer_kind ?? "unknown") +
                    (precision.human_review_completed === false ? " (not human review)" : ""),
                  "基于 " +
                    precision.sample_size +
                    " 个样本中的 " +
                    (precision.decidable_sample_size ?? 0) +
                    " 个可判定案例；复核者：" +
                    (precision.reviewer_kind === "human" ? "人工" : "AI 代理") +
                    (precision.human_review_completed === false ? "（非人工复核）" : ""),
                )
          }
          title={
            precisionDef.text +
            (precision.confidence_interval_95
              ? " 95% CI " + formatPercent(precision.confidence_interval_95[0]) + " - " + formatPercent(precision.confidence_interval_95[1]) + "."
              : "")
          }
        />
        <MetricTile
          label={retrievalDef.name}
          value={retrieval.state === "unknown" ? unknown : "-"}
          sub={bi("no independent denominator", "无独立真值分母")}
          title={retrievalDef.text + " " + retrievalDef.isNot}
        />
      </Grid>
      {record.provisional_share !== null && record.provisional_share > 0.3 ? (
        <Banner tone="warning" title={bi("Most attributed records are still provisional", "多数已归属记录仍为暂定")}>
          {bi(
            formatPercent(record.provisional_share) +
              " of attributed records rest on mappings with neither a rule nor independent evidence. Organization counts that depend on them are working assumptions; the curated share above is the only share that has been verified.",
            formatPercent(record.provisional_share) +
              " 的已归属记录既无规则也无可独立核验的证据。依赖这些映射的企业计数只是工作假设；上方“已核验比例”才是真正核验过的部分。",
          )}
        </Banner>
      ) : null}
      {compact ? null : (
        <div className="muted small">
          {bi(
            "Median organization curated share: " +
              (organization.median_curated_share === null ? "UNKNOWN" : formatPercent(organization.median_curated_share)) +
              " across " +
              organization.organizations_with_records +
              " organizations with records; " +
              organization.organizations_with_zero_verified_records +
              " organizations have no evidence-verified record.",
            "企业层面已核验比例中位数：" +
              (organization.median_curated_share === null ? "未知" : formatPercent(organization.median_curated_share)) +
              "（覆盖 " +
              organization.organizations_with_records +
              " 家有记录的企业）；其中 " +
              organization.organizations_with_zero_verified_records +
              " 家没有任何经证据核验的记录。",
          )}
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ precision / definitions */

export function MetricDefinitions({ data }: { data?: MetricsResponse }) {
  const { lang, bi } = useI18n();
  const fetched = useAsync(() => (data ? Promise.resolve(data) : getMetrics()), [data]);
  const metrics = data ?? fetched.data;
  if (!metrics) return fetched.error ? <div className="muted small">{fetched.error.message}</div> : <LoadingBlock lines={4} />;
  const precision = metrics.estimated_attribution_precision;
  const retrieval = metrics.retrieval_coverage;
  return (
    <>
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">{bi("Metric", "指标")}</th>
            <th scope="col">{bi("Definition", "定义")}</th>
            <th scope="col">{bi("What it is not", "它不是什么")}</th>
          </tr>
        </thead>
        <tbody>
          {metrics.definitions.map((definition) => (
            <tr key={definition.id}>
              <td>
                <strong>{lang === "zh" ? definition.name_zh : definition.name_en}</strong>
                <div className="muted tiny">{definition.unit}</div>
              </td>
              <td className="small">{lang === "zh" ? definition.definition_zh : definition.definition_en}</td>
              <td className="small muted">{definition.is_not}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <SectionHead
        title={bi("Estimated attribution precision", "归属准确率估计")}
        note={bi("A correctness estimate needs an independent sample. It is never derived from the attributed share.", "正确率必须来自独立抽样；绝不能用已归属比例推算。")}
      />
      {precision.state === "unknown" ? (
        <Banner tone="info" title={bi("UNKNOWN in this release", "本版本为未知")}>
          {bi(
            precision.reason ??
              "No completed independent sample review is recorded, so the product does not report a precision number.",
            "尚无已完成的独立抽样复核，因此本产品不报告准确率数字。",
          )}
          <div className="small" style={{ marginTop: 6 }}>
            {bi("Protocol: ", "复核方案：")}
            <Link to="/sources">{bi("identity review protocol and validation plan", "身份复核方案与验证计划")}</Link>
          </div>
        </Banner>
      ) : (
        <div className="small">
          {bi("Estimate", "估计值")}: {formatPercent(precision.estimate)}
          {precision.confidence_interval_95
            ? " (" + bi("95% CI", "95% 置信区间") + " " + formatPercent(precision.confidence_interval_95[0]) + " - " + formatPercent(precision.confidence_interval_95[1]) + ")"
            : ""}
          {" - "}
          {bi("reviewer class", "复核者类别")}: {precision.reviewer_kind}
        </div>
      )}

      <SectionHead
        title={bi("Retrieval coverage", "检索覆盖率")}
        note={bi("How much of the relevant FDA population the queries actually retrieved.", "查询实际找回的相关 FDA 记录比例。")}
      />
      <Banner tone="info" title={bi("UNKNOWN: no independent denominator", "未知：没有独立真值分母")}>
        {retrieval.reason}
        <ul className="small" style={{ marginTop: 6 }}>
          {retrieval.what_would_be_needed.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Banner>
    </>
  );
}

/* ------------------------------------------------------------------ organization transparency */

export function OrgTransparency({ verification, ownership }: { verification?: OrganizationVerification; ownership?: OrganizationOwnership }) {
  const { bi } = useI18n();
  if (!verification) return null;
  const statuses = Object.entries(verification.by_status ?? {}).sort((a, b) => b[1] - a[1]);
  return (
    <div className="stack">
      <Card
        title={bi("Attribution confidence for these counts", "这些计数的归属可信程度")}
        note={bi(
          "Every count on this page is a count of records whose applicant string was mapped to this organization. This block states how strong that mapping is.",
          "本页每个计数都是“申请人名称被映射到该企业”的记录数。本区块说明该映射的可信程度。",
        )}
      >
        <Grid cols={4}>
          <MetricTile label={bi("Attributed records", "已归属记录")} value={formatNumber(verification.attributed_records)} />
          <MetricTile
            label={bi("Curated share", "已核验比例")}
            value={verification.curated_share === null ? bi("UNKNOWN", "未知") : formatPercent(verification.curated_share)}
            accent
            sub={bi(formatNumber(verification.verified_records) + " records evidence-verified or human-reviewed", formatNumber(verification.verified_records) + " 条经证据核验或人工复核")}
          />
          <MetricTile
            label={bi("Rule-verified", "规则校验")}
            value={formatPercent(verification.rule_verified_share)}
            sub={bi(formatNumber(verification.rule_verified_records) + " records; a rule is not review", formatNumber(verification.rule_verified_records) + " 条；规则校验不等于复核")}
          />
          <MetricTile
            label={bi("Provisional", "暂定归属")}
            value={formatPercent(verification.provisional_share)}
            sub={bi(formatNumber(verification.provisional_records) + " records with no rule and no evidence", formatNumber(verification.provisional_records) + " 条既无规则也无可核验证据")}
          />
        </Grid>
        {verification.provisional_records > 0 ? (
          <Banner tone="warning" title={bi("Provisional attribution affects these numbers", "暂定归属会影响这些数字")}>
            {bi(
              verification.risk_note +
                " A provisional mapping is a working assumption, not a verified fact; treat comparisons that depend on it accordingly.",
              verification.risk_note + " 暂定映射只是工作假设，而非已核验事实；据此进行的比较应相应谨慎。",
            )}
          </Banner>
        ) : null}
        <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
          {statuses.map(([status, count]) => (
            <span key={status} className="row" style={{ gap: 6 }}>
              <VerificationBadge status={status} compact />
              <span className="mono small">{formatNumber(count)}</span>
            </span>
          ))}
        </div>
        <div className="muted small" style={{ marginTop: 8 }}>
          {bi(
            "Spellings: " +
              verification.accepted_spellings +
              " accepted, " +
              verification.verified_spellings +
              " evidence-verified, " +
              verification.rule_verified_spellings +
              " rule-verified, " +
              verification.provisional_spellings +
              " provisional, " +
              verification.human_reviewed_spellings +
              " human-reviewed.",
            "写法：" +
              verification.accepted_spellings +
              " 个已接受，" +
              verification.verified_spellings +
              " 个经证据核验，" +
              verification.rule_verified_spellings +
              " 个规则校验，" +
              verification.provisional_spellings +
              " 个暂定，" +
              verification.human_reviewed_spellings +
              " 个人工复核。",
          )}
        </div>
      </Card>

      {ownership ? (
        <Card
          title={bi("Ownership and historical limits", "所有权与历史口径")}
          note={bi("Three different questions: who filed the record, who owned the entity when it happened, and which group it belongs to today.", "三个不同问题：谁提交了记录、事件发生时谁拥有该实体、它今天属于哪个集团。")}
        >
          <Banner tone="info" title={bi("Counting basis on this page: current group", "本页统计口径：当前集团")}>
            {ownership.current_group_policy}
          </Banner>
          <Grid cols={4}>
            <MetricTile label={bi("Verified relations", "已核验关系")} value={ownership.verified_relation_count} />
            <MetricTile label={bi("Unresolved relations", "未解决关系")} value={ownership.unresolved_relation_count} />
            <MetricTile
              label={bi("Owner at event time: this group", "事件发生时所有者：本集团")}
              value={formatNumber(ownership.record_level?.verified_current_group ?? 0)}
              sub={bi("of " + formatNumber(ownership.record_level?.records_total ?? 0) + " attributed records", "占 " + formatNumber(ownership.record_level?.records_total ?? 0) + " 条已归属记录")}
            />
            <MetricTile
              label={bi("Owner at event time: UNKNOWN", "事件发生时所有者：未知")}
              value={formatNumber(ownership.record_level?.unknown ?? 0)}
              sub={bi("no verified relation, no effective date, or no event date", "无已核验关系、无生效日期或无事件日期")}
            />
          </Grid>
          {ownership.record_level ? (
            <Banner tone="info" title={bi("Counts on this page use the current group", "本页计数采用当前集团口径")}>
              {ownership.record_level.note}
              <div className="small" style={{ marginTop: 4 }}>
                {bi(
                  "In this organization's records: " +
                    ownership.record_level.verified_current_group +
                    " were controlled by this group on the event date, " +
                    ownership.record_level.verified_predecessor +
                    " were controlled by a predecessor, and " +
                    ownership.record_level.unknown +
                    " have an UNKNOWN owner at event time. UNKNOWN is never counted as zero.",
                  "该企业记录中：" +
                    ownership.record_level.verified_current_group +
                    " 条在事件当日由本集团控制，" +
                    ownership.record_level.verified_predecessor +
                    " 条由前身实体控制，" +
                    ownership.record_level.unknown +
                    " 条在事件当日的所有者未知。未知从不按零处理。",
                )}
              </div>
            </Banner>
          ) : null}
          {ownership.historical_split.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">{bi("Entity", "实体")}</th>
                  <th scope="col">{bi("Relation", "关系")}</th>
                  <th scope="col">{bi("Effective from", "生效日期")}</th>
                  <th scope="col" className="num">
                    {bi("Records before", "此前记录")}
                  </th>
                  <th scope="col" className="num">
                    {bi("Records after", "此后记录")}
                  </th>
                  <th scope="col">{bi("Owner before", "此前所属")}</th>
                </tr>
              </thead>
              <tbody>
                {ownership.historical_split.map((row) => (
                  <tr key={row.relation_id}>
                    <td className="small">{row.entity}</td>
                    <td className="small">{row.relation_type}</td>
                    <td className="mono small">{row.effective_from}</td>
                    <td className="num mono">{formatNumber(row.records_before_effective_date)}</td>
                    <td className="num mono">{formatNumber(row.records_on_or_after_effective_date)}</td>
                    <td className="small">{row.historical_owner_before ?? bi("UNKNOWN", "未知")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="muted small">
              {bi("No verified relation with an effective date is recorded for this organization.", "该企业没有记录到带生效日期的已核验关系。")}
            </div>
          )}
          <div className="muted small" style={{ marginTop: 8 }}>{ownership.uncertainty}</div>
          <div className="row" style={{ marginTop: 8 }}>
            <Link to="/sources" className="link">
              {bi("Ownership sources and evidence", "所有权来源与证据")}
            </Link>
          </div>
        </Card>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ compare transparency */

export function CompareTransparency({ compare }: { compare: CompareResponse }) {
  const { bi } = useI18n();
  const sides = compare.organizations;
  if (!sides.length) return null;
  const comparability = compare.comparability;
  return (
    <Card
      title={bi("Is this comparison fair?", "这个对比是否成立？")}
      note={bi("Same window, same event types and the same counting unit are necessary but not sufficient: the mappings behind each side must also be equally verified.", "同一时间窗口、同一事件类型与同一计数单位是必要条件，但还不充分：两侧计数所依赖的归属映射也必须同样经过核验。")}
    >
      {comparability ? (
        <Banner tone={comparability.coverage_symmetric ? "info" : "warning"} title={bi("Comparability verdict", "可比性结论")}>
          {comparability.verdict}
          <div className="small" style={{ marginTop: 4 }}>
            {bi(
              "Window shared: " +
                (comparability.window_shared ? "yes" : "no") +
                "; event types shared: " +
                (comparability.event_types_shared ? "yes" : "no") +
                "; ownership basis: " +
                comparability.ownership_basis +
                "; review filter: " +
                comparability.review_filter +
                "; source coverage symmetric: " +
                (comparability.coverage_symmetric ? "yes" : "no") +
                ".",
              "共用窗口：" +
                (comparability.window_shared ? "是" : "否") +
                "；共用事件类型：" +
                (comparability.event_types_shared ? "是" : "否") +
                "；所有权口径：" +
                comparability.ownership_basis +
                "；复核筛选：" +
                comparability.review_filter +
                "；来源覆盖对称：" +
                (comparability.coverage_symmetric ? "是" : "否") +
                "。",
            )}
          </div>
        </Banner>
      ) : null}

      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">{bi("Organization", "企业")}</th>
            <th scope="col" className="num">
              {bi("Records", "记录数")}
            </th>
            <th scope="col" className="num">
              {bi("Evidence/human verified", "证据/人工核验")}
            </th>
            <th scope="col" className="num">
              {bi("Curated share", "已核验比例")}
            </th>
            <th scope="col" className="num">
              {bi("Rule-verified", "规则校验")}
            </th>
            <th scope="col" className="num">
              {bi("Provisional", "暂定")}
            </th>
            <th scope="col" className="num">
              {bi("Owner = this group", "所有者=本集团")}
            </th>
            <th scope="col" className="num">
              {bi("Owner = predecessor", "所有者=前身")}
            </th>
            <th scope="col" className="num">
              {bi("Owner UNKNOWN", "所有者未知")}
            </th>
          </tr>
        </thead>
        <tbody>
          {sides.map((side) => (
            <tr key={side.key}>
              <td>{side.display_name}</td>
              <td className="num mono">{formatNumber(side.counts.records)}</td>
              <td className="num mono">{formatNumber(side.verification?.verified_records ?? side.counts.verified_records)}</td>
              <td className="num mono">
                {(side.verification?.curated_share ?? side.counts.curated_share) === null ||
                (side.verification?.curated_share ?? side.counts.curated_share) === undefined
                  ? bi("UNKNOWN", "未知")
                  : formatPercent(side.verification?.curated_share ?? side.counts.curated_share)}
              </td>
              <td className="num mono">{formatNumber(side.verification?.rule_verified_records ?? side.counts.rule_verified_records)}</td>
              <td className="num mono">{formatNumber(side.verification?.provisional_records ?? side.counts.provisional)}</td>
              <td className="num mono">{formatNumber(side.historical_ownership?.verified_current_group ?? 0)}</td>
              <td className="num mono">{formatNumber(side.historical_ownership?.verified_predecessor ?? 0)}</td>
              <td className="num mono">{formatNumber(side.historical_ownership?.unknown ?? 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {compare.comparability?.ownership_basis === "historical_owner_verified" ? (
        <Banner tone="warning" title={bi("This comparison excludes records it cannot date or attribute", "本对比排除了无法判断日期或归属的记录")}>
          {bi(
            "Excluded by the historical-owner basis: " +
              (compare.basis_excluded_totals?.excluded_predecessor_owner ?? 0) +
              " record(s) owned by a predecessor at event time and " +
              (compare.basis_excluded_totals?.excluded_unknown_owner ?? 0) +
              " record(s) whose owner at event time is UNKNOWN. A low count here means the evidence is thin, not that activity was low.",
            "事件发生时所有者口径排除了：" +
              (compare.basis_excluded_totals?.excluded_predecessor_owner ?? 0) +
              " 条当时由前身实体所有的记录，以及 " +
              (compare.basis_excluded_totals?.excluded_unknown_owner ?? 0) +
              " 条当时所有者未知的记录。计数偏低说明证据不足，不代表活动少。",
          )}
        </Banner>
      ) : null}

      {compare.not_evidence_of ? (
        <>
          <SectionHead title={bi("What this comparison does not show", "本对比不能说明什么")} />
          <ul className="small">
            {compare.not_evidence_of.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
    </Card>
  );
}

/* ------------------------------------------------------------------ glossary (zh/en parity) */

export function Glossary() {
  const { bi } = useI18n();
  const terms: { term: string; en: string; zh: string }[] = [
    {
      term: "510(k)",
      en: "A premarket notification: the manufacturer shows a new device is substantially equivalent to a legally marketed predicate device.",
      zh: "上市前通知：制造商证明新器械与已合法上市的对比器械（predicate）实质性等同。",
    },
    { term: "PMA", en: "Premarket approval: the most stringent FDA pathway, for high-risk (Class III) devices.", zh: "上市前批准：FDA 最严格的审批路径，适用于高风险（III 类）器械。" },
    {
      term: "PMA Supplement",
      en: "A change to an already-approved PMA device. It is not a new device and is counted as a separate event type.",
      zh: "PMA 补充批准：对已批准 PMA 器械的变更，不是新器械，单独计为一种事件类型。",
    },
    { term: "Recall", en: "A safety action removing or correcting a device in the field. It is not a product launch and not evidence of innovation.", zh: "召回：在现场撤除或纠正器械的安全行动，不是产品上市，也不是创新证据。" },
    { term: "Applicant", en: "The verbatim company string FDA recorded on the submission. MedRadar preserves it exactly and attributes it separately.", zh: "申请人：FDA 记录在申报上的公司名称原文。MedRadar 原样保留，并另行做归属映射。" },
    { term: "Predicate Device", en: "The already-cleared device a 510(k) submission is compared against.", zh: "对比器械：510(k) 申报时用于比较的、已获批准的器械。" },
    {
      term: "Provisional Attribution",
      en: "A mapping with neither a deterministic rule nor independent evidence. Counts that depend on it are working assumptions.",
      zh: "暂定归属：既没有确定性规则、也没有独立证据的映射；依赖它的计数只是工作假设。",
    },
    {
      term: "Curated Share",
      en: "The share of attributed records whose mapping is evidence-verified or human-reviewed. Typically far below the attributed share.",
      zh: "已核验比例：已归属记录中，映射经独立证据核验或人工复核的比例。通常远低于已归属比例。",
    },
    {
      term: "Current group vs original registrant",
      en: "Current-group counting credits an acquired business to its present owner; original-registrant counting only credits records filed under the organization's own applicant identities.",
      zh: "当前集团口径把被收购业务计入现所有者；原始申请主体口径只计入以本企业自身申请人名称提交的记录。",
    },
  ];
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">{bi("Term", "术语")}</th>
          <th scope="col">{bi("Plain-language explanation", "简明解释")}</th>
        </tr>
      </thead>
      <tbody>
        {terms.map((item) => (
          <tr key={item.term}>
            <td>
              <strong>{item.term}</strong>
            </td>
            <td className="small">{bi(item.en, item.zh)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
