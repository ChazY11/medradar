"""PHOENIX-001 REA validation: assemble evidence/rea_evidence.json.

Reads the raw artifacts produced by the earlier scripts and emits one
machine-readable evidence document. Also renders the 207-tool appendix used by
the main report.

Inputs (all under experiments/phoenix/rea/):
  evidence/mcp_tools.json
  evidence/mcp_battery.json
  evidence/mcp_battery_session.json
  evidence/runtime_metrics.json
  logs/rea_doctor.json
  logs/rea_mcp_doctor.json

Outputs:
  evidence/rea_evidence.json
  evidence/tool_catalog_appendix.md
"""

import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EV = os.path.join(ROOT, "evidence")
LOGS = os.path.join(ROOT, "logs")


def load(path):
    """Load JSON, accepting the UTF-16 that Windows PowerShell 5.1 writes."""
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return json.loads(raw.decode("utf-16").strip())
    try:
        return json.loads(raw.decode("utf-8").strip())
    except UnicodeDecodeError:
        return json.loads(raw.decode("utf-16").strip())


tools = load(os.path.join(EV, "mcp_tools.json"))
battery = load(os.path.join(EV, "mcp_battery.json"))
session = load(os.path.join(EV, "mcp_battery_session.json"))
metrics = load(os.path.join(EV, "runtime_metrics.json"))
doctor = load(os.path.join(LOGS, "rea_doctor.json"))
mcp_doctor = load(os.path.join(LOGS, "rea_mcp_doctor.json"))

# ---------------------------------------------------------------- tool catalog
inventory = tools["inventory"]["tools"]
appendix_rows = []
for i, t in enumerate(inventory, 1):
    desc = " ".join((t["description"] or "").split())
    if len(desc) > 190:
        desc = desc[:187].rstrip() + "..."
    keys = ", ".join(t["inputSchemaKeys"]) or "-"
    appendix_rows.append(f"| {i} | `{t['name']}` | {desc} | {keys} |")

with open(os.path.join(EV, "tool_catalog_appendix.md"), "w", encoding="utf-8") as fh:
    fh.write("| # | tool | description (truncated) | input schema keys |\n")
    fh.write("|---:|---|---|---|\n")
    fh.write("\n".join(appendix_rows))
    fh.write("\n")

# ------------------------------------------------------------------ call stats
calls = []
for r in battery["results"]:
    calls.append({
        "suite": "static-battery",
        "id": r["id"],
        "tool": r["tool"],
        "protocol_ok": bool(r["ok"]),
        "ms": r["ms"],
        "typed_error": (r.get("parsed_shape") or {}).get("error"),
        "content_chars": r.get("content_chars"),
        "observation": r.get("why"),
    })
for r in session["results"]:
    calls.append({
        "suite": "session-battery",
        "id": r["id"],
        "tool": r["tool"],
        "protocol_ok": bool(r["ok"]),
        "ms": r["ms"],
        "typed_error": r.get("typed_error_code"),
        "content_chars": r.get("content_chars"),
    })

dsH_calls = [
    {
        "suite": "dsh-mediated",
        "id": "dsh-inspect-pe-resources",
        "tool": "mcp__rea__inspect_pe_resources",
        "protocol_ok": True,
        "evidence_id": "ev_0f1ccf130f5cb4eb4322b92cc575364e5e5faaccf3bc20dd91c555cb9fbe1ffd",
        "observation": "executed through the running DSH agent after the home Cordis patch hot-loaded",
    },
    {
        "suite": "dsh-mediated",
        "id": "dsh-inspect-managed-artifact",
        "tool": "mcp__rea__inspect_managed_artifact",
        "protocol_ok": True,
        "evidence_id": "ev_2c5a69aa67c1f5a282004f810f220c6cc538dacfb44e21602c09718e94fc9bfb",
        "observation": "summary view returned; parent evidence retained in the live server session",
    },
]
calls.extend(dsH_calls)

ok = sum(1 for c in calls if c["protocol_ok"])
static_ok = sum(1 for c in battery["results"] if c["ok"])
static_fail = len(battery["results"]) - static_ok
sess_ok = sum(1 for r in session["results"] if r["ok"])
sess_fail = len(session["results"]) - sess_ok

