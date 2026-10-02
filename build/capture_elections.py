"""Capture the US election markets slice on both prediction markets.

This is the evidence behind the kaz-socket architecture plan: how many US
election markets each venue actually lists, and how fast they tick. The
tick rate is the number that decides cache-with-TTL over a straight relay.

All calls are anonymous.

Usage:
    python3 build/capture_elections.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

USER_AGENT = "prediction-markets-report/1.0 (public data survey)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(HERE, "elections.json")

TICK_SAMPLE_MARKETS = 12
TICK_SAMPLE_SECONDS = 60

# Series tickers that are US elections rather than elections elsewhere.
US_SERIES = re.compile(
    r"^(KXPRES|KXPRESNOM|KXVP|SENATE|HOUSE|GOV|KXGOV|KXSEN|KXHOUSE|"
    r"KXELEC|KXMIDTERM|KXSPEAKER|KXATTORNEY|KXSECSTATE|KXSOS)",
    re.I,
)

# Words that make a Polymarket question a US election market.
US_QUESTION_WORDS = (
    "president", "presidential", "senate", "house", "governor", "gubernatorial",
    "congress", "congressional", "electoral", "election", "nominee",
    "nomination", "primary", "democrat", "republican", "midterm",
    "speaker", "attorney general",
)
NON_US = (
    "uk ", "britain", "british", "france", "french", "germany", "german",
    "canada", "canadian", "australia", "india", "japan", "brazil", "mexico",
    "israel", "poland", "nigeria", "argentina", "thailand", "mongolia",
    "quebec", "nato", "pope", "venezuela", "turkey", "iran", "china",
)


def fetch(url: str, attempts: int = 3, timeout: int = 40) -> Any | None:
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception:  # noqa: BLE001 - survey, record and move on
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
    return None


def json_field(value: Any) -> Any:
    """Gamma returns some arrays as JSON encoded inside a string."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def to_cents(price: Any) -> float | None:
    """A 0..1 probability as the 1..99 contract price both venues use."""
    try:
        numeric = float(price)
    except (TypeError, ValueError):
        return None
    if 0 < numeric < 1:
        return round(numeric * 100, 2)
    return None


def probability_to_american(probability: float) -> str:
    if probability <= 0 or probability >= 1:
        return "n/a"
    if probability >= 0.5:
        return f"-{round(100 * probability / (1 - probability)):,}"
    return f"+{round(100 * (1 - probability) / probability):,}"


# --------------------------------------------------------------------------
# Kalshi
# --------------------------------------------------------------------------


def capture_kalshi() -> dict[str, Any]:
    out: dict[str, Any] = {}

    all_series: list[dict] = []
    cursor: str | None = None
    for _ in range(30):
        url = f"{KALSHI_BASE}/series?limit=200&category=Elections"
        if cursor:
            url += f"&cursor={cursor}"
        payload = fetch(url)
        if not isinstance(payload, dict):
            break
        page = payload.get("series") or []
        all_series.extend(page)
        cursor = payload.get("cursor")
        if not cursor or not page:
            break

    us_series = [
        row for row in all_series if US_SERIES.match(str(row.get("ticker") or ""))
    ]
    out["series_total_in_elections_category"] = len(all_series)
    out["us_series_count"] = len(us_series)
    out["us_series_sample"] = [
        {
            "ticker": row.get("ticker"),
            "title": row.get("title"),
            "frequency": row.get("frequency"),
        }
        for row in us_series[:15]
    ]

    # Open markets under a set of representative US election series.
    sampled = [
        row.get("ticker")
        for row in us_series[:40]
        if row.get("ticker")
    ]
    per_series: list[dict] = []
    total_markets = 0
    total_events = 0
    for ticker in sampled:
        payload = fetch(
            f"{KALSHI_BASE}/events?status=open&limit=200"
            f"&series_ticker={urllib.parse.quote(str(ticker), safe='')}"
            f"&with_nested_markets=true"
        )
        events = (payload or {}).get("events") or []
        markets = sum(len(event.get("markets") or []) for event in events)
        total_events += len(events)
        total_markets += markets
        if markets:
            per_series.append(
                {"series": ticker, "events": len(events), "markets": markets}
            )
    out["sampled_series"] = len(sampled)
    out["open_events_in_sample"] = total_events
    out["open_markets_in_sample"] = total_markets
    out["per_series"] = sorted(
        per_series, key=lambda row: -row["markets"]
    )[:15]

    # A worked example: the busiest open US election market.
    best: dict | None = None
    for row in per_series:
        payload = fetch(
            f"{KALSHI_BASE}/events?status=open&limit=200"
            f"&series_ticker={urllib.parse.quote(str(row['series']), safe='')}"
            f"&with_nested_markets=true"
        )
        for event in (payload or {}).get("events") or []:
            for market in event.get("markets") or []:
                try:
                    bid = float(market.get("yes_bid_dollars") or 0)
                    ask = float(market.get("yes_ask_dollars") or 0)
                except (TypeError, ValueError):
                    continue
                if not (0.03 < bid < 0.97):
                    continue
                volume = 0.0
                try:
                    volume = float(market.get("volume_fp") or 0)
                except (TypeError, ValueError):
                    pass
                score = volume * (1 - abs((bid + ask) / 2 - 0.5) * 2)
                if best is None or score > best["_score"]:
                    best = {
                        "_score": score,
                        "ticker": market.get("ticker"),
                        "event_ticker": market.get("event_ticker"),
                        "series_ticker": row["series"],
                        "title": market.get("title"),
                        "yes_sub_title": market.get("yes_sub_title"),
                        "yes_bid": market.get("yes_bid_dollars"),
                        "yes_ask": market.get("yes_ask_dollars"),
                        "last_price": market.get("last_price_dollars"),
                        "volume": market.get("volume_fp"),
                        "open_interest": market.get("open_interest_fp"),
                        "close_time": market.get("close_time"),
                    }
        if best and best["_score"] > 20:
            break

    if best:
        ticker = str(best.pop("ticker"))
        series = str(best.pop("series_ticker"))
        quoted = urllib.parse.quote(ticker, safe="")
        quoted_series = urllib.parse.quote(series, safe="")
        best["ticker"] = ticker
        best["series_ticker"] = series
        best["orderbook"] = fetch(
            f"{KALSHI_BASE}/markets/{quoted}/orderbook?depth=10"
        )
        now = int(time.time())
        best["candlesticks"] = fetch(
            f"{KALSHI_BASE}/series/{quoted_series}/markets/{quoted}"
            f"/candlesticks?start_ts={now - 86400 * 14}&end_ts={now}"
            f"&period_interval=1440"
        )
        bid = best.get("yes_bid")
        best["american_yes"] = (
            probability_to_american(float(bid)) if bid is not None else None
        )
        best["cents_yes"] = to_cents(bid)
    out["example"] = best

    return out


