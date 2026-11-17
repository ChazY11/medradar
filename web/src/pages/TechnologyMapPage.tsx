import { useEffect, useMemo, useState } from "react";
import { useAsync } from "../api/hooks";
import { useI18n } from "../i18n";
import {
  getCompare,
  getGraphChanges,
  getGraphNode,
  getTechnologyMap,
  type CompareResponse,
  type Confirmation,
  type GraphChanges,
  type GraphNodeDetail,
  type TechnologyBranch,
  type TechnologyMap,
  type TimeQuery,
} from "../api/radar";
import { AsyncSection } from "../components/async";
import {
  Badge,
  Banner,
  Callout,
  Card,
  EmptyState,
  KeyValue,
  PageHeader,
  Tabs,
  formatDate,
  formatDateTime,
} from "../components/ui";

const COMPANIES = ["philips", "ge_healthcare", "draeger"] as const;
const COMPANY_LABELS: Record<string, string> = {
  philips: "Philips",
  ge_healthcare: "GE HealthCare",
  draeger: "Dräger",
};

function toneFor(confirmation: Confirmation): "ok" | "warn" | "info" | "neutral" {
  if (confirmation === "CONFIRMED") return "ok";
  if (confirmation === "CANDIDATE") return "warn";
  if (confirmation === "TOPIC_RELATED") return "info";
  return "neutral";
}

function defaultEarlier(): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - 7);
  return date.toISOString().slice(0, 10);
}

