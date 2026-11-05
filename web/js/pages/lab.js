/* #/lab and #/lab/{study_id} — research lab: honest study statuses,
   findings, negative results, reproduction commands and frozen artifacts. */
import { api } from "../api.js";
import { el, fmtInt, fmtDate, fmtDateTime, buildHash, keyValueText, truncate } from "../util.js";
import {
  pageHead, panel, badge, dataTable, notice, list, errorState, skeletonBlock,
  linkButton, emptyState, kvList, disclosure, valueTable,
} from "../components.js";

const TONE_MAP = { blocked: "red", mixed: "amber", negative: "muted", positive: "green" };

const ARTIFACT_TITLES = {
  human_review: "人工复核状态",
  agent_pre_adjudication: "AI 预标注（agent-preliminary）",
  pilot: "Pilot 描述性结果",
  concurrent_detection: "同期检测（concurrent detection）",
  lead_time_small_sample: "提前量（小样本，描述性）",
  third_source: "第三方来源核查",
  five_firm_timeline: "五家企业进入时间线（hist_v1 冻结产物）",
  report: "研究产物",
  provenance: "产物来源（只读引用）",
  registered_forecasts: "已登记预测",
  prospective_set: "真正前瞻集合",
  calibration_claim_zh: "校准状态说明",
};

const ARTIFACT_ORDER = [
  "human_review", "agent_pre_adjudication", "pilot", "concurrent_detection",
  "lead_time_small_sample", "third_source", "five_firm_timeline", "report",
  "provenance", "registered_forecasts", "prospective_set", "calibration_claim_zh",
];

export async function mount(root, ctx) {
  if (ctx.params.studyId) return mountDetail(root, ctx);

  /* ------------------------------------------------------------- lab list */
  let data;
  let prospective = null;
  let prospectiveError = null;
  root.replaceChildren(skeletonBlock(8));
  try {
    data = await api.lab();
  } catch (error) {
    root.replaceChildren(errorState(error, () => ctx.refresh(), { title: "研究实验室加载失败" }));
    return { title: "研究实验室" };
  }
  /* The prospective registry is additive: its failure must never hide the lab. */
  try {
    prospective = await api.labProspective();
  } catch (error) {
    prospectiveError = error;
  }
  root.replaceChildren();

  const studies = data.studies || [];
  const provenance = data.provenance || {};

  root.append(pageHead({
    title: "研究实验室",
    subtitle: "只展示已验证、不确定与负面的研究状态；研究结论与产品观察结论严格分开，不把研究假设包装成产品预测。",
    captions: [
      { label: "研究", value: `${studies.length} 项` },
      { label: "数据截止", value: data.data_foundation?.data_edge || "—" },
      { label: "研究数据层", value: data.data_foundation?.store || "—" },
    ],
    actions: [linkButton("#/overview", "回到总览"), linkButton("#/radar", "技术雷达")],
  }));

  for (const key of Object.keys(provenance)) {
    const item = provenance[key] || {};
    if (item.merged === false) {
      root.append(notice({
        tone: "red",
        title: `未合入 main 的研究分支：${item.source_branch || key}`,
        label: "NOT MERGED",
        body: `${item.note_zh || "该分支只做只读引用，不合并其代码与结论。"}${item.source_commit ? `（commit ${item.source_commit}）` : ""}`,
      }));
    }
  }

  const grid = el("div", { class: "grid grid-2 mt-12" });
  for (const study of studies) {
    const card = el("a", { class: "lab-card", href: buildHash(`/lab/${study.id}`) });
    card.dataset.testid = "study-card";
    card.dataset.studyId = study.id;
    const head = el("div", { class: "row wrap between" },
      el("span", { class: "lab-title", text: study.title_zh }),
      badge(study.status_zh, TONE_MAP[study.status_tone] || "muted"),
    );
    card.append(head);
    card.append(el("div", { class: "muted tiny mono", text: `${study.id} · ${study.branch || ""}` }));
    card.append(el("div", { class: "lab-q", text: study.question_zh || "" }));
    const facts = el("div", { class: "row wrap muted tiny" });
    facts.append(
      el("span", { text: `周期：${study.period || "—"}` }),
      el("span", { text: `发现 ${fmtInt((study.findings_zh || []).length)} 条` }),
      el("span", { text: `限制 ${fmtInt((study.limits_zh || []).length)} 条` }),
      el("span", { text: study.has_artifacts ? `产物 ${fmtInt(Object.keys(study.artifacts || {}).length)} 项` : "无冻结产物" }),
    );
    card.append(facts);
    grid.append(card);
  }
  root.append(panel({ title: "研究状态", sub: "点击卡片查看问题、方法、发现、负面结果与产物", body: grid }));

  if (data.data_foundation) {
    root.append(panel({
      title: "研究数据层",
      sub: data.data_foundation.note_zh || "",
      body: kvList([
        { key: "store", value: data.data_foundation.store || "—" },
        { key: "data_edge", value: data.data_foundation.data_edge || "—" },
      ]),
    }));
  }
  if ((data.policy_zh || []).length) {
    root.append(panel({ title: "实验室政策", sub: "研究状态的展示规则", body: list(data.policy_zh) }));
  }

  /* Clearly separated, additive section: frozen prospective observations. */
  root.append(renderProspectiveRegistry({ data: prospective, error: prospectiveError, ctx }));

  return { title: "研究实验室" };
}

