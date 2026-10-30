# tests/fixtures/replay

`yahoo_chart_MDT_1m_sample.json` is a **synthetic** Yahoo `range=7d&interval=1m`
chart payload with the real response shape (epoch timestamps + parallel quote
arrays). It exists so the 1-minute parser can be tested offline; it is not real
market data and must never be used for a published number.
