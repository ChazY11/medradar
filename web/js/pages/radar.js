/* #/radar — eight technology domains with real totals, deltas and sparklines. */
import { api } from "../api.js";
import { el, fmtInt, fmtPct, fmtPctSigned, fmtSigned, buildHash, toneForDelta } from "../util.js";
import {
  pageHead, panel, badge, dataTable, notice, errorState, skeletonBlock, linkButton, emptyState,
} from "../components.js";
import { sparkline } from "../charts.js";

export async function mount(root, ctx) {
  const choices = (ctx.meta.window_choices || []).filter((value) => Number(value) > 0);
  const windows = choices.length ? choices.map(Number) : [3, 5, 10];
  let years = Number(ctx.query.get("years") || windows[0] || 3);
  if (!windows.includes(years)) years = windows[0] || 3;

  const curatedValue = el("b", { text: "—" });
  const head = pageHead({
    title: "技术雷达",
    subtitle: "八个技术领域、重点赛道的公开活动记录。统计探测信号只表示季度记录数偏离历史基线，不等于因果，也不是预测。",
    captions: [
      { label: "窗口", value: `${years} 年` },
      { label: "领域", value: `${(ctx.meta.domains || []).length} 个` },
      { label: "重点赛道", value: curatedValue },
      { label: "全库分类", value: `${(ctx.meta.tracks || []).length} 条` },
    ],
    actions: [
      windowSeg(windows, years, (value) => ctx.go("/radar", { years: value })),
      linkButton("#/evidence", "证据浏览器"),
    ],
  });
  root.append(head);

  const content = el("div", null, skeletonBlock(8));
  root.append(content);

  let radar;
  try {
    radar = await api.radar(years);
  } catch (error) {
    content.replaceChildren(errorState(error, () => ctx.refresh(), { title: "技术雷达加载失败" }));
    return { title: "技术雷达" };
  }

  content.replaceChildren();
  const domains = radar.domains || [];
  const curatedTracks = domains.reduce((total, domain) => total + (domain.tracks || []).length, 0);
  curatedValue.textContent = `${curatedTracks} 个`;
  const subtitleNode = head.querySelector(".page-sub");
  if (subtitleNode) {
    subtitleNode.textContent = `${domains.length} 个技术领域、${curatedTracks} 个重点赛道的公开活动记录；其余 ${(ctx.meta.tracks || []).length - curatedTracks} 条为全库分类、不在雷达产品视图中。统计探测信号只表示季度记录数偏离历史基线，不等于因果，也不是预测。`;
  }
  const allTracks = [];
  for (const domain of domains) {
    for (const track of domain.tracks || []) {
      allTracks.push({ ...track, domain_id: domain.id, domain_label_zh: domain.label_zh });
    }
  }

  /* ------------------------------------------------------------- domain cards */
  const grid = el("div", { class: "grid", style: "grid-template-columns:repeat(4,minmax(0,1fr))" });
  for (const domain of domains) {
    const tracks = domain.tracks || [];
    const { labels, values } = domainSpark(domain);
    const card = el("div", { class: "domain-card" });
    card.dataset.testid = "radar-domain";
    card.dataset.domainId = domain.id;
    card.style.cursor = "pointer";
    const target = tracks.slice().sort((a, b) => (b.recent || 0) - (a.recent || 0))[0];
    if (target) card.addEventListener("click", () => ctx.go(`/radar/${target.id}`));

    const head = el("div", { class: "domain-head" });
    head.append(el("span", { class: "domain-name", text: domain.label_zh }));
    head.append(el("span", { class: "muted tiny", text: domain.label_en || "" }));
    card.append(head);
    card.append(el("div", { class: "domain-blurb", text: domain.blurb_zh || "" }));

    const stats = el("div", { class: "domain-stats" });
    const numbers = el("div");
    numbers.append(
      el("div", { class: "domain-num", text: fmtInt(domain.recent) }),
      el("div", { class: "muted tiny", text: `近 ${years} 年记录` }),
    );
    const delta = el("div", { class: "domain-delta" });
    delta.append(
      el("div", { class: toneForDelta(domain.delta), text: `${fmtSigned(domain.delta)} · ${fmtPctSigned(domain.pct_change)}` }),
      el("div", { class: "muted tiny", text: `前窗 ${fmtInt(domain.prior)}` }),
    );
    stats.append(numbers, delta, sparkline(values, { width: 96, height: 30, color: "#2f81f7", labels }));
    card.append(stats);

    const meta = el("div", { class: "domain-meta" });
    meta.append(
      el("span", { text: `活跃企业 ${fmtInt(domain.companies_active)}` }),
      el("span", { text: `信号 ${fmtInt((domain.signal_tracks || []).length)}` }),
      el("span", { text: `${tracks.length} 条赛道` }),
    );
    card.append(meta);

    const trackRow = el("div", { class: "chip-row" });
    for (const track of tracks) {
      const flagged = (domain.signal_tracks || []).includes(track.id);
      const chip = el("a", {
        class: "chip",
        href: buildHash(`/radar/${track.id}`),
        title: `${track.name_zh} · 近窗 ${fmtInt(track.recent)} · Δ ${fmtSigned(track.delta)}`,
      });
      chip.dataset.testid = "track-link";
      chip.dataset.trackId = track.id;
      chip.append(el("span", { text: track.name_zh }));
      if (flagged) chip.append(el("span", { class: "badge badge-amber", text: "信号" }));
      chip.addEventListener("click", (event) => event.stopPropagation());
      trackRow.append(chip);
    }
    card.append(trackRow);
    grid.append(card);
  }
  content.append(panel({
    title: "技术领域总览",
    sub: `近 ${years} 年 vs 之前 ${years} 年 · 点击卡片进入该领域主要赛道`,
    body: grid,
  }));

  /* -------------------------------------------------------- signal tracks */
  const flagged = allTracks.filter((track) => track.signal && track.signal.flagged);
  const signalBody = el("div");
  if (!flagged.length) {
    signalBody.append(emptyState("该窗口内没有达到阈值的统计探测信号。", { title: "没有探测信号" }));
  } else {
    signalBody.append(dataTable({
      columns: [
        { key: "domain_label_zh", label: "领域", format: (row) => row.domain_label_zh },
        { key: "name_zh", label: "赛道", format: (row) => el("a", { class: "plain", href: buildHash(`/radar/${row.id}`) }, el("b", { text: row.name_zh })) },
        { key: "recent", label: "近窗", num: true, format: (row) => fmtInt(row.recent) },
        { key: "delta", label: "Δ", num: true, format: (row) => el("span", { class: toneForDelta(row.delta), text: fmtSigned(row.delta) }) },
        {
          key: "z", label: "当前季度 z", num: true,
          format: (row) => el("span", { class: row.signal.direction === "up" ? "tone-up" : "tone-down", text: row.signal.z == null ? "—" : fmtInt(row.signal.z) }),
        },
        { key: "direction", label: "方向", format: (row) => badge(row.signal.direction === "up" ? "高于基线" : "低于基线", row.signal.direction === "up" ? "green" : "amber") },
        { key: "current", label: "当前季度", num: true, format: (row) => fmtInt(row.signal.current) },
        { key: "baseline_mean", label: "基线均值", num: true, format: (row) => row.signal.baseline_mean == null ? "—" : row.signal.baseline_mean.toFixed(2) },
      ],
      rows: flagged,
      rowClick: (row) => ctx.go(`/radar/${row.id}`),
      empty: "没有探测信号",
    }));
  }
  content.append(panel({
    title: "统计探测信号",
    sub: "规则：完整季度计数相对前 8 个季度均值的 z 分数，|z| ≥ 2.5 且当前季度 ≥ 5 条",
    right: badge("Detected Signal", "amber"),
    body: signalBody,
    note: [radar.method?.caveat || "", "信号只在当前季度末被触发；它不构成对未来的预测。"],
  }));

  /* ------------------------------------------------------ mapping + method */
  content.append(panel({
    title: "覆盖与方法",
    sub: "未映射记录不会被当作零活动",
    body: [
      notice({
        tone: "muted",
        title: "映射覆盖",
        body: `窗口内已映射 ${fmtInt(radar.mapped_records)} 条 / 未映射 ${fmtInt(radar.unmapped_records)} 条（赛道映射覆盖 ${fmtPct(radar.track_mapping_coverage, 1)}）。未映射记录不计入任何赛道，也不代表该赛道没有活动。`,
      }),
      radar.method?.signal ? notice({ tone: "blue", title: "信号方法", body: radar.method.signal }) : null,
    ].filter(Boolean),
  }));

  return { title: "技术雷达" };
}

function windowSeg(windows, years, onChange) {
  const node = el("div", { class: "seg" });
  for (const value of windows) {
    node.append(el("button", {
      type: "button",
      class: `seg-btn${value === years ? " active" : ""}`,
      text: `${value} 年`,
      onclick: () => onChange(value),
    }));
  }
  return node;
}

function domainSpark(domain) {
  const tracks = (domain.tracks || []).filter((track) => (track.spark || []).length);
  if (!tracks.length) return { labels: [], values: [] };
  const labels = tracks[0].spark.map((point) => point.period);
  const values = labels.map((period) => tracks.reduce((total, track) => {
    const point = (track.spark || []).find((item) => item.period === period);
    return total + (point ? point.count : 0);
  }, 0));
  return { labels, values };
}
