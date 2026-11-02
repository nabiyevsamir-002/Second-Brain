"""Claude abunəsi (Pro/Max) üzərindən LLM — Claude Agent SDK (Claude Code CLI).

API açarı YOX: CLI `CLAUDE_CODE_OAUTH_TOKEN` (bir dəfə `claude setup-token`) ilə
abunəyə qoşulur. Hər çağırış CLI subprocess-i işə salır (~2-4 san əlavə gecikmə).
`complete()/text_of()` ClaudeLLMProvider ilə eynidir — servislər dəyişmir.

Təhlükəsizlik: Claude Code-un daxili alətləri (Bash, fayl, WebFetch...) SÖNDÜRÜLÜR —
yalnız açıq verilənlər işləyir. ANTHROPIC_API_KEY subprocess-ə ötürülmür ki, CLI
səhvən pullu API-yə keçməsin.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    RateLimitEvent,
    ResultMessage,
    TextBlock,
    query,
)

from app.logging_conf import get_logger
from app.providers.base import LLMProvider
from app.providers.errors import LLMUnavailableError, SubscriptionLimitError

log = get_logger("llm_subscription")

AUTH_FAILED = "Claude girişi uğursuz — CLAUDE_CODE_OAUTH_TOKEN-i yoxla (claude setup-token)"


@dataclass
class RunResult:
    text: str
    usage: Any  # input_tokens/output_tokens/cache_* — log_llm_usage üçün
    cost_usd: float  # API ekvivalenti (abunədə real ödəniş yoxdur)
    num_turns: int = 0


def _usage_ns(usage: dict | None) -> SimpleNamespace:
    u = usage or {}
    return SimpleNamespace(
        input_tokens=int(u.get("input_tokens", 0) or 0),
        output_tokens=int(u.get("output_tokens", 0) or 0),
        cache_creation_input_tokens=int(u.get("cache_creation_input_tokens", 0) or 0),
        cache_read_input_tokens=int(u.get("cache_read_input_tokens", 0) or 0),
    )


async def _single_message(content: list[dict[str, Any]]):
    """Streaming input: şəkil kimi content bloklu tək user mesajı."""
    yield {"type": "user", "message": {"role": "user", "content": content}}


def _to_prompt(messages: list[dict[str, Any]]) -> str | Any:
    """API-formatlı messages → SDK prompt (mətn və ya content bloklu stream)."""
    content = messages[-1]["content"] if messages else ""
    if isinstance(content, str):
        return content
    return _single_message(content)


class SubscriptionLLMProvider(LLMProvider):
    backend = "subscription"

    def __init__(
        self,
        model_main: str,
        model_fast: str,
        model_smart: str | None = None,
        *,
        oauth_token: str = "",
        timeout_sec: int = 180,
    ) -> None:
        self.model_main = model_main
        self.model_fast = model_fast
        self.model_smart = model_smart or model_main
        self._token = oauth_token
        self.timeout_sec = timeout_sec
        # CLI üçün boş iş qovluğu — layihə fayllarını görməsin, CLAUDE.md yükləməsin.
        self._cwd = tempfile.mkdtemp(prefix="brain_cli_")

    def _env(self) -> dict[str, str]:
        env = {"ANTHROPIC_API_KEY": "", "DISABLE_AUTOUPDATER": "1"}
        if self._token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self._token
            # Ayrıca config qovluğu: hostdakı istifadəçi pluginləri/hook-ları/MCP yüklənməsin.
            env["CLAUDE_CONFIG_DIR"] = os.path.join(tempfile.gettempdir(), "brain-claude-config")
        # Token yoxdursa CLI öz saxlanmış girişini işlədir (Mac-də `claude` ilə daxil olunubsa).
        return env

    def options(
        self,
        *,
        system: str,
        model: str | None = None,
        tools: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_turns: int = 1,
    ) -> ClaudeAgentOptions:
        model = model or self.model_main
        return ClaudeAgentOptions(
            system_prompt=system,
            model=model,
            fallback_model=self.model_fast if model != self.model_fast else None,
            tools=list(tools or []),  # [] → heç bir daxili Claude Code aləti yoxdur
            allowed_tools=list(allowed_tools or []),
            mcp_servers=mcp_servers or {},
            permission_mode="dontAsk",  # icazəsi verilməyən alət → rədd (sual yox)
            strict_mcp_config=True,  # yalnız bizim MCP server — kənar MCP konfiqurasiyası yox
            max_turns=max_turns,
            cwd=self._cwd,
            env=self._env(),
            # Transkriptlər diskə yazılmasın (24/7 işdə şişməsin); skill/slash əmrləri yox.
            extra_args={"no-session-persistence": None, "disable-slash-commands": None},
        )

    async def run(self, prompt: str | Any, options: ClaudeAgentOptions) -> RunResult:
        """Bir SDK sorğusu: son cavab mətni + usage. Limit/xəta → LLMUnavailableError."""
        texts: list[str] = []
        limit = None
        error: str | None = None
        result: ResultMessage | None = None
        stream = query(prompt=prompt, options=options)
        try:
            async with asyncio.timeout(self.timeout_sec):
                async for msg in stream:
                    if isinstance(msg, AssistantMessage):
                        error = msg.error or error
                        texts = [b.text for b in msg.content if isinstance(b, TextBlock)] or texts
                    elif isinstance(msg, RateLimitEvent):
                        limit = msg.rate_limit_info
                    elif isinstance(msg, ResultMessage):
                        result = msg
        except TimeoutError as exc:
            raise LLMUnavailableError("Claude vaxtında cavab vermədi (timeout)") from exc
        except ClaudeSDKError as exc:
            if error == "rate_limit" or (limit is not None and limit.status == "rejected"):
                raise SubscriptionLimitError(getattr(limit, "resets_at", None)) from exc
            log.error("claude_cli_failed", error=str(exc), assistant_error=error)
            if error == "authentication_failed":
                raise LLMUnavailableError(AUTH_FAILED) from exc
            raise LLMUnavailableError(f"Claude CLI xətası: {exc}") from exc
        finally:
            with contextlib.suppress(Exception):
                await stream.aclose()  # timeout/xətada da CLI subprocess-i bağlansın

        rejected = limit is not None and limit.status == "rejected"
        if error == "rate_limit" or (rejected and (result is None or result.is_error)):
            raise SubscriptionLimitError(getattr(limit, "resets_at", None))
        if error == "authentication_failed":
            raise LLMUnavailableError(AUTH_FAILED)
        if result is None or (result.is_error and not (result.result or texts)):
            detail = (result.subtype if result else "nəticə yoxdur") + (f", {error}" if error else "")
            raise LLMUnavailableError(f"Claude cavabı alınmadı ({detail})")

        if limit is not None and limit.status == "allowed_warning":
            log.warning("subscription_limit_warning", utilization=limit.utilization,
                        resets_at=limit.resets_at)
        text = (result.result or "\n".join(texts)).strip()
        return RunResult(
            text=text,
            usage=_usage_ns(result.usage),
            cost_usd=float(result.total_cost_usd or 0.0),
            num_turns=result.num_turns,
        )

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Any:
        """Alətsiz tək cavab (təmizlə/xülasə/vision) — Anthropic cavabına bənzər obyekt."""
        if tools:
            raise NotImplementedError("Abunə rejimində alətli çağırış SDKBrainAgent-dədir")
        res = await self.run(_to_prompt(messages), self.options(system=system, model=model))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=res.text)],
            stop_reason="end_turn",
            usage=res.usage,
        )

    @staticmethod
    def text_of(response: Any) -> str:
        return "".join(b.text for b in response.content if b.type == "text")
