"""Backend seçimi (auto/subscription/api/local) və factory — model yüklənmir."""

import math

import pytest

from app.config import Settings, settings
from app.providers import factory
from app.providers.embeddings_local import LocalEmbeddingProvider, pad_unit
from app.providers.registry import providers
from app.providers.stt_local import LocalWhisperSTTProvider


def _s(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_llm_backend_resolution():
    assert _s().resolved_llm_backend == "none"
    assert _s(anthropic_api_key="k").resolved_llm_backend == "api"
    # Abunə tokeni API açarından üstündür ("yalnız abunə" tələbi).
    assert _s(anthropic_api_key="k", claude_code_oauth_token="t").resolved_llm_backend == "subscription"
    assert _s(llm_backend="subscription").resolved_llm_backend == "subscription"  # Mac: CLI girişi
    assert _s(llm_backend="API", claude_code_oauth_token="t").resolved_llm_backend == "api"


def test_embed_and_stt_default_to_local_without_openai_key():
    assert _s().resolved_backend("auto") == "local"
    assert _s(openai_api_key="k").resolved_backend("auto") == "openai"
    assert _s(openai_api_key="k").resolved_backend("local") == "local"


def test_email_enabled_needs_all_fields():
    assert not _s(email_imap_host="imap.gmail.com", email_address="a@b.az").email_enabled
    assert _s(email_imap_host="h", email_address="a", email_password="p").email_enabled


def test_pad_unit_keeps_cosine():
    a, b = pad_unit([3.0, 4.0]), pad_unit([4.0, 3.0])
    assert len(a) == 1536 and math.isclose(sum(x * x for x in a), 1.0)
    assert math.isclose(sum(x * y for x, y in zip(a, b)), 24 / 25)
    with pytest.raises(ValueError):
        pad_unit([1.0] * 2000)


@pytest.fixture
def clean_registry(monkeypatch):
    monkeypatch.setattr(providers, "_providers", {})
    for key, value in {
        "llm_backend": "auto", "claude_code_oauth_token": "tok", "anthropic_api_key": "",
        "openai_api_key": "", "embed_backend": "auto", "stt_backend": "auto",
        "azure_speech_key": "", "tavily_api_key": "sk-tavily", "email_imap_host": "imap.x.az",
        "email_address": "s@x.az", "email_password": "p", "model_cache_dir": "/models",
    }.items():
        monkeypatch.setattr(settings, key, value)
    return providers


def test_factory_builds_subscription_stack_without_api_keys(clean_registry):
    factory.init_providers()
    from app.agent.sdk_agent import SDKBrainAgent
    from app.providers.llm_subscription import SubscriptionLLMProvider

    assert isinstance(providers.get("llm"), SubscriptionLLMProvider)
    assert isinstance(providers.get("embed"), LocalEmbeddingProvider)
    assert providers.get("embed").cache_dir == "/models/fastembed"
    assert isinstance(providers.get("stt"), LocalWhisperSTTProvider)
    assert not providers.has("search")  # Tavily yox — daxili WebSearch
    agent = providers.get("agent")
    assert isinstance(agent, SDKBrainAgent)
    assert {"save_note", "check_email", "read_email", "search_email"} <= set(agent._names)
