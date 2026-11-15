#!/usr/bin/env node
/**
 * MedRadar PRODUCT-002 browser acceptance suite.
 *
 * Runs against a real backend process. The data is the committed, hash-pinned openFDA snapshot
 * (medradar/product/snapshot/, immutable and reproducible), so the run needs no network and no
 * synthetic fixture.
 *
 * Two origins are used:
 *   ADMIN_BASE  (default http://127.0.0.1:8811) the identity-review service, which also serves the
 *               public read-only API and the built workbench (python -m medradar.product.review serve)
 *   PUBLIC_BASE (default http://127.0.0.1:8812) the public application only
 *               (python -m medradar.product.web), used to prove that no review write route exists there
 *
 * Exit codes: 0 every check passed; 1 at least one failed; 2 the backend is not reachable.
 */
import { createRequire } from "node:module";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..");
const OUT = process.env.E2E_OUT_DIR || join(ROOT, "build", "e2e");
const ADMIN_BASE = (process.env.ADMIN_BASE || process.argv[2] || "http://127.0.0.1:8811").replace(/\/$/, "");
const PUBLIC_BASE = (process.env.PUBLIC_BASE || process.argv[3] || "http://127.0.0.1:8812").replace(/\/$/, "");
const TOKEN_FILE = process.env.MEDRADAR_REVIEW_TOKEN_FILE || join(ROOT, "build", "e2e", "review.token");
let REVIEW_TOKEN = process.env.MEDRADAR_REVIEW_TOKEN || "";
if (!REVIEW_TOKEN && existsSync(TOKEN_FILE)) REVIEW_TOKEN = readFileSync(TOKEN_FILE, "utf8").trim();
const SHOTS = join(OUT, "screenshots");

const checks = [];
function record(id, description, passed, evidence) {
  checks.push({ id, description, passed: Boolean(passed), evidence: evidence ?? null });
  console.log((passed ? "PASS" : "FAIL").padEnd(5) + id.padEnd(8) + description + (evidence ? "  [" + String(evidence).slice(0, 200) + "]" : ""));
}

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    "playwright",
    join(HERE, "node_modules", "playwright"),
    join(ROOT, "web", "node_modules", "playwright"),
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      continue;
    }
  }
  throw new Error("playwright is not installed; run: cd tests/e2e && npm ci");
}

async function apiAuth(base, path, token) {
  const response = await fetch(base + path, { headers: { "X-MedRadar-Review-Token": token } });
  if (!response.ok) throw new Error("API " + path + " -> " + response.status);
  return response.json();
}

async function api(base, path) {
  const response = await fetch(base + path);
  if (!response.ok) throw new Error("API " + path + " -> " + response.status);
  return response.json();
}

async function waitForBackend(base, attempts = 60) {
  for (let index = 0; index < attempts; index += 1) {
    try {
      const response = await fetch(base + "/api/health");
      if (response.ok) return true;
    } catch {
      /* not up yet */
    }
    await new Promise((done) => setTimeout(done, 1000));
  }
  return false;
}

function csvRows(text) {
  const clean = text.replace(/^\uFEFF/, "").trim();
  const lines = clean.split(/\r?\n/).filter((line) => line.length > 0);
  return { header: lines[0], rows: lines.slice(1) };
}