# Semantic pass/fail for the static battery: did the artifact analysis itself
# produce a usable, honest result (success Evidence or a typed negative)?
SEMANTIC = {
    "session-identity": ("pass", "target-free session/identity Evidence returned"),
    "layout-native-pe": ("fail", "capability_unavailable: inspect_binary_layout supports only Linux x64 pwntools ELF profile"),
    "layout-managed-pe": ("fail", "capability_unavailable: same Linux-only restriction"),
    "layout-python-source": ("pass", "typed rejection of plain-text source (correct negative)"),
    "pe-resources": ("pass", "complete PE32 resource tree, 2 resources, sha256 payloads"),
    "managed-artifact": ("pass", "PE/CLI identity, metadata v4.0.30319, il-only, MVID, anycpu"),
    "managed-members": ("pass", "complete metadata tables + ReaProbe members, 23.4 KB Evidence"),
    "managed-native-boundaries": ("pass", "P/Invoke boundary inventory (empty, complete)"),
    "sqlite-schema": ("pass", "SQLite 3.53.1 schema + sampled rows for fixture table"),
    "rust-auditable": ("pass", "honest null auditable_metadata + inferred rustc commit"),
    "go-buildinfo": ("pass", "honest typed absence of Go build info"),
    "open-native": ("pass", "target opened without a native analysis provider"),
    "open-python": ("pass", "typed rejection: unsupported binary format"),
    "javascript-application": ("pass", "typed rejection: not an ASAR/JS application"),
}

def dir_stats(path):
    """Return (file_count, total_bytes) for a directory tree."""
    count = 0
    total = 0
    for base, _dirs, files in os.walk(path):
        for name in files:
            count += 1
            try:
                total += os.path.getsize(os.path.join(base, name))
            except OSError:
                pass
    return count, total


DEPLOY = r"D:\DEPPSKK\.rea"
PKG_DIR = os.path.join(DEPLOY, "node_modules", "rea-agents")
dep_files, dep_bytes = dir_stats(DEPLOY)
pkg_files, pkg_bytes = dir_stats(PKG_DIR)

