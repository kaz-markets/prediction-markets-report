---
type: reference
title: "The report and how it is built"
description: "What the published report covers, and the measured build that produces it."
owner: dan
tags: [report, kalshi, polymarket, build]
timestamp: 2026-10-02T04:11:25Z
code: ["build/**"]
---

# The report and how it is built

An interactive report on everything Kalshi and Polymarket expose publicly: REST, WebSocket
and FIX surfaces, historical archives, published specs, rate limits, auth models and on-chain
data. Published at <https://kaz-markets.github.io/prediction-markets-report/>.

## Measured, not copied

Every figure was measured against both venues' anonymous public endpoints and embedded by
the build scripts. Nothing is transcribed from vendor documentation.

- Kalshi's open catalog actually counted, with a category split
- a real Kalshi order book and candlestick series
- a real Polymarket two-sided market with bids, asks, holders and trades
- live WebSocket frames from the Polymarket market and sports channels
- an anonymous Kalshi WebSocket handshake, attempted and recorded

Prices are shown in American odds alongside each venue's own probability.

## How a page is produced

`build/` holds one capture script per surface (`capture.py`, `capture_candles.py`,
`capture_poly.py`, `capture_ws.py` and the rest) writing JSON, and `render_plan.py` turns
`docs/PLAN.md` into the self-contained `docs/plan.html`. The renderer supports exactly the
constructs `PLAN.md` uses, so a change to that file has to stay inside them.

Pages is served from the repository root, which is why there is a `.nojekyll`.

## What it is next to

The plan in `docs/PLAN.md` describes the service in `kaz-markets/kaz-socket`. This repository
is the research and the plan; that repository is the build.
