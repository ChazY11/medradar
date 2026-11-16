#!/usr/bin/env node
/**
 * PRODUCT-004 real-browser acceptance.
 *
 * Drives Chromium against a running workbench and performs the three research scenarios plus the
 * "no new changes" and regression checks. It records every check, every download, the operation
 * count and a screenshot per scenario. Exit code 0 = all checks passed.
 *
 *   python -m medradar.product.web --port 8790
 *   node scripts/product_004_acceptance.mjs http://127.0.0.1:8790
 *
 * Playwright is not a product dependency: it is resolved from PLAYWRIGHT_MODULE, a local
 * node_modules, or the environment used to run previous acceptance suites.
 */
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const BASE = (process.argv[2] || "http://127.0.0.1:8790").replace(/\/$/, "");
const OUT = join(ROOT, "docs", "product", "product_004", "screenshots");
const EXPORTS = join(ROOT, "docs", "product", "product_004", "exports");
mkdirSync(OUT, { recursive: true });
mkdirSync(EXPORTS, { recursive: true });

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    "playwright",
    join(ROOT, "web", "node_modules", "playwright"),
    join(ROOT, "tests", "e2e", "node_modules", "playwright"),
    "D:/DEPPSKK/browser-tools/node_modules/playwright",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      // try the next location
    }
  }
  throw new Error("Playwright not found. Set PLAYWRIGHT_MODULE to the module path.");
}

const { chromium } = loadPlaywright();
const report = {
  product: "PRODUCT-004",
  started_at: new Date().toISOString(),
  base_url: BASE,
  scenarios: [],
  regression: [],
  failures: [],
  console_errors: [],
  request_failures: [],
};

function relPath(path) {
  return relative(ROOT, path).split(String.fromCharCode(92)).join("/");
}

function check(scenario, name, condition, detail) {
  const row = { check: name, ok: Boolean(condition), detail: detail ?? null };
  scenario.checks.push(row);
  if (!condition) report.failures.push(`${scenario.id}: ${name}${detail ? " — " + detail : ""}`);
  return Boolean(condition);
}

async function text(page) {
  return page.locator("body").innerText();
}

async function shot(page, name, fullPage = false) {
  const path = join(OUT, name);
  await page.screenshot({ path, fullPage, animations: "disabled", timeout: 120000 });
  return relPath(path);
}

async function download(page, selector, filename) {
  const [item] = await Promise.all([
    page.waitForEvent("download", { timeout: 60000 }),
    page.locator(selector).first().click(),
  ]);
  const path = join(EXPORTS, filename);
  await item.saveAs(path);
  return { path, relative: relPath(path), suggested: item.suggestedFilename() };
}

async function newPage(context) {
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  page.on("console", (message) => {
    if (message.type() === "error") report.console_errors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    // Export links are downloads: Chromium aborts the navigation once the download starts.
    if (request.url().includes("/api/export/brief")) return;
    report.request_failures.push(`${request.url()} — ${request.failure()?.errorText ?? "failed"}`);
  });
  return page;
}

