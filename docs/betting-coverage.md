# Betting coverage — a standard, and the router that speaks it

_Written 2026-10-04. Companion to this repo's venue survey. The design record for
`openbook-data-standards/openbook-betting` and `kaz-markets/kaz-routing-service`._

## What this is

The survey on this site measures what **Kalshi** and **Polymarket** give away for
**reading**: catalogs, order books, trade tapes, sockets, rate limits. This document is
about the other half — **betting out**. Placing a bet on a venue, and everything that can
happen to it afterwards.

Two things are needed, in this order:

1. **A standard** for betting coverage and bet execution, added to OpenBook as a profile.
2. **A service** in KAZ that routes a bet out through a plug-in adapter per venue and
   handles the whole lifecycle.

The first is a data contract; the second is the thing that speaks it.

## Why OpenBook needs a new profile

OpenBook is a **data** contract. Its own guide says it plainly: it is "only the data
contract. How a book prices, models, or hedges stays [proprietary]." It carries a venue's
quote so a reader can compare prices. It says nothing about

- **coverage** — what a venue will *accept*: which markets, what stake bounds, which order
  types, what it costs, and where it is allowed; or
- **execution** — an order that can be accepted, partially filled, refused, repriced,
  settled or voided.

Those are not fields on a quote, and they are not the same for any two venues. The standard
already anticipates this: its decision log, **Q172**, says new shapes live in their **own
profile repository** that pins a core major, beside the prediction-market and reporting
profiles. Betting coverage is that profile.

```
OpenBook core                 the public data wire (this site's survey)
  ├── openbook-betting        this profile: venue capability + bet execution
  ├── prediction-market       the scheduled profile for Kalshi / Polymarket as data
  └── reporting / integrity   later profiles
```

## The measured trading surface

Everything below is read from the survey on this site (`index.html`) and the venues'
published specs. It is what an adapter has to absorb.

### Kalshi — a regulated US event-contract exchange

| Property | Value |
| --- | --- |
| REST | `https://external-api.kalshi.com/trade-api/v2` (demo at `external-api.demo.kalshi.co`) |
| Auth | RSA-PSS or Ed25519; the **full request path** is signed, not the host or query |
| Rate limit | token buckets, Read / Write, **default cost 10 tokens**; `429` with **no `Retry-After`** |
| Tiers | Basic 200/100 · Advanced 300/300 · Expert 600/600 · Premier 1,200/1,200 · Paragon 2,400/2,400 · Prime 4,800/4,800 · Prestige 12,000/9,600 |
| Burst | above Basic, buckets hold **three seconds** of budget |
| Main constraint | **every authenticated call costs tokens from a bucket** |

**Order surfaces** (from the OpenAPI tag counts): `orders` (11 paths — create, amend,
decrease, cancel, batch, queue position), `order-groups` (rolling contract limits with
auto-cancel), `portfolio` (balance, positions, fills, settlements, deposits, withdrawals),
`account` (usage tier, per-endpoint token costs), `RFQ` (requests for quote, block trades),
`FCM` (subtrader caps and blocked categories), `subaccounts` (isolated balances).

**Private push** (WebSocket channels, user-scoped): `user_orders`, `fill`,
`market_positions`, `order_group_updates`. A complete **FIX session** is documented for
order entry — the surface an institutional participant would use instead of REST.

**Historical partition** matters for a router: settled markets, trades and completed orders
move to `/historical/*`, but **resting orders never move**. A reconciliation that reads only
`/historical/*` would miss every open order.

### Polymarket — a crypto-native venue

| Property | Value |
| --- | --- |
| Auth | **wallet signature, then HMAC-signed requests**; scoped, time-limited **session keys**; a Relayer submits gasless transactions |
| Trading | the **CLOB**, with a separate authenticated quoter socket for combos / RFQ |
| Order constraints | **minimum order 5**, tick **0.01** (measured on a live market) |
| Rate limit | **IP**-based, not a token bucket |
| Main constraint | **order placement is geoblocked** |

### The consequence for a router

