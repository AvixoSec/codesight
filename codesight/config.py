import contextlib
import json
import os
import stat
import sys
import warnings
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".codesight"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-6-20251101"
DEFAULT_GOOGLE_MODEL = "gemini-3.1-pro"
DEFAULT_OLLAMA_MODEL = "llama3"

KEYRING_SERVICE = "codesight"


def _keyring():
    try:
        import keyring as _kr
        _kr.get_keyring()
        return _kr
    except Exception:
        return None


def _secret_ref(provider_label: str) -> str:
    return f"apikey:{provider_label}"


def _store_secret(provider_label: str, api_key: str | None) -> bool:
    kr = _keyring()
    if kr is None or api_key is None:
        return False
    try:
        kr.set_password(KEYRING_SERVICE, _secret_ref(provider_label), api_key)
        return True
    except Exception:
        return False


def _fetch_secret(provider_label: str) -> str | None:
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(KEYRING_SERVICE, _secret_ref(provider_label))
    except Exception:
        return None


@dataclass
class ProviderConfig:
    provider: str
    api_key: str | None = None
    model: str = DEFAULT_OPENAI_MODEL
    project_id: str | None = None
    region: str | None = None
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderConfig":
        allowed = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in allowed}
        return cls(**filtered)


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
        allowed = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in allowed}
        providers = {}
        for name, pconf in filtered.get("providers", {}).items():
            if isinstance(pconf, dict):
                providers[name] = ProviderConfig.from_dict(pconf)
        filtered["providers"] = providers
        return cls(**filtered)


def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        with contextlib.suppress(OSError):
            os.chmod(path, stat.S_IRWXU)


def _atomic_write_secret(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if sys.platform != "win32":
        fd = os.open(tmp, flags, stat.S_IRUSR | stat.S_IWUSR)
    else:
        fd = os.open(tmp, flags)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload)
    if sys.platform != "win32":
        with contextlib.suppress(OSError):
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)


def load_config() -> AppConfig:
    if not CONFIG_FILE.exists():
        return AppConfig()
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Config file is unreadable or malformed: {exc}") from exc

    cfg = AppConfig.from_dict(raw)
    _hydrate_secrets(cfg)
    return cfg


def _hydrate_secrets(cfg: AppConfig) -> None:
    for label, pconf in cfg.providers.items():
        if pconf.api_key:
            continue
        secret = _fetch_secret(label)
        if secret:
            pconf.api_key = secret


def save_config(config: AppConfig) -> None:
    _secure_dir(CONFIG_DIR)

    keyring_available = _keyring() is not None
    dump = config.to_dict()

    for label, pconf in config.providers.items():
        pd = dump["providers"].get(label, {})
        if pconf.api_key and keyring_available and _store_secret(label, pconf.api_key):
            pd["api_key"] = None
        dump["providers"][label] = pd

    if not keyring_available and any(p.api_key for p in config.providers.values()):
        warnings.warn(
            "python-keyring is not installed or unavailable; API keys will be "
            "saved to ~/.codesight/config.json with owner-only permissions. "
            "Install with: pip install keyring",
            stacklevel=2,
        )

    payload = json.dumps(dump, indent=2)
    _atomic_write_secret(CONFIG_FILE, payload)


def get_provider_config(config: AppConfig, provider_name: str | None = None) -> ProviderConfig:
    name = provider_name or config.default_provider
    if name in config.providers:
        return config.providers[name]

    if name == "openai":
        return ProviderConfig(
            provider="openai",
            api_key=os.environ.get("OPENAI_API_KEY"),
            model=os.environ.get("CODESIGHT_MODEL", DEFAULT_OPENAI_MODEL),
        )
    elif name == "anthropic":
        return ProviderConfig(
            provider="anthropic",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            model=os.environ.get("CODESIGHT_MODEL", DEFAULT_ANTHROPIC_MODEL),
        )
    elif name == "google":
        return ProviderConfig(
            provider="google",
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            region=os.environ.get("GOOGLE_CLOUD_REGION", "us-central1"),
            model=os.environ.get("CODESIGHT_MODEL", DEFAULT_GOOGLE_MODEL),
        )
    elif name == "ollama":
        return ProviderConfig(
            provider="ollama",
            base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            model=os.environ.get("CODESIGHT_MODEL", DEFAULT_OLLAMA_MODEL),
        )
    else:
        raise ValueError(
            f"Unknown provider: '{name}'. Run 'codesight config' to set it up."
        )
