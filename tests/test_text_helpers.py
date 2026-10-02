from app.agent.agent import is_complex_query
from app.bot.handlers import MAX_TTS_CHARS, _clean_for_speech, _fmt_uptime, _voice_settings
from app.config import Settings, settings
from app.services.ingest_service import chunk_text
from app.services.notes_service import _parse_json


# --- chunk_text -------------------------------------------------------------

def test_chunk_text_short_and_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert chunk_text("  qısa mətn  ") == ["qısa mətn"]


def test_chunk_text_splits_with_overlap():
    text = "".join(chr(ord("a") + i % 26) for i in range(25))
    chunks = chunk_text(text, size=10, overlap=2)
    assert [len(c) for c in chunks] == [10, 10, 9, 1]
    assert chunks[1][:2] == chunks[0][-2:]
    assert chunks[0] + chunks[1][2:] + chunks[2][2:] == text


# --- _parse_json --------------------------------------------------------------

def test_parse_json_plain_and_wrapped():
    assert _parse_json('{"category": "iş"}') == {"category": "iş"}
    fenced = '```json\n{"category": "sağlamlıq", "tags": ["həkim"]}\n```'
    assert _parse_json(fenced) == {"category": "sağlamlıq", "tags": ["həkim"]}
    assert _parse_json('Cavab: {"a": 1} — hazırdır') == {"a": 1}


def test_parse_json_returns_empty_dict_on_garbage():
    assert _parse_json("JSON yoxdur") == {}
    assert _parse_json("{pozulmuş") == {}


# --- is_complex_query (Haiku → Sonnet escalation) ------------------------------

def test_simple_messages_stay_on_the_fast_model():
    assert not is_complex_query("sabah 9-da həkimə zəng etməyi xatırlat")
    assert not is_complex_query("")
    assert not is_complex_query(None)


def test_complex_messages_escalate():
    assert is_complex_query("Bu iki planı müqayisə et")
    assert is_complex_query("Niyə belə oldu? Nə etməliyəm?")
    assert is_complex_query("a" * 221)


# --- səsli cavab köməkçiləri ---------------------------------------------------

def test_clean_for_speech_strips_citations_markdown_and_emoji():
    text = "**Xatırlatma** ⏰ hazırdır [#12]\n\n- `həkim` 👨‍⚕️ saat 9-da"
    assert _clean_for_speech(text) == "Xatırlatma hazırdır - həkim saat 9-da"


def test_clean_for_speech_truncates_on_a_word_boundary():
    cleaned = _clean_for_speech("söz " * 1000)
    assert len(cleaned) <= MAX_TTS_CHARS + 1
    assert cleaned.endswith("söz…")


def test_fmt_uptime():
    assert _fmt_uptime(59) == "0dəq"
    assert _fmt_uptime(3661) == "1s 1dəq"
    assert _fmt_uptime(86400 + 3600 + 60) == "1g 1s 1dəq"
    assert _fmt_uptime(86400) == "1g 0dəq"


def test_voice_settings_defaults_and_overrides():
    assert _voice_settings(None) == (False, settings.azure_tts_voice)
    custom = {"voice_reply": True, "voice_name": "az-AZ-BanuNeural"}
    assert _voice_settings(custom) == (True, "az-AZ-BanuNeural")


# --- config -------------------------------------------------------------------

def test_allowed_ids_skips_blank_and_invalid_entries():
    s = Settings(_env_file=None, allowed_user_ids=" 123, 456,abc,,789 ")
    assert s.allowed_ids == [123, 456, 789]
    assert Settings(_env_file=None, allowed_user_ids="").allowed_ids == []
