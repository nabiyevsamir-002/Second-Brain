"""Abunə provayderi — SDK axını fake `query` ilə (CLI/şəbəkə lazım deyil)."""

import asyncio

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ProcessError,
    RateLimitEvent,
    RateLimitInfo,
    ResultMessage,
    TextBlock,
)

from app.providers import llm_subscription as sub
from app.providers.errors import LLMUnavailableError, SubscriptionLimitError


def _result(text="Bakı", is_error=False, usage=None, cost=0.0012):
    return ResultMessage(
        subtype="success", duration_ms=10, duration_api_ms=8, is_error=is_error,
        num_turns=1, session_id="s", total_cost_usd=cost,
        usage=usage or {"input_tokens": 12, "output_tokens": 3}, result=text,
    )


def _assistant(text, error=None):
    return AssistantMessage(content=[TextBlock(text=text)], model="claude-haiku-4-5", error=error)


def _limit(status="rejected", resets_at=1793628000):
    return RateLimitEvent(
        rate_limit_info=RateLimitInfo(status=status, resets_at=resets_at), uuid="u", session_id="s"
    )


def _fake_query(monkeypatch, messages, raise_after=None):
    seen = {}

    async def fake(*, prompt, options):
        seen["prompt"], seen["options"] = prompt, options
        for m in messages:
            yield m
        if raise_after:
            raise raise_after

    monkeypatch.setattr(sub, "query", fake)
    return seen


def _llm(token=""):
    return sub.SubscriptionLLMProvider("haiku", "haiku", "sonnet", oauth_token=token)


def test_complete_returns_anthropic_like_response(monkeypatch):
    seen = _fake_query(monkeypatch, [_assistant("Bakı"), _result("Bakı")])
    llm = _llm()
    resp = asyncio.run(llm.complete(system="s", messages=[{"role": "user", "content": "paytaxt?"}]))
    assert llm.text_of(resp) == "Bakı"
    assert (resp.usage.input_tokens, resp.usage.output_tokens) == (12, 3)
    opts = seen["options"]
    assert opts.tools == [] and opts.permission_mode == "dontAsk" and opts.strict_mcp_config
    assert opts.env["ANTHROPIC_API_KEY"] == ""  # pullu API-yə səhvən keçməsin
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in opts.env  # token yoxdur → CLI öz girişi
    assert "no-session-persistence" in opts.extra_args


def test_token_goes_to_cli_with_isolated_config():
    opts = _llm(token="tok").options(system="s")
    assert opts.env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"
    assert opts.env["CLAUDE_CONFIG_DIR"].endswith("brain-claude-config")
    assert opts.fallback_model is None and _llm().options(system="s", model="sonnet").fallback_model == "haiku"


def test_image_content_is_sent_as_streaming_message(monkeypatch):
    seen = _fake_query(monkeypatch, [_result("şəkil")])
    blocks = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "x"}}]
    asyncio.run(_llm().complete(system="s", messages=[{"role": "user", "content": blocks}]))

    async def first(stream):
        return [m async for m in stream]

    msgs = asyncio.run(first(seen["prompt"]))
    assert msgs == [{"type": "user", "message": {"role": "user", "content": blocks}}]


def test_weekly_limit_raises_with_reset_time(monkeypatch):
    _fake_query(
        monkeypatch,
        [_limit(), _assistant("You've hit your weekly limit", error="rate_limit"),
         _result("You've hit your weekly limit", is_error=True)],
        raise_after=ProcessError("exit 1", exit_code=1),
    )
    with pytest.raises(SubscriptionLimitError) as info:
        asyncio.run(_llm().complete(system="s", messages=[{"role": "user", "content": "x"}]))
    assert info.value.resets_at == 1793628000


def test_auth_failure_has_a_clear_message(monkeypatch):
    _fake_query(
        monkeypatch, [_assistant("Failed to authenticate", error="authentication_failed")],
        raise_after=ProcessError("exit 1", exit_code=1),
    )
    with pytest.raises(LLMUnavailableError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        asyncio.run(_llm().complete(system="s", messages=[{"role": "user", "content": "x"}]))


def test_warning_level_limit_still_answers(monkeypatch):
    _fake_query(monkeypatch, [_limit("allowed_warning"), _result("Hazır")])
    resp = asyncio.run(_llm().complete(system="s", messages=[{"role": "user", "content": "x"}]))
    assert _llm().text_of(resp) == "Hazır"


def test_timeout_becomes_unavailable(monkeypatch):
    async def slow(*, prompt, options):
        await asyncio.sleep(5)
        yield _result()

    monkeypatch.setattr(sub, "query", slow)
    llm = _llm()
    llm.timeout_sec = 0.05
    with pytest.raises(LLMUnavailableError, match="timeout"):
        asyncio.run(llm.complete(system="s", messages=[{"role": "user", "content": "x"}]))


def test_tools_are_rejected_in_plain_complete():
    with pytest.raises(NotImplementedError):
        asyncio.run(_llm().complete(system="s", messages=[], tools=[{"name": "x"}]))
