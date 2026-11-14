#!/usr/bin/env node
/**
 * MedRadar PRODUCT-001 end-to-end acceptance walkthrough.
 *
 * This is the executable form of the acceptance criteria in docs/product/ACCEPTANCE.md. It
 * drives a real browser through the analyst workflow against a running workbench:
 *
 *   search -> organization page -> regulatory events -> evidence drawer -> filters
 *   -> compare two organizations -> export CSV -> verify export equals the screen
 *
 * Run the product first:
 *   python -m medradar web --port 8787
 * Then:
 *   node scripts/product_acceptance.mjs [baseUrl]
 *
 * Playwright is not a product dependency. The script resolves it from (in order)
 * PLAYWRIGHT_MODULE, a local node_modules, or the environment used to build this release.
 * Exit code 0 = every check passed; 1 = at least one failed (details in the JSON report).
 */
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const BASE = (process.argv[2] || "http://127.0.0.1:8787").replace(/\/$/, "");
const SHOT_DIR = join(ROOT, "docs", "product", "screenshots");

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    "playwright",
    join(ROOT, "web", "node_modules", "playwright"),
    "D:/DEPPSKK/browser-tools/node_modules/playwright",
    "/usr/lib/node_modules/playwright",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      continue;
    }
  }
  throw new Error("playwright not found; set PLAYWRIGHT_MODULE=/path/to/playwright");
}

const checks = [];
function record(id, description, passed, evidence) {
  checks.push({ id, description, passed, evidence });
  const mark = passed ? "PASS" : "FAIL";
  console.log(mark.padEnd(5) + id.padEnd(5) + description + (evidence ? "  [" + evidence + "]" : ""));
}

async function api(path) {
  const response = await fetch(BASE + path);
  if (!response.ok) throw new Error("API " + path + " -> " + response.status);
  return response.json();
}

function csvRows(text) {
  const clean = text.replace(/^\uFEFF/, "").trim();
  const lines = clean.split(/\r?\n/);
  return { header: lines[0], rows: lines.slice(1) };
}