/* ------------------------------------------------------------ study detail */
async function mountDetail(root, ctx) {
  const studyId = ctx.params.studyId;
  root.replaceChildren(skeletonBlock(8));
  let study;
  let globalProvenance = {};
  try {
    [study, globalProvenance] = await Promise.all([
      api.labStudy(studyId),
      api.lab().then((payload) => payload.provenance || {}).catch(() => ({})),
    ]);
  } catch (error) {
    root.replaceChildren(errorState(error, () => ctx.refresh(), { title: "研究详情加载失败" }));
    return { title: "研究详情" };
  }
  root.replaceChildren();

  const wrapper = el("div");
  wrapper.dataset.testid = "lab-detail";
  root.append(wrapper);

  const artifacts = study.artifacts || {};
  const provenance = artifacts.provenance || globalProvenance[studyId] || {};
  const statusTone = TONE_MAP[study.status_tone] || "muted";

  wrapper.append(pageHead({
    kicker: el("span", null,
      el("a", { href: "#/lab", text: "研究实验室" }),
      el("span", { class: "sep", text: "/" }),
      el("span", { text: study.id || studyId }),
    ),
    title: study.title_zh || studyId,
    badges: [
      badge(study.status_zh || "—", statusTone),
      study.branch ? badge(study.branch, "muted") : null,
      study.period ? badge(study.period, "muted") : null,
    ].filter(Boolean),
    subtitle: study.title_en || "",
    captions: [
      { label: "研究问题", value: study.question_zh || "—" },
      { label: "周期", value: study.period || "—" },
    ],
    actions: [linkButton(buildHash("/lab", {}), "返回研究列表")],
  }));

  /* provenance warning */
  const provenanceMerged = provenance.merged;
  if (provenanceMerged === false) {
    wrapper.append(notice({
      tone: "red",
      title: "该研究分支未合入 main，本页只读引用其冻结产物",
      label: "NOT MERGED",
      body: `${provenance.note_zh || ""} ${provenance.source_branch ? `分支：${provenance.source_branch}` : ""}${provenance.source_commit ? ` @ ${provenance.source_commit}` : ""}${provenance.artifact ? ` · 产物：${provenance.artifact}` : ""}`,
    }));
  }

  /* question / method */
  wrapper.append(panel({
    title: "研究问题与方法",
    sub: "研究回答「是否可能提前」，产品只陈述「记录中观察到什么」",
    body: [
      el("div", { class: "section-title", text: "问题" }),
      el("div", { class: "small", text: study.question_zh || "—" }),
      el("div", { class: "section-title mt-12", text: "方法" }),
      el("div", { class: "small", text: study.method_zh || "—" }),
    ],
  }));

  /* findings + negative results */
  const findingsGrid = el("div", { class: "grid grid-2 mt-12" });
  findingsGrid.append(panel({
    title: "研究结果",
    sub: "原文列出的发现（含不确定与负面结果）",
    body: list(study.findings_zh || []),
  }));
  findingsGrid.append(panel({
    title: "负面结果与限制",
    sub: "该研究明确声明不可用的结论",
    body: [
      list(study.limits_zh || []),
      (study.datasets_zh || []).length ? el("div", { class: "mt-12" }, el("div", { class: "section-title", text: "数据集" }), list(study.datasets_zh)) : null,
    ].filter(Boolean),
  }));
  wrapper.append(findingsGrid);

  /* reproduce */
  if ((study.reproduce_zh || []).length) {
    const pre = el("pre", { class: "code-block", text: study.reproduce_zh.join("\n") });
    wrapper.append(panel({
      title: "复现命令与研究材料",
      sub: "按研究材料原样展示，未做改写",
      body: pre,
    }));
  }

  /* artifacts */
  const keys = [
    ...ARTIFACT_ORDER.filter((key) => artifacts[key] != null),
    ...Object.keys(artifacts).filter((key) => !ARTIFACT_ORDER.includes(key) && artifacts[key] != null),
  ];
  if (keys.length) {
    const artifactGrid = el("div", { class: "artifact-grid" });
    for (const key of keys) {
      artifactGrid.append(panel({
        title: ARTIFACT_TITLES[key] || key,
        sub: key,
        body: renderArtifact(key, artifacts[key]),
      }));
    }
    wrapper.append(el("div", { class: "mt-12" }, panel({
      title: "冻结产物",
      sub: "研究实验产物原样引用，不作为产品结论",
      body: artifactGrid,
    })));
  } else {
    wrapper.append(panel({ title: "冻结产物", body: emptyState("该研究没有冻结产物。", { title: "无产物" }) }));
  }

  /* cross links */
  const crossLinks = study.cross_links || {};
  if (crossLinks.note_zh) {
    wrapper.append(panel({
      title: "研究结论与产品观察的边界",
      sub: crossLinks.note_zh,
      body: (crossLinks.related_views || []).length
        ? el("div", { class: "row wrap" }, ...(crossLinks.related_views || []).map((href) => linkButton(buildHash(href), href)))
        : null,
    }));
  }

  return { title: `${study.title_zh || studyId} · 研究` };
}