# --------------------------------------------------------------------------
# Polymarket
# --------------------------------------------------------------------------


def is_us_election(question: str) -> bool:
    text = (question or "").lower()
    if any(word in text for word in NON_US):
        return False
    return any(word in text for word in US_QUESTION_WORDS)


def is_open_market(market: dict) -> bool:
    """Gamma returns resolved markets unless filtered out explicitly.

    A resolved market carries a 0 or 1 outcome price; an open one does not.
    """
    if market.get("closed") is True or market.get("archived") is True:
        return False
    if market.get("active") is False:
        return False
    end_date = str(market.get("endDate") or "")
    if end_date:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if end_date < now:
            return False
    prices = json_field(market.get("outcomePrices")) or []
    for price in prices[:2]:
        try:
            numeric = float(price)
        except (TypeError, ValueError):
            continue
        if numeric <= 0 or numeric >= 1:
            return False
    return True


def capture_polymarket() -> tuple[dict[str, Any], list[str]]:
    """Returns the election market summary and the token ids to sample."""
    out: dict[str, Any] = {}

    # By tag, then by search, then a volume-ranked sweep.
    by_tag: list[dict] = []
    tags = fetch(f"{GAMMA_BASE}/tags?limit=1000") or []
    election_tags = [
        tag
        for tag in tags
        if isinstance(tag, dict)
        and any(
            word in ((tag.get("label") or "") + (tag.get("slug") or "")).lower()
            for word in ("election", "politic", "president", "senate", "house", "congress")
        )
    ]
    for tag in election_tags[:6]:
        events = fetch(
            f"{GAMMA_BASE}/events?closed=false&limit=100&tag_id={tag.get('id')}"
        )
        for event in (events or []):
            for market in (event.get("markets") or []):
                market["_tag"] = tag.get("slug")
                by_tag.append(market)
    out["tags_used"] = [
        {"id": tag.get("id"), "slug": tag.get("slug"), "label": tag.get("label")}
        for tag in election_tags[:10]
    ]

    candidates: dict[str, dict] = {}
    for market in by_tag:
        if market.get("conditionId"):
            candidates[str(market["conditionId"])] = market

    for query in ("president", "senate", "election", "nominee"):
        found = fetch(
            f"{GAMMA_BASE}/public-search?q={query}&limit_per_type=40"
        ) or {}
        for event in (found.get("events") or []):
            if event.get("closed") is True:
                continue
            for market in (event.get("markets") or []):
                if market.get("conditionId"):
                    candidates.setdefault(str(market["conditionId"]), market)

    ranked = fetch(
        f"{GAMMA_BASE}/markets?closed=false&limit=400"
        "&order=volumeNum&ascending=false"
    ) or []
    for market in ranked:
        if market.get("conditionId") and is_us_election(market.get("question") or ""):
            candidates.setdefault(str(market["conditionId"]), market)

    resolved = [
        market
        for market in candidates.values()
        if is_us_election(market.get("question") or "")
        and not is_open_market(market)
    ]
    us_markets = [
        market
        for market in candidates.values()
        if is_us_election(market.get("question") or "")
        and is_open_market(market)
    ]

    def summarise(market: dict) -> dict:
        tokens = json_field(market.get("clobTokenIds")) or []
        prices = json_field(market.get("outcomePrices")) or []
        yes = to_cents(prices[0]) if prices else None
        return {
            "condition_id": market.get("conditionId"),
            "question": market.get("question"),
            "slug": market.get("slug"),
            "volume": market.get("volumeNum") or market.get("volume"),
            "liquidity": market.get("liquidityNum") or market.get("liquidity"),
            "outcomes": json_field(market.get("outcomes")),
            "outcome_prices": prices,
            "cents_yes": yes,
            "american_yes": (
                probability_to_american(float(prices[0])) if prices else None
            ),
            "token_ids": tokens,
            "end_date": market.get("endDate"),
            "tag": market.get("_tag"),
        }

    us_markets.sort(
        key=lambda market: -float(market.get("volumeNum") or 0)
    )
    out["us_election_market_count"] = len(us_markets)
    out["resolved_us_election_count"] = len(resolved)
    out["us_election_markets"] = [
        summarise(market) for market in us_markets[:20]
    ]
    out["total_candidates_scanned"] = len(candidates)

    # Tokens for the tick-rate sample.
    sample_tokens: list[str] = []
    for market in us_markets[:TICK_SAMPLE_MARKETS]:
        for token in json_field(market.get("clobTokenIds")) or []:
            sample_tokens.append(str(token))
    out["tick_sample"] = {
        "markets": min(len(us_markets), TICK_SAMPLE_MARKETS),
        "tokens": len(sample_tokens),
        "seconds": TICK_SAMPLE_SECONDS,
    }
    return out, sample_tokens


