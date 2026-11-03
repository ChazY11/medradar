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
import { el, fmtInt, fmtDateTime, fmtNum } from "../util.js";
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

/* ---------------------------------------------------------------- mounting */
export async function mount(root, ctx) {
  const allowedWindows = WINDOW_OPTIONS.map((option) => option.id);
  const allowedChanges = CHANGE_OPTIONS.map((option) => option.id);
  const filters = {
    window: allowedWindows.includes(ctx.query.get("window")) ? ctx.query.get("window") : "7d",
    change: allowedChanges.includes(ctx.query.get("change")) ? ctx.query.get("change") : "all",
    source: ctx.query.get("source") || "",
    company: ctx.query.get("company") || "",
    track: ctx.query.get("track") || "",
    q: ctx.query.get("q") || "",
    limit: PAGE_LIMITS.includes(Number(ctx.query.get("limit"))) ? Number(ctx.query.get("limit")) : 50,
    offset: Math.max(0, Number(ctx.query.get("offset")) || 0),
  };

  root.append(skeletonBlock(8));
  let summary;
  let events;
  let sourcesPayload;
  try {
    [summary, events, sourcesPayload] = await Promise.all([
      api.observatorySummary(),
      api.observatoryEvents({
        window: filters.window,
        change: filters.change,
        source: filters.source || undefined,
        company: filters.company || undefined,
        track: filters.track || undefined,
        q: filters.q || undefined,
        limit: filters.limit,
        offset: filters.offset,
      }),
      api.observatorySources(),
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
    sub: "时间窗按 MedRadar 的 observed_at 过滤；企业/赛道来自当前时间窗的 facet，包含「未映射」选项（如果存在）",
    body: el("div", { class: "obs-filter-rows" },
      windowChips,
      changeChips,
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
      { key: "change", label: "变化", format: (row) => changeBadge(row) },
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
      "当前时间窗 / 变化类型 / 筛选条件下没有观察记录。请调整筛选，或查看更大的时间窗。",
      { title: "该筛选下没有观察记录", actionLabel: "重置筛选", onAction: reset },
    )));
  } else {
    eventBody.append(table);
  }
  root.append(panel({
    title: "观察到的变化",
    sub: `窗口 ${filters.window} · 每行同时给出「事件发生于」「首次观察于」「来源发布时间」三个独立时间口径；点击行打开版本链与映射历史`,
    right: items.length ? pager() : null,
    dense: true,
    body: eventBody,
    foot: items.length
      ? `共 ${fmtInt(total)} 条变化 · change=${filters.change}` +
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