/* ---------------------------------------------------------- artifacts */
function renderArtifact(key, value) {
  if (key === "five_firm_timeline") return renderFiveFirmTimeline(value);
  if (key === "human_review") return renderHumanReview(value);
  return artifactValue(value);
}

function renderFiveFirmTimeline(value) {
  const node = el("div");
  const cases = value.cases || [];
  node.append(kvList([
    { key: "schema", value: value.schema || "—" },
    { key: "n_companies", value: fmtInt(value.n_companies) },
    { key: "n_tracks", value: fmtInt(value.n_tracks) },
    { key: "note_zh", value: value.note_zh || "—" },
  ]));
  node.append(el("div", { class: "mt-8" }, dataTable({
    columns: [
      { key: "display_name", label: "企业", format: (row) => el("span", null, el("b", { text: row.display_name || row.company }), el("span", { class: "muted tiny", text: `  ${row.company}` })) },
      { key: "cohort", label: "队列", format: (row) => row.cohort || "—" },
      { key: "material_events", label: "material events", num: true, format: (row) => fmtInt(row.material_events) },
      { key: "tracks_entered", label: "进入赛道", num: true, format: (row) => fmtInt(row.tracks_entered) },
      { key: "first_entry", label: "首次进入", format: (row) => row.first_entry || "—" },
      { key: "last_entry", label: "最近进入", format: (row) => row.last_entry || "—" },
      { key: "eras", label: "按年代", format: (row) => Object.entries(row.entries_by_era || {}).map(([era, count]) => `${era}:${count}`).join(" · ") || "—" },
    ],
    rows: cases,
    empty: "没有企业进入记录",
  })));
  for (const item of cases) {
    if (!(item.entries || []).length) continue;
    node.append(disclosure(`${item.display_name || item.company} · 进入明细（${item.entries.length} 条）`, dataTable({
      columns: [
        { key: "entry_quarter", label: "季度", format: (row) => row.entry_quarter || "—" },
        { key: "track", label: "赛道", format: (row) => row.track || "—" },
        { key: "category", label: "类别", format: (row) => row.category || "—" },
        { key: "material_events", label: "material events", num: true, format: (row) => fmtInt(row.material_events) },
        { key: "co_entrant", label: "4 季度内同进入", format: (row) => ((row.co_entrant_firms_within_4q || []).length ? (row.co_entrant_firms_within_4q || []).join("、") : "—") },
      ],
      rows: item.entries,
      compact: true,
    })));
  }
  return node;
}

