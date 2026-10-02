"""Polymarket catalog counts via correct offset pagination.

Usage:
    python3 build/capture_poly_counts.py
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
USER_AGENT = "prediction-markets-report/1.0 (public data survey)"

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(HERE, "poly_counts.json")


def fetch(url: str, attempts: int = 3) -> Any | None:
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
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


def count(path: str, params: dict, page_size: int, page_cap: int):
    rows = 0
    offset = 0
    complete = False
    for _ in range(page_cap):
        query = dict(params)
        query["limit"] = page_size
        query["offset"] = offset
        url = f"{GAMMA_BASE}{path}?{urllib.parse.urlencode(query)}"
        payload = fetch(url)
        if not isinstance(payload, list):
            break
        rows += len(payload)
        if len(payload) < page_size:
            complete = True
            break
        offset += page_size
    return rows, complete


def main() -> None:
    out: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    out["events_open"] = count("/events", {"closed": "false"}, 100, 250)
    out["events_all"] = count("/events", {}, 100, 250)
    out["markets_open"] = count("/markets", {"closed": "false"}, 100, 250)
    out["markets_all"] = count("/markets", {}, 100, 250)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "captured_at": out["captured_at"],
                "events_open_count": out["events_open"][0],
                "events_open_complete": out["events_open"][1],
                "markets_open_count": out["markets_open"][0],
                "markets_open_complete": out["markets_open"][1],
            },
            handle,
            indent=2,
        )

    print(f"wrote {OUTPUT_PATH}")
    for key in ("events_open", "events_all", "markets_open", "markets_all"):
        print(f"  {key}: {out[key][0]} complete={out[key][1]}")


if __name__ == "__main__":
    main()
