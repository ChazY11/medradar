/* #/analyst — deterministic retrieval engine front-end. The badge
   “确定性检索引擎（无 LLM）” is always visible; never presented as an LLM. */
import { api } from "../api.js";
import { el, fmtDate, buildHash } from "../util.js";
import {
  pageHead, panel, badge, dataTable, notice, list, errorState, skeletonBlock,
  disclosure, emptyState, textButton, chip,
} from "../components.js";
import { openEvent } from "../event.js";

const STATUS_META = {
  answered: { label: "已回答", tone: "green" },
  needs_clarification: { label: "需要澄清", tone: "amber" },
  out_of_scope: { label: "超出范围", tone: "red" },
  not_ready: { label: "引擎未就绪", tone: "amber" },
};

const SPAN_KIND_LABEL = {
  time: "时间窗",
  company: "企业",
  track: "赛道",
  metric: "指标",
  compare: "对比",
  acceleration: "加速",
  record_lookup: "记录检索",
};

export async function mount(root, ctx) {
  const answerHost = el("div");
  answerHost.dataset.testid = "analyst-answer";
  const input = el("textarea", {
    class: "analyst-input",
    rows: 2,
    maxlength: 300,
    placeholder: "用中文提问，例如：过去五年，迈瑞的超声产品发生了什么变化？",
    "aria-label": "研究问题",
  });
  input.dataset.testid = "analyst-input";
  const submit = textButton("提问", () => run(input.value), { primary: true, small: false, testid: "analyst-submit" });
  const chipsRow = el("div", { class: "chip-row mt-8" });
  const capabilitiesHost = el("div");
  let examples = [];

  root.append(pageHead({
    title: "研究助手",
    badges: [badge("确定性检索引擎（无 LLM）", "blue", "不使用大模型、不需要 API Key；所有结论来自数据库查询")],
    subtitle: "把自然语言问题解析成企业 / 赛道 / 时间窗 / 指标，执行确定性检索与统计计算，并给出可打开的事件证据。",
    captions: [
      { label: "解析对象", value: "企业 · 赛道 · 时间窗 · 指标" },
      { label: "输出", value: "答案 + 章节 + 证据事件 + 限制" },
      { label: "不做", value: "因果推断 · 未经验证的预测" },
    ],
    actions: [el("a", { class: "btn", href: "#/evidence", text: "直接检索证据" })],
  }));

  const formBody = el("div");
  formBody.append(
    el("div", { class: "analyst-form" }, input, submit),
    chipsRow,
    el("div", { class: "muted tiny mt-8", text: "示例问题来自 API 的 analyst_examples；点击示例会立即执行确定性检索。" }),
  );
  root.append(panel({
    title: "提出问题",
    sub: "最多 300 字；解析结果会以「解析意图」展示，避免黑箱",
    body: formBody,
  }));

  const grid = el("div", { class: "grid grid-sidebar mt-12" });
  grid.append(answerHost);
  grid.append(panel({
    title: "能力与边界",
    sub: "研究助手能做什么、不能做什么",
    body: capabilitiesHost,
  }));
  root.append(grid);

  answerHost.replaceChildren(emptyState("输入问题或点击上方示例开始。", {
    title: "尚未提问",
    actionLabel: "打开证据浏览器",
    onAction: () => ctx.go("/evidence"),
  }));

  async function run(question) {
    const value = String(question || "").trim();
    if (!value) {
      answerHost.replaceChildren(emptyState("请先输入一个具体问题。", { title: "问题为空" }));
      return;
    }
    input.value = value;
    ctx.replaceUrl({ q: value });
    answerHost.replaceChildren(panel({ title: "检索中", body: skeletonBlock(6) }));
    submit.disabled = true;
    try {
      const payload = await api.analystAsk(value);
      answerHost.replaceChildren(renderAnswer(payload, { run }));
    } catch (error) {
      answerHost.replaceChildren(panel({
        title: "检索失败",
        body: errorState(error, () => run(value), { title: "研究助手请求失败" }),
      }));
    } finally {
      submit.disabled = false;
    }
  }

  /* --------------------------------------------------------- examples */
  try {
    const meta = await api.analystExamples();
    examples = meta.examples || [];
    for (const example of examples) {
      const node = chip(example, { testid: "analyst-example", title: "点击立即提问", onClick: () => run(example) });
      chipsRow.append(node);
    }
    capabilitiesHost.replaceChildren(renderCapabilities(meta));
  } catch (error) {
    capabilitiesHost.replaceChildren(errorState(error, () => ctx.refresh(), { title: "能力说明加载失败" }));
  }

  const preset = ctx.query.get("q");
  if (preset) run(preset);

  return { title: "研究助手" };
}

