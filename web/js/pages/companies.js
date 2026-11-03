/* #/companies — featured company cards + searchable full roster. */
import { el, fmtInt, fmtRange, buildHash, debounce } from "../util.js";
import { pageHead, panel, badge, dataTable, emptyState, linkButton } from "../components.js";

export async function mount(root, ctx) {
  const payload = ctx.companies;
  const all = payload.companies || [];
  const featured = payload.featured || [];
  const initialQuery = ctx.query.get("q") || "";

  root.append(pageHead({
    title: "企业情报",
    subtitle: "五家重点企业的记录结构，以及可检索的完整企业名册。所有计数来自企业归属事件（仓库名册 + 补充的精确名称映射）。",
    captions: [
      { label: "名册企业", value: fmtInt(payload.total) },
      { label: "重点企业", value: fmtInt(featured.length) },
      { label: "排序", value: "按事件总数倒序" },
    ],
    actions: [linkButton("#/compare", "企业对比", { primary: true }), linkButton("#/evidence", "证据浏览器")],
  }));

  /* ------------------------------------------------------- featured cards */
  const cardGrid = el("div", { class: "grid", style: "grid-template-columns:repeat(5,minmax(0,1fr))" });
  for (const company of featured) {
    const card = el("a", {
      class: "company-card",
      href: buildHash(`/companies/${company.key}`),
      dataset: { companyKey: company.key },
    });
    card.dataset.testid = "company-card";

    const head = el("div", { class: "cc-head" });
    head.append(
      el("span", { class: "cc-name", text: company.name_zh }),
      el("span", { class: "cc-en", text: company.name_en || "" }),
    );
    card.append(head);

    const facts = el("div", { class: "cc-facts" });
    if (company.ticker) facts.append(el("span", null, "代码 ", el("b", { text: company.ticker })));
    if (company.exchange) facts.append(el("span", { text: company.exchange }));
    if (company.hq_zh) facts.append(el("span", { text: company.hq_zh }));
    card.append(facts);

    const stats = el("div", { class: "cc-stats" });
    for (const [label, value] of [["事件", company.events], ["审批", company.approvals], ["召回", company.recalls], ["试验", company.trials]]) {
      stats.append(el("div", { class: "cc-stat" }, el("div", { class: "l", text: label }), el("div", { class: "v", text: fmtInt(value) })));
    }
    card.append(stats);

    const foot = el("div", { class: "row between" });
    foot.append(
      el("span", { class: "cc-span", text: `${fmtRange(company.first_event, company.last_event)} · ${fmtInt(company.tracks)} 赛道` }),
      company.roster_present ? badge("名册", "teal") : badge("待复核", "amber", "该企业不在仓库原有名册中，事件归属来自精确名称匹配。"),
    );
    card.append(foot);
    cardGrid.append(card);
  }
  root.append(panel({
    title: "重点企业",
    sub: "点击卡片进入企业画像：KPI、证据化结论、赛道结构、覆盖来源与里程碑",
    body: cardGrid,
  }));

  /* ------------------------------------------------------- roster search */
  const searchInput = el("input", {
    type: "search",
    value: initialQuery,
    placeholder: "搜索企业（中文名 / 英文名 / key / 代码）",
    "aria-label": "搜索企业",
    autocomplete: "off",
    style: "width:320px",
  });
  const countLabel = el("span", { class: "muted small" });
  const tableHost = el("div");
  let current = initialQuery;

  function rowsFor(query) {
    const needle = query.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((company) => [company.name_zh, company.name_en, company.key, company.ticker, company.hq_zh]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(needle)));
  }

  function renderTable() {
    const rows = rowsFor(current);
    countLabel.textContent = `匹配 ${rows.length} / ${all.length} 家企业`;
    tableHost.replaceChildren();
    if (!rows.length) {
      tableHost.append(emptyState("该搜索下没有企业", {
        title: "没有匹配的企业",
        actionLabel: "清除检索",
        onAction: () => {
          current = "";
          searchInput.value = "";
          renderTable();
          ctx.replaceUrl({ q: null });
        },
      }));
      return;
    }
    tableHost.append(dataTable({
      columns: [
        { key: "name_zh", label: "企业", format: (row) => el("span", null, el("b", { text: row.name_zh }), el("span", { class: "muted", text: `  ${row.name_en || ""}` })) },
        { key: "ticker", label: "代码", format: (row) => row.ticker || "—" },
        { key: "exchange", label: "交易所", format: (row) => row.exchange || "—" },
        { key: "events", label: "事件", num: true, format: (row) => fmtInt(row.events) },
        { key: "approvals", label: "审批", num: true, format: (row) => fmtInt(row.approvals) },
        { key: "recalls", label: "召回", num: true, format: (row) => fmtInt(row.recalls) },
        { key: "trials", label: "试验", num: true, format: (row) => fmtInt(row.trials) },
        { key: "corporate", label: "8-K", num: true, format: (row) => fmtInt(row.corporate) },
        { key: "tracks", label: "赛道", num: true, format: (row) => fmtInt(row.tracks) },
        { key: "span", label: "覆盖期", format: (row) => fmtRange(row.first_event, row.last_event) },
        {
          key: "status", label: "归属",
          format: (row) => (row.featured ? badge("重点", "blue") : row.roster_present ? badge("名册", "teal") : badge("待复核", "amber")),
        },
      ],
      rows,
      rowClick: (row) => ctx.go(`/companies/${row.key}`),
      rowAttrs: (row) => ({ testid: "company-card", dataset: { companyKey: row.key } }),
    }));
  }

  const toolbar = el("div", { class: "row wrap between" },
    el("div", { class: "row wrap" }, searchInput, countLabel),
    el("div", { class: "muted small", text: payload.method_zh || "" }),
  );
  root.append(panel({
    title: "完整企业名册",
    sub: "事件归属来自仓库名册；补充映射的企业标注为「待复核」",
    body: [toolbar, el("div", { class: "mt-8" }, tableHost)],
  }));

  searchInput.addEventListener("input", debounce(() => {
    current = searchInput.value;
    ctx.replaceUrl({ q: current || null });
    renderTable();
  }, 140));

  renderTable();
  return { title: "企业情报" };
}
