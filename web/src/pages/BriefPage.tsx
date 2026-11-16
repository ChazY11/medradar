import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  briefEvidenceUrl,
  briefMdUrl,
  getBrief,
  listOrganizations,
  type BriefQuery,
} from "../api/client";
import { useAsync } from "../api/hooks";
import type {
  Brief,
  BriefFinding,
  BriefRecordRef,
  CompareBrief,
  CompanyBrief,
  DeviceBrief,
  EventType,
} from "../api/types";
import { AsyncSection } from "../components/async";
import { BarBreakdown, YearSeries } from "../components/charts";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { ExplainDrawer } from "../components/ExplainDrawer";
import {
  Badge,
  Banner,
  Card,
  EmptyState,
  EventTypeBadge,
  MetricTile,
  PageHeader,
  SectionHead,
} from "../components/ui";
import { useI18n } from "../i18n";
import { fmtDate, fmtNumber, fmtPercent, fmtWindow, localisePathwayLabel, pickText, typeLabel, type Lang } from "../lib/brief";

const EVENT_TYPES: EventType[] = ["510k", "pma", "pma_supplement", "recall"];
const MODES = ["company", "compare", "device"] as const;
type Mode = (typeof MODES)[number];

interface Route {
  mode: Mode;
  org: string;
  orgB: string;
  device: string;
  years: number;
  from: string;
  to: string;
  types: EventType[];
}

interface FormState extends Route {
  explicit: boolean;
}

function defaultForm(): FormState {
  return {
    mode: "company",
    org: "",
    orgB: "",
    device: "",
    years: 5,
    from: "",
    to: "",
    types: [...EVENT_TYPES],
    explicit: false,
  };
}

function isEventType(value: string): value is EventType {
  return (EVENT_TYPES as string[]).includes(value);
}

function parseRoute(params: URLSearchParams): Route | null {
  const rawMode = params.get("mode");
  if (rawMode !== "company" && rawMode !== "compare" && rawMode !== "device") return null;
  const mode = rawMode as Mode;
  const yearsRaw = Number(params.get("years") ?? "5");
  const years = [3, 5, 10].includes(yearsRaw) ? yearsRaw : 5;
  const types = (params.get("types") ?? "")
    .split(",")
    .filter(isEventType);
  const route: Route = {
    mode,
    org: params.get("org") ?? "",
    orgB: "",
    device: params.get("device") ?? "",
    years,
    from: params.get("from") ?? "",
    to: params.get("to") ?? "",
    types: types.length ? types : [...EVENT_TYPES],
  };
  const orgs = (params.get("orgs") ?? "").split(",").filter(Boolean);
  route.org = route.org || orgs[0] || "";
  route.orgB = orgs[1] || "";
  if (mode === "company" && !route.org) return null;
  if (mode === "compare" && (!route.org || !route.orgB)) return null;
  if (mode === "device" && !route.device) return null;
  return route;
}

function formFromRoute(route: Route | null): FormState {
  if (!route) return defaultForm();
  return { ...route, explicit: Boolean(route.from && route.to) };
}

function routeToQuery(route: Route): BriefQuery {
  return {
    mode: route.mode,
    org: route.mode === "company" ? route.org : undefined,
    orgs: route.mode === "compare" ? [route.org, route.orgB] : undefined,
    device: route.mode === "device" ? route.device : undefined,
    years: route.from && route.to ? undefined : route.years,
    from: route.from && route.to ? route.from : undefined,
    to: route.from && route.to ? route.to : undefined,
    types: route.types.length && route.types.length < EVENT_TYPES.length ? route.types : undefined,
  };
}

