from decimal import Decimal

from app.pricing import embed_cost, llm_cost, search_cost, stt_cost, tts_cost


def test_llm_cost_uses_per_million_prices():
    assert llm_cost("claude-haiku-4-5", 1_000_000, 0) == Decimal("1")
    assert llm_cost("claude-haiku-4-5", 0, 1_000_000) == Decimal("5")
    assert llm_cost("claude-sonnet-5", 500_000, 100_000) == Decimal("3")


def test_llm_cost_prices_cache_writes_and_reads():
    # Yazma 1.25×, oxuma 0.1× input qiyməti.
    assert llm_cost("claude-sonnet-5", 0, 0, cache_write_tokens=1_000_000) == Decimal("3.75")
    assert llm_cost("claude-sonnet-5", 0, 0, cache_read_tokens=1_000_000) == Decimal("0.3")


def test_llm_cost_is_zero_for_unknown_model():
    assert llm_cost("unknown-model", 1_000_000, 1_000_000) == 0


def test_other_costs():
    assert embed_cost(1_000_000) == Decimal("0.02")
    assert stt_cost(90) == Decimal("0.009")
    assert tts_cost(1_000_000) == Decimal("16")
    assert search_cost(3) == Decimal("0.024")
