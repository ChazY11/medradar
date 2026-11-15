import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  devicesCsvUrl,
  getDeviceQuality,
  listDevices,
  listUnlinkedRecalls,
  type DeviceQualityResponse,
  type DevicesResponse,
} from "../api/devices";
import { listOrganizations } from "../api/client";
import { useAsync } from "../api/hooks";
import { useI18n } from "../i18n";
import { ExportLink } from "../components/ExportLink";
import {
  Badge,
  Banner,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  Grid,
  LoadingBlock,
  MetricTile,
  PageHeader,
  Pagination,
  formatDate,
  formatNumber,
} from "../components/ui";

const PATHWAYS = [
  { id: "510k", en: "510(k) clearances", zh: "510(k) 批准" },
  { id: "pma", en: "PMA approvals", zh: "PMA 批准" },
];

export function DevicesPage() {
  const { t, bi } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const org = searchParams.get("org") ?? "";
  const pathway = searchParams.get("pathway") ?? "";
  const category = searchParams.get("category") ?? "";
  const productCode = searchParams.get("product_code") ?? "";
  const relation = searchParams.get("relation") ?? "";
  const sort = searchParams.get("sort") ?? "relevance";
  const page = Number(searchParams.get("page") ?? "1") || 1;
  const showUnlinked = searchParams.get("view") === "unlinked";

  const organizations = useAsync(() => listOrganizations(), []);
  const quality = useAsync<DeviceQualityResponse>(() => getDeviceQuality(), []);
  const devices = useAsync<DevicesResponse>(
    () =>
      listDevices({
        q: q || undefined,
        org: org || undefined,
        pathway: pathway || undefined,
        category: category || undefined,
        product_code: productCode || undefined,
        relation: relation || undefined,
        sort,
        page,
        page_size: 25,
      }),
    [q, org, pathway, category, productCode, relation, sort, page],
  );
  const unlinked = useAsync(() => (showUnlinked ? listUnlinkedRecalls(1, 25) : Promise.resolve(null)), [showUnlinked]);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value || (key === "sort" && value === "relevance")) next.delete(key);
    else next.set(key, value);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const csvUrl = devicesCsvUrl({
    q: q || undefined,
    org: org || undefined,
    pathway: pathway || undefined,
    category: category || undefined,
    product_code: productCode || undefined,
    relation: relation || undefined,
    sort,
  });

  const filteredDescription = useMemo(() => {
    const parts = [];
    if (q) parts.push('"' + q + '"');
    if (org) parts.push(org);
    if (pathway) parts.push(pathway === "510k" ? "510(k)" : "PMA");
    if (productCode) parts.push("product code " + productCode);
    if (relation) parts.push("relations: " + relation);
    return parts.join(" - ");
  }, [q, org, pathway, productCode, relation]);

  return (
    <>
      <PageHeader
        eyebrow={bi("Device intelligence", "器械情报")}
        title={bi("Devices and product families", "器械与产品家族")}
        description={bi(
          "Search regulatory applications as devices: each device identity comes from its own FDA application, a PMA family is the official application hierarchy, and a candidate relation is never presented as established.",
          "把监管申请当作器械来检索：每个器械身份来自其自身的 FDA 申请；PMA 家族是官方申请层级；候选关系绝不会被当作已确认关系展示。",
        )}
        actions={
          <>
            {devices.data ? (
              <ExportLink href={csvUrl} title="CSV of every device matching the current filters, with the same provenance header as the other exports.">
                {bi("Export devices", "导出器械")} (CSV)
              </ExportLink>
            ) : null}
            <Link className="btn" to="/devices?view=unlinked">
              {bi("Records without a device identity", "未建立器械身份的记录")}
            </Link>
          </>
        }
      />

      <div className="stack">
        {quality.data ? (
          <Grid cols={5}>
            <MetricTile
              label={bi("Device identities", "器械身份")}
              value={formatNumber(quality.data.devices)}
              sub={bi(formatNumber(quality.data.applications) + " regulatory applications", formatNumber(quality.data.applications) + " 个监管申请")}
            />
            <MetricTile
              label={bi("PMA product families", "PMA 产品家族")}
              value={formatNumber((quality.data.families as { families?: number }).families ?? 0)}
              sub={bi(
                formatNumber((quality.data.families as { without_original_in_snapshot?: number }).without_original_in_snapshot ?? 0) +
                  " without the original approval in this snapshot",
                String((quality.data.families as { without_original_in_snapshot?: number }).without_original_in_snapshot ?? 0) +
                  " 个家族的原始批准不在本快照中",
              )}
            />
            <MetricTile
              label={bi("Recalls linked by official K number", "按官方 K 编号关联的召回")}
              value={formatNumber((quality.data.recalls as { with_confirmed_application_reference_in_snapshot?: number }).with_confirmed_application_reference_in_snapshot ?? 0)}
              sub={bi(
                formatNumber((quality.data.recalls as { without_any_official_reference?: number }).without_any_official_reference ?? 0) + " with no official reference",
                formatNumber((quality.data.recalls as { without_any_official_reference?: number }).without_any_official_reference ?? 0) + " 条没有任何官方引用",
              )}
            />
            <MetricTile
              label={bi("Confirmed relations", "已确认关系")}
              value={formatNumber((quality.data.relations as { by_status?: Record<string, number> }).by_status?.confirmed ?? 0)}
              sub={bi("official identifier or record field only", "仅来自官方标识或记录字段")}
            />
            <MetricTile
              label={bi("Candidate relations", "候选关系")}
              value={formatNumber((quality.data.relations as { by_status?: Record<string, number> }).by_status?.candidate ?? 0)}
              sub={bi("hypotheses, never established", "仅为假设，绝不视为已确认")}
            />
          </Grid>
        ) : (
          <LoadingBlock height={90} />
        )}

        <Banner tone="info" title={bi("How to read a device result", "如何阅读器械检索结果")}>
          {bi(
            "The name is not the identity. Two rows can share a device name and still be different devices; the official FDA identifier and the applicant distinguish them. A PMA row points at the approved device - its supplements are versions, not new devices. Candidate relations come from a deterministic rule and are always labelled.",
            "名称不等于身份。两行可能同名却是不同器械；区分它们的是官方 FDA 标识与申请人。PMA 行指向已批准的器械——补充批准是版本，不是新器械。候选关系来自确定性规则，且始终带有标注。",
          )}
        </Banner>

        <Card
          title={bi("Device explorer", "器械浏览器")}
          note={
            devices.data
              ? bi(formatNumber(devices.data.total) + " matching device identities", "匹配的器械身份 " + formatNumber(devices.data.total) + " 个") +
                (devices.data.index_build_ms ? " - " + bi("device index built in " + Math.round(devices.data.index_build_ms) + " ms for this process", "本进程构建器械索引耗时 " + Math.round(devices.data.index_build_ms) + " 毫秒") : "")
              : bi("Search by device name, trade name, applicant or an official K/PMA number.", "按器械名、商品名、申请人或官方 K/PMA 编号检索。")
          }
        >
          <div className="row wrap" style={{ gap: 10, alignItems: "flex-end" }}>
            <label className="field" style={{ minWidth: 280, flex: 1 }}>
              <span className="field-label">{bi("Device name, applicant or official number", "器械名、申请人或官方编号")}</span>
              <input
                className="input"
                value={q}
                placeholder="e.g. VIRTUSO, K181234, P980016, Medtronic"
                onChange={(event) => setParam("q", event.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">{bi("Organization", "企业")}</span>
              <select className="select" value={org} onChange={(event) => setParam("org", event.target.value)}>
                <option value="">{bi("all tracked", "全部收录企业")}</option>
                {(organizations.data?.organizations ?? []).map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">{bi("Pathway", "监管路径")}</span>
              <select className="select" value={pathway} onChange={(event) => setParam("pathway", event.target.value)}>
                <option value="">{bi("all", "全部")}</option>
                {PATHWAYS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {bi(item.en, item.zh)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">{bi("Product code", "产品代码")}</span>
              <input className="input mono" style={{ width: 110 }} value={productCode} onChange={(event) => setParam("product_code", event.target.value.toUpperCase())} />
            </label>
            <label className="field">
              <span className="field-label">{bi("Medical specialty", "医疗专科")}</span>
              <select className="select" value={category} onChange={(event) => setParam("category", event.target.value)}>
                <option value="">{bi("all", "全部")}</option>
                {(devices.data?.categories ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">{bi("Relations", "关系")}</span>
              <select className="select" value={relation} onChange={(event) => setParam("relation", event.target.value)}>
                <option value="">{bi("any", "不限")}</option>
                <option value="confirmed">{bi("has confirmed relation", "有已确认关系")}</option>
                <option value="candidate">{bi("candidate only", "仅有候选关系")}</option>
                <option value="none">{bi("no relation", "无关系")}</option>
              </select>
            </label>
            <label className="field">
              <span className="field-label">{bi("Sort", "排序")}</span>
              <select className="select" value={sort} onChange={(event) => setParam("sort", event.target.value)}>
                <option value="relevance">{bi("most relations", "关系最多")}</option>
                <option value="date_desc">{bi("newest decision", "最新决定")}</option>
                <option value="name_asc">{bi("name", "名称")}</option>
              </select>
            </label>
          </div>

          {filteredDescription ? <div className="small muted" style={{ marginTop: 6 }}>{bi("Filters: ", "筛选：")}{filteredDescription}</div> : null}

          {devices.error ? <ErrorState message={devices.error.message} onRetry={devices.reload} /> : null}
          {!devices.data && devices.status === "loading" ? <LoadingBlock lines={6} /> : null}

          {devices.data ? (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">{bi("Device", "器械")}</th>
                    <th scope="col">{bi("FDA identifier", "FDA 标识")}</th>
                    <th scope="col">{bi("Applicant / organization", "申请人/企业")}</th>
                    <th scope="col">{bi("Product code", "产品代码")}</th>
                    <th scope="col">{bi("Specialty", "专科")}</th>
                    <th scope="col" className="num">{bi("Applications", "申请数")}</th>
                    <th scope="col" className="num">{bi("Relations (confirmed / candidate)", "关系（已确认/候选）")}</th>
                    <th scope="col">{bi("First decision", "首个决定")}</th>
                  </tr>
                </thead>
                <tbody>
                  {devices.data.items.map((item) => (
                    <tr key={item.device_id}>
                      <td>
                        <Link className="link" to={"/devices/" + encodeURIComponent(item.device_id)}>
                          {(item.name || item.official_id).slice(0, 80)}
                        </Link>
                        <div className="cell-sub">
                          {item.kind === "510k" ? bi("device identified by a 510(k) clearance", "由 510(k) 批准识别的器械") : bi("device identified by a PMA approval", "由 PMA 批准识别的器械")}
                        </div>
                      </td>
                      <td className="mono small">{item.official_id}</td>
                      <td className="small">
                        {item.applicant_name}
                        <div className="cell-sub muted">{item.organization_display ?? bi("not attributed", "未归属")}</div>
                      </td>
                      <td className="mono small">{item.product_code ?? "-"}</td>
                      <td className="small">{item.category_label ?? "-"}</td>
                      <td className="num mono">{formatNumber(item.counts?.applications ?? 1)}</td>
                      <td className="small">
                        <Badge tone="ok">{formatNumber(item.counts?.confirmed_relations ?? 0)}</Badge>{" "}
                        <Badge tone="warn">{formatNumber(item.counts?.candidate_relations ?? 0)}</Badge>
                      </td>
                      <td className="mono small">{formatDate(item.first_event_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {devices.data.total === 0 ? (
                <EmptyState
                  title={bi("No device matches these filters", "没有器械符合当前筛选条件")}
                  description={bi("Try a different official number, organization or remove the relation filter.", "请尝试其他官方编号、企业，或移除关系筛选。")}
                />
              ) : null}
              <Pagination page={devices.data.page} totalPages={devices.data.total_pages} total={devices.data.total} onPage={(next) => setParam("page", String(next))} />
            </>
          ) : null}
        </Card>

        {showUnlinked ? (
          <Card
            title={bi("Records without a device identity", "未建立器械身份的记录")}
            note={bi(
              "A recall record does not identify a device. When it carries no official K-number reference it stays unlinked and is counted here; nothing is guessed and nothing is deleted.",
              "召回记录本身不标识器械。若没有任何官方 K 编号引用，就保持“未关联”并在此计数；系统不猜测、也不删除。",
            )}
          >
            {unlinked.data ? (
              <>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">{bi("Recall", "召回")}</th>
                      <th scope="col">{bi("Initiated", "启动日期")}</th>
                      <th scope="col">{bi("Applicant", "申请人")}</th>
                      <th scope="col">{bi("Why unlinked", "未关联原因")}</th>
                      <th scope="col" />
                    </tr>
                  </thead>
                  <tbody>
                    {unlinked.data.items.map((row) => (
                      <tr key={row.recall.event_id}>
                        <td className="small">{(row.recall.product_description ?? row.recall.official_id).slice(0, 70)}</td>
                        <td className="mono small">{formatDate(row.recall.initiated_date)}</td>
                        <td className="small">{row.recall.applicant_name}</td>
                        <td className="small muted">{row.reason}</td>
                        <td>
                          <a className="link small" href={row.official_url} target="_blank" rel="noreferrer">
                            {t("common.openRecord")}
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Callout>
                  {bi(
                    formatNumber(unlinked.data.total) + " recall records have no link to an application in this snapshot. " + unlinked.data.note,
                    "本快照中有 " + formatNumber(unlinked.data.total) + " 条召回记录未能关联到申请。" + unlinked.data.note,
                  )}
                </Callout>
              </>
            ) : (
              <LoadingBlock lines={5} />
            )}
          </Card>
        ) : null}

        {quality.data ? (
          <Callout>
            {bi(
              "Relationship quality: " +
                String((quality.data.relations as { by_status?: Record<string, number> }).by_status?.confirmed ?? 0) +
                " confirmed and " +
                String((quality.data.relations as { by_status?: Record<string, number> }).by_status?.candidate ?? 0) +
                " candidate relations. No independent sample of device relations has been reviewed yet, so no accuracy figure is claimed - rule consistency is not accuracy. Predicate relationships are not modelled because openFDA exposes no predicate identifier.",
              "关系质量：已确认 " +
                String((quality.data.relations as { by_status?: Record<string, number> }).by_status?.confirmed ?? 0) +
                " 条，候选 " +
                String((quality.data.relations as { by_status?: Record<string, number> }).by_status?.candidate ?? 0) +
                " 条。器械关系尚无独立抽样复核，因此不宣称准确率——规则一致性不等于准确率。由于 openFDA 不提供 predicate 标识，predicate 关系不予建模。",
            )}
          </Callout>
        ) : null}
      </div>
    </>
  );
}