function renderHumanReview(value) {
  const node = el("div");
  const labels = value.agent_preliminary_labels || {};
  node.append(kvList([
    { key: "证据包", value: fmtInt(value.packets) },
    { key: "已记录人工标签", value: fmtInt(value.human_labels_recorded) },
    { key: "状态", value: value.status || "—" },
    { key: "工作表", value: value.worksheet || "—" },
    { key: "note_zh", value: value.note_zh || "—" },
  ]));
  if (Object.keys(labels).length) {
    node.append(el("div", { class: "section-title mt-8", text: "agent-preliminary 标签分布（不是人工真值）" }));
    node.append(kvList(Object.entries(labels).map(([label, count]) => ({ key: label, value: fmtInt(count) }))));
  }
  node.append(notice({ tone: "amber", title: "AI 预标注不是人工真值", body: "这些标签不得用于给研究检测器打分，也不得用于宣称 Target B 结论。" }));
  return node;
}

function artifactValue(value, depth = 0) {
  if (value == null) return el("span", { class: "muted", text: "—" });
  if (typeof value !== "object") {
    return el("div", { class: "small", text: keyValueText(value) });
  }
  if (Array.isArray(value)) {
    if (!value.length) return el("span", { class: "muted", text: "（空）" });
    if (value.every((item) => item == null || typeof item !== "object")) {
      return el("div", { class: "chip-row" }, ...value.map((item) => badge(keyValueText(item), "muted")));
    }
    const keys = [];
    for (const item of value.slice(0, 40)) {
      if (!item || typeof item !== "object") continue;
      for (const [key, cell] of Object.entries(item)) {
        if (!keys.includes(key) && (cell == null || typeof cell !== "object")) keys.push(key);
      }
    }
    return dataTable({
      columns: keys.map((key) => ({
        key,
        label: key,
        format: (row) => {
          const cell = row[key];
          if (cell == null) return "—";
          return truncate(keyValueText(cell), 160);
        },
      })),
      rows: value,
      compact: true,
    });
  }
  const scalars = [];
  const complex = [];
  for (const [key, item] of Object.entries(value)) {
    if (item == null || typeof item !== "object") scalars.push({ key, value: keyValueText(item) });
    else complex.push([key, item]);
  }
  const node = el("div");
  if (scalars.length) node.append(kvList(scalars));
  if (depth > 2) {
    node.append(disclosure("原始结构", valueTable(value)));
    return node;
  }
  for (const [key, item] of complex) {
    const isTable = Array.isArray(item) && item.length && typeof item[0] === "object";
    if (isTable) {
      node.append(el("div", { class: "section-title mt-8", text: key }));
      node.append(artifactValue(item, depth + 1));
    } else {
      node.append(disclosure(key, artifactValue(item, depth + 1)));
    }
  }
  return node;
}

/* ------------------------------------- prospective observation registry
   Additive Research Lab section. The registry freezes a hypothesis together with
   the ledger's point-in-time evidence snapshot BEFORE outcomes are observable and
   later reports the outcome from append-only appendices. It is NOT a prediction
   engine: no probability, no score, no calibration. Synthetic fixtures are
   explicitly labelled 合成测试 and never presented as evidence. */
const PROSPECTIVE_STATUS_TONES = {
  EXPERIMENTAL: "violet",
  ACTIVE: "blue",
  DUE: "amber",
  MATURED: "green",
  RETRACTED: "red",
};

function prospectiveStatusBadge(entry) {
  const status = entry.status || "EXPERIMENTAL";
  return badge(
    entry.status_label_zh || status,
    PROSPECTIVE_STATUS_TONES[status] || "muted",
    `status: ${status}`,
  );
}