async function main() {
  const { chromium } = loadPlaywright();
  mkdirSync(SHOT_DIR, { recursive: true });
  const browser = await chromium.launch({ channel: "chrome", headless: true }).catch(() =>
    chromium.launch({ headless: true }),
  );
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  const failedRequests = [];
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText ?? "";
    // Aborted in-flight requests are normal when the user navigates away from a page.
    if (reason.includes("ERR_ABORTED")) return;
    failedRequests.push(request.url() + " (" + reason + ")");
  });

  const shots = {};
  const shoot = async (name) => {
    const file = join(SHOT_DIR, name + ".png");
    await page.screenshot({ path: file, fullPage: false });
    shots[name] = file;
  };

  try {
    // A1 - overview loads with navigation
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    await page.waitForSelector("h1");
    const h1 = (await page.locator("h1").first().textContent()) || "";
    const navCount = await page.locator("header nav a").count();
    record("A1", "Homepage loads with product title and 5 navigation items", h1.length > 10 && navCount >= 5, h1 + ", nav=" + navCount);
    await shoot("01-overview");

    // A2 - coverage numbers come from the API and are non-trivial
    const meta = await api("/api/meta");
    const tiles = await page.locator(".metric-value").allTextContents();
    const tileText = tiles.join(" | ");
    record(
      "A2",
      "Overview shows tracked organizations and record totals from the live API",
      tileText.includes(String(meta.coverage.tracked_organizations)) && meta.coverage.attributed_records > 1000,
      "orgs=" + meta.coverage.tracked_organizations + ", attributed=" + meta.coverage.attributed_records,
    );

    // A3 - search an organization through the real search box
    await page.fill("input#global-search", "medtronic");
    await page.waitForSelector(".search-pop .search-item", { timeout: 10000 });
    const firstResult = (await page.locator(".search-pop .search-item .title").first().textContent()) || "";
    await page.locator(".search-pop .search-item").first().click();
    await page.waitForSelector("h1");
    const orgH1 = (await page.locator("h1").first().textContent()) || "";
    record("A3", "Search by company name opens the organization page", firstResult.includes("Medtronic") && orgH1.includes("Medtronic"), "result=" + firstResult + ", h1=" + orgH1);
    await shoot("02-organization");

    // A4 - organization counts equal the API payload
    const profile = await api("/api/organizations/medtronic");
    const orgTiles = await page.locator(".metric-value").allTextContents();
    const orgTileText = orgTiles.join(" | ").replace(/,/g, "");
    record(
      "A4",
      "Organization page counts match the API measurement layer",
      orgTileText.includes(String(profile.counts.records)),
      "records=" + profile.counts.records,
    );

    // A5 - regulatory event browser for this organization
    await page.goto(BASE + "/organizations/medtronic?tab=events", { waitUntil: "networkidle" });
    await page.waitForSelector("table.data tbody tr", { timeout: 15000 });
    const rowCount = await page.locator("table.data tbody tr").count();
    const firstOfficialId = (await page.locator("table.data tbody tr td.mono").first().textContent())?.trim() || "";
    const orgEvents = await api("/api/organizations/medtronic/events?page_size=10");
    record(
      "A5",
      "Organization event tab lists real records with official FDA identifiers",
      rowCount > 0 && firstOfficialId.length > 3 && orgEvents.total > 0,
      "rows=" + rowCount + ", first=" + firstOfficialId + ", total=" + orgEvents.total,
    );
    await shoot("03-organization-events");

    // A6 - evidence drawer opens from a row and shows the official record and time semantics
    await page.locator("button.evidence-link").first().click();
    await page.waitForSelector(".drawer", { timeout: 10000 });
    await page.waitForFunction(() => {
      const drawer = document.querySelector(".drawer");
      return drawer ? drawer.textContent.includes("Official ID") : false;
    }, { timeout: 15000 });
    const drawerText = (await page.locator(".drawer").innerText()) || "";
    const officialLink = await page.locator(".drawer a[href*='accessdata.fda.gov']").first().getAttribute("href");
    record(
      "A6",
      "Evidence drawer shows the official record URL and the separate time fields",
      drawerText.includes("Event date") && drawerText.includes("Published by source") && drawerText.includes("First observed by MedRadar") && Boolean(officialLink),
      officialLink || "no official link",
    );
    record(
      "A6b",
      "510(k)/PMA records state that the source publishes no publication time",
      drawerText.includes("Not published by this source"),
      "publication-time rule visible",
    );
    await shoot("04-evidence-drawer");
    await page.keyboard.press("Escape");

    // A7 - filters change the result set consistently with the API
    await page.goto(BASE + "/events?types=510k&org=medtronic&from=2020-01-01", { waitUntil: "networkidle" });
    await page.waitForSelector("table.data tbody tr", { timeout: 15000 });
    const filteredTotal = await api("/api/events?types=510k&org=medtronic&from=2020-01-01&page_size=10");
    const summary = (await page.locator(".filter-bar .filter-summary .count").first().textContent()) || "";
    record(
      "A7",
      "Filter changes are reflected in the URL and the rendered result count",
      page.url().includes("types=510k") && summary.replace(/,/g, "").trim() === String(filteredTotal.total),
      "total=" + filteredTotal.total + ", url=" + page.url().replace(BASE, ""),
    );
    await shoot("05-events-filtered");

    // A8 - CSV export equals exactly the filtered screen set
    const eventsPage = await api("/api/events?types=510k&org=medtronic&from=2020-01-01&page_size=10");
    const downloadPromise = page.waitForEvent("download", { timeout: 15000 });
    await page.locator("a.btn", { hasText: "CSV" }).first().click();
    const download = await downloadPromise;
    const downloadPath = join(SHOT_DIR, "..", "..", "..", "_logs", "acceptance-export.csv");
    await download.saveAs(downloadPath);
    const { readFileSync } = await import("node:fs");
    const csv = csvRows(readFileSync(downloadPath, "utf8"));
    const rowCountCsv = csv.rows.filter((row) => row.trim().length).length;
    record(
      "A8",
      "CSV export contains exactly the filtered records and an official URL column",
      rowCountCsv === eventsPage.total && csv.header.includes("official_url") && csv.header.includes("attribution_review"),
      "csv_rows=" + rowCountCsv + ", expected=" + eventsPage.total,
    );

    // A9 - compare two organizations with warnings above the data
    await page.goto(BASE + "/compare?orgs=medtronic,ge_healthcare&years=5", { waitUntil: "networkidle" });
    await page.waitForSelector(".banner", { timeout: 15000 });
    const bannerCount = await page.locator(".banner").count();
    const compare = await api("/api/compare?orgs=medtronic,ge_healthcare");
    const compareText = (await page.locator("main").innerText()) || "";
    record(
      "A9",
      "Comparison shows both organizations, warnings and the records-are-not-innovation disclaimer",
      bannerCount >= 1 && compareText.includes("Medtronic") && compareText.includes("GE HealthCare") && compareText.includes("Records are not innovation"),
      "warnings=" + compare.warnings.length + ", banners=" + bannerCount,
    );
    await shoot("06-compare");

    // A10 - Markdown comparison report downloads
    const mdDownloadPromise = page.waitForEvent("download", { timeout: 15000 });
    await page.locator("a.btn", { hasText: "Export report" }).first().click();
    const mdDownload = await mdDownloadPromise;
    const mdPath = join(SHOT_DIR, "..", "..", "..", "_logs", "acceptance-compare.md");
    await mdDownload.saveAs(mdPath);
    const mdText = readFileSync(mdPath, "utf8");
    record(
      "A10",
      "Markdown comparison report contains the window, warnings, source links and counting rule",
      mdText.includes("Counting rule") && mdText.includes("accessdata.fda.gov") && mdText.includes("Warnings"),
      "chars=" + mdText.length,
    );

    // A11 - sources and coverage page states limits
    await page.goto(BASE + "/sources", { waitUntil: "networkidle" });
    await page.waitForSelector("h1");
    const sourcesText = (await page.locator("main").innerText()) || "";
    const coverage = await api("/api/coverage");
    record(
      "A11",
      "Sources page shows the snapshot manifest, attribution audit and out-of-scope list",
      sourcesText.includes(coverage.manifest.id) && sourcesText.includes("Not covered in this release") && sourcesText.includes("Collection audit"),
      "snapshot=" + coverage.manifest.id,
    );
    await shoot("07-sources");

    // A12 - mobile viewport has no horizontal overflow and a reachable navigation
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(BASE + "/organizations/medtronic", { waitUntil: "networkidle" });
    await page.waitForSelector("h1");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const menuVisible = await page.locator(".nav-toggle").isVisible();
    record("A12", "Mobile layout fits the viewport and exposes the navigation menu", overflow <= 1 && menuVisible, "overflow=" + overflow + "px, menu=" + menuVisible);
    await shoot("08-mobile-organization");
    await page.setViewportSize({ width: 1440, height: 900 });

    // A13 - language toggle switches the interface
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    await page.locator(".lang-toggle").click();
    await page.waitForTimeout(400);
    const zhNav = (await page.locator("header nav").innerText()) || "";
    const zhTitle = (await page.locator("h1").first().textContent()) || "";
    record("A13", "Interface language toggles to Chinese", zhNav.includes("总览") && /[\u4e00-\u9fff]/.test(zhTitle), zhNav.replace(/\n/g, "/"));
    await shoot("09-overview-zh");
    await page.locator(".lang-toggle").click();

    // A14 - no browser console errors or failed requests during the walkthrough
    record(
      "A14",
      "No console errors or failed network requests during the walkthrough",
      consoleErrors.length === 0 && failedRequests.length === 0,
      "console=" + consoleErrors.length + ", failedRequests=" + failedRequests.length,
    );
  } catch (error) {
    record("FATAL", "Acceptance walkthrough completed without an exception", false, String(error && error.message ? error.message : error));
  } finally {
    const report = {
      product: "MedRadar PRODUCT-001",
      baseUrl: BASE,
      ranAt: new Date().toISOString(),
      viewport: "1440x900 desktop, 390x844 mobile",
      browser: "Google Chrome via Playwright",
      checks,
      passed: checks.filter((check) => check.passed).length,
      failed: checks.filter((check) => !check.passed).length,
      screenshots: shots,
    };
    const outDir = join(ROOT, "docs", "product");
    writeFileSync(join(outDir, "acceptance-report.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    await browser.close();
    console.log("");
    console.log("checks=" + checks.length + " passed=" + report.passed + " failed=" + report.failed);
    console.log("report: docs/product/acceptance-report.json");
    process.exit(report.failed === 0 ? 0 : 1);
  }
}

main();