async function scenarioCompany(context) {
  const s = { id: "A-company", title: "Company research: Medtronic, last five complete years", checks: [], operations: 0 };
  report.scenarios.push(s);
  const page = await newPage(context);

  // Step 1: define the question in the structured form (not a chat box).
  await page.goto(BASE + "/brief", { waitUntil: "networkidle" });
  s.operations += 1;
  await page.locator('input[list="brief-organizations"]').first().fill("medtronic");
  s.operations += 1;
  await page.getByRole("button", { name: /Build intelligence brief|生成情报简报/ }).click();
  s.operations += 1;
  await page.waitForURL(/\/brief\?mode=company&org=medtronic/, { timeout: 60000 });
  await page.waitForSelector(".brief-finding", { timeout: 60000 });
  s.operations += 1;

  const body = await text(page);
  check(s, "URL records the full research scope", /org=medtronic/.test(page.url()) && /years=5/.test(page.url()), page.url());
  check(s, "Brief states the research question", /What does Medtronic/.test(body), body.slice(0, 160));
  check(s, "Window is 2021-01-01 to 2025-12-31", body.includes("2021-01-01 to 2025-12-31"));
  check(s, "Window record count is 3,426", /3,426/.test(body));
  check(s, "Findings are rendered", (await page.locator(".brief-finding").count()) >= 3, `${await page.locator(".brief-finding").count()} findings`);
  check(s, "Pathway concentration finding is present", body.includes("pathway_concentration"));
  check(s, "Technology table uses official classification names", body.includes("Implantable Cardioverter Defibrillator (Non-Crt)"));
  check(s, "PMA family section is present", body.includes("PMA families in the window") && body.includes("P010031"));
  check(s, "Attribution caution is present", body.includes("provisional_attribution"));

  const shot1 = await shot(page, "01-company-brief.png");
  s.screenshots = [shot1];

  // Step 2: reproduce a finding's supporting records in the event browser.
  await page.locator(".brief-finding a.btn").first().click();
  await page.waitForURL(/\/events\?/, { timeout: 30000 });
  await page.waitForSelector("table.data tbody tr", { timeout: 30000 });
  s.operations += 1;
  const eventsBody = await text(page);
  check(s, "Finding drill-down opens the event browser on the same pathway", page.url().includes("types=pma_supplement"), page.url());
  check(s, "Drill-down shows PMA supplement records", /PMA supplement/.test(eventsBody) && /P\d{6}/.test(eventsBody));
  const shot2 = await shot(page, "02-company-finding-records.png");
  s.screenshots.push(shot2);
  await page.goBack({ waitUntil: "networkidle" });

  // Step 3: verify one record's official evidence and its four time fields.
  const evidenceButton = page.locator('.card:has-text("Recent activity") button:has-text("Evidence")').first();
  await evidenceButton.click();
  await page.waitForSelector(".drawer", { timeout: 30000 });
  // The drawer fetches the record; assert the loaded content, not the loading skeleton.
  await page.waitForFunction(
    () => {
      const text = document.querySelector(".drawer")?.innerText || "";
      return /official id/i.test(text) && /event date/i.test(text);
    },
    null,
    { timeout: 30000 },
  );
  s.operations += 1;
  const drawer = await page.locator(".drawer").innerText();
  check(s, "Evidence drawer shows the official identifier", /official id|官方标识/i.test(drawer));
  check(s, "Evidence drawer keeps the four time fields separate", /event date/i.test(drawer) && /first observed by medradar/i.test(drawer));
  check(
    s,
    "Evidence drawer links the official FDA record",
    (await page.locator('.drawer a[href*="accessdata.fda.gov"]').count()) > 0,
  );
  const shot3 = await shot(page, "03-company-evidence-drawer.png");
  s.screenshots.push(shot3);
  await page.locator(".drawer .btn").first().click();
  await page.waitForTimeout(300);

  // Step 4: take the deliverable away.
  const md = await download(page, 'a[href*="/api/export/brief.md"]', "medtronic-company-brief-en.md");
  s.operations += 1;
  const mdBody = readFileSync(md.path, "utf8");
  check(s, "Company brief Markdown downloads", mdBody.length > 5000, `${mdBody.length} chars`);
  check(s, "Brief Markdown contains the findings section", mdBody.includes("Evidence-backed findings"));
  check(s, "Brief Markdown contains the counting rule and limitations", mdBody.includes("Counting rule") && mdBody.includes("Questions this cannot answer"));
  check(s, "Brief Markdown numbers match the page", mdBody.includes("3,426") || mdBody.includes("3426"));
  const csv = await download(page, 'a[href*="/api/export/brief-evidence.csv"]', "medtronic-evidence-appendix.csv");
  s.operations += 1;
  const csvBody = readFileSync(csv.path, "utf8");
  const csvLines = csvBody.trim().split("\n");
  check(s, "Evidence appendix downloads with a header and window rows", csvLines.length > 3000, `${csvLines.length} lines`);
  check(s, "Evidence appendix carries official URLs", csvBody.includes("https://www.accessdata.fda.gov/"));
  s.downloads = [md.relative, csv.relative];

  // The print layout is the browser-PDF deliverable: chrome and the form must disappear.
  await page.emulateMedia({ media: "print" });
  check(s, "Print stylesheet hides the app chrome", (await page.locator(".app-bar").evaluate((el) => getComputedStyle(el).display)) === "none");
  check(s, "Print stylesheet hides the question form", (await page.locator(".brief-form").evaluate((el) => getComputedStyle(el).display)) === "none");
  s.screenshots.push(await shot(page, "15-print-layout.png"));
  await page.emulateMedia({ media: "screen" });

  await page.goto(BASE + "/brief?mode=company&org=medtronic&years=5", { waitUntil: "networkidle" });
  s.operations += 1;

  // Step 5: the changes section must not invent updates.
  const changesText = await text(page);
  check(s, "Change ledger absence is stated, not masked", /no continuous-pipeline change ledger|未配置持续同步的变化台账/.test(changesText));
  check(s, "No fabricated change count is shown", !/1 new record|new today/i.test(changesText));

  await page.close();
  return s;
}

