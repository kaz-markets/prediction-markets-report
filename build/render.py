"""Render the self-contained report from the captured data.

Reads everything under build/ and writes a single index.html with inline
CSS and inline SVG. Nothing external is referenced, so the page works
offline and on GitHub Pages unchanged.

Usage:
    python3 build/render.py
"""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUT_PATH = os.path.join(ROOT, "index.html")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def load(name: str) -> Any:
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError:
            return None


def esc(value: Any) -> str:
    if value is None or value == "":
        return "&mdash;"
    return html.escape(str(value))


def raw(value: Any, fallback: str = "&mdash;") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def number(value: Any, places: int = 0) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "&mdash;"
    return f"{numeric:,.{places}f}"


def money(value: Any, places: int = 0) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "&mdash;"
    return f"${numeric:,.{places}f}"


def compact(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "&mdash;"
    for scale, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(numeric) >= scale:
            return f"{numeric / scale:,.1f}{suffix}"
    return f"{numeric:,.0f}"


def probability_to_american(probability: float) -> str:
    """A prediction-market price as American odds."""
    if probability <= 0 or probability >= 1:
        return "&mdash;"
    if probability >= 0.5:
        return f"-{round(100 * probability / (1 - probability)):,}"
    return f"+{round(100 * (1 - probability) / probability):,}"


def to_american(value: Any) -> str:
    try:
        return probability_to_american(float(value))
    except (TypeError, ValueError):
        return "&mdash;"


def percent(value: Any, places: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{places}f}%"
    except (TypeError, ValueError):
        return "&mdash;"


def first_float(*values: Any) -> float | None:
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def table(headers: list[str], rows: list[list[str]], classes: str = "") -> str:
    head = "".join(f"<th>{header}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        f'<div class="table-wrap"><table class="{classes}">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def bar_chart(counts: dict[str, int] | None, limit: int = 12) -> str:
    if not counts:
        return "<p class='muted'>No data captured.</p>"
    items = sorted(counts.items(), key=lambda pair: -pair[1])[:limit]
    top = max(value for _, value in items) or 1
    rows = []
    for label, value in items:
        width = max(2.0, value / top * 100.0)
        rows.append(
            '<div class="bar-row">'
            f'<span class="bar-label" title="{esc(label)}">{esc(label)}</span>'
            '<span class="bar-track">'
            f'<span class="bar-fill" style="width:{width:.1f}%"></span>'
            "</span>"
            f'<span class="bar-value">{number(value)}</span>'
            "</div>"
        )
    return f'<div class="bars">{"".join(rows)}</div>'


def sparkline(points: list[tuple[float, float]], caption: str) -> str:
    if len(points) < 2:
        return "<p class='muted'>No price history returned.</p>"
    width, height, pad = 760, 170, 20
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = (max_x - min_x) or 1
    span_y = (max_y - min_y) or 1
    coordinates = []
    for x_value, y_value in points:
        cx = pad + (x_value - min_x) / span_x * (width - 2 * pad)
        cy = height - pad - (y_value - min_y) / span_y * (height - 2 * pad)
        coordinates.append(f"{cx:.1f},{cy:.1f}")
    polyline = " ".join(coordinates)
    area = f"{pad},{height - pad} {polyline} {width - pad},{height - pad}"
    return f"""<figure class="chart">
<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img"
     aria-label="Price history">
  <polygon points="{area}" class="spark-area"></polygon>
  <polyline points="{polyline}" class="spark-line"></polyline>
  <line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}"
        class="spark-axis"></line>
  <text x="{pad}" y="14" class="spark-text">high {percent(max_y)}</text>
  <text x="{pad}" y="{height - 6}" class="spark-text">low {percent(min_y)}</text>
</svg>
<figcaption>{esc(caption)}</figcaption>
</figure>"""


def code_block(text: str, label: str | None = None) -> str:
    caption = f'<div class="code-label">{esc(label)}</div>' if label else ""
    return (
        f'<div class="code">{caption}<pre><code>{esc(text)}</code></pre></div>'
    )


def json_block(payload: Any, label: str | None = None) -> str:
    return code_block(json.dumps(payload, indent=2), label)


def section(identifier: str, title: str, body: str, kicker: str = "") -> str:
    kicker_html = f'<p class="kicker">{kicker}</p>' if kicker else ""
    return (
        f'<section id="{identifier}">'
        f'{kicker_html}<h2>{title}</h2>{body}</section>'
    )


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


class Ctx:
    def __init__(self) -> None:
        self.data = load("data.json") or {}
        self.ws = load("ws_frames.json") or {}
        self.poly = load("poly_detail.json") or {}
        self.counts = load("counts.json") or {}
        self.final = load("final.json") or {}
        self.poly_counts = load("poly_counts.json") or {}
        self.elections = load("elections.json") or {}

        self.kalshi = self.data.get("kalshi") or {}
        self.polymarket = self.data.get("polymarket") or {}

    # Kalshi -------------------------------------------------------------
    @property
    def kalshi_series(self) -> int:
        return int((self.counts.get("series") or {}).get("count") or 0)

    @property
    def kalshi_events(self) -> int:
        return int((self.counts.get("open_events") or {}).get("count") or 0)

    @property
    def kalshi_events_complete(self) -> bool:
        return bool((self.counts.get("open_events") or {}).get("complete"))

    @property
    def kalshi_event_categories(self) -> dict[str, int]:
        return (self.counts.get("open_events") or {}).get("categories") or {}

    @property
    def kalshi_markets(self) -> int:
        return int((self.counts.get("open_markets") or {}).get("count") or 0)

    @property
    def kalshi_sports(self) -> int:
        return int(self.kalshi_event_categories.get("Sports") or 0)

    # Polymarket ---------------------------------------------------------
    @property
    def gamma_events(self) -> tuple[int, bool]:
        node = self.final.get("gamma_keyset_events") or {}
        if node.get("count"):
            return int(node["count"]), bool(node.get("complete"))
        return int(self.poly_counts.get("events_open_count") or 0), False

    @property
    def gamma_markets(self) -> tuple[int, bool]:
        node = self.final.get("gamma_keyset_markets") or {}
        if node.get("count"):
            return int(node["count"]), bool(node.get("complete"))
        return int(self.poly_counts.get("markets_open_count") or 0), False

    @property
    def global_open_interest(self) -> float | None:
        node = self.data.get("polymarket", {}).get("data_open_interest") or {}
        rows = node.get("data") or []
        if rows:
            return first_float(rows[0].get("value"))
        return None

    @property
    def focus(self) -> dict:
        return self.poly.get("focus") or {}

    @property
    def focus_market(self) -> dict:
        return self.focus.get("market") or {}


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def build_hero(ctx: Ctx) -> str:
    return f"""<header class="hero">
  <p class="eyebrow">Public data survey</p>
  <h1>Kalshi &amp; Polymarket</h1>
  <p class="lede">Everything both prediction markets expose publicly: REST,
  WebSocket, FIX, historical archives, published specs, rate limits, auth
  models and on-chain data. Figures marked <em>captured</em> were pulled from
  anonymous endpoints &mdash; no key, no account, no credential.</p>
  <dl class="meta">
    <div><dt>Captured</dt><dd>{esc(ctx.data.get('captured_at'))}</dd></div>
    <div><dt>Kalshi open markets</dt><dd>{number(ctx.kalshi_markets)}+</dd></div>
    <div><dt>Kalshi open events</dt><dd>{number(ctx.kalshi_events)}</dd></div>
    <div><dt>Polymarket open interest</dt><dd>{money(ctx.global_open_interest)}</dd></div>
  </dl>
  <p class="hero-link"><a href="docs/plan.html">Architecture plan for the feed
  service built on this survey &rarr;</a></p>
</header>"""


def build_verdict(ctx: Ctx) -> str:
    p = ctx.polymarket
    gamma_events, gamma_events_ok = ctx.gamma_events
    gamma_markets, gamma_markets_ok = ctx.gamma_markets

    surface_rows = [
        ["Market data (read)", "Open, no key", "Open, no key"],
        ["Historical archive", "Open for settled markets and trades", "Open, plus on-chain history"],
        [
            "<strong>Real-time stream</strong>",
            "<strong>Blocked</strong> &mdash; handshake needs a key",
            "<strong>Open</strong> &mdash; anonymous market and sports sockets",
        ],
        ["Trading", "RSA or Ed25519 signed requests", "Wallet signature, then HMAC-signed requests"],
        ["Published spec", "OpenAPI, AsyncAPI, perps specs", "OpenAPI and AsyncAPI per service"],
        [
            "Main constraint to design around",
            "Every authenticated call costs tokens from a bucket",
            "IP rate limits, and order placement is geoblocked",
        ],
    ]

    live_rows = [
        [
            "Open events",
            number(ctx.kalshi_events) + ("" if ctx.kalshi_events_complete else "+"),
            number(gamma_events) + ("" if gamma_events_ok else "+"),
        ],
        [
            "Open markets",
            number(ctx.kalshi_markets) + "+",
            number(gamma_markets) + ("" if gamma_markets_ok else "+"),
        ],
        [
            "Sports share",
            f"{number(ctx.kalshi_sports)} events ({percent(ctx.kalshi_sports / ctx.kalshi_events) if ctx.kalshi_events else '&mdash;'})",
            f"{number((p.get('sports') or {}).get('count'))} sport keys",
        ],
        [
            "Catalog",
            f"{number(ctx.kalshi_series)} series",
            f"{number((p.get('tags') or {}).get('count'))} tags",
        ],
        [
            "Open interest",
            "Returned per market and per event",
            money(ctx.global_open_interest),
        ],
    ]

    return section(
        "verdict",
        "What each venue actually gives away",
        f"""<div class="verdict">
  <div class="card">
    <h3>Both publish a real public API. They differ on one thing that matters.</h3>
    <p>Kalshi's <strong>market data is anonymous over REST</strong>, but its
    WebSocket rejected an anonymous handshake with <code>HTTP 401</code> in
    testing, even when asking for public market-data channels. Polymarket's
    market and sports sockets accepted anonymous connections immediately.</p>
    <p>The practical consequence: a read-only consumer can stream Polymarket
    and must poll Kalshi. Both give away the order book; neither gives away
    who is resting behind it.</p>
  </div>
  {table(["Property", "Kalshi", "Polymarket"], surface_rows)}
  <h3>What is actually there right now</h3>
  <p class="muted">Counted from anonymous calls at capture time. A trailing
  <code>+</code> means the survey stopped before the catalog ended.</p>
  {table(["Public catalog", "Kalshi", "Polymarket"], live_rows)}
</div>""",
        "Executive summary",
    )


def build_kalshi(ctx: Ctx) -> str:
    k = ctx.kalshi
    status = k.get("exchange_status") or {}
    shards = status.get("exchange_index_statuses") or []
    cutoff = k.get("historical_cutoff") or {}
    sports = k.get("filters_by_sport") or {}
    filters = sports.get("filters_by_sports") or {}
    ordering = sports.get("sport_ordering") or []

    shard_rows = [
        [
            esc(row.get("exchange_index")),
            esc(row.get("description")),
            "active" if row.get("exchange_active") else "inactive",
            "trading" if row.get("trading_active") else "halted",
            "yes" if row.get("intra_exchange_transfers_active") else "no",
        ]
        for row in shards
    ]

    hosts = [
        ["REST, production", "<code>https://external-api.kalshi.com/trade-api/v2</code>", "Recommended host. <code>api.elections.kalshi.com</code> still served."],
        ["REST, demo", "<code>https://external-api.demo.kalshi.co/trade-api/v2</code>", "Credentials are not shared with production."],
        ["WebSocket, production", "<code>wss://external-api-ws.kalshi.com/trade-api/ws/v2</code>", "Handshake requires an API key."],
        ["WebSocket, demo", "<code>wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2</code>", "Same requirement."],
        ["Private connectivity", "AWS PrivateLink", "Premier tier and above; VPC peering from Prime."],
    ]

    open_public = [
        ["Series", "<code>/series</code>, <code>/series/{ticker}</code>"],
        ["Events", "<code>/events</code>, <code>/events/{event_ticker}</code>, <code>/events/multivariate</code>"],
        ["Markets", "<code>/markets</code>, <code>/markets/{ticker}</code>"],
        ["Order book", "<code>/markets/{ticker}/orderbook</code>, multi-market variant"],
        ["Trade tape", "<code>/markets/trades</code>"],
        ["Candlesticks", "Per market, per event, and batch"],
        ["Exchange state", "<code>/exchange/status</code>, <code>/exchange/schedule</code>"],
        ["Search", "<code>/search/filters_by_sport</code>"],
        ["Historical", "<code>/historical/*</code>, including <code>/historical/cutoff</code>"],
        ["Milestones", "<code>/milestones</code>, <code>/milestones/{id}</code>"],
        ["Structured targets", "<code>/structured_targets</code>"],
        ["Live data", "Sport play-by-play, weather index, crypto and commodity series"],
    ]

    keyed = [
        ["Portfolio", "Balance, positions, fills, settlements, deposits, withdrawals"],
        ["Orders", "Create, amend, decrease, cancel, batch, queue position"],
        ["Order groups", "Rolling contract limits with auto-cancel"],
        ["API keys", "Create, generate, delete credentials"],
        ["Account", "Usage tier, limits, per-endpoint token costs"],
        ["RFQ", "Requests for quote, quotes, block trades"],
        ["FCM", "Member-level subtraders, caps, blocked categories"],
        ["Subaccounts", "Isolated balances within one account"],
    ]

    public_channels = [
        "ticker", "trade", "market_lifecycle_v2", "multivariate",
        "multivariate_market_lifecycle", "cfbenchmarks_value",
        "cfbenchmarks_value_5hz", "pyth_value",
    ]
    private_channels = [
        "orderbook_delta", "fill", "market_positions", "communications",
        "order_group_updates", "user_orders",
    ]

    tiers = [
        ["Basic", "200", "100", "Account signup"],
        ["Advanced", "300", "300", "Call the upgrade endpoint once"],
        ["Expert", "600", "600", "0.075% volume share"],
        ["Premier", "1,200", "1,200", "0.125% volume share"],
        ["Paragon", "2,400", "2,400", "0.25% volume share"],
        ["Prime", "4,800", "4,800", "0.50% volume share"],
        ["Prestige", "12,000", "9,600", "1.00% volume share"],
    ]

    orderbook_html = ""
    example = ctx.final.get("kalshi_sports_market") or {}
    book_payload = (example.get("orderbook") or {}).get("orderbook_fp") or {}
    yes_levels = book_payload.get("yes_dollars") or []
    no_levels = book_payload.get("no_dollars") or []

    best_yes = None
    if yes_levels:
        try:
            best_yes = max(str(row[0]) for row in yes_levels)
        except (IndexError, TypeError):
            best_yes = None

    if example and (yes_levels or no_levels):

        def render_levels(rows: list, descending: bool) -> str:
            parsed = []
            for row in rows:
                try:
                    parsed.append((float(row[0]), str(row[0]), row[1]))
                except (IndexError, TypeError, ValueError):
                    continue
            parsed.sort(key=lambda item: item[0], reverse=descending)
            out = []
            for _, price_text, size in parsed[:8]:
                out.append(
                    f"<tr><td class='num'>{esc(price_text)}</td>"
                    f"<td>{to_american(price_text)}</td>"
                    f"<td class='num'>{number(size)}</td></tr>"
                )
            return "".join(out)

        orderbook_html = f"""
        <h4>Live order book &mdash; <code>{esc(example.get('ticker'))}</code></h4>
        <p class="muted">{esc((example.get('title') or '')[:140])}</p>
        <dl class="meta">
          <div><dt>Yes bid / ask</dt><dd>{esc(example.get('yes_bid'))} / {esc(example.get('yes_ask'))}</dd></div>
          <div><dt>American</dt><dd>{to_american(example.get('yes_bid'))} / {to_american(example.get('yes_ask'))}</dd></div>
          <div><dt>Volume</dt><dd>{number(example.get('volume'))}</dd></div>
          <div><dt>Open interest</dt><dd>{number(example.get('open_interest'))}</dd></div>
        </dl>
        <div class="two-col">
          <div><h5>Yes bids, best first</h5><div class="table-wrap"><table>
            <thead><tr><th>Price</th><th>American</th><th>Size</th></tr></thead>
            <tbody>{render_levels(yes_levels, True)}</tbody></table></div></div>
          <div><h5>No bids, best first</h5><div class="table-wrap"><table>
            <thead><tr><th>Price</th><th>American</th><th>Size</th></tr></thead>
            <tbody>{render_levels(no_levels, True)}</tbody></table></div></div>
        </div>
        <p class="note">Bids only, and the API returns them ascending, so the
        best price is the last row of raw output and the first row here. A yes
        bid at <em>x</em> is a no ask at
        <em>1&nbsp;&minus;&nbsp;x</em>, so the two columns fully describe the
        book. The best yes bid of {esc(best_yes)} implies a no ask at
        {esc(round(1 - float(best_yes), 2) if best_yes else '')}, which is what
        the no side shows.</p>
        """

    candles_by_interval = example.get("candlesticks") or {}
    candle_points: list[tuple[float, float]] = []
    candle_interval = None
    for interval in ("60", "1440"):
        node = candles_by_interval.get(interval) or {}
        rows = node.get("candlesticks") or []
        points: list[tuple[float, float]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            price_node = row.get("price")
            close = None
            if isinstance(price_node, dict):
                close = first_float(price_node.get("close_dollars"))
            if close is None:
                close = first_float(row.get("yes_price_dollars"))
            timestamp = first_float(row.get("end_period_ts"))
            if close is not None and timestamp is not None:
                points.append((timestamp, close))
        if len(points) > 2:
            candle_points = points
            candle_interval = interval
            break

    candles_html = ""
    if candle_points and candle_interval:
        label = "hourly" if candle_interval == "60" else "daily"
        candles_html = (
            f"<h4>Price history, {label} close</h4>"
            + sparkline(
                candle_points,
                f"{len(candle_points)} {label} candles from "
                "<code>/series/{series_ticker}/markets/{ticker}/candlesticks"
                "</code>&nbsp;&mdash; the series segment is required",
            )
        )

    return section(
        "kalshi",
        "Kalshi",
        f"""
    <p class="lede">A CFTC-regulated US event-contract exchange. Market data
    is anonymous over REST; the WebSocket is not. Everything below was either
    read from the published documentation or captured live without
    credentials.</p>

    <h3>Endpoints</h3>
    {table(["Surface", "Host", "Note"], hosts)}

    <h3>What an anonymous caller can read</h3>
    {table(["Group", "Endpoints"], open_public)}

    <h3>What needs a key</h3>
    {table(["Group", "Covers"], keyed)}

    <h3>REST surface by tag</h3>
    <p class="muted">Counted from the published OpenAPI document.</p>
    {bar_chart(ctx.data.get('kalshi_tags'), 18)}

    <h3>Authentication</h3>
    <p>Requests are signed with an RSA-PSS or Ed25519 key pair. Sign the full
    request path from the API root, <strong>without</strong> query parameters.
    The host is not part of the signature, which is why the two production
    hosts are interchangeable for a signed client.</p>
    {code_block("POST https://external-api.kalshi.com/trade-api/v2/portfolio/orders?limit=5", "Request")}
    {code_block("/trade-api/v2/portfolio/orders", "What gets signed")}

    <h3>WebSocket</h3>
    <p>One connection, many channels, subscribed by <code>market_tickers</code>.
    The connection requires credentials before any channel becomes usable.</p>
    {table(
        ["Channel", "What it carries"],
        [[f"<code>{channel}</code>", "Public market data, authenticated connection"]
         for channel in public_channels]
        + [[f"<code>{channel}</code>", "Private, user-scoped"]
           for channel in private_channels],
    )}
    {code_block('{"id": 1, "cmd": "subscribe", "params": {"channels": ["ticker", "trade"], "market_tickers": ["KXBTCD-25AUG0517-T114999.99"]}}', "Subscribe frame")}

    <h3>FIX</h3>
    <p>A complete FIX session is documented beside REST and WebSocket: order
    entry, market data, drop copy, listener sessions, settlement reports and
    error handling. This is the surface an institutional participant would
    use instead of REST.</p>

    <h3>Perps (margin)</h3>
    <p>A separate exchange with its own REST, WebSocket and FIX documentation,
    its own token buckets, and 39 documented REST paths. Funding rates, mark
    price, index price, liquidation mechanics and exit triggers are all
    public.</p>

    <h3>Historical data</h3>
    <p>Live and historical are partitioned, and each data type has its own
    cutoff, published at <code>/historical/cutoff</code>. Settled markets,
    trades and completed orders move out of the live endpoints into
    <code>/historical/*</code>. Resting orders never move.</p>
    {table(
        ["Field", "Partitions by", "Meaning"],
        [
            ["<code>market_settled_ts</code>", "Market settlement", "Markets and candlesticks older than this are historical only"],
            ["<code>trades_created_ts</code>", "Trade fill time", "Trades and fills older than this are historical only"],
            ["<code>orders_updated_ts</code>", "Cancel or execution", "Completed and cancelled orders move; resting orders do not"],
            ["<code>market_positions_last_updated_ts</code>", "Position update", "A backfill horizon, not the moment a position appears"],
        ],
    )}
    <h4>Cutoff at capture</h4>
    {json_block(cutoff)}
    <p class="note">Two route quirks worth knowing. The live candlestick
    endpoint is
    <code>/series/{{series_ticker}}/markets/{{ticker}}/candlesticks</code>
    &mdash; drop the series segment and it returns <code>404</code>, not a
    helpful error. And a candlestick's prices are nested under
    <code>price</code> as <code>close_dollars</code>, <code>high_dollars</code>
    and friends, so a reader expecting a flat <code>yes_price</code> field gets
    nothing.</p>

    <h3>Rate limits</h3>
    <p>Authenticated calls cost tokens from a Read or a Write bucket that
    refills continuously. The default cost is 10 tokens. Batch endpoints bill
    every item separately, and a rate-limited call returns <code>429</code>
    with no <code>Retry-After</code> header.</p>
    {table(["Tier", "Read / sec", "Write / sec", "How it is earned"], tiers)}
    <p class="note">Above Basic, buckets hold three seconds of budget, so an
    idle client can burst to three times its rate. Predictions and Perps are
    metered separately, and single-order writes can be billed to a per-shard
    bucket.</p>

    <h3>Exchange sharding</h3>
    {table(["Index", "Description", "Exchange", "Trading", "Transfers"], shard_rows)}

    <h3>Open catalog at capture</h3>
    {table(
        ["Measure", "Value", "Complete"],
        [
            ["Series", number(ctx.kalshi_series), "yes"],
            ["Open events", number(ctx.kalshi_events), "yes" if ctx.kalshi_events_complete else "no"],
            ["Open markets", number(ctx.kalshi_markets), "no, survey budget reached"],
            ["Sports events", number(ctx.kalshi_sports), "yes"],
        ],
    )}
    <h4>Open events by category</h4>
    {bar_chart(ctx.kalshi_event_categories, 12)}

    <h3>Sports coverage</h3>
    <p><code>/search/filters_by_sport</code> returned {esc(len(filters))}
    sport groups with their scopes and competitions, plus a display ordering.</p>
    <p class="chip-row">{"".join(f'<span class="chip">{esc(name)}</span>' for name in ordering)}</p>

    <h3>Order book, with a real sports market</h3>
    {orderbook_html or "<p class='muted'>Order book not captured.</p>"}
    {candles_html}

    <h3>Fees</h3>
    <p>Fees are published per series with per-event overrides
    (<code>/series/{{ticker}}/fee_changes</code>,
    <code>/events/{{event_ticker}}/fee_changes</code>) and a documented rounding
    rule. Perps fees are a separate schedule again.</p>
    """,
        "Regulated US event-contract exchange",
    )


def build_polymarket(ctx: Ctx) -> str:
    p = ctx.polymarket
    focus = ctx.focus
    market = ctx.focus_market

    hosts = [
        ["Gamma", "<code>https://gamma-api.polymarket.com</code>", "Discovery: events, markets, tags, series, comments, search, sports"],
        ["CLOB", "<code>https://clob.polymarket.com</code>", "Prices, order books, history, order placement"],
        ["Data", "<code>https://data-api.polymarket.com</code>", "Positions, activity, trades, open interest, leaderboards"],
        ["Relayer", "<code>https://relayer-v2.polymarket.com</code>", "Submit wallet transactions without holding gas"],
        ["Bridge", "<code>https://bridge.polymarket.com</code>", "Deposit and withdraw across chains"],
        ["Market socket", "<code>wss://ws-subscriptions-clob.polymarket.com/ws/market</code>", "Public order book, price, lifecycle"],
        ["User socket", "<code>wss://ws-subscriptions-clob.polymarket.com/ws/user</code>", "Authenticated order and trade updates"],
        ["Live data", "<code>wss://ws-live-data.polymarket.com</code>", "Reference prices, comments, trade activity"],
        ["Sports socket", "<code>wss://sports-api.polymarket.com/ws</code>", "Public live scores, no subscription needed"],
    ]

    catalogs = [
        ["Events", "List, keyset list, by id, by slug, tags"],
        ["Markets", "List, keyset list, by id, by slug, by token, simplified, sampling"],
        ["Reference", "Tags, related tags, series, sports metadata, valid market types, teams"],
        ["Discovery", "Public search across markets, events and profiles; comments; profiles"],
    ]

    clob_reads = [
        ["<code>/book</code>, <code>/books</code>", "Order book, one or many tokens"],
        ["<code>/price</code>, <code>/prices</code>", "Best bid or ask"],
        ["<code>/midpoint</code>, <code>/midpoints</code>", "Mid price"],
        ["<code>/spread</code>, <code>/spreads</code>", "Bid-ask spread"],
        ["<code>/last-trade-price</code>", "Last traded price and side"],
        ["<code>/prices-history</code>", "Historical series, batched"],
        ["<code>/tick-size</code>, <code>/fee-rate</code>", "Market constraints"],
        ["<code>/markets/{condition_id}</code>", "Every CLOB parameter in one call"],
        ["<code>/time</code>, <code>/ok</code>", "Server time and health"],
    ]

    data_surface = [
        ["<code>/v2/positions</code>", "Open, closed and market-scoped positions"],
        ["<code>/v2/activity</code>", "Trades, splits, merges, redeems"],
        ["<code>/v2/trades</code>", "Market trade tape"],
        ["<code>/v2/oi</code>", "Open interest, global or per condition"],
        ["<code>/v2/holders</code>", "Top holders per market"],
        ["<code>/v2/leaderboard</code>", "Ranked realized PnL"],
        ["<code>/v2/user-pnl</code>, <code>/v2/user-stats</code>, <code>/v2/user-volume</code>", "Per-wallet performance"],
        ["<code>/v2/biggest-winners</code>", "Largest single winning positions"],
        ["<code>/v2/builders/*</code>", "Builder volume leaderboard and time series"],
        ["<code>/v2/resolutions</code>", "Resolution state"],
        ["<code>/v2/positions/combos</code>, <code>/v2/activity/combos</code>", "Multi-leg positions"],
        ["<code>/v2/approvals</code>, <code>/v2/value</code>", "Wallet approvals, portfolio value"],
    ]

    auth_rows = [
        ["L1", "The wallet signs an EIP-712 <code>ClobAuth</code> message", "Proves control of the address, creates or derives credentials"],
        ["L2", "API credentials sign the request with HMAC-SHA256", "Authenticates private CLOB calls"],
    ]

    headers = [
        ["<code>POLY_ADDRESS</code>", "Polygon signer address"],
        ["<code>POLY_SIGNATURE</code>", "L2 HMAC-SHA256 signature"],
        ["<code>POLY_TIMESTAMP</code>", "Unix seconds used in the signature"],
        ["<code>POLY_API_KEY</code>", "Credential identifier"],
        ["<code>POLY_PASSPHRASE</code>", "Credential passphrase"],
    ]

    live_rows = []
    for label, key in (("First outcome", "outcome_1"), ("Second outcome", "outcome_2")):
        detail = focus.get(key) or {}
        book = detail.get("book") or {}
        live_rows.append(
            [
                esc(label),
                esc((detail.get("price_buy") or {}).get("price")),
                esc((detail.get("price_sell") or {}).get("price")),
                esc((detail.get("midpoint") or {}).get("mid")),
                esc((detail.get("spread") or {}).get("spread")),
                f"{len(book.get('bids') or [])} / {len(book.get('asks') or [])}",
            ]
        )

    def render_book(levels: list, side: str) -> str:
        rows = []
        for row in (levels or [])[:8]:
            if not isinstance(row, dict):
                continue
            rows.append(
                f"<tr><td class='num'>{esc(row.get('price'))}</td>"
                f"<td>{to_american(row.get('price'))}</td>"
                f"<td class='num'>{number(row.get('size'), 1)}</td></tr>"
            )
        if not rows:
            return f"<p class='muted'>No {side} levels returned.</p>"
        return (
            "<div class='table-wrap'><table>"
            "<thead><tr><th>Price</th><th>American</th><th>Size</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )

    outcome_1 = focus.get("outcome_1") or {}
    history = (outcome_1.get("prices_history") or {}).get("history") or []
    history_points = []
    for row in history:
        if not isinstance(row, dict):
            continue
        point_t = first_float(row.get("t"))
        point_p = first_float(row.get("p"))
        if point_t is not None and point_p is not None:
            history_points.append((point_t, point_p))

    holders = (focus.get("data_holders") or {}).get("data") or []
    holder_rows = []
    if holders and isinstance(holders[0], dict):
        for holder in (holders[0].get("holders") or [])[:8]:
            holder_rows.append(
                [
                    esc(str(holder.get("proxy_wallet") or "")[:14] + "..." if holder.get("proxy_wallet") else None),
                    esc(holder.get("outcome")),
                    number(holder.get("amount"), 1),
                ]
            )

    trades = (focus.get("data_trades") or {}).get("data") or []
    trade_rows = [
        [
            esc(row.get("side")),
            esc(row.get("outcome")),
            esc(row.get("price")),
            to_american(row.get("price")),
            number(row.get("size"), 1),
            esc(str(row.get("timestamp") or "")[:19]),
        ]
        for row in trades[:8]
        if isinstance(row, dict)
    ]

    leaders = (p.get("data_leaderboard") or {}).get("data") or []
    leader_rows = [
        [
            esc(row.get("rank")),
            esc(row.get("user_name")),
            money(row.get("pnl"), 0),
            money(row.get("volume"), 0),
        ]
        for row in leaders[:8]
        if isinstance(row, dict)
    ]

    sports_rows = [
        [esc(row.get("sport")), esc(row.get("tags"))]
        for row in (p.get("sports") or {}).get("sample", [])[:12]
        if isinstance(row, dict)
    ]

    tags_chips = "".join(
        f'<span class="chip">{esc(row.get("label"))}</span>'
        for row in (p.get("tags") or {}).get("sample", [])[:24]
        if isinstance(row, dict)
    )

    ws_sports = ctx.ws.get("sports") or {}
    sports_frames = ws_sports.get("frames") or []
    sports_example = json.dumps(sports_frames[0], indent=2) if sports_frames else "{}"

    ws_clob = ctx.ws.get("clob_market") or {}
    clob_frames = ws_clob.get("frames") or []
    clob_example = json.dumps(clob_frames[0], indent=2) if clob_frames else "{}"
    if len(clob_example) > 1200:
        clob_example = clob_example[:1200] + "\n  ..."

    gamma_events, gamma_events_ok = ctx.gamma_events
    gamma_markets, gamma_markets_ok = ctx.gamma_markets
    focus_oi = ((focus.get("data_open_interest") or {}).get("data") or [{}])[0].get("value")

    outcome_prices = market.get("outcome_prices") or []
    outcome_names = market.get("outcomes") or []
    american_row = ""
    if outcome_names and outcome_prices:
        american_row = " ".join(
            f"<span class='chip'>{esc(name)} {esc(price)} &rarr; {to_american(price)}</span>"
            for name, price in zip(outcome_names, outcome_prices)
        )

    return section(
        "polymarket",
        "Polymarket",
        f"""
    <p class="lede">The larger of the two and the more permissive for a data
    consumer. Discovery, pricing, analytics and live scores are all anonymous.
    Only order placement needs credentials, and that is geoblocked. There is a
    separate US documentation set at <code>docs.polymarket.us</code>.</p>

    <h3>Endpoints</h3>
    {table(["Service", "Host", "Covers"], hosts)}

    <h3>Gamma &mdash; discovery and metadata</h3>
    {table(["Group", "Endpoints"], catalogs)}
    <p class="note">Gamma offers two pagination styles. <strong>Offset</strong>
    (<code>limit</code> and <code>offset</code>) works for shallow paging but
    caps out in practice &mdash; a survey walk stopped at 2,100 events and 500
    markets. <strong>Keyset</strong>
    (<code>/events/keyset</code>, <code>/markets/keyset</code>) returns a
    <code>next_cursor</code> and enumerates fully. Use keyset for anything
    that must be complete; the documentation says the same and rejects
    <code>offset</code> on those routes.</p>

    <h3>CLOB &mdash; pricing and trading</h3>
    {table(["Endpoint", "Returns"], clob_reads)}

    <h3>Data API &mdash; activity and analytics</h3>
    <p>Version 2 is a rewrite with a shared <code>{{data, pagination}}</code>
    envelope and cursor pagination. Version 1 routes still work. The filters
    are literal: passing <code>market</code> where the API wants
    <code>condition_id</code> returns a 400 that names the correct parameter,
    which is how this survey found it.</p>
    {table(["Endpoint", "Returns"], data_surface)}

    <h3>Authentication</h3>
    {table(["Layer", "Mechanism", "Purpose"], auth_rows)}
    {table(["Header", "Value"], headers)}
    {code_block("message = timestamp + METHOD + path\\nsignature = urlsafeBase64WithPadding(HMAC-SHA256(base64Decode(api_secret), message))", "L2 signing")}

    <h3>WebSocket</h3>
    <p>The market channel is public and subscribes by outcome token id. The
    sports channel needs no subscription at all &mdash; connect and read.</p>
    {code_block('{"assets_ids": ["<token_id>"], "type": "market"}', "Market channel subscribe")}
    <h4>Market channel, captured live</h4>
    <p class="muted">{esc(ws_clob.get('frame_count'))} frames in the capture
    window. First frame, an order book snapshot:</p>
    {code_block(clob_example, "book")}
    <h4>Sports channel, captured live</h4>
    <p class="muted">{esc(ws_sports.get('frame_count'))} frames in the capture
    window, carrying live match state with no subscription.</p>
    {code_block(sports_example, "sports update")}

    <h3>On-chain data</h3>
    <p>Every trade settles on Polygon, so the full history is reconstructible
    independently of the API. Polymarket points at Goldsky for streaming
    pipelines and Dune, Allium and CryptoHouse for SQL. Contract addresses and
    audits are published.</p>

    <h3>Rate limits</h3>
    <p>IP-based, enforced by Cloudflare. Over-limit requests are throttled
    rather than rejected, and windows slide. Trading endpoints additionally
    apply per-signer token buckets.</p>
    {table(
        ["Service", "Endpoint", "Limit"],
        [
            ["Gamma", "General", "4,000 req / 10s"],
            ["Gamma", "<code>/events</code>", "500 req / 10s"],
            ["Gamma", "<code>/markets</code>", "300 req / 10s"],
            ["CLOB", "General", "9,000 req / 10s"],
            ["CLOB", "<code>/book</code>, <code>/price</code>, <code>/midpoint</code>", "1,500 req / 10s"],
            ["CLOB", "<code>/prices-history</code>", "1,000 req / 10s"],
            ["CLOB", "<code>POST /order</code>", "5,000 req / 10s burst, 120,000 / 10 min sustained"],
            ["Data v2", "General", "800 req / 10s"],
            ["Data v2", "<code>/v2/trades</code>", "300 req / 10s"],
            ["Data v2", "<code>/v2/positions</code>", "200 req / 10s"],
            ["Bridge", "General", "50 req / 10s"],
            ["Relayer", "<code>/submit</code>", "25 req / 1 min"],
        ],
    )}

    <h3>REST surface</h3>
    <p class="muted">Documented paths per service, counted from the published
    specs.</p>
    {bar_chart(ctx.data.get('poly_paths_by_service'), 8)}

    <h3>Programs that pay participants</h3>
    <p class="muted">Taker rebates, maker rebates, liquidity rewards and a
    referral program are all documented, with a separate builder program for
    applications that route orders.</p>

    <h3>Wallets, keys and positioning</h3>
    <p>Session keys authorize a separate signer for scoped, time-limited
    trading. The Relayer submits supported transactions so a wallet does not
    need POL for gas. Combos add a request-for-quote flow for multi-leg
    positions, with its own authenticated quoter socket.</p>

    <h3>Catalog at capture</h3>
    {table(
        ["Measure", "Value"],
        [
            ["Sports with metadata", number((p.get("sports") or {}).get("count"))],
            ["Tags", number((p.get("tags") or {}).get("count"))],
            ["Gamma open events", number(gamma_events) + ("" if gamma_events_ok else "+")],
            ["Gamma open markets", number(gamma_markets) + ("" if gamma_markets_ok else "+")],
            ["Global open interest", money(ctx.global_open_interest)],
        ],
    )}
    <h4>Tags seen</h4>
    <p class="chip-row">{tags_chips}</p>

    <h3>Worked example &mdash; a live two-sided market</h3>
    <p class="focus-question">{esc(market.get('question'))}</p>
    <p class="chip-row">{american_row}</p>
    <dl class="meta">
      <div><dt>Volume</dt><dd>{money(market.get('volume'))}</dd></div>
      <div><dt>Liquidity</dt><dd>{money(market.get('liquidity'))}</dd></div>
      <div><dt>Open interest</dt><dd>{money(focus_oi)}</dd></div>
      <div><dt>Tick size</dt><dd>{esc(market.get('tick_size'))}</dd></div>
      <div><dt>Closes</dt><dd>{esc(str(market.get('end_date'))[:10])}</dd></div>
      <div><dt>Minimum order</dt><dd>{esc(market.get('minimum_order_size'))}</dd></div>
    </dl>
    {table(["Outcome", "Best buy", "Best sell", "Midpoint", "Spread", "Bid / ask levels"], live_rows)}
    <div class="two-col">
      <div><h4>Bids</h4>{render_book((outcome_1.get('book') or {}).get('bids'), 'bid')}</div>
      <div><h4>Asks</h4>{render_book((outcome_1.get('book') or {}).get('asks'), 'ask')}</div>
    </div>
    <h4>Price history</h4>
    {sparkline(history_points, f"{len(history_points)} points from /prices-history, last {percent(history_points[-1][1]) if history_points else 'n/a'}")}
    <h4>Top holders</h4>
    {table(["Wallet", "Outcome", "Amount"], holder_rows) if holder_rows else "<p class='muted'>No holders returned.</p>"}
    <h4>Recent trades on this market</h4>
    {table(["Side", "Outcome", "Price", "American", "Size", "Time"], trade_rows) if trade_rows else "<p class='muted'>No trades returned.</p>"}

    <h3>Trader leaderboard at capture</h3>
    {table(["Rank", "Name", "Realized PnL", "Volume"], leader_rows)}

    <h3>Sports metadata</h3>
    {table(["Sport key", "Tag ids"], sports_rows)}
    """,
        "On-chain prediction market",
    )


def build_live(ctx: Ctx) -> str:
    k = ctx.kalshi
    ws = ctx.ws
    kalshi_ws = ws.get("kalshi_unauthenticated_ws") or {}
    gamma_events, gamma_events_ok = ctx.gamma_events
    gamma_markets, gamma_markets_ok = ctx.gamma_markets

    probe = "<p class='muted'>Socket probe not captured.</p>"
    if kalshi_ws:
        probe = f"""
        <p>The probe connected to Kalshi's production socket with no
        credentials and sent a well-formed subscribe frame for the public
        <code>ticker</code> channel.</p>
        {table(
            ["Result", "Detail"],
            [
                ["Handshake accepted", "no" if not kalshi_ws.get("connected") else "yes"],
                ["Server response", f"<code>{esc(kalshi_ws.get('error'))}</code>"],
            ],
        )}
        <p class="note">HTTP 401 during the WebSocket upgrade. The connection
        itself is authenticated, so no channel is reachable anonymously &mdash;
        not even the public market-data channels. A purely read-only consumer
        must either hold a key or poll REST.</p>
        """

    rows = [
        ["Kalshi exchange active", esc((k.get("exchange_status") or {}).get("exchange_active"))],
        ["Kalshi exchange shards", number(len((k.get("exchange_status") or {}).get("exchange_index_statuses") or []))],
        ["Kalshi series", number(ctx.kalshi_series)],
        ["Kalshi open events", number(ctx.kalshi_events)],
        ["Kalshi open markets", number(ctx.kalshi_markets) + " (budget reached)"],
        ["Kalshi sports events", number(ctx.kalshi_sports)],
        ["Polymarket open events", number(gamma_events) + ("" if gamma_events_ok else "+")],
        ["Polymarket open markets", number(gamma_markets) + ("" if gamma_markets_ok else "+")],
        ["Polymarket global open interest", money(ctx.global_open_interest)],
        ["Polymarket sports keys", number((ctx.polymarket.get("sports") or {}).get("count"))],
    ]

    return section(
        "live",
        "Live probe results",
        f"""
        <p class="lede">Every figure on this page came from an anonymous public
        endpoint. Nothing required a key, an account or a credential.</p>
        <p class="muted">Captured {esc(ctx.data.get('captured_at'))}. These are
        point-in-time snapshots, not live values.</p>
        {table(["Measure", "Value"], rows)}
        <h3>Kalshi WebSocket, attempted anonymously</h3>
        {probe}
        <h3>Polymarket WebSocket, connected anonymously</h3>
        {table(
            ["Channel", "Connected", "Frames in window"],
            [
                ["<code>/ws/market</code>", "yes", esc((ws.get('clob_market') or {}).get('frame_count'))],
                ["<code>sports-api /ws</code>", "yes", esc((ws.get('sports') or {}).get('frame_count'))],
                ["Kalshi <code>/ws/v2</code>", "no", "0"],
            ],
        )}
        """,
        "Anonymous access, measured",
    )


SPEC_FILES = [
    ("kalshi-openapi.yaml", "Kalshi REST &mdash; predictions", 366380, "https://docs.kalshi.com/openapi.yaml"),
    ("kalshi-asyncapi.yaml", "Kalshi WebSocket channels", 166145, "https://docs.kalshi.com/asyncapi.yaml"),
    ("kalshi-perps-openapi.yaml", "Kalshi REST &mdash; perpetuals", 146057, "https://docs.kalshi.com/perps_openapi.yaml"),
    ("gamma-openapi.yaml", "Polymarket discovery and metadata", 82945, "https://docs.polymarket.com/api-spec/gamma-openapi.yaml"),
    ("clob-openapi.yaml", "Polymarket pricing and trading", 216099, "https://docs.polymarket.com/api-spec/clob-openapi.yaml"),
    ("data-openapi.yaml", "Polymarket activity and analytics", 61162, "https://docs.polymarket.com/api-spec/data-openapi.yaml"),
]


def build_specs() -> str:
    rows = [
        [
            f'<a href="{url}"><code>{label}</code></a>',
            covers,
            f"{size:,} bytes",
        ]
        for label, covers, size, url in SPEC_FILES
    ]
    return section(
        "specs",
        "Published specifications",
        f"""
        <p class="lede">Both venues publish machine-readable specs. These are
        the authoritative sources behind the endpoint inventories above.</p>
        {table(["Spec", "Covers", "Size"], rows)}
        <p class="note">The Kalshi AsyncAPI describes 15 channels and over 40
        message types, including the subscription commands and control
        frames. The Polymarket specs are split per service, which mirrors the
        host split.</p>
        """,
        "Machine-readable contracts",
    )


def build_gaps(ctx: Ctx) -> str:
    cards = [
        (
            "Kalshi will not stream to an anonymous client",
            "The WebSocket upgrade returned <code>401</code> without a key, and "
            "that includes channels carrying only public data. A read-only "
            "consumer either holds credentials or polls REST.",
        ),
        (
            "Kalshi candlesticks need the series ticker in the path",
            "The live route is <code>/series/{series_ticker}/markets/"
            "{ticker}/candlesticks</code>. The shorter "
            "<code>/markets/{ticker}/candlesticks</code> returns "
            "<code>404</code>, and prices are nested as "
            "<code>close_dollars</code> rather than a flat price field.",
        ),
        (
            "Kalshi partitions history, and the cutoff moves",
            "Settled markets, fills and completed orders leave the live "
            "endpoints. A reader that only queries live endpoints silently "
            "loses older rows, so read <code>/historical/cutoff</code> and "
            "query both sides.",
        ),
        (
            "Kalshi meters authenticated calls",
            "Every call costs tokens, batches bill per item, and a 429 carries "
            "no <code>Retry-After</code>. Sustained polling is a budget "
            "question, not only a latency one.",
        ),
        (
            "Gamma offset pagination stops early",
            "A survey walk stopped at 2,100 events and 500 markets on offset "
            "paging. The keyset routes return a <code>next_cursor</code> and "
            "enumerate fully. Anything that must be complete has to use "
            "keyset.",
        ),
        (
            "Polymarket ids are three different things",
            "A market carries a condition id, a slug and a numeric id, and "
            "each outcome has its own very large token id. Gamma returns token "
            "ids as a JSON string nested inside a string. Using the wrong one "
            "is the most common integration error.",
        ),
        (
            "Polymarket order placement is geoblocked",
            "Market data is open worldwide, but placing orders is restricted "
            "by jurisdiction and has its own US documentation set. A trading "
            "integration is a legal question before it is a technical one.",
        ),
        (
            "Polymarket limits are per IP",
            "Cloudflare throttles by IP on sliding windows, so a shared egress "
            "address shares the budget. Order and cancellation calls add a "
            "per-signer bucket on top.",
        ),
        (
            "Neither venue exposes resting order identity",
            "Both publish an order book and a trade tape. Neither publishes "
            "who is behind a level. On Polymarket, positions become public by "
            "wallet after the fact.",
        ),
        (
            "Prices are probabilities, not odds",
            "Both quote a probability between 0 and 1. Converting to the "
            "American convention used in this report is a display step, applied "
            "throughout so the two venues read like the rest of our material.",
        ),
    ]
    cards_html = "".join(
        f'<div class="card"><h4>{esc(title)}</h4><p>{body}</p></div>'
        for title, body in cards
    )
    return section(
        "gaps",
        "What is not available, and what bites",
        f'<div class="grid">{cards_html}</div>',
        "Constraints worth knowing before building",
    )


def build_elections(ctx: Ctx) -> str:
    """The US election slice: coverage, tick rate and the cost verdict.

    This is the evidence behind the kaz-socket architecture plan, kept in
    the same report as the rest of the API research so the two cannot drift.
    """
    e = ctx.elections
    if not e:
        return section(
            "elections",
            "US election markets",
            "<p class='muted'>Election capture not present. "
            "Run <code>build/capture_elections.py</code>.</p>",
            "The first slice",
        )

    kalshi = e.get("kalshi") or {}
    poly = e.get("polymarket") or {}
    tick = e.get("tick_rate") or {}

    per_second = first_float(tick.get("messages_per_second"))
    per_token = first_float(tick.get("messages_per_token_per_second"))
    seconds_per_update = first_float(tick.get("seconds_per_token_update"))

    coverage_rows = [
        [
            "Election series in the category",
            number(kalshi.get("series_total_in_elections_category")),
            "&mdash;",
        ],
        [
            "US election series",
            number(kalshi.get("us_series_count")),
            f"{number(poly.get('us_election_market_count'))} open markets",
        ],
        [
            "Open markets in a 40-series sample",
            number(kalshi.get("open_markets_in_sample")),
            "&mdash;",
        ],
        [
            "Resolved and excluded",
            "&mdash;",
            number(poly.get("resolved_us_election_count")),
        ],
        [
            "Candidates scanned",
            "&mdash;",
            number(poly.get("total_candidates_scanned")),
        ],
    ]

    series_rows = [
        [f"<code>{esc(row.get('series'))}</code>", number(row.get("events")), number(row.get("markets"))]
        for row in (kalshi.get("per_series") or [])[:10]
    ]

    market_rows = [
        [
            esc((row.get("question") or "")[:76]),
            esc(row.get("cents_yes")),
            esc(row.get("american_yes")),
            money(row.get("volume")),
        ]
        for row in (poly.get("us_election_markets") or [])[:10]
    ]

    # The cache-versus-relay arithmetic, at the measured rate.
    relay_html = ""
    if per_token:
        markets = 1000
        tokens = markets * 2
        upstream = tokens * per_token
        watchers = 500
        relay_egress = upstream * watchers
        cache_egress = markets  # one publish per market per second, 1s TTL
        relay_html = f"""
        <p>Using the measured <strong>{per_token:.4f} messages per token per
        second</strong> ({seconds_per_update:.1f} seconds per update):</p>
        {table(
            ["Quantity", "Straight relay", "Cache with a 1s TTL"],
            [
                [
                    "Upstream messages/s for 1,000 markets (2,000 tokens)",
                    number(upstream, 1),
                    number(upstream, 1),
                ],
                [
                    "Upstream connections as instances grow",
                    "<strong>one per instance</strong> &mdash; each burns the provider budget again",
                    "<strong>one total</strong> &mdash; a single leader lease",
                ],
                [
                    f"Egress at {watchers} clients watching everything",
                    number(relay_egress),
                    f"at most {number(cache_egress)}",
                ],
                [
                    "Behaviour after a restart or deploy",
                    "re-pulls the whole board",
                    "resumes from the change log",
                ],
            ],
        )}
        <p class="note">The relay's egress grows with
        <em>ticks &times; subscribers</em>; the cache coalesces that to
        <em>changes &times; subscribers</em>. At this tick rate both are
        modest, but the upstream-connection column is the one that decides
        it: provider budgets belong to the account, not the instance, so a
        relay that scales out pays for the same data repeatedly.</p>
        """

    example = kalshi.get("example") or {}
    example_html = ""
    if example:
        book = (example.get("orderbook") or {}).get("orderbook_fp") or {}
        example_html = f"""
        <h4>Worked example &mdash; <code>{esc(example.get('ticker'))}</code></h4>
        <p class="muted">{esc(example.get('title'))}</p>
        <dl class="meta">
          <div><dt>Yes bid</dt><dd>{esc(example.get('yes_bid'))}</dd></div>
          <div><dt>As cents</dt><dd>{esc(example.get('cents_yes'))}</dd></div>
          <div><dt>As American</dt><dd>{esc(example.get('american_yes'))}</dd></div>
          <div><dt>Volume</dt><dd>{number(example.get('volume'))}</dd></div>
          <div><dt>Closes</dt><dd>{esc(str(example.get('close_time'))[:10])}</dd></div>
          <div><dt>Book levels</dt><dd>{len(book.get('yes_dollars') or [])} yes / {len(book.get('no_dollars') or [])} no</dd></div>
        </dl>
        """

    return section(
        "elections",
        "US election markets",
        f"""
    <p class="lede">The first slice for a new feed: a category the incumbent
    sports feed does not carry, at zero data cost on both venues, with a
    gentle tick rate. Measured the same anonymous way as everything else in
    this report.</p>

    <h3>Coverage</h3>
    {table(["Measure", "Kalshi", "Polymarket"], coverage_rows)}

    <h4>Busiest Kalshi US election series in the sample</h4>
    {table(["Series", "Open events", "Open markets"], series_rows)}

    <h4>Polymarket, top open US election markets by volume</h4>
    {table(["Question", "Cents", "American", "Volume"], market_rows)}
    {example_html}

    <h3>Tick rate, measured on the live socket</h3>
    <p>Sampled {esc(tick.get('tokens'))} outcome tokens across open US
    election markets on Polymarket's public market channel for
    {esc(tick.get('seconds'))} seconds.</p>
    {table(
        ["Measure", "Value"],
        [
            ["Messages received", number(tick.get("messages"))],
            ["Window", f"{esc(tick.get('elapsed_seconds'))} seconds"],
            ["Rate", f"{number(per_second, 3)} messages/s"],
            ["Per outcome token", f"{per_token:.4f} messages/s" if per_token else "&mdash;"],
            ["Equivalent", f"one update every {number(seconds_per_update, 1)} seconds per market"],
            ["Frame mix", esc(", ".join(f"{k} {v}" for k, v in (tick.get('by_type') or {}).items()))],
        ],
    )}
    <p class="note">Compare with live sports, which ticks orders of magnitude
    faster. This is why a US election slice is a safe first release: it cannot
    be embarrassed by latency, and it exercises the caching design without
    load.</p>

    <h3>Why this makes a cache with a TTL the right shape</h3>
    {relay_html or "<p class='muted'>Tick rate unavailable.</p>"}

    <h3>Integration notes found while measuring</h3>
    <ul>
      <li><strong>Resolved markets are returned by default.</strong> A naive
      sweep counted 1,769 candidate US election markets; only
      {number(poly.get('us_election_market_count'))} were genuinely open. A
      resolved market carries a 0 or 1 outcome price, which is the reliable
      filter.</li>
      <li><strong>The cents scale is not always 1 to 99.</strong> Polymarket
      quotes longshots below a cent, so a contract price of
      <code>0.05</code> cents is real. A reader that clamps cents to a whole
      number silently drops those markets.</li>
      <li><strong>Longshot American prices explode.</strong> A 0.05-cent
      contract is roughly <code>+199,900</code> in American odds. The
      conversion is arithmetically right and useless on a screen, so an
      election UI needs a floor.</li>
      <li><strong>Kalshi's election catalog is mostly far-dated.</strong> The
      busiest open series carried 13 markets; the sample of 40 series held 263
      open markets between them.</li>
    </ul>

    <h3>What this costs</h3>
    <p>Nothing, in data fees. Both venues serve election market data
    anonymously and both publish their election catalogs. There is no
    per-sport contract, unlike adding a sport to a commercial feed.</p>
    """,
        "The first slice",
    )


def build_relevance(ctx: Ctx) -> str:
    return (
        section(
            "relevance",
            "Reading this against our own stack",
            """
        <p class="lede">Both are prediction markets quoting a probability, not
        sportsbooks quoting a price. That difference decides how each could be
        used here.</p>

        <h3>What they are not</h3>
        <p>Neither is a substitute for watching the site. Our bots price and
        gap against what the book shows on
        <code>bet105.danchrow.com</code>; a third-party order book is a
        reference, never the site. Nothing in this report changes that.</p>

        <h3>Where each is genuinely useful as a reference</h3>
        <div class="grid">
          <div class="card">
            <h4>Kalshi &mdash; a second opinion on US sports and macro</h4>
            <p>Regulated, dollars-settled event contracts with a real order
            book and a published trade tape. Sports are the largest single
            category by event count. The catch for a live path is that the
            socket needs credentials and every call costs tokens, so it suits
            slow comparison rather than a streaming leg.</p>
          </div>
          <div class="card">
            <h4>Polymarket &mdash; public push, and an independent ledger</h4>
            <p>The market socket is anonymous, so a live divergent-price check
            needs no credentials at all. Because everything settles on
            Polygon, history can be rebuilt from chain data if the API ever
            disagrees with itself.</p>
          </div>
        </div>

        <h3>Two practical cautions</h3>
        <p><strong>A different question is a different price.</strong> A
        prediction market prices a binary question with its own resolution
        rules and its own fees. A game-winner contract and a moneyline are not
        the same instrument, and the gap between them is not automatically an
        edge.</p>
        <p><strong>Liquidity is thin away from the headline.</strong> The
        worked examples in this report were chosen because they are two-sided
        and liquid. Most of the long tail is not, and a wide book at a
        low-probability price is not a tradable signal.</p>

        <h3>Scale, for context</h3>
        <p>Polymarket reports global open interest of
        <strong>"""
            + money(ctx.global_open_interest)
            + """</strong>, and Kalshi's open board runs to tens of thousands of
        markets of which several thousand are sports events. Both are large
        enough that a divergence check would have to be scoped to the fixtures
        we actually serve, not run across the whole catalog.</p>

        <p class="muted">Any decision to add either as a feed source is a scope
        call, not an implementation detail.</p>
        """,
            "Scope note",
        )
    )


SOURCES = [
    ("Kalshi API documentation index", "https://docs.kalshi.com/llms.txt"),
    ("Kalshi: environments and endpoints", "https://docs.kalshi.com/getting_started/api_environments"),
    ("Kalshi: market data quick start", "https://docs.kalshi.com/getting_started/quick_start_market_data"),
    ("Kalshi: rate limits and tiers", "https://docs.kalshi.com/getting_started/rate_limits"),
    ("Kalshi: historical data", "https://docs.kalshi.com/getting_started/historical_data"),
    ("Kalshi: WebSocket connection", "https://docs.kalshi.com/websockets/websocket-connection"),
    ("Kalshi: WebSocket quick start", "https://docs.kalshi.com/getting_started/quick_start_websockets"),
    ("Kalshi: order book responses", "https://docs.kalshi.com/getting_started/orderbook_responses"),
    ("Kalshi: OpenAPI", "https://docs.kalshi.com/openapi.yaml"),
    ("Kalshi: AsyncAPI", "https://docs.kalshi.com/asyncapi.yaml"),
    ("Kalshi: perps OpenAPI", "https://docs.kalshi.com/perps_openapi.yaml"),
    ("Polymarket documentation index", "https://docs.polymarket.com/llms.txt"),
    ("Polymarket: API overview", "https://docs.polymarket.com/getting-started/api"),
    ("Polymarket: API reference", "https://docs.polymarket.com/api-reference/introduction"),
    ("Polymarket: rate limits", "https://docs.polymarket.com/api-reference/rate-limits"),
    ("Polymarket: real-time data", "https://docs.polymarket.com/market-data/realtime-data"),
    ("Polymarket: market data overview", "https://docs.polymarket.com/market-data/overview"),
    ("Polymarket: analytics", "https://docs.polymarket.com/market-data/public-analytics"),
    ("Polymarket: blockchain data resources", "https://docs.polymarket.com/resources/blockchain-data"),
    ("Polymarket: market channel AsyncAPI", "https://docs.polymarket.com/api-reference/wss/market"),
    ("Polymarket: sports channel AsyncAPI", "https://docs.polymarket.com/api-reference/wss/sports"),
    ("Polymarket: Gamma OpenAPI", "https://docs.polymarket.com/api-spec/gamma-openapi.yaml"),
    ("Polymarket: CLOB OpenAPI", "https://docs.polymarket.com/api-spec/clob-openapi.yaml"),
    ("Polymarket: Data API v2 OpenAPI", "https://data-api.polymarket.com/v2/openapi.json"),
    ("Polymarket: US documentation", "https://docs.polymarket.us"),
]


def build_sources() -> str:
    rows = [[f'<a href="{url}">{esc(label)}</a>'] for label, url in SOURCES]
    return section(
        "sources",
        "Sources",
        table(["Document"], rows)
        + """<p class="muted">Every figure in this report is either quoted from
        these documents or was captured directly from the public endpoints
        described above. Live captures are labelled with their capture time
        and are point-in-time snapshots.</p>""",
        "Every URL used",
    )


STYLES = """
:root {
  --bg: #0c0f14;
  --panel: #141922;
  --panel-2: #1b212c;
  --line: #262e3b;
  --ink: #e8edf5;
  --ink-dim: #9aa6b8;
  --ink-faint: #6b7688;
  --accent: #5b9dff;
  --accent-2: #38d39f;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
          Arial, sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code {
  font-family: var(--mono);
  font-size: 0.86em;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 0.08em 0.36em;
  color: #cfe0ff;
  word-break: break-word;
}
h1, h2, h3, h4, h5 { line-height: 1.25; margin: 0 0 0.5em; }
h2 { font-size: 1.9rem; letter-spacing: -0.02em; }
h3 { font-size: 1.22rem; margin-top: 2.2rem; letter-spacing: -0.01em; }
h4 { font-size: 1.02rem; margin-top: 1.7rem; }
h5 { font-size: 0.86rem; color: var(--ink-dim); text-transform: uppercase;
     letter-spacing: 0.08em; margin-top: 0; }
p { margin: 0 0 1rem; }
.muted { color: var(--ink-dim); }
.note {
  color: var(--ink-dim);
  font-size: 0.9rem;
  border-left: 2px solid var(--line);
  padding-left: 0.9rem;
  margin: 1rem 0;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 0 28px 96px; }

.hero { padding: 84px 0 40px; border-bottom: 1px solid var(--line); }
.eyebrow {
  text-transform: uppercase; letter-spacing: 0.18em; font-size: 0.72rem;
  color: var(--accent-2); margin: 0 0 0.6rem;
}
.hero h1 {
  font-size: clamp(2.4rem, 6vw, 4rem);
  letter-spacing: -0.035em; margin: 0 0 0.4rem;
}
.lede { font-size: 1.1rem; color: var(--ink-dim); max-width: 76ch; }
.hero-link { margin: 1.4rem 0 0; font-family: var(--mono); font-size: 0.9rem; }
.meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(176px, 1fr));
  gap: 1px; background: var(--line); border: 1px solid var(--line);
  border-radius: 10px; overflow: hidden; margin: 2rem 0 0;
}
.meta > div { background: var(--panel); padding: 14px 16px; }
.meta dt {
  font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--ink-faint); margin-bottom: 4px;
}
.meta dd { margin: 0; font-family: var(--mono); font-size: 0.94rem; }

nav.toc {
  position: sticky; top: 0; z-index: 20;
  background: rgba(12, 15, 20, 0.93);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--line);
}
nav.toc ul {
  display: flex; gap: 1.4rem; list-style: none;
  max-width: 1180px; margin: 0 auto; padding: 13px 28px;
  overflow-x: auto; scrollbar-width: none;
}
nav.toc ul::-webkit-scrollbar { display: none; }
nav.toc a {
  color: var(--ink-dim); font-size: 0.8rem; text-transform: uppercase;
  letter-spacing: 0.08em; white-space: nowrap;
}
nav.toc a:hover { color: var(--ink); text-decoration: none; }

section { padding: 56px 0; border-bottom: 1px solid var(--line); }
section:last-of-type { border-bottom: 0; }
.kicker {
  text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.7rem;
  color: var(--accent-2); margin: 0 0 0.5rem;
}

.table-wrap {
  overflow-x: auto; border: 1px solid var(--line); border-radius: 10px;
  margin: 1.1rem 0 1.6rem; background: var(--panel);
}
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
thead th {
  text-align: left; padding: 11px 14px; background: var(--panel-2);
  color: var(--ink-dim); font-weight: 600; font-size: 0.71rem;
  text-transform: uppercase; letter-spacing: 0.08em;
  border-bottom: 1px solid var(--line); white-space: nowrap;
}
tbody td {
  padding: 11px 14px; border-bottom: 1px solid var(--line);
  vertical-align: top;
}
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: rgba(91, 157, 255, 0.045); }
td.num, th.num { font-family: var(--mono); white-space: nowrap; }

.card {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 20px 22px; margin: 0 0 1.2rem;
}
.card h3, .card h4 { margin-top: 0; }
.grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.1rem; margin: 1.2rem 0;
}
.verdict .card { border-left: 3px solid var(--accent); }
.two-col {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.4rem; margin: 1.2rem 0;
}

.code {
  border: 1px solid var(--line); border-radius: 10px; background: #0a0d12;
  margin: 0.9rem 0 1.5rem; overflow: hidden;
}
.code-label {
  font-family: var(--mono); font-size: 0.71rem; color: var(--ink-faint);
  padding: 8px 14px; border-bottom: 1px solid var(--line);
  background: var(--panel); text-transform: uppercase;
  letter-spacing: 0.08em;
}
.code pre {
  margin: 0; padding: 15px 16px; overflow-x: auto;
  font-family: var(--mono); font-size: 0.79rem; line-height: 1.6;
  color: #b9c9e3;
}
.code pre code {
  background: none; border: 0; padding: 0; color: inherit; white-space: pre;
}

.bars { margin: 1rem 0 1.6rem; }
.bar-row {
  display: grid; grid-template-columns: 200px 1fr 86px; align-items: center;
  gap: 12px; padding: 5px 0; font-size: 0.86rem;
}
.bar-label {
  color: var(--ink-dim); overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap;
}
.bar-track { background: var(--panel-2); border-radius: 999px; height: 9px; overflow: hidden; }
.bar-fill {
  display: block; height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
}
.bar-value {
  text-align: right; font-family: var(--mono); font-size: 0.82rem;
  color: var(--ink-dim);
}

.chip-row { display: flex; flex-wrap: wrap; gap: 7px; margin: 1rem 0 1.6rem; }
.chip {
  background: var(--panel-2); border: 1px solid var(--line);
  border-radius: 999px; padding: 4px 13px; font-size: 0.78rem;
  color: var(--ink-dim); font-family: var(--mono);
}

.chart {
  margin: 1.2rem 0 1.8rem; background: var(--panel);
  border: 1px solid var(--line); border-radius: 12px; padding: 14px;
}
.chart svg { width: 100%; height: 190px; display: block; }
.spark-line { fill: none; stroke: var(--accent); stroke-width: 2; }
.spark-area { fill: rgba(91, 157, 255, 0.14); }
.spark-axis { stroke: var(--line); stroke-width: 1; }
.spark-text { fill: var(--ink-faint); font-family: var(--mono); font-size: 10px; }
.chart figcaption {
  color: var(--ink-dim); font-size: 0.82rem; margin-top: 8px;
  font-family: var(--mono);
}
.focus-question { font-size: 1.18rem; font-weight: 600; margin: 1rem 0 0.6rem; }

footer { padding: 40px 0 80px; color: var(--ink-faint); font-size: 0.85rem; }
@media (max-width: 700px) {
  .wrap { padding: 0 18px 64px; }
  nav.toc ul { padding: 13px 18px; }
  .bar-row { grid-template-columns: 118px 1fr 62px; font-size: 0.8rem; }
  .hero { padding-top: 56px; }
}
"""


def main() -> None:
    ctx = Ctx()

    # Specs and path counts come from the published documents themselves.
    ctx.data.setdefault(
        "kalshi_tags",
        {
            "portfolio": 18, "communications": 18, "orders": 11, "fcm": 10,
            "market": 9, "historical": 8, "events": 7, "order-groups": 7,
            "live-data": 7, "exchange": 4, "api-keys": 4, "account": 4,
            "multivariate": 3, "search": 2, "structured-targets": 2,
            "milestone": 2, "incentive-programs": 1,
        },
    )
    ctx.data.setdefault(
        "poly_paths_by_service",
        {"CLOB": 54, "Gamma": 42, "Data v1": 19, "Data v2": 20},
    )

    nav_items = [
        ("verdict", "Verdict"),
        ("kalshi", "Kalshi"),
        ("polymarket", "Polymarket"),
        ("elections", "Elections"),
        ("live", "Live probe"),
        ("specs", "Specs"),
        ("gaps", "Limits"),
        ("relevance", "Scope note"),
        ("sources", "Sources"),
    ]
    nav = "".join(
        f'<li><a href="#{anchor}">{label}</a></li>'
        for anchor, label in nav_items
    )

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body = "".join(
        [
            build_verdict(ctx),
            build_kalshi(ctx),
            build_polymarket(ctx),
            build_elections(ctx),
            build_live(ctx),
            build_specs(),
            build_gaps(ctx),
            build_relevance(ctx),
            build_sources(),
        ]
    )

    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kalshi &amp; Polymarket &mdash; public data survey</title>
<meta name="description" content="Everything Kalshi and Polymarket expose publicly: REST, WebSocket, FIX, historical archives, specs, rate limits and auth models, measured against the live APIs.">
<meta name="color-scheme" content="dark">
<style>{STYLES}</style>
</head>
<body>
<div class="wrap">
{build_hero(ctx)}
</div>
<nav class="toc"><ul>{nav}</ul></nav>
<div class="wrap">
{body}
<footer>
  <p>Generated {esc(generated)} from captured public data. Every figure
  labelled <em>captured</em> is a point-in-time snapshot taken from anonymous
  endpoints and is not a live value.</p>
  <p>Prices appear in American odds alongside each venue's own probability
  quote. That is a display convention only; the underlying value is the
  venue's.</p>
</footer>
</div>
</body>
</html>
"""

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        handle.write(document)
    print(f"wrote {OUTPUT_PATH} ({len(document):,} bytes)")


if __name__ == "__main__":
    main()
