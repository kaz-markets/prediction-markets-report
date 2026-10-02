"""Exact counts and category joins for the Kalshi open catalog.

The first pass caps pagination so a survey stays quick. This pass runs
longer to get complete counts and joins open markets to their series
category, so the report can say how much of the open board is sports.

Usage:
    python3 build/capture_counts.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
DATA_BASE = "https://data-api.polymarket.com"
USER_AGENT = "prediction-markets-report/1.0 (public data survey)"

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(HERE, "counts.json")


def fetch(url: str, attempts: int = 4) -> Any | None:
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
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


def paginate(url: str, key: str, page_cap: int, budget: float):
    rows: list[dict] = []
    cursor: str | None = None
    started = time.time()
    pages = 0
    while pages < page_cap and time.time() - started < budget:
        page_url = url if cursor is None else f"{url}&cursor={cursor}"
        payload = fetch(page_url)
        if not isinstance(payload, dict):
            return rows, False
        page = payload.get(key) or []
        rows.extend(page)
        pages += 1
        cursor = payload.get("cursor")
        if not cursor or not page:
            return rows, True
    return rows, False


def main() -> None:
    out: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    series_rows, series_complete = paginate(
        f"{KALSHI_BASE}/series?limit=200", "series", 400, 420.0
    )
    series_category = {
        str(row.get("ticker")): row.get("category") or "Uncategorised"
        for row in series_rows
    }
    out["series"] = {
        "count": len(series_rows),
        "complete": series_complete,
    }

    events, events_complete = paginate(
        f"{KALSHI_BASE}/events?status=open&limit=200", "events", 900, 600.0
    )
    out["open_events"] = {
        "count": len(events),
        "complete": events_complete,
        "categories": dict(
            Counter(
                row.get("category") or "Uncategorised" for row in events
            ).most_common()
        ),
    }

    markets, markets_complete = paginate(
        f"{KALSHI_BASE}/markets?status=open&limit=1000",
        "markets",
        900,
        900.0,
    )

    market_categories: Counter = Counter()
    sports_markets = 0
    for row in markets:
        event_ticker = str(row.get("event_ticker") or "")
        series_ticker = event_ticker.split("-")[0]
        category = series_category.get(series_ticker, "Uncategorised")
        market_categories[category] += 1
        if category == "Sports":
            sports_markets += 1

    out["open_markets"] = {
        "count": len(markets),
        "complete": markets_complete,
        "categories": dict(market_categories.most_common()),
        "sports_markets": sports_markets,
    }

    payload = fetch(f"{DATA_BASE}/v2/oi")
    out["polymarket_global_open_interest"] = payload

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2)

    print(f"wrote {OUTPUT_PATH}")
    print("series:", out["series"])
    print("events:", out["open_events"]["count"], out["open_events"]["complete"])
    print("markets:", out["open_markets"]["count"], out["open_markets"]["complete"])
    print("sports markets:", sports_markets)
    print("market categories:", list(market_categories.most_common(12)))


if __name__ == "__main__":
    main()
