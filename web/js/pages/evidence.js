/* #/evidence — the evidence explorer: filters, paginated result table,
   row → event detail drawer with mapping provenance and source link. */
import { api } from "../api.js";
import {
  el, fmtInt, fmtDate, fmtDateTime, kindLabel, buildHash, normalizeCompanyList,
} from "../util.js";
import {
  pageHead, panel, badge, dataTable, notice, errorState, skeletonBlock, emptyState,
  linkButton, textButton,
} from "../components.js";
import { openEvent, eventRowAttrs, eventHref, matchBadge } from "../event.js";

export async function mount(root, ctx) {
  const meta = ctx.meta;
  const roster = (ctx.companies.companies || []).slice().sort((a, b) => {
    if (a.featured !== b.featured) return a.featured ? -1 : 1;
    return (b.events || 0) - (a.events || 0);
  });
  const rosterKeys = new Set(roster.map((company) => company.key));
  const tracks = meta.tracks || [];
  const trackIds = new Set(tracks.map((track) => track.id));
  const metrics = meta.metrics || {};
  const sources = meta.sources || [];
  const sourceIds = new Set(sources.map((source) => source.id));

  const filters = {
    companies: normalizeCompanyList(ctx.query.get("companies")).filter((key) => rosterKeys.has(key)),
    track: trackIds.has(ctx.query.get("track")) ? ctx.query.get("track") : "",
    metric: metrics[ctx.query.get("metric")] ? ctx.query.get("metric") : "",
    source: sourceIds.has(ctx.query.get("source")) ? ctx.query.get("source") : "",
    start: ctx.query.get("start") || "",
    end: ctx.query.get("end") || "",
    q: ctx.query.get("q") || "",
    limit: [25, 50, 100, 200].includes(Number(ctx.query.get("limit"))) ? Number(ctx.query.get("limit")) : 50,
    offset: Math.max(0, Number(ctx.query.get("offset")) || 0),
  };

  root.append(pageHead({
    title: "证据浏览器",
    subtitle: "按企业、赛道、指标、来源、时间与关键词检索原始记录；每一行都能打开事件详情，查看映射来源、日期口径与原始链接。",
    captions: [
      { label: "排序", value: "事件日期倒序" },
      { label: "口径", value: "记录条数，不是产品数" },
      { label: "链接", value: "仅显示 API 返回的原始链接" },
    ],
    actions: [linkButton("#/analyst", "研究助手"), linkButton("#/companies", "企业情报")],
  }));

  /* ------------------------------------------------------------- filters */
  const companySelect = el("select", { multiple: true, size: 5, "aria-label": "企业（可多选）", style: "min-width:190px;height:96px" });
  for (const company of roster) {
    companySelect.append(el("option", {
      value: company.key,
      text: `${company.name_zh}${company.featured ? " ★" : ""}（${company.key}）`,
      selected: filters.companies.includes(company.key),
    }));
  }
  companySelect.dataset.testid = "evidence-filter-company";

  const trackSelect = el("select", { "aria-label": "技术赛道" });
  trackSelect.append(el("option", { value: "", text: "全部赛道" }));
  for (const track of tracks) trackSelect.append(el("option", { value: track.id, text: track.name_zh, selected: track.id === filters.track }));
  trackSelect.dataset.testid = "evidence-filter-track";

  const metricSelect = el("select", { "aria-label": "指标" });
  metricSelect.append(el("option", { value: "", text: "全部指标" }));
  for (const [key, value] of Object.entries(metrics)) {
    metricSelect.append(el("option", { value: key, text: value.label_zh, selected: key === filters.metric }));
  }
  metricSelect.dataset.testid = "evidence-filter-metric";

  const sourceSelect = el("select", { "aria-label": "来源" });
  sourceSelect.append(el("option", { value: "", text: "全部来源" }));
  for (const source of sources) {
    sourceSelect.append(el("option", { value: source.id, text: source.label_zh, selected: source.id === filters.source }));
  }
  sourceSelect.dataset.testid = "evidence-filter-source";

  const startInput = el("input", { type: "date", value: filters.start, "aria-label": "开始日期" });
  startInput.dataset.testid = "evidence-filter-start";
  const endInput = el("input", { type: "date", value: filters.end, "aria-label": "结束日期" });
  endInput.dataset.testid = "evidence-filter-end";
  const searchInput = el("input", {
    type: "search", value: filters.q,
    placeholder: "原文关键词（标题/申请人/摘要，多为英文）",
    maxlength: 120, "aria-label": "关键词",
    title: "q 为原文关键词（标题 / 申请人 / 摘要，通常为英文）；中文企业或赛道请使用筛选器。",
  });
  searchInput.dataset.testid = "evidence-search";
  searchInput.className = "search-wide";
  searchInput.style.width = "260px";

  function collect() {
    const companies = Array.from(companySelect.selectedOptions).map((option) => option.value);
    return {
      companies,
      track: trackSelect.value,
      metric: metricSelect.value,
      source: sourceSelect.value,
      start: startInput.value,
      end: endInput.value,
      q: searchInput.value.trim(),
      limit: limitSelect.value,
      offset: 0,
    };
  }

  function apply() {
    const next = collect();
    if (next.start && next.end && next.start > next.end) {
      noticeHost.replaceChildren(notice({ tone: "amber", title: "时间区间无效", body: "开始日期不能晚于结束日期。" }));
      return;
    }
    noticeHost.replaceChildren();
    ctx.go("/evidence", next);
  }

  function reset() {
    ctx.go("/evidence", {});
  }

  const limitSelect = el("select", { "aria-label": "每页条数" });
  for (const value of [25, 50, 100, 200]) {
    limitSelect.append(el("option", { value: String(value), text: `${value} 条/页`, selected: value === filters.limit }));
  }
  limitSelect.dataset.testid = "evidence-filter-limit";

  const applyButton = textButton("应用筛选", apply, { primary: true, small: false, testid: "evidence-apply" });
  const resetButton = textButton("重置", reset, { testid: "evidence-reset" });
  const noticeHost = el("div");

  const filterBody = el("div");
  const bar = el("div", { class: "filter-bar" },
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "企业（可多选）" }), companySelect),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "技术赛道" }), trackSelect),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "指标" }), metricSelect),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "来源" }), sourceSelect),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "开始日期" }), startInput),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "结束日期" }), endInput),
    el("div", { class: "filter-field wide" }, el("span", { class: "filter-label", text: "关键词" }), searchInput),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: " " }),
      el("div", { class: "row" }, applyButton, resetButton, limitSelect)),
  );
  filterBody.append(bar, el("div", { class: "muted tiny mt-8", text: "关键词 q 为原文关键词（标题 / 申请人 / 摘要，通常为英文），不支持中文语义匹配；中文企业或赛道请使用上方筛选器。" }), noticeHost);
  const activeChips = el("div", { class: "filter-active mt-8" });
  filterBody.append(activeChips);
  root.append(panel({
    title: "筛选条件",
    sub: "多选企业请按住 Ctrl / Cmd / Shift；应用后 URL 会记录当前筛选",
    body: filterBody,
  }));

  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      apply();
    }
  });

  /* ------------------------------------------------------------- results */
  const results = el("div", { class: "mt-12" });
  results.append(panel({ title: "检索结果", body: skeletonBlock(6) }));
  root.append(results);

  let payload;
  try {
    payload = await api.evidence({
      companies: filters.companies.join(",") || undefined,
      track: filters.track || undefined,
      metric: filters.metric || undefined,
      source: filters.source || undefined,
      start: filters.start || undefined,
      end: filters.end || undefined,
      q: filters.q || undefined,
      limit: filters.limit,
      offset: filters.offset,
    });
  } catch (error) {
    results.replaceChildren(errorState(error, () => ctx.refresh(), { title: "证据检索失败" }));
    return { title: "证据浏览器" };
  }

  results.replaceChildren();
  const items = payload.items || [];
  const total = payload.total || 0;
  const offset = payload.offset || 0;
  const limit = payload.limit || filters.limit;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + items.length, total);
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const page = Math.floor(offset / limit) + 1;

  /* active filter chips */
  const active = [];
  for (const key of filters.companies) {
    const company = roster.find((item) => item.key === key);
    active.push(el("span", { class: "chip chip-static" }, el("span", { text: company ? company.name_zh : key }), el("span", { class: "muted tiny", text: key })));
  }
  if (filters.track) active.push(el("span", { class: "chip chip-static", text: `赛道：${tracks.find((track) => track.id === filters.track)?.name_zh || filters.track}` }));
  if (filters.metric) active.push(el("span", { class: "chip chip-static", text: `指标：${metrics[filters.metric]?.label_zh || filters.metric}` }));
  if (filters.source) active.push(el("span", { class: "chip chip-static", text: `来源：${sources.find((source) => source.id === filters.source)?.label_zh || filters.source}` }));
  if (filters.start) active.push(el("span", { class: "chip chip-static mono", text: `≥ ${filters.start}` }));
  if (filters.end) active.push(el("span", { class: "chip chip-static mono", text: `≤ ${filters.end}` }));
  if (filters.q) active.push(el("span", { class: "chip chip-static", text: `关键词：${filters.q}` }));
  activeChips.replaceChildren(...(active.length ? active : [el("span", { class: "muted small", text: "未设置筛选（显示全部记录）" })]));

  const headerRow = el("div", { class: "row wrap between mb-8" });
  headerRow.append(...[
    el("div", { class: "row wrap small" },
      el("span", { text: "共 " }),
      el("b", { class: "mono", text: fmtInt(total) }),
      el("span", { text: " 条 · 当前 " }),
      el("b", { class: "mono", text: `${fmtInt(from)}–${fmtInt(to)}` }),
      el("span", { text: ` · 第 ${page} / ${pageCount} 页` }),
      payload.params ? el("span", { class: "muted tiny mono", text: ` · offset=${offset} limit=${limit}` }) : null,
    ),
  ].filter(Boolean));

  const pager = el("div", { class: "pager" });
  const prev = textButton("← 上一页", () => {
    ctx.go("/evidence", { ...currentParams(), offset: Math.max(0, offset - limit) });
  }, { disabled: offset <= 0, testid: "evidence-prev" });
  const next = textButton("下一页 →", () => {
    ctx.go("/evidence", { ...currentParams(), offset: offset + limit });
  }, { disabled: offset + limit >= total, testid: "evidence-next" });
  pager.append(prev, next);

  function makePager() {
    const node = el("div", { class: "pager" });
    node.append(
      textButton("← 上一页", () => {
        ctx.go("/evidence", { ...currentParams(), offset: Math.max(0, offset - limit) });
      }, { disabled: offset <= 0 }),
      el("span", { class: "mono", text: `第 ${page} / ${pageCount} 页` }),
      textButton("下一页 →", () => {
        ctx.go("/evidence", { ...currentParams(), offset: offset + limit });
      }, { disabled: offset + limit >= total }),
    );
    return node;
  }

  function currentParams() {
    return {
      companies: filters.companies.join(",") || undefined,
      track: filters.track || undefined,
      metric: filters.metric || undefined,
      source: filters.source || undefined,
      start: filters.start || undefined,
      end: filters.end || undefined,
      q: filters.q || undefined,
      limit,
      offset,
    };
  }

  const table = dataTable({
    columns: [
      { key: "event_date", label: "事件日", format: (row) => el("span", { class: "mono", text: fmtDate(row.event_date) }) },
      { key: "kind", label: "类型", format: (row) => badge(kindLabel(row.kind), "muted") },
      {
        key: "company_name_zh", label: "企业",
        format: (row) => el("span", { class: "nowrap" },
          row.company_name_zh || el("span", { class: "muted", text: "未映射" }),
          row.company_key && row.company_key !== row.company_name_zh
            ? el("span", { class: "muted tiny", text: ` ${row.company_key}` })
            : null),
      },
      { key: "track_name_zh", label: "赛道", format: (row) => row.track_name_zh || el("span", { class: "muted", text: "未映射" }) },
      { key: "source", label: "来源", format: (row) => sources.find((source) => source.id === row.source)?.short_zh || row.source },
      { key: "title", label: "标题", format: (row) => el("div", { class: "cell-title", text: row.title || "—", title: row.title || "" }) },
      { key: "product_code", label: "产品码", format: (row) => row.product_code || "—" },
      { key: "published_at", label: "发布日", format: (row) => el("span", { class: "mono muted", text: row.published_at ? fmtDateTime(row.published_at) : "—" }) },
      { key: "company_match", label: "归属", format: (row) => matchBadge(row.company_match) },
    ],
    rows: items,
    rowClick: (row) => {
      ctx.replaceUrl({ event: row.event_id });
      openEvent(row.event_id);
    },
    rowAttrs: (row) => ({ testid: "evidence-row", dataset: { eventId: row.event_id, eventHref: eventHref(row.event_id) } }),
    empty: "该筛选下没有记录",
  });

  const panelBody = el("div");
  panelBody.append(
    el("div", { class: "panel-body tight" }, headerRow),
    table,
    el("div", { class: "panel-foot" }, makePager()),
  );
  if (!items.length) {
    panelBody.append(el("div", { class: "panel-body" }, emptyState("该筛选下没有记录。", {
      title: "该筛选下没有记录",
      actionLabel: "重置筛选",
      onAction: reset,
    })));
  }
  results.append(panel({
    title: "检索结果",
    sub: "点击任意行打开事件详情（映射来源 · 日期口径 · 原始链接）",
    right: pager,
    dense: true,
    body: panelBody,
  }));

  results.append(panel({
    title: "口径与限制",
    sub: "证据浏览器的检索语义",
    body: [
      notice({
        tone: "muted",
        title: "检索口径",
        body: "结果为公开记录条数，按事件日期倒序。企业筛选使用企业归属映射；赛道筛选只包含已映射记录，因此「未映射」记录不会出现在赛道筛选下。日期区间按 event_date 过滤。",
      }),
      notice({
        tone: "amber",
        title: "链接与日期",
        body: "原始链接只展示 API 返回的字段，不臆造 URL；没有链接时事件详情会明确标注。event_date 是事件发生日期，published_at 是发布日，available_at 是数据可用日，三者可能不同。",
      }),
    ],
  }));

  /* deep link: #/evidence?...&event=<id> opens the drawer once */
  const eventId = ctx.query.get("event");
  if (eventId) {
    openEvent(eventId);
    ctx.replaceUrl({ event: null });
  }

  return { title: "证据浏览器" };
}
