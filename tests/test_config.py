from unittest.mock import patch

from codesight.config import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    AppConfig,
    ProviderConfig,
    load_config,
    save_config,
)


def test_default_config():
    cfg = AppConfig()
    assert cfg.default_provider == "openai"
    assert cfg.output_format == "markdown"
    assert isinstance(cfg.providers, dict)


def test_round_trip_serialization():
    cfg = AppConfig(
        default_provider="anthropic",
        providers={
            "anthropic": ProviderConfig(
                provider="anthropic",
                api_key="test-key",
                model=DEFAULT_ANTHROPIC_MODEL,
            )
        },
    )
    data = cfg.to_dict()
    restored = AppConfig.from_dict(data)
    assert restored.default_provider == "anthropic"
    assert restored.providers["anthropic"].api_key == "test-key"


def test_save_and_load(tmp_path):
    config_file = tmp_path / "config.json"
    config_dir = tmp_path

    cfg = AppConfig(default_provider="google")

    with patch("codesight.config.CONFIG_DIR", config_dir), \
         patch("codesight.config.CONFIG_FILE", config_file):
        save_config(cfg)
        loaded = load_config()

    assert loaded.default_provider == "google"


def test_provider_config_defaults():
    pc = ProviderConfig(provider="openai")
    assert pc.model == DEFAULT_OPENAI_MODEL
    assert pc.max_tokens == 4096
    assert pc.temperature == 0.2
