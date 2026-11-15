import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { exportCompareMdUrl, getCompare, getMeta, listOrganizations } from "../api/client";
import { useAsync } from "../api/hooks";
import { MiniBar } from "../components/charts";
import { ExportLink } from "../components/ExportLink";
import {
  Badge,
  Banner,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  formatDate,
  formatPercent,
} from "../components/ui";
import { CompareTransparency } from "../components/transparency";
import { useI18n } from "../i18n";
import type { CompareResponse, EventType, OrgValue } from "../api/types";

const EVENT_TYPES: EventType[] = ["510k", "pma", "pma_supplement", "recall"];
const WINDOWS = [3, 5, 10];

const WARNING_TITLES: Record<string, string> = {
  partial_year_excluded: "Partial calendar year excluded from rates",
  coverage_mismatch: "Source coverage differs between organizations",
  unmapped_category_present: "Some records are unclassified",
  pending_review_present: "Attribution pending human review",
  pathway_mix: "Different regulatory pathway mix",
  recall_share: "Recalls dominate one side",
  low_volume: "Small record base",
};

export function ComparePage() {
  const { t, bi } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const orgs = useMemo(() => (searchParams.get("orgs") ?? "").split(",").filter(Boolean), [searchParams]);
  const windowYears = Number(searchParams.get("years") ?? "5");
  const types = useMemo(() => (searchParams.get("types") ?? "").split(",").filter(Boolean), [searchParams]);
  const basis = searchParams.get("basis") ?? "current_group";
  const reviewFilter = searchParams.get("review") ?? "";
  const organizations = useAsync(() => listOrganizations(), []);
  const meta = useAsync(() => getMeta(), []);

  const setParams = (nextOrgs: string[], nextYears: number, nextTypes: string[]) => {
    const params = new URLSearchParams();
    if (nextOrgs.length) params.set("orgs", nextOrgs.join(","));
    if (nextYears !== 5) params.set("years", String(nextYears));
    if (nextTypes.length) params.set("types", nextTypes.join(","));
    setSearchParams(params);
  };

  const bounds = useMemo(() => windowBounds(meta.data?.coverage.latest_event_date ?? null, windowYears), [meta.data, windowYears]);

  const compare = useAsync(
    () =>
      getCompare(orgs, {
        from: bounds?.from,
        to: bounds?.to,
        types: types.length ? (types as EventType[]) : undefined,
        basis: basis === "current_group" ? undefined : basis,
        review: reviewFilter || undefined,
      }),
    [orgs.join(","), bounds?.from ?? "", bounds?.to ?? "", types.join(","), basis, reviewFilter],
  );

  const setExtra = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams);
    if (!value || (key === "basis" && value === "current_group")) params.delete(key);
    else params.set(key, value);
    setSearchParams(params);
  };

  const availableOrgs = organizations.data?.organizations ?? [];

  const addOrg = (key: string) => {
    if (!key || orgs.includes(key) || orgs.length >= 4) return;
    setParams([...orgs, key], windowYears, types);
  };
  const removeOrg = (key: string) => setParams(orgs.filter((item) => item !== key), windowYears, types);
  const toggleType = (type: EventType) => {
    const next = types.includes(type) ? types.filter((item) => item !== type) : [...types, type];
    setParams(orgs, windowYears, next);
  };

  return (
    <>
      <PageHeader
        eyebrow={bi("Competitive intelligence", "竞争情报")}
        title={t("compare.title")}
        description={t("compare.desc")}
        actions={
          orgs.length >= 2 ? (
            <ExportLink
              href={exportCompareMdUrl(orgs, {
                from: bounds?.from,
                to: bounds?.to,
                types: types.length ? (types as EventType[]) : undefined,
                basis: basis === "current_group" ? undefined : basis,
                review: reviewFilter || undefined,
              })}
              title="Markdown report with the same window, basis, warnings and counting rule as this screen."
            >
              {bi("Export report", "导出报告")} (MD)
            </ExportLink>
          ) : null
        }
      />

      <div className="stack">
        <Card title={bi("Selection and window", "对比设置")} note={bi("Two to four organizations. One window and one counting rule apply to every side.", "可选 2-4 家企业；所有对比方使用同一时间窗口与统计口径。")}>
          <div className="row wrap" style={{ gap: 8 }}>
            {orgs.map((key) => {
              const org = availableOrgs.find((item) => item.key === key);
              return (
                <span className="filter-token" key={key} style={{ fontSize: 12, padding: "3px 7px" }}>
                  {org?.display_name ?? key}
                  <button type="button" aria-label={"Remove " + key} onClick={() => removeOrg(key)}>
                    x
                  </button>
                </span>
              );
            })}
            {orgs.length < 4 ? (
              <select
                className="select"
                value=""
                onChange={(event) => {
                  addOrg(event.target.value);
                  event.target.value = "";
                }}
                aria-label={bi("Add an organization", "添加企业")}
              >
                <option value="">{bi("Add an organization...", "添加企业...")}</option>
                {availableOrgs
                  .filter((org) => !orgs.includes(org.key))
                  .map((org) => (
                    <option key={org.key} value={org.key}>
                      {org.display_name} {org.ticker ? "(" + org.ticker + ")" : ""}
                    </option>
                  ))}
              </select>
            ) : null}
          </div>

          <div className="divider" />

          <div className="row wrap" style={{ gap: 24 }}>
            <div className="field">
              <span className="field-label">{bi("Window", "时间窗口")}</span>
              <div className="chip-group">
                {WINDOWS.map((years) => (
                  <button
                    key={years}
                    type="button"
                    className="chip"
                    aria-pressed={windowYears === years}
                    onClick={() => setParams(orgs, years, types)}
                  >
                    {years} {bi("years", "年")}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <span className="field-label">{t("common.type")}</span>
              <div className="chip-group">
                {EVENT_TYPES.map((type) => (
                  <button key={type} type="button" className="chip" aria-pressed={types.length === 0 || types.includes(type)} onClick={() => toggleType(type)}>
                    {t(("type." + type) as never)}
                  </button>
                ))}
              </div>
              <div className="tiny muted">{bi("No selection means all event types.", "不选择即为全部事件类型。")}</div>
            </div>
            <div className="field">
              <span className="field-label">{bi("Ownership basis", "所有权口径")}</span>
              <select className="select" value={basis} onChange={(event) => setExtra("basis", event.target.value)}>
                <option value="current_group">{bi("Current group (acquired entities included)", "当前集团（含被收购实体）")}</option>
                <option value="original_registrant">{bi("Original registrant only", "仅原始申请主体")}</option>
              </select>
              <div className="tiny muted">{bi("Current-group counts credit an acquired business to its present owner; original-registrant counts only records filed under the organization's own applicant identities.", "当前集团口径把被收购业务计入现所有者；原始申请主体口径只计入以本企业自身申请人名称提交的记录。")}</div>
            </div>
            <div className="field">
              <span className="field-label">{bi("Only verified mappings", "仅已核验映射")}</span>
              <select className="select" value={reviewFilter} onChange={(event) => setExtra("review", event.target.value)}>
                <option value="">{bi("All mappings", "全部映射")}</option>
                <option value="curated">{bi("Evidence-verified or human-reviewed only", "仅经证据核验或人工复核")}</option>
                <option value="rule_verified">{bi("Deterministic rule only", "仅确定性规则")}</option>
              </select>
              <div className="tiny muted">{bi("Filtering to verified mappings usually lowers both counts; it does not rank the organizations.", "仅看已核验映射通常会让双方计数都下降；它并不构成企业排名。")}</div>
            </div>
          </div>
        </Card>

        {orgs.length < 2 ? (
          <Card>
            <EmptyState
              title={bi("Pick at least two organizations", "请选择至少两家企业")}
              description={bi(
                "Comparison needs two sides to be meaningful. Suggested starting point: Medtronic and GE HealthCare, the pair used in the product acceptance walkthrough.",
                "对比至少需要两家企业。建议起点：美敦力 与 GE 医疗（产品验收流程即使用这一组）。",
              )}
              actions={
                <>
                  <button type="button" className="btn primary" onClick={() => setParams(["medtronic", "ge_healthcare"], 5, [])}>
                    {bi("Compare Medtronic and GE HealthCare", "对比美敦力与 GE 医疗")}
                  </button>
                  <Link className="btn" to="/organizations">
                    {bi("Browse organizations", "浏览企业")}
                  </Link>
                </>
              }
            />
          </Card>
        ) : compare.status === "error" && compare.error ? (
          <Card>
            <ErrorState message={compare.error.message} onRetry={compare.reload} />
          </Card>
        ) : !compare.data ? (
          <Card>
            <LoadingBlock lines={10} />
          </Card>
        ) : (
          <CompareBody data={compare.data} />
        )}

        <Callout>
          {bi(
            "Comparison method: identical event-type filter and date window on every side; shares use all tracked organizations in the same window as the denominator; per-year rates use complete calendar years only. Coverage differences are stated as warnings above the numbers.",
            "对比方法：所有对比方使用相同的事件类型筛选与日期窗口；占比的分母是同一窗口内全部收录企业的记录数；逐年速率仅使用完整自然年。覆盖差异会以警告形式显示在数字之前。",
          )}
        </Callout>
      </div>
    </>
  );
}

/**
 * Window bounds derived from the snapshot's latest event date: the window ends at the last
 * complete calendar year, because partial years distort per-year rates.
 */
function windowBounds(latestEventDate: string | null, years: number): { from: string; to: string } | null {
  if (!latestEventDate) return null;
  const latest = new Date(latestEventDate.slice(0, 10) + "T00:00:00Z");
  if (Number.isNaN(latest.getTime())) return null;
  const isYearEnd = latest.getUTCMonth() === 11 && latest.getUTCDate() === 31;
  const lastCompleteYear = isYearEnd ? latest.getUTCFullYear() : latest.getUTCFullYear() - 1;
  const firstYear = lastCompleteYear - years + 1;
  return { from: firstYear + "-01-01", to: lastCompleteYear + "-12-31" };
}

function valueOf(values: OrgValue[], key: string): number {
  return values.find((item) => item.org_key === key)?.count ?? 0;
}

function CompareBody({ data }: { data: CompareResponse }) {
  const { t, bi } = useI18n();
  const sides = data.organizations;
  const names = sides.map((side) => side.display_name);
  const maxByType = (values: OrgValue[]) => Math.max(1, ...values.map((item) => item.count));

  return (
    <div className="stack">
      <CompareTransparency compare={data} />

      {data.warnings.length ? (
        <div className="stack" style={{ gap: 8 }}>
          {data.warnings.map((warning) => (
            <Banner key={warning.code + warning.org_keys.join(",")} tone={warning.severity === "warning" ? "warning" : "info"} title={WARNING_TITLES[warning.code] ?? warning.code.replace(/_/g, " ")}>
              {warning.message}
            </Banner>
          ))}
        </div>
      ) : (
        <Banner tone="info">{bi("No coverage or comparability warnings were raised for this window.", "该窗口内没有触发覆盖或可比性警告。")}</Banner>
      )}

      <Callout accent>
        {bi("Records are not innovation. ", "记录数不等于创新能力。")}
        {data.disclaimer}
      </Callout>

      <div className="grid cols-2">
        {sides.map((side) => (
          <Card
            key={side.key}
            title={
              <span className="row" style={{ gap: 8 }}>
                <Link className="link" to={"/organizations/" + side.key} style={{ color: "inherit", fontWeight: 600 }}>
                  {side.display_name}
                </Link>
                {side.ticker ? <Badge tone="outline">{side.ticker}</Badge> : null}
                {side.country ? <Badge tone="outline">{side.country}</Badge> : null}
              </span>
            }
            note={side.legal_name}
          >
            <div className="row wrap" style={{ gap: 18 }}>
              <div>
                <div className="metric-label">{t("common.records")}</div>
                <div className="metric-value sm">{side.counts.records.toLocaleString()}</div>
              </div>
              {side.counts.by_type.map((row) => (
                <div key={row.event_type}>
                  <div className="metric-label">{t(("type." + row.event_type) as never)}</div>
                  <div className="metric-value sm">{row.count.toLocaleString()}</div>
                </div>
              ))}
            </div>
            <div className="divider" />
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">{t("common.source")}</th>
                    <th scope="col" className="num">{t("common.records")}</th>
                    <th scope="col">{bi("Event dates", "事件日期")}</th>
                  </tr>
                </thead>
                <tbody>
                  {side.coverage.sources.map((source) => (
                    <tr key={source.source_id}>
                      <td className="small">{source.name}</td>
                      <td className="num">{source.records.toLocaleString()}</td>
                      <td className="small muted nowrap">
                        {formatDate(source.min_event_date)} {"\u2192"} {formatDate(source.max_event_date)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card-footer">
              {bi("Attribution pending review", "归属待复核")}: {side.coverage.pending_review.toLocaleString()} - {" "}
              {bi("unclassified", "未分类")}: {side.coverage.unmapped_category.toLocaleString()}
            </div>
          </Card>
        ))}
      </div>

      <Card
        title={bi("Records by event type", "按事件类型的记录数")}
        note={bi("Same window, same filters. Each count is a count of records, not products.", "同一窗口、同一筛选条件。计数单位为记录，而非产品。")}
      >
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">{t("common.type")}</th>
                {names.map((name) => (
                  <th key={name} scope="col" className="num">
                    {name}
                  </th>
                ))}
                <th scope="col">{bi("Share of all tracked", "占全部收录企业")}</th>
              </tr>
            </thead>
            <tbody>
              {data.totals_by_type.map((row) => {
                const max = maxByType(row.values);
                return (
                  <tr key={row.event_type}>
                    <td className="cell-primary">{row.label}</td>
                    {sides.map((side) => (
                      <td key={side.key} className="num">
                        <MiniBar value={valueOf(row.values, side.key)} max={max} />
                      </td>
                    ))}
                    <td className="small">
                      {sides.map((side) => side.display_name + " " + formatPercent(side.share_of_all_tracked[row.event_type] ?? 0, 1)).join(" / ")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="card-footer">{data.totals_by_type[0]?.note ?? ""}</div>
      </Card>

      <div className="grid cols-2">
        <Card title={bi("Records by FDA medical specialty", "按 FDA 医学专科分类")} note={bi("Category comes from the FDA classification dictionary through the product code.", "类别由产品代码经 FDA 分类字典映射。")} flush>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">{t("common.category")}</th>
                  {names.map((name) => (
                    <th key={name} scope="col" className="num">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.category_matrix.slice(0, 15).map((row) => {
                  const max = maxByType(row.values);
                  return (
                    <tr key={row.id}>
                      <td className="small">{row.label}</td>
                      {sides.map((side) => {
                        const value = valueOf(row.values, side.key);
                        return (
                          <td key={side.key} className="num">
                            {value ? <MiniBar value={value} max={max} /> : <span className="muted">-</span>}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title={bi("Records by device class", "按器械等级")} note={bi("Regulatory risk class, not a technology ranking.", "监管风险分级，不代表技术排名。")} flush>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">{t("common.deviceClass")}</th>
                  {names.map((name) => (
                    <th key={name} scope="col" className="num">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.class_matrix.map((row) => (
                  <tr key={row.device_class}>
                    <td className="small">{row.label}</td>
                    {sides.map((side) => (
                      <td key={side.key} className="num">
                        {valueOf(row.values, side.key).toLocaleString()}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card
        title={bi("Records per complete calendar year", "每个完整自然年的记录数")}
        note={bi("Complete years only: " + (data.window.complete_years.join(", ") || "none") + ". Window: " + (data.window.effective.from ?? "-") + " to " + (data.window.effective.to ?? "-") + ".", "仅完整年度：" + (data.window.complete_years.join(", ") || "无") + "。窗口：" + (data.window.effective.from ?? "-") + " 至 " + (data.window.effective.to ?? "-") + "。")}
        flush
      >
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">{t("common.year")}</th>
                {names.map((name) => (
                  <th key={name} scope="col" className="num">
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.window.complete_years.map((year) => (
                <tr key={year}>
                  <td className="mono">{year}</td>
                  {sides.map((side) => {
                    const row = side.per_year_totals.find((item) => item.year === year);
                    return (
                      <td key={side.key} className="num">
                        {(row?.total ?? 0).toLocaleString()}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <td className="cell-primary">{t("common.total")}</td>
                {sides.map((side) => (
                  <td key={side.key} className="num">
                    {side.counts.records.toLocaleString()}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <div className="card-footer">
          {bi(
            "Note: the total row counts the effective window, which can include partial years at the edges; those partial years are excluded from the per-year rows.",
            "说明：合计行为有效窗口内的记录数，窗口两端的非完整年份只在合计中体现，不计入逐年行。",
          )}
        </div>
      </Card>

      <div className="card-footer" style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)" }}>
        {bi("Snapshot", "快照")} <span className="mono">{data.snapshot.id}</span>, {bi("collected", "采集于")} <span className="mono">{data.snapshot.collected_at}</span>.{" "}
        {bi("Counting rule", "统计口径")}: {data.basis.rule}
      </div>
    </div>
  );
}
