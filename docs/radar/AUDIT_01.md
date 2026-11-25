# Audit 01 — rounds 1–9

First of the scheduled audits. Two defects were already known before it started; the audit looked for
the third kind, the one nobody has noticed yet.

## 1. A test suite that sometimes fails is a test suite that cannot be trusted

**Symptom.** One full run reported four failures — `test_the_device_endpoint_returns_the_whole_timeline`,
`test_the_device_page_is_reachable_without_the_react_bundle` and two others — and the next two runs
were green. Every failing test also passed when run alone. That is the shape of an order dependency,
not of a broken assertion.

**Cause.** `medradar/radar/api.py` keeps `_VIEW_CACHE`, a module-level TTL cache for the two heavy
graph views. Its keys were `("health",)`, `("technology-map", …)`, `("compare", …)`,
`("changes", …)` — none of them mentioned *which store* the answer came from. Every service in the
process shares that dict, so a test fixture's answer was served to the real store, and two fixtures
answered each other's questions whenever the random ordering put the same key in play twice inside
the 60-second window.

**Fix.** `build_router` now prefixes every key with `("store", <radar root>)`, through a local
`view()` helper so a future call site cannot reintroduce the leak by forgetting the prefix.

**Evidence.** Three consecutive full runs under `pytest-randomly`'s default random ordering:
1906 passed, 1906 passed, 1906 passed. A regression test builds two routers over two temporary
stores and asserts the second answer is not the first object.

**Not claimed.** The original failing seed was not captured, so I cannot prove this was the *only*
cause of that run's four failures. What I can show is that the mechanism was real, that it is fixed,
and that three random orders now agree.

## 2. The export could say less than the page it came from

**Symptom found by the audit, not by a user.** Every page and every export show the same reason codes
next to the same gaps. Each had its own `GAP_TEXT` dictionary.

**Measured drift.** Of the 22 codes the code can actually emit, the export's copy was missing four:
`section_absent_from_document`, `paper_not_in_index`, `device_index_absent`,
`no_registered_brand_shares_these_terms`. A downloaded Markdown file would have shown those as a bare
code while the page showed a sentence — exactly the failure mode the whole project is trying to
avoid, in the artifact that outlives the page.

**Fix.** `medradar/radar/gaps.py` holds the single table. `pages.py` and `export.py` both import it,
and a test asserts they are the same object, so a future copy cannot drift.

## 3. What the audit checked and found acceptable

| Check | Result |
| --- | --- |
| Every emitted code has a sentence | 26 codes in the table; the only one added by this audit was `section_absent_from_document` |
| Codes explained but never emitted | three, all reached through conditional expressions rather than literals; harmless |
| Pages reachable by clicking | fixed in round 9; a test now walks the landing page's links |
| Search-derived patents counted as the company's | excluded since round 4; `searched_for` reported separately |
| Group-level matches labelled | trials print 按集团名匹配, papers print 公司级匹配, the map prints `TOPIC_RELATED` beside every claim |
| A match needs a word that names one product | enforced since round 6 (register frequency + structural words), with the 349-paper example recorded |

## 4. Known and not fixed

- **Cold start on a name query.** A company or brand lookup costs 3.8–7.7 s on a freshly restarted
  process, 0.3 s warm. The work is real (ten device timelines); removing it means persisting paper
  histories to a table, which is a round of its own.
- **The landing page counts 5.2M rows.** 2.9 s cold locally, more through the tunnel. A materialised
  counter table would fix it; not done.
- **Patent coverage is 92 assignees** out of 12,537 labelers. Google Patents answers in bursts (one
  batch succeeds, the next returns 503 for thirty minutes), so the nightly job advances eight
  companies at a time.
- **Preprints are refused from this host.** europepmc is the lane that still works; the nightly job
  runs it regardless.
- **The public URL rotates.** localhost.run's free tier reissues the subdomain, so the address in
  `/srv/medradar/data/radar/public_url.txt` is the source of truth and a bookmark will eventually die.

## 5. What the next audit should look at

Two questions this one did not answer:

1. Does the device dossier's *headline* summary ever conflict with its sections? The summary row
   counts papers at company level for some devices while the section below labels them 公司级; a
   reader skimming the top could take the bigger number as device-level.
2. Are the 22 reason codes all *reachable*? A code that can only fire on an impossible state is dead
   weight; a code that fires for two different situations is a lie in miniature.
