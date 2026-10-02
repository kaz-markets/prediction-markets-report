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
| `capture_elections.py` | The US election slice: Kalshi election series and open markets, Polymarket election markets, and a measured tick rate from the public socket |
| `render.py` | Turns all of the above into `../index.html` |
| `render_plan.py` | Converts `../docs/PLAN.md` into the self-contained `../docs/plan.html` |

`*.json` here are cached captures, checked in so the published page is
reproducible. `specs/` holds the vendor OpenAPI and AsyncAPI documents and is
gitignored because it is large and re-fetchable.

## Rebuilding

```bash
python3 build/capture.py            # the full survey, several minutes
python3 build/capture_ws.py         # live WebSocket frames
python3 build/capture_counts.py     # exact Kalshi catalog counts
python3 build/capture_poly.py       # Polymarket detail and a focus market
python3 build/capture_poly_counts.py
python3 build/capture_patch.py
python3 build/capture_final.py      # Gamma keyset counts, Kalshi sports book
python3 build/capture_candles.py    # candlesticks, series-scoped route
python3 build/trim.py               # drop unused bulk from the caches
python3 build/capture_elections.py  # the US election slice and tick rate
python3 build/render.py             # writes index.html
python3 build/render_plan.py        # writes docs/plan.html from docs/PLAN.md
```

`docs/PLAN.md` is the source of `docs/plan.html`; edit the markdown and
re-run `render_plan.py` rather than editing the HTML.

No script authenticates. Anything that needs a key is out of scope by design,
which is the point of the survey.