async function scenarioCompare(context) {
  const s = { id: "B-compare", title: "Competitor comparison: GE HealthCare vs Philips", checks: [], operations: 0 };
  report.scenarios.push(s);
  const page = await newPage(context);
  await page.goto(BASE + "/brief?mode=compare&orgs=ge_healthcare,philips&years=5", { waitUntil: "networkidle" });
  s.operations += 1;
  await page.waitForSelector(".brief-metrics", { timeout: 60000 });
  const body = await text(page);
  check(s, "Comparison brief states the shared window", body.includes("2021-01-01 to 2025-12-31"));
  check(s, "GE HealthCare records are 493", /493/.test(body));
  check(s, "Philips records are 963", /963/.test(body));
  check(s, "Source coverage is assessed explicitly", /Coverage symmetric|coverage is symmetric|来源覆盖/.test(body), body.match(/coverage[^\n]{0,80}/i)?.[0]);
  check(s, "Verification asymmetry is stated", body.includes("verification_asymmetry") && /100\.0%/.test(body) && /71\.0%/.test(body));
  check(s, "Product-code overlap finding is present", body.includes("product_family_overlap"));
  const shot1 = await shot(page, "04-compare-brief.png");
  s.screenshots = [shot1];

  // Explain a difference down to records.
  const row = page.locator('.brief-metrics tbody tr:has-text("Recall")').first();
  await row.getByRole("button", { name: /Explain|解释差异/ }).click();
  await page.waitForSelector(".drawer", { timeout: 30000 });
  await page.waitForFunction(
    () => /definition/i.test(document.querySelector(".drawer")?.innerText || ""),
    null,
    { timeout: 30000 },
  );
  s.operations += 1;
  const drawer = await page.locator(".drawer").innerText();
  check(s, "Explain drawer gives the definition", /definition|指标定义/i.test(drawer));
  check(s, "Explain drawer gives the denominator", /denominator|分母/i.test(drawer));
  check(s, "Explain drawer lists records for both sides", /GE HealthCare/.test(drawer) && /Philips/.test(drawer));
  check(
    s,
    "Explain drawer links the identical event-browser filter",
    (await page.locator('.drawer a[href*="/events?"]').count()) > 0,
  );
  const shot2 = await shot(page, "05-compare-explain-difference.png");
  s.screenshots.push(shot2);
  await page.locator(".drawer .btn").first().click();
  await page.waitForTimeout(300);

  const md = await download(page, 'a[href*="/api/export/brief.md"]', "ge-healthcare-vs-philips-brief-en.md");
  s.operations += 1;
  const mdBody = readFileSync(md.path, "utf8");
  check(s, "Competitor brief Markdown downloads", mdBody.length > 3000, `${mdBody.length} chars`);
  check(s, "Competitor brief contains comparability and limitations", mdBody.includes("Comparability") && mdBody.includes("Questions this cannot answer"));
  check(s, "Competitor brief contains the explainable measures", mdBody.includes("Comparable measures"));
  const csv = await download(page, 'a[href*="/api/export/brief-evidence.csv"]', "compare-evidence-appendix.csv");
  s.operations += 1;
  check(s, "Comparison evidence appendix has both sides", readFileSync(csv.path, "utf8").includes("side:philips"));
  s.downloads = [md.relative, csv.relative];

  await page.close();
  return s;
}

