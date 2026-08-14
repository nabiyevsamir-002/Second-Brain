"""Model qiymətləri + xərc hesablaması (Phase 5 — /stats).

Qiymətlər 1M token üçün USD-də. Bunlar TƏXMİNİdir (rəsmi elan qiymətləri):
- Claude: claude-api skill (2026) — sonnet-5 $3/$15, haiku-4-5 $1/$5.
- OpenAI: text-embedding-3-small $0.02/1M, whisper-1 $0.006/dəqiqə.
Dəyişsə, buranı yenilə (yeganə mənbə).
"""

from __future__ import annotations

from decimal import Decimal

# (input, output) — 1M token üçün USD.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

EMBED_PRICE_PER_M = 0.02  # text-embedding-3-small (yalnız input)
STT_PRICE_PER_MIN = 0.006  # whisper-1
TTS_PRICE_PER_M = 16.0  # Azure Neural TTS (az-AZ) — 1M simvol üçün USD (təxmini)
SEARCH_PRICE_PER_CALL = 0.008  # Tavily basic search — hər çağırış üçün USD (təxmini)

_M = Decimal(1_000_000)


def llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> Decimal:
    """LLM çağırışının təxmini xərci.

    Prompt caching (Anthropic): cache YAZMA ~1.25× input qiyməti, cache OXUMA
    ~0.1× input qiyməti. Keşlənən sabit prefiks təkrar çağırışlarda çox ucuzdur.
    """
    inp, out = MODEL_PRICES.get(model, (0.0, 0.0))
    inp_d = Decimal(str(inp))
    cost = (
        Decimal(input_tokens) * inp_d
        + Decimal(output_tokens) * Decimal(str(out))
        + Decimal(cache_write_tokens) * inp_d * Decimal("1.25")
        + Decimal(cache_read_tokens) * inp_d * Decimal("0.1")
    ) / _M
    return cost


def embed_cost(tokens: int) -> Decimal:
    """Embedding xərci (text-embedding-3-small)."""
    return Decimal(tokens) * Decimal(str(EMBED_PRICE_PER_M)) / _M


def stt_cost(seconds: float) -> Decimal:
    """Whisper STT xərci (audio uzunluğuna görə)."""
    minutes = Decimal(str(seconds)) / Decimal(60)
    return minutes * Decimal(str(STT_PRICE_PER_MIN))


def tts_cost(chars: int) -> Decimal:
    """Azure Neural TTS xərci (sintez olunan simvol sayına görə)."""
    return Decimal(chars) * Decimal(str(TTS_PRICE_PER_M)) / _M


def search_cost(calls: int = 1) -> Decimal:
    """Tavily web axtarış xərci (çağırış sayına görə, təxmini)."""
    return Decimal(calls) * Decimal(str(SEARCH_PRICE_PER_CALL))
