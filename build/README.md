# build

The toolchain that produces `../index.html`. Nothing here is published.

| Script | What it captures |
|---|---|
| `capture.py` | The full survey: both venues' public catalogs, plus a sample order book and trade tape |
| `capture_ws.py` | Live WebSocket frames from the Polymarket market and sports channels, and an anonymous Kalshi handshake attempt |
| `capture_counts.py` | Exact Kalshi catalog counts and the open-event category split |
| `capture_poly.py` | Polymarket detail plus a liquid two-sided market |
| `capture_poly_counts.py` | Gamma offset-pagination counts, used to show where offset paging stops |
| `capture_patch.py` | Fixed Data API v2 parameters |
| `capture_final.py` | Gamma keyset enumeration and a near-even Kalshi sports market |
| `capture_candles.py` | Candlesticks for the example market, via the series-scoped route |
| `render.py` | Turns all of the above into `../index.html` |

`*.json` here are cached captures, checked in so the published page is
reproducible. `specs/` holds the vendor OpenAPI and AsyncAPI documents and is
gitignored because it is large and re-fetchable.

No script authenticates. Anything that needs a key is out of scope by design,
which is the point of the survey.