function renderCapabilities(meta) {
  const capabilities = meta.capabilities || {};
  const node = el("div");
  node.append(el("div", { class: "row wrap mb-8" },
    badge(meta.mode === "deterministic" ? "确定性检索引擎（无 LLM）" : (meta.mode || "确定性"), "blue"),
  ));
  if (meta.mode_zh) node.append(el("div", { class: "muted small mb-8", text: meta.mode_zh }));
  if ((capabilities.can_zh || []).length) {
    node.append(el("div", { class: "section-title mt-8", text: "可以做" }), list(capabilities.can_zh));
  }
  if ((capabilities.cannot_zh || []).length) {
    node.append(el("div", { class: "section-title mt-8", text: "不能做" }), list(capabilities.cannot_zh));
  }
  return node;
}

function renderAnswer(payload, { run }) {
  const status = payload.status || "answered";
  const statusMeta = STATUS_META[status] || { label: status, tone: "muted" };
  const container = el("div");

  /* header */
  const head = el("div", { class: "row wrap between" });
  head.append(
    el("div", { class: "row wrap" },
      badge(statusMeta.label, statusMeta.tone),
      badge("确定性检索引擎（无 LLM）", "blue"),
    ),
    el("span", { class: "muted tiny mono", text: payload.question || "" }),
  );
  container.append(head);

  if (payload.mode_zh || payload.mode) {
    container.append(el("div", { class: "muted small mt-8", text: payload.mode_zh || `mode: ${payload.mode}` }));
  }

  /* not ready */
  if (status === "not_ready") {
    container.append(notice({
      tone: "amber",
      title: "研究助手引擎尚未接入本轮构建",
      label: "not_ready",
      body: payload.answer_zh || "接口已就绪，解析与检索引擎尚未上线；本页不会用占位答案冒充结论。",
    }));
    container.append(el("div", { class: "muted small mt-8", text: "在引擎接入之前，可以直接使用证据浏览器与对比页完成同样口径的检索：" }));
    container.append(el("div", { class: "row wrap mt-8" },
      el("a", { class: "btn", href: "#/evidence", text: "证据浏览器" }),
      el("a", { class: "btn", href: "#/compare", text: "企业对比" }),
      el("a", { class: "btn", href: "#/radar", text: "技术雷达" }),
      el("a", { class: "btn", href: "#/companies", text: "企业画像" }),
    ));
  } else {
    /* intent */
    if (payload.intent) container.append(renderIntent(payload.intent));
    /* answer */
    if (payload.answer_zh) container.append(el("div", { class: "answer-text mt-12", text: payload.answer_zh }));
    /* sections */
    if ((payload.sections || []).length) container.append(renderSections(payload.sections));
    /* evidence */
    if ((payload.evidence || []).length) container.append(renderEvidence(payload.evidence));
    /* limitations */
    if ((payload.limitations || []).length) {
      container.append(el("div", { class: "section-block" },
        el("div", { class: "section-title", text: `引擎返回的限制（limitations 字段，${payload.limitations.length} 条）` }),
        list(payload.limitations),
      ));
    }
    /* computation */
    if (payload.computation_zh) {
      container.append(el("div", { class: "section-block" }, disclosure("计算过程", el("div", { class: "mono small", text: payload.computation_zh }))));
    }
    /* followups */
    if ((payload.followups || []).length) {
      container.append(el("div", { class: "section-block" },
        el("div", { class: "section-title", text: status === "needs_clarification" ? "请选择一个澄清方向" : "可以继续追问" }),
        el("div", { class: "chip-row" },
          ...payload.followups.map((text) => chip(text, {
            testid: "analyst-followup",
            onClick: () => run(text),
          })),
        ),
      ));
    }
    if (status === "needs_clarification" && !(payload.followups || []).length) {
      container.append(notice({ tone: "amber", title: "需要更具体的问题", body: "请补充企业、赛道或时间窗。" }));
    }
    if (status === "out_of_scope") {
      container.append(notice({
        tone: "red",
        title: "该问题超出确定性检索引擎的范围",
        body: "研究助手只回答可由数据库检索与统计计算支撑的问题；不做因果推断、不做未经验证的预测。",
      }));
    }
  }

  return panel({
    title: "检索结果",
    sub: `状态：${statusMeta.label} · 引擎：确定性检索引擎（无 LLM）`,
    body: container,
  });
}