async def measure_tick_rate(tokens: list[str], seconds: int) -> dict[str, Any]:
    """Subscribe to the public market channel and count what arrives."""
    result: dict[str, Any] = {
        "url": CLOB_WS,
        "tokens": len(tokens),
        "seconds": seconds,
    }
    if not tokens:
        result["error"] = "no tokens to sample"
        return result

    try:
        import websockets
    except ImportError:
        result["error"] = "websockets not installed"
        return result

    per_token: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total = 0
    started = time.time()
    try:
        async with websockets.connect(
            CLOB_WS, open_timeout=20, max_size=16 * 1024 * 1024
        ) as socket:
            await socket.send(
                json.dumps({"assets_ids": tokens, "type": "market"})
            )
            deadline = started + seconds
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=5)
                except asyncio.TimeoutError:
                    try:
                        await socket.send("PING")
                    except Exception:  # noqa: BLE001
                        break
                    continue
                if raw in ("PING", "PONG"):
                    try:
                        await socket.send("PONG")
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                for item in parsed if isinstance(parsed, list) else [parsed]:
                    if not isinstance(item, dict):
                        continue
                    total += 1
                    kind = str(item.get("event_type") or "unknown")
                    by_type[kind] = by_type.get(kind, 0) + 1
                    token = str(item.get("asset_id") or "")
                    if token:
                        per_token[token] = per_token.get(token, 0) + 1
        result["connected"] = True
    except Exception as error:  # noqa: BLE001
        result["connected"] = False
        result["error"] = str(error)[:300]

    elapsed = max(1.0, time.time() - started)
    result["messages"] = total
    result["elapsed_seconds"] = round(elapsed, 1)
    result["messages_per_second"] = round(total / elapsed, 3)
    result["messages_per_token_per_second"] = (
        round(total / elapsed / len(tokens), 5) if tokens else None
    )
    result["seconds_per_token_update"] = (
        round(elapsed * len(tokens) / total, 1) if total else None
    )
    result["by_type"] = by_type
    result["busiest_tokens"] = sorted(
        per_token.items(), key=lambda pair: -pair[1]
    )[:8]
    return result


def main() -> None:
    started = time.time()
    output: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "anonymous public endpoints only",
        "kalshi": capture_kalshi(),
    }

    polymarket, tokens = capture_polymarket()
    output["polymarket"] = polymarket

    output["tick_rate"] = asyncio.run(
        measure_tick_rate(tokens, TICK_SAMPLE_SECONDS)
    )
    output["elapsed_seconds"] = round(time.time() - started, 1)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)

    print(f"wrote {OUTPUT_PATH}")
    kalshi = output["kalshi"]
    poly = output["polymarket"]
    tick = output["tick_rate"]
    print(
        f"  kalshi: {kalshi['us_series_count']} US series of "
        f"{kalshi['series_total_in_elections_category']} in Elections"
    )
    print(
        f"  kalshi sample: {kalshi['open_markets_in_sample']} open markets "
        f"across {kalshi['sampled_series']} series"
    )
    print(f"  polymarket: {poly['us_election_market_count']} US election markets")
    print(
        f"  tick: {tick.get('messages')} msgs in {tick.get('elapsed_seconds')}s "
        f"= {tick.get('messages_per_second')}/s, "
        f"{tick.get('messages_per_token_per_second')}/s per token"
    )
    print(f"  elapsed {output['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
