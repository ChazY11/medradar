/* #/observatory — Live Observatory: what MedRadar actually observed, and when.
   Honesty rules (docs/LIVE_OBSERVATORY_DESIGN.md §8) are enforced here:
   * event time, source publish time and MedRadar first-seen time are three
     separate statements and are never merged into one date;
   * a measured lag is shown only when time_basis.measurable, otherwise
     "无法测量" plus the reason;
   * NEW / UPDATED / REMOVED_OR_UNAVAILABLE / FETCH_FAILED stay four claims;
   * a polled source is described as 轮询 + declared cadence, never "实时";
   * with no ledger the page shows an explicit empty state, never fake events. */
import { api } from "../api.js";
import { el, fmtInt, fmtDateTime, fmtNum, fmtPct } from "../util.js";
import {
  pageHead, panel, badge, dataTable, notice, errorState, skeletonBlock, emptyState,
  codeBlock, kvList, textButton, chip, linkButton, openDrawer, disclosure,
} from "../components.js";

const WINDOW_OPTIONS = [
  { id: "24h", label: "24 小时" },
  { id: "7d", label: "7 天" },
  { id: "30d", label: "30 天" },
];
const CHANGE_OPTIONS = [
  { id: "all", label: "全部", state: null },
  { id: "new", label: "新增", state: "NEW" },
  { id: "updated", label: "修订", state: "UPDATED" },
  { id: "removed", label: "不再提供", state: "REMOVED_OR_UNAVAILABLE" },
  { id: "failed", label: "采集失败", state: "FETCH_FAILED" },
];
const CHANGE_LABELS = {
  NEW: "新增",
  UPDATED: "修订",
  REMOVED_OR_UNAVAILABLE: "不再提供",
  FETCH_FAILED: "采集失败",
};
const CHANGE_TONES = {
  NEW: "green",
  UPDATED: "amber",
  REMOVED_OR_UNAVAILABLE: "muted",
  FETCH_FAILED: "red",
};
const MAPPING_TONES = {
  MAPPED: "green",
  PENDING_REVIEW: "amber",
  UNMAPPED: "muted",
  AMBIGUOUS: "red",
};
const SOURCE_STATUS_TONES = {
  OK: "green",
  DEGRADED: "amber",
  FAILED: "red",
  NEVER_RUN: "muted",
  PAUSED: "amber",
};
const RUN_LABELS = {
  RUNNING: "运行中",
  OK: "成功",
  PARTIAL: "部分成功",
  FAILED: "失败",
  INTERRUPTED: "中断",
  SKIPPED: "跳过",
};
const COVERAGE_TONES = {
  COVERED: "green",
  NOT_REGISTRANT: "muted",
  NOT_CURRENT_REGISTRANT: "amber",
  UNVERIFIED: "red",
};
/* ------------------------------------------------- observatory health words */
/* The five words are a closed vocabulary (docs/RELIABILITY_DESIGN.md §0). The UI
   never invents a sixth word and never shows a green badge while a component is
   failing: the per-source table below carries its own FAILED / stale / alert
   badges even when the overall word is NOT_DEPLOYED. */
const HEALTH_WORDS = {
  OPERATIONAL: {
    label: "运行正常",
    tone: "green",
    meaning: "已记录经过验证的部署，全部来源健康且新鲜，最近备份已验证、最近恢复演练成功，七天验证已完成并通过。",
  },
  DEGRADED: {
    label: "降级运行",
    tone: "amber",
    meaning: "至少一个组件不健康：来源失败或过期、存在未解决结构告警、备份或恢复演练缺失、账本一致性异常。必须逐项查看检查列表，不能只看一个徽标。",
  },
  PAUSED: {
    label: "已暂停",
    tone: "amber",
    meaning: "采集被显式暂停：暂停期间不会产生新的观察。暂停不是健康状态，也不代表七天验证在继续。",
  },
  NOT_DEPLOYED: {
    label: "未部署",
    tone: "muted",
    meaning: "没有经过验证的常驻部署（supervisor / 服务）。手动运行、本地验证与本地备份都不等于生产部署；即使账本里已有数据，也必须这样显示。",
  },
  VALIDATION_IN_PROGRESS: {
    label: "验证进行中",
    tone: "teal",
    meaning: "七天连续观察验证尚未结束，其余组件当前健康。只能报告进行中，绝不能宣称已通过；剩余天数按真实经过时间计算。",
  },
};
const PHASE_OPTIONS = [
  { id: "", label: "全部阶段" },
  { id: "INITIAL_DISCOVERY", label: "初次发现" },
  { id: "INCREMENTAL_DISCOVERY", label: "增量发现" },
  { id: "HISTORICAL_BACKFILL", label: "历史回填" },
];
const PHASE_TONES = {
  INITIAL_DISCOVERY: "blue",
  INCREMENTAL_DISCOVERY: "teal",
  HISTORICAL_BACKFILL: "violet",
};
const PHASE_SHORT = {
  INITIAL_DISCOVERY: "初次发现",
  INCREMENTAL_DISCOVERY: "增量发现",
  HISTORICAL_BACKFILL: "历史回填",
  __unlabelled__: "未标注阶段",
};
const PHASE_SENTENCE =
  "阶段只说明「系统何时第一次观察到这条记录」：初次发现＝系统首次上线时抓到的既有公开记录（不是历史回填）；"
  + "增量发现＝持续监测期间新发现的记录；历史回填＝有意导入的历史归档（需要理由）。「事件发生在过去」不等于「回填」。";
const PRECISION_SUFFIX = {
  date: "（日期精度）",
  datetime: "",
  year: "（年份精度）",
  unknown: "（精度未知）",
};
const PAGE_LIMITS = [25, 50, 100, 200];

/* --------------------------------------------------------------- helpers */
function precisionNote(item) {
  const suffix = PRECISION_SUFFIX[item.event_at_precision] || "";
  return suffix ? el("span", { class: "muted tiny", text: suffix }) : null;
}

function lagLine(item) {
  const basis = item.time_basis || {};
  if (basis.measurable) {
    const hours = basis.publish_to_first_seen_hours != null
      ? basis.publish_to_first_seen_hours
      : basis.event_to_first_seen_hours;
    return el("div", {
      class: "obs-lag",
      text: `发布 → 首次观察 ${fmtNum(hours, 1)} 小时（轮询采集）`,
      title: "measured lag：来源发布时间 → MedRadar 首次观察，只统计可精确到时刻的发布时间",
    });
  }
  const reason = String(item.evidence_zh || "").replace(/^无法测量发布到首次观察的间隔：/, "");
  return el("div", {
    class: "obs-lag na",
    text: `无法测量：${reason || "来源未提供可测量的发布时间"}`,
  });
}

