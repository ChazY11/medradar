# ALPHA_RELEASE_GUIDE

Controlled private alpha: a local installation. No paid infrastructure, no public cloud, no
multi-tenant SaaS. This is the exact procedure a reviewer followed to produce the acceptance evidence
in this delivery.

## 1. Requirements

* Python 3.10+ (verified on 3.12.10, Windows and Linux).
* Node 20+ only if you want to rebuild the UI (the built UI is committed, so end users do not need it).
* No network access at run time: the snapshot is committed and immutable.
* No API keys, no accounts, no paid services.

## 2. Install (from the repository)

```bash
git clone https://github.com/ChazY11/medradar.git
cd medradar
git checkout feat/product-002-trusted-intelligence   # the PRODUCT-002 branch
python -m pip install --upgrade pip
python -m pip install -e ".[product]"
```

Verify:

```bash
python -m medradar.product.web --port 8787 --host 127.0.0.1
```

Open http://127.0.0.1:8787 . If the page loads, the API and the built UI are in place.

## 3. Start the product

| Mode | Command | Origin | Writes attribution? |
|---|---|---|---|
| Public read-only workbench | `python -m medradar.product.web --port 8787` | http://127.0.0.1:8787 | **no** (no write route exists) |
| Internal review service (also serves the product) | `python -m medradar.product.review serve --port 8788` | http://127.0.0.1:8788 | yes, with the review token, loopback only |

The review service prints the token file path on start (`data/identity/review.token`). Open
http://127.0.0.1:8788/review and paste the token once.

## 4. Fixed-version snapshot

The product reads `medradar/product/snapshot/`:

* `snapshot.json` - id `2026-11-14T22:09:22Z-openfda`, collected 2026-11-14T22:09:22Z, openFDA last
  updated 2026-11-02, 258 requests, 1,335,152,376 response bytes.
* `events.jsonl.gz` - 91,457 records, sha256 `f2676ef7494467ae8256694c13c9da4a39b0da2c814c5d557c6dfb276c142971`
* `applicants.jsonl.gz` - 1,563 strings, sha256 `309a7cf4199fbb2f043b31e05b0de46a6260588b0a2cdb2e16ee3a4e2581f5fa`
* `classifications.jsonl.gz` - 7,098 product codes, sha256 `bbee2d1109abbbe5c70f97f08e7dbbd64462dec755b2b495de8e6a74e011e5db`

The data governance gate verifies those hashes against the inventory on every pull request
(`tools/governance/check_licence.py`). To run a different snapshot, pass `--data-dir` to either
server command; nothing else changes.

## 5. Demo walkthrough with real data (15 minutes)

1. **Overview** - read the five metrics. Note that Attributed Share (99.92%) and Curated Share
   (9.79%) are different answers to different questions; the "most records are provisional" banner
   says so in place.
2. **Search "Medtronic"** - open the organization page. The yellow banner states that part of the
   counts rests on unverified mappings; the attribution-confidence block gives the exact split.
3. **Scroll to Ownership** - see the Covidien relation with its 2015-01-26 effective date and the
   split of records filed before/after it.
4. **Regulatory events tab** - filter to recalls, open a row, read the evidence drawer: official ID,
   official FDA link, applicant string, verification status.
5. **Compare Medtronic vs GE HealthCare** - read the comparability verdict, then switch
   "Ownership basis" to "Original registrant only" and watch GE HealthCare drop to 0 records in the
   window: every record predates the 2023 spin-off. Switch back.
6. **Export** - download the Markdown report and the CSV; both state the basis, the verification
   table and the disclaimer.
7. **Chinese interface** - click 中文; the metrics, warnings and glossary are translated, not just
   the navigation.
8. **Identity review** - start the review service, open /review, paste the token, sort by records,
   open a case, append a decision, then look at the impact banner: one organization changed, all
   others are unchanged. Withdraw the decision and watch the previous state return.

## 6. Rollback

* The ledger is a file: `data/identity/review.db` (gitignored). Move it aside to start from a clean
  registry state; decisions can be re-imported from an export.
* Export before upgrading: `python -m medradar.product.review export --out review-backup.json`.
* To roll back the release, check out the previous tag/branch; the product reads only the committed
  snapshot, so no database migration is involved.
* To downgrade a single decision, append a withdrawal (never edit the database).

## 7. Version update

```bash
git fetch origin && git checkout <new-branch-or-tag>
python -m pip install -e ".[product]"
cd web && npm ci && npm run build && cd ..   # only if the UI changed
```

Record the snapshot id and the review ledger fingerprint before and after
(`GET /api/health` and `GET /api/review/stats`), so a change in counts can be attributed to the
right cause.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/api/health` returns `degraded` | snapshot directory missing or unreadable | check `medradar/product/snapshot/snapshot.json` exists; pass `--data-dir` |
| 503 `ui_not_built` | `web/dist` absent | `cd web && npm ci && npm run build` |
| `/review` shows "review service not reachable" | you are on the public app (:8787) | start the review service (:8788) and use that origin |
| 401 `review_token_required` | missing/stale token in sessionStorage | paste the token again from `data/identity/review.token` |
| 403 `review_not_local` | request did not come from the local machine | use the loopback origin; do not proxy the review service |
| `refusing to bind ... loopback-only` | `--host 0.0.0.0` | keep loopback, or pass `--allow-remote` only behind your own auth |
| Port already in use | another server | pass `--port` |

## 9. Limits and disclaimer

* Alpha software for professional evaluation, not a production system and not a medical, legal or
  investment advice product.
* Data is a frozen openFDA snapshot; it is not a live feed. Counts are regulatory records, not
  products, devices or innovations.
* Attribution is only 9.79% independently verified at record level; treat unverified counts as
  working assumptions.
* No claim of external user validation: no external alpha participant has tested this release yet
  (see `USER_TEST_TASKS.md`).
