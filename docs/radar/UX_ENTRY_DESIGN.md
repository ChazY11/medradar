# Entry-point design: what other tools do, and what this one adopted

Written after the first rebuild, because the original entry point was a filter wall and the question
"why is this hard to start with" needed an answer that was not a matter of taste.

## What was measured on our own tool first

| Symptom | Evidence |
| --- | --- |
| No device entry at all | The SPA had two routes (`/radar`, `/radar/technology-map`); the bundle mentioned `trial` and `patent` zero times. Device intelligence lived at `/api/radar/device/view`, an API path that happened to return HTML. |
| First screen said nothing | Landing on `/radar` produced eight filter groups and record counts in the thousands ("Arrhythmia detection (15137)"). None of it answers "what is this for". |
| Internal plumbing on the front page | The navigation listed 数据同步 and 身份复核, which are operator tools. |
| Twelve seconds to an answer | One device dossier built clearances, failures, trials, patents and papers on every request. |

## What the comparable tools do

| Tool | Entry | Result page | Notable |
| --- | --- | --- | --- |
| Google Patents | One box, any identifier (number, phrase, inventor) | One document, with citing/cited tabs | Accepts whatever the reader has in hand; never asks which field you mean |
| FDA 510(k) database | A form of eight fields with an explicit "or" between them | A result list, then a detail page | Correct data, hostile entry: the reader must know their own query type |
| ClinicalTrials.gov | One box plus optional filters | A record with summary / eligibility / outcomes tabs | Filters narrow, they do not gate; the box alone always works |
| PatSnap, Lens.org | Account-gated workbench, facets left, results right | Analysis views, charts, exports | Powerful, and it costs a session before the first answer |

## What this tool adopted, and why

1. **One box, any identifier.** K number, DI, DUNS, model, brand or company. The reader arrives
   holding something; asking them to classify it first is the FDA form's mistake.
2. **The entity page is the product.** Everything about one device on one page, ordered by the
   question an engineer asks: approval and specifications, then field failures, then what is being
   tried, then what is claimed, then what is written. Not by which table supplied the row.
3. **A citation beside every claim, and a reason beside every absence.** The comparable tools show
   what they have. None of them tells you *why* a section is empty, which is the question that stops
   a reader from trusting the rest.
4. **No login before the first answer.** The alpha gate is a single basic-auth prompt in front of the
   whole site, not an account system; the reader is never asked to register to see a device.
5. **Filters narrow, they never gate.** Facets live inside the result pages, not on the entry screen.
6. **Fast or cached.** Landing 0.3 s warm, device dossier 0.34 s warm, technology map 0.31 s from a
   snapshot. A cold dossier still costs 8 s because the work is real.
7. **Readable on a phone.** Two-column stat grid under 560 px, tables scroll inside their own box
   rather than pushing the page sideways.

## What is deliberately not copied

- **Charts on the landing page.** A count of 348,742 failure records is a fact about our database,
  not an insight about a device. Numbers appear where they answer a question.
- **Account tiers.** Nothing here needs one to be useful yet, and a paywall in front of a data
  correctness problem hides it rather than fixing it.
- **A "similar devices" recommender.** We do not have a sound similarity measure; a bad one would be
  worse than none.

## Known gaps against these tools

- Google Patents and Lens let you move patent → citing patent → assignee as a chain. We have assignee
  → patent list, one hop, and only where the patent tables were actually imported.
- ClinicalTrials.gov lets you filter by phase, status and country inside a topic. We show the trials
  attached to one company or device, with status, but no faceting.
- Neither our map nor our company page supports free-text search across the graph; navigation is
  topic → company → device.
