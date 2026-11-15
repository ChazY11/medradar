import { Link, useParams } from "react-router-dom";
import {
  deviceMarkdownUrl,
  getDevice,
  type ApplicationPayload,
  type DeviceDetailResponse,
  type DeviceRelationPayload,
} from "../api/devices";
import { useAsync } from "../api/hooks";
import { useI18n } from "../i18n";
import { DeviceTimeline } from "../components/DeviceTimeline";
import { ExportLink } from "../components/ExportLink";
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
  SectionHead,
  formatDate,
  formatNumber,
} from "../components/ui";

function ApplicationTable({ rows, emptyNote }: { rows: ApplicationPayload[]; emptyNote: string }) {
  const { bi } = useI18n();
  if (!rows.length) return <div className="muted small">{emptyNote}</div>;
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">{bi("Official identifier", "官方标识")}</th>
          <th scope="col">{bi("Type", "类型")}</th>
          <th scope="col">{bi("Decision date", "决定日期")}</th>
          <th scope="col">{bi("What changed", "变更内容")}</th>
          <th scope="col" />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.application_id}>
            <td className="mono small">{row.official_id}</td>
            <td className="small">{row.kind_label}</td>
            <td className="mono small">{formatDate(row.decision_date)}</td>
            <td className="small">{(row.supplement_type ?? row.supplement_reason ?? row.decision_code ?? "-").slice(0, 90)}</td>
            <td>
              <a className="link small" href={row.official_url} target="_blank" rel="noreferrer">
                {bi("official record", "官方记录")}
              </a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RelationTable({ rows, tone }: { rows: DeviceRelationPayload[]; tone: "confirmed" | "candidate" }) {
  const { bi } = useI18n();
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">{bi("Type", "类型")}</th>
          <th scope="col">{bi("From -> to", "来源 → 目标")}</th>
          <th scope="col">{bi("Rule", "规则")}</th>
          <th scope="col">{bi("Evidence", "证据")}</th>
          <th scope="col">{bi("Status", "状态")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((relation) => (
          <tr key={relation.relation_id}>
            <td className="small">{relation.relation_type}</td>
            <td className="mono tiny">
              {relation.source_id}
              {" -> "}
              {relation.target_id}
              {relation.target_in_snapshot ? null : <div className="muted">{bi("target not in this snapshot", "目标不在本快照中")}</div>}
            </td>
            <td className="mono tiny">{relation.rule}</td>
            <td className="small">
              {relation.evidence.map((item, index) => (
                <div key={index}>
                  <span className="mono tiny">{item.field}</span> = <span className="mono tiny">{item.value}</span>
                  {item.official_url ? (
                    <>
                      {" "}
                      <a className="link tiny" href={item.official_url} target="_blank" rel="noreferrer">
                        source
                      </a>
                    </>
                  ) : null}
                  {item.note ? <div className="tiny muted">{item.note}</div> : null}
                </div>
              ))}
            </td>
            <td>
              <Badge tone={tone === "confirmed" ? "ok" : "warn"}>{tone === "confirmed" ? bi("confirmed", "已确认") : bi("candidate only", "仅候选")}</Badge>
              {relation.score !== null ? <div className="tiny muted">score {relation.score}</div> : null}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DevicePage() {
  const { bi } = useI18n();
  const params = useParams();
  const deviceId = decodeURIComponent(params.deviceId ?? "");
  const device = useAsync<DeviceDetailResponse>(() => getDevice(deviceId), [deviceId]);

  if (device.error) {
    return (
      <>
        <PageHeader eyebrow={bi("Device intelligence", "器械情报")} title={bi("Device", "器械")} />
        <Card>
          <ErrorState message={device.error.message} onRetry={device.reload} />
        </Card>
      </>
    );
  }
  if (!device.data) {
    return (
      <>
        <PageHeader eyebrow={bi("Device intelligence", "器械情报")} title={bi("Device", "器械")} />
        <Card>
          <LoadingBlock lines={10} />
        </Card>
      </>
    );
  }

  const data = device.data;
  const summary = data.device;
  const confirmed = data.relations.confirmed;
  const candidates = data.relations.candidate;

  return (
    <>
      <PageHeader
        eyebrow={bi("Device intelligence", "器械情报") + " - " + (summary.kind === "510k" ? "510(k)" : "PMA")}
        title={summary.name.slice(0, 140)}
        description={data.identity.basis_text}
        actions={
          <>
            <ExportLink href={deviceMarkdownUrl(summary.device_id)} title="Markdown brief with the same identity, relations and evidence as this page.">
              {bi("Export device brief", "导出器械简报")} (MD)
            </ExportLink>
            <Link className="btn" to={"/devices?org=" + (summary.organization_key ?? "")}>
              {bi("More devices", "更多器械")}
            </Link>
          </>
        }
      />

      <div className="stack">
        <Card
          title={bi("What this page represents", "本页代表什么")}
          note={bi("A device identity, not a marketing product record and not a regulatory record.", "这是一个器械身份，而不是营销产品记录，也不是单条监管记录。")}
        >
          <KeyValue
            rows={[
              { label: bi("Identity basis", "身份依据"), value: <span className="small">{data.identity.what_this_page_represents}</span> },
              { label: bi("MedRadar identifier", "MedRadar 标识"), value: <span className="mono small">{summary.device_id}</span> },
              {
                label: bi("Official FDA identifier", "官方 FDA 标识"),
                value: data.application ? (
                  <a className="mono small link" href={data.application.official_url} target="_blank" rel="noreferrer">
                    {data.application.official_id}
                  </a>
                ) : (
                  "-"
                ),
              },
              { label: bi("Applicant (as recorded)", "申请人（原文）"), value: <span className="mono small">{summary.applicant_name}</span> },
              {
                label: bi("Registry attribution", "注册表归属"),
                value: (
                  <span className="row" style={{ gap: 6 }}>
                    {data.applicant.organization_display ? (
                      <Link className="link" to={"/organizations/" + data.applicant.organization_key}>
                        {data.applicant.organization_display}
                      </Link>
                    ) : (
                      <span className="muted">{bi("not attributed", "未归属")}</span>
                    )}
                    <Badge tone={data.applicant.verified ? "ok" : "warn"}>{data.applicant.verification}</Badge>
                  </span>
                ),
              },
              { label: bi("Product code", "产品代码"), value: <span className="mono small">{summary.product_code ?? "-"}</span> },
              { label: bi("Medical specialty", "医疗专科"), value: summary.category_label ?? "-" },
              { label: bi("Device class", "器械等级"), value: summary.device_class ? "Class " + summary.device_class : bi("unknown", "未知") },
              { label: bi("First decision", "首个决定日期"), value: formatDate(summary.first_event_date) },
            ]}
          />
          <Callout>
            {bi(
              data.identity.not_impersonating_fda +
                " Device names are not unique: MedRadar never merges two devices because their names match.",
              data.identity.not_impersonating_fda + " 器械名称并不唯一：MedRadar 不会因为名称相同而合并两个器械。",
            )}
          </Callout>
        </Card>

        <Grid cols={5}>
          <MetricTile label={bi("Applications", "申请数")} value={formatNumber(data.counts.applications)} sub={bi("1 approval + versions", "1 个批准 + 各版本")} />
          <MetricTile label={bi("Versions (supplements)", "版本（补充批准）")} value={formatNumber(data.counts.versions)} />
          <MetricTile label={bi("Related recalls", "相关召回")} value={formatNumber(data.counts.recalls)} sub={bi("official K-number reference", "官方 K 编号引用")} />
          <MetricTile label={bi("Confirmed relations", "已确认关系")} value={formatNumber(data.counts.confirmed_relations)} accent sub={bi("official identifier or field", "官方标识或字段")} />
          <MetricTile label={bi("Candidate relations", "候选关系")} value={formatNumber(data.counts.candidate_relations)} sub={bi("not established", "尚未确认")} />
        </Grid>

        {data.family ? (
          <Card
            title={bi("Product family: the official PMA application hierarchy", "产品家族：官方 PMA 申请层级")}
            note={bi(
              "The family is defined by the FDA PMA number: the original approval plus every supplement that carries the same number. A supplement is a version of this device, not a new device.",
              "家族由 FDA PMA 编号定义：原始批准加上所有同一编号的补充批准。补充批准是该器械的版本，而不是新器械。",
            )}
          >
            <KeyValue
              rows={[
                { label: bi("Family", "家族"), value: <span className="mono small">{data.family.family_id}</span> },
                { label: bi("Family name", "家族名称"), value: <span className="small">{(data.family.name || "-").slice(0, 160)}</span> },
                { label: bi("Supplements", "补充批准"), value: formatNumber(data.family.supplement_count) },
                { label: bi("Window", "时间跨度"), value: formatDate(data.family.first_event_date) + " - " + formatDate(data.family.last_event_date) },
                {
                  label: bi("Original approval in this snapshot", "原始批准是否在本快照中"),
                  value: data.family.original_in_snapshot ? <Badge tone="ok">{bi("yes", "是")}</Badge> : <Badge tone="warn">{bi("no", "否")}</Badge>,
                },
              ]}
            />
            {data.family.models.length ? (
              <div className="small" style={{ marginTop: 8 }}>
                <span className="muted">{bi("Model names recorded in the FDA trade-name field: ", "FDA 商品名字段记录的型号：")}</span>
                {data.family.models.slice(0, 18).join("; ")}
                {data.family.models.length > 18 ? " ..." : ""}
              </div>
            ) : null}
            <Banner tone="info" title={bi("This is not a commercial brand family", "这不是商业品牌家族")}>
              {data.disclosures.family_basis ?? ""}
            </Banner>
            <SectionHead
              title={bi("Versions of this device", "该器械的各版本")}
              note={bi(formatNumber(data.versions.length) + " supplement(s) ordered by decision date", formatNumber(data.versions.length) + " 个补充批准，按决定日期排序")}
            />
            <ApplicationTable rows={data.versions} emptyNote={bi("No supplement is recorded for this PMA in this snapshot.", "本快照中没有该 PMA 的补充批准记录。")} />
          </Card>
        ) : (
          <Callout>
            {bi(
              "No evidenced product family for this device. openFDA exposes no family or predicate identifier for 510(k) clearances, so MedRadar does not invent one.",
              "该器械没有有证据支持的产品家族。openFDA 不提供 510(k) 批准的产品家族或 predicate 标识，因此 MedRadar 不会凭空创建。",
            )}
          </Callout>
        )}

        <Card title={bi("Regulatory timeline", "监管时间线")} note={bi("Events with their official pages, event dates and first-observed dates.", "事件及其官方页面、事件日期与首次采集日期。")}>
          <DeviceTimeline items={data.timeline} />
        </Card>

        <Card
          title={bi("Relations and evidence", "关系与证据")}
          note={bi("Every confirmed relation names the official field that produced it. Candidates are hypotheses and are never presented as established.", "每条已确认关系都给出产生它的官方字段；候选关系只是假设，绝不作为已确认关系呈现。")}
        >
          <SectionHead title={bi("Confirmed relations", "已确认关系")} note={bi(formatNumber(confirmed.length) + " relation(s)", formatNumber(confirmed.length) + " 条")} />
          <RelationTable rows={confirmed} tone="confirmed" />
          <SectionHead title={bi("Candidate relations (not established)", "候选关系（尚未确认）")} note={bi(formatNumber(candidates.length) + " hypothesis/hypotheses", formatNumber(candidates.length) + " 条假设")} />
          {candidates.length ? <RelationTable rows={candidates} tone="candidate" /> : <div className="muted small">{bi("No candidate relation for this device.", "该器械没有候选关系。")}</div>}
        </Card>

        <Card
          title={bi("Related recalls (official reference only)", "相关召回（仅官方引用）")}
          note={data.related_recalls.note}
        >
          {data.related_recalls.confirmed.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">{bi("Recall", "召回")}</th>
                  <th scope="col">{bi("Initiated", "启动日期")}</th>
                  <th scope="col">{bi("Reason", "原因")}</th>
                  <th scope="col">{bi("Linked by", "关联依据")}</th>
                </tr>
              </thead>
              <tbody>
                {data.related_recalls.confirmed.map((recall) => (
                  <tr key={recall.event_id}>
                    <td className="small">
                      <a className="link" href={recall.official_url} target="_blank" rel="noreferrer">
                        {recall.official_id}
                      </a>
                      <div className="cell-sub">{(recall.product_description ?? "").slice(0, 90)}</div>
                    </td>
                    <td className="mono small">{formatDate(recall.initiated_date)}</td>
                    <td className="small">{(recall.reason_for_recall ?? "-").slice(0, 110)}</td>
                    <td className="small mono">{recall.k_numbers.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              title={bi("No recall references this application", "没有召回引用该申请")}
              description={bi(
                "A recall is attached here only when its official K-number field names this application. Recalls without that field are in the unlinked browser.",
                "只有当召回的官方 K 编号字段引用了该申请时才会挂接在这里。没有该字段的召回位于“未关联记录”浏览中。",
              )}
            />
          )}
          {data.related_recalls.candidate.length ? (
            <Banner tone="warning" title={bi("Candidate recall links (not confirmed)", "候选召回关联（未确认）")}>
              {bi(
                formatNumber(data.related_recalls.candidate.length) +
                  " recall(s) have no official K-number reference but share this application's product code and tracked group. They are listed as candidates and are not counted as related recalls.",
                formatNumber(data.related_recalls.candidate.length) +
                  " 条召回没有官方 K 编号引用，但与本次申请共享产品代码与所属集团。它们只是候选，不计入“相关召回”。",
              )}
            </Banner>
          ) : null}
        </Card>

        <Card title={bi("Official evidence", "官方证据")} note={bi("Every claim on this page links to the FDA record it came from.", "本页每个结论都链接到其来源的 FDA 记录。")}>
          <ul className="small">
            {data.evidence.map((item) => (
              <li key={item.official_url + item.label}>
                {item.label}:{" "}
                <a className="mono link" href={item.official_url} target="_blank" rel="noreferrer">
                  {item.official_id}
                </a>
              </li>
            ))}
          </ul>
          <Callout>
            {bi(
              "Predicate relations are not modelled: " + data.disclosures.predicate_relations,
              "未建模 predicate 关系：" + data.disclosures.predicate_relations,
            )}
          </Callout>
        </Card>
      </div>
    </>
  );
}