function timeBlock(item) {
  const eventText = item.event_at ? String(item.event_at) : "来源未提供事件发生时间";
  const seenText = item.first_seen_at ? fmtDateTime(item.first_seen_at) : "未知";
  const publishedText = item.published_at ? fmtDateTime(item.published_at) : "来源未提供发布时间";
  return el("div", { class: "obs-time-block" },
    el("div", { class: "obs-time-line" },
      el("span", { text: "事件发生于 " }), el("b", { text: eventText }), precisionNote(item)),
    el("div", { class: "obs-time-line" },
      el("span", { text: "MedRadar 于 " }), el("b", { text: seenText }), el("span", { text: " 首次观察到它" })),
    el("div", { class: "obs-time-line" },
      el("span", { text: "发布时间：" }), el("b", { text: publishedText })),
    lagLine(item),
  );
}

function changeBadge(item) {
  return badge(
    item.change_label_zh || CHANGE_LABELS[item.change_state] || item.change_state || "—",
    CHANGE_TONES[item.change_state] || "muted",
    `change_state: ${item.change_state}`,
  );
}

function phaseBadge(item) {
  const phase = item.phase;
  if (!phase) {
    return el("span", { class: "muted tiny", text: "阶段未标注", title: "该记录尚无采集阶段标签（旧账本或尚未重建）；未标注不等于任何阶段" });
  }
  return badge(
    PHASE_SHORT[phase] || phase,
    PHASE_TONES[phase] || "muted",
    `phase: ${phase}（采集阶段，不是 observation_origin，也不是事件发生时间）`,
  );
}

function mappingBadge(company) {
  const status = (company && company.status) || "UNMAPPED";
  const note = (company && (company.note_zh || company.method)) || status;
  return badge(status, MAPPING_TONES[status] || "muted", note);
}

function companyCell(item) {
  const company = item.company || {};
  const name = company.name_zh || company.entity_id || (company.status === "UNMAPPED" ? "未映射" : "—");
  return el("div", { class: "obs-company" },
    el("span", { class: "nowrap", text: name }),
    mappingBadge(company));
}

function trackCell(item) {
  const track = item.track || {};
  if (track.name_zh) return el("span", { text: track.name_zh });
  return el("span", { class: "muted", text: "未映射" });
}

function sourceCell(item) {
  return el("div", { class: "obs-cell-stack" },
    el("span", { text: item.source_label_zh || item.source || "—" }),
    el("span", { class: "muted tiny", text: `${item.record_type_label_zh || item.record_type || "—"} · ${item.record_type || ""}` }));
}

function sourceLink(item, { small = false } = {}) {
  if (!item || !item.url) {
    return el("span", { class: "muted tiny", text: "该记录没有可用的原始链接" });
  }
  return el("a", {
    class: "obs-action-link",
    href: item.url,
    target: "_blank",
    rel: "noopener noreferrer",
    text: small ? "打开原始来源" : "打开原始来源 ↗",
    onclick: (event) => event.stopPropagation(),
  });
}

