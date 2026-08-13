"""web_search tool — agent internetdə axtarış edir (Tavily).

Agent qeydlərdə OLMAYAN cari/aktual məlumat lazım olduqda bu tool-u çağırır.
Nəticələr başlıq + URL + snippet kimi Claude-a qaytarılır; Claude cavabı
Azərbaycanca qurub mənbə URL-lərini göstərir. Provider yoxdursa (açar yoxdur)
nəzakətli mesaj qaytarılır — agent onu istifadəçiyə çatdırır.
"""

from __future__ import annotations

from typing import Any

from app.logging_conf import get_logger
from app.pricing import search_cost
from app.providers.registry import providers
from app.repositories.usage import log_usage
from app.tools.base import Tool, ToolContext

log = get_logger("tools")


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "İnternetdə axtarış et. Cari/aktual məlumat, xəbər, hava, qiymət, "
        "ümumi faktlar üçün — istifadəçinin şəxsi qeydlərində OLMAYAN məlumat "
        "lazım olduqda. Nəticələr mənbə URL-ləri ilə qayıdır."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Axtarış sorğusu"},
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> str:
        query = (kwargs.get("query") or "").strip()
        if not query:
            return "Axtarış sorğusu boşdur."
        if not providers.has("search"):
            return "Web axtarış deaktivdir (TAVILY_API_KEY yoxdur)."

        try:
            results = await providers.get("search").search(query, max_results=5)
        except Exception as exc:  # noqa: BLE001
            log.error("web_search_failed", query=query, error=str(exc))
            return f"Web axtarışda xəta: {exc}"

        try:
            await log_usage(ctx.session, ctx.user_id, "search", cost=search_cost(1))
        except Exception:  # noqa: BLE001 — usage logu kritik deyil
            pass

        if not results:
            return f"'{query}' üzrə internetdə nəticə tapılmadı."

        lines = [f"'{query}' üzrə internet nəticələri:"]
        for i, r in enumerate(results, 1):
            snippet = r["content"][:300]
            lines.append(f"[{i}] {r['title']}\n{r['url']}\n{snippet}")
        return "\n\n".join(lines)