The two venues differ on every axis that matters to placing a bet: auth model (signed path
vs wallet-then-HMAC), order model (amend / decrease / order groups vs CLOB limits), rate
limiting (token bucket vs IP), and jurisdiction (US-regulated vs geoblocked). No single
"place a bet" call fits both. That is exactly the surface a **profile plus an adapter
boundary** exists to absorb.

## The proposed standard — `openbook-betting`

A profile that pins a core major. It adds three object families and redefines no core
field.

### Reference tier

**`venue`** — a place to bet. The thing a core market's `source` points at, made explicit.

```
id            our id (publisher-own); the venue's own id rides on identifier
name
venueType     exchange | book | broker
region        the territory the venue operates in
authModel     signed-path | wallet-hmac | oauth | api-key | none
status        open | degraded | closed
```

**`coverage`** — what a venue accepts, and on what terms. Keyed to a venue. This is the
document an operator reads to know where a bet *can* go.

```
venue                 the venue id
tradeable             sports · leagues · marketTypes · segments · bases
limits                minOrder · maxOrder · minPosition · maxPosition · tick · currency
orderTypes            fill-or-kill · immediate-or-cancel · good-till-cancel ·
                      good-till-date · amend · decrease · cancel · batch · request-for-quote
fees                  the fee model
throttle              token-bucket{read,write,cost,burstSec} | ip{rate}
reach                 geoblock regions · market hours
updatedAt             coverage moves; this is its freshness
```

### Live tier

**`bet`** — one order and its lifecycle, referencing a core market outcome by the ids a
core market already carries (`fixture`, `marketType`, `segment`, `line`, `side`, `basis`).

```
id                    our id
clientOrderId         idempotency: a retry after a timeout never double-places
venue
fixture · marketType · segment · line · side · basis   the outcome, in core ids
stake
limitPrice            decimal odds (the core convention for a price)
timeInForce           fok | ioc | gtc | gtd(+expiry)
tolerance             the worst price we will still take before we re-quote or drop
correlationId         ties the bet to the intent that produced it
status                see below
filledStake
averageFillPrice
reason                present when the status is not a plain accept
```

Actions on the `bet` object reuse the core envelope vocabulary: `create` (submit),
`update` (amend / decrease / accept a new price), `delete` (cancel), `change` (any
lifecycle transition), and the control actions `snapshotComplete` and `heartbeat`.

### The lifecycle vocabulary — every possibility

A status, plus a reason where the status is not a clean accept. This is the set an
operator's screen has to render and a router has to handle.

| Status | Means |
| --- | --- |
| `accepted` | filled, in full |
| `partially-accepted` | some stake filled; the rest working or dropped |
| `working` | accepted and resting, not yet filled (Kalshi: never moves to historical) |
| `repriced` | the venue's price moved past our limit / tolerance; re-quote, re-confirm, or drop |
| `denied` | refused, with a reason (below) |
| `expired` | time-in-force elapsed unfilled |
| `cancelled` | we cancelled a resting order |
| `settled` | resolved: win or loss, with the payout |
| `partially-settled` | one leg of a multi-leg bet resolved |
| `voided` | the venue voided the market |
| `reconciled` | position and fill state read back after a reconnect or restart |

**Denial reasons** — a fixed set, so a screen and a retry policy both key off it:

```
price-changed       no-liquidity        market-suspended    market-closed
insufficient-funds  stake-below-min     stake-above-max     position-limit
risk-limit          geoblocked          rate-limited        auth-failed
duplicate           invalid-order       venue-unavailable   timeout
self-trade
```

Each reason carries a **default remedy** a router applies without a human:

| Reason | Remedy |
| --- | --- |
| `price-changed` | re-quote; accept within tolerance, else re-confirm |
| `no-liquidity` | try the next venue, or work the order |
| `market-suspended` / `market-closed` | drop; do not retry |
| `stake-below-min` / `stake-above-max` | clamp to coverage bounds, then retry once |
| `position-limit` / `risk-limit` | drop; it is a policy ceiling |
| `geoblocked` | drop; route to another venue |
| `rate-limited` | back off and retry (Kalshi gives no `Retry-After`, so back off blind) |
| `auth-failed` / `duplicate` / `invalid-order` | drop; these are bugs, not luck |
| `venue-unavailable` / `timeout` | retry with backoff, then reconcile |

