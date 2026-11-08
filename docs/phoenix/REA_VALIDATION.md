# REA (Reverse Engineer Anything) — Deployment & Empirical Validation

**Program:** PHOENIX-001, Section 3 (external methods)
**Package:** [`rea-agents`](https://www.npmjs.com/package/rea-agents) 6.7.0 (MIT), upstream <https://github.com/morluto/rea>
**Validated on:** this workstation, 2026-11-08
**Author:** `rea-ops` (autonomous validation run)
**Machine-readable evidence:** [`rea_evidence.json`](../../experiments/phoenix/rea/evidence/rea_evidence.json) · raw logs and tool inventory under [`experiments/phoenix/rea/`](../../experiments/phoenix/rea/)

> Everything below was produced by commands actually run in this session. Where a step failed, the failure is reported with its exact error code. No result is inferred or filled in.

---

## 0. Headline

| Question | Answer |
|---|---|
| Verdict | **ADAPT** |
| Version validated | **rea-agents 6.7.0** (registry `latest` is 6.8.0) |
| Did DSH host it? | **Yes — succeeded.** Home-letter Cordis patch hot-loaded; the running DSH agent now exposes **207 `mcp__rea__*` tools**, and two of them were executed end-to-end through DSH. |
| Tool count | **207 tools / 6 prompts**, catalog digest `96d8f6e6…441c`, MCP protocol `2025-11-25` |
| Static analysis on our fixture | **Pass, with limits.** 12/14 battery calls produced a correct, honest expected outcome; PE/CLI, PE resources, SQLite and PE build-metadata all returned Evidence-grade output. Native decompilation is **blocked** (no Ghidra/Hopper/IDA) and `inspect_binary_layout` is **Linux-x64-only**. |
| Protocol-level tool-call success | 17/25 (68 %); the 8 failures are typed, named capability errors (`capability_unavailable`, `provider_unavailable`, `target_unavailable`, `unsupported_target`) — no crashes, no hangs. |
| Peak RSS of the MCP server | **391 MB** (median of 3) — the dominant cost of the deployment |
| Runtime network egress | **None observed.** No outbound TCP from the MCP process across 3 start-up rounds and 23 tool calls. |

---

## 1. Environment audit

| Item | Observed value |
|---|---|
| OS | Microsoft Windows 11 家庭版 (Chinese), version `10.0.26200`, build **26200** (WMI reports product string "Windows 10 Home China") |
| CPU | Intel Core Ultra 9 285H — 16 cores / 16 logical processors |
| RAM | 33 752 924 160 B ≈ **31.4 GiB** physical |
| Disk | `C:` 400.2 GB free / 923.9 GB · `D:` 488.3 GB free / 3 726 GB |
| Node | **v24.18.0** (satisfies REA `engines: ^22.19.0 \|\| ^24.11.0 \|\| >=26.0.0`) |
| npm | 11.16.0, registry `https://registry.npmjs.org/` (official, no mirror), `ignore-scripts=false` |
| Python | 3.12.10 on PATH |
| Other toolchains | git 2.55.0, rustc 1.97.0, in-box `csc.exe` 4.0.30319, PowerShell 5.1 (Desktop). **No** gcc/clang/cl, objdump, rizin, wasm-objdump, java, adb, frida, dotnet SDK. |
| Shell | Windows PowerShell 5.1 — JSON logs are UTF-16; readers must honour the BOM |

### 1.1 How the current agent runtime (DSH) is configured

- Runtime: **DeepSeek Harness desktop** (Electron) with the Web GUI at `http://127.0.0.1:59271`.
- Implementation checkout: `C:\Users\yjx0\AppData\Local\Programs\DeepSeek Harness\resources\app.asar\dsh` (inside `app.asar`; read with `@electron/asar`, not `Get-ChildItem`).
- Launch args prove the active profile: `…\dsh-desktop-host\lib\index.js … C:\Users\yjx0\.dsh\profiles\desktop …`.
- Active profile manifest: `~/.dsh/profiles/desktop/package.json` — 16 bundles, including `@deepseek-ai/dsh-base`, `dsh-web-app`, `dsh-experimental-agent-team-profile`, `dsh-computer-use`, and three local link bundles (`@local/work-board`, `@local/browser-mcp`, `@local/agent-hub`, `@local/dsh-mobile`).
- Agent model row: `provider: deepseek-account`, `model: deepseek-flash`, `reasoningEffort: high`.
- **MCP is a plugin, not a server table**: `@deepseek-ai/dsh-mcp-client`. Configuration layers are composed in this order (verified in `@deepseek-ai/dsh-app-boot`):

  1. each bundle's `cordis.patch.yml`
  2. `profiles/<name>/cordis.patch.yml`
  3. **`~/.dsh/cordis.patch.yml` — the home layer, applied to every profile**
  4. `--patch` overlays

  (Source: `loadProfileDirectory` → `readProfilePatches`, which calls `loadOptionalPatches(binName, join(context.home, "cordis.patch.yml"))`.)
- DSH's own MCP contract (from `dsh-mcp-client`'s README): tools appear as `mcp__<serverName>__<rawName>`; the config keys are `serverName`, `transport` (`stdio` | `streamable-http`), `command`/`args`/`env`/`cwd`, `failOnStartupError` (default **false**); stdio negotiation spawns a *temporary probe process* before the serving process; ambient env names matching `KEY|PASSWORD|SECRET|TOKEN` and all `DSH_*` names are scrubbed.

---

## 2. Upstream review

### 2.1 What the package is

`rea-agents` is a single-package CLI + MCP server (153 CLI commands, 207 MCP tools, 6 MCP prompts) for static and runtime analysis of binaries, application packages, browser pages, Android devices and debuggers. Its value proposition is **Evidence-grade output**: every tool result carries `evidence_id`, `subject.sha256`, `provider`, `confidence`, `authority`, explicit `coverage` and a `limitations` array.

README claims verified in this session:

- "REA does not install [analysis engines]" — **true**: Ghidra/IDA/jadx/Kuna are caller-supplied via env vars; `rea doctor` reports them as `missing_analysis_engine`, not as errors to auto-fix.
- "Any agent that supports local MCP servers" — **true**: `rea doctor` ships first-class adapters for 10 clients including `dsh` (DeepSeek Harness), `claude_code`, `codex`, `cursor`, `opencode`, `kimi`, `workbuddy`, `zcode`, `vscode`, `copilot_cli` — and a `manualRegistrationRemediation` path for clients without local config files.
- Native analysis needs Hopper (macOS), Ghidra, IDA or Kuna; JavaScript/Electron/PE/managed/SQLite lanes are self-contained.

### 2.2 Licence

- Package: **MIT**, `Copyright (c) 2026 morluto` (`LICENSE`, 1 064 B, unmodified MIT text).
- `DISCLAIMER.md` (7 105 B) is a responsible-use document: authorisation, runtime/network/device side effects, "results do not guarantee accuracy", third-party licences, no warranty.
- Bundled third-party components (`third_party/`, `licenses/`): evmole (MIT), pwntools 4.15.0 (MIT) + Unicorn 2.1.2 (**GPL-2.0**, used for PLT emulation), pwndbg 2026.09.15 (MIT), wabt 1.0.42 (Apache-2.0). Reachable only through the Linux-x64 pwntools profile; not used on this host.

### 2.3 Release history and provenance

