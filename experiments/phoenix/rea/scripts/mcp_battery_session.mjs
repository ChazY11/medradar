// PHOENIX-001 REA validation: provider-gated session battery over MCP.
//
// Opens the native PE fixture and the zip bundle fixture, then calls the
// session-scoped tools that need a native analysis provider. On this host no
// Ghidra/Hopper/IDA provider is configured, so these calls should return typed
// capability unavailability rather than crash. Also exercises the
// artifact-graph provider against a real archive.
//
// Writes: evidence/mcp_battery_session.json

import { createRequire } from "node:module";
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIX = join(HERE, "..", "fixtures");
const OUT = join(HERE, "..", "evidence");
mkdirSync(OUT, { recursive: true });

const REQ = createRequire("D:/DEPPSKK/.rea/package.json");
const { Client } = REQ("@modelcontextprotocol/client");
const { StdioClientTransport } = REQ("@modelcontextprotocol/client/stdio");

const REA_ROOT = "D:\\DEPPSKK\\.rea";
const SERVER = join(REA_ROOT, "node_modules", "rea-agents", "scripts", "rea.mjs");
const p = (rel) => join(FIX, rel).replaceAll("\\", "/");

const NATIVE = p("build/sample-native.exe");
const BUNDLE = p("build/sample-bundle.zip");

const STEPS = [
  { id: "open-native", tool: "open_binary", args: { path: NATIVE } },
  { id: "overview-native", tool: "binary_overview", args: {} },
  { id: "segments-native", tool: "list_segments", args: {} },
  { id: "strings-native", tool: "list_strings", args: {} },
  { id: "session-after-open", tool: "binary_session", args: {} },
  { id: "close-native", tool: "close_binary", args: {} },
  { id: "open-bundle", tool: "open_binary", args: { path: BUNDLE } },
  { id: "inspect-bundle", tool: "inspect_artifact", args: { detail: "summary" } },
  { id: "close-bundle", tool: "close_binary", args: {} },
];

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [SERVER, "mcp"],
  cwd: REA_ROOT,
  stderr: "pipe",
});
const client = new Client({ name: "phoenix-001-session-battery", version: "0.1.0" });
let stderrText = "";
const capStderr = (s) => {
  if (!s) return;
  s.setEncoding("utf8");
  s.on("data", (c) => {
    if (stderrText.length < 40000) stderrText += c;
  });
};
if (transport.stderr) capStderr(transport.stderr);
else if (transport._process && transport._process.stderr) capStderr(transport._process.stderr);

const tConn = performance.now();
await client.connect(transport);
const connectMs = +(performance.now() - tConn).toFixed(1);

const results = [];
for (const step of STEPS) {
  const t0 = performance.now();
  let rec = { id: step.id, tool: step.tool, args: step.args };
  try {
    const res = await client.callTool({ name: step.tool, arguments: step.args });
    const text = (res.content ?? [])
      .filter((c) => c && c.type === "text")
      .map((c) => c.text)
      .join("\n");
    let parsed = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
    let errCode = null;
    if (parsed && parsed.error) errCode = parsed.error.code ?? null;
    rec = {
      ...rec,
      ok: res.isError !== true,
      isError: res.isError === true,
      ms: +(performance.now() - t0).toFixed(1),
      content_chars: text.length,
      typed_error_code: errCode,
      text_excerpt: text.slice(0, 2500),
    };
  } catch (error) {
    rec = {
      ...rec,
      ok: false,
      hard_error: true,
      ms: +(performance.now() - t0).toFixed(1),
      error: String(error && error.message ? error.message : error),
    };
  }
  results.push(rec);
  process.stderr.write(`[session] ${step.id} -> ${rec.ok ? "ok" : "fail"} ${rec.ms}ms ${rec.typed_error_code ?? ""}\n`);
}

const out = {
  captured_at: new Date().toISOString(),
  connect_ms: connectMs,
  results,
  stderr_bytes_observed: stderrText.length,
  stderr_excerpt: stderrText.slice(0, 4000),
};
writeFileSync(join(OUT, "mcp_battery_session.json"), JSON.stringify(out, null, 2), "utf8");
await client.close();
process.stdout.write(
  JSON.stringify(
    {
      connect_ms: connectMs,
      per_call: results.map((r) => ({
        id: r.id,
        tool: r.tool,
        ok: r.ok,
        ms: r.ms,
        typed_error_code: r.typed_error_code ?? null,
        chars: r.content_chars ?? 0,
      })),
      out: join(OUT, "mcp_battery_session.json"),
    },
    null,
    2,
  ) + "\n",
);
process.exit(0);
