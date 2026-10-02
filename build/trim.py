"""Trim the cached captures down to what render.py actually reads.

The survey scripts are deliberately greedy: they keep whole catalog pages
so a future question can be answered from cache. Some of those pages are
megabytes and nothing renders them. This drops the unused bulk so the
repository stays small, keeping counts, samples and every figure that
appears in the report.

Usage:
    python3 build/trim.py
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name: str):
    with open(os.path.join(HERE, name), encoding="utf-8") as handle:
        return json.load(handle)


def save(name: str, payload) -> None:
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"  {name}: {os.path.getsize(path) / 1024:,.1f} KB")


def sample(node, limit: int):
    """Keep a list's first `limit` entries, or a dict's keys as counts."""
    if isinstance(node, list):
        return node[:limit]
    return node


def main() -> None:
    print("trimming")

    # data.json -- drop the full series list, keep the counts and a sample.
    data = load("data.json")
    kalshi = data.get("kalshi") or {}
    kalshi.pop("series_list", None)
    for key in ("milestones", "structured_targets", "multivariate_events"):
        node = kalshi.get(key)
        if isinstance(node, dict):
            list_key = next(
                (name for name, value in node.items() if isinstance(value, list)),
                None,
            )
            if list_key:
                node[list_key] = node[list_key][:3]
                node[f"{list_key}_total"] = len(node[list_key])
    # Keep the top-market tables short; the report renders the sports book.
    for key in ("top_markets_by_volume", "top_markets_by_open_interest"):
        if isinstance(kalshi.get(key), list):
            kalshi[key] = kalshi[key][:5]
    if isinstance(kalshi.get("sample_markets"), list):
        kalshi["sample_markets"] = kalshi["sample_markets"][:5]
    data["kalshi"] = kalshi
    save("data.json", data)

    # poly_detail.json -- drop the raw CLOB catalog pages and the v2 spec.
    poly = load("poly_detail.json")
    for key in ("clob_sampling_count", "clob_markets_count", "v2_openapi_paths"):
        node = poly.pop(key, None)
        if isinstance(node, dict):
            poly[f"{key}_summary"] = {
                name: value
                for name, value in node.items()
                if not isinstance(value, (list, dict))
            }
    focus = poly.get("focus") or {}
    for outcome in ("outcome_1", "outcome_2"):
        node = focus.get(outcome) or {}
        history = (node.get("prices_history") or {}).get("history")
        if isinstance(history, list) and len(history) > 400:
            node["prices_history"]["history"] = history[:400]
            node["prices_history"]["history_truncated_from"] = len(history)
    if isinstance((focus.get("data_trades") or {}).get("data"), list):
        focus["data_trades"]["data"] = focus["data_trades"]["data"][:10]
    poly["focus"] = focus
    save("poly_detail.json", poly)

    # final.json -- keep the candle series, they are the chart.
    final = load("final.json")
    save("final.json", final)


if __name__ == "__main__":
    main()
