/* Event detail drawer: the terminal node of the evidence chain.
   Every field shown comes from GET /api/evidence/{event_id}. */
import { api } from "./api.js";
import { el, fmtDate, fmtDateTime, kindLabel, buildHash } from "./util.js";
import {
  openDrawer, skeletonBlock, errorState, badge, kvList, valueTable,
  notice, list, disclosure, tierBadge,
} from "./components.js";

const MATCH_LABELS = {
  roster: ["名册映射", "badge-teal"],
  exact_alias: ["精确名称匹配（待复核）", "badge-amber"],
  unmatched: ["未映射企业", "badge-muted"],
  unmapped: ["未映射", "badge-muted"],
  derived: ["派生", "badge-violet"],
};

export function matchBadge(method, note = null) {
  const entry = MATCH_LABELS[method] || [method || "未映射", null];
  return badge(entry[0], entry[1] || null, note);
}

export function eventHref(eventId, params = {}) {
  return buildHash("/evidence", { ...params, event: eventId });
}

export function eventRowAttrs(row) {
  const id = row.event_id;
  return {
    testid: "event-row",
    dataset: { eventId: id, eventHref: eventHref(id) },
  };
}

export function eventRowButton(event, { compact = false } = {}) {
  const button = el("button", {
    type: "button",
    class: "ev-item",
    title: event.title || "",
    dataset: { eventId: event.event_id, eventHref: eventHref(event.event_id) },
  });
  button.dataset.testid = "event-row";
  button.append(
    el("span", { class: "ev-date", text: fmtDate(event.event_date) }),
    el("span", { class: "ev-title", text: compact ? (event.title || "") : `${kindLabel(event.kind)} · ${event.title || ""}` }),
  );
  button.addEventListener("click", () => openEvent(event.event_id));
  return button;
}

export async function openEvent(eventId, { replaceUrl = null } = {}) {
  openDrawer({
    title: "事件详情",
    sub: eventId,
    body: skeletonBlock(7),
  });
  if (typeof replaceUrl === "function") replaceUrl(eventId);
  try {
    const detail = await api.event(eventId);
    const event = detail.event || {};
    openDrawer({
      title: `${kindLabel(event.kind)} · ${fmtDate(event.event_date)}`,
      sub: `${event.event_id}`,
      body: renderDetail(detail),
    });
  } catch (error) {
    openDrawer({
      title: "事件详情",
      sub: eventId,
      body: errorState(error, () => openEvent(eventId)),
    });
  }
}

