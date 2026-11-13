// PHOENIX-001 REA validation: validate the DSH patch document that registers
// REA's MCP server, using the same YAML parser family DSH itself ships (yaml).
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const REQ = createRequire("D:/DEPPSKK/.rea/package.json");
const YAML = REQ("yaml");

const path = process.argv[2];
const text = readFileSync(path, "utf8");
const doc = YAML.parseDocument(text, { strict: true });
if (doc.errors.length > 0) {
  for (const e of doc.errors) console.log("PARSE ERROR:", e.message);
  process.exit(1);
}
const value = doc.toJS();
if (!Array.isArray(value)) {
  console.log("FAIL: root is not a list");
  process.exit(1);
}
const inserts = value.filter((e) => e && typeof e === "object" && "insert" in e);
const rows = inserts.flatMap((e) => e.insert ?? []);
const rea = rows.filter((r) => r && r.id === "rea-mcp");
const summary = {
  ok: rea.length === 1,
  root_is_list: true,
  patch_ops: value.length,
  inserted_rows: rows.map((r) => ({ id: r.id, name: r.name, config_keys: Object.keys(r.config ?? {}) })),
  rea_row: rea[0] ?? null,
};
process.stdout.write(JSON.stringify(summary, null, 2) + "\n");
process.exit(summary.ok ? 0 : 1);
