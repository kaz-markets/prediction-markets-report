# prediction-markets-report

An interactive report on everything **Kalshi** and **Polymarket** expose
publicly: REST, WebSocket and FIX surfaces, historical archives, published
specs, rate limits, auth models and on-chain data.

**Read it here:** https://kaz-markets.github.io/prediction-markets-report/

## What makes this different from the docs

Every figure in the report was measured, not copied. The build scripts query
both venues' anonymous public endpoints and embed the results:

- Kalshi's open catalog actually counted, with a category split
- a real Kalshi order book and candlestick series
- a real Polymarket two-sided market with bids, asks, holders and trades
- live WebSocket frames from the Polymarket market and sports channels
- an anonymous Kalshi WebSocket handshake, attempted and recorded

Prices are shown in American odds alongside each venue's own probability
quote, as a display convention.

## Headline finding

Kalshi's WebSocket rejected an anonymous handshake with `HTTP 401`, even for
channels that carry only public market data. Its REST market data needs no key
at all. Polymarket's market and sports sockets accepted anonymous connections
immediately. So a read-only consumer can stream Polymarket and must poll
Kalshi.

## Rebuilding

The report is generated, not hand-written. `index.html` is the only published
artifact; everything else is the toolchain that produces it.

```bash
python3 build/capture.py          # the full survey, several minutes
python3 build/capture_ws.py       # live WebSocket frames
python3 build/capture_counts.py   # exact Kalshi catalog counts
python3 build/capture_poly.py     # Polymarket detail and a focus market
python3 build/capture_poly_counts.py
python3 build/capture_patch.py
python3 build/capture_final.py    # Gamma keyset counts, Kalshi sports book
python3 build/render.py           # writes index.html
```

Requires Python 3.13 and `websockets` for the WebSocket capture. No
credentials are needed for any of it, and none are stored.

The survey scripts are deliberately tolerant: an endpoint that fails is
recorded in `errors` rather than aborting the run, and a page cap that trips
is reported honestly in the output as a trailing `+`.

## Cached captures

`build/*.json` are point-in-time captures. They are checked in so the report
can be regenerated without re-hitting the APIs, and so the numbers in the
published page are reproducible and auditable.

## Notes on sources

Endpoint inventories, rate-limit tables, auth models and channel lists come
from the two vendors' own published documentation and their OpenAPI and
AsyncAPI specs, all linked in the report's Sources section. Anything labelled
*captured* came from a live anonymous call.

## Licence

The report text and layout are mine. The underlying data belongs to Kalshi and
Polymarket respectively, and the API documentation belongs to each vendor.
