"""Patch pass: fixed v2 params plus a near-even Kalshi market.

Merges extra fields into build/data.json so render.py has everything it
needs without re-running the full survey.

Usage:
    python3 build/capture_patch.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
DATA_BASE = "https://data-api.polymarket.com"
USER_AGENT = "prediction-markets-report/1.0 (public data survey)"

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "data.json")


def fetch(url: str, attempts: int = 3) -> Any | None:
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            body = ""
            try:
                body = error.read()[:200].decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                pass
            if error.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            return {"_error": f"HTTP {error.code}", "_body": body}
        except Exception:  # noqa: BLE001
            if attempt < attempts - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
    return None


def main() -> None:
    with open(PATH, encoding="utf-8") as handle:
        data = json.load(handle)

    kalshi = data["kalshi"]
    poly = data["polymarket"]

    def as_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # A near-even Kalshi market: both sides priced, close to 50c.
    markets = fetch(
        f"{KALSHI_BASE}/markets?status=open&limit=1000"
    )
    rows = (markets or {}).get("markets") or []
    best = None
    best_distance = 1.0
    for row in rows:
        bid = as_float(row.get("yes_bid_dollars"))
        ask = as_float(row.get("yes_ask_dollars"))
        if not (0.02 < bid < 0.98 and 0.02 < ask < 0.98):
            continue
        mid = (bid + ask) / 2
        distance = abs(mid - 0.5)
        if distance < best_distance:
            best_distance = distance
            best = row
    if best:
        kalshi["nearest_to_even_market"] = {
            "ticker": best.get("ticker"),
            "event_ticker": best.get("event_ticker"),
            "title": best.get("title"),
            "yes_bid": best.get("yes_bid_dollars"),
            "yes_ask": best.get("yes_ask_dollars"),
            "volume": best.get("volume_fp"),
            "open_interest": best.get("open_interest_fp"),
            "close_time": best.get("close_time"),
        }

        import urllib.parse

        quoted = urllib.parse.quote(str(best.get("ticker")), safe="")
        kalshi["nearest_orderbook"] = {
            "ticker": best.get("ticker"),
            "payload": fetch(
                f"{KALSHI_BASE}/markets/{quoted}/orderbook?depth=10"
            ),
        }

    # Fixed Data API v2 calls.
    focus = (poly.get("clob_focus") or {}).get("market") or {}
    condition = focus.get("condition_id")
    if condition:
        poly["data_positions"] = fetch(
            f"{DATA_BASE}/v2/positions?condition_id={condition}&limit=5"
        )
        poly["data_holders"] = fetch(
            f"{DATA_BASE}/v2/holders?condition_id={condition}&limit=5"
        )
        poly["data_open_interest_market"] = fetch(
            f"{DATA_BASE}/v2/oi?condition_id={condition}"
        )
        poly["data_live_volume"] = fetch(
            f"{DATA_BASE}/v2/live-volume?condition_id={condition}"
        )

    with open(PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)

    print("patched", PATH)
    if kalshi.get("nearest_to_even_market"):
        row = kalshi["nearest_to_even_market"]
        print("nearest to even:", row["ticker"], row["yes_bid"], row["yes_ask"])
    print("positions err:", str(poly.get("data_positions"))[:80])


if __name__ == "__main__":
    main()
