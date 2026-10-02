"""Fetch candlesticks for the example market using the correct route.

The live candlestick route is
/series/{series_ticker}/markets/{ticker}/candlesticks - without the series
segment it returns 404. Prices come back nested as *_dollars.

Usage:
    python3 build/capture_candles.py
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
USER_AGENT = "prediction-markets-report/1.0 (public data survey)"

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "final.json")


def fetch(url: str, attempts: int = 3) -> Any | None:
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return {"_error": f"HTTP {error.code}"}
        except Exception:  # noqa: BLE001
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
    return None


def main() -> None:
    with open(PATH, encoding="utf-8") as handle:
        data = json.load(handle)

    example = data.get("kalshi_sports_market") or {}
    ticker = example.get("ticker")
    event_ticker = example.get("event_ticker") or ""
    series_ticker = event_ticker.split("-")[0]

    if not ticker or not series_ticker:
        print("no example market to fetch candles for")
        return

    quoted_ticker = urllib.parse.quote(str(ticker), safe="")
    quoted_series = urllib.parse.quote(str(series_ticker), safe="")
    now = int(time.time())

    collected: dict[str, dict] = {}

    for interval, window in ((60, 86400 * 2), (1440, 86400 * 14)):
        payload = fetch(
            f"{KALSHI_BASE}/series/{quoted_series}/markets/{quoted_ticker}"
            f"/candlesticks?start_ts={now - window}&end_ts={now}"
            f"&period_interval={interval}"
        )
        candles = (payload or {}).get("candlesticks") or []
        collected[str(interval)] = {
            "period_interval": interval,
            "count": len(candles),
            "candlesticks": candles,
        }
        print(f"interval {interval}: {len(candles)} candles")

    example["candlesticks"] = collected
    example["candlestick_series_ticker"] = series_ticker
    data["kalshi_sports_market"] = example

    with open(PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    print("patched", PATH)


if __name__ == "__main__":
    main()
