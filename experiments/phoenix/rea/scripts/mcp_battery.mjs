// PHOENIX-001 REA validation: static-analysis battery over MCP.
//
// Connects to REA's MCP server over stdio and calls a fixed, harmless battery of
// tools against fixtures created under ../fixtures. For every call it records
// latency, ok/isError, the typed error when it fails, and a bounded excerpt of
// the returned content so output quality can be judged.
//
// Writes: evidence/mcp_battery.json
// Prints: one JSON summary object.

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

const PY = p("sample.py");
const NATIVE = p("build/sample-native.exe");
const MANAGED = p("build/sample-managed.exe");
const SQLITE = p("sample.sqlite");

const BATTERY = [
  {
    id: "session-identity",
    tool: "binary_session",
    args: {},
    expect: "success",
    why: "target-free session/identity probe",
  },
  {
    id: "layout-native-pe",
    tool: "inspect_binary_layout",
    args: { path: NATIVE },
    expect: "success",
    why: "unsigned x86-64 PE built for this program",
  },
  {
    id: "layout-managed-pe",
    tool: "inspect_binary_layout",
    args: { path: MANAGED },
    expect: "success",
    why: "PE/CLI image built with in-box csc",
  },
  {
    id: "layout-python-source",
    tool: "inspect_binary_layout",
    args: { path: PY },
    expect: "failure",
    why: "negative control: plain-text source is not a binary",
  },
  {
    id: "pe-resources",
    tool: "inspect_pe_resources",
    args: { path: MANAGED },
    expect: "success",
    why: "bounded PE resource tree",
  },
  {
    id: "managed-artifact",
    tool: "inspect_managed_artifact",
    args: { path: MANAGED },
    expect: "success",
    why: "PE/CLI identity without loading the assembly",
  },
  {
    id: "managed-members",
    tool: "inspect_managed_members",
    args: { path: MANAGED, type_names: ["ReaProbe"] },
    expect: "success",
    why: "metadata members of the fixture type",
  },
  {
    id: "managed-native-boundaries",
    tool: "inspect_managed_native_boundaries",
    args: { path: MANAGED },
    expect: "success",
    why: "P/Invoke boundary inventory",
  },
  {
    id: "sqlite-schema",
    tool: "inspect_sqlite_database",
    args: { path: SQLITE, table: "signals" },
    expect: "success",
    why: "schema + rows from a fixture SQLite snapshot",
  },
  {
    id: "rust-auditable",
    tool: "inspect_rust_binary",
    args: { path: NATIVE },
    expect: "typed-unavailable",
    why: "negative control: plain rustc build has no cargo-auditable .dep-v0",
  },
  {
    id: "go-buildinfo",
    tool: "inspect_go_binary",
    args: { path: NATIVE },
    expect: "typed-unavailable",
    why: "negative control: not a Go binary",
  },
  {
    id: "open-native",
    tool: "open_binary",
    args: { path: NATIVE },
    expect: "failure-without-provider",
    why: "requires a native analysis provider (none installed)",
  },
  {
    id: "open-python",
    tool: "open_binary",
    args: { path: PY },
    expect: "failure",
    why: "negative control: unsupported format",
  },
  {
    id: "javascript-application",
    tool: "analyze_javascript_application",
    args: { input_path: PY },
    expect: "failure",
    why: "negative control: not an ASAR/JS application",
  },
];

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [SERVER, "mcp"],
  cwd: REA_ROOT,
  stderr: "pipe",
});
const client = new Client({ name: "phoenix-001-battery", version: "0.1.0" });

let stderrText = "";
const capStderr = (s) => {
  if (!s) return;
  s.setEncoding("utf8");
  s.on("data", (c) => {
    if (stderrText.length < 40000) stderrText += c;
  });
};
const transportAny = transport;
if (transportAny.stderr) capStderr(transportAny.stderr);
else if (transportAny._process && transportAny._process.stderr) capStderr(transportAny._process.stderr);

const tConn = performance.now();
await client.connect(transport);
const connectMs = +(performance.now() - tConn).toFixed(1);

const shape = (value, depth = 0) => {
  if (value === null || value === undefined) return value ?? null;
  if (Array.isArray(value)) return { array: value.length, first: depth < 2 ? shape(value[0], depth + 1) : null };
  if (typeof value === "object") {
    const keys = Object.keys(value);
    const out = { keys: keys.slice(0, 24) };
    if (depth < 2) {
      for (const k of keys.slice(0, 8)) out[k] = shape(value[k], depth + 1);
    }
    return out;
  }
  return value;
};

const results = [];
for (const item of BATTERY) {
  const t0 = performance.now();
  let record = {
    id: item.id,
    tool: item.tool,
    args: item.args,
    expectation: item.expect,
    why: item.why,
  };
  try {
    const res = await client.callTool({ name: item.tool, arguments: item.args });
    const ms = +(performance.now() - t0).toFixed(1);
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
    record = {
      ...record,
      ok: res.isError !== true,
      isError: res.isError === true,
      ms,
      content_chars: text.length,
      text_excerpt: text.slice(0, 3000),
      parsed_shape: parsed ? shape(parsed) : null,
      structured_keys: res.structuredContent ? Object.keys(res.structuredContent) : [],
    };
  } catch (error) {
    record = {
      ...record,
      ok: false,
      hard_error: true,
      ms: +(performance.now() - t0).toFixed(1),
      error: String(error && error.message ? error.message : error),
      error_code: error && error.code ? String(error.code) : null,
    };
  }
  results.push(record);
  process.stderr.write(`[battery] ${item.id} -> ${record.ok ? "ok" : "fail"} ${record.ms}ms\n`);
}

const succeeded = results.filter((r) => r.ok).length;
const out = {
  captured_at: new Date().toISOString(),
  server: { command: process.execPath, args: [SERVER, "mcp"], cwd: REA_ROOT },
  connect_ms: connectMs,
  totals: { calls: results.length, ok: succeeded, failed: results.length - succeeded },
  results,
  stderr_bytes_observed: stderrText.length,
  stderr_excerpt: stderrText.slice(0, 4000),
};
writeFileSync(join(OUT, "mcp_battery.json"), JSON.stringify(out, null, 2), "utf8");
await client.close();

process.stdout.write(
  JSON.stringify(
    {
      connect_ms: connectMs,
      totals: out.totals,
      per_call: results.map((r) => ({ id: r.id, tool: r.tool, ok: r.ok, ms: r.ms, err: r.error ?? null })),
      out: join(OUT, "mcp_battery.json"),
    },
    null,
    2,
  ) + "\n",
);
process.exit(0);
