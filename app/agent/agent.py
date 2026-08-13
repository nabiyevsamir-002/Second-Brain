"""BrainAgent — Claude tool-use döngəsi (manual loop, AsyncAnthropic)."""

from __future__ import annotations

from typing import Any

from app.logging_conf import get_logger
from app.models import NoteSource
from app.providers.llm_claude import ClaudeLLMProvider
from app.repositories.usage import log_llm_usage
from app.timeutils import now_local_prompt
from app.tools.base import ToolContext
from app.tools.create_reminder import CreateReminderTool
from app.tools.create_task import CreateTaskTool
from app.tools.registry import ToolRegistry
from app.tools.save_note import SaveNoteTool
from app.tools.search_notes import SearchNotesTool

log = get_logger("agent")

MAX_TOOL_ROUNDS = 5

AGENT_SYSTEM_TMPL = (
    "Sən Samir-in şəxsi 'Second Brain' assistentisən. HƏMIŞƏ Azərbaycanca cavab ver.\n"
    "CARİ VAXT (Asia/Baku): {now}. Nisbi vaxtları ('sabah', '2 saatdan sonra', "
    "'cümə axşamı 9-da') HƏMİŞƏ bu vaxta əsasən hesabla.\n\n"
    "Gələn mesajın niyyətini anla və uyğun aləti çağır:\n\n"
    "• XATIRLATMA — istifadəçi müəyyən vaxtda xəbərdar edilmək istəyir ('...-ı "
    "xatırlat', 'yadıma sal') → `create_reminder` (text + remind_at, local ISO).\n\n"
    "• TAPŞIRIQ — görüləcək iş / todo əlavə etmək ('tapşırıq əlavə et', 'et', "
    "'bitir', deadline) → `create_task` (title + istəyə bağlı due_at).\n\n"
    "• QEYD — fikir, məlumat, sadəcə yadda saxlamaq → `save_note` (content = mesaj). "
    "Saxladıqdan sonra qısa təsdiq ver: kateqoriya, tag-lar və varsa əlaqəli qeydlər.\n\n"
    "• SUAL / axtarış — mövcud qeydlər barədə ('nə vaxt', 'harada', '... haqqında nə "
    "yazmışdım', 'tap', 'hansı') → `search_notes`, sonra tapılan qeydlərə ƏSASLANARAQ "
    "cavab ver və istifadə etdiyin qeydləri [#id] ilə SİTAT gətir. Uydurma etmə.\n\n"
    "Qaydalar:\n"
    "- Vaxt qeyd olunubsa və istifadəçi xəbərdar edilmək istəyirsə → create_reminder; "
    "sadəcə görüləcək işdirsə → create_task; qalan hallarda şübhə varsa → save_note.\n"
    "- search_notes boş nəticə verirsə: 'Bu barədə qeyd tapmadım' de.\n"
    "- Cavabların qısa, aydın və Azərbaycanca olsun."
)


def build_system() -> str:
    """System prompt-u cari local vaxtla qur (nisbi vaxt hesablaması üçün)."""
    return AGENT_SYSTEM_TMPL.format(now=now_local_prompt())


class BrainAgent:
    def __init__(self, llm: ClaudeLLMProvider) -> None:
        self.llm = llm
        self.tools = ToolRegistry()
        self.tools.register(SaveNoteTool())
        self.tools.register(SearchNotesTool())
        self.tools.register(CreateReminderTool())
        self.tools.register(CreateTaskTool())

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

        system = build_system()
        for _ in range(MAX_TOOL_ROUNDS):
            resp = await self.llm.complete(
                system=system,
                messages=messages,
                tools=self.tools.schemas(),
                model=self.llm.model_main,
                max_tokens=2048,
            )
            try:
                await log_llm_usage(session, user_id, self.llm.model_main, resp.usage)
            except Exception:  # noqa: BLE001 — usage logu kritik deyil
                pass

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