function renderDetail(detail) {
  const event = detail.event || {};
  const body = el("div");
  body.dataset.testid = "event-detail";

  const flagRow = el("div", { class: "row wrap mb-8" });
  flagRow.append(
    badge(kindLabel(event.kind), "blue"),
    badge((detail.source && detail.source.label_zh) || event.source || "未知来源", "muted"),
    event.company_name_zh ? badge(event.company_name_zh, "teal") : badge("企业未映射", "muted"),
    matchBadge(event.company_match),
    badge(event.track_name_zh || "未映射赛道", event.track_mapped ? "violet" : "muted"),
    event.as_of ? badge(`数据 as-of ${event.as_of}`, "muted") : null,
  );
  body.append(flagRow);

  body.append(el("div", { class: "drawer-section" },
    el("h4", { text: "记录标题" }),
    el("div", { style: "font-size:12.5px;line-height:1.6", text: event.title || "—" }),
    event.summary ? el("div", { class: "muted small mt-8", text: event.summary }) : null,
  ));

  body.append(el("div", { class: "drawer-section" },
    el("h4", { text: "日期与时间口径" }),
    kvList([
      { key: "event_date（事件日）", value: fmtDate(detail.dates ? detail.dates.event_date : event.event_date) },
      { key: "published_at（发布）", value: detail.dates && detail.dates.published_at ? fmtDateTime(detail.dates.published_at) : "—" },
      { key: "available_at（可用）", value: detail.dates && detail.dates.available_at ? fmtDateTime(detail.dates.available_at) : "—" },
      { key: "timestamp_quality", value: (detail.dates && detail.dates.timestamp_quality) || event.timestamp_quality || "—" },
      { key: "as_of（快照）", value: event.as_of || "—" },
      { key: "note_zh", value: (detail.dates && detail.dates.note_zh) || "—" },
    ]),
  ));

  body.append(el("div", { class: "drawer-section" },
    el("h4", { text: "企业归属（映射来源）" }),
    kvList([
      { key: "company_key", value: event.company_key || "—" },
      { key: "company_name_zh", value: event.company_name_zh || "—" },
      { key: "applicant_raw", value: event.applicant_raw || "—" },
      { key: "company_match", value: event.company_match || "—" },
      { key: "company_method", value: (detail.mapping && detail.mapping.company_method) || "—" },
      { key: "company_note_zh", value: (detail.mapping && detail.mapping.company_note_zh) || "—" },
    ]),
  ));

  body.append(el("div", { class: "drawer-section" },
    el("h4", { text: "赛道映射（产品代码）" }),
    kvList([
      { key: "track", value: event.track_name_zh || "未映射赛道" },
      { key: "track_id", value: event.track_id || "—" },
      { key: "domain", value: (detail.track && detail.track.domain_label_zh) || "—" },
      { key: "track_method", value: (detail.mapping && detail.mapping.track_method) || "—" },
      { key: "track_note_zh", value: (detail.mapping && detail.mapping.track_note_zh) || "—" },
      { key: "product_code", value: event.product_code || "—" },
      detail.product_code
        ? { key: "device_name", value: detail.product_code.device_name || "—" }
        : null,
      detail.product_code && detail.product_code.specialty
        ? { key: "specialty", value: detail.product_code.specialty }
        : null,
      detail.product_code && detail.product_code.regulation_number
        ? { key: "regulation", value: detail.product_code.regulation_number }
        : null,
      detail.product_code && detail.product_code.definition
        ? { key: "definition", value: detail.product_code.definition }
        : null,
    ].filter(Boolean)),
  ));

  body.append(el("div", { class: "drawer-section" },
    el("h4", { text: "来源与原始链接" }),
    kvList([
      { key: "source", value: (detail.source && detail.source.label_zh) || event.source || "—" },
      { key: "market", value: (detail.source && detail.source.market) || "—" },
      { key: "coverage", value: (detail.source && detail.source.coverage_zh) || "—" },
      { key: "caveat", value: (detail.source && detail.source.caveat_zh) || "—" },
    ]),
    renderSourceLink(detail),
  ));

  const payload = detail.payload || {};
  if (payload && Object.keys(payload).length) {
    body.append(el("div", { class: "drawer-section" },
      disclosure(`原始字段 payload（${Object.keys(payload).length} 个字段）`, valueTable(payload)),
    ));
  }

  if (detail.limitations && detail.limitations.length) {
    body.append(el("div", { class: "drawer-section" },
      el("h4", { text: "限制说明" }),
      list(detail.limitations),
    ));
  }

  const actions = el("div", { class: "row wrap mt-12" });
  if (event.company_key) {
    actions.append(el("a", {
      class: "btn btn-sm",
      href: buildHash(`/companies/${event.company_key}`),
      text: "查看企业画像",
    }));
  }
  if (event.track_id) {
    actions.append(el("a", {
      class: "btn btn-sm",
      href: buildHash(`/radar/${event.track_id}`),
      text: "查看该赛道",
    }));
  }
  actions.append(el("a", {
    class: "btn btn-sm",
    href: eventHref(event.event_id),
    text: "该记录的固定链接",
    title: "在证据浏览器中通过 URL 直接打开此记录",
  }));
  body.append(actions);

  return body;
}

function renderSourceLink(detail) {
  const url = (detail.links && detail.links.source_url) || (detail.event && detail.event.url) || "";
  const row = el("div", { class: "mt-8" });
  if (url) {
    const anchor = el("a", {
      class: "btn btn-sm btn-primary",
      href: url,
      target: "_blank",
      rel: "noopener noreferrer",
      text: "打开原始来源 ↗",
      title: url,
    });
    anchor.dataset.testid = "event-source-link";
    row.append(anchor, el("div", { class: "muted tiny mt-4 mono", text: url }));
  } else {
    const missing = el("span", { class: "muted", text: "该记录没有可用的原始链接" });
    missing.dataset.testid = "event-source-link";
    row.append(missing);
  }
  return row;
}
