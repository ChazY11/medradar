# accessgudid - probe notes

- **status**: `VERIFIED_API`
- **run at**: `2026-11-08T21:51:09.518902Z`
- **requests made**: 4
- **evidence dirs**: `probes/accessgudid/`, `samples/accessgudid/`

## What was tested

Four requests: three `/api/v3/devices/lookup?di=` calls with real DIs for Medtronic, Dräger and Mindray, plus the same Medtronic DI through openFDA `/device/udi.json` for a direct comparison.

## Verdict

VERIFIED_API. The NLM lookup returns the GUDID record as JSON. The comparison settled the de-duplication question: **the same DI returns the same `publicDeviceRecordKey` (424a88d6-a714-4a49-a747-54abc7ba1259-shaped UUID) on both AccessGUDID and openFDA**, so the two interfaces publish one upstream record and must count as one evidence item.

## Time semantics (`event_at` vs `source_public_at`)

GUDID is the one device source with a real per-record publication date: `devicePublishDate` -> `source_public_at`, `quality="day"`. `publicVersionDate` is a **version stamp** and is kept only inside `normalized`, never used as a clock (verified by a test that asserts 2024-07-05 does not appear in any clock field).

## Cross-national product identity

Stable product ID: **yes** - the UDI-DI, an official identifier. Linkable to FDA 510(k)/PMA: **yes, officially** - GUDID `premarketSubmissions`/openFDA `premarket_submissions` names the K/PMA number (verified: DI 00643169718425 -> K973011). Linkable across countries: the DI is the *shared* identifier, but only MDALL exposes an endpoint that accepts one; EUDAMED/NMPA could not be tested, so cross-country DI matching currently works for exactly one non-US market (Canada).

## Request ledger

| probe | HTTP | bytes | elapsed ms | url |
|---|---|---|---|---|
| `lookup_medtronic_00643169718425` | 200 | 2987 | 797 | <https://accessgudid.nlm.nih.gov/api/v3/devices/lookup?di=00643169718425> |
| `lookup_draeger_04049098054089` | 200 | 2867 | 922 | <https://accessgudid.nlm.nih.gov/api/v3/devices/lookup?di=04049098054089> |
| `lookup_mindray_06944904092515` | 200 | 2648 | 750 | <https://accessgudid.nlm.nih.gov/api/v3/devices/lookup?di=06944904092515> |
| `openfda_udi_same_di` | 200 | 3677 | 1047 | <https://api.fda.gov/device/udi.json?search=identifiers.id%3A%2200643169718425%22&limit=1> |

## Probe-level note

AccessGUDID (NLM) /api/v3/devices/lookup?di= returns the GUDID record as JSON. GUDID is the upstream database that openFDA /device/udi.json re-publishes: the same DI yields the same publicDeviceRecordKey on both interfaces, so they are ONE evidence item, not two. GUDID publish_date is a real per-record first-publication date; public_version_date is a version stamp and must never be used as the first-publication date.

## Documentation opened

- download / release files: https://accessgudid.nlm.nih.gov/download
- lookup endpoint: https://accessgudid.nlm.nih.gov/api/v3/devices/lookup?di=00643169718425
- licence (FDA side): https://open.fda.gov/license/

## Caveats

- Every request above is in `requests.jsonl` (successes **and** failures); nothing here is reconstructed from memory.
- Samples under `samples/<source_id>/` are byte-for-byte response slices; `SAMPLES.json` records `sha256_full` for the complete body and `sha256_stored` for the stored part.
- A negative result is the deliverable in its own right: no status here was upgraded to make a source look usable.
