"""Tavily web axtarış canlı smoke test (agent web_search tool).

İşə salma (açar `.env`-də olduqdan sonra):
    docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts:ro" \
        -e RUN_MIGRATIONS=0 bot python scripts/tavily_smoke.py

Yoxlayır:
  1) search provider açarla qeydiyyatdan keçir.
  2) real sorğu → nəticələr (başlıq + URL + snippet) qayıdır.
  3) agent-də web_search tool qeydiyyatdadır (has_web_search=True).
"""

from __future__ import annotations

import asyncio

from app.providers.factory import init_providers
from app.providers.registry import providers

QUERY = "Azərbaycanın paytaxtı hansı şəhərdir"


async def main() -> int:
    init_providers()
    if not providers.has("search"):
        print("❌ search provider yoxdur — TAVILY_API_KEY .env-də boşdur?")
        return 1
    print("✅ Tavily search provider hazırdır.")

    try:
        results = await providers.get("search").search(QUERY, max_results=3)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Axtarış xətası: {exc}")
        return 1

    print(f"🔎 '{QUERY}' → {len(results)} nəticə:")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r['title'][:70]} — {r['url']}")
        print(f"       {r['content'][:120]}…")

    # Agent tool qeydiyyatını yoxla (search provider varsa tool da olmalıdır).
    agent = providers.get("agent") if providers.has("agent") else None
    tool_ok = bool(agent and getattr(agent, "has_web_search", False)
                   and "web_search" in {t.name for t in agent.tools.all()})
    print(f"🤖 agent.web_search tool qeydiyyatı: {'✅' if tool_ok else '❌'}")

    ok = bool(results) and tool_ok
    print("\n🎯 Nəticə:", "KEÇDİ" if ok else "PROBLEM VAR")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
