import json
from pathlib import Path

from hermes_jarvis.app import cli_config_file, config_file, legacy_config_file, read_cli_config


def test_config_file_honors_override(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "custom.env"
    monkeypatch.setenv("HERMES_JARVIS_CONFIG_FILE", str(override))
    assert config_file() == override
    assert legacy_config_file() == override


def test_config_file_defaults_to_orbitylabs_folder(monkeypatch) -> None:
    monkeypatch.delenv("HERMES_JARVIS_CONFIG_FILE", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = config_file()
    assert "OrbityLabs" in path.parts
    legacy = legacy_config_file()
    assert "Hermes Jarvis" in legacy.parts


def test_read_cli_config_defaults_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ORBITYLABS_CONFIG_FILE", str(tmp_path / "does-not-exist.json"))
    result = read_cli_config()
    assert result == {"autonomy": "manual", "models": [], "default_model": "", "agents": {}}


def test_read_cli_config_reflects_real_cli_state(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "autonomy": "auto-safe",
        "models": ["ollama:llama3.2"],
        "default_model": "ollama:llama3.2",
        "agents": {"ceo": "openrouter:openai/gpt-4.1"},
    }))
    monkeypatch.setenv("ORBITYLABS_CONFIG_FILE", str(config_path))
    result = read_cli_config()
    assert result["autonomy"] == "auto-safe"
    assert result["default_model"] == "ollama:llama3.2"
    assert result["agents"] == {"ceo": "openrouter:openai/gpt-4.1"}
    assert "HERMES_API_KEY" not in json.dumps(result)


def test_read_cli_config_never_exposes_unexpected_keys(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"autonomy": "manual", "secret_field": "should-not-appear"}))
    monkeypatch.setenv("ORBITYLABS_CONFIG_FILE", str(config_path))
    result = read_cli_config()
    assert "secret_field" not in result


def test_cli_config_file_honors_override(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "config.json"
    monkeypatch.setenv("ORBITYLABS_CONFIG_FILE", str(override))
    assert cli_config_file() == override
