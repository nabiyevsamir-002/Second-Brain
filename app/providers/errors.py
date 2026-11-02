"""Provayder xətaları — handler-lər SDK-nı import etmədən tuta bilsin."""

from __future__ import annotations


class LLMUnavailableError(RuntimeError):
    """Claude hazırda cavab verə bilmir (giriş, şəbəkə, CLI xətası, timeout)."""


class SubscriptionLimitError(LLMUnavailableError):
    """Abunə istifadə limiti doldu. resets_at — bərpa vaxtı (unix ts) və ya None."""

    def __init__(self, resets_at: int | None = None) -> None:
        super().__init__("Claude abunə limiti doldu")
        self.resets_at = resets_at