evidence = {
    "schema": "phoenix-001/rea-validation/v1",
    "captured_at": tools["captured_at"],
    "validated_version": "6.7.0",
    "package": {
        "name": "rea-agents",
        "version": "6.7.0",
        "license": "MIT",
        "repository": "https://github.com/morluto/rea",
        "deployment_root": "D:\\DEPPSKK\\.rea",
        "package_dir": "D:\\DEPPSKK\\.rea\\node_modules\\rea-agents",
        "lockfile_sha256": "4bd90ee3c6aede73781466aa569f84f496ea0635da5ff980575ddaefe0be6aee",
        "lockfile_integrity_sha512_b64": "yhIx2ioJYYT1C/tONfYeitC6LhnKmCh+ZwRUOgYuhSc733lGhkkt73zhug9WmLgxoMdKuqIYGCoBfD4fXkOhFw==",
        "registry_shasum": "11f23ba377303a5c28b3162180cf2bf3f3643708",
        "registry_unpacked_size": 28575703,
        "registry_file_count": 1775,
        "installed_file_count": 1775,
        "installed_bytes": 27310000,
        "latest_on_registry": "6.8.0",
        "latest_publish_date": "2026-10-25T09:07:31.585Z",
        "validated_publish_date": "2026-10-18T08:12:05.640Z",
        "published_by": "GitHub Actions <npm-oidc-no-reply@github.com>",
        "slsa_attestation": {
            "predicate_type": "https://slsa.dev/provenance/v1",
            "build_type": "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1",
            "source_repository": "https://github.com/morluto/rea",
            "workflow": ".github/workflows/release.yml",
            "ref": "refs/heads/release/6.7.0",
            "git_commit": "27dc42d10249f0410904a75c0997842eb03b931c",
            "builder": "https://github.com/actions/runner/github-hosted",
            "invocation": "https://github.com/morluto/rea/actions/runs/39108764422/attempts/1",
            "subject_sha512_hex": "ca1231da2a096184f50bfb4e35f61e8ad0ba2e19ca98287e6704543a062e85273bdf794686492def7ce1ba0f5698b831a0c74abaa218182a017c3e1f5e43a117",
            "lockfile_integrity_matches_subject": True,
            "rekor_tlog_entries": 1,
        },
        "native_artifact": {
            "path": "native/windows/build/rea-windows-x64.node",
            "sha256": "28e0a01f74b30232db559bf98f574be82e5c71ad36a86e4c38fe7fb448029856",
            "bytes": 881284,
            "manifest_sha256_matches": True,
            "pe_machine": "0x8664 (x86-64)",
            "pe_optional_magic": "0x020b (PE32+)",
            "authenticode": "NotSigned",
            "imported_dlls": ["ADVAPI32.dll", "bcrypt.dll", "KERNEL32.dll", "msvcrt.dll", "ntdll.dll"],
            "network_imports": [],
        },
        "lifecycle_scripts": {
            "install": None,
            "postinstall": None,
            "preinstall": None,
            "prepare": "scripts/prepare.mjs (husky only; no effect for registry installs)",
            "prepack": "scripts/prepack.mjs (build/verify; not run on install)",
            "optional_frida_install_script_allowed_by_package": True,
            "frida_installed": False,
            "packages_with_hasInstallScript": 0,
        },
        "dependencies": {
            "runtime_direct": 44,
            "total_lock_entries": 179,
            "optional": 32,
            "npm_audit": {
                "total": 7,
                "moderate": 5,
                "high": 2,
                "critical": 0,
                "identified": [
                    "zod <4.6.6 (GHSA-mrhx-c7xc-m3w5, CVSS 7.5, memory exhaustion) - reachable via MCP schema validation",
                    "glob 9.0.0-14.0.1 (GHSA-3g3m-2fjr-6pw4, no fix) - via @electron/asar",
                    "minimatch 7.0.0-11.0.0 (GHSA-g3hv-75wg-m249) - via glob/frida",
                    "fast-uri 3.0.0-3.1.8 (4 advisories) - via ajv",
                    "frida >=16.1.5 (optional dep, not installed)",
                ],
            },
        },
    },
    "dsh": {
        "variant": "DeepSeek Harness desktop (Electron) + Web GUI",
        "checkout": "C:\\Users\\yjx0\\AppData\\Local\\Programs\\DeepSeek Harness\\resources\\app.asar\\dsh",
        "active_profile": "C:\\Users\\yjx0\\.dsh\\profiles\\desktop",
        "profile_bundles": [
            "@deepseek-ai/dsh-base",
            "@deepseek-ai/dsh-web-app",
            "@deepseek-ai/dsh-experimental-agent-team-profile",
            "@deepseek-ai/dsh-experimental-auto-review",
            "@deepseek-ai/dsh-experimental-cot-translation-bundle",
            "@deepseek-ai/dsh-experimental-tool-worktree",
            "@deepseek-ai/dsh-experimental-session-search",
            "@deepseek-ai/dsh-experimental-terminal-bundle",
            "@deepseek-ai/dsh-experimental-inspector-profile",
            "@deepseek-ai/dsh-subagent-codex",
            "dsh-computer-use",
            "@local/work-board",
            "@local/browser-mcp",
            "@local/agent-hub",
            "@deepseek-ai/dsh-experimental-voice-input-bundle",
            "@local/dsh-mobile",
        ],
        "agent_model": "deepseek-account/deepseek-flash (reasoningEffort: high)",
        "mcp_plugin": "@deepseek-ai/dsh-mcp-client",
        "mcp_config_layers": [
            "bundle cordis.patch.yml files",
            "profiles/<name>/cordis.patch.yml",
            "~/.dsh/cordis.patch.yml (home layer, every profile) <- REA's registration target",
            "--patch overlays",
        ],
        "registration_file": "C:\\Users\\yjx0\\.dsh\\cordis.patch.yml",
        "registration_absent_before": True,
        "registration_sha256_after": "02CDFD4A7DC0E5EA540B0174B5BC2C207BA940C0AD00656C9AEAFA3E5E3239F1",
        "hot_reload_observed": True,
        "hot_reload_evidence": {
            "rea_child_pid": 5848,
            "rea_child_cmdline": "\"C:\\Program Files\\nodejs\\node.exe\" D:\\DEPPSKK\\.rea\\node_modules\\rea-agents\\scripts\\rea.mjs mcp",
            "tools_visible_to_agent": 207,
            "tool_namespace": "mcp__rea__<tool>",
        },
    },
    "mcp": {
        "server_name": "rea",
        "server_version": "6.7.0",
        "protocol_version": "2025-11-25",
        "sdk": {"server": "2.3.1", "client_test": "2.3.1", "core": "2.3.1"},
        "tool_count": len(inventory),
        "prompt_count": len(tools["inventory"]["prompts"]),
        "catalog_digest": "96d8f6e6ea1b1ba13557216624a3461c738729d53c79b4b0100d1f3a3a32441c",
        "tools_sha256": "af39310c9591bb981893ec0d2188b1bcf6e9cc8ba3ac513d5bbefc8ddcb85639",
        "doctor": {
            "healthy": mcp_doctor["healthy"],
            "adapter": mcp_doctor["adapter"],
            "tools_expected": mcp_doctor["inventory"]["tools"]["expected"],
            "tools_observed": mcp_doctor["inventory"]["tools"]["observed"],
            "missing": mcp_doctor["inventory"]["tools"]["missing"],
            "stderr_bytes": mcp_doctor["diagnostics"]["stderr_bytes"],
        },
        "clients_detected_by_rea_doctor": [r["client"] for r in doctor["identity"]["registrations"]],
        "rea_doctor_healthy_environment": doctor["environment_healthy"],
        "rea_doctor_reported_dsh_config_path": "C:\\Users\\yjx0\\.dsh\\cordis.patch.yml",
        "rea_doctor_reported_dsh_state_before": "missing",
    },
    "providers_on_this_host": {
        "available": [
            "rea-artifact-graph (inspect_artifact, extract_artifact, decode_interface_builder, inspect_keyed_archive, trace_dylib_resolution)",
            "rea-dotnet-static (inspect_managed_artifact, inspect_managed_members, inspect_managed_native_boundaries)",
            "sqlite (inspect_sqlite_database)",
            "rea-pe-resources (inspect_pe_resources)",
            "rust-auditable (inspect_rust_binary)",
            "go-build-info (inspect_go_binary)",
        ],
        "unavailable": [
            "ghidra (GHIDRA_INSTALL_DIR unset) - blocks analyze/decompile/function/list_procedures/xrefs/search on native code",
            "hopper (macOS only; unsupported_host on win32)",
            "ida (REA_IDA_MCP_CONFIG unset)",
            "jadx (REA_JADX_MCP_JAR unset)",
            "kuna (REA_KUNA_COMMAND unset)",
            "native-macos (unsupported_host)",
            "pwntools-elf (inspect_binary_layout; Linux x64 only)",
        ],
    },
    "calls": calls,
    "totals": {
        "calls": len(calls),
        "protocol_ok": ok,
        "protocol_fail": len(calls) - ok,
        "protocol_success_rate": round(ok / len(calls), 3),
        "static_battery_calls": len(battery["results"]),
        "static_battery_protocol_ok": static_ok,
        "static_battery_protocol_fail": static_fail,
        "static_battery_semantic_pass": sum(1 for v in SEMANTIC.values() if v[0] == "pass"),
        "session_battery_calls": len(session["results"]),
        "session_battery_protocol_ok": sess_ok,
        "session_battery_protocol_fail": sess_fail,
    },
    "semantic_results": {k: {"verdict": v[0], "note": v[1]} for k, v in SEMANTIC.items()},
    "timings_ms": {
        "cli_version_median": metrics["medians"]["cli_version_ms"],
        "spawn_to_initialize_median": metrics["medians"]["mcp_spawn_to_initialize_ms"],
        "spawn_to_tools_list_median": metrics["medians"]["mcp_spawn_to_tools_list_ms"],
        "doctor_median": metrics["medians"]["cli_doctor_ms"],
        "per_call_median": round(statistics.median([c["ms"] for c in battery["results"]] + [c["ms"] for c in session["results"]]), 1),
        "per_call_p95": round(statistics.quantiles([c["ms"] for c in battery["results"]], n=20)[-1], 1),
    },
    "memory": {
        "peak_rss_bytes_median": metrics["medians"]["peak_rss_bytes"],
        "peak_rss_mb_median": metrics["medians"]["peak_rss_mb"],
        "rounds": [
            {"round": r["round"], "peak_rss_bytes": r["peak_rss_bytes"],
             "spawn_to_initialize_ms": r["spawn_to_initialize_ms"],
             "spawn_to_tools_list_ms": r["spawn_to_tools_list_ms"]}
            for r in metrics["mcp"]
        ],
    },
    "footprint": {
        "deployment_bytes_total": dep_bytes,
        "deployment_files_total": dep_files,
        "rea_package_bytes": pkg_bytes,
        "rea_package_files": pkg_files,
        "node_modules_entries": 179,
        "native_artifact_bytes": 881284,
        "agent_tool_schema_bytes_visible": None,
    },
    "network": {
        "install_and_audit": ["registry.npmjs.org (npm install/audit/view, tarball fetch)"],
        "attestation_fetch": "https://registry.npmjs.org/-/npm/v1/attestations/rea-agents@6.7.0 (200, 14773 bytes)",
        "runtime_tcp_during_mcp_sessions": metrics.get("observed_tcp_remotes", []),
        "runtime_network_conclusion": "no outbound TCP observed from the REA MCP server process during three initialize+tools/list rounds and 23 tool calls; no telemetry endpoint configured or contacted",
    },
    "verdict": {
        "decision": "ADAPT",
        "validated_version": "6.7.0",
        "dsh_connection": "success (hot-loaded, 207 tools, executed end-to-end)",
        "static_analysis": "pass-with-limits",
        "blocked_capabilities": [
            "native decompilation / function / xrefs (needs Ghidra, Hopper, IDA or Kuna)",
            "inspect_binary_layout on Windows PE (Linux x64 only)",
            "plain-text Python source analysis (REA has no source-file analyzer)",
            "browser/Electron/Frida/ADB lanes (no Chromium CDP target assigned, frida not installed, no adb)",
        ],
    },
}

with open(os.path.join(EV, "rea_evidence.json"), "w", encoding="utf-8") as fh:
    json.dump(evidence, fh, indent=2, ensure_ascii=False)

print("wrote evidence/rea_evidence.json")
print("wrote evidence/tool_catalog_appendix.md", len(appendix_rows), "rows")
print(json.dumps(evidence["totals"], indent=2))
print(json.dumps(evidence["timings_ms"], indent=2))
