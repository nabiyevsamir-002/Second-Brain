"""Tavily web axtarış provider — agent üçün internet axtarışı.

Tavily LLM-lər üçün optimallaşdırılmış axtarış API-sidir: qısa, təmiz snippet-lər
qaytarır. `AsyncTavilyClient` native async-dır (thread lazım deyil).

Nəticə normallaşdırılır: [{title, url, content}] siyahısı — tool bunu Claude-a
mətn kimi ötürür, Claude cavabı Azərbaycanca qurub mənbə URL-lərini göstərir.
"""

from __future__ import annotations

from typing import Any

from tavily import AsyncTavilyClient


class TavilySearchProvider:
    def __init__(self, api_key: str) -> None:
        self.client = AsyncTavilyClient(api_key=api_key)

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        resp = await self.client.search(
            query,
            max_results=max_results,
            search_depth="basic",  # "advanced" bahalıdır — sadə üçün basic kifayətdir
        )
        results = resp.get("results", []) if isinstance(resp, dict) else []
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content", "") or "").strip(),
            }
            for r in results
        ]
