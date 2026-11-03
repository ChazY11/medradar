# MedRadar 2.0 — Web Contract (v1)

This file is the binding interface contract between the FastAPI backend (already
running) and the static SPA in `web/`. Both sides are built in parallel, so the
shapes below are authoritative: do not rename fields, do not add fake data.

- Backend: `medradar/web/app.py` + `medradar/product/store.py`
- Frontend: `web/index.html`, `web/styles.css`, `web/app.js` (vanilla JS, no build
  step, no CDN, no external fonts — must work offline)
- Local server: `python -m medradar web --port 8787` (already running)
- Health check: `GET /api/health`

All prose returned by the API is Chinese. The UI language is Chinese (with
English labels for the product/domain names where the API provides them).

---

## 1. Design direction (must follow)

Professional research terminal, not a marketing site:

- dark-first; background `#0a0f16`, panel `#111823`, panel-2 `#0d141d`,
  border `#1e2a3a`, text `#d7e0ea`, muted `#8296ab`, accent blue `#2f81f7`,
  teal `#2dd4bf`, amber `#d29922`, red `#f85149`, green `#3fb950`
- system font stack + monospace for all numbers (`ui-monospace, "SF Mono", Menlo, Consolas`)
- dense, quiet layout; 12–14 px body; clear hierarchy; no huge hero cards,
  no decorative animation, no gradient blobs, no emoji
- every page: title row + data-window/source caption; panels with 1px borders
- charts: inline SVG built in JS, hover tooltips with exact values, click a bar
  → evidence search for the same filters (no dead interactivity)
- states: skeleton/loading, empty ("该筛选下没有记录" + reset), error (message + retry)
- responsive down to 390px: nav collapses to a menu, tables scroll horizontally

Evidence tiers (use the returned `tier`/`tier_label_zh`): Observed / Detected
Signal / Research Hypothesis. Prediction is never shown as fact.

---

## 2. Navigation & routes (hash routing, links must work)

`#/overview`, `#/companies`, `#/companies/{key}`, `#/compare`, `#/radar`,
`#/radar/{track}`, `#/analyst`, `#/lab`, `#/lab/{study_id}`, `#/evidence`.

Nav labels: 总览 / 企业情报 / 技术雷达 / 研究助手 / 研究实验室 / 证据浏览器.

Global header: brand `MedRadar`, subtitle `Evidence-Driven MedTech Intelligence`,
data cut-off chip (`meta.dataset.date_range.last`), and a global evidence search
input that routes to `#/evidence?q=...`.

---

## 3. Endpoints

### GET /api/meta
Top-level: `product`, `dataset` (`.counts`, `.date_range.last`, `.track_mapping_coverage`,
`.modified_utc`), `sources[]` (`id,label_zh,market,coverage_zh,caveat_zh,observed_count`),
`tracks[]` (`id,name_zh,name_en,category`), `domains[]` (`id,label_zh,tracks[]`),
`metrics{name:{label_zh,definition_zh,caveats[]}}`, `featured_companies[]`,
`limitations[]{id,text_zh}`, `evidence_tiers`, `entity_review[]`, `studies[]`,
`analyst_examples[]`, `window_choices[]`, `comparability_notes[]`.

### GET /api/companies?include_all=true
`{companies:[{key,name_zh,name_en,ticker,featured,events,approvals,recalls,trials,
corporate,tracks,first_event,last_event}], featured:[...], total}`

### GET /api/companies/{key}?years=5
`{key,info{name_zh,name_en,ticker,exchange,hq_zh,profile_zh,featured},window{years,start,end},
headline{events_all_time,approvals_all_time,approvals_window,approvals_window_mapped,approvals_window_all,
approvals_prior,approvals_prior_all,unmapped_window,unmapped_prior,window_basis_zh,delta,pct_change,
tracks_active,first_event,last_event,recalls_all_time,trials_all_time,pathway_mix{pma,510k,basis,note_zh},
pathway_mix_counts},
coverage[{source,kind,n,first,last,label_zh,coverage_zh,caveat_zh}],
tracks{rows[{track,name_zh,recent,prior,delta,pct_change,share_recent,share_prior,
industry_recent,industry_prior,industry_pct_change,first_approval,new_in_window,z}],window},
series{approvals{points[{period,count,partial}],granularity},by_kind_year{periods,series}},
milestones[{event_date,label_zh,title,url,track_name_zh,kind,event_id|null}],
recent_events[{event_id,event_date,kind,title,url,company_name_zh,track_name_zh,company_match}],
claims[{claim_id,tier,tier_label_zh,statement_zh,direction,confidence,caveats[],
metrics{recent,prior,delta,pct_change,industry_*,share_*,low_volume},window,
evidence_params{company,track,metric,recent_start,recent_end,prior_start,prior_end}}],
entity_review[],limitations[{id,text_zh}],flags}`

### GET /api/compare?companies=a,b,c&metric=approvals&years=5&granularity=quarter
`{companies[{key,name_zh,total,total_complete,partial_total,prior_total,series[{period,count,partial}],
tracks{},unmapped,coverage[],pathway{pma,510k,pma_share,510k_share}}],metric,window{start,end,years},
granularity,track_table[{track,name_zh,domain,industry_total,industry_share,
companies[{key,n,share,location_quotient}]}],warnings[{code,severity,text_zh}],notes[]}`