export function TechnologyMapPage() {
  const { bi } = useI18n();
  const [tab, setTab] = useState("map");
  const [mode, setMode] = useState<TimeQuery["mode"]>("public");
  const [at, setAt] = useState<string>("");
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [node, setNode] = useState<{ nodeType: string; nodeId: string } | null>(null);
  // The company switcher is the primary navigation on a phone: one company at a time, instead
  // of scrolling a three-company comparison built for a desktop column.
  const [activeCompanies, setActiveCompanies] = useState<string[]>([...COMPANIES]);

  const companyQuery = useMemo(
    () => (activeCompanies.length ? activeCompanies.join(",") : COMPANIES.join(",")),
    [activeCompanies],
  );

  const timeQuery: TimeQuery = useMemo(
    () => (at ? { mode, at } : { mode }),
    [mode, at],
  );

  const map = useAsync(
    () => getTechnologyMap({ ...timeQuery, companies: companyQuery }),
    [mode, at, companyQuery],
  );
  const compare = useAsync(
    () => getCompare({ ...timeQuery, companies: companyQuery }),
    [mode, at, companyQuery],
  );
  const [earlier, setEarlier] = useState(defaultEarlier);
  // The diff view can answer with every assertion in the graph (megabytes on a busy ledger).
  // It is fetched only when its tab is opened, so a phone does not download it to look at the
  // technology tree.
  const changes = useAsync<GraphChanges | null>(
    () => (tab === "changes" ? getGraphChanges(`${earlier}T00:00:00Z`) : Promise.resolve(null)),
    [tab, earlier],
  );

  const branches: TechnologyBranch[] = map.data?.topics ?? [];

  return (
    <>
      <PageHeader
        eyebrow={bi("Company technology graph", "企业科技图谱")}
        title={bi("Company Technology Map", "企业科技地图")}
        description={bi(
          "Which technologies do Philips, GE HealthCare and Dräger have public evidence for? Every branch below is generated from the observation database with a citable evidence record. Nothing on this page is a static capability list.",
          "Philips、GE HealthCare、Dräger 有哪些技术拥有公开证据？以下每个分支都由观察数据库动态生成，并可追溯到证据记录。本页面没有任何静态能力清单。",
        )}
      />

      <div className="company-switcher" role="group" aria-label={bi("Company switcher", "企业切换")}>
        <span className="small muted">{bi("Companies", "企业")}</span>
        <button
          type="button"
          className="chip"
          aria-pressed={activeCompanies.length === COMPANIES.length}
          onClick={() => setActiveCompanies([...COMPANIES])}
        >
          {bi("All", "全部")}
        </button>
        {COMPANIES.map((company) => {
          const on = activeCompanies.includes(company);
          return (
            <button
              key={company}
              type="button"
              className="chip"
              aria-pressed={on && activeCompanies.length !== COMPANIES.length}
              onClick={() => {
                const next = on
                  ? activeCompanies.filter((item) => item !== company)
                  : [...activeCompanies, company];
                // Never leave the view empty: the last remaining company stays selected.
                setActiveCompanies(next.length ? next : [company]);
              }}
            >
              {COMPANY_LABELS[company]}
            </button>
          );
        })}
      </div>

      <Card
        title={bi("Observation time", "观察时间")}
        note={bi(
          "Two clocks, deliberately separate. 'Public time' reconstructs what was publicly true on a date from today's knowledge. 'Knowledge time' shows only what MedRadar had actually recorded by then.",
          "两个时钟刻意分离。『公开时间』基于今天的知识回溯某日公开为真的事实；『知识时间』只显示 MedRadar 当时已实际记录的断言。",
        )}
      >
        <div className="row wrap" style={{ gap: 14 }}>
          <Tabs
            items={[
              { id: "public", label: bi("Public time", "公开时间") },
              { id: "knowledge", label: bi("Knowledge time", "知识时间") },
            ]}
            active={mode}
            onChange={(next) => setMode(next as TimeQuery["mode"])}
          />
          <label className="small muted">
            {bi("As of", "截至")}
            <input
              type="date"
              className="input"
              value={at.slice(0, 10)}
              onChange={(event) => setAt(event.target.value ? `${event.target.value}T00:00:00Z` : "")}
            />
          </label>
          {at ? (
            <button type="button" className="btn sm" onClick={() => setAt("")}>
              {bi("Now", "现在")}
            </button>
          ) : null}
        </div>
        {map.data ? (
          <Banner tone={map.data.reconstructed ? "warning" : "info"} title={map.data.reconstructed ? bi("Reconstruction, not history", "这是回溯重建，不是当时已知") : bi("Knowledge-time view", "知识时间视图")}>
            {map.data.time_semantics.statement}
          </Banner>
        ) : null}
      </Card>

      <Tabs
        items={[
          { id: "map", label: bi("Technology tree", "科技树"), count: branches.length },
          { id: "compare", label: bi("Company comparison", "企业对比") },
          { id: "changes", label: bi("What changed", "变化") },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "map" ? (
        <AsyncSection status={map.status} data={map.data} error={map.error} reload={map.reload} loadingLines={8}>
          {(payload: TechnologyMap) => (
            <>
              <div className="row between wrap" style={{ gap: 8 }}>
                <span className="small muted">
                  {bi(
                    `${payload.counts.topics_with_evidence} topic branch(es) with evidence; ${payload.counts.nodes} nodes / ${payload.counts.edges} edges in this view.`,
                    `本视图中有 ${payload.counts.topics_with_evidence} 个技术分支含证据；共 ${payload.counts.nodes} 个节点 / ${payload.counts.edges} 条边。`,
                  )}
                </span>
              </div>

              {payload.topics.length === 0 ? (
                <EmptyState
                  title={bi("No technology branch has evidence in this view yet", "当前视图中尚无含证据的技术分支")}
                  description={bi(
                    "The graph is built from real observations. Run `python -m medradar radar run` and then `python -m medradar radar advance` to collect and link evidence. An empty tree is a statement about evidence, not about the companies.",
                    "图谱由真实观察构建。请运行 `python -m medradar radar run` 与 `python -m medradar radar advance` 采集并关联证据。空树是证据陈述，不代表企业没有该技术。",
                  )}
                />
              ) : (
                <div className="grid" style={{ gridTemplateColumns: "1fr", gap: 12 }}>
                  {payload.topics.map((branch) => (
                    <Card
                      key={branch.topic_id}
                      title={
                        <span>
                          {branch.label_en}
                          <span className="small muted" style={{ marginLeft: 8 }}>
                            {branch.family} · {branch.topic_id}
                          </span>
                        </span>
                      }
                      actions={
                        <button
                          type="button"
                          className="btn sm"
                          onClick={() => setSelectedTopic(selectedTopic === branch.topic_id ? null : branch.topic_id)}
                        >
                          {selectedTopic === branch.topic_id ? bi("Collapse", "收起") : bi("Evidence", "证据")}
                        </button>
                      }
                    >
                      {branch.description ? <div className="small muted">{branch.description}</div> : null}
                      <div className="grid cols-3" style={{ marginTop: 10 }}>
                        {branch.companies.map((company) => (
                          <div key={company.organization_id} className="state-block" style={{ margin: 0 }}>
                            <div className="row between">
                              <strong>{company.label_zh ?? company.display_name}</strong>
                              <span className="small muted">
                                {bi("earliest", "最早")} {company.earliest_evidence ? formatDate(company.earliest_evidence) : "—"}
                              </span>
                            </div>
                            <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                              {company.products.map((product) => (
                                <button
                                  key={product.product_id}
                                  type="button"
                                  className="chip"
                                  onClick={() => setNode({ nodeType: "product", nodeId: product.product_id })}
                                  title={product.evidence_id ?? product.product_id}
                                >
                                  {product.name ?? product.product_id}
                                  {product.capabilities.length ? (
                                    <span className="small muted" style={{ marginLeft: 6 }}>
                                      {product.capabilities.length} {bi("capability", "能力")}
                                    </span>
                                  ) : null}
                                </button>
                              ))}
                              {company.evidence.slice(0, 4).map((row) => (
                                <button
                                  key={`${row.record_node}-${row.evidence_id}`}
                                  type="button"
                                  className="chip"
                                  onClick={() =>
                                    setNode({ nodeType: row.record_type, nodeId: row.record_node.split(":").slice(1).join(":") })
                                  }
                                  title={row.title ?? row.record_node}
                                >
                                  <span className={`badge ${toneFor(row.confirmation)}`} style={{ marginRight: 6 }}>
                                    {row.confirmation}
                                  </span>
                                  {(row.title ?? row.record_node).slice(0, 46)}
                                </button>
                              ))}
                            </div>
                            {company.evidence.length > 4 ? (
                              <div className="small muted mt-8">
                                +{company.evidence.length - 4} {bi("more evidence rows", "条更多证据")}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>

                      {selectedTopic === branch.topic_id ? (
                        <div className="mt-8">
                          <div className="table-wrap">
                            <table className="data">
                              <thead>
                                <tr>
                                  <th>{bi("Evidence", "证据")}</th>
                                  <th>{bi("Confirmation", "确认等级")}</th>
                                  <th>{bi("Method", "方法")}</th>
                                  <th>{bi("Valid from", "适用起")}</th>
                                  <th>{bi("Recorded at", "记录时间")}</th>
                                  <th>{bi("Official source", "官方来源")}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {branch.companies.flatMap((company) =>
                                  company.evidence.map((row) => (
                                    <tr key={`${company.organization_id}-${row.record_node}-${row.evidence_id}`}>
                                      <td data-label={bi("Evidence", "证据")}>
                                        {company.display_name} · {(row.title ?? row.record_node).slice(0, 70)}
                                      </td>
                                      <td data-label={bi("Confirmation", "确认等级")}>
                                        <Badge tone={toneFor(row.confirmation)}>{row.confirmation}</Badge>
                                      </td>
                                      <td className="small" data-label={bi("Method", "方法")}>{row.method ?? "—"}</td>
                                      <td className="small" data-label={bi("Valid from", "适用起")}>{row.valid_from ? formatDate(row.valid_from) : "—"}</td>
                                      <td className="small" data-label={bi("Recorded at", "记录时间")}>{formatDateTime(row.recorded_at)}</td>
                                      <td className="small" data-label={bi("Official source", "官方来源")}>
                                        {row.source_url ? (
                                          <a href={row.source_url} target="_blank" rel="noreferrer noopener">
                                            {bi("open", "打开")}
                                          </a>
                                        ) : (
                                          "—"
                                        )}
                                      </td>
                                    </tr>
                                  )),
                                )}
                              </tbody>
                            </table>
                          </div>
                          <div className="small muted mt-8">{payload.time_semantics.cannot_do}</div>
                        </div>
                      ) : null}
                    </Card>
                  ))}
                </div>
              )}
            </>
          )}
        </AsyncSection>
      ) : null}

      {tab === "compare" ? (
        <AsyncSection status={compare.status} data={compare.data} error={compare.error} reload={compare.reload} loadingLines={8}>
          {(payload: CompareResponse) => (
            <>
              <Callout>{payload.no_evidence_means}</Callout>
              <Callout>{payload.not_comparable_warning}</Callout>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>{bi("Technology topic", "技术主题")}</th>
                      {(payload.rows[0]?.cells ?? []).map((cell) => (
                        <th key={cell.organization_id}>
                          {cell.label_zh ?? cell.display_name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {payload.rows.map((row) => (
                      <tr key={row.topic_id}>
                        <td data-label={bi("Technology topic", "技术主题")}>
                          <div>{bi(row.label_en, row.label_zh ?? row.label_en)}</div>
                          <div className="small muted">{row.topic_id}</div>
                        </td>
                        {row.cells.map((cell) => (
                          <td key={cell.organization_id} data-label={cell.label_zh ?? cell.display_name}>
                            {cell.state === "EVIDENCE_PRESENT" ? (
                              <div>
                                <Badge tone="ok">{bi("evidence present", "有证据")}</Badge>
                                <div className="small muted" style={{ marginTop: 6 }}>
                                  {bi("reported capability", "官方能力陈述")} {cell.reported_capability_evidence} ·{" "}
                                  {bi("regulatory", "监管记录")} {cell.regulatory_topic_evidence} ·{" "}
                                  {bi("publications", "论文")} {cell.publication_topic_evidence} ·{" "}
                                  {bi("official documents", "官方文档")} {cell.official_document_topic_evidence}
                                </div>
                              </div>
                            ) : (
                              <div>
                                <Badge tone="neutral">{bi("no evidence found", "未发现证据")}</Badge>
                                <div className="small muted" style={{ marginTop: 6 }}>
                                  {bi("not a claim that the technology is absent", "不代表该技术不存在")}
                                </div>
                              </div>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </AsyncSection>
      ) : null}

      {tab === "changes" ? (
        <Card
          title={bi("Technology branch changes", "技术分支变化")}
          note={bi(
            "A diff of graph assertions: what MedRadar learned between two knowledge times. 'Added' means the assertion was recorded in this window, not that the underlying event happened then.",
            "图谱断言的差异：MedRadar 在两个知识时间之间新学到什么。『新增』指该断言在此时段被记录，不代表底层事件发生在此时段。",
          )}
          actions={
            <label className="small muted">
              {bi("Earlier", "起点")}
              <input
                type="date"
                className="input"
                value={earlier}
                onChange={(event) => setEarlier(event.target.value || defaultEarlier())}
              />
            </label>
          }
        >
          <AsyncSection status={changes.status} data={changes.data} error={changes.error} reload={changes.reload} loadingLines={6}>
            {(payload: GraphChanges) => (
              <>
                <div className="row wrap" style={{ gap: 8 }}>
                  <Badge tone="ok">{bi("added", "新增")}: {payload.counts.added}</Badge>
                  <Badge tone="info">{bi("changed", "变更")}: {payload.counts.changed}</Badge>
                  <Badge tone="warn">{bi("removed", "移除")}: {payload.counts.removed}</Badge>
                </div>
                {payload.added.length + payload.changed.length + payload.removed.length === 0 ? (
                  <EmptyState
                    title={bi("No assertion was added or changed in this window", "此时段没有新增或变更的断言")}
                    description={bi(
                      "That is a real result: the monitored sources produced no new linked evidence. It is not an error.",
                      "这是一个真实结果：已监测来源没有产生新的关联证据。这不是错误。",
                    )}
                  />
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{bi("Change", "变化")}</th>
                          <th>{bi("Relation", "关系")}</th>
                          <th>{bi("Recorded at", "记录时间")}</th>
                          <th>{bi("Valid from", "适用起")}</th>
                          <th>{bi("Source", "来源")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {([
                          ["added", payload.added],
                          ["changed", payload.changed],
                          ["removed", payload.removed],
                        ] as const).flatMap(([kind, edges]) =>
                          edges.map((edge, index) => (
                            <tr key={`${kind}-${index}-${edge.edge_type}-${edge.src.node_id}-${edge.dst.node_id}`}>
                              <td>
                                <Badge tone={kind === "added" ? "ok" : kind === "changed" ? "info" : "warn"}>
                                  {kind}
                                </Badge>
                              </td>
                              <td className="small">
                                {edge.edge_type}
                                <div className="muted">
                                  {edge.src.node_id} → {edge.dst.node_id}
                                </div>
                              </td>
                              <td className="small">{formatDateTime(edge.recorded_at)}</td>
                              <td className="small">{edge.valid_from ? formatDate(edge.valid_from) : "—"}</td>
                              <td className="small">
                                {edge.source_url ? (
                                  <a href={edge.source_url} target="_blank" rel="noreferrer noopener">
                                    {edge.source ?? "source"}
                                  </a>
                                ) : (
                                  edge.source ?? "—"
                                )}
                              </td>
                            </tr>
                          )),
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="small muted mt-8">{payload.note}</div>
              </>
            )}
          </AsyncSection>
        </Card>
      ) : null}

      {node ? <NodeDrawer nodeType={node.nodeType} nodeId={node.nodeId} timeQuery={timeQuery} onClose={() => setNode(null)} /> : null}
    </>
  );
}

function NodeDrawer({
  nodeType,
  nodeId,
  timeQuery,
  onClose,
}: {
  nodeType: string;
  nodeId: string;
  timeQuery: TimeQuery;
  onClose: () => void;
}) {
  const { bi } = useI18n();
  const detail = useAsync(() => getGraphNode(nodeType, nodeId, timeQuery), [nodeType, nodeId, timeQuery.mode, timeQuery.at]);

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
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={bi("Graph evidence", "图谱证据")}>
        <div className="drawer-head">
          <div>
            <div className="eyebrow">{nodeType}</div>
            <div className="mono small" style={{ marginTop: 4 }}>{nodeId}</div>
          </div>
          <button type="button" className="btn sm" onClick={onClose}>Esc</button>
        </div>
        <div className="drawer-body">
          <AsyncSection status={detail.status} data={detail.data} error={detail.error} reload={detail.reload} loadingLines={8}>
            {(payload: GraphNodeDetail) => (
              <>
                <div className="drawer-section">
                  <KeyValue
                    rows={[
                      { label: bi("Node type", "节点类型"), value: payload.node_type },
                      { label: bi("Earliest evidence", "最早证据"), value: payload.earliest_evidence ? formatDate(payload.earliest_evidence) : "—" },
                      { label: bi("Latest change", "最近变化"), value: payload.latest_change ? formatDateTime(payload.latest_change) : "—" },
                      { label: bi("View mode", "视图模式"), value: payload.mode },
                    ]}
                  />
                  <div className="small muted mt-8">{payload.time_semantics.statement}</div>
                </div>
                {([["incoming", payload.incoming], ["outgoing", payload.outgoing]] as const).map(([kind, edges]) => (
                  <div className="drawer-section" key={kind}>
                    <h3>{kind === "incoming" ? bi("Incoming relations", "指向该节点的关系") : bi("Outgoing relations", "该节点指出的关系")}</h3>
                    {edges.length === 0 ? (
                      <div className="small muted">{bi("No relation in this view.", "本视图中没有关系。")}</div>
                    ) : (
                      <ul className="small">
                        {edges.map((edge, index) => (
                          <li key={`${kind}-${index}`} style={{ marginBottom: 8 }}>
                            <Badge tone={toneFor(edge.confirmation)}>{edge.confirmation}</Badge>{" "}
                            <span className="mono small">{edge.edge_type}</span>
                            <div className="muted">
                              {edge.src.node_id} → {edge.dst.node_id}
                            </div>
                            <div className="muted">
                              {bi("valid from", "适用起")} {edge.valid_from ? formatDate(edge.valid_from) : "—"} ·{" "}
                              {bi("recorded", "记录")} {formatDateTime(edge.recorded_at)} · {edge.method ?? "—"}
                              {edge.matched_terms?.length ? ` · ${edge.matched_terms.join(", ")}` : ""}
                            </div>
                            {edge.source_url ? (
                              <a href={edge.source_url} target="_blank" rel="noreferrer noopener">
                                {bi("open evidence", "打开证据")}
                              </a>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </>
            )}
          </AsyncSection>
        </div>
      </aside>
    </>
  );
}