async function scenarioDevice(context) {
  const s = { id: "C-device", title: "Device investigation: PMA P980016", checks: [], operations: 0 };
  report.scenarios.push(s);
  const page = await newPage(context);
  await page.goto(BASE + "/brief?mode=device&device=P980016", { waitUntil: "networkidle" });
  s.operations += 1;
  await page.waitForSelector(".brief-finding", { timeout: 60000 });
  const body = await text(page);
  check(s, "Device brief identifies the official PMA number", body.includes("P980016"));
  check(s, "Supplement history is 934", /934/.test(body));
  check(s, "Original approval and supplements are separated", /Official application history/.test(body));
  check(s, "No confirmed recall link is stated honestly", body.includes("no_confirmed_recall_link") && /not evidence that no recall occurred|不等于没有发生召回/.test(body));
  check(s, "Candidate relations are not presented as established", /candidate|候选/i.test(body));
  const shot1 = await shot(page, "06-device-brief.png");
  s.screenshots = [shot1];

  // Open the official application record link and confirm it points at FDA.
  const href = await page.locator('.card:has-text("Device identity") a[href*="accessdata.fda.gov"]').first().getAttribute("href");
  check(s, "Official FDA application link is present", Boolean(href && href.includes("accessdata.fda.gov")), href);
  s.operations += 1;

  const md = await download(page, 'a[href*="/api/export/brief.md"]', "device-p980016-brief-en.md");
  s.operations += 1;
  const mdBody = readFileSync(md.path, "utf8");
  check(s, "Device brief Markdown downloads", mdBody.length > 3000, `${mdBody.length} chars`);
  check(s, "Device brief states what it cannot conclude", mdBody.includes("cannot answer") || mdBody.includes("not evidence that no recall"));
  const csv = await download(page, 'a[href*="/api/export/brief-evidence.csv"]', "device-evidence-appendix.csv");
  s.operations += 1;
  const csvBody = readFileSync(csv.path, "utf8");
  check(s, "Device evidence appendix lists the application and supplements", csvBody.includes("device_history") && csvBody.split("\n").length > 900, `${csvBody.split("\n").length} lines`);
  s.downloads = [md.relative, csv.relative];

  await page.close();
  return s;
}

async function scenarioNoChanges(context) {
  const s = { id: "D-no-changes", title: "No new changes: the brief must not invent an update", checks: [], operations: 0 };
  report.scenarios.push(s);
  const page = await newPage(context);
  await page.goto(BASE + "/brief?mode=company&org=medtronic&years=5", { waitUntil: "networkidle" });
  s.operations += 1;
  await page.waitForSelector(".brief-finding", { timeout: 60000 });
  const body = await text(page);
  check(s, "Changes section states that no ledger is configured", body.includes("not_configured") || body.includes("no continuous-pipeline change ledger"));
  check(s, "No event is described as happening today", !/today/.test(body));
  const api = await page.evaluate(async (base) => {
    const [changes, status] = await Promise.all([
      fetch(base + "/api/changes").then((response) => response.json()),
      fetch(base + "/api/data-status").then((response) => response.json()),
    ]);
    return { changes, status };
  }, BASE);
  check(s, "Change feed has no fabricated items", api.changes.total === 0 && api.changes.items.length === 0, JSON.stringify(api.changes.total));
  check(s, "Data status reports the pipeline as not configured", api.status.configured === false && api.status.state === "not_configured", api.status.state);
  await page.locator('.card:has-text("Changes since")').first().scrollIntoViewIfNeeded();
  const shot1 = await shot(page, "07-no-new-changes.png");
  s.screenshots = [shot1];
  await page.close();
  return s;
}