## The KAZ router — `kaz-routing-service`

Its own service, in `kaz-markets`, because it grows (venues, order types, routing policy)
and because order placement concentrates **credentials, jurisdiction and money movement**
that should not sit in the feed edge or the platform. It also serves **market coverage**, so
the operator can see where a bet can go before sending it.

```
                         ┌───────────────────────────────┐
                         │  kaz-routing-service           │
   bet intent  ───────▶  │  router: policy · checks ·     │
                         │  idempotency · ledger · recon  │
                         └───────┬───────────────┬────────┘
                                 │               │
                    ┌────────────▼──┐      ┌─────▼──────────┐
                    │ Kalshi adapter │      │ Polymarket     │
                    │ signed path ·  │      │ adapter        │
                    │ token buckets  │      │ wallet+HMAC ·  │
                    │ amend/decrease │      │ CLOB · geo     │
                    └────────┬───────┘      └───────┬────────┘
                             ▼                      ▼
                          Kalshi                Polymarket
```

### The plug-in adapter

One adapter per venue; the router holds the policy, the adapter holds the venue's dialect.

```ts
interface BetOutAdapter {
  readonly venue: string;
  coverage(): Promise<Coverage>;                 // the OpenBook coverage document
  place(intent: BetIntent): Promise<Execution>;  // submit; returns a handle + first status
  amend(id: string, patch: BetPatch): Promise<Execution>;
  decrease(id: string, delta: Stake): Promise<Execution>;
  cancel(id: string): Promise<Execution>;
  status(id: string): Promise<Execution>;        // poll fallback
  subscribe(onExecution: (e: Execution) => void): () => void;  // push where the venue has it
  positions(): Promise<Position[]>;
  balance(): Promise<Balance>;
}
```

The path is always `create → accept | work | deny → (partial) → settle`. Each adapter
absorbs its venue: Kalshi's signed path, token buckets, amend/decrease and order groups;
Polymarket's wallet-then-HMAC, session keys, the relayer, the tick and minimum, and the
geoblock.

### The router

- **Routing policy** — pick the venue (or split) by coverage, price, limits and jurisdiction;
  fall back when the first choice is unavailable.
- **Pre-trade checks** — coverage, stake bounds, position and risk limits, geoblock, and the
  price tolerance, before anything is sent.
- **Idempotency** — one client order id per intent.
- **Rate-limit and error handling** — backoff, and the per-reason remedy above.
- **Reconciliation** — on connect and on a timer, read back open orders, positions and
  balances, because resting orders and private channels are what a restart loses.
- **Ledger** — orders, executions, positions, and the reconciliation state.
- **Coverage service** — serve each venue's `coverage` so the operator sees where a bet can
  go, and flag staleness.

### Integration

- **Prices** — the router reads the OpenBook wire from `kaz-socket` (the feed edge), never a
  venue directly, so a bet references the same ids the price came in on.
- **Contract** — the router's types are a new domain in `kaz-control/packages/api-contract`,
  so the platform consumes bet-out the way it consumes everything else.
- **Credentials** — only order placement needs venue keys; they live in the router, not the
  edge or the platform.

## Sequencing

1. **This report** — the design record.
2. **`openbook-betting`** — the `venue`, `coverage` and `bet` schemas, the lifecycle
   vocabulary, conformance cases, validated against the core validator.
3. **`kaz-routing-service`** — the adapter interface, the router core, the ledger, the
   reconciliation loop, a mock adapter, and the coverage service.
4. **Kalshi adapter**, then the **Polymarket adapter**, each shaped by the measured surface
   above (Kalshi's demo host first).
5. **Wire into the platform** — the router domain in the API contract, and the operator
   surface showing bets out and their outcomes.
