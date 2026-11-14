import { useMemo } from "react";
import { Link } from "react-router-dom";
import { getAttribution, getCoverage, getMeta } from "../api/client";
import { useAsync } from "../api/hooks";
import { AsyncSection } from "../components/async";
import { Badge, Banner, Callout, Card, EmptyState, FreshnessBadge, Grid, MetricTile, PageHeader, SectionHead, formatDate, formatDateTime } from "../components/ui";
import { useI18n } from "../i18n";

export function SourcesPage() {
  const { t, bi } = useI18n();
  const coverage = useAsync(() => getCoverage(), []);
  const attribution = useAsync(() => getAttribution(), []);
  const meta = useAsync(() => getMeta(), []);

  const orgAudit = useMemo(() => {
    const audit = coverage.data?.collection_audit;
    if (!audit) return [];
    const byOrg = new Map<string, { org_key: string; pages: number; records: number; endpoints: Set<string>; urls: string[] }>();
    for (const token of audit.tokens) {
      const bucket = byOrg.get(token.org_key) ?? { org_key: token.org_key, pages: 0, records: 0, endpoints: new Set<string>(), urls: [] };
      bucket.pages += token.pages;
      bucket.records += token.records_retrieved;
      bucket.endpoints.add(token.endpoint);
      if (token.urls.length) bucket.urls.push(token.urls[0]);
      byOrg.set(token.org_key, bucket);
    }
    return [...byOrg.values()].sort((a, b) => b.records - a.records);
  }, [coverage.data]);

  return (
    <>
      <PageHeader
        eyebrow={bi("Trust and method", "可信度与方法")}
        title={t("sources.title")}
        description={t("sources.desc")}
        actions={
          meta.data ? <FreshnessBadge state={meta.data.freshness.state} ageDays={meta.data.freshness.age_days} threshold={meta.data.freshness.threshold_days} /> : null
        }
      />

      <div className="stack">
        {coverage.status === "error" && coverage.error ? (
          <Card>
            <EmptyState title={bi("Coverage unavailable", "覆盖信息不可用")} description={coverage.error.message} actions={<button className="btn" onClick={coverage.reload}>{t("state.retry")}</button>} />
          </Card>
        ) : null}

        <AsyncSection status={coverage.status} data={coverage.data} error={coverage.error} reload={coverage.reload} loadingLines={10}>
          {(data) => (
            <>
              <Grid cols={5}>
                <MetricTile label={t("common.records")} value={(data.manifest.counts.records ?? 0).toLocaleString()} sub={bi("collected from openFDA", "采集自 openFDA")} accent />
                <MetricTile label={bi("Attributed", "已归属")} value={((data.manifest.counts.records ?? 0) - data.attribution_summary.unattributed_records).toLocaleString()} sub={bi(data.attribution_summary.unattributed_records + " unattributed records", data.attribution_summary.unattributed_records + " 条未归属记录")} />
                <MetricTile label={bi("Organizations", "企业")} value={data.manifest.organization_count ?? 0} sub={bi("tracked with a reviewed identity entry", "均有身份登记与归属规则")} />
                <MetricTile label={bi("API requests", "API 请求")} value={(data.manifest.request_count ?? 0).toLocaleString()} sub={bi("every URL recorded in the manifest", "所有 URL 均记录在清单中")} />
                <MetricTile label={bi("Product codes", "产品代码")} value={(data.manifest.counts.product_codes ?? 0).toLocaleString()} sub={bi("FDA classification dictionary", "FDA 分类字典")} />
              </Grid>

              <Card
                title={bi("Snapshot manifest", "快照清单")}
                note={bi("The snapshot is immutable. Re-running the collector produces a new snapshot with new hashes; nothing is edited in place.", "快照不可变。重新运行采集会生成带新哈希的新快照，不会原地修改。")}
              >
                <div className="grid cols-2">
                  <div>
                    <dl className="kv">
                      <dt>{bi("Snapshot id", "快照 ID")}</dt>
                      <dd className="mono small">{data.manifest.id}</dd>
                      <dt>{bi("Collected at", "采集时间")}</dt>
                      <dd className="mono small">{data.manifest.collected_at}</dd>
                      <dt>{bi("Collection started", "采集开始")}</dt>
                      <dd className="mono small">{data.manifest.collection_started_at ?? "-"}</dd>
                      <dt>{bi("openFDA last updated", "openFDA 最后更新")}</dt>
                      <dd className="mono small">{data.manifest.openfda_last_updated ?? "-"}</dd>
                      <dt>{bi("Response bytes", "响应字节")}</dt>
                      <dd className="mono small">{(data.manifest.response_bytes ?? 0).toLocaleString()}</dd>
                      <dt>{bi("Collection errors", "采集错误")}</dt>
                      <dd>{data.manifest.errors.length ? <Badge tone="danger">{data.manifest.errors.length}</Badge> : <Badge tone="ok">{bi("none", "无")}</Badge>}</dd>
                      <dt>{bi("Implausible dates quarantined", "剔除的不合理日期")}</dt>
                      <dd>{data.manifest.data_quality.implausible_event_date ?? 0}</dd>
                    </dl>
                  </div>
                  <div>
                    <div className="card-note mb-8">{bi("Data files and content hashes", "数据文件与内容哈希")}</div>
                    <div className="table-wrap">
                      <table className="data">
                        <thead>
                          <tr>
                            <th scope="col">{bi("File", "文件")}</th>
                            <th scope="col" className="num">{bi("Records", "记录")}</th>
                            <th scope="col">{bi("SHA-256", "SHA-256")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.manifest.files.map((file) => (
                            <tr key={file.name}>
                              <td className="mono small">{file.name}</td>
                              <td className="num">{(file.records ?? 0).toLocaleString()}</td>
                              <td className="mono tiny truncate" title={file.sha256 ?? ""}>
                                {(file.sha256 ?? "").slice(0, 16)}...
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
                {data.manifest.notes.length ? (
                  <div className="mt-12">
                    {data.manifest.notes.map((note, index) => (
                      <div key={index} className="small muted" style={{ lineHeight: 1.6 }}>
                        - {note}
                      </div>
                    ))}
                  </div>
                ) : null}
              </Card>

              <Card title={bi("Sources of record", "数据来源")} note={bi("Only these sources are collected. Anything else is out of scope and shown as such, never as zero.", "仅采集以下来源；其他内容不在范围内，并会明确标注，而不是显示为 0。")} flush>
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th scope="col">{t("common.source")}</th>
                        <th scope="col">{bi("Endpoint", "接口")}</th>
                        <th scope="col" className="num">{t("common.records")}</th>
                        <th scope="col">{bi("Event dates", "事件日期")}</th>
                        <th scope="col">{bi("Licence", "许可")}</th>
                        <th scope="col">{bi("Official record", "官方记录")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.sources.map((source) => (
                        <tr key={source.source_id}>
                          <td>
                            <div className="cell-primary">{source.name}</div>
                            <div className="cell-sub mono">{source.source_id}</div>
                            <div className="cell-sub">{source.note}</div>
                          </td>
                          <td className="mono tiny">{source.endpoints.join(" ; ")}</td>
                          <td className="num">{(source.records ?? 0).toLocaleString()}</td>
                          <td className="small muted nowrap">
                            {formatDate(source.min_event_date)} {"\u2192"} {formatDate(source.max_event_date)}
                          </td>
                          <td className="small">{source.licence}</td>
                          <td className="small">
                            <a className="link mono tiny" href={source.official_base_url} target="_blank" rel="noopener noreferrer">
                              accessdata.fda.gov
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              <Card
                title={bi("Collection audit", "采集审计")}
                note={bi("What was queried, how much came back, and what could not be attributed. This is the evidence that the coverage statement is honest.", "查询了什么、返回多少、哪些无法归属。这是覆盖范围说明可信的证据。")}
              >
                <SectionHead
                  title={bi("Query scope per organization", "各企业的检索范围")}
                  note={bi(orgAudit.length + " organizations, " + data.collection_audit.tokens.reduce((sum, token) => sum + token.pages, 0) + " pages", orgAudit.length + " 家企业，" + data.collection_audit.tokens.reduce((sum, token) => sum + token.pages, 0) + " 页")}
                />
                <div className="table-wrap" style={{ maxHeight: 360, overflow: "auto" }}>
                  <table className="data">
                    <thead>
                      <tr>
                        <th scope="col">{t("common.organization")}</th>
                        <th scope="col" className="num">{bi("Pages", "页数")}</th>
                        <th scope="col" className="num">{bi("Records retrieved", "检索记录数")}</th>
                        <th scope="col">{bi("Endpoints", "接口")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orgAudit.map((row) => (
                        <tr key={row.org_key}>
                          <td className="cell-primary">{row.org_key}</td>
                          <td className="num">{row.pages}</td>
                          <td className="num">{row.records.toLocaleString()}</td>
                          <td className="small muted">{[...row.endpoints].join(", ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="divider" />
                <SectionHead
                  title={bi("Attribution review state", "归属复核状态")}
                  note={bi("Exact-string decisions only. Pending-review spellings were proposed by MedRadar from observed FDA spellings and are labelled provisional in the UI.", "仅使用精确字符串决策；待复核写法由 MedRadar 基于观察到的 FDA 写法提出，界面中标注为暂定。")}
                />
                <Grid cols={4}>
                  <MetricTile label={bi("Curated spellings", "已复核写法")} value={data.attribution_summary.curated_spellings} sub={bi("from the reviewed roster", "来自已复核名单")} />
                  <MetricTile label={bi("Pending review", "待复核写法")} value={data.attribution_summary.pending_review_spellings} sub={bi("proposed from observed spellings", "基于观察到的写法提出")} />
                  <MetricTile label={bi("Rejected similar names", "已排除近似名称")} value={data.attribution_summary.rejected_spellings} sub={bi("explicitly excluded", "明确排除")} />
                  <MetricTile label={bi("Unattributed records", "未归属记录")} value={data.attribution_summary.unattributed_records.toLocaleString()} sub={bi("never counted as company activity", "不计入任何企业活动")} />
                </Grid>

                {data.collection_audit.unattributed.length ? (
                  <>
                    <div className="divider" />
                    <SectionHead title={bi("Applicant strings not attributed", "未归属的申请人名称")} note={bi("Top strings by record count. They are not companies in this product; they are a coverage gap to review.", "按记录数排序的前若干项。它们在本产品中不是企业实体，而是待复核的覆盖缺口。")} />
                    <div className="table-wrap" style={{ maxHeight: 300, overflow: "auto" }}>
                      <table className="data">
                        <thead>
                          <tr>
                            <th scope="col">{bi("Applicant string (verbatim)", "申请人名称（原始）")}</th>
                            <th scope="col" className="num">{t("common.records")}</th>
                            <th scope="col">{bi("Endpoints", "接口")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.collection_audit.unattributed.slice(0, 40).map((row) => (
                            <tr key={row.applicant_name}>
                              <td className="mono small">{row.applicant_name}</td>
                              <td className="num">{row.records.toLocaleString()}</td>
                              <td className="small muted">{row.endpoints.join(", ")}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <div className="empty-inline">{bi("Every retrieved applicant string was attributed by the reviewed registry.", "所有检索到的申请人名称均已按复核登记表归属。")}</div>
                )}

                {data.collection_audit.rejected.length ? (
                  <>
                    <div className="divider" />
                    <SectionHead title={bi("Explicitly rejected strings", "明确排除的名称")} note={bi("These look similar but belong to a different business; their records are never counted.", "这些名称看似相近但属于不同业务，其记录不会被计入。")} />
                    <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
                      {data.collection_audit.rejected.map((row) => (
                        <li key={row.applicant_name + row.org_key}>
                          <span className="mono">{row.applicant_name}</span> {"->"} {row.org_key}: {row.reason}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </Card>

              <div className="grid cols-2">
                <Card title={bi("Four times, not one date", "四类时间，而非单一日期")} note={bi("Every record exposes these fields separately; the product never invents the time an event became public.", "每条记录分别提供这些字段；产品不会凭空推断事件公开时间。")}>
                  <div className="stack" style={{ gap: 10 }}>
                    {data.time_semantics.map((item) => (
                      <div key={item.field}>
                        <div className="mono small strong">{item.field}</div>
                        <div className="small muted" style={{ lineHeight: 1.55 }}>
                          {item.meaning}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
                <Card title={bi("Not covered in this release", "本版本未覆盖")} note={bi("Shown as out of scope, never as zero activity.", "明确标注为不在范围内，而不是显示为 0。")}>
                  <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
                    {data.out_of_scope.map((item) => (
                      <li key={item.item}>
                        <span className="strong">{item.item}</span> - {item.reason}
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>

              <Card title={bi("Known limitations", "已知限制")} note={bi("These are properties of the data and the method, not bugs to be hidden.", "这些是数据与方法本身的性质，不是需要隐藏的缺陷。")}>
                <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
                  {data.limitations.map((limitation, index) => (
                    <li key={index}>{limitation}</li>
                  ))}
                </ul>
              </Card>

              <Card title={bi("Reproduce this", "复现方式")} note={bi("A new developer can rebuild the same product from the same public sources.", "新开发者可用相同的公开来源重建同一产品。")}>
                <div className="table-wrap">
                  <table className="raw-table">
                    <tbody>
                      <tr>
                        <td>collect</td>
                        <td className="mono small">{data.reproduce.collect}</td>
                      </tr>
                      <tr>
                        <td>curate</td>
                        <td className="mono small">{data.reproduce.curate}</td>
                      </tr>
                      <tr>
                        <td>serve</td>
                        <td className="mono small">{data.reproduce.serve}</td>
                      </tr>
                      <tr>
                        <td>test</td>
                        <td className="mono small">{data.reproduce.test}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div className="mt-12">
                  <Callout>
                    {bi(
                      "Prerequisite: Python 3.10+ with fastapi and uvicorn (pip install -e '.[product]'). The committed snapshot in data/product/ lets the product run offline without re-collecting.",
                      "前提：Python 3.10+，并安装 fastapi 与 uvicorn（pip install -e '.[product]'）。仓库中已提交的 data/product/ 快照可让产品离线运行，无需重新采集。",
                    )}
                  </Callout>
                </div>
              </Card>

              <AsyncSection status={attribution.status} data={attribution.data} error={attribution.error} reload={attribution.reload} loadingLines={6}>
                {(payload) => (
                  <Card title={bi("Attribution policy and unmatched strings", "归属规则与未匹配名称")} note={bi("The complete list behind the attribution numbers, for review.", "归属数字背后的完整名单，供复核。")}>
                    <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
                      {payload.policy.map((line, index) => (
                        <li key={index}>{line}</li>
                      ))}
                    </ul>
                    <div className="divider" />
                    <div className="row wrap" style={{ gap: 16 }}>
                      <div>
                        <div className="metric-label">{bi("Decisions", "归属决策")}</div>
                        <div className="metric-value sm">{payload.decisions.length.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="metric-label">{bi("Rejected", "已排除")}</div>
                        <div className="metric-value sm">{payload.rejected.length.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="metric-label">{bi("Unmatched strings", "未匹配名称")}</div>
                        <div className="metric-value sm">{payload.unmatched.length.toLocaleString()}</div>
                      </div>
                    </div>
                    {payload.unmatched.length ? (
                      <div className="table-wrap mt-12" style={{ maxHeight: 260, overflow: "auto" }}>
                        <table className="data">
                          <thead>
                            <tr>
                              <th scope="col">{bi("Applicant string", "申请人名称")}</th>
                              <th scope="col" className="num">{t("common.records")}</th>
                              <th scope="col">{bi("Seen with tokens", "关联检索词")}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {payload.unmatched.slice(0, 30).map((row) => (
                              <tr key={row.applicant_name}>
                                <td className="mono small">{row.applicant_name}</td>
                                <td className="num">{row.records.toLocaleString()}</td>
                                <td className="small muted">{row.seen_with_tokens.join(", ")}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                  </Card>
                )}
              </AsyncSection>

              <Banner tone="neutral" title={bi("What this snapshot cannot tell you", "本快照无法回答的问题")}>
                {bi(
                  "It cannot tell you whether a company is innovative, how much market share it has, or what happened outside FDA device records. It can tell you which FDA records are attributed to a company, when they happened, and where the official record is.",
                  "无法判断某企业是否更具创新性、市场份额多少，或 FDA 器械记录之外发生了什么。它可以说明：哪些 FDA 记录归属该企业、事件何时发生、官方记录在哪里。",
                )}
              </Banner>

              <div className="small muted">
                {bi("Snapshot", "快照")} <span className="mono">{data.manifest.id}</span> - {bi("collected", "采集于")} {formatDateTime(data.manifest.collected_at)} -{" "}
                <Link className="link" to="/">
                  {t("nav.overview")}
                </Link>
              </div>
            </>
          )}
        </AsyncSection>
      </div>
    </>
  );
}