`total` is the full window (including the partial period at the data edge);
`total_complete` excludes partial periods; `partial_total` is the difference.

Metrics: `approvals` (510(k)+PMA), `510k`, `pma`, `recalls`, `trials`, `corporate`.

### GET /api/radar?years=3
`{window,domains[{id,label_zh,recent,prior,delta,pct_change,companies_active,
signal_tracks[],tracks[{track,id,name_zh,recent,prior,delta,pct_change,spark[],
signal{z,flagged}|null,companies_active,top_companies[]}]}],mapped_records,
unmapped_records,track_mapping_coverage,method{caveat}}`

### GET /api/radar/{track}?years=10
`{track{id,name_zh,name_en,category,domain},domain,totals{recent,prior,delta,pct_change,all_time},
attribution{attributed_recent,unattributed_recent,attributed_share,note_zh},
series{periods[],approvals[{period,count,partial}],by_kind{510k[],pma[]}},
companies[{company,name_zh,n,share,first,last,featured}],entrants[{company,name_zh,first_date,n}],
signals[{period,z,current,baseline_mean,direction}],events[{event_id,event_date,title,url,
track_name_zh,company_name_zh}],method}`

### GET /api/evidence?companies=&track=&metric=&source=&start=&end=&q=&limit=&offset=
`{total,limit,offset,items[{event_id,event_date,kind,source,title,url,company_name_zh,
track_name_zh,company_match,product_code,published_at}]}`

### GET /api/evidence/{event_id}
`{event{...all fields, company_key,company_name_zh,company_match,track_name_zh,track_mapped},
product_code{product_code,device_name,definition,specialty}|null,source{...},
track,payload,mapping{company_method,company_note_zh,track_method,track_note_zh},
dates{event_date,published_at,available_at,note_zh},links{source_url},limitations[]}`

### POST /api/evidence/claim (body = claim.evidence_params)
`{company,company_name_zh,track,metric,window,recomputed{recent,prior},
recent_events[],prior_events[],note_zh,limitations[]}`

### GET /api/analyst/examples
`{examples[],capabilities{can_zh[],cannot_zh[]},mode,mode_zh}`

### POST /api/analyst/ask  body `{question}`
`{status:"answered"|"needs_clarification"|"out_of_scope",question,mode:"deterministic",
mode_zh,intent{type,label_zh,parsed{companies[],tracks[],years,metric}},answer_zh,
sections[{title_zh,body_zh,table?{columns[],rows[][]},bullets[]}],
evidence[{event_id,event_date,title,url,company_name_zh,track_name_zh,why_zh}]|[],
limitations[],followups[],computation_zh}`
The analyst is a deterministic engine; never present its output as an LLM answer.

### GET /api/lab and GET /api/lab/{study_id}
`{studies[{id,title_zh,status_zh,status_tone,period,branch,question_zh,method_zh,
findings_zh[],datasets_zh[],reproduce_zh[],limits_zh[],artifacts{...}}],provenance,...}`
Study detail adds `artifacts`: for `S-027-early-signal-5firms` → `human_review`,
`agent_pre_adjudication`, `pilot`, `concurrent_detection`, `lead_time_small_sample`,
`third_source`; for `C43-hist-v1` → `five_firm_timeline{cases[]}`, `report`,
`provenance`.

---

## 4. Required behaviour per page

1. **Overview** — data foundation KPIs from `/api/meta`+`/api/companies`
   (featured 5, events, tracks, mapping coverage, data cut-off); "从结论到证据"
   3-step explainer; top radar domains from `/api/radar`; quick links; limitation banner.
2. **Companies** — featured five as dense cards with real counts; searchable full list;
   each card links to profile.
3. **Company profile** — header facts; KPI strip; claims list with tier badge,
   confidence, "查看证据" button opening the claim evidence panel (POST /api/evidence/claim);
   technology mix table; interactive trend chart with window switch (3/5/10 years);
   milestones timeline; coverage & limitations panel; entity-review note for Dräger/Mindray.
4. **Compare** — multi-select up to 5 companies; metric + window + granularity;
   grouped line/bar chart; track matrix table with share and location quotient;
   comparability warnings rendered prominently (not hidden).
5. **Radar** — 8 domain cards with real totals + sparkline; track detail with
   quarterly chart, company composition, entrants, detected signals (labelled),
   recent events → evidence.
6. **Analyst** — question box + example chips; renders sections, tables, evidence
   list (each item opens event detail), limitations, parsed intent; explicit
   "确定性检索引擎（无 LLM）" badge; if `needs_clarification`, render the offered
   choices as clickable.
7. **Lab** — study cards with status tone; detail with findings, negative results,
   reproduction commands, artifacts tables (five-firm timeline), provenance note
   that the hist_v1 branch is not merged.
8. **Evidence explorer** — filters (company multi, track, metric, source, window, q);
   result table with pagination; row → detail drawer with mapping provenance,
   dates, source link, limitations; URL reflects filters when reasonable.

Never invent a source URL: use only `url` returned by the API; if empty show
"该记录没有可用的原始链接".

---

## 5. Verification

- `curl` every endpoint once after implementing each page.
- Open every route in a browser at 1440×900 and 390×844; check no console errors.
- Click: featured company → claim → evidence events → event detail → source link.
- Scenario acceptance is done by the Lead afterwards; report what you verified.