function prospectiveIdentityBadges(entry) {
  const row = el("span", { class: "badge-row" });
  row.append(prospectiveStatusBadge(entry));
  if (entry.synthetic) {
    row.append(badge("合成测试", "amber", "该条目由测试构造，不是真实的前瞻观察结果"));
  }
  row.append(entry.frozen_verified
    ? badge("冻结哈希校验通过", "green", entry.content_sha256 || "")
    : badge("冻结哈希校验失败", "red", "冻结文档可能已被改写；评估会被拒绝"));
  return row;
}

function prospectiveCount(value, hint = null) {
  return el("span", { title: hint || null, text: fmtInt(value) });
}

function renderProspectiveRegistry({ data, error, ctx }) {
  const node = el("div", { class: "mt-12" });
  node.dataset.testid = "prospective-registry";
  const right = [badge("非预测引擎", "muted"), badge("EXPERIMENTAL", "violet")];
  const body = el("div");

  if (error) {
    body.append(notice({
      tone: "amber",
      title: "前瞻观察登记器暂不可用",
      label: "REGISTRY",
      body: `登记器接口读取失败：${error && error.message ? error.message : String(error)}。研究实验室其余内容不受影响。`,
    }));
    body.append(el("div", { class: "mt-8" }, el("button", {
      type: "button",
      class: "btn btn-sm",
      text: "重试",
      onclick: () => ctx.refresh(),
    })));
    node.append(panel({
      title: "前瞻观察登记 / Prospective Observation Registry",
      sub: "冻结假设与冻结证据的可审计登记器；不是预测引擎",
      right,
      body,
    }));
    return node;
  }

  const registry = (data && data.registry) || {};
  const entries = (data && data.entries) || [];
  const statusCounts = registry.status_counts || {};

  body.append(notice({
    tone: "amber",
    title: "这是一个可审计的登记器，不是预测引擎",
    label: "NOT A FORECAST",
    body: "条目在假设冻结后才报告声明窗口内新观察到的候选证据；不给出概率、评分、校准误差或已验证结论。默认状态 EXPERIMENTAL，合成测试条目只用于测试机制。",
  }));

  body.append(el("div", { class: "mt-8" }, kvList([
    { key: "登记目录", value: registry.path || "—" },
    { key: "冻结条目", value: fmtInt(registry.entry_count) },
    {
      key: "状态分布",
      value: Object.keys(statusCounts).length
        ? Object.entries(statusCounts).map(([key, count]) => `${key}:${fmtInt(count)}`).join(" · ")
        : "—",
    },
    { key: "合成测试条目", value: fmtInt(registry.synthetic_count) },
    { key: "已到期并评估", value: fmtInt(registry.matured_count) },
    { key: "完整性异常", value: fmtInt(registry.integrity_issues) },
  ])));
  if (registry.notice_zh) body.append(el("div", { class: "muted tiny mt-8", text: registry.notice_zh }));

  if (!entries.length) {
    body.append(el("div", { class: "mt-12" }, emptyState(
      (data && data.empty_zh) || "登记器尚未冻结任何条目；这里不会显示示例或伪造的前瞻结果。",
      { title: "暂无可审计的前瞻登记" },
    )));
  } else {
    body.append(el("div", { class: "mt-12" }, dataTable({
      columns: [
        {
          key: "entry_id",
          label: "条目",
          format: (row) => el("span", null,
            el("b", { text: row.entry_id }),
            el("span", { class: "muted tiny", text: `  ${truncate(row.label_zh || "", 60)}` }),
            el("div", { class: "muted tiny", text: truncate(row.hypothesis_zh || "—", 120) }),
          ),
        },
        { key: "freeze_at", label: "冻结时间", format: (row) => fmtDateTime(row.freeze_at) },
        {
          key: "window",
          label: "声明窗口",
          format: (row) => el("span", {
            class: "mono tiny",
            text: `${row.window_start || "—"} → ${row.window_end || "—"}`,
          }),
        },
        { key: "target_event_definition_zh", label: "目标事件定义", format: (row) => truncate(row.target_event_definition_zh || "—", 90) },
        { key: "baseline_zh", label: "基线", format: (row) => truncate(row.baseline_zh || "—", 70) },
        { key: "evaluation_criteria_zh", label: "判据", format: (row) => truncate(row.evaluation_criteria_zh || "—", 70) },
        { key: "status", label: "状态 / 标识", format: (row) => prospectiveIdentityBadges(row) },
        {
          key: "frozen_evidence_count",
          label: "冻结证据",
          num: true,
          format: (row) => prospectiveCount(
            row.frozen_evidence_count,
            row.frozen_evidence_as_of ? `as_of ${row.frozen_evidence_as_of}` : null,
          ),
        },
        {
          key: "evaluation_count",
          label: "评估",
          num: true,
          format: (row) => {
            const latest = row.latest_evaluation;
            const suffix = latest ? `（候选结局 ${fmtInt(latest.outcomes_count)}）` : "";
            return el("span", { text: `${fmtInt(row.evaluation_count)}${suffix}` });
          },
        },
      ],
      rows: entries,
      rowAttrs: (row) => ({ testid: "prospective-row", dataset: { entryId: row.entry_id } }),
      empty: "没有登记条目",
    })));

    for (const entry of entries) body.append(renderProspectiveHistory(entry));
  }

  if (((data && data.policy_zh) || []).length) {
    body.append(el("div", { class: "mt-12" }, list(data.policy_zh)));
  }
  const validation = (data && data.validation) || {};
  body.append(el("div", {
    class: "muted tiny mt-8",
    text: validation.note_zh || "本接口不返回概率、评分或校准结论。",
  }));

  node.append(panel({
    title: "前瞻观察登记 / Prospective Observation Registry",
    sub: "冻结假设、冻结证据与声明窗口的可审计登记器；不是预测引擎",
    right,
    body,
  }));
  return node;
}

