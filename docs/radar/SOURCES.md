# Sources, access verification and licensing

Every adapter in RADAR-001 was enabled only after its read path was fetched successfully by
this project's own user agent **and** its access policy was checked. The raw result is
committed at [`evidence/source_probe.json`](evidence/source_probe.json) and can be regenerated
with:

```
python scripts/radar_source_probe.py --out docs/radar/evidence/source_probe.json
```

The probe uses one honest identity on every request:

```
MedRadarBot/0.1 (+https://github.com/ChazY11/medradar; research; contact: repository owner) Python-urllib
```

It never spoofs a browser, never sends a cookie, never authenticates, never uses a proxy, and
never retries a refusal. A refusal is recorded and the adapter stays disabled.

## Status at the last probe

| Source | Adapter | Access | Decision |
| --- | --- | --- | --- |
| openFDA device (`/device/510k.json`, `/device/pma.json`) | `openfda.py` | documented public API, HTTP 200 | **ENABLED** |
| PubMed / NCBI E-utilities | `pubmed.py` | documented API, HTTP 200, 3 req/s without a key | **ENABLED** |
| Crossref REST | `crossref.py` | documented API, HTTP 200, `mailto` sent | **ENABLED** |
| Philips official news | `philips.py` | robots.txt read; news index and press pages HTTP 200 | **ENABLED** |
| Dräger official newsroom | `draeger.py` | robots.txt read; `NewsroomArticle.xml` HTTP 200 | **ENABLED** |
| GE HealthCare official newsroom | `gehealthcare.py` | **HTTP 403** on `robots.txt` and on the newsroom | **BLOCKED — disabled** |

### Why GE HealthCare is listed but never fetched

`www.gehealthcare.com` returns an Akamai "Access Denied" page to our user agent for
`robots.txt` itself. That is an operator decision. MedRadar:

* ships the adapter so the gap is visible;
* keeps it disabled, so no request is ever made;
* shows the restriction in the product as an access-policy state;
* never renders it as "no news found".

GE HealthCare's technology evidence is still present through FDA, PubMed and Crossref. What is
missing is only the vendor's own press releases, and the product states exactly that.

### Vendor-site rules this project follows

* `robots.txt` is read before any vendor page, and the adapter only requests paths the
  longest-match rule allows. For Philips, `/content/` and `/crsc/` are disallowed - the
  news RSS feed lives under `/content/`, so it is **not** used even though it would be
  convenient.
* One request every four seconds per vendor host (`rate_limit.requests_per_second: 0.25`).
* Only the headline, the publication timestamp, the canonical URL and a bounded excerpt are
  stored. Articles are never mirrored.
* No pagination beyond what the permitted index exposes. If the index is JavaScript-rendered,
  the adapter reports what it could see rather than reconstructing the archive.

## Licence statements

| Source | Licence basis | What MedRadar stores |
| --- | --- | --- |
| openFDA | openFDA terms; U.S. Government work, public domain | identifiers, titles, official URLs, record fields |
| PubMed | NCBI E-utilities usage guidelines; abstracts are public | PMID, title, journal, dates, authors, affiliations, abstract, DOI, MeSH |
| Crossref | Crossref REST API terms; metadata is open | DOI, title, container title, dates, authors, affiliations, abstract |
| Philips | site terms; press releases published for media use | headline, publication timestamp, URL, bounded excerpt |
| Dräger | site terms; newsroom articles published for media use | headline, sitemap `lastmod`, URL, bounded excerpt |

Each source's statement is machine-readable in `config/radar/sources.json` under `licence`.

## Cadence

| Source | Check interval | Basis |
| --- | --- | --- |
| openFDA | 24 h | openFDA declares monthly 510(k)/PMA and weekly recall refreshes; 24 h notices a version change without polling an unchanged dataset. The full 21-product-code sweep runs only when `meta.last_updated` changes. |
| PubMed | 6 h | indexing is continuous; this is the only source where a 6 h check can surface something the same day |
| Crossref | 12 h | deposits arrive continuously from publishers |
| Philips | 12 h | the index changes only when a release is published; 12 h is a politeness ceiling |
| Dräger | 12 h | the sitemap carries a per-article `lastmod`, so a cheap diff is enough |

A failing source is retried sooner than its cadence (down to a 15-minute floor) so a recovered
source is noticed, and its cursor is never advanced by a failed check.

## Adding a source

1. Write one module implementing `SourceAdapter` (`plan` / `fetch_page` / `map_record`).
2. Register it in `medradar/radar/adapters/__init__.py`.
3. Add an entry to `config/radar/sources.json` with the access verification, the licence and
   the cadence basis.
4. Run `python scripts/radar_source_probe.py` and commit the updated evidence.
5. If the operator refuses access, ship the adapter **disabled** with the reason.
