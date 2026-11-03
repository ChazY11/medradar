#!/usr/bin/env node
/**
 * MedRadar 2.0 — browser end-to-end acceptance (five MVP user scenarios + Live Observatory).
 *
 * Usage:
 *   node scripts/product_e2e.cjs [baseUrl]
 *
 * Needs Playwright. Resolution order:
 *   1. require("playwright") (local node_modules)
 *   2. PLAYWRIGHT_MODULE env var
 *   3. D:/DEPPSKK/browser-tools/node_modules/playwright (this dev machine)
 *
 * Writes screenshots + report to out/product_e2e/ (gitignored).
 */
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8787";
const OUT_DIR = path.resolve(__dirname, "..", "out", "product_e2e");

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    "playwright",
    "D:/DEPPSKK/browser-tools/node_modules/playwright",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      /* try next */
    }
  }
  throw new Error("playwright not found; set PLAYWRIGHT_MODULE to its install path");
}

const results = [];
const consoleErrors = [];

function record(name, ok, detail, screenshot) {
  results.push({ name, ok, detail, screenshot: screenshot || null });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}  ${detail || ""}`);
}

async function shot(page, name) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const file = path.join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return file;
}

async function textOf(page, selector) {
  const element = await page.$(selector);
  return element ? (await element.innerText()).trim() : "";
}

async function main() {
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text().slice(0, 300));
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${String(error).slice(0, 300)}`));

  const goto = async (route) => {
    await page.goto(`${BASE}/${route}`, { waitUntil: "networkidle", timeout: 45000 });
    await page.waitForTimeout(500);
  };
  const body = async () => (await page.textContent("body")) || "";

  // ---------------------------------------------------------------- scenario 1
  try {
    await goto("#/companies");
    await page.waitForSelector('[data-testid="company-card"]', { timeout: 20000 });
    const card = await page.$('[data-testid="company-card"][data-company-key="mindray"]');
    if (!card) throw new Error("mindray company card not found");
    await card.click();
    await page.waitForSelector('[data-testid="company-profile"]', { timeout: 20000 });
    await page.waitForTimeout(800);
    const text = await body();
    if (!text.includes("迈瑞")) throw new Error("profile does not show 迈瑞医疗");
    const claims = await page.$$eval('[data-testid="claim-card"]', (nodes) => nodes.length);
    if (claims < 1) throw new Error("no evidence-linked claims rendered");
    const coverage = text.includes("数据覆盖") || text.includes("覆盖范围");
    const profile = await page.evaluate(async () => {
      const response = await fetch("/api/companies/mindray?years=5");
      return response.json();
    });
    const headline = profile.headline;
    if (!text.includes(String(headline.approvals_window))) {
      throw new Error(`profile does not show complete-window approvals ${headline.approvals_window}`);
    }
    if (!text.includes("窗口全部") && !text.includes(String(headline.approvals_window_all))) {
      throw new Error("profile does not disclose the requested-window total");
    }
    if (!text.includes("PMA")) throw new Error("profile does not show PMA composition");
    const screenshot = await shot(page, "s1-company-mindray");
    record("Scenario 1 研究一家公司 (Mindray)", coverage, `claims=${claims}; complete=${headline.approvals_window}`, screenshot);
  } catch (error) {
    record("Scenario 1 研究一家公司 (Mindray)", false, String(error.message));
  }

  // ---------------------------------------------------------------- scenario 2
  try {
    await goto("#/compare");
    await page.waitForTimeout(1200);
    const isPressed = async (toggle) => {
      const aria = await toggle.getAttribute("aria-pressed");
      if (aria === "true" || aria === "false") return aria === "true";
      return toggle.evaluate((element) => element.classList.contains("active"));
    };
    for (const key of ["medtronic", "philips"]) {
      const toggle = await page.$(`[data-testid="compare-toggle"][data-company-key="${key}"]`);
      if (!toggle) throw new Error(`compare toggle ${key} not found`);
      if (!(await isPressed(toggle))) await toggle.click();
      await page.waitForTimeout(300);
    }
    const run = await page.$('[data-testid="compare-run"]');
    if (run) await run.click();
    await page.waitForSelector('[data-testid="compare-chart"], [data-testid="page-compare"] svg', { timeout: 30000 });
    await page.waitForTimeout(1500);
    let text = await body();
    if (!text.includes("美敦力") && !text.includes("Medtronic")) throw new Error("medtronic missing from compare output");
    if (!text.includes("飞利浦") && !text.includes("Philips")) throw new Error("philips missing from compare output");
    const warnings = await page.$$eval('[data-testid="compare-warning"]', (nodes) => nodes.length);
    if (warnings < 1) throw new Error("comparability warnings not rendered");
    const compare = await page.evaluate(async () => {
      const response = await fetch("/api/compare?companies=medtronic%2Cphilips&metric=approvals&years=5&granularity=quarter");
      return response.json();
    });
    if (!compare.analysis_window || compare.analysis_window.comparable !== true) {
      throw new Error("compare API did not report a comparable complete-quarter window");
    }
    if (!text.includes(compare.analysis_window.analysis_start)) {
      throw new Error(`compare page does not show analysis window start ${compare.analysis_window.analysis_start}`);
    }
    const warningCodes = new Set((compare.warnings || []).map((warning) => warning.code));
    if (!warningCodes.has("complete_quarter_basis")) {
      throw new Error("complete-quarter basis warning missing from compare API");
    }
    const med = compare.companies.find((company) => company.key === "medtronic");
    const philips = compare.companies.find((company) => company.key === "philips");
    if (!med || !philips) throw new Error("compare API missing selected companies");
    if (med.total_all !== med.total_mapped + med.total_unmapped) {
      throw new Error("compare company total does not split into mapped + unmapped");
    }
    // every reported LQ must reproduce from the disclosed mapped denominators
    for (const row of compare.track_table) {
      for (const cell of row.companies) {
        if (cell.lq_status !== "ok") {
          if (cell.location_quotient !== null) throw new Error("non-ok LQ still carries a number");
          continue;
        }
        const company = compare.companies.find((item) => item.key === cell.key);
        const expected = (cell.n / company.total_mapped) /
          (row.industry_total / compare.comparability.industry_records.mapped_records);
        if (Math.abs(expected - cell.location_quotient) > 0.002) {
          throw new Error(`LQ mismatch for ${cell.key}/${row.track}`);
        }
      }
    }
    if (!(await body()).includes("不适用")) throw new Error("LQ not-applicable state not rendered");

    // deselect one company: the page must clear stale results and show the prompt
    const medtronicToggle = await page.$('[data-testid="compare-toggle"][data-company-key="medtronic"]');
    await medtronicToggle.click();
    await page.waitForTimeout(900);
    const afterDeselect = await body();
    if (!afterDeselect.includes("选择无效") && !afterDeselect.includes("尚未选择")) {
      throw new Error("invalid selection does not show validation prompt");
    }
    const staleChart = await page.$('[data-testid="compare-chart"]');
    if (staleChart && (await staleChart.isVisible())) {
      throw new Error("stale compare chart still visible after deselecting below 2 companies");
    }
    const medtronicAgain = await page.$('[data-testid="compare-toggle"][data-company-key="medtronic"]');
    if (medtronicAgain) await medtronicAgain.click();
    await page.waitForTimeout(900);

    const screenshot = await shot(page, "s2-compare");
    record("Scenario 2 比较竞争对手 (Medtronic vs Philips)", true, `warnings=${warnings}; invalid-selection cleared`, screenshot);
  } catch (error) {
    record("Scenario 2 比较竞争对手 (Medtronic vs Philips)", false, String(error.message));
  }

  // ---------------------------------------------------------------- scenario 3
  try {
    await goto("#/radar/respiratory");
    await page.waitForSelector('[data-testid="track-detail"]', { timeout: 30000 });
    await page.waitForTimeout(1200);
    const text = await body();
    if (!text.includes("呼吸")) throw new Error("respiratory track detail missing");
    const chart = await page.$('[data-testid="track-chart"]');
    if (!chart) throw new Error("track chart missing");
    const svgBox = await chart.boundingBox();
    if (!svgBox || svgBox.width < 100) throw new Error("track chart not visible");
    const track = await page.evaluate(async () => {
      const response = await fetch("/api/radar/respiratory?years=10");
      return response.json();
    });
    if (!text.includes(String(track.totals.recent))) {
      throw new Error(`track page does not show complete-window total ${track.totals.recent}`);
    }
    if (!text.includes("未归属") && !text.includes("未归属企业")) {
      throw new Error("track page does not disclose unattributed records");
    }
    if (!text.includes("首次") || !text.includes("原始批准")) {
      throw new Error("track page does not use the first-original-approval wording");
    }
    const screenshot = await shot(page, "s3-radar-respiratory");
    record("Scenario 3 分析技术趋势 (Respiratory)", true, `complete=${track.totals.recent} windowAll=${track.totals.recent_all}`, screenshot);
  } catch (error) {
    record("Scenario 3 分析技术趋势 (Respiratory)", false, String(error.message));
  }

  // ---------------------------------------------------------------- scenario 4
  try {
    await goto("#/companies/medtronic");
    await page.waitForSelector('[data-testid="company-claims"]', { timeout: 30000 });
    await page.waitForTimeout(800);
    const button = await page.$('[data-testid="claim-evidence-btn"]');
    if (!button) throw new Error("claim evidence button missing");
    await button.click();
    await page.waitForSelector('[data-testid="claim-evidence-panel"]', { timeout: 30000 });
    await page.waitForTimeout(1200);
    const rows = await page.$$eval('[data-testid="event-row"]', (nodes) => nodes.length);
    if (rows < 1) throw new Error("claim evidence panel has no event rows");
    await page.click('[data-testid="event-row"]');
    await page.waitForSelector('[data-testid="event-detail"]', { timeout: 30000 });
    await page.waitForTimeout(800);
    const text = await body();
    if (!text.includes("来源") && !text.includes("原始")) throw new Error("event detail missing provenance");
    if (!text.includes("PMA") && !text.includes("510(k)")) throw new Error("event detail missing approval type");
    if (!text.includes("类型") && !text.includes("补充") && !text.includes("原始")) {
      throw new Error("event detail missing approval subtype disclosure");
    }
    const screenshot = await shot(page, "s4-evidence-trace");
    record("Scenario 4 追溯研究结论 → 原始证据", true, `events=${rows}`, screenshot);
  } catch (error) {
    record("Scenario 4 追溯研究结论 → 原始证据", false, String(error.message));
  }

  // ---------------------------------------------------------------- scenario 5
  try {
    await goto("#/analyst");
    await page.waitForSelector('[data-testid="analyst-input"]', { timeout: 20000 });
    await page.fill('[data-testid="analyst-input"]', "过去五年，迈瑞的超声产品发生了什么变化？");
    await page.click('[data-testid="analyst-submit"]');
    await page.waitForSelector('[data-testid="analyst-answer"]', { timeout: 45000 });
    await page.waitForTimeout(2000);
    const text = await body();
    if (text.includes("尚未接入") || text.includes("not_ready")) throw new Error("analyst engine not ready");
    if (!text.includes("迈瑞")) throw new Error("analyst answer does not mention 迈瑞");
    if (!text.includes("超声")) throw new Error("analyst answer does not mention 超声");
    const evidence = await page.$$eval('[data-testid="analyst-evidence"]', (nodes) => nodes.length);
    if (evidence < 1) throw new Error("analyst answer has no traceable evidence");
    const screenshot = await shot(page, "s5-analyst");
    record("Scenario 5 使用研究助手", true, `evidence=${evidence}`, screenshot);
  } catch (error) {
    record("Scenario 5 使用研究助手", false, String(error.message));
  }

  // ---------------------------------------------------------------- scenario 6
  // Live Observatory: the page must state *both* times separately, prove itself
  // against the API, and never present a polled source as realtime. It also runs
  // green with an empty/missing ledger, where the honest empty state is required.
  try {
    await goto("#/observatory");
    await page.waitForSelector('[data-testid="page-observatory"]', { timeout: 30000 });
    await page.waitForTimeout(1200);
    const navLink = await page.$('[data-testid="nav-observatory"]');
    if (!navLink) throw new Error("observatory nav link missing");
    const summary = await page.evaluate(async () => {
      const response = await fetch("/api/observatory/summary");
      return response.json();
    });
    let text = await body();
    const noLedger = Boolean(await page.$('[data-testid="observatory-no-ledger"]'));
    if (!summary.ledger || typeof summary.ledger.exists !== "boolean") {
      throw new Error("summary.ledger.exists missing from API");
    }
    if (!summary.ledger.exists || noLedger || summary.ledger.observations === 0) {
      if (!/尚无观察记录|观察账本|没有观察记录|尚未|没有数据源同步状态/.test(text)) {
        throw new Error("empty-state copy missing when no observations exist");
      }
      const screenshot = await shot(page, "s6-observatory-empty");
      record("Scenario 6 实时观察站 (空账本诚实状态)", true,
        `ledger.exists=${summary.ledger.exists} observations=${summary.ledger.observations}`, screenshot);
    } else {
      if (!text.includes("事件发生于")) throw new Error("event_at statement missing");
      if (!text.includes("首次观察")) throw new Error("first_seen_at statement missing");
      if (!text.includes("轮询")) throw new Error("polled cadence copy missing");
      if (/实时推送/.test(text) && !/不是实时推送|非实时|不做实时|不代表实时/.test(text)) {
        throw new Error("page claims realtime push");
      }
      for (const label of ["新增", "修订", "不再提供", "采集失败"]) {
        if (!text.includes(label)) throw new Error(`change-state chip ${label} missing`);
      }
      const rows = await page.$$('[data-testid="observatory-row"]');
      if (rows.length < 1) throw new Error("no observation rows rendered");
      const events = await page.evaluate(async () => {
        const response = await fetch("/api/observatory/events?window=24h&limit=1");
        return response.json();
      });
      if (typeof events.total !== "number" || events.total < 1) {
        throw new Error("events API returned no rows for a populated ledger");
      }
      if (!Array.isArray(events.items) || !events.items[0].first_seen_at || !events.items[0].observed_at) {
        throw new Error("event item is missing real observation timestamps");
      }
      if (!events.items[0].time_basis || !("measurable" in events.items[0].time_basis)) {
        throw new Error("event item is missing the measurable-lag contract");
      }
      const sources = await page.evaluate(async () => {
        const response = await fetch("/api/observatory/sources");
        return response.json();
      });
      if (!Array.isArray(sources.sources) || sources.sources.length < 1) {
        throw new Error("sources API returned no sync state");
      }
      if (!text.includes("数据源同步状态")) throw new Error("sync-status panel missing");
      for (const source of sources.sources) {
        const node = await page.$(`[data-testid="observatory-source-${source.source}"]`);
        if (!node) throw new Error(`sync panel for source ${source.source} missing`);
        if (!source.last_success_at) throw new Error(`source ${source.source} has no last_success_at`);
      }
      const sec = sources.sources.find((item) => item.source === "sec_edgar");
      if (sec && Array.isArray(sec.entity_coverage) && sec.entity_coverage.length) {
        const statuses = sec.entity_coverage.map((row) => String(row.status));
        if (!statuses.some((status) => status === "COVERED")) {
          throw new Error("SEC coverage does not report any verified COVERED issuer");
        }
        const nonCovered = sec.entity_coverage.filter((row) => row.status !== "COVERED");
        if (nonCovered.length && !text.includes("NOT_CURRENT_REGISTRANT") && !text.includes("未覆盖")) {
          throw new Error("non-covered SEC issuers are not disclosed on the page");
        }
      }
      // (h) health panel states one of the five honest words and is backed by the API
      const healthNode = await page.$('[data-testid="observatory-health-overall"]');
      if (!healthNode) throw new Error("Observatory Health panel is missing");
      const healthText = (await healthNode.innerText()).trim();
      const allowed = ["OPERATIONAL", "DEGRADED", "PAUSED", "NOT_DEPLOYED", "VALIDATION_IN_PROGRESS"];
      if (!allowed.some((word) => healthText.includes(word))) {
        throw new Error(`health badge shows an unknown state: ${healthText}`);
      }
      const healthApi = await page.evaluate(async () => {
        const response = await fetch("/api/observatory/health");
        return response.json();
      });
      if (!healthApi.overall || !allowed.includes(healthApi.overall)) {
        throw new Error("health API overall is missing or unknown");
      }
      if (!Array.isArray(healthApi.checks) || healthApi.checks.length < 5) {
        throw new Error("health API does not expose its checks");
      }
      // (i) acquisition phase is visible and filterable (initial vs incremental)
      if (!text.includes("初次发现") && !text.includes("增量发现")) {
        throw new Error("acquisition-phase distinction is missing from the page");
      }
      const phaseChips = await page.$$('[data-testid^="observatory-phase-"]');
      if (phaseChips.length < 2) {
        throw new Error("acquisition-phase filter chips are missing");
      }
      const phaseSummary = summary.phases || {};
      const phaseCounts = phaseSummary.counts || {};
      if (typeof phaseCounts.INITIAL_DISCOVERY !== "number"
          && typeof phaseCounts.INCREMENTAL_DISCOVERY !== "number") {
        throw new Error("summary.phases counts are missing");
      }
      await rows[0].click();
      await page.waitForTimeout(900);
      text = await body();
      if (!text.includes("版本") && !text.includes("version")) {
        throw new Error("drawer does not show the payload version chain");
      }
      const screenshot = await shot(page, "s6-observatory");
      record("Scenario 6 实时观察站", true,
        `observations=${summary.ledger.observations} sources=${sources.sources.length} ` +
        `rows=${rows.length} events_24h=${events.total} health=${healthApi.overall} ` +
        `phases=${JSON.stringify(phaseCounts)}`, screenshot);
    }
  } catch (error) {
    record("Scenario 6 实时观察站", false, String(error.message));
  }

  // -------------------------------------------------- responsive check (mobile)
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await goto("#/companies/mindray");
    await page.waitForSelector('[data-testid="company-profile"]', { timeout: 20000 });
    await page.waitForTimeout(600);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const screenshot = await shot(page, "s6-mobile-company");
    record("Mobile 390px company page", overflow <= 4, `horizontal overflow=${overflow}px`, screenshot);
  } catch (error) {
    record("Mobile 390px company page", false, String(error.message));
  }

  // -------------------------------------------------- responsive check (observatory)
  try {
    await goto("#/observatory");
    await page.waitForSelector('[data-testid="page-observatory"]', { timeout: 30000 });
    await page.waitForTimeout(1000);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const screenshot = await shot(page, "s6-mobile-observatory");
    record("Mobile 390px Live Observatory", overflow <= 4, `horizontal overflow=${overflow}px`, screenshot);
  } catch (error) {
    record("Mobile 390px Live Observatory", false, String(error.message));
  }

  const report = {
    base: BASE,
    ran_at: new Date().toISOString(),
    results,
    console_errors: [...new Set(consoleErrors)].slice(0, 20),
    passed: results.filter((row) => row.ok).length,
    failed: results.filter((row) => !row.ok).length,
  };
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(path.join(OUT_DIR, "report.json"), JSON.stringify(report, null, 2));
  await browser.close();
  console.log(`\n${report.passed} passed, ${report.failed} failed; report: ${path.join(OUT_DIR, "report.json")}`);
  if (report.console_errors.length) console.log("console errors:", report.console_errors.slice(0, 5));
  process.exit(report.failed === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error("E2E crashed:", error);
  process.exit(2);
});
