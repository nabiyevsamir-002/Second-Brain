"""BrainAgent — Claude tool-use döngəsi (manual loop, AsyncAnthropic)."""

from __future__ import annotations

from typing import Any

from app.logging_conf import get_logger
from app.models import NoteSource
from app.providers.llm_claude import ClaudeLLMProvider
from app.repositories.usage import log_llm_usage
from app.timeutils import now_local_prompt
from app.tools.base import ToolContext
from app.tools.activity_report import ActivityReportTool
from app.tools.create_reminder import CreateReminderTool
from app.tools.create_task import CreateTaskTool
from app.tools.registry import ToolRegistry
from app.tools.save_note import SaveNoteTool
from app.tools.search_notes import SearchNotesTool
from app.tools.summarize_category import SummarizeCategoryTool

log = get_logger("agent")

MAX_TOOL_ROUNDS = 5

# --- System prompt: STATİK hissə (prompt caching üçün) --------------------
# Cari vaxt AYRICA dinamik blokda gedir (aşağı bax) — beləliklə statik hissə +
# tool sxemaları dəyişmir və Anthropic prompt caching ilə keşlənir (cache read
# ~0.1× qiymət). Keyfiyyət eyni qalır; yalnız təkrar göndərilən sabit prefiks ucuzlaşır.
AGENT_SYSTEM_STATIC = (
    "Sən Samir-in şəxsi 'Second Brain' assistentisən.\n"
    "DİL: cavabı istifadəçinin sonuncu mesajının DİLİNDƏ ver (default Azərbaycanca). "
    "Azərbaycanca yazsa Azərbaycanca, ingiliscə yazsa ingiliscə, rusca yazsa rusca cavab ver.\n\n"
    "Gələn mesajın niyyətini anla və uyğun aləti çağır:\n\n"
    "• XATIRLATMA — istifadəçi müəyyən vaxtda xəbərdar edilmək istəyir ('...-ı "
    "xatırlat', 'yadıma sal') → `create_reminder` (text + remind_at, local ISO). "
    "İstifadəçi mövcud və ya yeni saxlanmış qeydə istinad edib xatırlatma istəsə "
    "('bunu sabah xatırlat'), qeydin məzmununu text kimi istifadə et.\n\n"
    "• TAPŞIRIQ — görüləcək iş / todo əlavə etmək ('tapşırıq əlavə et', 'et', "
    "'bitir', deadline) → `create_task` (title + istəyə bağlı due_at). Təkrarlanma "
    "istənsə ('hər gün', 'hər həftə', 'hər ay') → recur ver.\n\n"
    "• QEYD — fikir, məlumat, sadəcə yadda saxlamaq → `save_note` (content = mesaj). "
    "Saxladıqdan sonra qısa təsdiq ver: kateqoriya, tag-lar və varsa əlaqəli qeydlər.\n\n"
    "• SUAL / axtarış — mövcud qeydlər barədə ('nə vaxt', 'harada', '... haqqında nə "
    "yazmışdım', 'tap', 'hansı') → `search_notes`, sonra tapılan qeydlərə ƏSASLANARAQ "
    "cavab ver və istifadə etdiyin qeydləri [#id] ilə SİTAT gətir. Uydurma etmə.\n\n"
    "• XÜLASƏ — bir kateqoriyanın/mövzunun qeydlərini ümumiləşdirmək ('iş qeydlərimi "
    "xülasə et', 'ideyalarımı ümumiləşdir') → `summarize_category` (category), sonra qısa xülasə yaz.\n\n"
    "• FƏALİYYƏT — 'bu həftə/dövrdə nə etdim?', 'son 3 gündə nə oldu?' → `activity_report` "
    "(days), sonra təbii, qısa icmal yaz.\n\n"
    "{web_search_intent}"
    "Qaydalar:\n"
    "- Vaxt qeyd olunubsa və istifadəçi xəbərdar edilmək istəyirsə → create_reminder; "
    "sadəcə görüləcək işdirsə → create_task; qalan hallarda şübhə varsa → save_note.\n"
    "- Niyyət və ya vacib detal (məs. xatırlatma vaxtı) HƏQİQƏTƏN qeyri-müəyyəndirsə, "
    "hərəkətdən ƏVVƏL bir QISA dəqiqləşdirici sual ver. Amma şübhə yoxdursa soruşma — "
    "hər mesajda soruşma, gərəksiz sual vermə.\n"
    "- search_notes boş nəticə verirsə: 'Bu barədə qeyd tapmadım' de.\n"
    "- Cavabların qısa və aydın olsun."
)


WEB_SEARCH_INTENT = (
    "• İNTERNET AXTARIŞ — cari/aktual məlumat, xəbər, hava, qiymət, ümumi faktlar "
    "(istifadəçinin qeydlərində OLMAYAN, internetdən) → `web_search`; sonra "
    "nəticələrə ƏSASLANARAQ cavab ver və mənbə URL-lərini göstər. "
    "Uydurma etmə. (Şəxsi qeydlər üçün search_notes, internet üçün web_search.)\n\n"
)