async function regression(context) {
  const s = { id: "R-regression", title: "Existing pages, mobile, Chinese and new product-code filter", checks: [], operations: 0 };
  report.regression.push(s);
  const page = await newPage(context);

  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  s.operations += 1;
  const home = await text(page);
  check(s, "Home starts from a research task, not the QA strip", /Start a research task/.test(home));
  check(s, "Home no longer claims Product 001", !/Product 001/.test(home));
  check(s, "Whole-snapshot year chart is fed by the snapshot aggregation", await page.locator(".chart svg rect").count() > 20, `${await page.locator(".chart svg rect").count()} bars`);
  const homeShot = await shot(page, "10-home.png");
  s.screenshots = [homeShot];

  await page.goto(BASE + "/organizations/medtronic", { waitUntil: "networkidle" });
  s.operations += 1;
  const org = await text(page);
  check(s, "Organization page links to the intelligence brief", Boolean(await page.locator('a:has-text("Open intelligence brief")').count()));
  check(s, "Organization page shows official product-code families", org.includes("Implantable Cardioverter Defibrillator (Non-Crt)"));
  await page.locator('.card:has-text("Technology areas")').first().scrollIntoViewIfNeeded();
  s.screenshots.push(await shot(page, "11-organization-product-families.png"));

  await page.goto(BASE + "/compare?orgs=ge_healthcare,philips", { waitUntil: "networkidle" });
  s.operations += 1;
  check(s, "Compare page links to the comparison brief", Boolean(await page.locator('a:has-text("Open comparison brief")').count()));
  s.screenshots.push(await shot(page, "12-compare-page.png"));

  await page.goto(BASE + "/events?org=medtronic&product_code=NIK&from=2021-01-01&to=2025-12-31", { waitUntil: "networkidle" });
  s.operations += 1;
  const events = await text(page);
  check(s, "Product-code filter is applied and reproducible", /257/.test(events) && /NIK/.test(events), events.match(/257 records/)?.[0]);
  s.screenshots.push(await shot(page, "13-events-product-code.png"));

  // Chinese interface, desktop.
  await page.evaluate(() => localStorage.setItem("medradar.lang", "zh"));
  await page.goto(BASE + "/brief?mode=company&org=medtronic&years=5", { waitUntil: "networkidle" });
  s.operations += 1;
  await page.waitForSelector(".brief-finding", { timeout: 60000 });
  const zh = await text(page);
  check(s, "Chinese brief renders the analysis in Chinese", /情报简报/.test(zh) && /有证据支持的发现/.test(zh));
  const shotZh = await shot(page, "08-company-brief-zh.png");
  s.screenshots.push(shotZh);

  // Mobile: the language control must remain reachable.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  s.operations += 1;
  await page.getByRole("button", { name: /Menu|菜单/ }).click();
  s.operations += 1;
  check(s, "Mobile navigation exposes the language control", Boolean(await page.locator(".nav-lang").count()));
  check(s, "Mobile page has no horizontal overflow", await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1));
  const shotMobile = await shot(page, "09-mobile-nav-zh.png");
  s.screenshots.push(shotMobile);
  await page.goto(BASE + "/brief?mode=company&org=medtronic&years=5", { waitUntil: "networkidle" });
  await page.waitForSelector(".brief-finding", { timeout: 60000 });
  check(
    s,
    "Mobile brief has no horizontal overflow",
    await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1),
  );
  s.screenshots.push(await shot(page, "14-mobile-company-brief-zh.png"));
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.close();
  return s;
}

const CHROMIUM = process.env.CHROMIUM_EXECUTABLE || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const browser = await chromium.launch({ headless: true, executablePath: CHROMIUM });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  locale: "en-US",
  timezoneId: "Asia/Shanghai",
  acceptDownloads: true,
});
context.setDefaultTimeout(60000);

try {
  await scenarioCompany(context);
  await scenarioCompare(context);
  await scenarioDevice(context);
  await scenarioNoChanges(context);
  await regression(context);
} catch (error) {
  report.failures.push(`runner: ${error && error.stack ? error.stack : String(error)}`);
} finally {
  await context.close();
  await browser.close();
}

report.finished_at = new Date().toISOString();
report.ok = report.failures.length === 0;
writeFileSync(join(ROOT, "docs", "product", "product_004", "acceptance-report.json"), JSON.stringify(report, null, 2));
for (const scenario of [...report.scenarios, ...report.regression]) {
  const passed = scenario.checks.filter((item) => item.ok).length;
  console.log(`${scenario.id}: ${passed}/${scenario.checks.length} checks, ${scenario.operations} operations`);
  for (const item of scenario.checks.filter((row) => !row.ok)) console.log(`  FAIL ${item.check}${item.detail ? " — " + item.detail : ""}`);
}
console.log(report.ok ? "ACCEPTANCE PASSED" : `ACCEPTANCE FAILED: ${report.failures.length} failure(s)`);
process.exit(report.ok ? 0 : 1);
