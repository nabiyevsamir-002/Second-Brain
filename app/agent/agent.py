"""BrainAgent — Claude tool-use döngəsi (manual loop, AsyncAnthropic)."""

from __future__ import annotations

from typing import Any

from app.logging_conf import get_logger
from app.models import NoteSource
from app.providers.llm_claude import ClaudeLLMProvider
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.save_note import SaveNoteTool
from app.tools.search_notes import SearchNotesTool

log = get_logger("agent")

MAX_TOOL_ROUNDS = 5

AGENT_SYSTEM = (
    "Sən Samir-in şəxsi 'Second Brain' assistentisən. HƏMIŞƏ Azərbaycanca cavab ver.\n"
    "Gələn mesajın niyyətini anla və uyğun aləti çağır:\n\n"
    "• Mesaj bir QEYD, fikir, tapşırıq, məlumat və ya xatırlatmadırsa (istifadəçi "
    "nəyisə yadda saxlamaq istəyir) → `save_note` aləti (content = mesajın mətni). "
    "Saxladıqdan sonra qısa təsdiq ver: kateqoriya, tag-lar və varsa əlaqəli qeydlər.\n\n"
    "• Mesaj SUAL və ya mövcud qeydlər barədə axtarışdırsa ('nə vaxt', 'harada', "
    "'... haqqında nə yazmışdım', 'tap', 'xatırlat', 'hansı') → `search_notes` aləti, "
    "sonra tapılan qeydlərə ƏSASLANARAQ cavab ver və istifadə etdiyin qeydləri [#id] "
    "ilə SİTAT gətir. Uydurma etmə — yalnız tapılan qeydlərdən danış.\n\n"
    "Qaydalar:\n"
    "- Şübhə varsa, mesajı qeyd kimi saxla (default = save_note).\n"
    "- search_notes boş nəticə verirsə: 'Bu barədə qeyd tapmadım' de.\n"
    "- Cavabların qısa, aydın və Azərbaycanca olsun."
)


class BrainAgent:
    def __init__(self, llm: ClaudeLLMProvider) -> None:
        self.llm = llm
        self.tools = ToolRegistry()
        self.tools.register(SaveNoteTool())
        self.tools.register(SearchNotesTool())

    async def handle(
        self,
        session: Any,
        user_id: int,
        user_text: str,
        source: NoteSource,
        embedder: Any,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        ctx = ToolContext(
            session=session,
            user_id=user_id,
            llm=self.llm,
            embedder=embedder,
            source=source,
        )

        hist = list(history or [])
        # Anthropic tələbi: ilk mesaj "user" olmalıdır.
        while hist and hist[0]["role"] != "user":
            hist.pop(0)

        messages: list[dict[str, Any]] = hist + [{"role": "user", "content": user_text}]

        for _ in range(MAX_TOOL_ROUNDS):
            resp = await self.llm.complete(
                system=AGENT_SYSTEM,
                messages=messages,
                tools=self.tools.schemas(),
                model=self.llm.model_main,
                max_tokens=2048,
            )

            if resp.stop_reason != "tool_use":
                text = self.llm.text_of(resp).strip()
                return text or "Hazırdır."

            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                try:
                    out = await self.tools.get(block.name).run(ctx, **block.input)
                except Exception as exc:  # noqa: BLE001
                    log.error("tool_error", tool=block.name, error=str(exc))
                    out = f"Alət xətası: {exc}"
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": out}
                )
            messages.append({"role": "user", "content": results})

        return "Emal tamamlana bilmədi — təkrar yoxla."