- **34 published versions**, 2026-07-12 → 2026-10-25.
- Sequence: `… 6.2.0, 6.3.0, 6.4.0, 6.5.0, 6.7.0, 6.8.0` — **6.6.0 was never published** (no yank notice available; treat as a skipped number, not evidence of a removed release).
- Installed/validated: **6.7.0**, published `2026-10-18T08:12:05.640Z`.
- Registry `latest`: **6.8.0**, published `2026-10-25T09:07:31.585Z` (unpacked 49.3 MB, 2 398 files — 72 % larger than 6.7.0's 28.6 MB / 1 775 files).
- Publisher identity: `_npmUser = "GitHub Actions <npm-oidc-no-reply@github.com>"`, maintainer `morluto <morluto@hotmail.com>`, repo `git+https://github.com/morluto/rea.git`.

**Provenance chain (independently verified, not just read off a page):**

| Link | Value |
|---|---|
| `npm view rea-agents@6.7.0 dist.integrity` | `sha512-yhIx2ioJYYT1C/tONfYeitC6LhnKmCh+ZwRUOgYuhSc733lGhkkt73zhug9WmLgxoMdKuqIYGCoBfD4fXkOhFw==` |
| → decoded to hex | `ca1231da…5e43a117` |
| npm registry signatures | 2 ECDSA sigs, key `SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U` |
| SLSA attestation (`registry.npmjs.org/-/npm/v1/attestations/rea-agents@6.7.0`, fetched, 14 773 B) | subject `pkg:npm/rea-agents@6.7.0`, sha512 **identical to the lockfile integrity** |
| SLSA provenance | `buildType: github-actions workflow v1`, repo `github.com/morluto/rea`, workflow `.github/workflows/release.yml`, ref `refs/heads/release/6.7.0`, commit `27dc42d10249f0410904a75c0997842eb03b931c`, builder `github-hosted`, run `39108764422/attempts/1` |
| Transparency log | 1 Rekor `tlogEntry` present |

This is a genuinely strong chain: the tarball the lockfile pins is the artefact that a GitHub-hosted Actions run built from a named commit on a release branch, with a public transparency-log entry.

### 2.4 What ships inside, and what would execute

- Package layout: `dist/` (compiled JS), `scripts/rea.mjs` (CLI entry), `skills/`, `bridge/` (Python/Java/Swift bridge sources for Hopper/Ghidra/JADX/Frida), `native/windows/build/rea-windows-x64.node`, `licenses/`, `third_party/`, `install.sh`.
- **`install.sh` is not a lifecycle hook** (no `postinstall`/`preinstall`/`install` field in `package.json`) and it **refuses to run on Windows** (`platform` must be Darwin or Linux). It installs with `npm install --global`, then checks the installed version. It is macOS/Linux-only and was never executed here.
- Only two lifecycle scripts exist: `prepare` → `scripts/prepare.mjs` (installs husky, and only when a `src/` tree exists) and `prepack` → `scripts/prepack.mjs` (build + file-presence checks). npm does not run either for a registry tarball dependency.
- Lockfile audit: **0 packages with `hasInstallScript`**. The one dependency that declares one, `frida` 17.23.2, is an *optional* dependency and is **not installed**. (`package.json` carries `allowScripts: {"frida@17.23.2": true}`, which matters only if frida is ever installed.)
- Dependency count: **44 runtime dependencies** (all exact-pinned in the package's own manifest), **179 lock entries**, 32 optional. Prebuilt native payload: **1** (`rea-windows-x64.node`).

---

## 3. Version lock

| Item | Value |
|---|---|
| Validated version | **`rea-agents@6.7.0`** |
| Why this version | It is what `D:\DEPPSKK\.rea` already pins and has installed; no upgrade was performed, so every measurement is against the artefact whose hash is recorded below. 6.8.0 is newer but unvalidated here. |
| Deployment root | `D:\DEPPSKK\.rea` (`package.json`, `package-lock.json`, `node_modules\`) |
| Lockfile format | `lockfileVersion: 3` |
| **Lockfile SHA-256** | `4bd90ee3c6aede73781466aa569f84f496ea0635da5ff980575ddaefe0be6aee` (78 645 B) |
| Tarball integrity (sha512) | `yhIx2ioJYYT1C/tONfYeitC6LhnKmCh+ZwRUOgYuhSc733lGhkkt73zhug9WmLgxoMdKuqIYGCoBfD4fXkOhFw==` |
| Registry `shasum` (sha1) | `11f23ba377303a5c28b3162180cf2bf3f3643708` |
| Installed size / files | 28 575 703 B / **1 775 files** — **byte-identical to the registry's `unpackedSize: 28575703`** and to its `fileCount: 1775`, an independent integrity signal on top of the tarball hash |
| Native artifact SHA-256 | `28e0a01f74b30232db559bf98f574be82e5c71ad36a86e4c38fe7fb448029856`, 881 284 B; matches the in-package `native/windows/build/manifest.json` and the package's own verifier (`node scripts/verify-windows-native-artifact.mjs` → `{"ok":true,…}`) |
| Engine | node `^22.19.0 \|\| ^24.11.0 \|\| >=26.0.0`; host 24.18.0 ✔ |

**Stability caveat worth acting on.** `D:\DEPPSKK\.rea\package.json` declares `"rea-agents": "^6.7.0"`. A caret range means the *next* `npm install` in that directory would resolve to **6.8.0**; only the committed lockfile holds 6.7.0 in place. If this deployment is to be cited later, pin the exact version (`"6.7.0"`) and keep the lockfile under version control.

---

## 4. Supply-chain risk list

| # | Component / behaviour | Risk | Evidence | Verdict |
|---|---|---|---|---|
| 1 | **`native/windows/build/rea-windows-x64.node`** — 881 284 B prebuilt, **unsigned** PE32+ AMD64 shipping *inside* the npm tarball | Unmanaged code loaded in-process at startup; no Authenticode signer to check. Root of trust is the tarball → SLSA chain, not the binary's own signature. Imports only `ADVAPI32`, `bcrypt`, `KERNEL32`, `msvcrt`, `ntdll` — **no network APIs** (no `WS2_32`/`WININET`), so it cannot phone home by itself. | `Get-AuthenticodeSignature` → `NotSigned`; PE header `machine=0x8664`, `optMagic=0x020B`; independent SHA-256 == manifest | **Accept with pinning.** Hash-pin the file; re-run `verify-windows-native-artifact.mjs` on every install; do not accept a rebuild without a new recorded hash. |
| 2 | **`zod` < 4.6.6** (transitive) — GHSA-mrhx-c7xc-m3w5, CVSS 7.5, memory exhaustion on oversized constrained collections | **High** by npm audit. Reachable at the MCP schema-validation boundary — i.e. attacker-controlled *tool arguments*, not target content. Blast radius is the MCP host process (DoS), not data disclosure. | `npm audit --json`: `zod` high, `fixAvailable: false` at 6.7.0 | **Real but bounded.** Accept for an operator-driven session; treat as a reason not to expose this server to untrusted callers. Check whether 6.8.0 bumps zod before adopting upstream. |
| 3 | `glob` 9.0.0–14.0.1 / `minimatch` ≤ 11.0.0 (via `@electron/asar`) | Moderate DoS in globbing/pattern matching. Only reached by asar/glob code paths; `maxEntries`-style bounds are not applied there. | npm audit, `fixAvailable: false` | **Low.** Not on the default static-analysis path; keep asar analysis out of automated loops. |
| 4 | `fast-uri` 3.0.0–3.1.8 (4 advisories, via `ajv`) | Moderate/low URI parsing confusion (scheme spoofing, host confusion). Relevant only where REA parses attacker-supplied URIs (web/CDP lanes, HAR analysis). | npm audit | **Low** for our use; do not point the web lanes at hostile pages. |
| 5 | **`frida` 17.23.2** — optional dependency whose install script is explicitly allowed (`allowScripts`) | If ever installed, it downloads a native instrumentation runtime. Not installed here, so no script ran. | `Test-Path .rea\node_modules\frida` → `False`; 0 `hasInstallScript` entries in the locked tree | **Keep uninstalled.** Do not add `frida` to the deployment unless dynamic instrumentation is explicitly authorised. |
| 6 | Bundled `third_party/` (pwntools, Unicorn GPL-2.0, pwndbg, wabt, evmole) | Licence hygiene only; the GPL-2.0 Unicorn engine is used **out of process** by the Linux pwntools profile, which this host cannot use. | `THIRD_PARTY_NOTICES.md`, `licenses/*`, `third_party/*/README.md` | **OK for internal analysis.** Re-review if any output is redistributed. |
| 7 | `rea setup` can install Hopper "after approval"; Ghidra/IDA/jadx/Kuna must be caller-supplied | Silent third-party downloads would be a policy violation | `rea doctor` shows all engines as `missing_analysis_engine`/`not_configured`; README states installation is approval-gated | **Accept; never run `rea setup` unattended.** We did not run it. |
| 8 | MCP tool surface — 207 tools, many with declared side effects (`launches_process`, `may_write_filesystem`, `mutates_artifact`, `may_show_ui`, `may_access_network`, ADB device-mutating tools) | Broad capability reachable by one mis-prompt | `rea capabilities` effects arrays; tool descriptions | **High-steer risk.** Register with the narrow `serverName`-scoped tool names and keep human review for any tool whose description says *mutates*, *install*, *push*, *uninstall*, *start*, *instrument*. |
| 9 | Target content is untrusted input | Prompt injection via analysed artefacts | REA marks such results with `_meta.provenance.untrusted_content` and its own guidance says treat them as data | **Policy control, not a bug.** Our program already treats fetched/repo content as untrusted; extend that to REA tool output explicitly. |
| 10 | Network egress at runtime | Unexpected telemetry/uploads | No outbound TCP observed from the server process during 3 start-ups + 23 calls; no telemetry endpoint in config | **None observed.** Install-time traffic is npm registry only (plus the one attestation fetch). |

Aggregate `npm audit` result: **7 advisories — 0 critical, 2 high (`zod`, aggregated `rea-agents`), 5 moderate**; `fixAvailable: false` for every one at 6.7.0.

---

## 5. MCP registration (config diff, applied and reversible)

### 5.1 Where DSH actually reads MCP config

Investigated `C:\Users\yjx0\.dsh\`: `profiles\{desktop,headless}\{package.json,cordis.yml,cordis.patch.yml}`, `storages\{workspace.json,schedule.json,session_projcache\}`, `cache/`, `sessions/`, `.credentials.yaml`. There is **no** project-level MCP file under `D:\DEPPSKK\medradar`, and no `mcp.json` anywhere.

Confirmed from `@deepseek-ai/dsh-app-boot` that `~/.dsh/cordis.patch.yml` is a **valid, home-wide user layer**. This validates REA's own `dsh` client adapter, which writes exactly that path (`rea doctor` reports `registration:dsh` → `C:\Users\yjx0\.dsh\cordis.patch.yml`). Note: `rea doctor` reported it `missing` **before** this deployment — i.e. REA was installed but not registered.

### 5.2 The diff

**File:** `C:\Users\yjx0\.dsh\cordis.patch.yml` — **did not exist before** (`Test-Path` → `False`; pre-state of `~/.dsh` contained only `.anonymous-user-id` and `.credentials.yaml`).

```diff
+ # PHOENIX-001 / REA 6.7.0 MCP registration for DeepSeek Harness.
+ # (comments elided here; full file kept verbatim in evidence/dsh_cordis.patch.yml)
+ - insert:
+     - id: rea-mcp
+       name: '@deepseek-ai/dsh-mcp-client'
+       config:
+         serverName: rea
+         transport: stdio
+         command: 'C:\Program Files\nodejs\node.exe'
+         args:
+           - 'D:\DEPPSKK\.rea\node_modules\rea-agents\scripts\rea.mjs'
+           - mcp
+         failOnStartupError: false
```

Design notes for this diff:

- `id: rea-mcp` and `name: '@deepseek-ai/dsh-mcp-client'` are exactly the constants REA's own `DshCordisPatch.js` uses (`DSH_ENTRY_ID`, `DSH_CLIENT_PACKAGE`), so a later `rea setup` will recognise and update this row instead of duplicating it.
- `node.exe` and `rea.mjs` are **absolute paths**: DSH spawns the command without a shell, and the desktop process' PATH cannot be assumed to contain the npm shim.
- `failOnStartupError: false` is stated explicitly (it is also the documented default). Rationale: a broken third-party server must never be able to block DSH startup. **This is a deliberate, documented deviation** from the npm-package template, which uses `true`.
- Serialisation uses `yaml` (the same parser family DSH ships); validation script `scripts/validate_dsh_patch.mjs` parsed it strictly and confirmed one `insert` op with the expected keys.

### 5.3 Backup and rollback

| Item | Value |
|---|---|
| Backup path | `experiments/phoenix/rea/evidence/dsh_cordis.patch.yml` (verbatim copy) |
| Pre-state | file absent → nothing to overwrite; rollback is file deletion |
| Post-state SHA-256 | `02CDFD4A7DC0E5EA540B0174B5BC2C207BA940C0AD00656C9AEAFA3E5E3239F1` |
| Rollback | `Remove-Item C:\Users\yjx0\.dsh\cordis.patch.yml` — returns DSH to its exact prior tool inventory on next start |
| Blast radius | home layer ⇒ applies to **every** profile (`desktop` and `headless`) |

---

## 6. Connection verification

**Result: succeeded, in this running session.**

1. **Static validation first.** `rea mcp doctor --json` → `healthy: true`, adapter `production-stdio`, server `rea@6.7.0`, protocol `2025-11-25`, tools `expected=207 observed=207` (no missing/unexpected/duplicates), prompts `6/6`, catalog digest match, and a real `binary_session` request-flow round trip. 3 runs: median **4 608 ms**, exit 0.
2. **Independent client.** `scripts/mcp_probe.mjs` drives the official `@modelcontextprotocol/client` 2.3.1 over stdio: connect **1 677 ms**, `tools/list` **511 ms**, `prompts/list` 5 ms, 207 tools, 6 prompts, negotiated `2025-11-25`, `serverInfo {name: rea, version: 6.7.0}`.
3. **DSH-side hosting.** After writing the home patch, **DSH hot-reloaded the layer without a restart**: a new child appeared —
   `PID 5848  "C:\Program Files\nodejs\node.exe" D:\DEPPSKK\.rea\node_modules\rea-agents\scripts\rea.mjs mcp`
   and the agent's tool namespace gained **207 `mcp__rea__<tool>` entries**.
4. **End-to-end execution through DSH.** Two tools were then called *through the host agent itself*:
   - `mcp__rea__inspect_pe_resources` → Evidence `ev_0f1ccf13…be1ffd`, complete PE32 resource tree, 2 resources, payload SHA-256s, `coverage.status = complete`.
   - `mcp__rea__inspect_managed_artifact` (summary) → Evidence `ev_2c5a69aa…c9bfb`, CI header, metadata `v4.0.30319`, `il-only`, `anycpu`, MVID `a2ba9acc-…`, retaining parent `ev_05a8ae24…b01c`.
   This is the strongest form of connection proof available: the tool list negotiated, the tools registered under DSH's naming contract, and calls returned real Evidence.
5. **Reported version:** `rea 6.7.0` on both the CLI and the MCP `serverInfo`; protocol `2025-11-25` (DSH's client prefers `2026-07-28` and negotiated down — it works, but this is a legacy-revision path worth re-checking on future DSH builds).
6. **Tool list:** 207 names + descriptions + input-schema keys are reproduced in full in the appendix below and in `evidence/mcp_tools.json`; prompts are 6.

---

## 7. Static-analysis validation on self-built fixtures

Fixtures (all created by this run, harmless, under `experiments/phoenix/rea/fixtures/`):

| Fixture | Origin | Size | SHA-256 |
|---|---|---|---|
| `sample.py` | hand-written, stdlib only | 1.1 KB | — |
| `build/sample-native.exe` | `rustc 1.97.0 -O` | 126 464 B | `0e0e39e2…afc3c` |
| `build/sample-managed.exe` | in-box `csc.exe /target:exe` (PE/CLI) | 4 608 B | `5676d983…3e53f` |
| `sample.sqlite` | `sqlite3` via stdlib `make_sqlite.py` | 12 288 B | `8918356a…f9f8` |
| `build/sample-bundle.zip` | `System.IO.Compression` | 331 B | — |

All fixtures were also run once to prove they execute/parse normally (`sample-managed.exe` and `sample-native.exe` print `negative,zero,positive`).

### 7.1 Results (MCP calls, in-session timings)

| # | Tool | Target | Latency | Protocol | Outcome quality |
|---|---|---:|---:|---|---|
| 1 | `binary_session` | — | 95 ms | ok | Full capability matrix; identified every engine as unavailable with remediation text. 68 KB — large |
| 2 | `inspect_binary_layout` | native PE | 15 ms | **fail** | `capability_unavailable` / `unsupported_provider`: *"The initial real-verified pwntools artifact profile supports Linux x64 only."* Provider `pwntools-elf` |
| 3 | `inspect_binary_layout` | managed PE | 2 ms | **fail** | same restriction |
| 4 | `inspect_binary_layout` | `sample.py` | 2 ms | **fail** | same restriction (masked the real reason: the tool is Linux-only before it ever inspects the file) |
| 5 | `inspect_pe_resources` | managed PE | 15 ms | ok | **Excellent.** PE32, machine 332, complete resource tree, per-payload SHA-256, `coverage.complete` |
| 6 | `inspect_managed_artifact` | managed PE | 33 ms | ok | **Excellent.** CLI header at offset 520, runtime `2.5`/metadata `v4.0.30319`, `il-only`, entry `0x06000003`, metadata size 1 228, MVID |
| 7 | `inspect_managed_members` | managed PE, `type_names:["ReaProbe"]` | 30 ms | ok | **Excellent.** Full metadata row counts, TypeDef/Field/MethodDef, decoded CIL, `#US` literals — 23.4 KB of Evidence |
| 8 | `inspect_managed_native_boundaries` | managed PE | 11 ms | ok | Complete P/Invoke inventory (empty, correctly, for a pure-CIL assembly) |
| 9 | `inspect_sqlite_database` | `sample.sqlite`, table `signals` | 265 ms | ok | **Good.** SQLite 3.53.1, engine + WAL digests, `CREATE TABLE` SQL, column types/PK, sampled rows. Includes a JS worker, hence the latency |
| 10 | `inspect_rust_binary` | native PE | 13 ms | ok | **Honest negative.** `auditable_metadata: null` + limitation text; also inferred the rustc commit hash from a `/rustc/<40-hex>/` path |
| 11 | `inspect_go_binary` | native PE | 8 ms | ok | **Honest negative.** `build_info: null`, explicit "absence does not establish the binary is not Go" |
| 12 | `open_binary` | native PE | 13 ms | ok | Opens and digests a PE **without** any native provider (format/kind/arch/sha256) |
| 13 | `open_binary` | `sample.py` | 5 ms | **fail** | `target_unavailable` — *"unsupported binary format"* (correct: REA has no source-file analyser) |
| 14 | `analyze_javascript_application` | `sample.py` | 9 ms | **fail** | `unsupported_target` — accepts only a directory or `.asar` |

Session-scoped follow-ups (14 fixtures + 9 = 23 MCP calls before the two DSH-mediated calls):

| # | Tool | Latency | Outcome |
|---|---|---:|---|
| 15 | `open_binary` (native PE) | 29 ms | ok — session target bound |
| 16 | `binary_overview` | 7 ms | **`provider_unavailable`** — typed, with remediation |
| 17 | `list_segments` | 5 ms | `provider_unavailable` |
| 18 | `list_strings` | 4 ms | `provider_unavailable` |
| 19 | `binary_session` (after open) | 72 ms | ok — session state reflected |
| 20 | `close_binary` | 11 ms | ok |
| 21 | `open_binary` (zip) | 6 ms | ok — archive accepted |
| 22 | `inspect_artifact` (summary) | 38 ms | ok — content-addressed artifact graph for a real archive |
| 23 | `close_binary` | 2 ms | ok |

CLI parity spot-checks (same fixtures, from `D:\DEPPSKK\.rea`):

- `rea inspect-managed-members <fixture>` → exit 0, 23 179 B JSON, **2 371 ms** wall.
- `rea inspect-sqlite-database <fixture>` → exit 0, 4 524 B JSON, **2 139 ms** wall.
- `rea inspect-binary-layout <fixture>` → exit **1**, same `capability_unavailable` JSON, 1 816 ms.

### 7.2 Reading of the static-analysis result

- **Pass** for everything REA can actually do on this host: PE resource inventory, PE/CLI identity, PE/CLI metadata members, managed native boundaries, SQLite schema+rows, PE build metadata readers (Go/Rust), archive artifact graphs. Output is precise, digest-anchored, and — importantly — **honest about absence** (`null` + limitation rather than a guess).
- **Fail / blocked**, recorded rather than excused:
  - `inspect_binary_layout` is **Linux-x64-only** despite its generic CLI description. On Windows it cannot inspect a Windows PE. This is the single largest surprise of the run.
  - No decompilation, function dossiers, xrefs, string search or procedure listing for a native PE — all of those are Ghidra/Hopper/IDA/Kuna-backed and every engine is absent.
  - Plain-text source (Python here) is not a supported artifact at all.
- Output is verbose: the same PE resource result is 3.7 KB over MCP and 4.5 KB compact JSON over CLI, while `binary_session` is 68 KB and `inspect_managed_members` 23 KB. **Token budget is a real operational cost**, not a rounding error.

---

## 8. Metrics

| Metric | Value | Method |
|---|---|---|
| CLI startup (`rea --version`) | **1 534 ms** median (1 527 / 1 906 / 1 534) | 3 × subprocess, wall clock |
| `rea mcp doctor --json` | **4 608 ms** median (4 608 / 4 830 / 4 316) | 3 × subprocess; spawns a server and does a full round trip |
| MCP cold start (spawn → `initialize` reply) | **2 015 ms** median (1 849 / 2 071 / 2 015) | raw newline JSON-RPC over stdio, 3 rounds |
| MCP spawn → 207 tools listed | **2 671 ms** median (2 357 / 2 708 / 2 671) | same |
| Per-tool-call latency | **10.7 ms** median, **307.9 ms** p95 | 23 MCP calls: most 2–40 ms; outliers `inspect_sqlite_database` 265 ms (worker), `binary_session` 95/72 ms |
| Peak RSS (server) | **391.2 MB** median (413 / 410 / 408 MB) | PSAPI `PeakWorkingSetSize` on the spawned `node rea.mjs mcp` |
| On-disk footprint | deployment **124.2 MB / 7 371 files**; `rea-agents` **27.3 MB / 1 775 files**; native addon 0.88 MB | `os.walk` |
| Network egress | install/audit: `registry.npmjs.org` only; **runtime: none** (0 outbound TCP across 3 sessions + 23 calls) | `netstat -ano` filtered by owning PID |
| Tool-call success rate | **17/25 = 68 %** protocol-level; **all 8 failures typed** (`capability_unavailable` ×3, `provider_unavailable` ×3, `target_unavailable` ×1, `unsupported_target` ×1); **0 crashes, 0 timeouts, 0 hangs** | both batteries + DSH-mediated calls |
| Expectation match (behaviour the test predicted) | 23/25 | 2 surprises: `inspect_binary_layout` is Linux-only (×2 calls), and `open_binary` accepts a PE with no provider (test predicted failure) |
| Server stderr | 0 bytes in every run | captured pipes |

Failure reasons, exhaustively: (1) Linux-only `inspect_binary_layout`; (2) no native analysis engine configured, which gates all decompile/overview/segment/string work; (3) REA's format model does not include plain-text source. None of these is a defect in the sense of a crash — each is a named, retry-inapplicable capability error.

**Cost model:** the server is a permanent ~391 MB RSS sidecar and adds ~2 s to DSH start-up (and, per DSH's transport design, a temporary *probe* process as well, so start-up can briefly cost two REA processes). In exchange the agent gains 207 tools; the schema payload alone is far larger than a typical session budget.

---

## 9. Verdict: **ADAPT**

**Why not ADOPT.** REA is a strong, well-engineered, provenance-clean package, but on *this* host its headline capability — "reverse engineer anything" — collapses to "inventory anything that is already a structured artefact". Every path to actual native reverse engineering is blocked by the absence of Ghidra/Hopper/IDA, and `inspect_binary_layout` does not work on Windows at all. ADOPT would imply the program can plan native-binary work around it, which it cannot.

**Why not STUDY_ONLY.** It is not a paper exercise: a real, hashed, CI-attested artefact registered with DSH in one config file, exposed 207 tools, and returned correct, reproducible Evidence for a .NET assembly, a PE resource tree, a SQLite database and a Rust PE — verified both through a standalone MCP client and **through the DSH agent itself**. That is deployable value today.

**Why not BLOCKED.** Nothing about the deployment was blocked. The only blocked *capabilities* are engine-dependent and are clearly named by the tool itself.

### ADAPT means, concretely

1. **Adopt the Evidence discipline, not the whole tool surface.** Borrow REA's result contract — `evidence_id`, artefact SHA-256, `coverage`, explicit `limitations`, and "absence is not proof" — as the model for how PHOENIX records artefact facts.
2. **Keep the deployment pinned and narrow.** `rea-agents@6.7.0` exactly (not `^6.7.0`), lockfile committed, native addon hash re-verified on every install, DSH registration limited to the `rea` namespace, `failOnStartupError: false`.
3. **Install an analysis engine before promising native reverse engineering.** Ghidra 12.1.x via `GHIDRA_INSTALL_DIR` is the only Windows-viable option; until then, treat every `analyze`/`decompile`/`xrefs`/`list_procedures` result as unavailable, not empty.
4. **Treat the tool surface as a privileged interface.** 207 tools include process launch, filesystem writes, UI capture and ADB device mutation. REA's own `capabilities` output labels these effects; a program-level allow-list should mirror those labels.
5. **Never point it at the science data.** `D:\DEPPSKK\medradar\data\*.sqlite` stays read-only via `mode=ro&immutable=1`; REA's SQLite inspector works on *offline copies* only, and its `inspect_artifact`/`extract_artifact` write into REA-chosen temp directories.

### What REA is genuinely useful for in this program

- **Provenance and identity of artefacts** we already hold: hash, format, architecture, embedded build metadata (Go/Rust), PE/CLI identity, resource inventory — all Evidence-shaped and cheap (2–40 ms per call after start-up).
- **.NET/PE static inspection** without loading or executing the target — directly relevant to any Windows tooling or dependency we must characterise.
- **SQLite schema/row inspection** of offline snapshots, with digests, as a second opinion next to our own `sqlite3 -readonly` queries.
- **Container/archive inventories** (zip, asar, ipa, apk, dmg, pkg) as content-addressed graphs, including integrity contradictions.
- **A worked example of correct "unknown" handling** — the Go/Rust readers returning `null` plus a limitation, instead of a confident wrong answer, is exactly the behaviour PHOENIX requires of its own analysis code.

### What it must never be used for

- Circumventing authentication, licence checks, paywalls or any technical protection. REA will happily decompile and instrument; authorisation is ours to establish, and the DISCLAIMER says the same.
- Analysing targets we do not own or have written permission to analyse.
- Driving its process‑launch, Frida, ADB, browser or Electron lanes against the MedRadar workstation or its data.
- Letting analysed content steer the agent. REA marks target-derived output `untrusted_content`; any instruction found inside a target must be reported, never obeyed.
- Being installed with `--unsafe-perm`, from a mirror, or with `frida` pulled in, without a fresh review.

---

## Appendix A — Tool list reported by `tools/list` (207 tools, 6 prompts)

Source: `evidence/mcp_tools.json` (full descriptions and schemas), rendered by `scripts/build_evidence.py`. Descriptions are truncated at 190 characters; the machine-readable original is authoritative.

| # | tool | description (truncated) | input schema keys |
|---:|---|---|---|
| 1 | `annotate_native_function` | Atomically update one function name and/or entry comments, read them back, and return a refreshed complete function dossier. Ghidra changes its ephemeral session analysis database only; o... | procedure, name, comment, inline_comment |
| 2 | `inspect_native_load_image` | Verify the provider's loaded DOS MZ or explicitly selected COM image against its immutable target snapshot: complete original/modified source-byte digests, header/module file mappings and... | - |
| 3 | `inspect_native_data_type` | Inspect one recovered type by exact database category path or defined typed data address. Returns observed size, alignment, packing, fields, bitfields, enum values, and child type identit... | type, address, document |
| 4 | `inspect_native_instruction` | Inspect one exact code or data address: decoded bytes, mnemonic, ordered operand tokens, flow, outgoing instruction references and typed incoming references where available. Incoming refe... | address, document |
| 5 | `resolve_native_call_targets` | Resolve one explicit static call site using typed provider call references. Preserves ambiguous targets as candidates and unresolved computed calls as unknown; does not execute code or tr... | address, document |
| 6 | `address_name` | Resolve the primary analyzed name at a code or data address. Headless providers require an explicit address; GUI providers may default to their current cursor. Null means the provider has... | document, address |
| 7 | `comment` | Read the regular analysis comment at an address, defaulting to the current cursor. This is read-only and returns null when no comment exists; use set_comment to persist a finding. | document, address |
| 8 | `current_address` | Return Hopper's current cursor address for the selected document. Use only for interactive navigation state; prefer explicit addresses in reproducible investigations. | document |
| 9 | `current_procedure` | Return the analyzed procedure containing Hopper's current cursor. This uses GUI cursor state and is not a procedure-name lookup. | document |
| 10 | `current_document` | Return the document currently selected by REA's Hopper bridge. | - |
| 11 | `goto_address` | Move Hopper's GUI cursor to a mapped address and return the observed cursor address. Interior coordinates snap to the containing analyzed object's start. Unmapped destinations fail withou... | address, document |
| 12 | `inline_comment` | Read the inline instruction comment at an address, defaulting to the current cursor. Returns null when absent; use set_inline_comment to write one. | document, address |
| 13 | `list_bookmarks` | List every bookmark in the selected Hopper document as address and name pairs; unnamed bookmarks retain a null name. Use bookmarks as analyst-authored navigation aids; this does not disco... | document |
| 14 | `list_documents` | List provider program or document identities. Hopper may expose several documents; a Ghidra headless session contains exactly its one imported Program. | - |
| 15 | `list_names` | List every analyzed memory and external symbol as address/value pairs. Provider metadata distinguishes Ghidra primary, dynamic, external, type, and source facts when available. | document, address |
| 16 | `list_procedures` | List every analyzed procedure as address/value pairs after provider analysis. Ghidra metadata distinguishes thunks and external functions; use returned addresses in later function operati... | document |
| 17 | `list_segments` | List segments or memory blocks using exclusive end addresses. Ghidra reports block permissions, address space, image base, initialization, and overlay facts; Hopper marks unavailable perm... | document |
| 18 | `list_strings` | List every provider-reported string object or candidate, or filter to one address, as address/value pairs with encoding, terminator status, and byte length when available. Hopper reads co... | document, address |
| 19 | `next_address` | Return the next analyzed object address after an explicit address or current cursor. This is a navigation primitive, not instruction-flow or CFG analysis. | document, address |
| 20 | `prev_address` | Return the previous analyzed object start before an explicit address or current cursor. This is a navigation primitive and may fail at document boundaries; data objects and instructions r... | document, address |
| 21 | `procedure_address` | Resolve an unambiguous procedure symbol name or provider-normalized address to its canonical entry address. External address spaces remain explicit. | procedure, document |
| 22 | `procedure_assembly` | Return assembly for one analyzed procedure identified by symbol or hexadecimal address. Use when pseudocode loses calling-convention or instruction-level detail; output is currently retur... | procedure, document |
| 23 | `procedure_callees` | Return the provider's resolved direct callees for one procedure identified by symbol or address. Unresolved indirect calls may be absent; use analyze_function and typed references to pres... | procedure, document |
| 24 | `procedure_callers` | Return the provider's resolved direct callers for one procedure identified by symbol or address. Results reflect completed static analysis and may omit unresolved indirect references. Ghi... | procedure, document |
| 25 | `procedure_info` | Return provider metadata for one procedure identified by symbol or address: entrypoint, signature, locals, size, block count, and complete inclusive body ranges when observed. Extents ref... | procedure, document |
| 26 | `read_function_instructions` | Return every raw instruction for one analyzed procedure. Instruction text and body extent are provider-specific. Ghidra terminal-call assumptions that may cut the analyzed body are report... | procedure, document |
| 27 | `search_bytes` | Find masked byte signatures in initialized analyzed memory. Hex byte pairs and ?? wildcards are supported; an optional equal-length hex mask selects bits. Bounds are inclusive. Matches ar... | pattern, mask, document, start, end, limit, cursor |
| 28 | `read_bytes` | Read analyzed bytes from one provider-normalized virtual address. The hexadecimal payload reports the exact returned length; incomplete reads remain explicit and unsupported provider APIs... | address, length, document |
| 29 | `address_to_file_offset` | Map one provider-normalized virtual address to its original nonnegative file offset. Hopper verifies the original bytes against the selected executable digest and translates FAT image-rel... | address, document |
| 30 | `procedure_references` | Return every raw incoming or outgoing reference edge for one procedure. Endpoint procedures are resolved only from provider containment. Ghidra preserves detailed reference flags. Hopper... | procedure, direction, document |
| 31 | `procedure_pseudo_code` | Decompile one analyzed procedure by symbol name or provider-normalized address. Ghidra also accepts file-offset:0x... selectors and falls back to a unique source-file mapping when a 0x-pr... | procedure, document |
| 32 | `resolve_containing_procedure` | Resolve an arbitrary address, including an interior instruction or exact external entry, to its provider-analyzed containing procedure. A negative result distinguishes outside segments fr... | address, document |
| 33 | `search_procedures` | Search every analyzed procedure name using literal matching by default or regex when requested. Results are deterministic and complete. Hopper regex mode uses ECMAScript Unicode syntax in... | pattern, mode, case_sensitive, document |
| 34 | `search_strings` | Search every provider-reported string object or candidate using literal matching by default or regex when requested. Results are deterministic and complete over that provider inventory, n... | pattern, mode, case_sensitive, document |
| 35 | `set_address_name` | Assign an analyst name to one mapped hexadecimal address and report whether the native edit succeeded and exact readback matched. Hopper rejects symbol names exceeding 1024 UTF-16 code un... | address, name, document |
| 36 | `set_addresses_names` | Assign analyst names to multiple mapped addresses in one call and return per-address edit/readback success booleans. Hopper validates mapped destinations, native string representations, i... | names, document |
| 37 | `set_bookmark` | Create or replace a bookmark at a mapped hexadecimal address and report success. This mutates navigation metadata; bookmarks are analyst-authored navigation aids, not binary evidence. | address, name, document |
| 38 | `set_comment` | Write a regular analysis comment at a hexadecimal address and return whether readback matched. An empty comment clears it. This mutates the Hopper document; use comments to record evidenc... | address, comment, document |
| 39 | `set_inline_comment` | Write an inline instruction comment at a hexadecimal address and return whether readback matched. An empty comment clears it; Hopper may flatten newlines, producing false on exact readbac... | address, comment, document |
| 40 | `unset_bookmark` | Remove the bookmark at a mapped hexadecimal address and return whether it is absent. Hopper also permits removing an existing legacy bookmark outside mapped memory. This mutates navigatio... | address, document |
| 41 | `xrefs` | Return analyzed references to a code or data address. Hopper may default to its current cursor; headless providers such as Ghidra require an explicit address. Use to connect strings, glob... | document, address |
| 42 | `trace_native_values` | Trace a bounded static dependency graph from one explicit native procedure. Includes high-p-code def-use, constants, operators, memory and branch operations, resolved call edges, and deri... | procedure, max_depth, max_functions, max_call_sites, max_nodes, max_edges, offset, limit |
| 43 | `inspect_native_dispatch_metadata` | Inspect the bound provider's name inventory for Objective-C class/method symbols and Swift mangled symbols, returning at most max_records decoded names. Includes target SHA-256 when avail... | max_records |
| 44 | `get_objc_classes` | Discover and deduplicate Objective-C class labels, optionally filtering by literal substring. | pattern |
| 45 | `get_objc_protocols` | Discover and deduplicate Objective-C and Swift protocol labels. | - |
| 46 | `batch_decompile` | Decompile each explicit procedure symbol or address concurrently. Preserves each input selector in address and reports the observed canonical entry and entry label in procedure; identity... | addresses |
| 47 | `get_call_graph` | Resolve one symbol or address to its canonical procedure entry, then traverse the bound provider's caller or callee relationships until the reachable graph is exhausted. Every node uses a... | address, direction |
| 48 | `analyze_swift_types` | Categorize analyzed Swift procedure names using their manglings or same-address Swift symbol aliases. Decodes legacy and literal modern nominal contexts into classes, structs, enums, prot... | category, pattern |
| 49 | `find_xrefs_to_name` | Resolve an exact name against the bound provider's name inventory and return a resolved or unresolved result. Unresolved names use the stable name_not_found reason; this xref workflow ret... | name |
| 50 | `binary_overview` | Return the bound document and exhaustive procedure/string counts, plus every segment and segment_count when the provider supports segment enumeration. If segment fields are omitted, segme... | - |
| 51 | `analyze_function` | Build a dossier for one native function identified by symbol or provider-returned address. Returns identity with complete inclusive analyzed body ranges or explicit unknown, provider-spec... | procedure |
| 52 | `inspect_native_api` | Analyze a native API boundary in one function identified by symbol or provider-returned address. Returns confidence, evidence, jump-table dispatch/data/case mappings, separately evidenced... | procedure |
| 53 | `trace_feature` | Trace the complete literal query, preserving spaces, through every matching string and procedure, their xrefs, and truthful containing-procedure resolution. Returns observations, operatio... | query, case_sensitive |
| 54 | `trace_call_path` | Resolve start and optional goal symbols or addresses to canonical procedure entries, then trace direct callers or callees until the graph is exhausted or the goal is reached. Results use... | start, goal, direction |
| 55 | `trace_native_ui_action` | Trace one unique compiled UI action, object ID, native symbol or exact function address through authored connections, encoded or symbolized Objective-C handlers, and bounded static call r... | action, max_depth, max_nodes, max_edges |
| 56 | `observe_native_ui` | Observe an already-running native app by PID and window ID, bound to the active Mach-O target. Captures a bounded accessibility tree and selected-window screenshot; OS permission denial f... | pid, window_id, screenshot, accessibility, max_nodes |
| 57 | `capture_native_ui_scenario` | Run selected-element press, increment/decrement scroll, AXValue text entry and bounded wait steps in one exact native app window. Returns ordered before/after captures and action/capture... | pid, window_id, screenshot, accessibility, max_nodes, steps |
| 58 | `observe_native_calls` | Launch the active Mach-O as an owned process under LLDB and record each entry into caller-selected functions or Objective-C methods: thread, module, symbol, load and file address, raw arg... | breakpoints, arguments, environment, working_directory, duration_ms, max_events, argument_registers, backtrace_frames |
| 59 | `inspect_macho` | Inspect Mach-O slices, load commands, imports, exports, dependencies, build metadata, segments, sections, permissions, and exact command provenance without launching Hopper. Large framewo... | detail |
| 60 | `inspect_signature` | Inspect the active Mach-O executable's code-signing identity, hashes, authorities, requirements, entitlements, hardened-runtime state, and exact command provenance. | - |
| 61 | `inspect_plist` | Parse Info.plist from the active artifact by default, or pass any local plist path. Returns normalized JSON rather than plutil text. | path |
| 62 | `list_architectures` | List thin or universal Mach-O slices with offsets, sizes, alignment, explicit coverage, and native-tool provenance. | - |
| 63 | `demangle_swift` | Demangle an ordered list of single-line Swift symbols without requiring Hopper. Each input returns demangled, unchanged, or invalid status. | symbols |
| 64 | `inspect_artifact` | Inspect an active archive or application package in one call. By default returns the complete content-addressed artifact graph once, as the typed nested inventory Evidence, with root and... | integrity_policy, detail |
| 65 | `extract_artifact` | Extract all regular files from the active archive or application package into a fresh temporary directory chosen by REA. The result includes its location. Rejects traversal and symlink es... | integrity_policy |
| 66 | `decode_interface_builder` | Decode compiled storyboard and nib archives inside the active Apple app bundle, including keyed property lists and NIBArchive object tables, into a bounded object, hierarchy, and connecti... | max_documents, max_objects, max_connections, detail |
| 67 | `inspect_keyed_archive` | Inspect one Foundation NSKeyedArchiver plist in the active app bundle as original object-table nodes, class descriptors, named roots, and UID edges. Preserves shared and cyclic references... | path, root, offset, limit |
| 68 | `inspect_asset_catalog` | Inspect compiled Assets.car metadata in an active Apple app bundle. Returns stable paginated catalog and rendition records with raw assetutil metadata and catalog digests; rendition bytes... | offset, limit |
| 69 | `trace_dylib_resolution` | Trace how dyld would resolve each Mach-O dylib load for the active Mach-O, or for every executable in the active .app bundle (the main app, XPC services, extensions, login items, helpers)... | roots, architecture |
| 70 | `inspect_managed_artifact` | Inspect an explicit PE/CLI path, or the selected managed target, without loading or executing target code. Omitted or complete detail returns complete metadata inventories with original c... | path, detail |
| 71 | `inspect_managed_members` | Inspect PE/CLI metadata members, signatures, raw CIL hashes, decoded-instruction-tuple hashes, separately reported exception regions, call edges, field-access anchors, and the #US string... | path, detail, type_names |
| 72 | `inspect_managed_native_boundaries` | Inspect PE/CLI ModuleRef, ImplMap/PInvoke declarations, CLI native-header indicators, and non-IL method implementation flags without loading or executing target code. Results are managed... | path |
| 73 | `compare_managed_members` | Compare two authenticated inspect_managed_members Evidence records using unique-only tiers: exact declared type, name, and CIL/signature; exact declared type, name, and signature (decoded... | left, right |
| 74 | `verify_managed_native_boundaries` | Verify managed P/Invoke/native-boundary declarations against authenticated native export or function Evidence without executing managed code or translating managed metadata tokens into na... | managed_boundaries, native_observations |
| 75 | `import_managed_reconstruction` | Import decompiler-produced managed reconstruction against authenticated inspect_managed_members Evidence. The workflow locks each method to artifact SHA-256, MVID, metadata token, signatu... | static_members, decompiler, methods, notes |
| 76 | `project_managed_application_graph` | Project authenticated managed artifact, member, and native-boundary Evidence into the provider-neutral application graph without executing managed code, loading assemblies, or translating... | managed_artifact, managed_members, managed_native_boundaries |
| 77 | `inspect_with_objdump` | Run caller-selected GNU objdump inspection against a local artifact, or request operation=architectures without a path to list BFD targets advertised by the installed binary. Preserves de... | path, operation, follow_debug_links |
| 78 | `execute_rizin_command` | Execute one caller-selected Rizin command against a local artifact using the Rizin CLI profile that suppresses user settings and scripts while retaining plugins. Preserves decoded stdout... | path, command |
| 79 | `list_frida_devices` | List Frida devices currently available to this host, optionally connecting to the caller-selected remote Frida endpoint. Remote authentication options are used for this call only and are... | remote |
| 80 | `list_frida_processes` | List processes observed on a selected Frida device or caller-supplied remote endpoint. A remote connection is closed after discovery; authentication values are never returned or recorded. | device_id, remote |
| 81 | `start_frida_session` | Attach Frida to one selected process or spawn one selected target. Spawned targets remain paused until resume_frida_session, allowing scripts to load before execution. Closing a session d... | mode, device_id, remote, pid, program, argv |
| 82 | `load_frida_script` | Load caller-supplied JavaScript into a Frida session. Scripts can read or change target memory and behavior and can access the target process's capabilities. Messages and script errors ar... | session_id, source_kind, source, path |
| 83 | `resume_frida_session` | Resume the process created by a paused Frida spawn session. Attached processes are already running and cannot be resumed through this operation. | session_id |
| 84 | `unload_frida_script` | Unload one caller-selected Frida script from a live session. This removes that script's instrumentation from the target. | session_id, script_id |
| 85 | `frida_session_status` | Return observed Frida session state and queued script messages. Message history is bounded by the provider capture budget and reports truncation. | session_id |
| 86 | `close_frida_session` | Unload session scripts and detach REA's Frida session. If a spawned process is still paused, resume it before detaching so it is not left suspended. REA never kills the target; its final... | session_id |
| 87 | `instrument_with_frida` | Run one caller-authored Frida script against an explicitly selected process and detach when the observation window ends. The CLI and MCP share this ephemeral workflow; use MCP session ope... | mode, device_id, remote, pid, program, argv, source_kind, source, path, duration_ms |
| 88 | `list_cutter_sessions` | List live REA bridge sessions hosted by upstream Cutter instances, including observed document identity and bridge-directory security status. Discovery admits at most 256 descriptor candi... | - |
| 89 | `cutter_command` | Run one arbitrary Rizin command in a selected live Cutter session. Commands may edit and persist analysis state or execute plugin-provided effects; completion uncertainty is returned as E... | session_id, expected_generation, command, json |
| 90 | `start_gdb_session` | Start a BYO GDB process in MI3 mode when available, suppress startup files, and disable auto-loading. Persistent GDB sessions are available only on Linux, where REA can verify live inferi... | inferior_tty |
| 91 | `gdb_console` | Run one unrestricted GDB CLI command through MI interpreter-exec console and return raw MI, console, target, and log records inline with Evidence. A command timeout preserves collected re... | session_id, command |
| 92 | `gdb_session_status` | Return the observed lifecycle state and bounded recent MI records and process diagnostics for one persistent REA GDB session; truncation and invalid-UTF-8 fields report discarded or lossy... | session_id |
| 93 | `close_gdb_session` | Close the owned GDB process after verifying the inferior state. When one live thread group has a verified durable output TTY, REA automatically detaches it, which may resume target execut... | session_id |
| 94 | `start_rizin_debug_session` | Start a persistent Rizin debugger session using `-N` to suppress user settings and scripts while retaining plugins, `-0` for NUL framing, and `-d` with an optional caller-selected IO debu... | path, inferior_tty, backend |
| 95 | `rizin_debug_command` | Execute one unrestricted command in a persistent Rizin debugger session. Returns raw output inline with Evidence, including backend output interleaved before the completion marker. If the... | session_id, command |
| 96 | `rizin_debug_session_status` | Return observed lifecycle state and bounded recent NUL-framed output and process diagnostics for one Rizin debugger session; truncation fields report discarded data, and output_invalid_ut... | session_id |
| 97 | `close_rizin_debug_session` | Close the REA-owned Rizin debugger only after verifying no inferior remains or detaching one with a verified caller-selected TTY output sink. A detached target may continue running and wr... | session_id |
| 98 | `inspect_packet_capture` | Inspect caller-selected fields in an existing local packet capture with TShark 4.x. Return 50 matching frames by default, with match_offset/match_limit paging and coverage counts; match_l... | path, fields, display_filter, decode_as, packet_limit, two_pass, match_offset, match_limit |
| 99 | `inspect_packet_fields` | Discover protocols or field names/types registered in the installed TShark 4.x. kind defaults to protocols; use fields and optional exact protocol abbreviation to select field definitions... | kind, protocol, query, offset, limit |
| 100 | `decode_signal_recording` | Decode an existing local logic/signal recording on Linux with sigrok-cli 0.7.2 and util-linux prlimit. Supply decoder stack, channels and options explicitly; optionally select input forma... | path, decoders, input_format, annotations, line_offset, line_limit |
| 101 | `inspect_signal_decoders` | Discover installed sigrok protocol decoders or inspect one decoder's channel/option help on Linux. Omit decoder to list ID/name pairs; supply its exact ID for literal help lines with sour... | decoder, query, offset, limit |
| 102 | `inspect_android_package` | Inspect a local APK's package, SDK and permission declarations, decoded manifest and class/resource counts. Omitted or complete detail preserves the complete result. Select detail: "summa... | path, detail |
| 103 | `search_android_classes` | Search complete top-level decompiler class-name rows in an explicit local APK by case-sensitive substring. Empty query inventories all rows. Repeated names remain repeated and appear in d... | path, query |
| 104 | `inspect_android_class` | Inspect one exact Android class's parsed methods, fields and inner classes, including synthetic members. Returns display signatures and exact DEX prototypes without generating source. A p... | path, class_name |
| 105 | `inspect_android_method` | Decompile one Android method with smali fallback. Requires explicit overload_index when multiple methods share a name. Reports its DEX prototype, representation, fallback markers and sour... | path, class_name, method_name, overload_index |
| 106 | `trace_android_references` | Trace incoming static using nodes to an exact Android class or selected method overload. The total counts containing nodes, not individual invoke instructions. Use inspect_android_class t... | path, class_name, method_name, overload_index |
| 107 | `inspect_jeb_client` | Inspect the running JEB client serving MCP: engine version, GUI or headless mode, and startup time. Does not open a target. Requires a caller-started JEB client reachable at REA_JEB_MCP_U... | - |
| 108 | `open_jeb_project` | Open or create a JEB project from an artifact file or existing .jdb2 database on the engine host. Returns the project's input-file digests and top-level units. The engine analyzes the tar... | path |
| 109 | `list_jeb_units` | List project units by stable unit path and type, with optional wildcard filter, parent restriction, and pagination. The engine caps pages at 100 units; a full page reports partial coverag... | filter, parent_unit_path, index, count |
| 110 | `decompile_jeb_item` | Decompile one type or method to engine pseudo-code using its decompiler (Dalvik, Java, or native). item_address comes from the engine's code item listing; unit_path defaults to the engine... | unit_path, item_address, item_kind |
| 111 | `inspect_binary_layout` | Inspect an explicit local binary without launching it as a host process. Returns file-backed section/segment ranges, linked addresses, original symbol/REL/RELA table identities, complete... | path, detail |
| 112 | `inspect_analysis_view` | Inspect selected views of completed binary-layout, JavaScript application, native analyze_function, inspect_artifact, inventory_artifact, inspect_wasm_artifact, inspect_macho, decode_inte... | source, view |
| 113 | `inspect_pe_resources` | Inspect one explicit local PE32/PE32+ image's complete bounded type/name/language resource tree without executing it or opening a disassembler. Returns numeric IDs versus original UTF-16... | path, max_file_bytes, max_entries |
| 114 | `inspect_go_binary` | Inspect embedded Go compiler version, main module, dependency/replacement versions and build settings in an explicit local ELF, PE or thin Mach-O image. Returns original artifact SHA-256,... | path |
| 115 | `inspect_rust_binary` | Inspect the cargo-auditable crate dependency list embedded in an explicit local ELF, PE or thin Mach-O image. Returns the artifact SHA-256, the .dep-v0 section file offset and size, compr... | path |
| 116 | `compare_wasm_interfaces` | Compare typed core WASM import/export names, kinds and exact signatures from two authenticated inspect_wasm_artifact Evidence records. Select imports, exports or both explicitly. Retained... | left, right, scope |
| 117 | `inspect_wasm_artifact` | Validate an explicit local WASM artifact with caller-supplied WABT 1.0.42. Omitted or complete detail returns exact byte SHA-256, sections, upstream import/export WAT forms and decoded WA... | path, glue_paths, candidate_paths, detail |
| 118 | `inspect_evm_interface` | Inspect explicit local flat EVM bytecode without target execution or chain/RPC access. Select raw or hex encoding explicitly. Omitted or complete detail returns original carrier and decod... | path, encoding, detail |
| 119 | `inspect_sqlite_database` | Inspect an explicit local SQLite database snapshot and its existing sibling WAL without modifying source files or opening a native analysis provider. Requires Node.js 24.x >=24.15 or 26+... | path, table, columns, schema_scope, row_limit |
| 120 | `inspect_recorded_crash` | Inspect a supplied Linux ELF64 amd64 or AArch64 little-endian core without launching its target or attaching to any live PID. Returns all recorded segments, raw note owners/descriptors an... | path, include_debugger_context |
| 121 | `inspect_firmware_regions` | Inspect signature candidates in a local firmware file with Binwalk 3.1.x (verified with 3.1.0). Returns offsets, reported lengths, descriptions and raw confidence values. Length validatio... | path |
| 122 | `extract_firmware` | Extract caller-selected firmware bytes with Unblob 26.6.x (verified with 26.6.4) into an absent output directory. Returns verified child paths/digests, task derivations, unknown chunks, e... | path, output_directory, range, max_depth, max_output_bytes, max_output_files |
| 123 | `trace_web_module_imports` | Trace one exported website script's outgoing native ES imports/re-exports, using exact URL and optional selected import-map context. Reads a local export_web_scripts manifest and verifies... | manifest_path, script_index, importer_url, import_map |
| 124 | `trace_web_source_location` | Trace one generated position in an exported website script through an explicitly paired local source map. Verifies manifest, selected script and map SHA-256/byte identities; returns every... | manifest_path, script_index, source_map, generated_position |
| 125 | `observe_web_execution` | Instrument one selected CDP page for a finite, externally driven precise coverage window. Resets execution counters and prevents optimized execution until stopped. Returns complete nested... | cdp_endpoint, allowed_origins, target_id, observation_ms |
| 126 | `inspect_web_event_listeners` | Inspect listeners registered directly on the first main-document CSS match in one selected CDP page. Returns event flags, native callback locations, source ownership and exact script text... | cdp_endpoint, allowed_origins, target_id, selector |
| 127 | `inspect_web_network_capture` | Request detail summary for capture identity and counts; then page retained records with inspect_analysis_view kind capture (preview or complete), avoiding repeated decoding. Default detai... | capture_path, format, record_ordinals, sensitive_values, detail |
| 128 | `recover_javascript_sources` | Recover readable modules from local UTF-8 JavaScript scripts/bundles into an absent directory, using caller-supplied Wakaru ^1.13.0 (verified with 1.14.0) on Linux x64. Use additional_pat... | path, additional_paths, output_directory, extraction_mode, rewrite_level |
| 129 | `inspect_adb_client` | Inspect the caller-selected adb client: resolved binary, version, and install path. Never contacts devices and never starts the adb server. REA never installs platform tools; select a bin... | - |
| 130 | `list_adb_devices` | List attached devices exactly as `adb devices -l` reports them: serial, state, transport, model metadata, and an inferred emulator/physical kind with its evidence basis. Emulators and USB... | - |
| 131 | `inspect_adb_device` | Inspect one device's build identity through a fixed `getprop` whitelist: Android and SDK versions, security patch, fingerprint, product identity, CPU ABIs, and debuggable flag, plus the o... | serial |
| 132 | `list_adb_packages` | List installed packages on one device with each base APK's device path, optionally scoped to third-party or system packages. Paths are device filesystem paths, not host-local. Read-only. | serial, scope |
| 133 | `pull_adb_package` | Pull one installed package's complete APK set (base plus every split, as `pm path` reports) from the device into a caller-selected output directory, creating a package-named subdirectory... | serial, package, output_directory |
| 134 | `read_adb_logcat` | Read a bounded dump of the device log (`logcat -d -t`) for one buffer, optionally restricted to a process id. No streaming, no clearing; the newest lines are kept when the count cap trims... | serial, count, buffer, pid |
| 135 | `inspect_adb_package` | Inspect one installed package through `dumpsys package`: version name/code, install and update times, installer, user id, flags, and the requested-permission count. A fixed projection of... | serial, package |
| 136 | `pull_adb_file` | Pull one absolute device path (a database, shared-preferences XML, or any readable file) into a caller-selected output directory, digesting it with SHA-256. The local copy must not alread... | serial, device_path, output_directory |
| 137 | `push_adb_file` | Push one local file to an absolute device path. A device-mutating tool: checks for an existing device file before transfer and refuses it unless overwrite is explicitly requested; this ch... | serial, local_path, device_path, overwrite |
| 138 | `capture_adb_screen` | Capture one frame of the device screen as a PNG (`screencap -p` through exec-out, no device-side file) into a caller-selected output directory, digesting it and reporting its dimensions.... | serial, output_directory |
| 139 | `list_adb_processes` | List running processes exactly as `ps -A` reports them: user, pid, ppid, rss, state, and name. Useful for pairing with instrumentation lanes. Read-only. | serial |
| 140 | `list_adb_directory` | List the immediate children of one absolute device directory, including hidden entries: names, kinds, permissions, owner, group, sizes, dates, and symlink targets. Names and targets prese... | serial, device_path |
| 141 | `list_adb_features` | List the device's declared hardware and software features (`pm list features`) for device fingerprinting. Read-only. | serial |
| 142 | `list_adb_services` | List the device's binder services with their interfaces (`service list`). Read-only. | serial |
| 143 | `inspect_adb_display` | Report the display's physical and any overridden size (`wm size`) and density (`wm density`) as the device declares them. Read-only; setting values is not exposed. | serial |
| 144 | `inspect_adb_window` | Report the window manager's focus declarations with display context, original lines and explicit summary status. Reads `dumpsys window windows`, falling back to `displays` only when no fo... | serial |
| 145 | `read_adb_setting` | Read one settings value (`settings get`) from the system, secure, or global namespace. Absent keys report the device's own null observation. Read-only; writing settings is not exposed. | serial, namespace, key |
| 146 | `collect_adb_bugreport` | Collect one device-generated bugreport archive (`adb bugreport`) into a caller-selected output directory, digesting the zip. The archive contains the device's own dumpstate, dumpsys, and... | serial, output_directory |
| 147 | `resolve_adb_packages` | Find installed packages by case-insensitive substring of the package name (e.g. `whatsapp` → `com.whatsapp`), returning each match's base APK device path. The first step of an easy get: r... | serial, query |
| 148 | `install_adb_package` | Install one local APK on the device (`adb install [-r]`), recording the APK's host digest and byte size. A device-mutating tool: `replace_requested` records whether `-r` was selected; `re... | serial, apk_path, replace |
| 149 | `uninstall_adb_package` | Request package removal for user 0 (`adb shell pm uninstall --user 0`) without data retention. A device-mutating tool; absent packages report the device's own refusal reason. | serial, package |
| 150 | `start_adb_app` | Start one installed app's resolved launcher activity with `am start -W -n`. A device-mutating tool for dynamic analysis. The full wait report determines success; failures retain launch-at... | serial, package |
| 151 | `start_adb_activity` | Start an intent with `am start -W`: one action, optional data URI, optional explicit component, and up to 16 typed extras (string, boolean, int, long, float). A device-mutating tool; the... | serial, action, data_uri, component, extras |
| 152 | `stop_adb_app` | Force-stop every process of one package (`am force-stop`), ending a dynamic-analysis run. A device-mutating tool; it succeeds whether or not the package had running processes. | serial, package |
| 153 | `inspect_pcap_client` | Inspect the caller-selected tshark and capinfos binaries: selected commands, selection sources, and versions. Both tools must be usable. Reads no capture file. REA never installs the Wire... | - |
| 154 | `inspect_pcap_capture` | Request detail summary for capture identity/counts, then page retained facts with inspect_analysis_view kind pcap. Default detail complete preserves inline delivery. Inspect one saved pca... | path, detail |
| 155 | `identify_flutter_build` | Identify a Flutter app's build facts by pure parsing: the Dart VM snapshot hash from every lib/<abi>/libapp.so AOT section (vm and isolate, cross-checked), per-ABI library digests, the en... | path |
| 156 | `inspect_dart_aot` | Inspect one ABI's Dart AOT snapshot inside an APK: the four snapshot symbols located through the ELF dynamic symbol table with their offsets, sizes, and section headers (magic, kind, leng... | path, abi, detail |
| 157 | `inspect_apktool_client` | Inspect the caller-selected apktool launcher: resolved command, selection source, and version. Decodes nothing. REA never installs Apktool or Java; select a launcher with REA_APKTOOL_COMM... | - |
| 158 | `decode_android_resources` | Decode one local APK's resources with `apktool d --no-src` in a provider-owned workspace that is removed after projection: the readable AndroidManifest.xml, apktool.yml version and SDK fa... | path, include_strings, locale, locales |
| 159 | `export_web_scripts` | Export JavaScript bytes already retained in one local inspect_web_page or capture_browser_scenario JSON capture (normalized result or complete Evidence). Writes scripts and a digest-verif... | capture_path, output_directory |
| 160 | `list_browser_targets` | List page targets exposed by the selected loopback Chrome DevTools Protocol endpoint. Optionally filter by exact origin. URLs preserve query values and fragments; only URL userinfo creden... | cdp_endpoint, allowed_origins |
| 161 | `inspect_web_page` | Passively inspect one selected page target through CDP without evaluating JavaScript, navigating, clicking, closing, or mutating the page. If no origin filter is supplied, capture is scop... | cdp_endpoint, allowed_origins, target_id, observation_ms, include_accessibility_text, include_console_text, include_json_body_shapes, include_websocket_shapes, include_storage_keys, include_storage_fingerprints, include_script_sources |
| 162 | `analyze_web_bundle` | Capture JavaScript source from one selected CDP page and statically derive a chunk graph, route and endpoint candidates, vendor fingerprints, page-declared WebMCP metadata, and optionally... | cdp_endpoint, allowed_origins, target_id, observation_ms, include_accessibility_text, include_console_text, include_json_body_shapes, include_websocket_shapes, include_storage_keys, include_storage_fingerprints, include_script_sources, fetch_source_maps |
| 163 | `observe_web_session` | Arm a CDP observation window of the requested duration while the user operates the page. By default it follows the selected target's current origin; an explicit origin list controls which... | cdp_endpoint, allowed_origins, target_id, observation_ms |
| 164 | `discover_webmcp_tools` | Passively inventory every page-registered WebMCP tool and its complete structural input-schema summary using the experimental CDP WebMCP domain. Metadata is page-declared-untrusted; REA n... | cdp_endpoint, allowed_origins, target_id, observation_ms |
| 165 | `compare_web_captures` | Compare passive web captures by providing before and after, each with the complete inspect_web_page normalized_result in inspection and an optional complete discover_webmcp_tools normaliz... | before, after, before_scenario, after_scenario, normalization |
| 166 | `capture_web_screenshot` | Capture the current visible viewport of one configured page as an inline, content-addressed PNG artifact. The operation never scrolls, navigates, or evaluates page JavaScript. | cdp_endpoint, allowed_origins, target_id |
| 167 | `compare_web_screenshots` | Compare two self-verifying PNG screenshot artifacts with local pixel metrics. Returns exact changed-pixel ratios and channel deltas without OCR or external services. | before, after, channel_threshold |
| 168 | `capture_browser_scenario` | Run a controlled browser scenario when passive observation cannot exercise the application. Launch the selected executable or connect to a loopback CDP target, provide a start URL and act... | browser, start_url, environment, actions, storage, secrets, capture |
| 169 | `inspect_electron_fuses` | Inspect packaged Electron fuse bytes in one local macOS app bundle, Electron Framework binary, Windows PE executable, or Linux ELF executable. Returns the artifact digest, per-slice wire... | path |
| 170 | `list_electron_targets` | List every Electron file:// page target from a selected loopback CDP endpoint. Local file paths are canonicalized after symlink resolution. Selecting an endpoint exposes every eligible ta... | cdp_endpoint |
| 171 | `inspect_electron_page` | Passively inspect one Electron file page by supplying its loopback CDP endpoint and target ID. The provider rechecks that the target currently exists at that endpoint and is a local file... | cdp_endpoint, target_id, observation_ms, include_script_sources |
| 172 | `analyze_javascript_application` | Reconstruct one local ASAR or extracted JavaScript application as an inline application graph without executing it. Returns recovered graph nodes, edges, semantic relations, integrity con... | input_path, format, integrity_policy, source_paths, max_semantic_nodes, max_semantic_nodes_per_file, max_semantic_unknowns, max_semantic_unknowns_per_file, max_heap_mb, analysis_timeout_ms, detail |
| 173 | `reconcile_javascript_runtime` | Reconcile verified static JavaScript application graphs with existing passive web/Electron CDP, passive V8 Inspector, or provider-owned active Electron Evidence. Active Electron captures... | static_layers, runtime_observations |
| 174 | `capture_electron_scenario` | Use this for a provider-owned Electron run when passive CDP or Inspector observation cannot exercise application behavior. REA owns startup and teardown, accepts caller-defined click/wait... | executable_path, application_path, application_root, args, actions |
| 175 | `list_javascript_runtime_targets` | List every eligible Node/Electron V8 Inspector target from an explicit literal-loopback endpoint. Node discovery file locations that cannot be verified are preserved as unresolved reporte... | inspector_endpoint |
| 176 | `observe_javascript_runtime` | Attach passively to one Node/Electron V8 Inspector target by supplying its loopback Inspector endpoint and target ID. The provider rechecks target presence and attachability; a Node disco... | inspector_endpoint, target_id, runtime_kind, observation_ms |
| 177 | `trace_application_feature` | Trace a typed literal seed through every reachable part of an authenticated JavaScript Application Graph supplied as inline Evidence or exact same-session retained references. Original st... | native_observations, seed, direction, application |
| 178 | `trace_javascript_semantics` | Trace static JavaScript data-flow, direct call/return, and closure relations from inline application Evidence or an exact same-session retained reference. Dynamic or unsupported semantics... | application, query |
| 179 | `compare_application_versions` | Compare two authenticated JavaScript Application Graph versions supplied as inline Evidence or exact same-session retained references. Uses unique-only exact digest, module source digest,... | left_native_observations, right_native_observations, left, right |
| 180 | `compare_source_to_bundle` | Compare a cryptographically committed HistoricalSourceGraph with authenticated JavaScript Application Graph Evidence supplied inline or by exact same-session retained reference. Uses expl... | reference, application |
| 181 | `compare_javascript_export_shapes` | Compare static return shapes for one exact module/export selector on each authenticated JavaScript Application Graph supplied as inline Evidence or exact same-session retained references.... | left_module_path, left_export_name, right_module_path, right_export_name, left, right |
| 182 | `build_reconstruction_obligation_ledger` | Generate the complete deterministic ReconstructionObligationLedger from an authenticated Evidence bundle, reviewed obligations, and an explicit reconstruction manifest. Static candidates... | evidence_bundle, reviewed_obligations, manifest |
| 183 | `evaluate_reconstruction_coverage` | Evaluate inline evidence-backed reconstruction coverage against one named boundary. Missing ownership or inventory is partial; stale, weak, truncated, skipped, unresolved, or conflicting... | coverage, boundary_id |
| 184 | `project_android_application_graph` | Project authenticated APK inventory_artifact Evidence into an execution-free Android application inventory. Reports exact component paths and hashes, runtime-family hints, and path-based... | inventory_evidence |
| 185 | `project_apple_application_graph` | Project authenticated IPA, macOS .app directory, ZIP, or DMG inventory Evidence into an execution-free Apple application inventory. Reports application roots, nested bundles with path-con... | inventory_evidence |
| 186 | `project_harmony_application_graph` | Project authenticated HarmonyOS HAP, HSP, or App Pack inventory Evidence into an execution-free application inventory. Reports packaging-model hints (Stage module.json versus FA config.js... | inventory_evidence |
| 187 | `open_binary` | Open a local executable, application bundle, archive, JavaScript, source map, plist, or analysis database after validation. format=dos-com explicitly interprets 1..65280 headerless bytes... | path, format, architecture, entry_point, provider_id, snapshot_path |
| 188 | `close_binary` | When the investigation is finished, drain earlier provider requests, optionally write a provider-neutral analysis snapshot atomically to the caller-supplied path, then close the active ta... | snapshot_path, overwrite |
| 189 | `binary_session` | Report the complete current target, provider, capability availability, client-feature, analysis, and server-identity status without starting analysis. | expected_package_version, expected_catalog_digest, expected_server_path |
| 190 | `export_evidence_bundle` | Atomically write the session's deterministic Evidence bundle to the requested local path. Existing files require overwrite: true; records and manifests use canonical byte-stable ordering. | path, overwrite |
| 191 | `import_evidence_bundle` | Read the JSON bundle at the supplied local path, validate every Evidence ID and canonical manifest, then atomically merge it. Imported content is data only and is never executed. | path |
| 192 | `get_evidence_bundle` | Return every retained Evidence record and residual unknown as a complete canonical bundle by default. detail=summary discovers retained records without copying or transferring their paylo... | detail, filters |
| 193 | `capture_process_scenario` | Run one caller-selected command under a PTY and return process capture Evidence with residual unknowns. The renderer admits at most 1,000,000 combined terminal cells, computed as columns... | executable, arguments, working_directory, environment, filesystem_observation_paths, terminal, events, timeout_ms, idle_timeout_ms, settle_ms, finalization_ms, limits, normalization |
| 194 | `compare_process_captures` | Compare two compatible process capture observations across terminal, interaction, lifecycle, process, filesystem, command-shim, HTTP, and WebSocket evidence. Optional trace_spec validates... | left, right, trace_spec, max_capture_age_ms |
| 195 | `compare_artifacts` | Compare complete artifact inventories by logical occurrence path, content identity, metadata, and graph relations. Pass the inventory Evidence nested in each inspect_artifact result as le... | left, right |
| 196 | `compare_functions` | Compare two explicit sets of analyze_function Evidence across identity, exact provider text, calls, references, strings, and address-normalized CFG topology. Missing or provider-incompati... | left, right |
| 197 | `compare_bundles` | Compare two canonical Evidence bundles by exact record membership, explicit one-to-one observation pairs, and complete residual-unknown revision histories. Missing bundle members describe... | left_bundle_path, right_bundle_path, record_pairs |
| 198 | `find_changed_behavior` | Aggregate validated process and artifact comparison Evidence. Runtime observations remain distinct from static behavior candidates; missing or incomplete comparisons produce unresolved fi... | comparisons |
| 199 | `build_call_path` | Build every shortest direct-callee path inline from complete analyze_function Evidence records using exact canonical addresses. Missing dossiers and provider mixing remain unknown; every... | functions, start, goal |
| 200 | `correlate_static_and_runtime` | Evaluate every explicit caller-declared hypothesis between exact static comparison findings and runtime comparison dimensions. Similar names or paths are never auto-matched, consistent co... | static_comparisons, runtime_comparisons, mappings |
| 201 | `verify_reconstruction` | Verify a finite typed behavioral and structural specification against a canonical Evidence bundle. Pass means every declared claim has complete comparable authority—not global source equi... | specification |
| 202 | `list_unknowns` | List current residual-unknown heads in deterministic ID order, with optional exact status, severity, and domain filters. Results are complete inline by default; supply offset and limit to... | status, severity, domain, offset, limit |
| 203 | `record_unknown` | Create one deterministic residual unknown and immutable mutation evidence. Validates all evidence and relationship references, and rejects duplicate stable identity. | question, severity, domain, comparison_conclusion_scope, required_authority, required_confidence, required_environment, recommended_probes, relationships, supporting_evidence_ids, contradicting_evidence_ids |
| 204 | `update_unknown` | Append one immutable full-state revision and mutation evidence. Requires exact expected_revision; stale concurrent writers fail instead of overwriting newer analysis. | unknown_id, expected_revision, status, severity, supporting_evidence_ids, contradicting_evidence_ids, required_authority, required_confidence, required_environment, recommended_probes, relationships, resolution |
| 205 | `verify_unknown_resolution` | Revalidate the current residual-unknown head against live bundled evidence, exact authority/confidence/environment requirements, and revision integrity. Withdrawn and out-of-scope disposi... | unknown_id |
| 206 | `get_navigation_context` | Return the selected document, current address, and containing/current procedure in one provider-neutral result. The result reflects sequential provider observations, not an atomic cursor... | document |
| 207 | `inspect_address_context` | Inspect one explicit reproducible address for its analyzed name, containing procedure, regular and inline comments, and matching bookmarks. Each unsupported facet returns a typed unavaila... | address, document |


Prompt names (6): see `evidence/mcp_tools.json → inventory.prompts`.

---

## Appendix B — Files written by this validation

| Path (under `medradar/`) | Purpose |
|---|---|
| `docs/phoenix/REA_VALIDATION.md` | this report |
| `experiments/phoenix/rea/fixtures/sample.py`, `sample.cs`, `sample.rs`, `make_sqlite.py` | harmless fixtures |
| `experiments/phoenix/rea/fixtures/build/{sample-native.exe,sample-managed.exe,sample-native.pdb,sample-bundle.zip}` | compiled fixtures |
| `experiments/phoenix/rea/fixtures/sample.sqlite` | SQLite fixture |
| `experiments/phoenix/rea/scripts/mcp_probe.mjs` | official-SDK MCP inventory |
| `experiments/phoenix/rea/scripts/mcp_battery.mjs` | 14-call static battery |
| `experiments/phoenix/rea/scripts/mcp_battery_session.mjs` | 9-call session/provider battery |
| `experiments/phoenix/rea/scripts/measure_runtime.py` | latency + peak-RSS + netstat harness |
| `experiments/phoenix/rea/scripts/build_evidence.py` | evidence aggregation + appendix renderer |
| `experiments/phoenix/rea/scripts/validate_dsh_patch.mjs` | strict YAML validation of the DSH patch |
| `experiments/phoenix/rea/evidence/rea_evidence.json` | machine-readable results |
| `experiments/phoenix/rea/evidence/mcp_tools.json` | 207 tools + 6 prompts, full schemas |
| `experiments/phoenix/rea/evidence/mcp_battery.json`, `mcp_battery_session.json` | per-call records |
| `experiments/phoenix/rea/evidence/runtime_metrics.json` | 3-round timings + RSS + TCP |
| `experiments/phoenix/rea/evidence/dsh_cordis.patch.yml` | verbatim copy = rollback backup |
| `experiments/phoenix/rea/evidence/tool_catalog_appendix.md` | rendered appendix |
| `experiments/phoenix/rea/logs/*` | raw `--help`, `doctor`, `mcp doctor`, native-verify, CLI runs, attestation, npm views |

Outside the repo, one file was created (authorised deployment, reversible):

| Path | Change | Rollback |
|---|---|---|
| `C:\Users\yjx0\.dsh\cordis.patch.yml` | **created** (home Cordis layer, `rea-mcp` insert) | delete the file |
