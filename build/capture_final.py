"""Final capture: Gamma keyset counts and a near-even Kalshi sports market.

Gamma's offset pagination caps out, so totals come from the keyset
endpoints. The Kalshi example market is taken from a sports series so the
order book shown in the report is a real two-sided game market.

Usage:
    python3 build/capture_final.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GAMMA_BASE = "https://gamma-api.polymarket.com"
KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
USER_AGENT = "prediction-markets-report/1.0 (public data survey)"

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(HERE, "final.json")


def fetch(url: str, attempts: int = 4, timeout: int = 40) -> Any | None:
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
        except Exception:  # noqa: BLE001
            if attempt < attempts - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
    return None


def keyset_count(path: str, key: str, page_size: int, budget: float):
    """Enumerate a Gamma keyset endpoint within a time budget."""
    rows = 0
    cursor = None
    started = time.time()
    pages = 0
    while time.time() - started < budget:
        query: dict[str, Any] = {"closed": "false", "limit": page_size}
        if cursor:
            query["after_cursor"] = cursor
        url = f"{GAMMA_BASE}{path}?{urllib.parse.urlencode(query)}"
        payload = fetch(url)
        if not isinstance(payload, dict):
            return rows, False, pages
        page = payload.get(key) or []
        rows += len(page)
        pages += 1
        cursor = payload.get("next_cursor")
        if not cursor or not page:
            return rows, True, pages
    return rows, False, pages


def main() -> None:
    out: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    events, events_complete, events_pages = keyset_count(
        "/events/keyset", "events", 100, 240.0
    )
    out["gamma_keyset_events"] = {
        "count": events,
        "complete": events_complete,
        "pages": events_pages,
    }

    markets, markets_complete, markets_pages = keyset_count(
        "/markets/keyset", "markets", 100, 360.0
    )
    out["gamma_keyset_markets"] = {
        "count": markets,
        "complete": markets_complete,
        "pages": markets_pages,
    }

    # Kalshi sports market nearest to even money.
    sports_series = ["KXNFLGAME", "KXNBAGAME", "KXMLBGAME", "KXNHLGAME"]
    candidates: list[dict] = []
    for ticker in sports_series:
        payload = fetch(
            f"{KALSHI_BASE}/events?status=open&limit=200"
            f"&with_nested_markets=true&series_ticker={ticker}"
        )
        for event in (payload or {}).get("events") or []:
            for market in event.get("markets") or []:
                candidates.append(market)
        if len(candidates) > 60:
            break

    def as_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    best = None
    best_distance = 1.0
    for row in candidates:
        bid = as_float(row.get("yes_bid_dollars"))
        ask = as_float(row.get("yes_ask_dollars"))
        if not (0.05 < bid < 0.95 and 0.05 < ask < 0.95):
            continue
        mid = (bid + ask) / 2
        distance = abs(mid - 0.5)
        if distance < best_distance:
            best_distance = distance
            best = row

    if best:
        ticker = best.get("ticker")
        quoted = urllib.parse.quote(str(ticker), safe="")
        out["kalshi_sports_market"] = {
            "ticker": ticker,
            "event_ticker": best.get("event_ticker"),
            "title": best.get("title"),
            "yes_sub_title": best.get("yes_sub_title"),
            "no_sub_title": best.get("no_sub_title"),
            "yes_bid": best.get("yes_bid_dollars"),
            "yes_ask": best.get("yes_ask_dollars"),
            "no_bid": best.get("no_bid_dollars"),
            "no_ask": best.get("no_ask_dollars"),
            "last_price": best.get("last_price_dollars"),
            "volume": best.get("volume_fp"),
            "open_interest": best.get("open_interest_fp"),
            "liquidity": best.get("liquidity_dollars"),
            "close_time": best.get("close_time"),
            "open_time": best.get("open_time"),
            "rules_primary": (best.get("rules_primary") or "")[:400],
            "orderbook": fetch(
                f"{KALSHI_BASE}/markets/{quoted}/orderbook?depth=10"
            ),
            "candlesticks": fetch(
                f"{KALSHI_BASE}/markets/{quoted}/candlesticks"
                f"?start_ts={int(time.time()) - 86400}"
                f"&end_ts={int(time.time())}"
                f"&period_interval=60"
            ),
        }
    out["kalshi_sports_market_count_sampled"] = len(candidates)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2)

    print(f"wrote {OUTPUT_PATH}")
    print("gamma keyset events:", out["gamma_keyset_events"])
    print("gamma keyset markets:", out["gamma_keyset_markets"])
    print("kalshi sports candidates:", len(candidates))
    if out.get("kalshi_sports_market"):
        row = out["kalshi_sports_market"]
        print("kalshi example:", row["ticker"], "| yes", row["yes_bid"], "/", row["yes_ask"])


if __name__ == "__main__":
    main()
