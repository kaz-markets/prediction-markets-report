"""Second Polymarket pass: real counts and a balanced focus market.

The first pass used a single page per catalog, which Gamma caps at 100
rows. This pass paginates, and picks a two-sided market (price near 0.50
with real liquidity) so the order book shown in the report is
representative rather than a longshot.

Usage:
    python3 build/capture_poly.py
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
CLOB_BASE = "https://clob.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"
USER_AGENT = "prediction-markets-report/1.0 (public data survey)"

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(HERE, "poly_detail.json")


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
        except Exception as error:  # noqa: BLE001
            if attempt < attempts - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            return {"_error": str(error)[:200]}
    return None


def count_rows(base: str, path: str, page_size: int, page_cap: int):
    """Offset-paginate a Gamma catalog to a count."""
    rows = 0
    offset = 0
    complete = False
    for _ in range(page_cap):
        payload = fetch(
            f"{base}{path}?limit={page_size}&offset={offset}"
        )
        if not isinstance(payload, list):
            break
        rows += len(payload)
        if len(payload) < page_size:
            complete = True
            break
        offset += page_size
    return rows, complete


def parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def main() -> None:
    out: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    out["open_events_count"], out["open_events_complete"] = count_rows(
        GAMMA_BASE, "/events", 100, 120
    )
    out["open_events_closed_false_count"], out["open_events_closed_false_complete"] = (
        count_rows(GAMMA_BASE, "/events?closed=false&x=1", 100, 120)
    )
    out["open_markets_count"], out["open_markets_complete"] = count_rows(
        GAMMA_BASE, "/markets?closed=false&x=1", 100, 120
    )

    # CLOB catalog counts.
    out["clob_markets_count"] = fetch(f"{CLOB_BASE}/markets?limit=1")
    out["clob_sampling_count"] = fetch(
        f"{CLOB_BASE}/sampling-markets?limit=1"
    )

    # Pick a balanced, liquid market for the worked example.
    candidates = fetch(
        f"{GAMMA_BASE}/markets?closed=false&limit=100"
        "&order=liquidityNum&ascending=false"
    )
    focus = None
    if isinstance(candidates, list):
        for row in candidates:
            if not row.get("enableOrderBook"):
                continue
            tokens = parse_json_field(row.get("clobTokenIds"))
            prices = parse_json_field(row.get("outcomePrices"))
            if not (isinstance(tokens, list) and len(tokens) == 2):
                continue
            if not (isinstance(prices, list) and len(prices) == 2):
                continue
            try:
                mid = float(prices[0])
            except (TypeError, ValueError):
                continue
            if 0.30 <= mid <= 0.70:
                focus = row
                break
    if focus is None and isinstance(candidates, list) and candidates:
        focus = candidates[0]

    if focus is not None:
        tokens = parse_json_field(focus.get("clobTokenIds")) or []
        outcomes = parse_json_field(focus.get("outcomes")) or []
        prices = parse_json_field(focus.get("outcomePrices")) or []
        condition = focus.get("conditionId")
        summary = {
            "question": focus.get("question"),
            "slug": focus.get("slug"),
            "condition_id": condition,
            "event_id": (focus.get("events") or [{}])[0].get("id")
            if isinstance(focus.get("events"), list)
            else None,
            "outcomes": outcomes,
            "outcome_prices": prices,
            "token_ids": tokens,
            "volume": row.get("volumeNum") if False else focus.get("volumeNum"),
            "liquidity": focus.get("liquidityNum"),
            "end_date": focus.get("endDate"),
            "tick_size": focus.get("orderPriceMinTickSize"),
            "neg_risk": focus.get("negRisk"),
            "minimum_order_size": focus.get("orderMinSize"),
            "spread": focus.get("spread"),
            "best_bid": focus.get("bestBid"),
            "best_ask": focus.get("bestAsk"),
            "last_trade_price": focus.get("lastTradePrice"),
        }

        detail: dict[str, Any] = {"market": summary}

        for label, token in zip(("outcome_1", "outcome_2"), tokens):
            quoted = urllib.parse.quote(str(token), safe="")
            detail[label] = {
                "token_id": token,
                "book": fetch(f"{CLOB_BASE}/book?token_id={quoted}"),
                "price_buy": fetch(
                    f"{CLOB_BASE}/price?token_id={quoted}&side=buy"
                ),
                "price_sell": fetch(
                    f"{CLOB_BASE}/price?token_id={quoted}&side=sell"
                ),
                "midpoint": fetch(f"{CLOB_BASE}/midpoint?token_id={quoted}"),
                "spread": fetch(f"{CLOB_BASE}/spread?token_id={quoted}"),
                "tick_size": fetch(
                    f"{CLOB_BASE}/tick-size?token_id={quoted}"
                ),
                "fee_rate": fetch(f"{CLOB_BASE}/fee-rate?token_id={quoted}"),
                "prices_history": fetch(
                    f"{CLOB_BASE}/prices-history?market={quoted}"
                    "&interval=1m&fidelity=60"
                ),
            }

        if condition:
            detail["data_positions"] = fetch(
                f"{DATA_BASE}/v2/positions?condition_id={condition}&limit=5"
            )
            detail["data_holders"] = fetch(
                f"{DATA_BASE}/v2/holders?condition_id={condition}&limit=5"
            )
            detail["data_open_interest"] = fetch(
                f"{DATA_BASE}/v2/oi?condition_id={condition}"
            )
            detail["data_live_volume"] = fetch(
                f"{DATA_BASE}/v2/live-volume?condition_id={condition}"
            )
            detail["data_trades"] = fetch(
                f"{DATA_BASE}/v2/trades?condition_id={condition}&limit=10"
            )
            detail["clob_market_info"] = fetch(
                f"{CLOB_BASE}/markets/{condition}"
            )

        out["focus"] = detail

    # The live Data API v2 spec, for the endpoint inventory.
    out["v2_openapi_paths"] = fetch(
        "https://data-api.polymarket.com/v2/openapi.json"
    )

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2)

    print(f"wrote {OUTPUT_PATH}")
    print("gamma open events:", out["open_events_count"], out["open_events_complete"])
    print("gamma open markets:", out["open_markets_count"], out["open_markets_complete"])
    if out.get("focus"):
        print("focus:", out["focus"]["market"]["question"])
        print("  outcomes:", out["focus"]["market"]["outcomes"])
        print("  prices:", out["focus"]["market"]["outcome_prices"])


if __name__ == "__main__":
    main()
