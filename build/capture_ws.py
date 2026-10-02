"""Capture live WebSocket frames from the public prediction-market feeds.

Public, no credentials:
  - Polymarket CLOB market channel (order book / price / trade)
  - Polymarket sports channel (live scores)
  - Kalshi WS is attempted anonymously as well, and the outcome is
    recorded, so the report can state the handshake requirement from
    evidence rather than from documentation alone.

Usage:
    python3 build/capture_ws.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import urllib.request
import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(HERE, "ws_frames.json")

CLOB_MARKET_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
SPORTS_WS = "wss://sports-api.polymarket.com/ws"
KALSHI_WS = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"

USER_AGENT = "prediction-markets-report/1.0 (public data survey)"


def busiest_token() -> str | None:
    """Pick the outcome token of the highest-volume open market."""
    url = (
        "https://gamma-api.polymarket.com/markets?closed=false&limit=1"
        "&order=volumeNum&ascending=false"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            rows = json.loads(response.read())
    except Exception:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    tokens = rows[0].get("clobTokenIds")
    if isinstance(tokens, str):
        try:
            tokens = json.loads(tokens)
        except json.JSONDecodeError:
            return None
    if isinstance(tokens, list) and tokens:
        return str(tokens[0])
    return None


async def capture_clob_market(token: str, seconds: float = 25.0) -> dict:
    """Subscribe to the public CLOB market channel and keep raw frames."""
    result: dict[str, Any] = {"url": CLOB_MARKET_WS, "token_id": token}
    frames: list[dict] = []
    try:
        async with websockets.connect(
            CLOB_MARKET_WS, open_timeout=20, max_size=8 * 1024 * 1024
        ) as socket:
            await socket.send(
                json.dumps(
                    {
                        "assets_ids": [token],
                        "type": "market",
                    }
                )
            )
            deadline = time.time() + seconds
            while time.time() < deadline and len(frames) < 40:
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=8)
                except asyncio.TimeoutError:
                    try:
                        await socket.send("PING")
                    except Exception:
                        break
                    continue
                if raw in ("PING", "PONG"):
                    try:
                        await socket.send("PONG")
                    except Exception:
                        pass
                    continue
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list):
                    frames.extend(parsed)
                else:
                    frames.append(parsed)
        result["connected"] = True
    except Exception as error:  # noqa: BLE001
        result["connected"] = False
        result["error"] = str(error)[:300]
    result["frame_count"] = len(frames)
    result["frames"] = frames[:25]
    return result


async def capture_sports(seconds: float = 20.0) -> dict:
    """The sports channel needs no subscription; connect and read."""
    result: dict[str, Any] = {"url": SPORTS_WS}
    frames: list[dict] = []
    try:
        async with websockets.connect(
            SPORTS_WS, open_timeout=20, max_size=8 * 1024 * 1024
        ) as socket:
            deadline = time.time() + seconds
            while time.time() < deadline and len(frames) < 25:
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=8)
                except asyncio.TimeoutError:
                    break
                if raw in ("ping", "pong"):
                    if raw == "ping":
                        try:
                            await socket.send("pong")
                        except Exception:
                            pass
                    continue
                try:
                    frames.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        result["connected"] = True
    except Exception as error:  # noqa: BLE001
        result["connected"] = False
        result["error"] = str(error)[:300]
    result["frame_count"] = len(frames)
    result["frames"] = frames[:20]
    return result


async def probe_kalshi_unauthenticated() -> dict:
    """Try the Kalshi socket with no credentials and record the result."""
    result: dict[str, Any] = {"url": KALSHI_WS}
    try:
        async with websockets.connect(
            KALSHI_WS,
            open_timeout=20,
            additional_headers={"User-Agent": USER_AGENT},
        ) as socket:
            await socket.send(
                json.dumps(
                    {
                        "id": 1,
                        "cmd": "subscribe",
                        "params": {
                            "channels": ["ticker"],
                            "market_tickers": ["KXBTCD-25AUG0517-T114999.99"],
                        },
                    }
                )
            )
            raw = await asyncio.wait_for(socket.recv(), timeout=12)
            result["connected"] = True
            result["first_frame"] = raw[:500]
    except Exception as error:  # noqa: BLE001
        result["connected"] = False
        result["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    return result


async def main() -> None:
    token = busiest_token()
    payload: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kalshi_unauthenticated_ws": await probe_kalshi_unauthenticated(),
        "clob_market": (
            await capture_clob_market(token) if token else {"error": "no token"}
        ),
        "sports": await capture_sports(),
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"wrote {OUTPUT_PATH}")
    print("kalshi unauth connected:", payload["kalshi_unauthenticated_ws"].get("connected"))
    if payload["kalshi_unauthenticated_ws"].get("error"):
        print("  error:", payload["kalshi_unauthenticated_ws"]["error"])
    print("clob frames:", payload["clob_market"].get("frame_count"))
    print("sports frames:", payload["sports"].get("frame_count"))


if __name__ == "__main__":
    asyncio.run(main())
