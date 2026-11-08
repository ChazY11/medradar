// PHOENIX-001 REA validation: MCP client inventory probe.
//
// Connects to REA's MCP server exactly the way an MCP host would
// (newline-delimited JSON-RPC over stdio) using the official
// @modelcontextprotocol/client SDK that REA itself ships, then records the
// negotiated identity, the full tool list (name, description, input-schema
// keys) and the prompt list.
//
// Writes: evidence/mcp_tools.json  (full machine-readable inventory)
// Prints: one JSON object of summary facts.

import { createRequire } from "node:module";
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "evidence");
mkdirSync(OUT, { recursive: true });

// Resolve the SDK from the deployment tree (D:\DEPPSKK\.rea).
const REQ = createRequire("D:/DEPPSKK/.rea/package.json");
const { Client } = REQ("@modelcontextprotocol/client");
const { StdioClientTransport } = REQ("@modelcontextprotocol/client/stdio");

const REA_ROOT = "D:\\DEPPSKK\\.rea";
const SERVER = join(REA_ROOT, "node_modules", "rea-agents", "scripts", "rea.mjs");

const now = () => performance.now();
const iso = () => new Date().toISOString();

const result = {
  captured_at: iso(),
  server_command: { command: process.execPath, args: [SERVER, "mcp"], cwd: REA_ROOT },
  client: { name: "phoenix-001-rea-validation", version: "0.1.0" },
  steps: [],
};

const step = async (name, fn) => {
  const t0 = now();
  try {
    const value = await fn();
    result.steps.push({ name, ok: true, ms: +(now() - t0).toFixed(1) });
    return value;
  } catch (error) {
    result.steps.push({
      name,
      ok: false,
      ms: +(now() - t0).toFixed(1),
      error: String(error && error.message ? error.message : error),
      code: error && error.code ? String(error.code) : null,
    });
    return undefined;
  }
};

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [SERVER, "mcp"],
  cwd: REA_ROOT,
  stderr: "pipe",
});

let stderrText = "";
const capStderr = (stream) => {
  if (!stream) return;
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    if (stderrText.length < 40000) stderrText += chunk;
  });
};

const client = new Client({ name: result.client.name, version: result.client.version });

result.connect = {};
const tConn = now();
await client.connect(transport);
result.connect.ms = +(now() - tConn).toFixed(1);
result.connect.protocolVersion = client.getNegotiatedProtocolVersion
  ? client.getNegotiatedProtocolVersion()
  : null;
result.connect.serverVersion = client.getServerVersion ? client.getServerVersion() : null;
result.connect.serverCapabilities = client.getServerCapabilities
  ? client.getServerCapabilities()
  : null;

// StdioClientTransport spawns the child internally; take stderr if exposed.
const anyTransport = transport;
if (anyTransport.stderr) capStderr(anyTransport.stderr);
else if (anyTransport._process && anyTransport._process.stderr) capStderr(anyTransport._process.stderr);

const toolsResult = await step("tools/list", () => client.listTools());
const promptsResult = await step("prompts/list", () => client.listPrompts());

const tools = (toolsResult && toolsResult.tools ? toolsResult.tools : []).map((tool) => ({
  name: tool.name,
  title: tool.title ?? null,
  description: tool.description ?? "",
  inputSchemaKeys: tool.inputSchema && tool.inputSchema.properties
    ? Object.keys(tool.inputSchema.properties)
    : [],
  requiredKeys: tool.inputSchema && Array.isArray(tool.inputSchema.required)
    ? tool.inputSchema.required
    : [],
  annotations: tool.annotations ?? null,
  outputSchemaKeys: tool.outputSchema && tool.outputSchema.properties
    ? Object.keys(tool.outputSchema.properties)
    : [],
}));

const prompts = (promptsResult && promptsResult.prompts ? promptsResult.prompts : []).map((p) => ({
  name: p.name,
  title: p.title ?? null,
  description: p.description ?? "",
  arguments: (p.arguments ?? []).map((a) => a.name),
}));

result.inventory = {
  tool_count: tools.length,
  prompt_count: prompts.length,
  tools,
  prompts,
};
result.stderr_bytes_observed = stderrText.length;
result.stderr_excerpt = stderrText.slice(0, 4000);

writeFileSync(join(OUT, "mcp_tools.json"), JSON.stringify(result, null, 2), "utf8");

await client.close();

const summary = {
  ok: true,
  connect_ms: result.connect.ms,
  protocol_version: result.connect.protocolVersion,
  server: result.connect.serverVersion,
  tool_count: tools.length,
  prompt_count: prompts.length,
  steps: result.steps,
  out: join(OUT, "mcp_tools.json"),
};
process.stdout.write(JSON.stringify(summary, null, 2) + "\n");
process.exit(0);