export function BriefPage() {
  const { lang } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const route = useMemo(() => parseRoute(searchParams), [searchParams]);
  const [form, setForm] = useState<FormState>(() => formFromRoute(route));
  const [drawerEvent, setDrawerEvent] = useState<string | null>(null);
  const [explain, setExplain] = useState<{ metric: string; orgs: string[] } | null>(null);

  useEffect(() => {
    setForm(formFromRoute(route));
  }, [route]);

  const organizations = useAsync(() => listOrganizations(), []);
  const query = route ? routeToQuery(route) : null;
  const brief = useAsync<Brief | null>(
    () => (query ? getBrief(query) : Promise.resolve(null)),
    [JSON.stringify(query)],
  );

  const submit = (overrides?: Partial<FormState>) => {
    const next = { ...form, ...overrides };
    if (next.mode === "company" && !next.org.trim()) return;
    if (next.mode === "compare" && (!next.org.trim() || !next.orgB.trim())) return;
    if (next.mode === "device" && !next.device.trim()) return;
    if (next.explicit && (!next.from || !next.to)) return;
    const params = new URLSearchParams();
    params.set("mode", next.mode);
    if (next.mode === "company") params.set("org", next.org.trim());
    if (next.mode === "compare") params.set("orgs", [next.org.trim(), next.orgB.trim()].join(","));
    if (next.mode === "device") params.set("device", next.device.trim());
    if (next.explicit && next.from && next.to) {
      params.set("from", next.from);
      params.set("to", next.to);
    } else {
      params.set("years", String(next.years));
    }
    if (next.types.length && next.types.length < EVENT_TYPES.length) params.set("types", next.types.join(","));
    navigate("/brief?" + params.toString());
  };

  const quick = (org: string, orgB?: string) => {
    const next: Partial<FormState> = orgB ? { mode: "compare", org, orgB } : { mode: "company", org };
    setForm((current) => ({ ...current, ...next }));
    submit(next);
  };

  const data = brief.data;
  const title = data ? pickText(data.title, lang) : lang === "zh" ? "情报简报工作台" : "Intelligence Brief";
  const description = data
    ? pickText(data.question, lang)
    : lang === "zh"
      ? "先定义研究问题与范围，再生成一份带证据、发现与限制的简报。所有数字都可由官方 FDA 记录复现。"
      : "Define a research question and a scope, then produce a brief with findings, evidence and limitations. Every number is reproducible from official FDA records.";

  return (
    <>
      <PageHeader
        eyebrow={lang === "zh" ? "情报简报 · PRODUCT-004" : "Intelligence brief · PRODUCT-004"}
        title={title}
        description={description}
        actions={
          data && query ? (
            <>
              <a className="btn primary" href={briefMdUrl(query, lang)}>
                {lang === "zh" ? "↓ 下载简报 (MD)" : "↓ Download brief (MD)"}
              </a>
              <a className="btn" href={briefEvidenceUrl(query)}>
                {lang === "zh" ? "↓ 证据附录 (CSV)" : "↓ Evidence appendix (CSV)"}
              </a>
              <button type="button" className="btn" onClick={() => window.print()}>
                {lang === "zh" ? "打印 / PDF" : "Print / PDF"}
              </button>
            </>
          ) : undefined
        }
      />

      <div className="stack">
        <BriefForm
          form={form}
          onChange={setForm}
          onSubmit={() => submit()}
          organizations={organizations.data?.organizations ?? []}
          lang={lang}
        />

        {!route && !organizations.status.startsWith("loading") ? (
          <div className="grid cols-3">
            <QuickStart
              title={lang === "zh" ? "研究一家企业" : "Research a company"}
              note={lang === "zh" ? "默认窗口为最近五个完整自然年。" : "Default window: the last five complete calendar years."}
              action={lang === "zh" ? "以美敦力为例" : "Try Medtronic"}
              onClick={() => quick("medtronic")}
            />
            <QuickStart
              title={lang === "zh" ? "比较竞争对手" : "Compare competitors"}
              note={lang === "zh" ? "同一窗口、同一统计口径，先呈现可比性限制。" : "One window, one counting rule, comparability limits first."}
              action={lang === "zh" ? "GE HealthCare 对比 Philips" : "GE HealthCare vs Philips"}
              onClick={() => quick("ge_healthcare", "philips")}
            />
            <QuickStart
              title={lang === "zh" ? "调查器械家族" : "Investigate a device family"}
              note={lang === "zh" ? "查看官方 PMA 层级、补充申请与有关联的召回。" : "Official PMA hierarchy, supplements and linked recalls."}
              action={lang === "zh" ? "以 PMA P980016 为例" : "Try PMA P980016"}
              onClick={() => {
                const next = { ...form, mode: "device" as Mode, device: "P980016" };
                setForm(next);
                submit(next);
              }}
            />
          </div>
        ) : null}

        {route ? (
          <AsyncSection status={brief.status} data={brief.data} error={brief.error} reload={brief.reload} loadingLines={6}>
            {(loaded) =>
              loaded ? (
                loaded.kind === "company" ? (
                  <CompanyBriefView brief={loaded} onOpenEvent={setDrawerEvent} lang={lang} />
                ) : loaded.kind === "compare" ? (
                  <CompareBriefView brief={loaded} onExplain={setExplain} onOpenEvent={setDrawerEvent} lang={lang} />
                ) : (
                  <DeviceBriefView brief={loaded} onOpenEvent={setDrawerEvent} lang={lang} />
                )
              ) : null
            }
          </AsyncSection>
        ) : (
          <Card
            title={lang === "zh" ? "从问题到简报" : "From a question to a brief"}
            note={
              lang === "zh"
                ? "PRODUCT-004 的工作流固定为：定义问题 → 探索证据 → 比较与解释 → 核验 → 交付。"
                : "The PRODUCT-004 workflow is fixed: define the question → explore evidence → compare and explain → verify → deliver."
            }
          >
            <EmptyState
              title={lang === "zh" ? "选择研究对象以开始" : "Choose a research target to begin"}
              description={
                lang === "zh"
                  ? "可为一家企业、两家企业或一个 PMA / K 号码生成简报。生成后 URL 会保存完整范围，便于复现与分享。"
                  : "A brief can cover one company, a comparison set, or a PMA/K number. The URL records the full scope so it can be reproduced and shared."
              }
            />
          </Card>
        )}
      </div>

      {drawerEvent ? <EvidenceDrawer eventId={drawerEvent} onClose={() => setDrawerEvent(null)} /> : null}
      {explain ? (
        <ExplainDrawer
          query={{
            metric: explain.metric,
            orgs: explain.orgs,
            years: route?.years,
            from: route?.from || undefined,
            to: route?.to || undefined,
            types: route?.types,
          }}
          onClose={() => setExplain(null)}
        />
      ) : null}
    </>
  );
}

/* ------------------------------------------------------------------ form */