# Escalation (task #2): sadə mesaj Haiku-da qalır, YALNIZ analitik/mürəkkəb sual
# smart modelə (Sonnet) qalxır. Keyfiyyəti çətin suallarda artırır, xərci sadə
# hallarda aşağı saxlayır. Aşağıdakı işarələr → mürəkkəb sayılır.
_COMPLEX_HINTS = (
    "müqayisə", "təhlil", "analiz", "izah et", "niyə", "səbəb", "strategiya",
    "plan qur", "addım-addım", "hansı daha", "üstünlük", "fərq", "qiymətləndir",
    "nəticə çıxar", "ümumiləşdir", "tövsiyə et", "debug", "hesabla", "düstur",
    "compare", "analyze", "explain",
)


def is_complex_query(user_text: str) -> bool:
    """Mesaj analitik/mürəkkəb görünürsə True (escalation üçün) — saf funksiya."""
    t = (user_text or "").lower()
    return (
        len(t) > 220
        or t.count("?") >= 2
        or any(h in t for h in _COMPLEX_HINTS)
    )


def _system_blocks(has_web_search: bool, now: str) -> list[dict[str, Any]]:
    """System-i 2 blok kimi qur: [statik (keşlənir)] + [cari vaxt (dinamik)].

    cache_control statik blokda → tools + statik system keşlənir. Cari vaxt bloku
    breakpoint-dən SONRA gəlir, ona görə keşi pozmur (hər dəqiqə dəyişsə də).
    """
    static = AGENT_SYSTEM_STATIC.format(
        web_search_intent=WEB_SEARCH_INTENT if has_web_search else ""
    )
    return [
        {"type": "text", "text": static, "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": (
                f"CARİ VAXT (Asia/Baku): {now}. Nisbi vaxtları ('sabah', "
                "'2 saatdan sonra', 'cümə axşamı 9-da') HƏMİŞƏ bu vaxta əsasən hesabla."
            ),
        },
    ]


def build_system(has_web_search: bool = False) -> str:
    """Düz mətn system prompt (geriyə uyğunluq / test üçün)."""
    return AGENT_SYSTEM_STATIC.format(
        web_search_intent=WEB_SEARCH_INTENT if has_web_search else ""
    ) + f"\n\nCARİ VAXT (Asia/Baku): {now_local_prompt()}."


class BrainAgent:
    def __init__(self, llm: ClaudeLLMProvider) -> None:
        self.llm = llm
        self.tools = ToolRegistry()
        self.tools.register(SaveNoteTool())
        self.tools.register(SearchNotesTool())
        self.tools.register(CreateReminderTool())
        self.tools.register(CreateTaskTool())
        self.tools.register(SummarizeCategoryTool())
        self.tools.register(ActivityReportTool())

        # web_search yalnız Tavily provider varsa qeydiyyatdan keçir (yoxdursa
        # Claude-a təklif olunmur).
        from app.providers.registry import providers

        self.has_web_search = providers.has("search")
        if self.has_web_search:
            from app.tools.web_search import WebSearchTool

            self.tools.register(WebSearchTool())

        from app.config import settings as _settings

        self.escalation_enabled = _settings.escalation_enabled
        # Tool sxemalarını bir dəfə keşlə + sonuncuya cache_control qoy (prompt
        # caching: tools + statik system keşlənən sabit prefiksdir).
        self._tool_schemas = self.tools.schemas()
        if self._tool_schemas:
            self._tool_schemas[-1] = {
                **self._tool_schemas[-1],
                "cache_control": {"type": "ephemeral"},
            }

    def _pick_model(self, user_text: str) -> str:
        """Sadə mesaj → Haiku (ucuz); analitik/mürəkkəb sual → smart (Sonnet).

        Keyfiyyət balansı: escalation yalnız həqiqətən çətin suallarda işə düşür.
        """
        if not self.escalation_enabled:
            return self.llm.model_fast
        return self.llm.model_smart if is_complex_query(user_text) else self.llm.model_fast

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

        # System = keşlənən statik blok + dinamik cari vaxt bloku (prompt caching).
        system = _system_blocks(self.has_web_search, now_local_prompt())
        # Model seçimi bütün tur üçün bir dəfə (sadə=Haiku, mürəkkəb=Sonnet).
        model = self._pick_model(user_text)
        for _ in range(MAX_TOOL_ROUNDS):
            resp = await self.llm.complete(
                system=system,
                messages=messages,
                tools=self._tool_schemas,
                model=model,
                max_tokens=2048,
            )
            try:
                await log_llm_usage(session, user_id, model, resp.usage)
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
