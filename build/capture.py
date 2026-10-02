"""Capture the public Kalshi and Polymarket API surface.

Every call here is anonymous. Nothing in this file authenticates, so it
can only reach what a member of the public can reach. Output is
build/data.json, which render.py turns into the report.

Usage:
    python3 build/capture.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

USER_AGENT = "prediction-markets-report/1.0 (public data survey)"
TIMEOUT_SECONDS = 30

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(HERE, "data.json")

ERRORS: list[dict[str, str]] = []


def fetch(url: str, attempts: int = 3) -> Any | None:
    """GET a URL and return parsed JSON, or None on failure."""
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(
                request, timeout=TIMEOUT_SECONDS
            ) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            ERRORS.append({"url": url, "error": f"HTTP {error.code}"})
            return None
        except Exception as error:  # noqa: BLE001 - survey, record and move on
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            ERRORS.append({"url": url, "error": str(error)[:200]})
            return None
    return None


def collect_pages(
    url: str,
    list_key: str,
    page_cap: int = 60,
    deadline_seconds: float = 150.0,
) -> tuple[list[dict], bool]:
    """Follow cursor pagination. Returns (rows, complete)."""
    rows: list[dict] = []
    cursor: str | None = None
    started = time.time()
    for _ in range(page_cap):
        if time.time() - started > deadline_seconds:
            return rows, False
        separator = "&" if "?" in url else "?"
        page_url = url if cursor is None else f"{url}{separator}cursor={cursor}"
        payload = fetch(page_url)
        if not isinstance(payload, dict):
            return rows, False
        page = payload.get(list_key) or []
        rows.extend(page)
        cursor = payload.get("cursor")
        if not cursor or not page:
            return rows, True
    return rows, False


# --------------------------------------------------------------------------
# Kalshi
# --------------------------------------------------------------------------


def capture_kalshi() -> dict[str, Any]:
    out: dict[str, Any] = {}

    out["base_url"] = KALSHI_BASE
    out["exchange_status"] = fetch(f"{KALSHI_BASE}/exchange/status")
    out["exchange_schedule"] = fetch(f"{KALSHI_BASE}/exchange/schedule")
    out["historical_cutoff"] = fetch(f"{KALSHI_BASE}/historical/cutoff")
    out["filters_by_sport"] = fetch(f"{KALSHI_BASE}/search/filters_by_sport")

    # Series catalog, grouped by category.
    series_rows, series_complete = collect_pages(
        f"{KALSHI_BASE}/series?limit=200", "series"
    )
    categories: dict[str, int] = {}
    for row in series_rows:
        category = row.get("category") or "Uncategorised"
        categories[category] = categories.get(category, 0) + 1
    out["series"] = {
        "count": len(series_rows),
        "complete": series_complete,
        "categories": dict(
            sorted(categories.items(), key=lambda item: -item[1])
        ),
        "sample": [
            {
                "ticker": row.get("ticker"),
                "title": row.get("title"),
                "category": row.get("category"),
                "frequency": row.get("frequency"),
            }
            for row in series_rows[:8]
        ],
    }
    out["series_list"] = [
        {
            "ticker": row.get("ticker"),
            "title": row.get("title"),
            "category": row.get("category"),
        }
        for row in series_rows
    ]

    # Open events.
    event_rows, events_complete = collect_pages(
        f"{KALSHI_BASE}/events?status=open&limit=200", "events"
    )
    categories_events: dict[str, int] = {}
    for row in event_rows:
        category = row.get("category") or "Uncategorised"
        categories_events[category] = categories_events.get(category, 0) + 1
    out["open_events"] = {
        "count": len(event_rows),
        "complete": events_complete,
        "categories": dict(
            sorted(categories_events.items(), key=lambda item: -item[1])
        ),
        "sample": [
            {
                "event_ticker": row.get("event_ticker"),
                "title": row.get("title"),
                "category": row.get("category"),
                "sub_title": row.get("sub_title"),
            }
            for row in event_rows[:10]
        ],
    }

    # Open markets.
    market_rows, markets_complete = collect_pages(
        f"{KALSHI_BASE}/markets?status=open&limit=1000", "markets"
    )
    out["open_markets"] = {
        "count": len(market_rows),
        "complete": markets_complete,
    }

    def market_row(row: dict) -> dict:
        return {
            "ticker": row.get("ticker"),
            "event_ticker": row.get("event_ticker"),
            "title": row.get("title"),
            "yes_bid": row.get("yes_bid_dollars"),
            "yes_ask": row.get("yes_ask_dollars"),
            "no_bid": row.get("no_bid_dollars"),
            "no_ask": row.get("no_ask_dollars"),
            "last_price": row.get("last_price_dollars"),
            "volume": row.get("volume_fp"),
            "open_interest": row.get("open_interest_fp"),
            "liquidity": row.get("liquidity_dollars"),
            "close_time": row.get("close_time"),
            "status": row.get("status"),
        }

    def as_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    by_volume = sorted(
        market_rows, key=lambda row: -as_float(row.get("volume_fp"))
    )
    by_oi = sorted(
        market_rows, key=lambda row: -as_float(row.get("open_interest_fp"))
    )
    out["top_markets_by_volume"] = [market_row(r) for r in by_volume[:10]]
    out["top_markets_by_open_interest"] = [market_row(r) for r in by_oi[:10]]
    out["sample_markets"] = [market_row(r) for r in market_rows[:10]]

    sport_markets = [
        row
        for row in market_rows
        if str(row.get("ticker", "")).startswith("KX")
        and any(
            token
            in str(row.get("event_ticker", "")).upper()
            for token in (
                "GAME",
                "SPREAD",
                "TOTAL",
                "ML",
                "NBA",
                "NFL",
                "MLB",
                "NHL",
            )
        )
    ]
    out["sports_like_open_markets"] = len(sport_markets)

    # A real orderbook for the busiest market.
    if by_volume:
        top_ticker = by_volume[0].get("ticker")
        if top_ticker:
            quoted = urllib.parse.quote(str(top_ticker), safe="")
            out["orderbook"] = {
                "ticker": top_ticker,
                "title": by_volume[0].get("title"),
                "payload": fetch(
                    f"{KALSHI_BASE}/markets/{quoted}/orderbook?depth=10"
                ),
            }

    # Public trade tape.
    trades = fetch(f"{KALSHI_BASE}/markets/trades?limit=20")
    out["recent_trades"] = trades

    # Other public catalogs.
    out["milestones"] = fetch(f"{KALSHI_BASE}/milestones?limit=100")
    out["structured_targets"] = fetch(
        f"{KALSHI_BASE}/structured_targets?limit=100"
    )
    out["multivariate_events"] = fetch(
        f"{KALSHI_BASE}/events/multivariate?limit=100"
    )

    return out


# --------------------------------------------------------------------------
# Polymarket
# --------------------------------------------------------------------------


def capture_polymarket() -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["gamma_base"] = GAMMA_BASE
    out["clob_base"] = CLOB_BASE
    out["data_base"] = DATA_BASE

    # Discovery catalogs from Gamma.
    events = fetch(f"{GAMMA_BASE}/events?closed=false&limit=500")
    out["open_events"] = {
        "count": len(events) if isinstance(events, list) else None,
        "sample": [
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "slug": row.get("slug"),
                "volume": row.get("volume"),
                "liquidity": row.get("liquidity"),
                "markets": len(row.get("markets") or []),
            }
            for row in (events or [])[:10]
        ],
    }

    markets = fetch(f"{GAMMA_BASE}/markets?closed=false&limit=500")
    out["open_markets"] = {
        "count": len(markets) if isinstance(markets, list) else None
    }

    ranked = fetch(
        f"{GAMMA_BASE}/markets?closed=false&limit=10"
        "&order=volumeNum&ascending=false"
    )

    def gamma_market(row: dict) -> dict:
        tokens = row.get("clobTokenIds")
        if isinstance(tokens, str):
            try:
                tokens = json.loads(tokens)
            except json.JSONDecodeError:
                tokens = []
        outcomes = row.get("outcomes")
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = []
        prices = row.get("outcomePrices")
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except json.JSONDecodeError:
                prices = []
        return {
            "id": row.get("id"),
            "question": row.get("question"),
            "slug": row.get("slug"),
            "condition_id": row.get("conditionId"),
            "outcomes": outcomes,
            "outcome_prices": prices,
            "token_ids": tokens,
            "volume": row.get("volumeNum") or row.get("volume"),
            "liquidity": row.get("liquidityNum") or row.get("liquidity"),
            "end_date": row.get("endDate"),
            "tick_size": row.get("orderPriceMinTickSize"),
            "neg_risk": row.get("negRisk"),
        }

    out["top_markets_by_volume"] = [
        gamma_market(row) for row in (ranked or [])
    ]

    tags = fetch(f"{GAMMA_BASE}/tags?limit=100")
    out["tags"] = {
        "count": len(tags) if isinstance(tags, list) else None,
        "sample": [
            {"label": row.get("label"), "slug": row.get("slug")}
            for row in (tags or [])[:20]
        ],
    }

    sports = fetch(f"{GAMMA_BASE}/sports")
    out["sports"] = {
        "count": len(sports) if isinstance(sports, list) else None,
        "sample": [
            {
                "sport": row.get("sport"),
                "image": row.get("image"),
                "tags": row.get("tags"),
            }
            for row in (sports or [])[:20]
        ],
    }

    teams = fetch(f"{GAMMA_BASE}/teams?limit=50")
    out["teams"] = {
        "count": len(teams) if isinstance(teams, list) else None,
        "sample": [
            {
                "name": row.get("name"),
                "league": row.get("league"),
                "abbreviation": row.get("abbreviation"),
            }
            for row in (teams or [])[:15]
        ],
    }

    series = fetch(f"{GAMMA_BASE}/series?limit=50")
    out["series"] = {
        "count": len(series) if isinstance(series, list) else None,
        "sample": [
            {"title": row.get("title"), "slug": row.get("slug")}
            for row in (series or [])[:10]
        ],
    }

    search = fetch(
        f"{GAMMA_BASE}/public-search?q=election&limit_per_type=3"
    )
    out["public_search"] = search

    # CLOB: live pricing for the busiest market.
    clob_counts = {}
    for name, path in (
        ("markets", "/markets?limit=1"),
        ("sampling_markets", "/sampling-markets?limit=1"),
        ("simplified_markets", "/simplified-markets?limit=1"),
    ):
        payload = fetch(f"{CLOB_BASE}{path}")
        clob_counts[name] = (
            payload.get("count") if isinstance(payload, dict) else None
        )
    payload = fetch(f"{CLOB_BASE}/rewards/markets/multi?limit=1")
    clob_counts["reward_markets"] = (
        payload.get("count") if isinstance(payload, dict) else None
    )
    out["clob_counts"] = clob_counts
    out["clob_ok"] = fetch(f"{CLOB_BASE}/ok")
    out["clob_time"] = fetch(f"{CLOB_BASE}/time")

    focus = None
    if isinstance(ranked, list) and ranked:
        focus = gamma_market(ranked[0])
    if focus and focus.get("token_ids"):
        primary = focus["token_ids"][0]
        secondary = focus["token_ids"][1] if len(focus["token_ids"]) > 1 else None
        quoted = urllib.parse.quote(str(primary), safe="")
        out["clob_focus"] = {
            "market": focus,
            "book": fetch(f"{CLOB_BASE}/book?token_id={quoted}"),
            "price_buy": fetch(
                f"{CLOB_BASE}/price?token_id={quoted}&side=buy"
            ),
            "price_sell": fetch(
                f"{CLOB_BASE}/price?token_id={quoted}&side=sell"
            ),
            "midpoint": fetch(f"{CLOB_BASE}/midpoint?token_id={quoted}"),
            "spread": fetch(f"{CLOB_BASE}/spread?token_id={quoted}"),
            "tick_size": fetch(f"{CLOB_BASE}/tick-size?token_id={quoted}"),
            "fee_rate": fetch(f"{CLOB_BASE}/fee-rate?token_id={quoted}"),
            "prices_history": fetch(
                f"{CLOB_BASE}/prices-history?market={quoted}"
                "&interval=1w&fidelity=180"
            ),
        }
        if secondary:
            secondary_quoted = urllib.parse.quote(str(secondary), safe="")
            out["clob_focus"]["book_secondary"] = fetch(
                f"{CLOB_BASE}/book?token_id={secondary_quoted}"
            )

    # Data API v2.
    out["data_status"] = fetch(f"{DATA_BASE}/v2/status")
    out["data_open_interest"] = fetch(f"{DATA_BASE}/v2/oi")
    out["data_leaderboard"] = fetch(f"{DATA_BASE}/v2/leaderboard?limit=10")
    out["data_trades"] = fetch(f"{DATA_BASE}/v2/trades?limit=20")

    if focus and focus.get("condition_id"):
        condition = focus["condition_id"]
        out["data_positions"] = fetch(
            f"{DATA_BASE}/v2/positions?condition_id={condition}&limit=5"
        )
        out["data_holders"] = fetch(
            f"{DATA_BASE}/v2/holders?condition_id={condition}&limit=5"
        )
        out["data_open_interest_market"] = fetch(
            f"{DATA_BASE}/v2/oi?condition_id={condition}"
        )
    return out


def main() -> None:
    started = time.time()
    data: dict[str, Any] = {
        "captured_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        ),
        "source": "anonymous public endpoints only",
    }
    data["kalshi"] = capture_kalshi()
    data["polymarket"] = capture_polymarket()
    data["errors"] = ERRORS
    data["elapsed_seconds"] = round(time.time() - started, 1)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=False)

    print(f"wrote {OUTPUT_PATH}")
    print(f"elapsed {data['elapsed_seconds']}s")
    print(f"errors {len(ERRORS)}")
    for error in ERRORS[:20]:
        print("  ", error["url"], "->", error["error"])


if __name__ == "__main__":
    main()
