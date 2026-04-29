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
PROJECT_CONFIG_NAMES = (".codesight.toml", ".codesight.json")
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-6-20251101"
DEFAULT_GOOGLE_MODEL = "gemini-3.1-pro"
DEFAULT_OLLAMA_MODEL = "llama3"

KEYRING_SERVICE = "codesight"
ALLOW_PLAINTEXT_ENV = "CODESIGHT_ALLOW_PLAINTEXT_KEYS"


class KeyringUnavailableError(RuntimeError):
    """Raised when keyring is unavailable and plaintext fallback is not opted in."""


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
    ignore_patterns: list = field(
        default_factory=lambda: ["*.pyc", "__pycache__", ".git", "node_modules", ".env"]
    )
    # Opt-in to plaintext fallback when keyring is unavailable.
    # Env override: CODESIGHT_ALLOW_PLAINTEXT_KEYS=1
    allow_plaintext_keys: bool = False

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
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Config file is unreadable or malformed: {exc}") from exc
        cfg = AppConfig.from_dict(raw)
    else:
        cfg = AppConfig()

    _hydrate_secrets(cfg)

    project = _load_project_config()
    if project is not None:
        _apply_project_config(cfg, project)
    return cfg


def _find_project_config_file(start: Path | None = None) -> Path | None:
    try:
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        return None
    if not home:
        return None
    cur = (start or Path.cwd()).resolve()
    try:
        cur.relative_to(home)
    except ValueError:
        return None
    for path in [cur, *cur.parents]:
        try:
            path.relative_to(home)
        except ValueError:
            break
        for name in PROJECT_CONFIG_NAMES:
            candidate = path / name
            if candidate.is_file():
                return candidate
    return None


def _load_project_config() -> dict[str, Any] | None:
    path = _find_project_config_file()
    if path is None:
        return None
    try:
        data = path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.warn(f"Failed to read {path}: {exc}", stacklevel=2)
        return None

    if path.suffix == ".toml":
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # Python 3.10 fallback
            except ImportError:
                warnings.warn(
                    f"Found {path.name} but tomllib is unavailable; "
                    "upgrade to Python 3.11+ or `pip install tomli`.",
                    stacklevel=2,
                )
                return None
        try:
            return tomllib.loads(data)
        except Exception as exc:
            warnings.warn(f"Malformed TOML in {path}: {exc}", stacklevel=2)
            return None

    if path.suffix == ".json":
        try:
            return json.loads(data)
        except json.JSONDecodeError as exc:
            warnings.warn(f"Malformed JSON in {path}: {exc}", stacklevel=2)
            return None

    return None


# Fields that a project .codesight.toml/json is allowed to override on AppConfig.
# We deliberately exclude allow_plaintext_keys so a hostile repo cannot flip
# the plaintext-secret gate on.
_PROJECT_ALLOWED_APP_FIELDS = {
    "output_format",
    "language",
    "max_file_size_kb",
    "ignore_patterns",
}


_PROJECT_PROVIDER_BLOCKED = {"api_key", "base_url"}


def _apply_project_config(cfg: AppConfig, data: dict[str, Any]) -> None:
    for key in _PROJECT_ALLOWED_APP_FIELDS:
        if key in data:
            setattr(cfg, key, data[key])

    # Project config can pin model / project_id / region per provider but
    # NOT api_key (would expose secrets in a committed file) and NOT
    # base_url (a hostile repo could redirect requests to attacker.tld and
    # exfiltrate the user's keyring-stored API key).
    project_providers = data.get("providers")
    if isinstance(project_providers, dict):
        for label, pdata in project_providers.items():
            if not isinstance(pdata, dict):
                continue
            pdata = {k: v for k, v in pdata.items() if k not in _PROJECT_PROVIDER_BLOCKED}
            existing = cfg.providers.get(label)
            if existing is None:
                cfg.providers[label] = ProviderConfig.from_dict(
                    {"provider": pdata.get("provider", label), **pdata}
                )
            else:
                allowed_fields = {f.name for f in fields(ProviderConfig)}
                for k, v in pdata.items():
                    if k in allowed_fields:
                        setattr(existing, k, v)


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
    allow_plaintext = config.allow_plaintext_keys or os.environ.get(ALLOW_PLAINTEXT_ENV) == "1"
    dump = config.to_dict()
    has_secrets = any(p.api_key for p in config.providers.values())

    for label, pconf in config.providers.items():
        pd = dump["providers"].get(label, {})
        if pconf.api_key and keyring_available and _store_secret(label, pconf.api_key):
            pd["api_key"] = None
        dump["providers"][label] = pd

    residual_plaintext = any(
        (pd.get("api_key") is not None) for pd in dump.get("providers", {}).values()
    )

    if residual_plaintext and not allow_plaintext:
        raise KeyringUnavailableError(
            "Cannot persist API keys: keyring is unavailable and plaintext "
            "fallback is not enabled. To opt in, either set "
            "CODESIGHT_ALLOW_PLAINTEXT_KEYS=1 or AppConfig.allow_plaintext_keys=True. "
            "Recommended: install a working keyring backend (pip install keyring "
            "on most systems, or brew install keyring on macOS; "
            "secret-tool / gnome-keyring on Linux)."
        )

    if not keyring_available and has_secrets and allow_plaintext:
        warnings.warn(
            "python-keyring is unavailable; API keys are being saved to "
            "~/.codesight/config.json with owner-only permissions because "
            f"{ALLOW_PLAINTEXT_ENV}=1 (or allow_plaintext_keys=True). "
            "Install a keyring backend to stop writing plaintext secrets.",
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
        raise ValueError(f"Unknown provider: '{name}'. Run 'codesight config' to set it up.")