function previewValue(value, limit = 160) {
  if (value == null) return "—";
  let text;
  if (typeof value === "object") text = JSON.stringify(value);
  else text = String(value);
  text = text.replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

/* ----------------------------------------------------------------- drawer */
function drawerSection(title, ...children) {
  return el("div", { class: "drawer-section" },
    el("h4", { text: title }),
    ...children.flat().filter(Boolean));
}

function fieldLabelMap(observation) {
  const map = new Map();
  for (const item of observation.changed_fields || []) {
    if (item && item.field) map.set(item.field, item.label_zh || item.field);
  }
  return map;
}

function renderVersionChain(detail) {
  const versions = detail.versions || [];
  if (!versions.length) return el("div", { class: "muted small", text: "没有版本记录。" });
  const labels = fieldLabelMap(detail.observation || {});
  const container = el("div");
  let previous = null;
  for (const version of versions) {
    const head = el("div", { class: "obs-version-head" },
      badge(`v${version.version_seq}`, CHANGE_TONES[version.change_state] || "muted"),
      badge(CHANGE_LABELS[version.change_state] || version.change_state, CHANGE_TONES[version.change_state] || "muted"),
      el("span", { class: "obs-version-date", text: fmtDateTime(version.captured_at) }),
      el("span", { class: "muted tiny mono", text: `payload ${String(version.payload_hash || "").slice(0, 10)}` }));
    const node = el("div", { class: "obs-version" });
    node.append(head);
    if (version.change_state === "UPDATED" && (version.changed_fields || []).length) {
      const fields = el("div", { class: "obs-version-fields" });
      for (const field of version.changed_fields) {
        fields.append(el("div", { class: "obs-field-row" },
          el("div", { class: "obs-field-name", text: `${labels.get(field) || field}（${field}）` }),
          el("div", null,
            el("div", { class: "obs-field-old" }, el("b", { text: "旧" }), previewValue(previous ? (previous.payload || {})[field] : null)),
            el("div", { class: "obs-field-new" }, el("b", { text: "新" }), previewValue((version.payload || {})[field])))));
      }
      node.append(fields);
    }
    node.append(disclosure(
      "原始 payload（只读，来源字段）",
      el("div", { class: "obs-payload" }, codeBlock(JSON.stringify(version.payload || {}, null, 2))),
      { open: version.version_seq === versions[versions.length - 1].version_seq },
    ));
    container.append(node);
    previous = version;
  }
  return container;
}

function renderSyncContext(context) {
  const ctxData = context || {};
  const run = ctxData.run || null;
  const state = ctxData.source_state || null;
  const rows = [
    { key: "first_seen_run_id", value: ctxData.first_seen_run_id || "—" },
  ];
  if (run) {
    rows.push({ key: "运行状态", value: `${RUN_LABELS[run.status] || run.status}（${run.status}）· 触发 ${run.trigger || "—"}` });
    rows.push({ key: "运行起止", value: `${fmtDateTime(run.started_at)} → ${run.finished_at ? fmtDateTime(run.finished_at) : "—"}` });
    rows.push({ key: "运行计数", value: `seen ${fmtInt(run.records_seen)} · new ${fmtInt(run.records_new)} · updated ${fmtInt(run.records_updated)} · unchanged ${fmtInt(run.records_unchanged)} · removed ${fmtInt(run.records_removed)} · failed ${fmtInt(run.records_failed)}` });
    if (run.error_detail) rows.push({ key: "运行错误", value: run.error_detail });
  } else {
    rows.push({ key: "运行记录", value: "没有找到首次观察对应的运行记录" });
  }
  if (state) {
    rows.push({ key: "来源状态", value: `${state.status || "—"} · 连续失败 ${fmtInt(state.consecutive_failures)}` });
    rows.push({ key: "声明轮询周期", value: state.declared_cadence_zh || "未声明轮询周期" });
    rows.push({ key: "来源最近成功", value: state.last_success_at ? fmtDateTime(state.last_success_at) : "—" });
  }
  return kvList(rows);
}

function renderMappingHistory(detail) {
  const rows = detail.mapping_history || [];
  if (!rows.length) return el("div", { class: "muted small", text: "没有映射历史。" });
  return dataTable({
    columns: [
      { key: "mapping_version", label: "映射版本", format: (row) => el("span", { class: "mono tiny", text: row.mapping_version || "—" }) },
      { key: "mapped_at", label: "记录时间", format: (row) => el("span", { class: "mono", text: fmtDateTime(row.mapped_at) }) },
      { key: "entity_id", label: "企业", format: (row) => row.entity_id || el("span", { class: "muted", text: "未映射" }) },
      { key: "entity_status", label: "企业状态", format: (row) => badge(row.entity_status || "UNMAPPED", MAPPING_TONES[row.entity_status] || "muted") },
      { key: "track_id", label: "赛道", format: (row) => row.track_id || el("span", { class: "muted", text: "未映射" }) },
      { key: "track_status", label: "赛道状态", format: (row) => badge(row.track_status || "UNMAPPED", MAPPING_TONES[row.track_status] || "muted") },
      { key: "note_zh", label: "说明", format: (row) => el("span", { class: "small", text: row.note_zh || "—" }) },
    ],
    rows,
    compact: true,
  });
}

function renderStatusHistory(detail) {
  const rows = detail.status_history || [];
  if (!rows.length) return el("div", { class: "muted small", text: "没有状态历史。" });
  return dataTable({
    columns: [
      { key: "changed_at", label: "时间", format: (row) => el("span", { class: "mono", text: fmtDateTime(row.changed_at) }) },
      { key: "status", label: "状态", format: (row) => badge(row.status || "—", row.status === "ACTIVE" ? "green" : "red") },
      { key: "note", label: "说明", format: (row) => el("span", { class: "small", text: row.note || "—" }) },
    ],
    rows,
    compact: true,
  });
}

function renderDetail(detail) {
  const observation = detail.observation || {};
  const nodes = [];
  const evidenceNote = String(observation.evidence_zh || "").trim();
  const noteIsDuplicated = /^无法测量/.test(evidenceNote);
  nodes.push(drawerSection(
    "时间口径（三个时间始终分开陈述）",
    timeBlock(observation),
    noteIsDuplicated ? null : el("div", { class: "obs-drawer-note", text: evidenceNote }),
    el("div", { class: "obs-drawer-actions" },
      changeBadge(observation),
      mappingBadge(observation.company || {}),
      sourceLink(observation)),
  ));
  nodes.push(drawerSection("来源与身份", kvList([
    { key: "source", value: observation.source_label_zh || observation.source || "—" },
    { key: "source_record_id", value: observation.source_record_id || "—" },
    { key: "record_type", value: `${observation.record_type_label_zh || "—"}（${observation.record_type || "—"}）` },
    { key: "observation_id", value: observation.observation_id || "—" },
    { key: "observation_origin", value: observation.observation_origin || "—" },
    { key: "observation_status", value: observation.observation_status || "—" },
    { key: "ingested_at", value: observation.ingested_at ? fmtDateTime(observation.ingested_at) : "—" },
    { key: "last_checked_at", value: observation.last_checked_at ? fmtDateTime(observation.last_checked_at) : "—" },
    observation.backfill_reason ? { key: "backfill_reason", value: observation.backfill_reason } : null,
  ])));
  nodes.push(drawerSection("版本链（append-only，按抓取时刻）", renderVersionChain(detail)));
  nodes.push(drawerSection("映射历史（不重写来源历史）", renderMappingHistory(detail)));
  nodes.push(drawerSection("状态历史", renderStatusHistory(detail)));
  nodes.push(drawerSection("同步上下文", renderSyncContext(detail.sync_context)));
  const limitations = detail.limitations || [];
  if (limitations.length) {
    nodes.push(drawerSection("限制与说明",
      notice({ tone: "muted", title: "该记录的口径限制", items: limitations.map((item) => item.text_zh) })));
  }
  return nodes;
}

function openObservation(row) {
  const body = el("div");
  body.append(skeletonBlock(8));
  openDrawer({
    title: row.title || "观察详情",
    sub: `${row.source_label_zh || row.source || ""} · ${row.record_type_label_zh || row.record_type || ""} · ${row.change_label_zh || ""}`,
    body,
    wide: true,
  });
  api.observatoryEvent(row.observation_id)
    .then((detail) => body.replaceChildren(...renderDetail(detail)))
    .catch((error) => {
      body.replaceChildren(errorState(error, () => openObservation(row), { title: "观察详情加载失败" }));
    });
}

/* ------------------------------------------------------------ source panel */
function lagNode(lag) {
  const data = lag || {};
  if (data.measurable) {
    return el("div", null,
      el("span", { class: "mono", text: `发布 → 首次观察：p50 ${fmtNum(data.p50_hours, 1)} 小时 · p90 ${fmtNum(data.p90_hours, 1)} 小时 · n=${fmtInt(data.n)}` }),
      el("div", { class: "muted tiny", text: data.note_zh || "" }));
  }
  return el("div", null,
    el("span", { class: "lq-na", text: "无法测量" }),
    el("span", { class: "muted tiny", text: ` ${data.note_zh || "来源未提供可测量的发布时间"}` }));
}

function recentRunsTable(runs) {
  if (!runs || !runs.length) return el("div", { class: "obs-empty-inline", text: "没有运行记录。" });
  return dataTable({
    columns: [
      { key: "started_at", label: "开始", format: (row) => el("span", { class: "mono", text: fmtDateTime(row.started_at) }) },
      { key: "status", label: "状态", format: (row) => badge(RUN_LABELS[row.status] || row.status || "—", row.status === "OK" ? "green" : row.status === "FAILED" ? "red" : "amber") },
      { key: "trigger", label: "触发", format: (row) => row.trigger || "—" },
      {
        key: "counters",
        label: "记录（新 / 改 / 未变 / 移除 / 失败）",
        format: (row) => el("span", { class: "mono tiny", text: `${fmtInt(row.records_new)} / ${fmtInt(row.records_updated)} / ${fmtInt(row.records_unchanged)} / ${fmtInt(row.records_removed)} / ${fmtInt(row.records_failed)}` }),
      },
      { key: "error_detail", label: "错误", format: (row) => el("span", { class: "small muted", text: row.error_detail || "—" }) },
    ],
    rows: runs,
    compact: true,
  });
}

function recentFailuresTable(failures) {
  if (!failures || !failures.length) return el("div", { class: "obs-empty-inline", text: "没有记录的采集失败。" });
  return dataTable({
    columns: [
      { key: "occurred_at", label: "时间", format: (row) => el("span", { class: "mono", text: fmtDateTime(row.occurred_at) }) },
      { key: "kind", label: "类型", format: (row) => badge(row.kind || "—", "red") },
      { key: "http_status", label: "HTTP", format: (row) => (row.http_status == null ? "—" : String(row.http_status)) },
      { key: "retryable", label: "可重试", format: (row) => (row.retryable ? "是" : "否") },
      { key: "message", label: "消息", format: (row) => el("span", { class: "small", text: row.message || "—" }) },
    ],
    rows: failures,
    compact: true,
  });
}

function coverageTable(rows) {
  if (!rows || !rows.length) {
    return el("div", { class: "obs-empty-inline", text: "该来源尚未记录已验证的实体覆盖；没有记录不等于零活动。" });
  }
  return dataTable({
    columns: [
      { key: "entity_id", label: "企业 / 实体", format: (row) => el("div", null, el("div", { text: row.name_zh || row.entity_id || "—" }), el("div", { class: "muted tiny", text: row.entity_id || "" })) },
      { key: "status", label: "核验状态", format: (row) => badge(row.status || "UNVERIFIED", COVERAGE_TONES[row.status] || "muted", `covered=${Boolean(row.covered)}`) },
      { key: "identifier", label: "标识", format: (row) => el("span", { class: "mono tiny", text: row.identifier || "—" }) },
      { key: "evidence_zh", label: "核验证据", format: (row) => el("span", { class: "small", text: row.evidence_zh || "—" }) },
    ],
    rows,
    compact: true,
  });
}

function sourcePanel(source) {
  const meta = el("div", { class: "obs-source-meta" },
    el("span", null, el("span", { text: "轮询周期：" }), el("b", { text: source.declared_cadence_zh || "未声明轮询周期" })),
    el("span", null, el("span", { text: "最近成功：" }), el("b", { text: source.last_success_at ? fmtDateTime(source.last_success_at) : "—" })),
    el("span", null, el("span", { text: "最近尝试：" }), el("b", { text: source.last_attempt_at ? fmtDateTime(source.last_attempt_at) : "—" })),
    el("span", null, el("span", { text: "连续失败：" }), el("b", { text: fmtInt(source.consecutive_failures) })),
  );
  const body = el("div");
  body.append(meta);
  body.append(el("div", { class: "obs-source-section" }, el("h4", { text: "实测观察延迟（声明周期 ≠ 实测延迟）" }), lagNode(source.measured_lag)));
  body.append(el("div", { class: "obs-source-section" }, el("h4", { text: "最近运行" }), recentRunsTable(source.recent_runs)));
  body.append(el("div", { class: "obs-source-section" }, el("h4", { text: "最近采集失败" }), recentFailuresTable(source.recent_failures)));
  body.append(el("div", { class: "obs-source-section" },
    el("h4", { text: "已验证的实体覆盖" }),
    coverageTable(source.entity_coverage),
    el("div", { class: "muted tiny mt-8", text: source.coverage_note_zh || "" })));
  const node = panel({
    title: `${source.label_zh || source.source} · ${source.source}`,
    sub: "轮询采集（非实时推送）",
    right: badge(source.status_label_zh || source.status, SOURCE_STATUS_TONES[source.status] || "muted", `status: ${source.status}`),
    className: "obs-source-panel",
    body,
    note: source.limitation_zh || null,
  });
  node.dataset.testid = `observatory-source-${source.source}`;
  return node;
}

/* ----------------------------------------------------- observatory health */
function fmtBytes(value) {
  const n = Number(value);
  if (value == null || !Number.isFinite(n) || n < 0) return "—";
  if (n < 1024) return `${fmtInt(n)} B`;
  if (n < 1024 * 1024) return `${fmtNum(n / 1024, 1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${fmtNum(n / (1024 * 1024), 2)} MB`;
  return `${fmtNum(n / (1024 * 1024 * 1024), 2)} GB`;
}

function healthBadge(word) {
  const meta = HEALTH_WORDS[word] || { label: word || "未知", tone: "muted", meaning: "健康状态未知。" };
  return badge(`${meta.label} · ${word || "UNKNOWN"}`, meta.tone, meta.meaning);
}

function deploymentTone(status) {
  if (status === "DEPLOYED_SERVICE") return "green";
  if (status === "DEPLOYED_LOCAL") return "teal";
  return "muted";
}

function validationTone(status) {
  if (status === "VALIDATION_PASSED") return "green";
  if (status === "VALIDATION_FAILED") return "red";
  if (status === "VALIDATION_IN_PROGRESS") return "teal";
  return "muted";
}

function healthBlock(title, rows) {
  return el("div", { class: "obs-health-block" },
    el("h4", { text: title }),
    kvList(rows));
}

function deploymentRows(health) {
  const d = health.deployment || {};
  return [
    { key: "状态", value: badge(d.status_label_zh || d.status || "未部署", deploymentTone(d.status)) },
    { key: "supervisor", value: d.supervisor || "none" },
    { key: "安装时间", value: d.installed_at ? fmtDateTime(d.installed_at) : "—" },
    { key: "主机", value: d.host || "—" },
    { key: "说明", value: d.note_zh || "—" },
  ];
}

function validationRows(health) {
  const v = health.validation || {};
  const slots = v.slots || {};
  const runs = v.runs || {};
  const planned = slots.planned_total != null ? slots.planned_total : v.planned_slots;
  const rate = runs.scheduler_success_rate != null ? runs.scheduler_success_rate : v.scheduler_success_rate;
  const rows = [
    { key: "状态", value: badge(v.status_label_zh || v.status || "未开始", validationTone(v.status)) },
    {
      key: "开始 → 结束",
      value: `${v.started_at ? fmtDateTime(v.started_at) : "—"} → ${v.ends_at ? fmtDateTime(v.ends_at) : "—"}`,
    },
  ];
  if (v.days_elapsed != null || v.days_remaining != null) {
    rows.push({
      key: "已过 / 剩余",
      value: `${v.days_elapsed != null ? fmtNum(v.days_elapsed, 2) : "—"} / ${v.days_remaining != null ? fmtNum(v.days_remaining, 2) : "—"} 天`,
    });
  }
  rows.push({
    key: "计划 / 到期 / 已执行 / 缺失",
    value: `${fmtInt(planned)} / ${fmtInt(slots.due)} / ${fmtInt(slots.executed)} / ${fmtInt(slots.missed)}`,
  });
  rows.push({ key: "调度成功率（ok/到期轮次）", value: fmtPct(rate, 1) });
  if (v.status === "VALIDATION_IN_PROGRESS") {
    rows.push({ key: "口径", value: "验证尚未结束：只能报告进行中，不能宣称已通过" });
  }
  if (v.note_zh) rows.push({ key: "说明", value: v.note_zh });
  return rows;
}

function collectorRows(health) {
  const c = health.collector || {};
  const lock = c.lock || {};
  const lastRun = c.last_run || null;
  let lockText;
  if (lock.held) {
    const holder = lock.holder || {};
    lockText = `持有中 · pid ${holder.pid != null ? holder.pid : "—"} · ${holder.host || "—"} · mode ${holder.mode || "—"}`;
    if (lock.heartbeat_age_seconds != null) {
      lockText += ` · 心跳 ${fmtNum(lock.heartbeat_age_seconds, 0)} 秒前`;
    }
  } else if (lock.stale) {
    lockText = "锁文件存在但已过期（当前没有存活的采集进程）";
  } else {
    lockText = "未持有锁（当前没有采集进程）";
  }
  return [
    { key: "当前是否运行", value: c.running ? badge("运行中", "green") : badge("未运行", "muted") },
    { key: "单写锁", value: lockText },
    {
      key: "最近运行",
      value: lastRun
        ? `${lastRun.run_id || "—"} · ${lastRun.source || "—"} · ${RUN_LABELS[lastRun.status] || lastRun.status || "—"} · ${lastRun.started_at ? fmtDateTime(lastRun.started_at) : "—"}`
        : "—",
    },
    { key: "已观察时长", value: c.uptime_days != null ? `${fmtNum(c.uptime_days, 2)} 天` : "—" },
  ];
}

function persistenceRows(health) {
  const p = health.persistence || {};
  const backup = p.backup || {};
  const drill = p.restore_drill || {};
  const backupOk = backup.status === "OK" && Boolean(backup.verified);
  const drillOk = drill.status === "OK";
  return [
    { key: "账本大小", value: fmtBytes(p.ledger_bytes) },
    { key: "原始响应缓存", value: p.raw_cache_bytes != null ? `${fmtBytes(p.raw_cache_bytes)}（可再生成）` : "—" },
    {
      key: "最近备份",
      value: el("div", { class: "obs-cell-stack" },
        badge(backup.status || "NEVER", backupOk ? "green" : "red", "只有 status=OK 且已验证（verified=true）才算通过"),
        el("span", {
          class: "muted tiny",
          text: `${backup.at ? fmtDateTime(backup.at) : "从未记录"}`
            + `${backup.age_hours != null ? ` · ${fmtNum(backup.age_hours, 1)} 小时前` : ""}`
            + ` · verified=${backup.verified ? "true" : "false"}`,
        })),
    },
    {
      key: "最近恢复演练",
      value: el("div", { class: "obs-cell-stack" },
        badge(drill.status || "NEVER", drillOk ? "green" : "red", "未做恢复演练不等于可恢复"),
        el("span", {
          class: "muted tiny",
          text: `${drill.at ? fmtDateTime(drill.at) : "从未记录"}`
            + `${drill.ok != null ? ` · ok=${drill.ok}` : ""}`,
        })),
    },
    { key: "磁盘可用", value: fmtBytes(p.disk_free_bytes) },
  ];
}

function outcomeCell(row) {
  if (!row.last_outcome) {
    return el("span", { class: "muted", text: "尚未记录", title: "该来源还没有记录最近一次采集结果" });
  }
  const severity = row.last_outcome_severity || "unknown";
  const tone = severity === "failure" ? "red"
    : severity === "partial" ? "amber"
      : severity === "normal" ? "green" : "muted";
  const bits = [];
  if (row.last_new_records != null) bits.push(`新 ${fmtInt(row.last_new_records)}`);
  if (row.last_updated_records != null) bits.push(`改 ${fmtInt(row.last_updated_records)}`);
  return el("div", { class: "obs-cell-stack" },
    el("span", null, badge(
      row.last_outcome_label_zh || row.last_outcome,
      tone,
      `last_outcome: ${row.last_outcome}（NO_NEW_RECORDS 是正常结果；FETCH_FAILED 是失败，二者不同）`,
    )),
    el("span", { class: "muted tiny", text: bits.join(" · ") }));
}

function freshnessCell(row) {
  if (row.freshness_hours == null) {
    return el("span", { class: "muted", text: "无成功记录", title: "该来源还没有任何真实成功记录；新鲜度无法计算" });
  }
  const expected = row.expected_interval_hours != null ? `${fmtNum(row.expected_interval_hours, 1)}h` : "—";
  const threshold = row.stale_after_hours != null ? `${fmtNum(row.stale_after_hours, 1)}h` : "—";
  return el("span", {
    class: row.stale ? "tone-down mono" : "mono",
    text: `${fmtNum(row.freshness_hours, 1)}h / 周期 ${expected} / 阈值 ${threshold}`,
    title: "距该来源最近一次真实成功的时间；阈值 = max(3 × 声明周期, 12 小时)；声明周期 ≠ 实测新鲜度",
  });
}

function healthSourceTable(sources) {
  return dataTable({
    columns: [
      {
        key: "source",
        label: "来源",
        format: (row) => el("div", { class: "obs-cell-stack" },
          el("span", { text: row.label_zh || row.source || "—" }),
          el("span", { class: "muted tiny mono", text: row.source || "" })),
      },
      {
        key: "status",
        label: "状态",
        format: (row) => badge(row.status_label_zh || row.status || "—", SOURCE_STATUS_TONES[row.status] || "muted", `status: ${row.status}`),
      },
      { key: "last_success_at", label: "最近成功", format: (row) => el("span", { class: "mono", text: fmtDateTime(row.last_success_at) }) },
      { key: "last_attempt_at", label: "最近尝试", format: (row) => el("span", { class: "mono", text: fmtDateTime(row.last_attempt_at) }) },
      { key: "last_outcome", label: "最近结果（正常 / 失败分开）", format: (row) => outcomeCell(row) },
      {
        key: "consecutive_failures",
        label: "连续失败",
        num: true,
        format: (row) => (Number(row.consecutive_failures || 0) > 0
          ? el("b", { class: "tone-down", text: fmtInt(row.consecutive_failures) })
          : el("span", { class: "muted", text: "0" })),
      },
      { key: "freshness", label: "新鲜度 / 周期 / 阈值", format: (row) => freshnessCell(row) },
      {
        key: "stale",
        label: "新鲜度",
        format: (row) => (row.stale
          ? badge("已过期", "red", `超过阈值 ${row.stale_after_hours}h 未成功`)
          : badge("新鲜", "green", "在阈值内")),
      },
      {
        key: "structure_alert",
        label: "结构告警",
        format: (row) => (row.structure_alert
          ? badge("结构变化", "red", row.structure_note_zh || "来源结构发生变化，尚未人工解决")
          : el("span", { class: "muted", text: "—" })),
      },
    ],
    rows: sources,
    compact: true,
    empty: "账本里还没有来源状态记录。",
  });
}

function healthCheckRow(check) {
  const ok = Boolean(check.ok);
  return el("div", {
    class: "obs-health-check",
    dataset: { checkId: check.id || "", checkOk: ok ? "true" : "false" },
  },
  badge(ok ? "OK" : "FAIL", ok ? "green" : "red", `check: ${check.id}`),
  el("span", { class: "mono tiny obs-health-check-id", text: check.id || "—" }),
  el("span", { class: "small", text: check.detail_zh || "—" }));
}

function renderHealthPanel(health) {
  if (!health) {
    return panel({
      title: "观察站健康 / Observatory Health",
      sub: "健康状态无法获取时不展示任何绿色徽标",
      body: notice({
        tone: "amber",
        title: "健康状态加载失败",
        body: "无法获取 /api/observatory/health。这里没有可展示的健康结论；下方数据源行仍然逐项显示各自状态。",
      }),
    });
  }
  const word = health.overall || "NOT_DEPLOYED";
  const meta = HEALTH_WORDS[word] || { label: word, tone: "muted", meaning: "健康状态未知。" };
  const sources = health.sources || [];
  const checks = health.checks || [];
  const alerts = health.unresolved_structure_alerts || [];
  const failingSources = sources.filter((source) => source.status && source.status !== "OK");
  const failedChecks = checks.filter((check) => !check.ok);

  const body = el("div", { class: "obs-health" });
  const overallBadge = healthBadge(word);
  overallBadge.dataset.testid = "observatory-health-overall";
  overallBadge.dataset.healthWord = word;
  body.append(el("div", { class: "obs-health-overall" },
    overallBadge,
    el("div", { class: "obs-health-meaning", text: health.overall_note_zh || meta.meaning })));

  const reasons = [];
  const deployment = health.deployment || {};
  if (deployment.status === "NOT_DEPLOYED") reasons.push("没有经过验证的常驻部署（数据存在也不等于已部署）");
  if (deployment.status === "DEPLOYED_LOCAL") reasons.push("仅本地部署：不是生产常驻服务");
  if (failingSources.length) {
    reasons.push(`${failingSources.length} 个来源异常：${failingSources.map((source) => source.source).join("、")}`);
  }
  const staleSources = sources.filter((source) => source.stale);
  if (staleSources.length) reasons.push(`${staleSources.length} 个来源超过新鲜度阈值：${staleSources.map((source) => source.source).join("、")}`);
  if (alerts.length) reasons.push(`${alerts.length} 条未解决的结构变化告警`);
  for (const check of failedChecks) {
    if (check.id === "backup" || check.id === "backup_freshness") reasons.push("最近备份未通过 / 已过期");
    if (check.id === "restore_drill") reasons.push("最近恢复演练未成功或未执行");
    if (check.id === "integrity") reasons.push("账本一致性检查未通过");
    if (check.id === "collector_recent") reasons.push("没有任何采集运行记录");
  }
  if (reasons.length) {
    const alarming = Boolean(
      failingSources.length || staleSources.length || alerts.length || failedChecks.length
      || deployment.status === "NOT_DEPLOYED",
    );
    body.append(notice({
      tone: alarming ? "amber" : "muted",
      title: `必须与「${meta.label}」一起阅读的降级/限制原因`,
      items: Array.from(new Set(reasons)),
      testid: "observatory-health-reasons",
    }));
  }

  const grid = el("div", { class: "obs-health-grid" });
  grid.append(
    healthBlock("部署 / Deployment", deploymentRows(health)),
    healthBlock("七天连续验证 / Validation", validationRows(health)),
    healthBlock("采集器 / Collector", collectorRows(health)),
    healthBlock("持久化 / Persistence", persistenceRows(health)),
  );
  body.append(grid);

  body.append(el("div", { class: "obs-health-section" },
    el("h4", { text: `数据源健康（${sources.length} 个）` }),
    healthSourceTable(sources)));

  if (alerts.length) {
    body.append(notice({
      tone: "amber",
      title: `未解决的结构变化告警 ${alerts.length} 条`,
      items: alerts.map((item) => `${item.source || "未知来源"} · ${item.changed_at ? fmtDateTime(item.changed_at) : "时间未知"} · ${item.note_zh || "来源结构发生变化，需人工确认"}`),
    }));
  }

  const passed = checks.length - failedChecks.length;
  body.append(disclosure(
    `检查项 ${passed}/${checks.length} 通过${failedChecks.length ? ` · ${failedChecks.length} 项 FAIL` : ""}`,
    el("div", { class: "obs-health-checks", testid: "observatory-health-checks" }, ...checks.map((check) => healthCheckRow(check))),
    { open: failedChecks.length > 0 },
  ));

  if ((health.limitations_zh || []).length) {
    body.append(notice({ tone: "muted", title: "健康面板不声称的内容", items: health.limitations_zh }));
  }

  const node = panel({
    title: "观察站健康 / Observatory Health",
    sub: "由账本、文件系统与运行记录计算，不是 HTTP 200 的另一种写法；降级必须能在下方来源行中看到",
    right: el("span", { class: "muted small", text: `${fmtInt(sources.length)} 个来源 · 检查 ${fmtInt(passed)}/${fmtInt(checks.length)}` }),
    body,
  });
  node.dataset.testid = "observatory-health";
  return node;
}

/* ------------------------------------------------------------- phase chips */
function phaseChipRow(eventsFacets, phasesSummary, filters, goFilters) {
  const facets = (eventsFacets && eventsFacets.phases) || [];
  const counts = {};
  let total = 0;
  for (const item of facets) {
    counts[item.phase] = Number(item.count || 0);
    total += Number(item.count || 0);
  }
  const summary = phasesSummary || {};
  const options = [{ id: "", label: "全部阶段", count: total }];
  for (const option of PHASE_OPTIONS.slice(1)) {
    const facet = facets.find((item) => item.phase === option.id) || {};
    options.push({
      id: option.id,
      label: option.label,
      count: counts[option.id] || 0,
      description: facet.description_zh,
    });
  }
  const row = el("div", { class: "obs-chip-row" },
    el("span", { class: "obs-chip-label", text: "采集阶段" }),
    ...options.map((option) => chip(
      `${option.label} · ${fmtInt(option.count)}`,
      {
        active: (filters.phase || "") === option.id,
        testid: `observatory-phase-${option.id || "all"}`,
        title: option.description || "按「系统何时第一次观察到该记录」过滤；不是 observation_origin，也不是事件发生时间",
        onClick: () => goFilters({ phase: option.id, offset: 0 }),
      },
    )));
  row.append(el("span", {
    class: "muted tiny",
    text: `当前时间窗口径：全部 ${fmtInt(total)}`
      + ` · 初次发现 ${fmtInt(summary.initial)} · 增量发现 ${fmtInt(summary.incremental)}`
      + ` · 历史回填 ${fmtInt(summary.backfill)}`
      + (Number(summary.unlabelled || 0) > 0 ? ` · 未标注 ${fmtInt(summary.unlabelled)}` : ""),
    title: "「全部/初次发现/…」前一列是当前时间窗内的变化数；账本口径为全账本观察数，两者口径不同",
  }));
  return row;
}

/* ---------------------------------------------------------------- mounting */
export async function mount(root, ctx) {
  const allowedWindows = WINDOW_OPTIONS.map((option) => option.id);
  const allowedChanges = CHANGE_OPTIONS.map((option) => option.id);
  const allowedPhases = PHASE_OPTIONS.map((option) => option.id).filter(Boolean);
  const filters = {
    window: allowedWindows.includes(ctx.query.get("window")) ? ctx.query.get("window") : "7d",
    change: allowedChanges.includes(ctx.query.get("change")) ? ctx.query.get("change") : "all",
    source: ctx.query.get("source") || "",
    company: ctx.query.get("company") || "",
    track: ctx.query.get("track") || "",
    q: ctx.query.get("q") || "",
    phase: allowedPhases.includes(ctx.query.get("phase")) ? ctx.query.get("phase") : "",
    limit: PAGE_LIMITS.includes(Number(ctx.query.get("limit"))) ? Number(ctx.query.get("limit")) : 50,
    offset: Math.max(0, Number(ctx.query.get("offset")) || 0),
  };

  root.append(skeletonBlock(8));
  let summary;
  let events;
  let sourcesPayload;
  let healthPayload;
  try {
    [summary, events, sourcesPayload, healthPayload] = await Promise.all([
      api.observatorySummary(),
      api.observatoryEvents({
        window: filters.window,
        change: filters.change,
        source: filters.source || undefined,
        company: filters.company || undefined,
        track: filters.track || undefined,
        q: filters.q || undefined,
        phase: filters.phase || undefined,
        limit: filters.limit,
        offset: filters.offset,
      }),
      api.observatorySources(),
      // A health failure must not block the observation list; the panel then states
      // honestly that no health conclusion is available.
      api.request("/api/observatory/health").catch(() => null),
    ]);
  } catch (error) {
    root.replaceChildren(errorState(error, () => ctx.refresh(), { title: "实时观察站加载失败" }));
    return { title: "实时观察站" };
  }
  root.replaceChildren();

  const ledger = summary.ledger || {};
  const ledgerExists = Boolean(ledger.exists);
  const facetChanges = (events.facets && events.facets.changes) || [];
  const changeCount = (state) => {
    if (!state) return facetChanges.reduce((total, item) => total + Number(item.count || 0), 0);
    const found = facetChanges.find((item) => item.change_state === state);
    return Number(found ? found.count : 0);
  };

  function goFilters(patch = {}) {
    const next = { ...filters, ...patch };
    ctx.go("/observatory", {
      window: next.window,
      change: next.change,
      source: next.source || undefined,
      company: next.company || undefined,
      track: next.track || undefined,
      q: next.q || undefined,
      phase: next.phase || undefined,
      limit: next.limit,
      offset: next.offset || undefined,
    });
  }

  /* ---------------------------------------------------------------- head */
  root.append(pageHead({
    title: "实时观察站 / Live Observatory",
    subtitle: "只陈述 MedRadar 实际观察到的公开记录：事件发生时间、来源发布时间与 MedRadar 首次观察时间始终分开；所有来源均为轮询采集，不是实时推送。",
    captions: [
      { label: "观察账本", value: ledgerExists ? `${ledger.path || "—"}（${fmtInt(ledger.bytes)} bytes）` : "尚不存在" },
      { label: "观察总数", value: fmtInt(ledger.observations) },
      { label: "数据源", value: `${fmtInt(ledger.sources)} 个` },
      { label: "生成时间", value: summary.generated_at ? fmtDateTime(summary.generated_at) : "—" },
    ],
    actions: [linkButton("#/evidence", "证据浏览器"), linkButton("#/overview", "回到总览")],
  }));

  /* ------------------------------------------------ health (top of page) */
  root.append(renderHealthPanel(healthPayload));

  if (!ledgerExists) {
    root.append(notice({
      tone: "amber",
      title: "尚无观察记录：观察账本不存在",
      label: "EMPTY LEDGER",
      body: ledger.honesty_zh || "观察账本尚未建立，因此没有任何观察记录。空状态不等于「来源没有新事件」。",
      testid: "observatory-no-ledger",
    }));
  } else if (summary.empty) {
    root.append(notice({
      tone: "muted",
      title: "观察账本已建立，但还没有任何观察记录",
      label: "NO OBSERVATIONS",
      body: "采集器尚未观察到任何记录；这不表示来源没有活动，只表示本账本里还没有观察证据。",
    }));
  }

  /* ------------------------------------------------------------- filters */
  const facetSources = (events.facets && events.facets.sources) || [];
  const facetCompanies = (events.facets && events.facets.companies) || [];
  const facetTracks = (events.facets && events.facets.tracks) || [];

  const windowChips = el("div", { class: "obs-chip-row" },
    el("span", { class: "obs-chip-label", text: "时间窗" }),
    ...WINDOW_OPTIONS.map((option) => chip(
      `${option.label} · ${fmtInt((summary.windows && summary.windows[option.id] && summary.windows[option.id].total) || 0)}`,
      {
        active: filters.window === option.id,
        testid: `observatory-window-${option.id}`,
        title: `统计 observed_at 落在最近 ${option.label} 内的观察变化`,
        onClick: () => goFilters({ window: option.id }),
      },
    )));

  const changeChips = el("div", { class: "obs-chip-row" },
    el("span", { class: "obs-chip-label", text: "变化类型" }),
    ...CHANGE_OPTIONS.map((option) => chip(
      `${option.label} · ${fmtInt(changeCount(option.state))}`,
      {
        active: filters.change === option.id,
        testid: `observatory-change-${option.id}`,
        title: option.state ? `change_state = ${option.state}` : "四种变化状态全部展示",
        onClick: () => goFilters({ change: option.id }),
      },
    )));

  /* Acquisition phase is a *different* claim from change type: it says when in
     MedRadar's life a record was first observed, not what happened to it. */
  const phaseChips = phaseChipRow(events.facets, summary.phases, filters, goFilters);

  const sourceSelect = el("select", { "aria-label": "数据源" });
  sourceSelect.dataset.testid = "observatory-filter-source";
  sourceSelect.append(el("option", { value: "", text: "全部来源", selected: !filters.source }));
  for (const item of facetSources) {
    sourceSelect.append(el("option", {
      value: item.source,
      text: `${item.label_zh || item.source}（${fmtInt(item.count)}）`,
      selected: filters.source === item.source,
    }));
  }

  const companySelect = el("select", { "aria-label": "企业" });
  companySelect.dataset.testid = "observatory-filter-company";
  companySelect.append(el("option", { value: "", text: "全部企业", selected: !filters.company }));
  for (const item of facetCompanies) {
    const label = item.entity_id === "__unmapped__" ? "未映射" : (item.name_zh || item.entity_id);
    companySelect.append(el("option", {
      value: item.entity_id,
      text: `${label}（${fmtInt(item.count)}）`,
      selected: filters.company === item.entity_id,
    }));
  }

  const trackSelect = el("select", { "aria-label": "技术赛道" });
  trackSelect.dataset.testid = "observatory-filter-track";
  trackSelect.append(el("option", { value: "", text: "全部赛道", selected: !filters.track }));
  for (const item of facetTracks) {
    const label = item.track_id === "__unmapped__" ? "未映射" : (item.name_zh || item.track_id);
    trackSelect.append(el("option", {
      value: item.track_id,
      text: `${label}（${fmtInt(item.count)}）`,
      selected: filters.track === item.track_id,
    }));
  }

  const searchInput = el("input", {
    type: "search",
    value: filters.q,
    maxlength: 120,
    placeholder: "标题关键词（原文，多为英文）",
    "aria-label": "标题关键词",
  });
  searchInput.dataset.testid = "observatory-search";
  searchInput.style.width = "240px";

  const limitSelect = el("select", { "aria-label": "每页条数" });
  limitSelect.dataset.testid = "observatory-limit";
  for (const value of PAGE_LIMITS) {
    limitSelect.append(el("option", { value: String(value), text: `${value} 条/页`, selected: value === filters.limit }));
  }

  const apply = () => goFilters({
    source: sourceSelect.value,
    company: companySelect.value,
    track: trackSelect.value,
    q: searchInput.value.trim(),
    limit: Number(limitSelect.value),
  });
  const reset = () => ctx.go("/observatory", {});
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      apply();
    }
  });

  root.append(panel({
    title: "观察筛选",
    sub: "时间窗按 MedRadar 的 observed_at 过滤；企业/赛道来自当前时间窗的 facet，包含「未映射」选项（如果存在）；采集阶段是另一条独立口径，不是变化类型",
    body: el("div", { class: "obs-filter-rows" },
      windowChips,
      changeChips,
      phaseChips,
      el("div", { class: "muted tiny", text: PHASE_SENTENCE }),
      el("div", { class: "filter-bar" },
        el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "数据源" }), sourceSelect),
        el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "企业" }), companySelect),
        el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "技术赛道" }), trackSelect),
        el("div", { class: "filter-field wide" }, el("span", { class: "filter-label", text: "标题关键词 q" }), searchInput),
        el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: " " }),
          el("div", { class: "row wrap" },
            textButton("应用筛选", apply, { primary: true, testid: "observatory-apply" }),
            textButton("重置", reset, { testid: "observatory-reset" }),
            limitSelect)),
      ),
      el("div", { class: "muted tiny", text: "关键词只匹配记录标题（通常是来源原文，多为英文）；中文企业或赛道请使用下拉筛选。「未映射」表示来源记录未能被验证映射，不是零活动。" }),
    ),
  }));

  /* --------------------------------------------------------- event table */
  const items = events.items || [];
  const total = Number(events.total || 0);
  const offset = Number(events.offset || 0);
  const limit = Number(events.limit || filters.limit);
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + items.length, total);

  function pager() {
    return el("div", { class: "pager" },
      textButton("← 上一页", () => goFilters({ offset: Math.max(0, offset - limit) }), { disabled: offset <= 0, testid: "observatory-prev" }),
      el("span", { class: "mono", text: `第 ${page} / ${pageCount} 页 · ${fmtInt(from)}–${fmtInt(to)} / ${fmtInt(total)}` }),
      textButton("下一页 →", () => goFilters({ offset: offset + limit }), { disabled: offset + limit >= total, testid: "observatory-next" }));
  }

  const table = dataTable({
    columns: [
      { key: "source", label: "来源 / 记录类型", format: (row) => sourceCell(row) },
      { key: "title", label: "记录与时间口径", format: (row) => el("div", null, el("div", { class: "obs-title", text: row.title || "—" }), timeBlock(row)) },
      { key: "company", label: "企业（映射状态）", format: (row) => companyCell(row) },
      { key: "track", label: "技术赛道", format: (row) => trackCell(row) },
      {
        key: "change",
        label: "变化 / 采集阶段",
        format: (row) => el("div", { class: "obs-cell-stack" }, changeBadge(row), phaseBadge(row)),
      },
      { key: "observed_at", label: "观察时间", format: (row) => el("div", { class: "obs-cell-stack" }, el("span", { class: "mono", text: fmtDateTime(row.observed_at) }), el("span", { class: "muted tiny", text: `首次观察 ${fmtDateTime(row.first_seen_at)}` })) },
      { key: "event_at", label: "事件时间", format: (row) => el("div", { class: "obs-cell-stack" }, el("span", { class: "mono", text: row.event_at || "来源未提供" }), el("span", { class: "muted tiny", text: row.event_at_precision || "unknown" })) },
      { key: "url", label: "原始来源", format: (row) => sourceLink(row, { small: true }) },
    ],
    rows: items,
    rowClick: (row) => openObservation(row),
    rowAttrs: (row) => ({ testid: "observatory-row", dataset: { observationId: row.observation_id, changeState: row.change_state } }),
    empty: "该时间窗与筛选条件下没有观察记录。",
  });

  const eventBody = el("div");
  if (!ledgerExists) {
    eventBody.append(el("div", { class: "panel-body" }, emptyState(
      ledger.honesty_zh || "观察账本不存在，因此没有任何观察记录。",
      { title: "尚无观察记录" },
    )));
  } else if (!items.length) {
    eventBody.append(el("div", { class: "panel-body" }, emptyState(
      filters.phase
        ? `当前时间窗内没有「${PHASE_SHORT[filters.phase] || filters.phase}」的记录。没有该阶段的记录是诚实的空结果，不等于系统没有观察过任何记录；可切换阶段或查看更大的时间窗。`
        : "当前时间窗 / 变化类型 / 筛选条件下没有观察记录。请调整筛选，或查看更大的时间窗。",
      { title: "该筛选下没有观察记录", actionLabel: "重置筛选", onAction: reset },
    )));
  } else {
    eventBody.append(table);
  }
  root.append(panel({
    title: "观察到的变化",
    sub: `窗口 ${filters.window} · 每行同时给出「事件发生于」「首次观察于」「来源发布时间」三个独立时间口径，以及该记录的采集阶段；点击行打开版本链与映射历史`,
    right: items.length ? pager() : null,
    dense: true,
    body: eventBody,
    foot: items.length
      ? `共 ${fmtInt(total)} 条变化 · change=${filters.change}` +
        (filters.phase ? ` · phase=${filters.phase}` : "") +
        (filters.source ? ` · source=${filters.source}` : "") +
        (filters.company ? ` · company=${filters.company}` : "") +
        (filters.track ? ` · track=${filters.track}` : "") +
        (filters.q ? ` · q=${filters.q}` : "")
      : null,
  }));

  /* ------------------------------------------------------- source panel */
  const sourceRows = sourcesPayload.sources || [];
  const sourcesBody = el("div");
  if (!sourceRows.length) {
    sourcesBody.append(emptyState(
      ledgerExists
        ? "账本已建立，但还没有任何数据源同步记录（尚未运行采集）。"
        : "观察账本尚不存在，因此没有数据源同步状态。",
      { title: "没有数据源同步状态" },
    ));
  } else {
    sourcesBody.append(el("div", { class: "obs-source-grid" }, ...sourceRows.map((source) => sourcePanel(source))));
  }
  root.append(panel({
    title: "数据源同步状态",
    sub: "所有来源均为轮询采集（不是实时推送）：声明周期、最近成功/失败、实测观察延迟与已验证实体覆盖分开展示",
    body: sourcesBody,
  }));

  /* --------------------------------------------------------- limitations */
  const limitations = summary.limitations || [];
  if (limitations.length) {
    root.append(panel({
      title: "必须与观察一起阅读的口径限制",
      sub: `${limitations.length} 条已声明的观察/时间口径限制`,
      body: notice({
        tone: "muted",
        title: "观察站口径",
        items: limitations.map((item) => item.text_zh),
      }),
    }));
  }

  return { title: "实时观察站" };
}
