"""Web search via DuckDuckGo (ddgs): return the top results as title/url/snippet.

A read-only ``deep_web_search`` skill. It declares the ``network`` permission and runs in the
sandbox; the query comes from the trusted caller (never from retrieved content — the taint
boundary). A blocked or flaky search degrades to an empty result list rather than raising.
"""

from __future__ import annotations

from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    max_results = int(arguments.get("max_results", 5))
    if not query:
        return {"query": query, "results": []}

    from ddgs import DDGS  # imported lazily so loading the manifest needs no network deps

    results: list[dict[str, str]] = []
    try:
        for hit in DDGS().text(query, max_results=max_results):
            results.append(
                {
                    "title": str(hit.get("title", "")),
                    "url": str(hit.get("href", "")),
                    "snippet": str(hit.get("body", "")),
                }
            )
    except Exception:
        pass
    return {"query": query, "results": results}
