# Synthetic governance fixtures

These files are deliberately fake. They exist so the licence gate's
content-classification tests can exercise restricted formats **without** any
third-party data:

* `fake_market.sqlite` — the SQLite magic header plus fake bytes, containing a
  synthetic marker string (`SYNTHETIC-RESTRICTED-TOKEN-42`) that tests assert is
  never echoed into gate logs.
* `fake_market.csv` — synthetic rows, one synthetic ticker.
* `fake_market.json` — synthetic JSON object.
* `fake_archive.gz` — the gzip magic header plus fake bytes.

No real market data, no real identifiers. The inventory classifies these as
`synthetic_fixtures`, which is the only source allowed to declare restricted
binary formats.
