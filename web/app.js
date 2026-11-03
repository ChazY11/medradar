/* MedRadar 2.0 SPA — hash router, app shell and global chrome. */
import { api } from "./js/api.js";
import { el, parseHash, buildHash, fmtInt } from "./js/util.js";
import { closeDrawer, drawerIsOpen, skeletonPage, errorState, notice, pageHead, linkButton } from "./js/components.js";
import * as charts from "./js/charts.js";
import * as overviewPage from "./js/pages/overview.js";
import * as companiesPage from "./js/pages/companies.js";
import * as companyPage from "./js/pages/company.js";
import * as comparePage from "./js/pages/compare.js";
import * as radarPage from "./js/pages/radar.js";
import * as trackPage from "./js/pages/track.js";
import * as analystPage from "./js/pages/analyst.js";
import * as labPage from "./js/pages/lab.js";
import * as evidencePage from "./js/pages/evidence.js";

const ROUTES = [
  { id: "overview", pattern: /^\/overview\/?$/, module: overviewPage, nav: "overview" },
  { id: "companies", pattern: /^\/companies\/?$/, module: companiesPage, nav: "companies" },
  { id: "company", pattern: /^\/companies\/([^/]+)\/?$/, module: companyPage, nav: "companies", params: ["key"] },
  { id: "compare", pattern: /^\/compare\/?$/, module: comparePage, nav: "companies" },
  { id: "radar", pattern: /^\/radar\/?$/, module: radarPage, nav: "radar" },
  { id: "track", pattern: /^\/radar\/([^/]+)\/?$/, module: trackPage, nav: "radar", params: ["track"] },
  { id: "analyst", pattern: /^\/analyst\/?$/, module: analystPage, nav: "analyst" },
  { id: "lab", pattern: /^\/lab\/?$/, module: labPage, nav: "lab" },
  { id: "lab", pattern: /^\/lab\/([^/]+)\/?$/, module: labPage, nav: "lab", params: ["studyId"] },
  { id: "evidence", pattern: /^\/evidence\/?$/, module: evidencePage, nav: "evidence" },
];

const state = { meta: null, companies: null, booted: false };

const main = document.getElementById("main");
const nav = document.getElementById("nav");
const navToggle = document.getElementById("nav-toggle");
const header = document.getElementById("app-header");

function setActiveNav(navKey) {
  for (const link of document.querySelectorAll("[data-nav]")) {
    link.classList.toggle("active", link.dataset.nav === navKey);
  }
}

function go(path, params = {}) {
  const hash = buildHash(path, params);
  if (location.hash === hash) {
    renderRoute();
  } else {
    location.hash = hash;
  }
}

function normalizePath(path) {
  if (!path || path === "/" || path === "") return "/overview";
  return path;
}

function matchRoute(path) {
  for (const route of ROUTES) {
    const match = route.pattern.exec(path);
    if (!match) continue;
    const params = {};
    (route.params || []).forEach((name, index) => {
      params[name] = decodeURIComponent(match[index + 1] || "");
    });
    return { route, params };
  }
  return null;
}

function renderShellMeta(meta) {
  const cutoff = document.getElementById("cutoff-chip");
  if (cutoff) {
    const edge = meta.dataset?.date_range?.last || "—";
    cutoff.textContent = `数据截止 ${edge}`;
    cutoff.dataset.testid = "data-cutoff";
    cutoff.title = `dataset.modified_utc: ${meta.dataset?.modified_utc || "—"}`;
  }
  const footer = document.getElementById("app-footer");
  if (footer) {
    const counts = meta.dataset?.counts || {};
    footer.replaceChildren(
      el("span", null, el("b", { text: "MedRadar" }), document.createTextNode(` ${meta.product?.version || ""} · ${meta.product?.schema || ""}`)),
      el("span", { text: `事件 ${fmtInt(counts.events)} · 企业 ${fmtInt(counts.companies)} · 赛道 ${fmtInt(counts.tracks)} · 数据源 ${fmtInt((meta.sources || []).length)}` }),
      el("span", { text: `数据截止 ${meta.dataset?.date_range?.last || "—"} · 只读研究数据层 · 不展示经验证的前瞻预测` }),
    );
  }
  document.title = "MedRadar · 医疗技术情报";
}