function renderProspectiveHistory(entry) {
  const history = entry.evaluation_history || [];
  const node = el("div", { class: "mt-8" });
  const content = el("div");
  content.append(kvList([
    { key: "冻结证据数", value: fmtInt(entry.frozen_evidence_count) },
    { key: "冻结证据时点（as_of）", value: entry.frozen_evidence_as_of || "—" },
    { key: "冻结文档哈希", value: entry.content_sha256 ? `${String(entry.content_sha256).slice(0, 24)}…` : "—" },
    { key: "冻结完整性", value: entry.frozen_verified ? "冻结文档哈希校验通过" : "校验失败：冻结文档可能已被改写" },
    { key: "状态说明", value: entry.status_note_zh || "—" },
  ]));
  if (!history.length) {
    content.append(notice({
      tone: "muted",
      title: "尚无评估附录",
      body: "窗口结束前不会产生评估结果；窗口结束后按冻结时声明的判据统计候选证据。",
    }));
  } else {
    content.append(el("div", { class: "section-title mt-8", text: "评估历史（append-only 附录）" }));
    content.append(dataTable({
      columns: [
        { key: "evaluation_seq", label: "#", num: true, format: (row) => fmtInt(row.evaluation_seq) },
        { key: "computed_at", label: "计算时间", format: (row) => fmtDateTime(row.computed_at) },
        { key: "inputs_count", label: "冻结输入", num: true, format: (row) => fmtInt(row.inputs_count) },
        { key: "outcomes_count", label: "窗口内新观察", num: true, format: (row) => fmtInt(row.outcomes_count) },
        { key: "new_version_count", label: "输入修订", num: true, format: (row) => fmtInt(row.new_version_count) },
        {
          key: "ledger_counts",
          label: "评估时账本",
          format: (row) => {
            const counts = row.ledger_counts || {};
            return el("span", {
              class: "mono tiny",
              text: `obs ${fmtInt(counts.observations)} · ver ${fmtInt(counts.versions)}`,
            });
          },
        },
        {
          key: "classification",
          label: "判定",
          format: (row) => (row.human_classification_required
            ? badge("需人工判定", "muted", "登记器不自动判定目标事件是否发生")
            : (row.classification || "—")),
        },
      ],
      rows: history,
      compact: true,
    }));
  }
  if (entry.synthetic) {
    content.append(notice({
      tone: "amber",
      title: "合成测试条目",
      body: "该条目只用于测试登记器机制，不是真实的前瞻观察结果；不得引用为证据。",
    }));
  }
  node.append(disclosure(`冻结输入与评估历史 · ${entry.entry_id}`, content));
  return node;
}