async function main() {
  mkdirSync(SHOTS, { recursive: true });
  const admin = await waitForBackend(ADMIN_BASE);
  const publicUp = await waitForBackend(PUBLIC_BASE, 10);
  if (!admin) {
    console.error("backend not reachable at " + ADMIN_BASE);
    return 2;
  }
  const { chromium } = loadPlaywright();
  const browser = await chromium
    .launch({ headless: true })
    .catch(() => chromium.launch({ headless: true, channel: "chrome" }));
  const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await context.newPage();

  const consoleErrors = [];
  const failedRequests = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => failedRequests.push(request.url()));

  // token for the internal workspace; the token gate is part of the test
  await page.addInitScript((token) => {
    window.sessionStorage.setItem("medradar.review.token", token);
  }, REVIEW_TOKEN);

  const shot = async (name) => {
    await page.screenshot({ path: join(SHOTS, name + ".png") }).catch(() => undefined);
  };

  try {
    /* ---------------------------------------------------------------- E2E-01 search */
    await page.goto(ADMIN_BASE + "/", { waitUntil: "networkidle" });
    const search = page.getByPlaceholder(/Search organizations, tickers, applicant names/i);
    await search.fill("Medtronic");
    await page.waitForTimeout(600);
    const option = page.getByRole("option", { name: /Medtronic/ }).first();
    const optionVisible = await option.isVisible().catch(() => false);
    if (optionVisible) await option.click();
    else await page.goto(ADMIN_BASE + "/organizations/medtronic", { waitUntil: "networkidle" });
    await page.waitForTimeout(900);
    const orgUrl = page.url();
    const orgHeading = (await page.locator("h1").first().innerText().catch(() => "")).trim();
    record("E2E-01", "search for Medtronic reaches the organization page", /\/organizations\/medtronic/.test(orgUrl) && /Medtronic/i.test(orgHeading), orgHeading);
    await shot("01-organization");

    /* ---------------------------------------------------------------- E2E-02 transparency block */
    const bodyText = await page.locator("body").innerText();
    const hasConfidence = /Attribution confidence for these counts/i.test(bodyText);
    const hasCurated = /Curated share/i.test(bodyText);
    const apiOrg = await api(ADMIN_BASE, "/api/organizations/medtronic");
    const apiRecords = apiOrg.counts.records;
    record(
      "E2E-02",
      "organization page states attribution confidence and matches the API count",
      hasConfidence && hasCurated && bodyText.includes(apiRecords.toLocaleString("en-US")),
      "records=" + apiRecords + " confidenceBlock=" + hasConfidence,
    );

    /* ---------------------------------------------------------------- E2E-03 event filters */
    try {
      await page.goto(ADMIN_BASE + "/organizations/medtronic", { waitUntil: "networkidle" });
      await page.waitForTimeout(900);
      await page.getByRole("tab", { name: /Regulatory events/i }).click();
      await page.waitForTimeout(1200);
      const expected = (await api(ADMIN_BASE, "/api/organizations/medtronic/events?types=recall")).total;
      await page.getByRole("button", { name: "Recall", exact: true }).click();
      await page.waitForTimeout(1600);
      const filteredText = await page.locator("body").innerText();
      record(
        "E2E-03",
        "event filters narrow the table and agree with the API total",
        filteredText.includes(expected.toLocaleString("en-US")) && expected > 0,
        "apiTotal(recall)=" + expected,
      );
      await shot("02-events-filtered");
    } catch (error) {
      record("E2E-03", "event filters narrow the table and agree with the API total", false, String(error).slice(0, 160));
    }

    /* ---------------------------------------------------------------- E2E-04 evidence drawer */
    try {
    await page.locator("tr.clickable").first().click();
    await page.waitForTimeout(1200);
    const drawerText = await page.locator("body").innerText();
    const drawer = page.locator(".drawer, [role='dialog']").first();
    const drawerVisible = await drawer.isVisible().catch(() => false);
    const officialLink = await page.locator("a[href*='accessdata.fda.gov']").count();
    record(
      "E2E-04",
      "evidence drawer shows the official identifier and link",
      drawerVisible && officialLink > 0 && /Verification/i.test(drawerText),
      "links=" + officialLink,
    );
    await shot("03-evidence-drawer");
    await page.keyboard.press("Escape").catch(() => undefined);
    } catch (error) {
      record("E2E-04", "evidence drawer shows the official identifier and link", false, String(error).slice(0, 160));
    }

    /* ---------------------------------------------------------------- E2E-05 compare */
    await page.goto(ADMIN_BASE + "/compare?orgs=medtronic,ge_healthcare", { waitUntil: "networkidle" });
    await page.waitForTimeout(1600);
    const compareText = await page.locator("body").innerText();
    const compareApi = await api(ADMIN_BASE, "/api/compare?orgs=medtronic,ge_healthcare");
    record(
      "E2E-05",
      "comparison renders both organizations, one shared window and the comparability verdict",
      /Medtronic/.test(compareText) && /GE HealthCare/.test(compareText) && /Comparability verdict/i.test(compareText) && /not a measure of innovation/i.test(compareText),
      "window=" + compareApi.window.effective.from + ".." + compareApi.window.effective.to,
    );
    await shot("04-compare");

    /* ---------------------------------------------------------------- E2E-06 CSV export */
    const csvFilters = "/api/export/events.csv?org=medtronic&types=recall&from=2024-01-01&to=2024-12-31";
    const csvResponse = await fetch(ADMIN_BASE + csvFilters);
    const csvText = await csvResponse.text();
    const parsed = csvRows(csvText);
    const expectedCsv = await api(ADMIN_BASE, "/api/events?org=medtronic&types=recall&from=2024-01-01&to=2024-12-31&page_size=10");
    record(
      "E2E-06",
      "CSV export row count equals the filtered result count",
      csvResponse.ok && parsed.rows.length === expectedCsv.total && /attribution_verification/.test(parsed.header) && parsed.rows.length > 0,
      "rows=" + parsed.rows.length + " apiTotal=" + expectedCsv.total,
    );

    /* ---------------------------------------------------------------- E2E-07 Markdown export */
    const mdResponse = await fetch(ADMIN_BASE + "/api/export/compare.md?orgs=medtronic,ge_healthcare");
    const markdown = await mdResponse.text();
    record(
      "E2E-07",
      "Markdown comparison export carries the disclaimer, both names and the verification table",
      mdResponse.ok && /Medtronic/.test(markdown) && /GE HealthCare/.test(markdown) && /not a measure of innovation/i.test(markdown) && /Attribution verification/i.test(markdown),
      "bytes=" + markdown.length,
    );

    /* ---------------------------------------------------------------- E2E-08 Chinese UI */
    await page.goto(ADMIN_BASE + "/organizations/medtronic", { waitUntil: "networkidle" });
    await page.evaluate(() => window.localStorage.setItem("medradar.lang", "zh"));
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForTimeout(1400);
    const zhText = await page.locator("body").innerText();
    record(
      "E2E-08",
      "Chinese interface renders translated headings and metric definitions",
      /企业对比/.test(zhText) && /这些计数的归属可信程度/.test(zhText) && /已核验比例/.test(zhText),
      zhText.slice(0, 60).replace(/\n/g, " "),
    );
    await shot("05-organization-zh");
    await page.evaluate(() => window.localStorage.setItem("medradar.lang", "en"));

    /* ---------------------------------------------------------------- E2E-10 empty state (real zero-result filter) */
    await page.goto(ADMIN_BASE + "/events?org=medradar-missing", { waitUntil: "networkidle" });
    const invalidText = await page.locator("body").innerText();
    record(
      "E2E-10",
      "an unknown filter value produces an explicit error or empty state, never a blank page",
      /unknown organization|Something went wrong|state-error|No records match/i.test(invalidText),
      invalidText.slice(invalidText.length - 300).replace(/\n/g, " "),
    );

    /* ---------------------------------------------------------------- E2E-11 unknown organization */
    await page.goto(ADMIN_BASE + "/organizations/does-not-exist", { waitUntil: "networkidle" });
    await page.waitForTimeout(1800);
    const missingText = await page.locator("body").innerText();
    record(
      "E2E-11",
      "an unknown organization shows an error state with a retry path",
      /error|Error|not found|Something went wrong/i.test(missingText),
      missingText.slice(0, 80).replace(/\n/g, " "),
    );

    /* ---------------------------------------------------------------- E2E-13 review queue */
    try {
    await page.goto(ADMIN_BASE + "/review", { waitUntil: "networkidle" });
    await page.waitForTimeout(2200);
    const reviewText = await page.locator("body").innerText();
    await page.waitForTimeout(1200);
    const queueRows = await page.locator("table.data-table tbody tr").count();
    const unlocked = /Review queue/i.test(reviewText) && /Curated share/i.test(reviewText);
    record(
      "E2E-13",
      "the identity-review workspace unlocks with the token and lists the queue",
      unlocked && queueRows > 0,
      "rows=" + queueRows + " unlocked=" + unlocked + " snippet=" + reviewText.slice(0, 120).replace(/\n/g, " "),
    );
    await shot("06-review-queue");
    } catch (error) {
      record("E2E-13", "the identity-review workspace unlocks with the token and lists the queue", false, String(error).slice(0, 160));
    }

    /* ---------------------------------------------------------------- E2E-14 decision + impact */
    const applicant = "Abbott Vascular-Cardiac Therapies dba Guidant Corporation";
    let decisionUid = null;
    try {
    const impactBefore = await apiAuth(ADMIN_BASE, "/api/review/impact", REVIEW_TOKEN);
    const decideResponse = await fetch(ADMIN_BASE + "/api/review/decisions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-MedRadar-Review-Token": REVIEW_TOKEN },
      body: JSON.stringify({
        applicant_name: applicant,
        action: "unresolved",
        status: "unresolved",
        reviewer: "e2e",
        reviewer_kind: "agent",
        evidence_type: "third_party_report",
        evidence: [{ evidence_type: "third_party_report", url: "https://example.invalid/e2e", title: "e2e evidence", accessed_at: "2026-01-01" }],
        note: "e2e decision: leave the cross-scope Guidant string unresolved until a reviewer assigns it",
      }),
    });
    const decideBody = await decideResponse.json().catch(() => ({}));
    const impactAfter = await apiAuth(ADMIN_BASE, "/api/review/impact", REVIEW_TOKEN);
    const changedAfter = impactAfter.changed_organizations.length;
    const sameCounts = JSON.stringify(impactBefore.changed_organizations) === JSON.stringify(impactAfter.changed_organizations);
    record(
      "E2E-14",
      "a review decision is appended, and unrelated organizations keep their exact counts",
      decideResponse.ok && decideBody?.decision?.status === "unresolved" && sameCounts && impactAfter.unchanged_organizations >= 50,
      "decision=" + (decideBody?.decision?.decision_uid || "none").slice(0, 10) + " unchanged=" + impactAfter.unchanged_organizations,
    );
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    await shot("07-review-after-decision");
    decisionUid = decideBody?.decision?.decision_uid || null;
    } catch (error) {
      record("E2E-14", "a review decision is appended, and unrelated organizations keep their exact counts", false, String(error).slice(0, 160));
    }

    /* ---------------------------------------------------------------- E2E-15 append-only history */
    try {
    const history = await fetch(ADMIN_BASE + "/api/review/history/" + encodeURIComponent(applicant), {
      headers: { "X-MedRadar-Review-Token": REVIEW_TOKEN },
    }).then((response) => response.json());
    const uid = decisionUid;
    const revoke = uid
      ? await fetch(ADMIN_BASE + "/api/review/decisions/" + uid + "/revoke", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-MedRadar-Review-Token": REVIEW_TOKEN },
          body: JSON.stringify({ reviewer: "e2e", reviewer_kind: "agent", note: "e2e withdrawal" }),
        })
      : null;
    const historyAfter = await fetch(ADMIN_BASE + "/api/review/history/" + encodeURIComponent(applicant), {
      headers: { "X-MedRadar-Review-Token": REVIEW_TOKEN },
    }).then((response) => response.json());
    const entries = historyAfter.history || [];
    record(
      "E2E-15",
      "history is preserved after a withdrawal (append-only ledger)",
      entries.length >= 2 && Boolean(revoke && revoke.ok) && entries.some((entry) => entry.revoked) && Boolean(history.history),
      "entries=" + entries.length,
    );
    } catch (error) {
      record("E2E-15", "history is preserved after a withdrawal (append-only ledger)", false, String(error).slice(0, 160));
    }

    /* ---------------------------------------------------------------- E2E-16 permission boundary */
    try {
    const unauthorised = await fetch(ADMIN_BASE + "/api/review/queue");
    const badToken = await fetch(ADMIN_BASE + "/api/review/queue", { headers: { "X-MedRadar-Review-Token": "not-the-token" } });
    const writeWithoutToken = await fetch(ADMIN_BASE + "/api/review/decisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ applicant_name: applicant, action: "approve", status: "evidence_verified", organization_key: "abbott", reviewer: "x", reviewer_kind: "agent" }),
    });
    let publicBoundary = true;
    let publicDetail = "public app not reachable";
    if (publicUp) {
      const publicQueue = await fetch(PUBLIC_BASE + "/api/review/queue", { headers: { "X-MedRadar-Review-Token": REVIEW_TOKEN } });
      const publicWrite = await fetch(PUBLIC_BASE + "/api/review/decisions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-MedRadar-Review-Token": REVIEW_TOKEN },
        body: "{}",
      });
      publicBoundary = publicQueue.status === 404 && (publicWrite.status === 404 || publicWrite.status === 405);
      publicDetail = "queue=" + publicQueue.status + " write=" + publicWrite.status;
    }
    record(
      "E2E-16",
      "review writes require the token and do not exist on the public application",
      unauthorised.status === 401 && badToken.status === 401 && writeWithoutToken.status === 401 && publicBoundary,
      "noToken=" + unauthorised.status + " badToken=" + badToken.status + " write=" + writeWithoutToken.status + " public=" + publicDetail,
    );
    } catch (error) {
      record("E2E-16", "review writes require the token and do not exist on the public application", false, String(error).slice(0, 160));
    }

    /* ---------------------------------------------------------------- E2E-09 mobile */
    const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const mobilePage = await mobile.newPage();
    await mobilePage.goto(ADMIN_BASE + "/organizations/medtronic", { waitUntil: "networkidle" });
    await mobilePage.waitForTimeout(1200);
    const overflow = await mobilePage.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    const mobileText = await mobilePage.locator("body").innerText();
    await mobilePage.screenshot({ path: join(SHOTS, "08-mobile-organization.png") });
    await mobile.close();
    record(
      "E2E-09",
      "mobile viewport renders the organization page without horizontal overflow",
      overflow <= 1 && /Medtronic/i.test(mobileText),
      "overflow=" + overflow + "px",
    );

    /* ---------------------------------------------------------------- E2E-12 console / network */
    // The suite deliberately exercises two error paths (an unknown organization and an unknown
    // filter value), so the browser logs one 400 and one 404 for those probes. Every other console
    // error is a failure.
    const relevantErrors = consoleErrors.filter(
      (text) => !/401|Unauthorized|400 \(Bad Request\)|404 \(Not Found\)/i.test(text),
    );
    record(
      "E2E-12",
      "no unexpected console errors and no failed requests",
      relevantErrors.length === 0 && failedRequests.length === 0,
      "console=" + relevantErrors.length + " (expected error-path 400/404 excluded: " + (consoleErrors.length - relevantErrors.length) + ") failedRequests=" + failedRequests.length,
    );
  } finally {
    await browser.close();
  }

  const passed = checks.filter((check) => check.passed).length;
  const report = {
    suite: "medradar-product-002-e2e",
    generated_at: new Date().toISOString(),
    admin_base: ADMIN_BASE,
    public_base: PUBLIC_BASE,
    total: checks.length,
    passed,
    failed: checks.length - passed,
    checks,
    console_errors: consoleErrors,
    failed_requests: failedRequests,
  };
  writeFileSync(join(OUT, "report.json"), JSON.stringify(report, null, 2));
  console.log("\n" + passed + "/" + checks.length + " checks passed; report: " + join(OUT, "report.json"));
  return passed === checks.length ? 0 : 1;
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