async function boot() {
  main.replaceChildren(skeletonPage());
  try {
    const [meta, companies] = await Promise.all([api.meta(), api.companies(true)]);
    state.meta = meta;
    state.companies = companies;
    state.booted = true;
    renderShellMeta(meta);
    renderRoute();
    // keep the global search box in sync with the evidence route
    syncSearchInput();
  } catch (error) {
    main.replaceChildren(errorState(error, boot, { title: "无法加载产品元数据" }));
  }
}

function syncSearchInput() {
  const input = document.getElementById("global-search-input");
  if (!input) return;
  const { path, query } = parseHash();
  input.value = path === "/evidence" ? query.get("q") || "" : input.value;
}

function notFoundPanel(path) {
  const root = el("div", { class: "page" });
  root.dataset.testid = "page-notfound";
  root.append(
    pageHead({ title: "页面不存在", subtitle: `没有找到路由 ${path}。` }),
    notice({
      tone: "amber",
      title: "可用路由",
      items: [
        "#/overview · 总览",
        "#/companies · 企业情报（含 #/companies/{key}）",
        "#/compare · 企业对比",
        "#/radar · 技术雷达（含 #/radar/{track}）",
        "#/analyst · 研究助手",
        "#/lab · 研究实验室（含 #/lab/{study_id}）",
        "#/evidence · 证据浏览器",
      ],
    }),
    el("div", { class: "mt-12" }, linkButton("#/overview", "返回总览", { primary: true })),
  );
  return root;
}

async function renderRoute() {
  const { path: rawPath, query } = parseHash();
  const path = normalizePath(rawPath);
  if (path !== rawPath) {
    history.replaceState(null, "", `#${path}`);
  }
  charts.reset();
  closeDrawer();
  closeMobileNav();

  const matched = matchRoute(path);
  if (!matched) {
    main.replaceChildren(notFoundPanel(path));
    setActiveNav(null);
    document.title = "页面不存在 · MedRadar";
    return;
  }

  const { route, params } = matched;
  setActiveNav(route.nav);
  const pageRoot = el("div", { class: "page" });
  pageRoot.dataset.testid = `page-${route.id}`;
  main.replaceChildren(pageRoot);
  window.scrollTo({ top: 0, behavior: "auto" });

  const ctx = {
    params,
    query,
    meta: state.meta,
    companies: state.companies,
    go,
    refresh: renderRoute,
    replaceUrl: (paramsPartial) => {
      const next = new URLSearchParams(query.toString());
      for (const [key, value] of Object.entries(paramsPartial || {})) {
        if (value == null || value === "") next.delete(key);
        else next.set(key, String(value));
      }
      const search = next.toString();
      history.replaceState(null, "", `#${path}${search ? `?${search}` : ""}`);
    },
  };

  try {
    const result = await route.module.mount(pageRoot, ctx);
    document.title = result && result.title ? `${result.title} · MedRadar` : "MedRadar · 医疗技术情报";
  } catch (error) {
    console.error("[medradar] page failed", error);
    pageRoot.append(errorState(error, renderRoute, { title: "页面数据加载失败" }));
  }
  syncSearchInput();
}

function closeMobileNav() {
  if (nav) nav.classList.remove("open");
  if (navToggle) navToggle.setAttribute("aria-expanded", "false");
}

function wireChrome() {
  if (navToggle) {
    navToggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  const searchForm = document.getElementById("global-search");
  if (searchForm) {
    searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const input = document.getElementById("global-search-input");
      const value = (input?.value || "").trim();
      go("/evidence", value ? { q: value } : {});
    });
  }
  document.getElementById("drawer-backdrop")?.addEventListener("click", () => closeDrawer());
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawerIsOpen()) {
      closeDrawer();
      event.stopPropagation();
    }
  });
  if (header) {
    // keep the mobile menu from staying open after a route change
    window.addEventListener("hashchange", closeMobileNav);
  }
}

wireChrome();
window.addEventListener("hashchange", renderRoute);
boot();
