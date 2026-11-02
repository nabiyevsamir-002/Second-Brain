"""Linux quraşdırıcısı: skript sintaksisi və .env köməkçiləri (sirlər korlanmasın)."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "scripts" / "linux" / "install.sh"
DEPLOY = ROOT / "scripts" / "linux" / "deploy-from-mac.sh"


def _function(script: Path, name: str) -> str:
    """Skriptdən bir bash funksiyasını mətn kimi çıxar (skript özü işə düşmədən)."""
    match = re.search(rf"^{name}\(\) \{{.*?^\}}$", script.read_text(), re.S | re.M)
    assert match, f"{name} tapılmadı"
    return match.group(0)


def _bash(code: str) -> str:
    return subprocess.run(["bash", "-c", code], check=True, capture_output=True, text=True).stdout


@pytest.mark.parametrize("script", [INSTALL, DEPLOY], ids=lambda p: p.name)
def test_scripts_parse(script):
    subprocess.run(["bash", "-n", str(script)], check=True)


@pytest.mark.parametrize("script", [INSTALL, DEPLOY], ids=lambda p: p.name)
@pytest.mark.parametrize(
    "line, expected",
    [
        ("KEY=value", "value"),
        ("KEY=value   # şərh", "value"),
        ("export KEY='a b'", "a b"),
        ('KEY="x#y"', "x#y"),
        ("KEY=", ""),
        ("OTHER=nope", ""),
        ("KEY=one\nKEY=two", "two"),
    ],
)
def test_env_value_reads_every_form(tmp_path, script, line, expected):
    env = tmp_path / ".env"
    env.write_text(line + "\n")
    code = f"{_function(script, 'env_value')}\nenv_value '{env}' KEY"
    assert _bash(code) == expected


def _set_env(tmp_path, content: str, key: str, value: str) -> str:
    env = tmp_path / ".env"
    env.write_text(content)
    code = f"ENV_FILE='{env}'\n{_function(INSTALL, 'set_env')}\nset_env '{key}' \"$VALUE\""
    subprocess.run(["bash", "-c", code], check=True, env={"VALUE": value, "PATH": "/usr/bin:/bin"})
    return env.read_text()


def test_set_env_never_merges_lines_on_a_file_without_trailing_newline(tmp_path):
    # JobRadar 2026-10-20: `>>` sətirləri birləşdirib açarı korlamışdı.
    assert _set_env(tmp_path, "SECRET=abc", "NEW", "1") == "SECRET=abc\nNEW=1\n"


def test_set_env_replaces_in_place_and_keeps_other_lines(tmp_path):
    out = _set_env(tmp_path, "# şərh\nA=1\nB=2   # qeyd\nC=3\n", "B", "yeni")
    assert out == "# şərh\nA=1\nB=yeni\nC=3\n"


def test_set_env_only_matches_the_exact_key(tmp_path):
    assert _set_env(tmp_path, "MY_KEY=1\nKEY_2=2\n", "KEY", "x") == "MY_KEY=1\nKEY_2=2\nKEY=x\n"


@pytest.mark.parametrize(
    "value, stored",
    [
        ("123456:AAF_x-y", "123456:AAF_x-y"),
        ("sk-ant-oat01-abc_DEF-1", "sk-ant-oat01-abc_DEF-1"),
        ("a$b#c d", "'a$b#c d'"),  # compose $ və # işarəsini yozmasın
        ("&/\\", "'&/\\'"),  # sed/awk xüsusi simvolları korlanmasın
    ],
)
def test_set_env_keeps_secrets_intact(tmp_path, value, stored):
    assert _set_env(tmp_path, "X=1\n", "TOKEN", value) == f"X=1\nTOKEN={stored}\n"


def test_set_env_keeps_the_file_private(tmp_path):
    _set_env(tmp_path, "A=1\n", "B", "2")
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600


def test_redact_hides_tokens_in_printed_logs():
    match = re.search(r"^redact\(\) \{ (.*) \}$", INSTALL.read_text(), re.M)
    assert match
    code = "printf '%s' 'The token `123456:AAFabcdefghijklmnopqrstuv` x sk-ant-oat01-abc_D-1' | " + match.group(1)
    out = _bash(code)
    assert "AAFabc" not in out and "oat01" not in out
    assert "<telegram-token>" in out and "<claude-token>" in out


@pytest.mark.parametrize("key, expected", [("", False), ("/k/gh_actions", True)])
def test_vps_uses_the_given_key_only_when_set(key, expected):
    code = (
        'SSH_OPTS=(-o ConnectTimeout=15); VPS=root@1.2.3.4; '
        f'VPS_KEY="{key}"; ssh() {{ printf "%s " "$@"; }}\n'
        f"{_function(DEPLOY, 'vps')}\nvps true"
    )
    out = _bash(code)
    assert out.endswith("root@1.2.3.4 true ") and "BatchMode=yes" in out
    assert ("-i /k/gh_actions" in out) is expected
    assert ("IdentitiesOnly=yes" in out) is expected
