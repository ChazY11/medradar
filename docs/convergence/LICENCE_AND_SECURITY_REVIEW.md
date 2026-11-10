# LICENCE AND SECURITY REVIEW (P0-C)

**Task:** `task-3` — data licence, secrets and public-repository exposure audit
**Branch audited:** `integration/convergence-001` @ `3c3a295`
**Upstream heads audited:** `research/horizon-001` (PR #29) @ `2dcdc99`, `foundation/atlas-001` (PR #28) @ `c636836`, `main` @ `b2a14c0`
**Repository:** `https://github.com/ChazY11/medradar.git` (public)
**Audit date:** 2026-11-11 (Asia/Shanghai)
**Owner of this document:** `licence-auditor`
**Status:** complete. **Nothing in this audit has been executed against history, credentials or remote state.** Every remediation below requires the repository owner's explicit authorisation.

---

## 0. Executive summary

| Question | Answer |
|---|---|
| How many export sources are materialised? | **24** sources, **6,492** records, **20,335,003** B declared in `MANIFEST.json` |
| How many are redistribution-blocked? | **1** — `un_comtrade` (608 records of 6,492; 9.4 %) |
| Is the restricted payload on `integration/convergence-001`? | **No.** 0 of 30 quarantined paths; the export gate exits **0 (PASS)** |
| Is it on PR #29's public branch? | **Yes.** 30 paths, **29 distinct blobs, 6,234,301 B**, introduced by one commit `18a7580`, reachable from `origin/research/horizon-001` (pushed) |
| Any credentials committed? | **None found.** 1,838 blobs across 4 refs scanned; every high/critical hit triaged to a documented placeholder, a public client-side widget key, or a runtime lookup |
| Any patient data / private-individual PII? | **No patient data.** Named professional contact details (name + work email/phone) of study contacts, authors and public-sector buyers are vendored inside published source snapshots — **248 distinct UK procurement contacts** are the largest concentration. Disclosed and remediable |
| Does the integration branch need the restricted data? | **No.** The 23 permitted sources carry **5,884 records** and exercise every stage of the pipeline (§11) |
| What needs owner authorisation? | (1) any history rewrite / force-push / branch deletion, (2) contacting GitHub support, (3) credential rotation, (4) the decision to keep or strip the derived Comtrade figures (§10) |

**Two findings that are not fixed by the UN Comtrade quarantine:**

1. **Derived UN Comtrade figures survive in two retained files** — `research/horizon/reports/INDUSTRY_DATA_REPORT.md` (5 annual cells + the exact Germany-2023 cell, lines 82–88 and 127) and `research/horizon/experiments/industry/EXP_H4_INDUSTRY.json` (`/cross_checks/de_9018_imports_2023/comtrade_usd = 13359445208.517`). The payload files are gone; these derivative figures are not. Owner decision required (§10.4).
2. **Named-individual contact data is vendored on the integration branch** — 3 raw OCDS packages under `research/horizon/DATASETS/industry/uk_find_a_tender/raw/` carry 415 occurrences of 248 distinct named buyers' work emails. The derived export (`uk_find_a_tender.jsonl`, 62 records) carries **zero** emails, so the raw packages are not needed for the pipeline.

---

## 1. Method and artefacts

All Git work was **read-only** (`log`, `show`, `ls-tree`, `rev-list`, `cat-file`, `branch --contains`, `ls-remote`). No branch, index, object or remote was modified. No commit was created. Live network access was confined to four public documentation pages (§3.1); no restricted data was fetched, no account was created, no credential was used.

| Artefact | Purpose |
|---|---|
| `config/convergence/licence_policy.json` | **Authoritative machine-readable gate**, 51 sources |
| `tools/convergence/licence/licence_gate.py` | Export-directory gate (`check_export()` + CLI) |
| `tools/convergence/licence/build_policy.py` | Regenerates the policy from the registry + the audited decision table |
| `tools/convergence/licence/secrets_scan.py` | Committed-blob secrets/PII scanner (ref-based) |
| `tools/convergence/licence/exposure_report.py` | Git-history exposure quantity for the quarantined paths |
| `research/convergence/licence/gate_integration_branch.json` | Gate run on the integration worktree — **PASS, exit 0** |
| `research/convergence/licence/gate_pr29_worktree.json` | Gate run on the PR #29 worktree — **FAIL, exit 1** |
| `research/convergence/licence/pr29_exposure.json` | Per-path blob OIDs, sizes, introducing commit, reachability |
| `research/convergence/licence/secrets_scan.json` | Full secrets/PII scan report |

Reproduce:

```powershell
python tools\convergence\licence\build_policy.py --repo . --out config/convergence/licence_policy.json
python tools\convergence\licence\licence_gate.py --export-dir research\horizon\exports\horizon-2026-11-10 `
    --policy config\convergence\licence_policy.json --repo . `
    --json-out research\convergence\licence\gate_integration_branch.json
python tools\convergence\licence\secrets_scan.py --repo D:\path\to\repo `
    --ref integration/convergence-001 --ref research/horizon-001 `
    --ref foundation/atlas-001 --ref main `
    --out research\convergence\licence\secrets_scan.json --fail-on critical
python tools\convergence\licence\exposure_report.py --repo D:\path\to\repo `
    --payload-ref research/horizon-001 --check-ref integration/convergence-001 `
    --paths-from config\convergence\licence_policy.json `
    --out research\convergence\licence\pr29_exposure.json
```

---

## 2. The rights model used throughout

Three distinct rights are tracked separately, because conflating them is the standard way a "public API" argument becomes an unjustified redistribution claim:

| Right | Field | Question it answers |
|---|---|---|
| Query | `may_query` | May the pipeline make automated requests to the published endpoint? |
| Ingest + analyse | `may_ingest`, `may_analyse_locally` | May the fetched bytes be stored and analysed locally? |
| Redistribute | `may_redistribute` | May the materialised/derived records be **committed to this public repository**? |

`config/convergence/licence_policy.json` carries these per source, together with `redistribution_condition`, `attribution_required`, `attribution_text`, `evidence_url`, `checked_at` and `verification`. A source with `may_redistribute=false` is *quarantined*: the gate fails if its payload is committed and passes if it is absent.

**The governing rule of this audit:** *"it came from a public API" establishes at most the right to query.* It does not establish the right to redistribute. Every verdict below is derived from the publisher's own written terms, not from the mechanics of access.

---

## 3. The UN Comtrade restriction — what is actually permitted

### 3.1 The two instruments, and their conflict

| # | Instrument | URL | Retrieved | Status |
|---|---|---|---|---|
| **A** | UN Comtrade **API documentation** (the access/query instrument) | `https://comtradeplus.un.org/en/api-docs` | 2026-11-11 (this audit) | HTTP 200 |
| **B** | UN Comtrade **License agreement / Usage Agreement** (the reuse instrument) | `https://comtradeplus.un.org/en/license-agreement` | 2026-11-11 (this audit) | HTTP 200 |

**Instrument A — the right to query, quoted verbatim:**

> "The public API needs no key. The others need a subscription key, free with any account, from My API portal."
>
> "### Public API — Free API to preview trade data. Results are limited to 500 records. No subscription key required."
>
> "This one needs no key: open it in your browser, **or call it from your program**."

Instrument A therefore expressly invites programmatic, automated, keyless retrieval of bounded previews. That is a genuine grant of the *query* right, and it is why HORIZON's acquisition was not a rogue scrape.

**Instrument B — the redistribution prohibition, quoted verbatim (§5 "Usage"):**

> "United Nations COMTRADE contains copyrighted material and/or other proprietary information. The materials contained on or otherwise made available to you on United Nations COMTRADE may be copyrighted by the United Nations and, thus, are protected by copyright laws and regulations worldwide. **Except as may otherwise be expressly permitted by applicable law, any copying, automated browsing or downloading, redistribution, publication, or commercial exploitation of any material contained on or otherwise made available to you on United Nations COMTRADE is strictly prohibited without the prior written permission of the United Nations.** Any requests for permission to reproduce or otherwise use any material … should be directed to The Director of the United Nations Statistics Division: comtrade[at]un.org"

Also note the preamble, which binds **non-subscribers**:

> "By subscribing to the United Nations COMTRADE **or using UN Comtrade without subscription**, you are agreeing to abide by all of the following terms and conditions…"

### 3.2 Verdict, right by right

| Right | Verdict | Basis |
|---|---|---|
| **Query** | **Permitted** for the keyless public preview API | Instrument A expressly documents and demonstrates programmatic calls ("call it from your program", no key, ≤500 rows). Instrument B's "automated browsing or downloading" is read as aimed at bulk/systematic extraction of the site, and is displaced for the preview path by Instrument A's specific invitation. **This is the conflict, and it is genuine.** |
| **Local analysis** | **Permitted** as an incident of permitted querying | The API returns data for the caller to use; a bounded sample is analysed locally. Nothing in Instrument A restricts it. |
| **Redistribution / publication** | **PROHIBITED** without prior written permission | Instrument B §5 names "redistribution" and "publication" explicitly. No instrument grants it. Instrument A says nothing about reuse. |
| **Commercial exploitation** | **PROHIBITED** without prior written permission | Instrument B §5, same sentence. |
| **Attribution** | **Necessary but insufficient** | Instrument B §5 further forbids altering or removing "any copyright symbol or other identification or any information concerning authorship". Attribution does not cure the redistribution prohibition. |
| **Written permission route** | The Director, UN Statistics Division (`comtrade@un.org`) | Instrument B §5. A licensed/marketplace subscription is a separate commercial route, not a reuse licence. |

**Consequence for this repository:** committing `un_comtrade.jsonl` (608 trade records) to a public repository is a redistribution of UN Comtrade material without written permission. The export was taken under Instrument A; publishing it relies on Instrument B, which forbids it. **This is the finding, and it is not cured by the API being public.**

Caveat worth stating honestly: §5 opens with *"Except as may otherwise be expressly permitted by applicable law"*. A statutory text-and-data-mining or fair-dealing exception could in principle cover *analysis*; no such exception covers standing up a permanent public mirror of 608 records. We do not rely on it.

### 3.3 Divergence between HORIZON's own `licence_note` and the archived terms

HORIZON's registry entry `research/horizon/registry/sources/un_comtrade.json` states:

> `"licence_note": "UN Comtrade Usage Agreement §5: 'any copying, automated browsing or downloading, redistribution, publication, or commercial exploitation of any material contained on or otherwise made available to you on United Nations COMTRADE is strictly prohibited without the prior written permission of the United Nations.' The keyless preview API is published for programmatic access, so the two instruments conflict; HORIZON-001 treats operational reuse as requiring written permission."`

| Check | Finding |
|---|---|
| Is the quoted clause accurate? | **Yes, verbatim**, except that the leading qualifier *"Except as may otherwise be expressly permitted by applicable law,"* is dropped, which slightly overstates the absolute character of the ban. `licence_status: terms_restricted` is the correct classification. |
| Does the registry call the conflict correctly? | **Yes.** It names the conflict and does not resolve it by assertion. This audit reaches the same conclusion with a sharper split: query+analysis defensible, redistribution not. |
| **Evidence-integrity gap** | `research/horizon/DATASETS/industry/LICENCE_EVIDENCE.json → by_source.un_comtrade` registers only **two pages, both HTTP 404** (`/TermsOfUse` 36,681 B and `https://comtradeapi.un.org/` 54 B) with `"sentences": []`. **It does not register `comtrade_license.html`**, the one file that actually contains §5. The strongest licence evidence in the repository is therefore *not linked from the machine-readable evidence index*, and a reviewer checking only `LICENCE_EVIDENCE.json` would find zero quoted clauses for the one restricted source. **Fix recommended (low risk, docs only):** add `comtrade_license.html` with its URL, SHA-256 and the §5 sentences to `LICENCE_EVIDENCE.json`. |
| Stale-content risk | The archived `terms_of_use.html` is a **404 page** ("Error 404 — This page has sailed off course"), not terms of use. It is retained and shipped to readers as if it were the terms page. It should be relabelled as a negative probe result. |
| Has the live text changed since the archive? | **No.** The 2026-11-11 live fetch of `/en/license-agreement` is **word-for-word identical** to the archived `comtrade_license.html` (SHA-256 `030990afc459a04114386610815986dbaa64e7fd41b30929f65b8059601e32ca`, 50,778 B). The only differences are cosmetic: the URL moved from `/LicenseAgreement` to `/en/license-agreement`, and the site serves the contact address base64-obfuscated (`Z3JvLm51QGVkYXJ0bW9j` = `gro.nu@edartmoc` reversed = `comtrade@un.org`). |

### 3.4 Rights conclusion for the record

- **May HORIZON query UN Comtrade?** Yes — the public preview API is published for exactly that.
- **May it analyse locally?** Yes, on a bounded sample.
- **May it publish the records?** **No.** Not with attribution, not with a caveat, not reduced to a "sample" that still reproduces the records. Only with prior written permission from UNSD or a publisher licence that grants redistribution.
- **May it publish *derived aggregates*?** Contested. §5 reaches "any material … made available"; a derived figure is arguably still that material. Safe course: do not publish UN Comtrade-derived figures, or obtain permission first (§10.4).

---

## 4. Redistribution verdict — aggregate counts

Machine-readable authority: `config/convergence/licence_policy.json`.

| Verdict | Sources | Meaning |
|---|---:|---|
| **Redistribution allowed** (`may_redistribute=true`, condition `null` or `attribution`) | **20** | `public_domain` (10) + `open_licence` (10) |
| **Redistribution allowed only under attribution + rights caveat** (`open_no_explicit_licence`) | **10** | rights unverified; a conservative compromise, one edit away from quarantine |
| **Redistribution forbidden** (`may_redistribute=false`) | **21** | `terms_restricted` (9) + `requires_licence` (2) + `unknown` (10) |
| **Total classified** | **51** | registry-wide, i.e. includes the 27 never-materialised sources |

Restricted to the **24 materialised sources**: 15 allowed outright, 8 allowed-with-caveat, **1 forbidden** (`un_comtrade`).

Status distribution after this audit (one refinement: `importgenius` moved `requires_licence → terms_restricted`, because its terms explicitly prohibit reuse; the gate outcome is identical either way):

| `licence_status` | Sources | Materialised | Records |
|---|---:|---:|---:|
| `public_domain` | 10 | 7 | 888 |
| `open_licence` | 10 | 8 | 3,892 |
| `open_no_explicit_licence` | 10 | 8 | 1,104 |
| `terms_restricted` | 9 | 1 | 608 |
| `requires_licence` | 2 | 0 | 0 |
| `unknown` | 10 | 0 | 0 |
| **total** | **51** | **24** | **6,492** |

---

## 5. Rights matrix — the 24 materialised sources

Verdict key: **Y** = redistribution allowed · **Y\*** = allowed with attribution + rights caveat only · **N** = forbidden.

| # | Source | Records | Status | What the real terms say | Redistribute | Attribution | Action |
|---:|---|---:|---|---|:--:|---|---|
| 1 | `accessgudid` | 320 | `public_domain` | US federal dataset (FDA GUDID via NLM); no restriction stated. Basis is US federal authorship, not a positive licence sentence. GMDN term names inside GUDID remain third-party content | **Y** | courtesy | Publish. Do not extract GMDN term definitions as a standalone glossary |
| 2 | `brazil_anvisa` | 120 | `open_no_explicit_licence` | ANVISA "dados abertos": no login, no key, **no licence statement** on the index | **Y\*** | required | Publish with caveat; flip to quarantine if ANVISA terms later forbid |
| 3 | `canada_mdall` | 174 | `open_licence` | OGL-Canada v2.0: "worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes" | **Y** | **required** ("Contains information licensed under the Open Government Licence – Canada") | Publish with attribution |
| 4 | `cipo_canada` | 2,000 | `open_licence` | Same OGL-Canada v2.0 | **Y** | **required** | Publish with attribution |
| 5 | `clinicaltrials_gov` | 164 | `public_domain` | "available for public use and is not subject to copyright restrictions in the United States" | **Y** | courtesy | Publish. Contains no patient data; contains sponsor names and public study-contact details |
| 6 | `crossref` | 59 | `open_no_explicit_licence` | Metadata openly available for reuse, polite contact requested, **no blanket content licence**; rights live in per-record `license[]` | **Y\*** | required | Publish with caveat; keep per-record `license[]` intact |
| 7 | `epo_publication_server` | 228 | `open_no_explicit_licence` | EPO terms of use apply; **no explicit reuse licence** for the publication servers | **Y\*** | required | Publish derived bibliographic records only — no mirror (already the case) |
| 8 | `eu_cordis` | 60 | `open_no_explicit_licence` | Commission legal notice permits reuse with attribution, but the `/api/search/results` endpoint is **undocumented** and carries no machine-interface licence | **Y\*** | required | Publish with caveat |
| 9 | `eu_ted` | 299 | `open_no_explicit_licence` | TED API docs address "reusers of TED Data" and permit retrieval "for analysis or reuse"; **no formal licence sentence** located | **Y\*** | required | Publish with caveat |
| 10 | `europepmc` | 37 | `open_licence` | ELIXIR Core Data Resource; content reusable with attribution; per-record `license` preserved | **Y** | **required** | Publish with attribution |
| 11 | `eurostat_comext` | 1,400 | `open_licence` | "Reuse … for commercial or non-commercial purposes is authorised **provided the source is acknowledged**" (Commission Decision 2011/833/EU) | **Y** | **required** ("Source: Eurostat") | Publish with attribution |
| 12 | `nih_reporter` | 64 | `public_domain` | RePORTER FAQ: data is not copyrighted; US federal government data | **Y** | courtesy | Publish |
| 13 | `openaire` | 59 | `open_licence` | Graph published as open data under **CC-BY 4.0**; per-record rights preserved | **Y** | **required** | Publish with attribution |
| 14 | `openalex` | 60 | `open_licence` | "All data … is licensed under **CC0 1.0**" | **Y** | courtesy (CC0) | Publish |
| 15 | `openfda_device_510k` | 160 | `public_domain` | openFDA: "public domain and made available with a **Creative Commons CC0 1.0** Universal dedication". GMDN(R) carved out as third-party content — not present in device endpoints | **Y** | courtesy | Publish |
| 16 | `openfda_device_classification` | 60 | `public_domain` | as #15 | **Y** | courtesy | Publish |
| 17 | `openfda_device_pma` | 60 | `public_domain` | as #15 | **Y** | courtesy | Publish |
| 18 | `openfda_device_registrationlisting` | 60 | `public_domain` | as #15 | **Y** | courtesy | Publish |
| 19 | `pubmed_eutils` | 37 | `open_no_explicit_licence` | NLM makes citation data available for public use; **no blanket licence**; abstract copyright stays with the publisher | **Y\*** | required | Publish citation metadata, **not abstracts**. Vendor-level XML contains author affiliation emails — see §7.3 |
| 20 | `semantic_scholar` | 56 | `open_no_explicit_licence` | Graph API free for research; API terms restrict **bulk redistribution** and require attribution; corpus is ODC-BY | **Y\*** | required | Publish with caveat; bounded sample only (already the case) |
| 21 | `uk_find_a_tender` | 62 | `open_licence` | OCDS packages declare `licence: OGL v3.0` in their own payload | **Y** | **required** | Publish derived records. **The vendored raw packages carry 248 named buyers' work emails — see §7.3** |
| 22 | `uk_hmrc_trade` | 100 | `open_licence` | uktradeinfo.com: "All content is available under the **Open Government Licence v3.0**, except where otherwise stated" | **Y** | **required** | Publish with attribution |
| 23 | `usaspending` | 245 | `open_no_explicit_licence` | **No reuse-licence sentence found** (the `/about` page is a 3,003 B JS shell). Records are awarding agencies' own public contract data | **Y\*** | required | Publish with caveat |
| **24** | **`un_comtrade`** | **608** | **`terms_restricted`** | **§5 forbids copying, automated browsing/downloading, redistribution, publication and commercial exploitation without prior written permission** | **N** | n/a | **QUARANTINED.** See §3, §8, §10 |

### 5.1 The 27 registry-only sources

None is materialised, so none contributes bytes to the repository; the policy nevertheless classifies them so a future connector cannot silently ingest them.

| Verdict | Sources |
|---|---|
| **Redistribution allowed** | `openfda_bulk_download` (public domain), `uspto_bulkdata`, `uspto_open_data_portal` (US Government work), `ip_australia` (CC BY per dataset), `uk_mhra_device` (OGL v3.0 — but no open per-device register exists) |
| **Allowed with caveat** | `sam_gov` (account+key required, no reuse licence stated), `us_census_trade` (key required, no reuse sentence found) |
| **Forbidden — `terms_restricted`** | `epo_ops` (contract + OAuth consumer key), `espacenet` (WAF anti-automation), `google_patents` (billing account; scraping contrary to terms), `wipo_patentscope` (JSF session, no anonymous interface), `eudamed` (HTTP 429 with explicit anti-scraping instruction; official API needs EU Login + subscription key), `lens_org` (401 anonymous), `importyeti` (robots.txt disallows exactly the data endpoints), `importgenius` (terms: "No other use is permitted without our prior written consent") |
| **Forbidden — `requires_licence`** | `descartes_datamyne` (SaaS terms + EULA; contractual only), `panjiva` (S&P Global subscription; terms page returned **403**, so the clause is explicitly **not quoted** and the status is inferred from product structure, not read) |
| **Forbidden — `unknown`** | `australia_tga_artg`, `china_nmpa_udi`, `japan_pmda`, `dpma_open_data`, `epo_global_patent_index`, `epo_linked_open_data`, `eu_ctis`, `jpo_bulk`, `patentsview`, `usitc_dataweb` |

`unknown` is **not** a permissive class. Ten sources could not be read — mostly because the host refused automated access, served an SPA shell, or returned a WAF challenge that HORIZON correctly declined to circumvent. All ten are `may_ingest=false`, `may_redistribute=false`.

---

## 6. Policy decision for `open_no_explicit_licence` (the 10 "unknown rights" sources)

This is the second-largest risk class after `terms_restricted` (10 sources, 8 of them materialised, 1,104 records), so it needs an explicit, defensible rule rather than a reflex.

**The trap:** "no licence statement" is not "no restrictions". Copyright subsists by default; open publication without a licence grants nothing beyond what the publisher's terms and applicable law allow.

**The chosen rule (encoded in the policy, one field per source):**

| Right | Decision | Rationale |
|---|---|---|
| `may_query` | **true** | The publisher openly serves the content without authentication and documents the endpoint |
| `may_ingest` | **true** | Local storage for research is an incident of the permitted query, at a bounded sample size |
| `may_analyse_locally` | **true** | Same |
| `may_redistribute` | **true**, but only with `redistribution_condition = "attribution_and_caveat"` | These are factual data records published without an asserted restriction. Committing **attributed, caveated derived records** — not mirrors — is the least-risk option that still allows the project to function. It is a **conservative compromise, not a licence conclusion** |
| `attribution_required` | **true** | Always, for every source in this class |

**Explicitly rejected alternatives:**

- ❌ *"No licence = public domain"* — false as a matter of law and unauditable.
- ❌ *"Public API = free to redistribute"* — the fallacy this whole audit exists to refute.
- ✅ *Full quarantine of all 10* — the safest option, and one edit away: set `may_redistribute=false` for the source, and the gate fails immediately if its payload is present. Recommended if the owner wants zero residual licence risk.

**Residual risk accepted under this rule:** a publisher could later assert terms that forbid the redistribution already performed. Mitigations in place: (a) derived records only, never a byte-for-byte mirror of a publisher's file; (b) attribution text per source in the policy; (c) the rights caveat is surfaced in the review and the export README; (d) the class is reversible in one edit. **This is the item most in need of a lawyer's eye, and it is flagged as such rather than asserted as settled.**

---

## 7. Secrets, credentials and PII scan

### 7.1 What was scanned

| Refs scanned | Tracked files | Distinct blobs read | Text blobs scanned | Binary skipped |
|---|---|---:|---:|---:|
| `integration/convergence-001` | 1,864 | — | 1,757 | — |
| `research/horizon-001` (PR #29) | 1,826 | — | 1,719 | — |
| `foundation/atlas-001` (PR #28) | 1,203 | — | 1,098 | — |
| `main` @ `b2a14c0` | 1,135 | **1,838** | 1,030 | **384** |

Scanned the **committed blobs** (read through `git cat-file --batch`), not the working tree — so the result describes what is *published*, at every ref, with blobs deduplicated. 17 content rules + 9 path rules, ~30 patterns: PEM/OpenSSH/PGP private keys, AWS/GitHub/OpenAI/Slack/Google token shapes, JWTs, `Authorization`/`Bearer`/`X-API-Key`/`Cookie` headers, credential-named field assignments, hard-coded passwords, `.env`/`.netrc`/`.pypirc`/`.npmrc`/`id_rsa`/`*.pem|key|p12|pfx|jks|kdbx`/`credentials.*`/`.git-credentials` paths, email addresses, Chinese resident-ID and US-SSN shapes, patient-data markers.

**Final result: `python tools\convergence\licence\secrets_scan.py … --fail-on high` → exit 0. Zero critical, zero high findings on all four refs.** Two auditable mechanisms produce that clean result, and both are visible in `secrets_scan.json` rather than hidden:

- `*_placeholder` rules — the value is a vendor's own published placeholder (`PLACEHOLDER_ALLOWLIST`, e.g. `yourAPIKeyHere`, `DEMO_KEY`), reported at `info`;
- `*_known_fp` rules — one of **6 reviewed false positives**, each carrying a written `reason` (`KNOWN_FALSE_POSITIVES`). A new hit at the same path/rule would not be suppressed, because suppression matches on the surrounding line text as well.

Residual distribution after the baseline: `medium` 38, `low` 139, `info` 170 on the integration branch; identical on PR #29; `medium` 4 / `low` 1 / `info` 3 on `main` and PR #28. Nothing at `high` or above anywhere.

### 7.2 Triage: the scanner's raw high/critical hits, all of which are false positives

Before the reviewed baseline was applied the scanner raised **1 critical and 6 high** hits. Each was read in context and cleared:

| Severity | Path : line | What it actually is | Verdict |
|---|---|---|---|
| critical | `research/horizon/DATASETS/regulatory/_discovery/openfda_auth_docs.html:62` | `Authorization: Basic eW91ckFQSUtleUhlcmU6` — base64 decodes to **`yourAPIkeyHere:`**, i.e. openFDA's own documentation placeholder, captured while archiving the auth docs page | **False positive** (documentation) |
| high | `research/horizon/DATASETS/industry/eu_ted/raw/api_docs_index.html:937` | `<script src="…/search-algolia.js" data-api-key="7bd6f4bb…" data-api-id="BE8MR7O2G7">` — **Algolia search-only, client-side key** embedded in TED's own docs page. Public by construction (it ships to every browser); grants only read access to TED's *documentation* search index | **Not our credential**; third-party public widget key captured by archiving the page. No action beyond noting it |
| high | `research/horizon/DATASETS/industry/importgenius/raw/terms_of_use.html:1` | `data-public-api-key="cme0d109…"` on `https://app.optibase.io/script.js` — an **Optibase analytics widget public key** in ImportGenius's page. The attribute name says `public` | **Not our credential**; same class as above |
| high | `tools/github_api.py:29` | `password = line.split("=", 1)[1]` — the variable is populated at runtime from `git credential fill`. **No secret is stored in the file**; it is the correct way to handle a token | **False positive** (good practice) |
| high ×3 | `research/horizon/DATASETS/scholarly/clinicaltrials_gov/CTGOV_INDEX.json:50639, 52431, 67991` | `"phone": "011-34-9166-30970"` etc. — **telephone numbers** whose prefix matches a US-SSN regex. ClinicalTrials.gov study-contact phone numbers | **False positive** (see §7.3 for the PII analysis that does apply) |
| medium | `medradar/llm.py:95` | `api_key=os.environ.get("MEDRADAR_LLM_API_KEY", "")` — env-var lookup, no literal | **False positive** (good practice) |
| medium | `config/product_catalog_zh.json:3942`, `config/product_families.json:8113`, `scripts/build_product_catalog.py:646` | `"MRN"` — a **product/model abbreviation key**, not "medical record number" | **False positive** |
| medium ×35 | `…/accessgudid/records.jsonl`, `…/uk_find_a_tender/raw/*.json`, `…/clinicaltrials_gov/*.json` | `"Patient Record"`, `"medical record"`, `"date of birth"` as **device descriptions or study-design prose** in public source snapshots | **False positive** (no patient data) |

**No `.env`, `.netrc`, `.pypirc`, `.npmrc`, private key, keystore, or credential-store file exists in any tracked tree.** Rule counts for those path rules: zero on all four refs.

*Notes on the table:* the `eu_ted`, `importgenius` and `openfda_auth_docs` HTML rows each fire **two** rules (a `high` header/key rule and a `medium` `secret_assignment` rule), so the four `medium` `secret_assignment` hits are those three plus `medradar/llm.py:95`. The 35 `medium` `patient_data_marker` hits comprise the three `MRN` product-catalogue rows, one GUDID device description, six Find-a-Tender award descriptions and the remainder in ClinicalTrials.gov study prose. None is a patient record.

### 7.3 PII finding — named professional contact data in vendored source snapshots

**No patient data, no medical records, no private-individual data of the kind that would trigger a breach notification.** What *is* present is already-public professional contact information, re-published a second time inside a git repository. Census on the integration branch: **1,785 email-shaped occurrences / 604 distinct strings**, of which:

| Concentration | Occurrences | Distinct | Nature | Assessment |
|---|---:|---:|---|---|
| `experiments/detect_v1_verify/results.json` | 576 | 12 | **Not emails at all** — strings like `readout@0.01.naive` are JSON group/path names that happen to match an email regex | **False positive** |
| `uk_find_a_tender/raw/award_packages_p1-3.json` | **415** | **248** | OCDS `parties[].contactPoint` — **named individuals + work email** of UK public-sector procurement staff, e.g. `"name": "Andrew Dyer", "email": "andrew.dyer@cognus.org.uk"` | **Real PII, low sensitivity**: already published by the buyer in the award notice. Republishing vendors it into permanent Git history. **The derived export has 0 emails** |
| `clinicaltrials_gov` (`CTGOV_INDEX.json` + `raw/studies_spons_*.json`) | 351 | — | `centralContacts[]` = **named investigators + phone + email**, e.g. `"name": "Young Ah Lee, MD, PhD", "email": "nina337@snu.ac.kr"` | **Real PII, low sensitivity**: CT.gov publishes these deliberately for trial recruitment |
| `pubmed_eutils/raw/efetch*.xml` | ~123 | — | Author affiliation strings containing **corresponding-author emails** as printed in the article | **Real PII, low sensitivity**: published bibliographic data |
| `openfda_device_registrationlisting/raw/*.json` | ~53 | — | Firm/company email addresses (`@…`) | **Not personal data** |
| Government/institutional addresses (UN, EU, gov.uk, nhs, universities, dataset contacts) | rest | — | Published organisational contact addresses | **Not personal data** |

**Recommendation (no owner authorisation needed for the analysis; a separate decision for the change):** the 3 FTS raw OCDS packages are ~3.9 MB of vendored upstream payload whose only unique content beyond the derived export is (a) the contact block and (b) boilerplate. If the integration does not consume the raw packages — and `MANIFEST.json` shows it does not; only `uk_find_a_tender.jsonl` (62 records, 0 emails) is declared — they can be dropped from the repository with no loss of evidence, since `PROVENANCE.json` already records their URLs and SHA-256. That single change removes the largest named-individual concentration.

### 7.4 Request logs and provenance files — clean by design

The task specifically asked about embedded request headers, cookies and tokens. Result:

| File group | Records | Fields present | Headers / cookies / tokens |
|---|---:|---|---|
| `research/horizon/SOURCE_PROBES/**/REQUEST_LOG*.jsonl` (6 files) | 802 | `client, url, final_url, status, outcome, bytes, sha256, elapsed_ms, attempt, method, request_body_sha256, …` | **None.** No header, cookie, auth, token or credential field exists in the schema |
| `research/horizon/DATASETS/patents/epo_publication_server/REQUEST_LOG.jsonl` (the 7th log, outside `SOURCE_PROBES`) | 241 | same 9-field schema (`client, url, final_url, status, outcome, bytes, sha256, elapsed_ms, attempt`) | **None**, and no query parameters at all |
| `research/horizon/DATASETS/**/PROVENANCE.json` (all sources) | — | union of ~80 keys (`licence_*`, `raw_files`, `budget`, `observers`, …) | **None.** No header/cookie/token/credential key. Only `auth_required` (a boolean) |
| `research/atlas/staging/atlas_requests.jsonl` (PR #28 worktree, **not tracked on any ref**) | **933** | `attempts, bytes, elapsed_ms, error, logged_at, method, note, path, sha256, source_id, status, truncated, url` | **None.** Zero auth-ish keys; query params are only `search/di/id/limit/skip/state/type/lang` |

**Total probe-log records examined: 1,043 across 7 files, plus 933 ATLAS staging records.** The ATLAS staging log is worth one correction to the task's premise: `research/atlas/staging/` is **gitignored** (`.gitignore:34`) and `atlas_requests.jsonl` is tracked on **no ref** — it exists only as a local working file in the read-only `atlas-001` worktree. It is therefore **not published**, and it contains no credentials either. Auditing it was still worthwhile: had that directory ever been force-added, the log would have been safe to publish anyway.

**Query strings do carry two placeholder keys — both are non-credentials:**

- `research/horizon/SOURCE_PROBES/industry/REQUEST_LOG.jsonl:57` → `https://api.sam.gov/entity-information/v3/entities?api_key=DEMO_KEY&…`
- `research/horizon/SOURCE_PROBES/industry/REQUEST_LOG.jsonl:68, 111` → `…?api_key=test&…`

`DEMO_KEY` is a published demo placeholder and `test` is a literal dummy string; both requests failed. Recording them is harmless but the audit recommends the probe logger redact `api_key`/`subscription-key`/`token` query values in future, so a *real* key can never leak into a log.

**One project-owned identifier is published:** `email=medradar-research@proton.me` / `mailto=medradar-research@proton.me` in scholarly probe URLs (NCBI/OpenAlex polite-pool convention) and at `research/horizon/CONNECTORS/scholarly/_util.py:32`. This is a **deliberate project alias, not a personal address**. No action needed; if the project later wants to stop publishing it, switch to a no-reply address.

### 7.5 Git metadata

Commit author identity is `ChazY11 <zczcjyi@ucl.ac.uk>` on all four PR #29 commits. That is the repository owner's **public institutional address**, already present in every commit on every branch, including `main`. It is git metadata, not a credential, and no action is recommended. No other author identity appears on the audited refs.

### 7.6 Secrets conclusion

**Zero credentials, zero private keys, zero tokens, zero session material, zero patient data.** The remediation list contains **no credential rotation** item, because nothing was found that would need rotating. Two hygiene improvements are recommended but neither is an exposure: redact credential-shaped query parameters in the probe logger; and stop vendoring raw OCDS packages that carry third parties' contact blocks.

---

## 8. Historical exposure — PR #29

### 8.1 What was committed, where, and when

| Property | Value |
|---|---|
| Branch | `research/horizon-001` (PR #29), head `2dcdc99` |
| **Pushed to the public remote** | **Yes** — `git ls-remote origin` returns `2dcdc995102f094d723005c79bb9b0ec7d9737f7 refs/heads/research/horizon-001` |
| Commits unique to the branch | **4** (`18a7580`, `4c8d8f9`, `dd79693`, `2dcdc99`) |
| Commits that introduced restricted payloads | **1** — `18a7580` `research(horizon-001): global data-frontier acquisition, two new patent corpora and a versioned evidence export`, 2026-11-10T07:34:17+08:00 |
| Paths introduced | **30** |
| Distinct blobs | **29** (the two copies of `un_comtrade.jsonl` share blob `f5111f62…`) |
| Total payload bytes (blob sizes) | **6,234,301** |
| Branches containing `18a7580` | `research/horizon-001`, `origin/research/horizon-001` — **and no other branch** |
| Current reachability from `main` | **No** |

### 8.2 The exact list an owner would need to purge

Largest first. Full machine-readable version with blob OIDs and per-path metadata: `research/convergence/licence/pr29_exposure.json`.

| Path (relative to repo root) | Bytes | Blob OID (short) |
|---|---:|---|
| `research/horizon/exports/horizon-2026-11-10/un_comtrade.jsonl` | 1,832,311 | `f5111f62` |
| `research/horizon/experiments/industry/evidence/un_comtrade.jsonl` | 1,832,311 | `f5111f62` *(same blob)* |
| `research/horizon/DATASETS/industry/un_comtrade/raw/hs.json` | 1,886,837 | `7808cc6d` |
| `research/horizon/DATASETS/industry/un_comtrade/raw/reporters.json` | 81,177 | `e41f1deb` |
| `research/horizon/DATASETS/industry/un_comtrade/raw/annual_2015..2024.json` (10 files) | 50,684–50,774 each (507,235 total) | `608a7294`, `b6de7fee`, `a98f942e`, `0f0d8a1b`, `54907c43`, `19eddc3c`, `0a5a3e28`, `54038454`, `ce2f8f28`, `737f15ea` |
| `research/horizon/DATASETS/industry/un_comtrade/raw/comtradeplus_home.html` | 49,414 | `e54abf39` |
| `research/horizon/DATASETS/industry/un_comtrade/raw/monthly_2025{01..12}.json` (12 files) | 3,669–3,677 each (44,088 total) | `4fe967d8`, `5eae3090`, `067b6a06`, `56cdef1b`, `5170735a`, `477c6667`, `2f023c2b`, `5ef0ea98`, `c7f47939`, `d97a5bf7`, `8681d015`, `ddcce131` |
| `research/horizon/DATASETS/industry/un_comtrade/summary.json` | 790 | `06785d36` |
| `research/horizon/exports/horizon-2026-11-10/un_comtrade.jsonl.sha256` | 84 | `15ce2f8a` |
| `research/horizon/DATASETS/industry/un_comtrade/raw/api_root.html` | 54 | `3c494092` |
| **Total** | **6,234,301** | **29 distinct blobs** |

Content note: `hs.json` and `reporters.json` are the UN's HS nomenclature and reporter code tables. They are *reference* material rather than trade values, but they are still UN Comtrade material fetched under the same §5 and are treated as restricted (no exception was taken).

### 8.3 Verification that the integration branch is clean

| Check | Command | Result |
|---|---|---|
| Paths present on integration branch | tree diff `research/horizon-001` vs `integration/convergence-001` | **691 vs 661 files; exactly 30 only-on-PR#29 paths; 0 added** |
| Restricted blob reachable from integration | `git rev-list --objects integration/convergence-001 \| grep f5111f62` | **no match** |
| Any `un_comtrade` payload path in integration history | `git rev-list --objects integration/convergence-001 \| grep un_comtrade` | only `CONNECTORS/industry/un_comtrade.py`, `PROVENANCE.json`, `raw/comtrade_license.html`, `raw/terms_of_use.html`, `registry/sources/un_comtrade.json` |
| Gate — explicit quarantine path list | `exposure_report.py --check-ref integration/convergence-001` | **0 of 30 present** |
| Gate — same for `main` and PR #28 | `--check-ref main --check-ref foundation/atlas-001` | **0 of 30 present on either** |

**What *is* retained on the integration branch, deliberately, as licence evidence (no trade values):** `DATASETS/industry/un_comtrade/raw/comtrade_license.html` (50,778 B, contains §5), `raw/terms_of_use.html` (36,681 B — a 404 page), `DATASETS/industry/un_comtrade/PROVENANCE.json` (22,576 B — reporters/years/budget/HS codes, no values), `registry/sources/un_comtrade.json`.

---

## 9. The gate: config + tool + results

### 9.1 Configuration

`config/convergence/licence_policy.json` — `schema: medradar.licence_policy.v1`, version 1.0.0, 51 sources, generated reproducibly by `tools/convergence/licence/build_policy.py`. Per source: `licence_status`, `may_query`, `may_ingest`, `may_analyse_locally`, `may_redistribute`, `redistribution_condition`, `attribution_required`, `attribution_text`, `notes`, `evidence_url`, `checked_at`, `verification`. Plus `quarantine.paths` (the 30 paths), `quarantine.licence_evidence_allowlist`, `quarantine.derived_value_references`, and a `gate_contract` block defining the five verdicts.

The `verification` field distinguishes what this session actually re-read from primary sources (`live_verified`: `un_comtrade`, `canada_mdall`, `cipo_canada`), what is evidenced by a page archived in the repository (`archived_page_in_repo`), and what rests on HORIZON's probe record (`registry_recorded_not_reverified`). **A reviewer can see at a glance which verdicts were independently checked today.**

### 9.2 Tool

`tools/convergence/licence/licence_gate.py` — `check_export(export_dir, policy_path, repo=None) -> dict`, plus a CLI. It reads `MANIFEST.json`, classifies **every declared file**, verifies declared SHA-256 against the bytes on disk, and lists undeclared files so a payload cannot be smuggled in uninventoried. It also checks the explicit `quarantine.paths` list against the repository so absence can be asserted even for paths the manifest no longer declares.

| Verdict | Condition | Exit code |
|---|---|---|
| `ALLOW` | source redistributable, file present (SHA-256 verified) | — |
| `QUARANTINE` | source non-redistributable, file correctly absent | — |
| `VIOLATION` | source non-redistributable, file **present** | **1** |
| `MISSING-EXPECTED` | source redistributable, declared file absent | **2** |
| `UNKNOWN-SOURCE` | manifest declares a source the policy does not classify | **3** |

`MISSING-EXPECTED` is a *distinct* non-zero code on purpose: an export whose restricted payload was intentionally removed necessarily has a manifest that overshoots the disk, and CI must be able to tell "incomplete export" apart from "restricted payload found".

### 9.3 Results

**Integration branch `integration/convergence-001` @ `3c3a295` — `research/convergence/licence/gate_integration_branch.json`:**

```
declared: 24 files
VERDICT PASS  {'ALLOW': 23, 'QUARANTINE': 1, 'VIOLATION': 0, 'MISSING-EXPECTED': 0, 'UNKNOWN-SOURCE': 0}  exit=0
```

- 23 × `ALLOW`, every one with `integrity=ok` (declared SHA-256 matches the bytes on disk).
- 1 × `QUARANTINE` — `un_comtrade.jsonl`: *"source is NOT redistributable but the payload is correctly absent (intentionally quarantined)."*
- `quarantine_path_hits`: **[]** — none of the 30 restricted paths exists anywhere in the repository.
- 24 undeclared files present, all expected and harmless: `README.md` + 23 `*.jsonl.sha256` sidecars.

**PR #29 worktree @ `2dcdc99` (read-only) — `research/convergence/licence/gate_pr29_worktree.json`:**

```
declared: 24 files
VERDICT FAIL  {'ALLOW': 23, 'QUARANTINE': 0, 'VIOLATION': 1, 'MISSING-EXPECTED': 0, 'UNKNOWN-SOURCE': 0}  exit=1
```

- 1 × `VIOLATION` — `un_comtrade.jsonl` present (1,832,311 B).
- `quarantine_path_hits`: **30** — every restricted path present. (The gate reports **on-disk worktree** sizes, which differ slightly from Git blob sizes because the checkout applies CRLF expansion: `hs.json` is 1,952,940 B on disk but its blob is 1,886,837 B. The 6,234,301 B total in §8.2 is the sum of **blob** sizes, i.e. what is actually stored in and served from the object database.)

The gate therefore demonstrably distinguishes the two states, and the quarantine on the integration branch is real rather than declared.

---

## 10. Remediation for the owner — options, costs, authorisation

**Nothing below has been executed. Items 10.1–10.3 and 10.5 change public state and each requires the repository owner's explicit authorisation.**
Constraining fact: **PR #29's branch is already pushed to the public remote**, so the payload is already public and may already have been fetched, forked, cached by GitHub, indexed by search engines, or cloned. **Deleting history cannot un-publish what has been published.** That asymmetry should drive the decision.

### 10.1 Option A — leave PR #29 history as-is; land only the quarantine elsewhere  ⟵ *lowest cost, no authorisation needed beyond merging*

| | |
|---|---|
| **What** | Do not rewrite anything. Take the integration branch (which is already clean) as the deliverable. Close PR #29 without merging its branch tip, or merge it and immediately follow with a removal commit. Add the gate to CI so it can never recur. |
| **Benefit** | No force-push, no coordination cost, no risk of breaking anyone's clone. The clean state is already achieved and gate-verified. |
| **Cost / risk** | The 6,234,301 B remain readable in `origin/research/horizon-001` for as long as the branch exists. A future `git log --all` or a clone of all branches still surfaces them. **This does not remediate; it contains.** |
| **Authorisation** | Owner only needs to agree to *not* rewrite. |

### 10.2 Option B — owner rewrites PR #29 history and force-pushes the branch  ⟵ *removes the branch copy; irreversible*

| | |
|---|---|
| **What** | Owner (only) rewrites `research/horizon-001` to drop the 30 paths from `18a7580` (e.g. `git filter-repo --invert-paths --path …` × 30), then `--force-with-lease` pushes. |
| **Benefit** | The branch no longer serves the payload. Any *new* clone gets a clean history. |
| **Cost / risk** | (a) All 4 commit SHAs change, invalidating the PR's recorded head `2dcdc99` and every reference to it (including this audit, `EXPERIMENT_RESULTS.md`, PR bodies, and any teammate's notes); (b) force-push is destructive to anyone who has the branch checked out; (c) old objects persist on GitHub until garbage-collected and may remain reachable by SHA / cached views / forks for an unbounded period; (d) **it does not un-publish** what has already been fetched. |
| **Authorisation** | **Explicit owner authorisation required.** Never routine. |

### 10.3 Option C — owner deletes and re-creates the branch

| | |
|---|---|
| **What** | Owner deletes `research/horizon-001` on the remote, then pushes a new branch containing only the wanted commits (i.e. the selective-import content already on the integration branch). |
| **Benefit** | Simpler than a rewrite; the branch ref stops pointing at any restricted blob, and the PR is cleanly superseded rather than rewritten. |
| **Cost / risk** | Same residual as B — GitHub may keep unreachable objects for a while, and forks/caches are outside the owner's control. All commit SHAs change. Loses the reviewable PR history that documents how HORIZON's numbers were produced (though `research/horizon/` on the integration branch preserves the artefacts). |
| **Authorisation** | **Explicit owner authorisation required.** |

### 10.4 Option D — decide the destination of the *derived* Comtrade figures  ⟵ *needs a decision, not a rewrite*

| | |
|---|---|
| **What** | Two retained files still publish UN Comtrade-derived numbers: `research/horizon/reports/INDUSTRY_DATA_REPORT.md` lines 82–88 (China HS-9018 imports 2015/2019/2021/2023/2024 in USD bn) and line 127 (Germany-2023 cell `US$13,359,445,208.52`), and `research/horizon/experiments/industry/EXP_H4_INDUSTRY.json` `cross_checks.de_9018_imports_2023.comtrade_usd = 13359445208.517`. The payload files are gone; these derivative figures are not. |
| **Options** | (i) **Strip them** — replace with "UN Comtrade cell withheld pending written permission" and keep the Comext/HMRC side of the cross-check, which is explicitly open. Cheapest, safest, loses one reconciliation illustration. (ii) **Keep them** — argue a derived aggregate is analysis rather than "material". Defensible but contested under §5; would want UNSD's written view. (iii) **Seek permission** from the Director, UNSD — the only path that keeps the figures *and* removes the doubt. |
| **Additional consistency bug** | `INDUSTRY_DATA_REPORT.md:90` tells readers "the full series is in `experiments/industry/evidence/*.jsonl`" — but `evidence/un_comtrade.jsonl` is one of the quarantined files, so that pointer now dangles. Fix whichever way 10.4 is decided. |
| **Authorisation** | Owner decision (or owner delegates it to whoever owns the report text). No history change implied. |

### 10.5 Option E — ask GitHub support to purge cached views

| | |
|---|---|
| **What** | Owner opens a request to GitHub Support to expire cached views and run GC on the repository after B or C, and optionally to purge forked copies if any exist. |
| **Benefit** | The only mechanism that can reach beyond the owner's own refs (caches, unreachable-object retention). |
| **Cost / risk** | Slow (days–weeks), involves disclosing the situation to GitHub, no guarantee. Nothing here needs it urgently because no credential leaks. |
| **Authorisation** | **Explicit owner authorisation required** (only the owner can act as the repo's owner). |

### 10.6 Option F — rotate credentials

**Not applicable.** No credential, token, key or session artefact was found on any audited ref (§7). There is nothing to rotate. *If* the owner ever commits a real key, rotate first and rewrite second — rotation is the only step that actually removes risk.

### 10.7 Recommended sequence

1. **Now, no authorisation needed:** merge the integration branch as the deliverable; keep the gate green in CI (`licence_gate.py` → exit 0 required); keep PR #29's branch as documented-but-quarantined.
2. **Owner decision (text, low risk):** strip or justify the derived Comtrade figures (§10.4) and fix the dangling pointer at `INDUSTRY_DATA_REPORT.md:90`.
3. **Owner decision (privacy hygiene, low risk):** drop the 3 vendored FTS raw OCDS packages, which carry 248 named buyers' work emails and are not needed by any declared export (§7.3).
4. **Owner decision (irreversible):** only if the owner judges that leaving 6.2 MB of UN Comtrade material readable on a public branch is unacceptable, choose **B or C**, then **E**. Treat this as a one-way door and record the decision.
5. **Never:** treat a history rewrite as routine, or rewrite someone else's work without their explicit say-so.

---

## 11. Clean substitute sample for integration validation

**Requirement:** demonstrate the end-to-end flow without touching any restricted data. **Confirmed: no restricted data is needed.**

| Property | Value |
|---|---|
| Sources | **23** (all materialised sources except `un_comtrade`) |
| Records | **5,884** of 6,492 (90.6 %) |
| Bytes | 18,502,692 of 20,335,003 (the withheld 1,832,311 B is exactly the `un_comtrade.jsonl` payload) |
| Coverage of licence classes | `public_domain` 7 sources / 888 records; `open_licence` 8 / 3,892; `open_no_explicit_licence` 8 / 1,104 — so all three permissive classes are exercised |
| Gate expectation | `PASS`, 23 × `ALLOW`, 1 × `QUARANTINE`, exit 0 — the current integration state |

**Suggested source assignment by pipeline stage** (chosen so every stage has an explicitly-open or public-domain source, and so the withdrawal of `un_comtrade` costs nothing analytically):

| Stage | Primary sources | Why these |
|---|---|---|
| Regulatory identity / UDI | `accessgudid` (320), `openfda_device_registrationlisting` (60), `openfda_device_510k` (160), `canada_mdall` (174), `brazil_anvisa` (120) | Public domain + open licence; carries device identifiers for the identity stage |
| Patent / IP | `cipo_canada` (2,000), `epo_publication_server` (228) | Largest corpus; OGL-Canada attribution + EPO derived records |
| Scholarly links | `crossref` (59), `pubmed_eutils` (37), `openalex` (60), `openaire` (59), `europepmc` (37), `semantic_scholar` (56), `clinicaltrials_gov` (164), `nih_reporter` (64), `eu_cordis` (60) | Enough to rebuild the anchor/relation matrices |
| **Trade** | **`eurostat_comext` (1,400) + `uk_hmrc_trade` (100)** | **The explicit substitute for `un_comtrade`.** Both are `open_licence` (Eurostat: reuse authorised with source acknowledgement; HMRC: OGL v3.0) and both cover the same HS-9018..9022 medical-device codes for 2015–2024, so the trade stage is exercised with **zero** licence ambiguity. This is precisely the fallback HORIZON's own `DATA_QUALITY_AUDIT.md` and `GLOBAL_SOURCE_DEEP_AUDIT.md` already recommend ("drop Comtrade and rely on Eurostat Comext + UK HMRC") |
| Procurement | `usaspending` (245), `eu_ted` (299), `uk_find_a_tender` (62) | Firm-award relations; supplier identifiers and OCDS ids |

**What is lost by dropping `un_comtrade`:** 608 country-total trade observations for 7 reporters. The trade stage remains exercisable and independently verifiable on 1,500 open records covering 5 HS4 codes and 7 reporters; the only capability that changes is cross-source *compilation* comparison for China/Japan/USA, which `INDUSTRY_DATA_REPORT.md:122–135` uses as a mislabelling check. For that check, the Comext-vs-HMRC comparison remains available (different currencies/compilers) — no restricted data required.

---

## 12. Residual uncertainties (with dates)

| # | Uncertainty | Why it matters | Dated status |
|---|---|---|---|
| R1 | **UN Comtrade: is a derived aggregate "material" under §5?** No official guidance read. | Decides §10.4 (keep/strip the 6 figures) | 2026-11-11, unresolved. Would need correspondence with UNSD |
| R2 | **`open_no_explicit_licence` class is a compromise, not a licence.** 10 sources / 1,104 materialised records are redistributed on an attributed-caveat basis that no publisher has affirmed | The largest residual legal risk in the repository | 2026-11-11, accepted with mitigation; reversible in one field |
| R3 | **Panjiva's terms were never read** (HTTP 403 to the automated client). Status inferred from product structure | `requires_licence` is likely right but is not evidenced by a quoted clause | 2026-11-09 probe / 2026-11-11 audit, unresolved |
| R4 | **10 `unknown` sources could not be read at all** — mostly WAF/SPA/JSF shells. Silence was not treated as permission | If any is later found permissive, nothing is gained; if restrictive, nothing was ingested, so no exposure | 2026-11-11, closed by non-ingestion |
| R5 | **Only 3 verdicts were re-read live today** (`un_comtrade`, `canada_mdall`, `cipo_canada`). The other 48 rest on HORIZON's probe record and on archived pages in the repository | Publisher terms change; a stale verdict could be wrong | Policies carry `checked_at` + `verification` so staleness is visible; recommend re-verification before any new ingestion |
| R6 | **GitHub-side retention is unobservable from here.** Unreachable objects, caches, forks and clones are outside local evidence | Any claim that a rewrite "removed" the payload is unverifiable from the local repository alone | 2026-11-11, unobservable. Only GitHub Support (Option E) could speak to it |
| R7 | **Whether the payload has already been fetched by a third party** | Cannot be determined locally; assume it has, since the branch is public and pushed | 2026-11-11, unknowable |
| R8 | **`LICENCE_EVIDENCE.json` does not register `comtrade_license.html`** (§3.3) | A reviewer trusting the evidence index sees zero quoted clauses for the one restricted source | 2026-11-11, open; docs-only fix recommended |
| R9 | **PII: no lawful-basis analysis performed.** The contact data was already public in its source; republication is a second processing operation | A GDPR/UK-GDPR assessment is a lawyer's task, not this audit's | 2026-11-11, flagged not concluded |

---

## 13. One-line answers to the questions this task asked

1. **What is the real UN Comtrade restriction?** §5 of the Usage Agreement forbids "any copying, automated browsing or downloading, redistribution, publication, or commercial exploitation of any material … without the prior written permission of the United Nations". The public preview API separately invites programmatic querying. **Query and bounded local analysis: defensible. Redistribution of the records: prohibited.** Attribution does not cure it.
2. **What may be redistributed?** 20 sources outright, 10 only with attribution + a rights caveat, 21 not at all. Of the 24 materialised sources: 15 / 8 / 1.
3. **Any secrets?** None. 1,838 blobs on 4 refs; every high/critical hit is a documentation placeholder, a third-party public widget key, or a runtime credential lookup.
4. **Any PII?** No patient data. Named professional contacts inside already-public source snapshots; 248 distinct UK procurement contacts are the largest single concentration and the only one worth removing for hygiene.
5. **How large is the PR #29 exposure?** 1 commit (`18a7580`), 30 paths, 29 blobs, **6,234,301 bytes**, reachable from the pushed `origin/research/horizon-001`, reachable from no other branch.
6. **Is the integration branch clean?** Yes — 0 of 30 paths, gate **PASS exit 0**. The PR #29 worktree gives gate **FAIL exit 1**.
7. **What needs owner authorisation?** History rewrite (§10.2), branch deletion/re-creation (§10.3), GitHub Support contact (§10.5), and the keep/strip decision on the derived Comtrade figures (§10.4).
