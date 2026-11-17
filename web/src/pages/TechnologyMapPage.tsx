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
  type GraphEvidenceRow,
  type GraphNodeDetail,
  type GraphProduct,
  type TechnologyBranch,
  type TechnologyMap,
  type TimeQuery,
} from "../api/radar";
import { AsyncSection } from "../components/async";
import { cleanTitle } from "../lib/text";
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
  // Exclusive company selection: tapping Dräger shows Dräger. The previous toggle-off behaviour
  // meant tapping a company hid it, which on a phone reads as "the filter is broken".
  const [activeCompany, setActiveCompany] = useState<string | null>(null);

  const companyQuery = useMemo(
    () => (activeCompany ? activeCompany : COMPANIES.join(",")),
    [activeCompany],
  );

  const timeQuery: TimeQuery = useMemo(
    () => (at ? { mode, at } : { mode }),
    [mode, at],
  );

  // Only the open tab fetches. Loading all three views on mount made a phone request three
  // heavy graph projections to show one, which is how a 3 s first paint became 10 s timeouts.
  const map = useAsync<TechnologyMap | null>(
    () => (tab === "map" ? getTechnologyMap({ ...timeQuery, companies: companyQuery }) : Promise.resolve(null)),
    [tab, mode, at, companyQuery],
  );
  const compare = useAsync<CompareResponse | null>(
    () => (tab === "compare" ? getCompare({ ...timeQuery, companies: companyQuery }) : Promise.resolve(null)),
    [tab, mode, at, companyQuery],
  );
  const [earlier, setEarlier] = useState(defaultEarlier);
  const [pager, setPager] = useState<{ topicId: string; orgId: string; kind: "evidence" | "products" } | null>(null);

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
          aria-pressed={activeCompany === null}
          onClick={() => setActiveCompany(null)}
        >
          {bi("All", "全部")}
        </button>
        {COMPANIES.map((company) => (
          <button
            key={company}
            type="button"
            className="chip"
            aria-pressed={activeCompany === company}
            onClick={() => setActiveCompany(company)}
          >
            {COMPANY_LABELS[company]}
          </button>
        ))}
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
            {bi(
              map.data.time_semantics.statement,
              "本视图仅包含截至所选时间点 MedRadar 已实际记录的断言；之后发现的证据不会出现在更早的视图里。",
            )}
          </Banner>
        ) : null}
      </Card>

      <Tabs
        items={[
          { id: "map", label: bi("Technology tree", "科技树"), count: map.status === "ready" ? branches.length : undefined },
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
                          {bi(branch.label_en, branch.label_zh ?? branch.label_en)}
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
                            <div className="small muted" style={{ marginTop: 4 }}>
                              {bi("Official capability", "官方能力")} {company.reported_capabilities_total} ·{" "}
                              {bi("Regulatory topic evidence", "监管主题证据")} {company.regulatory_evidence_total} ·{" "}
                              {bi("Research evidence", "科研证据")} {company.publication_evidence_total}
                            </div>
                            <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                              {company.products.map((product) => {
                                const caps = product.reported_capabilities.length;
                                return (
                                  <button
                                    key={product.product_id}
                                    type="button"
                                    className="chip"
                                    onClick={() => setNode({ nodeType: "product", nodeId: product.product_id })}
                                    title={product.evidence_id ?? product.product_id}
                                  >
                                    {product.name ?? product.product_id}
                                    {caps ? (
                                      <span className="badge confirmed" style={{ marginLeft: 6 }}>
                                        {caps} {bi("official capability", "官方能力")}
                                      </span>
                                    ) : (
                                      <span className="badge topic" style={{ marginLeft: 6 }}>
                                        {bi("filed device", "注册设备")}
                                      </span>
                                    )}
                                  </button>
                                );
                              })}
                              {company.products_total > company.products.length ? (
                                <button
                                  type="button"
                                  className="btn sm touch"
                                  onClick={() => setPager({ topicId: branch.topic_id, orgId: company.organization_id, kind: "products" })}
                                >
                                  {bi(`All ${company.products_total} products`, `全部 ${company.products_total} 个产品`)}
                                </button>
                              ) : null}
                              {company.evidence.slice(0, 4).map((row) => (
                                <button
                                  key={`${row.record_node}-${row.evidence_id}`}
                                  type="button"
                                  className="chip"
                                  onClick={() =>
                                    setNode({ nodeType: row.record_node_type, nodeId: row.record_node_id })
                                  }
                                  title={row.title ?? row.record_node}
                                >
                                  <span className={`badge ${toneFor(row.confirmation)}`} style={{ marginRight: 6 }}>
                                    {row.confirmation}
                                  </span>
                                  {cleanTitle(row.title ?? row.record_node).slice(0, 46)}
                                </button>
                              ))}
                            </div>
                            {company.evidence_total > 0 ? (
                              <div className="row wrap mt-8" style={{ gap: 8 }}>
                                <span className="small muted">
                                  {bi(
                                    `loaded ${company.evidence.length} of ${company.evidence_total} evidence rows`,
                                    `已加载 ${company.evidence.length} / ${company.evidence_total} 条证据`,
                                  )}
                                </span>
                                <button
                                  type="button"
                                  className="btn sm touch"
                                  onClick={() => setPager({ topicId: branch.topic_id, orgId: company.organization_id, kind: "evidence" })}
                                >
                                  {bi("Browse all evidence", "查看全部证据")}
                                </button>
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
                                        {company.display_name} · {cleanTitle(row.title ?? row.record_node).slice(0, 70)}
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
                          <div className="small muted mt-8">
                            {bi(
                              payload.time_semantics.cannot_do,
                              "已经记录的断言不会被回填到更早的知识时间：如果 MedRadar 在 2026 年才发现 2016 年的批文，它只会出现在 2026 年的知识视图中。",
                            )}
                          </div>
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
          <PagedChanges earlier={`${earlier}T00:00:00Z`} />
        </Card>
      ) : null}

      {pager ? (
        <BranchPager
          topicId={pager.topicId}
          orgId={pager.orgId}
          kind={pager.kind}
          timeQuery={timeQuery}
          onClose={() => setPager(null)}
          onOpenNode={(nodeType, nodeId) => {
            setPager(null);
            setNode({ nodeType, nodeId });
          }}
        />
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

/** Walk one branch's evidence or product list to its end. */
function BranchPager({
  topicId,
  orgId,
  kind,
  timeQuery,
  onClose,
  onOpenNode,
}: {
  topicId: string;
  orgId: string;
  kind: "evidence" | "products";
  timeQuery: TimeQuery;
  onClose: () => void;
  onOpenNode: (nodeType: string, nodeId: string) => void;
}) {
  const { bi } = useI18n();
  const PAGE = 25;
  const [items, setItems] = useState<(GraphEvidenceRow | GraphProduct)[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (nextOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      const payload = await getTechnologyMap({
        ...timeQuery,
        companies: orgId,
        topic_id: topicId,
        max_evidence: kind === "evidence" ? PAGE : 1,
        max_products: kind === "products" ? PAGE : 1,
        evidence_offset: kind === "evidence" ? nextOffset : 0,
        product_offset: kind === "products" ? nextOffset : 0,
      });
      const branch = payload.topics?.[0]?.companies.find((company) => company.organization_id === orgId);
      const page: (GraphEvidenceRow | GraphProduct)[] = kind === "evidence"
        ? branch?.evidence ?? []
        : branch?.products ?? [];
      const pageTotal = kind === "evidence" ? branch?.evidence_total ?? 0 : branch?.products_total ?? 0;
      setTotal(pageTotal);
      setItems((previous) => (nextOffset === 0 ? page : [...previous, ...page]));
      setOffset(nextOffset + page.length);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId, orgId, kind, timeQuery.mode, timeQuery.at]);

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
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={bi("Branch evidence", "分支证据")}>
        <div className="drawer-head">
          <div>
            <div className="eyebrow">{kind === "evidence" ? bi("Evidence", "证据") : bi("Products", "产品")}</div>
            <div className="small" style={{ marginTop: 4 }}>{topicId} · {COMPANY_LABELS[orgId] ?? orgId}</div>
          </div>
          <button type="button" className="btn sm touch" onClick={onClose}>Esc</button>
        </div>
        <div className="drawer-body">
          <div className="small muted" style={{ marginBottom: 8 }}>
            {bi(`loaded ${items.length} of ${total}`, `已加载 ${items.length} / ${total}`)}
          </div>
          {error ? (
            <div className="row wrap" style={{ gap: 8 }}>
              <Badge tone="danger">{error}</Badge>
              <button type="button" className="btn sm touch" onClick={() => void load(offset)}>
                {bi("Retry", "重试")}
              </button>
            </div>
          ) : null}
          <div className="grid" style={{ gridTemplateColumns: "1fr", gap: 8 }}>
            {kind === "evidence"
              ? (items as GraphEvidenceRow[]).map((row) => (
                  <div key={`${row.evidence_id}-${row.record_node_id}`} className="state-block" style={{ margin: 0 }}>
                    <div className="row wrap" style={{ gap: 6 }}>
                      <Badge tone={toneFor(row.confirmation)}>{row.confirmation}</Badge>
                      <Badge tone="neutral">{row.record_type}</Badge>
                      <span className="small muted">{row.valid_from ? formatDate(row.valid_from) : "—"}</span>
                    </div>
                    <div style={{ marginTop: 6 }}>{cleanTitle(row.title ?? row.record_node_id)}</div>
                    <div className="row wrap" style={{ gap: 8, marginTop: 6 }}>
                      <button
                        type="button"
                        className="btn sm touch"
                        onClick={() => onOpenNode(row.record_node_type, row.record_node_id)}
                      >
                        {bi("Open evidence", "查看证据")}
                      </button>
                      {row.source_url ? (
                        <a href={row.source_url} target="_blank" rel="noreferrer noopener" className="small">
                          {bi("Official source", "官方来源")}
                        </a>
                      ) : null}
                    </div>
                  </div>
                ))
              : (items as GraphProduct[]).map((product) => (
                  <div key={product.product_id} className="row between wrap" style={{ gap: 8 }}>
                    <span>{product.name ?? product.product_id}</span>
                    <span className="row wrap" style={{ gap: 6 }}>
                      {product.reported_capabilities.length ? (
                        <Badge tone="ok">
                          {product.reported_capabilities.length} {bi("official capability", "官方能力")}
                        </Badge>
                      ) : (
                        <Badge tone="info">{bi("filed device", "注册设备")}</Badge>
                      )}
                      <button
                        type="button"
                        className="btn sm touch"
                        onClick={() => onOpenNode("product", product.product_id)}
                      >
                        {bi("Open", "打开")}
                      </button>
                    </span>
                  </div>
                ))}
          </div>
          {loading ? <div className="small muted">{bi("Loading…", "加载中…")}</div> : null}
          {!loading && items.length < total ? (
            <button type="button" className="btn sm touch" onClick={() => void load(offset)}>
              {bi(`Load next ${PAGE}`, `继续加载 ${PAGE} 条`)}
            </button>
          ) : null}
          {!loading && items.length >= total ? (
            <div className="small muted">{bi("End of this branch.", "已到该分支末尾。")}</div>
          ) : null}
        </div>
      </aside>
    </>
  );
}

/** The assertion diff, paged to the end instead of a silent 300-row cap. */
function PagedChanges({ earlier }: { earlier: string }) {
  const { bi } = useI18n();
  const PAGE = 300;
  const [payload, setPayload] = useState<GraphChanges | null>(null);
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<{ kind: "added" | "changed" | "removed"; edge: GraphChanges["added"][number] }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (nextOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      const page = await getGraphChanges(earlier, undefined, nextOffset, PAGE);
      setPayload(page);
      const appended = [
        ...page.added.map((edge) => ({ kind: "added" as const, edge })),
        ...page.changed.map((edge) => ({ kind: "changed" as const, edge })),
        ...page.removed.map((edge) => ({ kind: "removed" as const, edge })),
      ];
      setRows((previous) => (nextOffset === 0 ? appended : [...previous, ...appended]));
      setOffset(nextOffset + PAGE);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [earlier]);

  const maxRows = payload
    ? Math.max(payload.counts.added, payload.counts.changed, payload.counts.removed)
    : 0;
  return (
    <>
      {payload ? (
        <div className="row wrap" style={{ gap: 8 }}>
          <Badge tone="ok">{bi("added", "新增")}: {payload.counts.added}</Badge>
          <Badge tone="info">{bi("changed", "变更")}: {payload.counts.changed}</Badge>
          <Badge tone="warn">{bi("removed", "移除")}: {payload.counts.removed}</Badge>
          <span className="small muted">
            {bi(`listed ${rows.length} of up to ${maxRows} per kind`, `已列出 ${rows.length} 条（每类最多 ${maxRows} 条）`)}
          </span>
        </div>
      ) : null}
      {error ? (
        <div className="row wrap" style={{ gap: 8 }}>
          <Badge tone="danger">{error}</Badge>
          <button type="button" className="btn sm touch" onClick={() => void load(offset)}>
            {bi("Retry", "重试")}
          </button>
        </div>
      ) : null}
      {rows.length === 0 && !loading ? (
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
              {rows.map(({ kind, edge }, index) => (
                <tr key={`${kind}-${index}-${edge.edge_type}-${edge.src.node_id}-${edge.dst.node_id}`}>
                  <td>
                    <Badge tone={kind === "added" ? "ok" : kind === "changed" ? "info" : "warn"}>{kind}</Badge>
                  </td>
                  <td className="small">
                    {edge.edge_type}
                    <div className="muted">{edge.src.node_id} → {edge.dst.node_id}</div>
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
              ))}
            </tbody>
          </table>
        </div>
      )}
      {loading ? <div className="small muted">{bi("Loading…", "加载中…")}</div> : null}
      {!loading && payload?.has_more ? (
        <button type="button" className="btn sm touch" onClick={() => void load(offset)}>
          {bi(`Load more (${rows.length} listed)`, `继续加载（已列出 ${rows.length} 条）`)}
        </button>
      ) : null}
      {payload ? <div className="small muted mt-8">{payload.note}</div> : null}
    </>
  );
}
