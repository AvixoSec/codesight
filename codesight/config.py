import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".codesight"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class ProviderConfig:
    provider: str
    api_key: str | None = None
    model: str = "gpt-5.4"
    project_id: str | None = None
    region: str | None = None
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.2


@dataclass
class AppConfig:
    default_provider: str = "openai"
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    output_format: str = "markdown"
    language: str = "en"
    max_file_size_kb: int = 500
    ignore_patterns: list = field(default_factory=lambda: [
        "*.pyc", "__pycache__", ".git", "node_modules", ".env"
    ])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        providers = {}
        for name, pconf in data.get("providers", {}).items():
            providers[name] = ProviderConfig(**pconf)
        data["providers"] = providers
        return cls(**data)


def load_config() -> AppConfig:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return AppConfig.from_dict(json.load(f))
    return AppConfig()


def save_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)


def get_provider_config(config: AppConfig, provider_name: str | None = None) -> ProviderConfig:
    name = provider_name or config.default_provider
    if name in config.providers:
        return config.providers[name]

    if name == "openai":
        return ProviderConfig(
            provider="openai",
            api_key=os.environ.get("OPENAI_API_KEY"),
            model=os.environ.get("CODESIGHT_MODEL", "gpt-5.4"),
        )
    elif name == "anthropic":
        return ProviderConfig(
            provider="anthropic",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            model=os.environ.get("CODESIGHT_MODEL", "claude-opus-4-6-20251101"),
        )
    elif name == "google":
        return ProviderConfig(
            provider="google",
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            region=os.environ.get("GOOGLE_CLOUD_REGION", "us-central1"),
            model=os.environ.get("CODESIGHT_MODEL", "gemini-3.1-pro"),
        )
    elif name == "ollama":
        return ProviderConfig(
            provider="ollama",
            base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            model=os.environ.get("CODESIGHT_MODEL", "llama3"),
        )
    else:
        raise ValueError(f"Unknown provider: {name}")
