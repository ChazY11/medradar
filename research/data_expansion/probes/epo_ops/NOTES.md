# epo_ops — EPO Open Patent Services (OPS) 3.2

Probe: 2026-11-09, 4 requests, min_interval 0.8 s, **no credentials**.

| probe | URL | status |
|---|---|---|
| official_docs_page | https://www.epo.org/en/searching-for-patents/data/web-services/ops | 200 |
| unauthenticated_search | https://ops.epo.org/3.2/rest-services/published-data/search?q=ti%3D%22stent%22 | 403 |
| unauthenticated_family_lookup | https://ops.epo.org/3.2/rest-services/family/publication/docdb/EP.1000000.A1 | 403 |
| auth_token_endpoint_no_credentials | https://ops.epo.org/3.2/auth/accesstoken | 401 |

## Conclusion (empirical)
- **REQUIRES_REGISTRATION**. Both OPS REST calls were rejected with `403` and the body
  `<error><code>403</code><message>This request has been rejected due to the violation of
  Fair Use policy</message></error>`. The token endpoint also refused (no Basic credentials).
- The 403 wording is EPO's generic rejection for unauthenticated traffic; the documented
  contract is OAuth2 client-credentials, so a *credentialled* request is the only way to see
  whether the account quota is workable.

## What a free OPS account would give (documented, not observed)
- Free registration, 4 GB/month free tier, OAuth2 `client_credentials` flow:
  POST `https://ops.epo.org/3.2/auth/accesstoken` with HTTP Basic (consumer key/secret),
  ~20-minute bearer token.
- Services: `published-data` (search + biblio + full text), `family`, `legal`, `register`,
  `classification` (CPC). CQL query language (`ti=`, `pa=`, `ipc=`, `pd=`).
- Fields available: applicant name + address, inventor name + address, IPC/CPC,
  publication / filing / priority dates, INPADOC family, cited + citing documents.
  **This is the only surveyed source that offers family *and* citations *and* a real
  publication-date clock without a paid contract.**

## Time semantics (mandatory for any future connector)
OPS returns `date-publ`, `date-filing` and priority dates as distinct fields.
`source_public_at` MUST be `date-publ` (publication, normally 18 months after priority).
`event_at` may be the filing/priority date for invention-timeline work — but filing dates of
not-yet-published applications are *not* public and must never be used as an early signal.

## Doc links
- https://www.epo.org/en/searching-for-patents/data/web-services/ops
- OPS reference guide (v3.2) is linked from that page.