function renderIntent(intent) {
  const block = el("div");
  block.dataset.testid = "analyst-intent";
  block.append(el("div", { class: "section-title", text: `解析意图：${intent.label_zh || intent.type || "—"}` }));
  const parsed = intent.parsed || {};
  const names = (list, pick) => (Array.isArray(list) ? list : [])
    .map((item) => (typeof item === "string" ? item : pick(item)))
    .filter(Boolean);

  const companyNames = names(parsed.companies, (item) => item.name_zh || item.key);
  const companyKeys = Array.isArray(parsed.company_keys) ? parsed.company_keys : [];
  const trackNames = names(parsed.tracks, (item) => item.label_zh || item.name_zh || item.id);
  const trackIds = Array.isArray(parsed.track_ids) ? parsed.track_ids : [];
  const windowInfo = parsed.window || null;
  const windowText = windowInfo && (windowInfo.start || windowInfo.end)
    ? `${windowInfo.start || "—"} → ${windowInfo.end || "—"}（对照 ${windowInfo.prior_start || "—"} → ${windowInfo.prior_end || "—"}）`
    : parsed.years == null ? "—" : `${parsed.years} 年`;

  const grid = el("div", { class: "intent-grid" });
  const entries = [
    ["企业", companyNames.length ? companyNames.join("、") : (companyKeys.length ? companyKeys.join("、") : "—")],
    ["赛道", trackNames.length ? trackNames.join("、") : (trackIds.length ? trackIds.join("、") : "—")],
    ["时间窗", windowText],
    ["指标", parsed.metric_label_zh || parsed.metric || "—"],
  ];
  for (const [label, value] of entries) {
    grid.append(el("div", { class: "intent-cell" },
      el("div", { class: "l", text: label }),
      el("div", { class: "v", text: String(value) }),
    ));
  }
  block.append(grid);

  if (Array.isArray(parsed.spans) && parsed.spans.length) {
    const spanRow = el("div", { class: "chip-row mt-8" });
    for (const span of parsed.spans) {
      const kindLabel = SPAN_KIND_LABEL[span.kind] || span.kind || "";
      spanRow.append(badge(`「${span.text || ""}」· ${kindLabel}`, "muted", span.kind || null));
    }
    block.append(spanRow);
  }

  if (Array.isArray(parsed.companies) && parsed.companies.some((item) => item && item.matched != null)) {
    const matchRow = el("div", { class: "row wrap mt-8" });
    for (const item of parsed.companies) {
      if (!item || typeof item === "string") continue;
      const matched = typeof item.matched === "string" ? ` · 匹配「${item.matched}」` : "";
      matchRow.append(badge(`${item.name_zh || item.key}${item.matched === false ? " · 未匹配" : matched}`, item.matched === false ? "amber" : "teal"));
    }
    block.append(matchRow);
  }

  block.append(el("div", { class: "muted tiny mt-4", text: "解析结果直接决定检索参数；它不是自然语言生成，不做语义改写。" }));
  return block;
}

function renderSections(sections) {
  const wrap = el("div", { class: "section-block" });
  for (const section of sections) {
    const block = el("div", { class: "section-block" });
    block.append(el("div", { class: "section-title", text: section.title_zh || "章节" }));
    if (section.body_zh) block.append(el("div", { class: "small", text: section.body_zh }));
    if (section.table && section.table.columns && section.table.rows) {
      const rows = section.table.rows.map((row) => {
        const object = {};
        row.forEach((value, index) => { object[index] = value; });
        return object;
      });
      block.append(el("div", { class: "mt-8" }, dataTable({
        columns: section.table.columns.map((label, index) => ({ key: String(index), label: String(label) })),
        rows,
        compact: true,
      })));
    }
    if (section.bullets && section.bullets.length) block.append(list(section.bullets));
    wrap.append(block);
  }
  return wrap;
}

function renderEvidence(evidence) {
  const wrap = el("div", { class: "section-block" });
  wrap.append(el("div", { class: "section-title", text: `证据事件（${evidence.length} 条，点击打开原始记录）` }));
  const listNode = el("div", { class: "evidence-list" });
  for (const item of evidence) {
    const row = el("button", { type: "button", class: "evidence-row" });
    row.dataset.testid = "analyst-evidence";
    row.dataset.eventId = item.event_id;
    row.append(...[
      el("span", { class: "d", text: fmtDate(item.event_date) }),
      el("span", { class: "t", text: item.title || item.event_id }),
      el("span", { class: "muted tiny", text: [item.company_name_zh, item.track_name_zh].filter(Boolean).join(" · ") }),
      item.why_zh ? el("span", { class: "why", text: item.why_zh, title: item.why_zh }) : null,
    ].filter(Boolean));
    row.addEventListener("click", () => openEvent(item.event_id));
    listNode.append(row);
  }
  wrap.append(listNode);
  return wrap;
}