function BriefForm({
  form,
  onChange,
  onSubmit,
  organizations,
  lang,
}: {
  form: FormState;
  onChange: (form: FormState) => void;
  onSubmit: () => void;
  organizations: { key: string; display_name: string; ticker: string | null }[];
  lang: Lang;
}) {
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => onChange({ ...form, [key]: value });
  const toggleType = (type: EventType) => {
    const has = form.types.includes(type);
    const next = has ? form.types.filter((item) => item !== type) : [...form.types, type];
    set("types", next);
  };
  const valid =
    (form.mode === "company" && form.org.trim().length > 0) ||
    (form.mode === "compare" && form.org.trim().length > 0 && form.orgB.trim().length > 0) ||
    (form.mode === "device" && form.device.trim().length > 0);
  return (
    <Card
      title={lang === "zh" ? "1 · 定义研究问题" : "1 · Define the research question"}
      note={
        lang === "zh"
          ? "选择对象与时间窗口。所有计算都使用同一口径；生成后完整范围会写入 URL。"
          : "Choose a target and a window. One counting rule applies throughout; the full scope is written into the URL."
      }
      actions={
        <button type="button" className="btn primary" onClick={onSubmit} disabled={!valid}>
          {lang === "zh" ? "生成情报简报" : "Build intelligence brief"}
        </button>
      }
    >
      <div className="brief-form">
        <div className="tabs" role="tablist" aria-label={lang === "zh" ? "研究类型" : "Research type"}>
          {MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              role="tab"
              aria-selected={form.mode === mode}
              className={form.mode === mode ? "active" : undefined}
              onClick={() => set("mode", mode)}
            >
              {mode === "company"
                ? lang === "zh"
                  ? "研究企业"
                  : "Company"
                : mode === "compare"
                  ? lang === "zh"
                    ? "比较竞争对手"
                    : "Compare"
                  : lang === "zh"
                    ? "调查器械"
                    : "Device"}
            </button>
          ))}
        </div>

        <datalist id="brief-organizations">
          {organizations.map((org) => (
            <option key={org.key} value={org.key}>
              {org.display_name}
              {org.ticker ? " (" + org.ticker + ")" : ""}
            </option>
          ))}
        </datalist>

        {form.mode === "device" ? (
          <div className="grid cols-2">
            <label className="field">
              <span className="field-label">{lang === "zh" ? "PMA / 510(k) / 器械标识" : "PMA / 510(k) / device identifier"}</span>
              <input
                className="input"
                value={form.device}
                onChange={(event) => set("device", event.target.value)}
                placeholder="P980016 / K260306 / device:openfda_pma:P980016"
              />
              <span className="tiny muted">
                {lang === "zh"
                  ? "设备调查按官方申请层级汇总，不使用时间窗口。"
                  : "A device investigation summarises the official application hierarchy; it is not windowed."}
              </span>
            </label>
          </div>
        ) : (
          <div className="grid cols-2">
            <label className="field">
              <span className="field-label">{lang === "zh" ? "企业" : "Organization"}</span>
              <input
                className="input"
                list="brief-organizations"
                value={form.org}
                onChange={(event) => set("org", event.target.value)}
                placeholder={lang === "zh" ? "输入 key 或从列表选择，例如 medtronic" : "Type a key or pick from the list, e.g. medtronic"}
              />
            </label>
            {form.mode === "compare" ? (
              <label className="field">
                <span className="field-label">{lang === "zh" ? "对比企业" : "Compare with"}</span>
                <input
                  className="input"
                  list="brief-organizations"
                  value={form.orgB}
                  onChange={(event) => set("orgB", event.target.value)}
                  placeholder={lang === "zh" ? "例如 philips" : "e.g. philips"}
                />
              </label>
            ) : null}
          </div>
        )}

        {form.mode !== "device" ? (
          <div className="row wrap" style={{ gap: 8 }}>
            <span className="field-label" style={{ marginRight: 4 }}>
              {lang === "zh" ? "窗口" : "Window"}
            </span>
            {[3, 5, 10].map((years) => (
              <button
                key={years}
                type="button"
                className="chip"
                aria-pressed={!form.explicit && form.years === years}
                onClick={() => onChange({ ...form, years, explicit: false, from: "", to: "" })}
              >
                {years} {lang === "zh" ? "个完整年度" : "complete years"}
              </button>
            ))}
            <button
              type="button"
              className="chip"
              aria-pressed={form.explicit}
              onClick={() => onChange({ ...form, explicit: true })}
            >
              {lang === "zh" ? "自定义日期" : "Custom dates"}
            </button>
          </div>
        ) : null}

        {form.explicit && form.mode !== "device" ? (
          <div className="grid cols-3">
            <label className="field">
              <span className="field-label">{lang === "zh" ? "起始日期" : "From"}</span>
              <input className="input" type="date" value={form.from} onChange={(event) => set("from", event.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">{lang === "zh" ? "截止日期" : "To"}</span>
              <input className="input" type="date" value={form.to} onChange={(event) => set("to", event.target.value)} />
            </label>
            <div className="field">
              <span className="field-label">{lang === "zh" ? "说明" : "Note"}</span>
              <span className="tiny muted">
                {lang === "zh"
                  ? "边缘不完整年度会标注，且不参与年度变化规则。"
                  : "Partial years at the edges are marked and excluded from the year-change rule."}
              </span>
            </div>
          </div>
        ) : null}

        {form.mode !== "device" ? (
          <div className="row wrap" style={{ gap: 10 }}>
            <span className="field-label" style={{ marginRight: 4 }}>
              {lang === "zh" ? "事件类型" : "Event types"}
            </span>
            {EVENT_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                className="chip"
                aria-pressed={form.types.includes(type)}
                onClick={() => toggleType(type)}
              >
                <span className="dot" style={{ background: "var(--" + type + ")" }} aria-hidden="true" />
                {typeLabel(type, lang)}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function QuickStart({ title, note, action, onClick }: { title: string; note: string; action: string; onClick: () => void }) {
  return (
    <div className="card">
      <div className="card-body">
        <div className="card-title">{title}</div>
        <div className="card-note">{note}</div>
        <button type="button" className="btn primary sm mt-12" onClick={onClick}>
          {action}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ shared */

function FindingsList({
  findings,
  lang,
  onOpenEvent,
}: {
  findings: BriefFinding[];
  lang: Lang;
  onOpenEvent: (eventId: string) => void;
}) {
  if (!findings.length) {
    return (
      <Card title={lang === "zh" ? "有证据支持的发现" : "Evidence-backed findings"}>
        <div className="empty-inline">
          {lang === "zh"
            ? "该范围没有触发任何发现规则。这也是结果：简报不编造观察。"
            : "No finding rule fired for this scope. That is a result: the brief does not invent observations."}
        </div>
      </Card>
    );
  }
  return (
    <section className="section">
      <SectionHead
        title={lang === "zh" ? "有证据支持的发现" : "Evidence-backed findings"}
        note={
          lang === "zh"
            ? "每条发现都给出规则、引用记录与“不能说明什么”；没有预测或商业结论。"
            : "Each finding states its rule, the records it cites and what it does not mean. No prediction or commercial conclusion."
        }
      />
      <div className="brief-findings">
        {findings.map((finding) => (
          <article className={"brief-finding " + finding.category} key={finding.id}>
            <div className="row" style={{ gap: 8, alignItems: "center" }}>
              <Badge tone={finding.category === "finding" ? "info" : "warn"}>
                {finding.category === "finding" ? (lang === "zh" ? "发现" : "Finding") : lang === "zh" ? "注意事项" : "Caution"}
              </Badge>
              <span className="mono tiny muted">{finding.id}</span>
            </div>
            <h3 className="brief-finding-title">{pickText(finding.title, lang)}</h3>
            <p className="brief-finding-statement">{pickText(finding.statement, lang)}</p>
            <div className="brief-cannot">
              <b>{lang === "zh" ? "这不能说明什么：" : "What this does not mean: "}</b>
              {pickText(finding.cannot_conclude, lang)}
            </div>
            <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
              {finding.drilldown?.url ? (
                <Link className="btn sm" to={finding.drilldown.url}>
                  {finding.drilldown.label ? pickText(finding.drilldown.label, lang) : lang === "zh" ? "查看支持记录" : "View supporting records"}
                </Link>
              ) : null}
              <details className="brief-details">
                <summary className="small">{lang === "zh" ? "规则与引用记录" : "Rule and cited records"}</summary>
                <div className="small muted mt-8">
                  <div>
                    <b>{lang === "zh" ? "规则：" : "Rule: "}</b>
                    <span className="mono">{finding.basis.rule}</span>
                  </div>
                  <div className="mt-8">
                    {lang === "zh" ? "引用记录" : "Cited records"}: {fmtNumber(finding.evidence.record_count)}
                  </div>
                </div>
                {finding.evidence.records.length ? (
                  <RecordTable records={finding.evidence.records} onOpenEvent={onOpenEvent} lang={lang} compact />
                ) : null}
              </details>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function RecordTable({
  records,
  onOpenEvent,
  lang,
  compact = false,
}: {
  records: BriefRecordRef[];
  onOpenEvent: (eventId: string) => void;
  lang: Lang;
  compact?: boolean;
}) {
  return (
    <div className="table-wrap mt-8">
      <table className="data">
        <thead>
          <tr>
            <th>{lang === "zh" ? "事件日期" : "Event date"}</th>
            <th>{lang === "zh" ? "官方标识" : "Official ID"}</th>
            <th>{lang === "zh" ? "类型" : "Type"}</th>
            {compact ? null : <th>{lang === "zh" ? "器械" : "Device"}</th>}
            <th>{lang === "zh" ? "归属复核" : "Attribution"}</th>
            <th>{lang === "zh" ? "证据" : "Evidence"}</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.event_id}>
              <td data-label={lang === "zh" ? "事件日期" : "Event date"}>{fmtDate(record.event_date)}</td>
              <td data-label={lang === "zh" ? "官方标识" : "Official ID"} className="mono">
                {record.official_url ? (
                  <a href={record.official_url} target="_blank" rel="noreferrer">
                    {record.official_id}
                  </a>
                ) : (
                  record.official_id
                )}
              </td>
              <td data-label={lang === "zh" ? "类型" : "Type"}>
                <EventTypeBadge type={record.event_type} short />
              </td>
              {compact ? null : (
                <td data-label={lang === "zh" ? "器械" : "Device"}>
                  <div className="cell-primary">{record.device_name || "—"}</div>
                  <div className="cell-sub">{record.applicant_name}</div>
                </td>
              )}
              <td data-label={lang === "zh" ? "归属复核" : "Attribution"}>
                <Badge tone={record.attribution_verified ? "ok" : "warn"}>
                  {lang === "zh" ? record.verification_label_zh : record.verification_label_en}
                </Badge>
              </td>
              <td>
                <button type="button" className="evidence-link" onClick={() => onOpenEvent(record.event_id)}>
                  {lang === "zh" ? "证据" : "Evidence"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScopeStrip({ brief, lang }: { brief: Brief; lang: Lang }) {
  const scope = brief.scope;
  const snapshot = scope.snapshot;
  return (
    <div className="brief-scope">
      <div>
        <span className="brief-scope-label">{lang === "zh" ? "范围" : "Window"}</span>
        <span className="mono">{fmtWindow(scope, lang)}</span>
      </div>
      <div>
        <span className="brief-scope-label">{lang === "zh" ? "事件类型" : "Event types"}</span>
        <span>{scope.event_type_labels.map((label, index) => (lang === "zh" ? typeLabel(scope.event_types[index], "zh") : label)).join(", ")}</span>
      </div>
      <div>
        <span className="brief-scope-label">{lang === "zh" ? "数据快照" : "Snapshot"}</span>
        <span className="mono">{snapshot.id}</span>
        <span className="muted small"> · {lang === "zh" ? "采集于" : "collected"} {fmtDate(snapshot.collected_at)}</span>
      </div>
      <div>
        <span className="brief-scope-label">{lang === "zh" ? "统计口径" : "Counting rule"}</span>
        <span className="small">{pickText(scope.counting_rule, lang)}</span>
      </div>
    </div>
  );
}

function Limitations({ brief, lang }: { brief: Brief; lang: Lang }) {
  const sections: { key: keyof Brief["limitations"]; label: string }[] = [
    { key: "scope", label: lang === "zh" ? "范围" : "Scope" },
    { key: "coverage", label: lang === "zh" ? "覆盖" : "Coverage" },
    { key: "identity", label: lang === "zh" ? "身份与归属" : "Identity" },
    { key: "time", label: lang === "zh" ? "时间语义" : "Time" },
    { key: "relationship", label: lang === "zh" ? "关系" : "Relationships" },
    { key: "cannot_answer", label: lang === "zh" ? "无法回答的问题" : "Questions this cannot answer" },
  ];
  return (
    <Card
      title={lang === "zh" ? "证据、覆盖与限制" : "Evidence, coverage and limitations"}
      note={
        lang === "zh"
          ? "这些限制是简报的一部分，不是脚注；它们与发现同等重要。"
          : "These limits are part of the brief, not a footnote; they matter as much as the findings."
      }
    >
      <div className="brief-limits">
        {sections.map((section) => {
          const items = brief.limitations[section.key] ?? [];
          if (!items.length) return null;
          return (
            <div key={section.key}>
              <div className="brief-limit-title">{section.label}</div>
              <ul className="brief-list">
                {items.map((item, index) => (
                  <li key={index}>{pickText(item, lang)}</li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

interface ChangeBlockShape {
  state?: string;
  note?: { en: string; zh: string } | string;
  display_name?: string;
  items?: unknown[];
}

function ChangesBlock({ changes, lang }: { changes: unknown; lang: Lang }) {
  const blocks = (Array.isArray(changes) ? changes : [changes]) as ChangeBlockShape[];
  return (
    <Card
      title={lang === "zh" ? "自上一快照以来的变化" : "Changes since the previous snapshot"}
      note={lang === "zh" ? "来自 DATA-001 变化台账；没有台账时如实说明，不制造“最新动态”。" : "From the DATA-001 change ledger. Without a ledger the brief says so instead of inventing updates."}
    >
      <div className="stack" style={{ gap: 10 }}>
        {blocks.map((block, index) => (
          <div key={index} className="callout">
            {block.display_name ? <b>{block.display_name}: </b> : null}
            <span>{pickText(block.note ?? "", lang)}</span>
            <div className="tiny muted mt-8">
              {lang === "zh" ? "状态：" : "State: "}
              <span className="mono">{block.state ?? "unknown"}</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ company */

function CompanyBriefView({ brief, onOpenEvent, lang }: { brief: CompanyBrief; onOpenEvent: (id: string) => void; lang: Lang }) {
  const [showAllFamilies, setShowAllFamilies] = useState(false);
  const activityRows = brief.activity.by_year.map((row) => ({ year: row.year, counts: row.counts, total: row.total }));
  const specialtyRows = brief.technology.specialty.rows.map((row) => ({
    id: row.id,
    label: row.label,
    counts: row.by_type,
    total: row.count,
  }));
  const org = brief.organization;
  const families = showAllFamilies ? brief.technology.product_families.rows : brief.technology.product_families.rows.slice(0, 10);
  return (
    <>
      <ScopeStrip brief={brief} lang={lang} />

      <div className="grid cols-4">
        {brief.summary.tiles.map((tile) => (
          <MetricTile
            key={tile.id}
            label={pickText(tile.label, lang)}
            value={
              typeof tile.value === "number"
                ? fmtNumber(tile.value)
                : tile.id === "top_pathway"
                  ? localisePathwayLabel(tile.value, lang)
                  : tile.value
            }
            sub={pickText(tile.note, lang)}
          />
        ))}
      </div>

      <FindingsList findings={brief.findings} lang={lang} onOpenEvent={onOpenEvent} />

      <div className="grid cols-2">
        <Card
          title={lang === "zh" ? "监管活动" : "Regulatory activity"}
          note={lang === "zh" ? "事件类型不合并；PMA 补充申请不是新器械。" : "Event types are never merged; a PMA supplement is not a new device."}
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{lang === "zh" ? "路径" : "Pathway"}</th>
                  <th className="num">{lang === "zh" ? "记录" : "Records"}</th>
                  <th className="num">{lang === "zh" ? "占比" : "Share"}</th>
                </tr>
              </thead>
              <tbody>
                {brief.summary.by_type.map((row) => (
                  <tr key={row.event_type}>
                    <td>
                      <EventTypeBadge type={row.event_type} />
                      <div className="tiny muted mt-8">{pickText(row.definition, lang)}</div>
                    </td>
                    <td className="num">{fmtNumber(row.count)}</td>
                    <td className="num">{fmtPercent(row.share)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card
          title={lang === "zh" ? "逐年记录（完整年度）" : "Records per complete calendar year"}
          note={lang === "zh" ? "不满整年会在表格中标注，并不参与年度变化规则。" : "Partial years are marked in the table and excluded from the year-change rule."}
        >
          <YearSeries data={activityRows} />
          {brief.activity.partial_years.length ? (
            <div className="callout mt-8">
              {lang === "zh" ? "不完整年度：" : "Partial years: "}
              {brief.activity.partial_years.join(", ")}
            </div>
          ) : null}
        </Card>
      </div>

      <div className="grid cols-2">
        <Card
          title={lang === "zh" ? "技术领域 · FDA 医学专科" : "Technology areas · FDA medical specialty"}
          note={pickText(brief.technology.specialty.note, lang)}
        >
          <BarBreakdown rows={specialtyRows} limit={10} />
          <div className="callout mt-8">
            {lang === "zh"
              ? `官方专科为“Unknown”的记录：${fmtNumber(brief.technology.specialty.unknown_count)} / ${fmtNumber(brief.summary.records)}（${fmtPercent(brief.technology.specialty.unknown_share)}）。`
              : `Records whose official specialty is "Unknown": ${fmtNumber(brief.technology.specialty.unknown_count)} / ${fmtNumber(brief.summary.records)} (${fmtPercent(brief.technology.specialty.unknown_share)}).`}
          </div>
        </Card>
        <Card
          title={lang === "zh" ? "技术领域 · FDA 产品代码家族" : "Technology areas · FDA product-code families"}
          note={pickText(brief.technology.product_families.note, lang)}
          actions={
            brief.technology.product_families.rows.length > 10 ? (
              <button type="button" className="btn sm" onClick={() => setShowAllFamilies((value) => !value)}>
                {showAllFamilies ? (lang === "zh" ? "收起" : "Show fewer") : lang === "zh" ? "显示全部" : "Show all"}
              </button>
            ) : null
          }
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{lang === "zh" ? "代码" : "Code"}</th>
                  <th>{lang === "zh" ? "FDA 官方分类名称" : "Official FDA classification name"}</th>
                  <th className="num">{lang === "zh" ? "记录" : "Records"}</th>
                  <th>{lang === "zh" ? "首次 / 最近" : "First / last"}</th>
                </tr>
              </thead>
              <tbody>
                {families.map((row) => (
                  <tr key={row.product_code}>
                    <td className="mono">
                      <Link to={"/events?org=" + org.key + "&product_code=" + row.product_code + "&from=" + brief.scope.from + "&to=" + brief.scope.to}>
                        {row.product_code}
                      </Link>
                    </td>
                    <td>
                      <div className="cell-primary">{row.official_name ?? (lang === "zh" ? "—（不在 FDA 分类字典中）" : "— (not in the FDA dictionary)")}</div>
                      <div className="cell-sub">
                        {lang === "zh" ? "专科：" : "Specialty: "}
                        {row.specialty}
                        {row.device_class ? " · Class " + row.device_class : ""}
                      </div>
                    </td>
                    <td className="num">{fmtNumber(row.records)}</td>
                    <td className="small">
                      {fmtDate(row.first_event_date)} → {fmtDate(row.last_event_date)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {brief.devices.families.length ? (
        <Card
          title={lang === "zh" ? "器械情报 · 本窗口内的 PMA 家族" : "Device intelligence · PMA families in the window"}
          note={pickText(brief.devices.note, lang)}
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>PMA</th>
                  <th>{lang === "zh" ? "家族 / 官方标识" : "Family / official identifier"}</th>
                  <th className="num">{lang === "zh" ? "窗口内补充申请" : "Supplements in window"}</th>
                  <th>{lang === "zh" ? "首次 / 最近" : "First / last"}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {brief.devices.families.map((family) => (
                  <tr key={family.pma_number}>
                    <td className="mono">{family.pma_number}</td>
                    <td>
                      <div className="cell-primary">{family.name}</div>
                      <div className="cell-sub">
                        {family.original_in_snapshot
                          ? lang === "zh"
                            ? "原始批准在快照中"
                            : "original approval in snapshot"
                          : lang === "zh"
                            ? "原始批准不在快照中"
                            : "original approval not in snapshot"}
                      </div>
                    </td>
                    <td className="num">{fmtNumber(family.supplements_in_window)}</td>
                    <td className="small">
                      {fmtDate(family.first_event_date)} → {fmtDate(family.last_event_date)}
                    </td>
                    <td>
                      <Link className="link small" to={family.device_url}>
                        {lang === "zh" ? "打开器械" : "Open device"}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      <Card
        title={lang === "zh" ? "近期活动" : "Recent activity"}
        note={pickText(brief.recent.note, lang)}
        actions={<Link className="btn sm" to={"/events?org=" + org.key + "&from=" + brief.scope.from + "&to=" + brief.scope.to}>{lang === "zh" ? "在事件浏览器中查看全部" : "Open all in the event browser"}</Link>}
      >
        <RecordTable records={brief.recent.records} onOpenEvent={onOpenEvent} lang={lang} />
      </Card>

      <div className="grid cols-2">
        <Card title={lang === "zh" ? "来源覆盖" : "Source coverage"}>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{lang === "zh" ? "来源" : "Source"}</th>
                  <th className="num">{lang === "zh" ? "记录" : "Records"}</th>
                  <th>{lang === "zh" ? "日期范围" : "Date range"}</th>
                </tr>
              </thead>
              <tbody>
                {brief.summary.sources.map((row) => (
                  <tr key={row.source_id}>
                    <td>{row.name}</td>
                    <td className="num">{fmtNumber(row.records)}</td>
                    <td className="small">
                      {fmtDate(row.min_event_date)} → {fmtDate(row.max_event_date)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="callout mt-8">
            {lang === "zh"
              ? `已核验：${fmtNumber(brief.summary.verification.verified_records)}；规则校验：${fmtNumber(brief.summary.verification.rule_verified_records)}；暂定：${fmtNumber(brief.summary.verification.provisional_records)}。`
              : `Verified: ${fmtNumber(brief.summary.verification.verified_records)}; rule-verified: ${fmtNumber(brief.summary.verification.rule_verified_records)}; provisional: ${fmtNumber(brief.summary.verification.provisional_records)}.`}
          </div>
          <div className="callout mt-8">
            {pickText(brief.summary.ownership.note, lang)}
          </div>
        </Card>

        <ChangesBlock changes={brief.changes} lang={lang} />
      </div>

      <Limitations brief={brief} lang={lang} />

      <Card title={lang === "zh" ? "把成果带走" : "Take the work away"}>
        <div className="row wrap" style={{ gap: 10 }}>
          <a className="btn primary" href={briefMdUrl(routeToQuery(routeFromBrief(brief)), lang)}>
            {lang === "zh" ? "下载企业情报简报 (MD)" : "Download company intelligence brief (MD)"}
          </a>
          <a className="btn" href={briefEvidenceUrl(routeToQuery(routeFromBrief(brief)))}>
            {lang === "zh" ? "下载证据附录 (CSV)" : "Download evidence appendix (CSV)"}
          </a>
        </div>
        <div className="small muted mt-8">{pickText(brief.evidence.appendix.note, lang)}</div>
        <div className="small muted mt-8 brief-link-list">
          <span>{lang === "zh" ? "官方记录链接：" : "Official record links:"}</span>
          {brief.evidence.official_links.slice(0, 6).map((row) => (
            <a key={row.url} className="link" href={row.url} target="_blank" rel="noreferrer">
              {row.label}
            </a>
          ))}
        </div>
      </Card>
    </>
  );
}

/** Reconstruct the exact scope the brief was generated with, for exports. */
function routeFromBrief(brief: Brief): FormState {
  const explicit = brief.scope.requested_years === null;
  const base = defaultForm();
  if (brief.kind === "company") {
    return {
      ...base,
      mode: "company",
      org: brief.organization.key,
      years: brief.scope.requested_years ?? 5,
      from: explicit ? brief.scope.from : "",
      to: explicit ? brief.scope.to : "",
      types: brief.scope.event_types,
      explicit,
    };
  }
  if (brief.kind === "compare") {
    return {
      ...base,
      mode: "compare",
      org: brief.sides[0]?.key ?? "",
      orgB: brief.sides[1]?.key ?? "",
      years: brief.scope.requested_years ?? 5,
      from: explicit ? brief.scope.from : "",
      to: explicit ? brief.scope.to : "",
      types: brief.scope.event_types,
      explicit,
    };
  }
  return {
    ...base,
    mode: "device",
    device: String(brief.application?.official_id ?? brief.device.official_id ?? ""),
    types: brief.scope.event_types,
    explicit: false,
  };
}

/* ------------------------------------------------------------------ compare */

const WARNING_LABELS: Record<string, { en: string; zh: string }> = {
  coverage_mismatch: { en: "Source coverage differs", zh: "来源覆盖不同" },
  pathway_mix: { en: "Pathway mix differs", zh: "监管路径构成不同" },
  recall_share: { en: "Recall share", zh: "召回占比" },
  unmapped_category_present: { en: "Unclassified records present", zh: "存在未分类记录" },
  provisional_attribution_present: { en: "Provisional attribution present", zh: "存在暂定归属" },
  verification_asymmetry: { en: "Verification differs between sides", zh: "双方核验程度不同" },
  historical_ownership_basis: { en: "Ownership-at-event basis", zh: "事件时所有权口径" },
  historical_owner_basis_excludes_records: { en: "Ownership basis excludes records", zh: "所有权口径排除了部分记录" },
  partial_year_excluded: { en: "Partial years excluded", zh: "不完整年度已排除" },
  low_volume: { en: "Small base", zh: "基数较小" },
};

function CompareBriefView({
  brief,
  onExplain,
  onOpenEvent,
  lang,
}: {
  brief: CompareBrief;
  onExplain: (value: { metric: string; orgs: string[] }) => void;
  onOpenEvent: (id: string) => void;
  lang: Lang;
}) {
  const keys = brief.sides.map((side) => side.key);
  const coverageTone: "info" | "warning" = brief.coverage_assessment.symmetric ? "info" : "warning";
  return (
    <>
      <ScopeStrip brief={brief} lang={lang} />

      <Banner
        tone={coverageTone}
        title={
          lang === "zh"
            ? brief.comparability.coverage_symmetric
              ? "在所述窗口与事件类型内可比"
              : "差异包含覆盖或所有权口径差异；比较总数前请先阅读限制"
            : brief.comparability.verdict
        }
      >
        {pickText(brief.coverage_assessment.note, lang)}
      </Banner>

      <div className="grid cols-4">
        {brief.sides.map((side) => (
          <MetricTile
            key={side.key}
            label={side.display_name}
            value={fmtNumber(side.counts.records)}
            sub={
              lang === "zh"
                ? `510(k) ${fmtNumber(side.counts_by_type["510k"])} · PMA ${fmtNumber(side.counts_by_type.pma)} · 补充 ${fmtNumber(side.counts_by_type.pma_supplement)} · 召回 ${fmtNumber(side.counts_by_type.recall)}`
                : `510(k) ${fmtNumber(side.counts_by_type["510k"])} · PMA ${fmtNumber(side.counts_by_type.pma)} · supp. ${fmtNumber(side.counts_by_type.pma_supplement)} · recall ${fmtNumber(side.counts_by_type.recall)}`
            }
          />
        ))}
        <MetricTile
          label={lang === "zh" ? "可比性" : "Comparability"}
          value={brief.comparability.coverage_symmetric ? (lang === "zh" ? "覆盖对称" : "Coverage symmetric") : lang === "zh" ? "覆盖不对称" : "Coverage asymmetric"}
          sub={lang === "zh" ? "同一窗口、同一计数单位" : "One window, one counting unit"}
        />
      </div>

      <FindingsList findings={brief.findings} lang={lang} onOpenEvent={onOpenEvent} />

      <Card
        title={lang === "zh" ? "可比指标与解释" : "Comparable measures and explanation"}
        note={
          lang === "zh"
            ? "每一行都可以展开定义、分子、分母与背后记录；数字与对比页使用同一计算。"
            : "Every row expands into its definition, numerator, denominator and records; the numbers come from the same computation as Compare."
        }
      >
        <div className="table-wrap">
          <table className="data brief-metrics">
            <thead>
              <tr>
                <th>{lang === "zh" ? "指标" : "Measure"}</th>
                {brief.sides.map((side) => (
                  <th key={side.key} className="num">
                    {side.display_name}
                  </th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {brief.metrics.map((metric) => (
                <tr key={metric.id}>
                  <td>
                    <div className="cell-primary">{pickText(metric.label, lang)}</div>
                    <div className="cell-sub">{pickText(metric.definition, lang)}</div>
                  </td>
                  {brief.sides.map((side) => {
                    const value = metric.values.find((item) => item.key === side.key);
                    return (
                      <td key={side.key} className="num">
                        {fmtNumber(value?.value)}
                      </td>
                    );
                  })}
                  <td>
                    <button type="button" className="btn sm" onClick={() => onExplain({ metric: metric.id, orgs: keys })}>
                      {lang === "zh" ? "解释差异" : "Explain"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid cols-2">
        <Card title={lang === "zh" ? "逐年记录" : "Records per complete year"}>
          <div className="stack" style={{ gap: 14 }}>
            {brief.by_year.map((side) => (
              <div key={side.key}>
                <div className="brief-limit-title">{side.name}</div>
                <YearSeries data={side.rows as unknown as { year: string; counts: Record<EventType, number>; total: number }[]} height={150} />
              </div>
            ))}
          </div>
        </Card>
        <Card title={lang === "zh" ? "数据覆盖与核验" : "Coverage and verification"}>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{lang === "zh" ? "对比方" : "Side"}</th>
                  <th>{lang === "zh" ? "来源" : "Sources"}</th>
                  <th className="num">{lang === "zh" ? "已核验占比" : "Curated share"}</th>
                  <th className="num">{lang === "zh" ? "暂定" : "Provisional"}</th>
                </tr>
              </thead>
              <tbody>
                {brief.sides.map((side) => (
                  <tr key={side.key}>
                    <td>{side.display_name}</td>
                    <td className="small">
                      {side.coverage.sources.filter((row) => row.records).map((row) => row.source_id + " (" + row.records + ")").join(", ")}
                    </td>
                    <td className="num">{fmtPercent(side.counts.curated_share)}</td>
                    <td className="num">{fmtNumber(side.counts.provisional)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="callout mt-8">
            {lang === "zh"
              ? "已核验指有证据支持或经人工复核；规则校验与暂定不是同等可信。"
              : "Verified means evidence-verified or human-reviewed; rule-verified and provisional mappings are not equally trustworthy."}
          </div>
        </Card>
      </div>

      <Card
        title={lang === "zh" ? "比较时需要先读的限制" : "Limits to read before comparing"}
        note={lang === "zh" ? "这些限制来自同一比较计算，与对比页一致。" : "These come from the same comparison computation as the Compare page."}
      >
        <div className="stack" style={{ gap: 8 }}>
          {brief.warnings.length ? (
            brief.warnings.map((warning, index) => (
              <div className="callout" key={warning.code + index}>
                <b>{(() => { const label = WARNING_LABELS[warning.code]; return label ? pickText(label, lang) : warning.code; })()}</b>
                <span className="small">
                  {" — "}
                  {lang === "zh" ? "（英文原文）" : ""}
                  {warning.message}
                </span>
              </div>
            ))
          ) : (
            <div className="empty-inline">{lang === "zh" ? "没有额外警告。" : "No additional warnings."}</div>
          )}
          <div className="callout">
            <b>{lang === "zh" ? "这不是：" : "This is not: "}</b>
            {brief.not_evidence_of.join("; ")}
          </div>
        </div>
      </Card>

      <div className="grid cols-2">
        <Card title={lang === "zh" ? "各来源覆盖明细" : "Coverage by source"}>
          <div className="stack" style={{ gap: 12 }}>
            {brief.evidence.sources.map((group) => (
              <div key={group.key}>
                <div className="brief-limit-title">{group.name}</div>
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>{lang === "zh" ? "来源" : "Source"}</th>
                        <th className="num">{lang === "zh" ? "记录" : "Records"}</th>
                        <th>{lang === "zh" ? "范围" : "Range"}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.sources.map((row) => (
                        <tr key={row.source_id}>
                          <td>{row.name}</td>
                          <td className="num">{fmtNumber(row.records)}</td>
                          <td className="small">
                            {fmtDate(row.min_event_date)} → {fmtDate(row.max_event_date)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        </Card>
        <ChangesBlock changes={brief.changes} lang={lang} />
      </div>

      <Limitations brief={brief} lang={lang} />

      <Card title={lang === "zh" ? "把成果带走" : "Take the work away"}>
        <div className="row wrap" style={{ gap: 10 }}>
          <a className="btn primary" href={briefMdUrl(routeToQuery(routeFromBrief(brief)), lang)}>
            {lang === "zh" ? "下载竞争对比简报 (MD)" : "Download competitor comparison brief (MD)"}
          </a>
          <a className="btn" href={briefEvidenceUrl(routeToQuery(routeFromBrief(brief)))}>
            {lang === "zh" ? "下载证据附录 (CSV)" : "Download evidence appendix (CSV)"}
          </a>
        </div>
        <div className="small muted mt-8">{pickText(brief.evidence.appendix.note, lang)}</div>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ device */

function DeviceBriefView({ brief, onOpenEvent, lang }: { brief: DeviceBrief; onOpenEvent: (id: string) => void; lang: Lang }) {
  const [limit, setLimit] = useState(40);
  const versions = brief.versions;
  const application = brief.application;
  const recalls = brief.related_recalls.confirmed;
  return (
    <>
      <ScopeStrip brief={brief} lang={lang} />
      <div className="grid cols-4">
        {brief.tiles.map((tile) => (
          <MetricTile key={tile.id} label={pickText(tile.label, lang)} value={typeof tile.value === "number" ? fmtNumber(tile.value) : tile.value} sub={pickText(tile.note, lang)} />
        ))}
      </div>

      <FindingsList findings={brief.findings} lang={lang} onOpenEvent={onOpenEvent} />

      <Card
        title={lang === "zh" ? "器械身份与官方申请" : "Device identity and official application"}
        note={
          lang === "zh"
            ? "MedRadar 标识是内部标识；FDA 官方标识单独展示并链接到官方页面。补充申请是同一已获批器械的版本。"
            : "MedRadar identifiers are internal; the official FDA identifier is shown separately and links to the official page. Supplements are versions of one approved device."
        }
      >
        <dl className="kv">
          <dt>{lang === "zh" ? "名称" : "Name"}</dt>
          <dd>{String(brief.device.name ?? "—")}</dd>
          <dt>{lang === "zh" ? "官方 FDA 标识" : "Official FDA identifier"}</dt>
          <dd className="mono">
            {application?.official_url ? (
              <a href={String(application.official_url)} target="_blank" rel="noreferrer">
                {String(application.official_id ?? "—")}
              </a>
            ) : (
              String(application?.official_id ?? "—")
            )}
          </dd>
          <dt>{lang === "zh" ? "申请人（记录原文）" : "Applicant as recorded"}</dt>
          <dd>{String(brief.device.applicant_name ?? "—")}</dd>
          <dt>{lang === "zh" ? "产品代码 / 等级" : "Product code / class"}</dt>
          <dd>
            <span className="mono">{String(brief.device.product_code ?? "—")}</span>
            {brief.device.device_class ? " · Class " + String(brief.device.device_class) : ""}
          </dd>
          <dt>{lang === "zh" ? "身份依据" : "Identity basis"}</dt>
          <dd>{brief.device.identity_basis_text ? String(brief.device.identity_basis_text) : String(brief.device.identity_basis ?? "—")}</dd>
          <dt>{lang === "zh" ? "已确认 / 候选关系" : "Confirmed / candidate relations"}</dt>
          <dd>
            {fmtNumber(brief.relations.confirmed_count)} / {fmtNumber(brief.relations.candidate_count)}
            <div className="tiny muted">{pickText(brief.relations.candidate_rule, lang)}</div>
          </dd>
        </dl>
      </Card>

      <Card
        title={lang === "zh" ? "官方申请历史" : "Official application history"}
        note={
          lang === "zh"
            ? `原始批准 + ${fmtNumber(brief.supplements_count)} 条补充申请。补充申请不是新器械。`
            : `Original approval + ${fmtNumber(brief.supplements_count)} supplement decisions. A supplement is not a new device.`
        }
      >
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>{lang === "zh" ? "官方标识" : "Official ID"}</th>
                <th>{lang === "zh" ? "决定日期" : "Decision date"}</th>
                <th>{lang === "zh" ? "类型" : "Type"}</th>
                <th>{lang === "zh" ? "补充原因 / 类型" : "Supplement reason / type"}</th>
                <th>{lang === "zh" ? "记录" : "Record"}</th>
              </tr>
            </thead>
            <tbody>
              {application ? (
                <tr>
                  <td className="mono">{String(application.official_id)}</td>
                  <td>{fmtDate(String(application.decision_date ?? ""))}</td>
                  <td>PMA</td>
                  <td className="small">{String(application.trade_name ?? application.device_name ?? "—")}</td>
                  <td>
                    <a className="link small" href={String(application.official_url)} target="_blank" rel="noreferrer">
                      {lang === "zh" ? "官方记录" : "Official record"}
                    </a>
                  </td>
                </tr>
              ) : null}
              {versions.slice(0, limit).map((row, index) => (
                <tr key={String(row.official_id ?? index)}>
                  <td className="mono">{String(row.official_id ?? "—")}</td>
                  <td>{fmtDate(String(row.decision_date ?? ""))}</td>
                  <td>{lang === "zh" ? "PMA 补充" : "PMA supplement"}</td>
                  <td className="small">{String(row.supplement_type ?? row.supplement_reason ?? "—")}</td>
                  <td>
                    {row.official_url ? (
                      <a className="link small" href={String(row.official_url)} target="_blank" rel="noreferrer">
                        {lang === "zh" ? "官方记录" : "Official record"}
                      </a>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {versions.length > limit ? (
          <button type="button" className="btn sm mt-8" onClick={() => setLimit((value) => value + 80)}>
            {lang === "zh" ? `再显示 80 条（共 ${fmtNumber(versions.length)} 条）` : `Show 80 more (of ${fmtNumber(versions.length)})`}
          </button>
        ) : null}
      </Card>

      <Card
        title={lang === "zh" ? "通过官方 K 号码关联的召回" : "Recalls linked by official K number"}
        note={pickText(brief.related_recalls.note, lang)}
      >
        {recalls.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{lang === "zh" ? "召回" : "Recall"}</th>
                  <th>{lang === "zh" ? "启动日期" : "Initiated date"}</th>
                  <th>{lang === "zh" ? "原因" : "Reason"}</th>
                  <th>{lang === "zh" ? "记录" : "Record"}</th>
                </tr>
              </thead>
              <tbody>
                {recalls.map((row, index) => (
                  <tr key={String(row.official_id ?? index)}>
                    <td className="mono">{String(row.official_id ?? "—")}</td>
                    <td>{fmtDate(String(row.initiated_date ?? row.event_date ?? ""))}</td>
                    <td className="small">{String(row.reason_for_recall ?? row.summary ?? "—").slice(0, 160)}</td>
                    <td>
                      {row.official_url ? (
                        <a className="link small" href={String(row.official_url)} target="_blank" rel="noreferrer">
                          {lang === "zh" ? "官方记录" : "Official record"}
                        </a>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="callout">
            {lang === "zh"
              ? "本快照中没有召回记录通过官方 K 号码字段关联到该申请。这不等于没有发生召回。"
              : "No recall record in this snapshot links to this application through its official K-number field. This is not evidence that no recall occurred."}
          </div>
        )}
        <div className="mt-8">
          <Link className="link small" to={brief.related_recalls.unlinked_url}>
            {lang === "zh" ? "打开未关联召回浏览器" : "Open the unlinked recall browser"}
          </Link>
        </div>
      </Card>

      <div className="grid cols-2">
        <Card title={lang === "zh" ? "时间线（官方决定日期）" : "Timeline (official decision dates)"}>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{lang === "zh" ? "日期" : "Date"}</th>
                  <th>{lang === "zh" ? "官方标识" : "Official ID"}</th>
                  <th>{lang === "zh" ? "类型" : "Type"}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {brief.timeline.slice(0, 40).map((row, index) => (
                  <tr key={String(row.event_id ?? index)}>
                    <td>{fmtDate(String(row.event_date ?? row.date ?? ""))}</td>
                    <td className="mono">{String(row.official_id ?? "—")}</td>
                    <td>{typeLabel(String(row.kind ?? ""), lang)}</td>
                    <td>
                      {row.event_id ? (
                        <button type="button" className="evidence-link" onClick={() => onOpenEvent(String(row.event_id))}>
                          {lang === "zh" ? "证据" : "Evidence"}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <ChangesBlock changes={brief.changes} lang={lang} />
      </div>

      <Limitations brief={brief} lang={lang} />

      <Card title={lang === "zh" ? "把成果带走" : "Take the work away"}>
        <div className="row wrap" style={{ gap: 10 }}>
          <a className="btn primary" href={briefMdUrl(routeToQuery(routeFromBrief(brief)), lang)}>
            {lang === "zh" ? "下载器械简报 (MD)" : "Download device brief (MD)"}
          </a>
          <a className="btn" href={briefEvidenceUrl(routeToQuery(routeFromBrief(brief)))}>
            {lang === "zh" ? "下载证据附录 (CSV)" : "Download evidence appendix (CSV)"}
          </a>
        </div>
        <div className="small muted mt-8">{pickText(brief.evidence.appendix.note, lang)}</div>
      </Card>
    </>
  );
}
