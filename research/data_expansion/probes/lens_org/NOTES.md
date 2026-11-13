# lens_org — Lens.org (patent + scholarly API)

Probe: 2026-11-09, 4 requests, no token.

| probe | URL | status |
|---|---|---|
| api_docs | https://docs.api.lens.org/ | 200 |
| patent_api_terms_of_use | https://about.lens.org/lens-patent-api-terms-of-use/ | 403 |
| subscription_pricing_page | https://www.lens.org/lens/user/subscriptions | 200 |
| unauthenticated_api_search | https://api.lens.org/scholarly/search | 401 |

## Conclusion
- **PAID_ONLY**. The API returns `401` + `{"message":"Missing/Incorrect Authorization Header"}` without a bearer token.
- Lens' own *Lens Patent API Terms of Use* page was fetched successfully once at
  2026-11-09T05:39Z and contained the sentence:

  > "… Lens API service is only available through an institutional subscription. Individuals
  > are encouraged to approach their institutional librarian to take up a lens institutional
  > subscription."

  (Recorded verbatim here because a repeat request ~2 minutes later was answered `403` by the
  site's WAF — the page is real, the site is bot-hostile. The 403 is in the request ledger.)
- So: **paid institutional subscription, no free API tier.** Individual 'Lens Scholars'
  accounts are for the *website*, not the API.
- Licensing is at least as big a blocker as price: the API terms restrict redistribution of
  derived data, which conflicts with MedRadar keeping evidence reusable.
- The subscriptions page is public (see sample) but prices are quoted per institution, not
  published as a price list; requesting a quote is outside this round's rules.

## Doc links
- https://docs.api.lens.org/
- https://about.lens.org/lens-patent-api-terms-of-use/
