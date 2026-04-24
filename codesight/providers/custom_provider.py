import ipaddress
import os
import socket
from urllib.parse import urlparse

import httpx

from ..config import ProviderConfig
from .base import BaseLLMProvider, LLMResponse, Message

_ALLOWED_SCHEMES = {"http", "https"}
_PRIVATE_ENV = "CODESIGHT_ALLOW_PRIVATE_URLS"
_LOCALHOST_NAMES = {"localhost", "ip6-localhost", "ip6-loopback", "localhost.localdomain"}


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _host_of(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"base_url must use http or https, got: {parsed.scheme or '(none)'}"
        )
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError(f"base_url has no hostname: {base_url}")
    return host


def _validate_base_url(base_url: str) -> None:
    # Fails closed on DNS error. Previous version returned silently, which
    # effectively disabled the guard when the resolver misbehaved.
    host = _host_of(base_url)

    if os.environ.get(_PRIVATE_ENV) == "1":
        return

    if host.lower() in _LOCALHOST_NAMES:
        raise ValueError(
            f"base_url points at localhost ({host}). "
            f"Set {_PRIVATE_ENV}=1 to allow it."
        )

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not _is_public_ip(literal):
        raise ValueError(
            f"base_url points at a non-public address ({host}). "
            f"Set {_PRIVATE_ENV}=1 to allow it."
        )
    if literal is not None:
        return

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise ValueError(
            f"DNS resolution failed for base_url host {host!r}: {exc}. "
            "Refusing to send request to unverifiable target. "
            f"Set {_PRIVATE_ENV}=1 only if you trust this environment."
        ) from exc
    if not infos:
        raise ValueError(
            f"No addresses returned for host {host!r}; refusing to proceed."
        )
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise ValueError(
                f"Unparseable address {addr!r} returned for {host}; refusing."
            ) from None
        if not _is_public_ip(ip):
            raise ValueError(
                f"base_url host {host} resolves to non-public address {addr}. "
                f"Set {_PRIVATE_ENV}=1 to allow it."
            )

KNOWN_PRESETS: dict[str, tuple[str, str]] = {
    "OpenRouter": (
        "https://openrouter.ai/api/v1",
        "meta-llama/llama-4-maverick",
    ),
    "Groq": (
        "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile",
    ),
    "Together AI": (
        "https://api.together.xyz/v1",
        "meta-llama/Llama-3-70b-chat-hf",
    ),
    "Mistral": (
        "https://api.mistral.ai/v1",
        "mistral-large-latest",
    ),
    "xAI (Grok)": (
        "https://api.x.ai/v1",
        "grok-3",
    ),
    "Fireworks AI": (
        "https://api.fireworks.ai/inference/v1",
        "accounts/fireworks/models/llama-v3p1-70b-instruct",
    ),
    "DeepSeek": (
        "https://api.deepseek.com",
        "deepseek-chat",
    ),
    "Perplexity": (
        "https://api.perplexity.ai",
        "llama-3.1-sonar-large-128k-online",
    ),
    "Cerebras": (
        "https://api.cerebras.ai/v1",
        "llama3.1-70b",
    ),
    "Cohere": (
        "https://api.cohere.ai/compatibility/v1",
        "command-r-plus",
    ),
    "Custom URL": ("", ""),
}


class CustomProvider(BaseLLMProvider):

    def __init__(self, config: ProviderConfig) -> None:
        if not config.base_url:
            raise ValueError(
                "Custom provider requires a base_url. Run: codesight config"
            )
        _validate_base_url(config.base_url)
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._host = _host_of(self._base_url)
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        self._api_version: str | None = None
        self._client: httpx.AsyncClient | None = None

        if ".services.ai.azure.com" in self._base_url or ".openai.azure.com" in self._base_url:
            self._chat_path = "/models/chat/completions"
            self._models_path = "/models"
            self._api_version = "2024-05-01-preview"
            if config.api_key:
                self._headers["api-key"] = config.api_key
        else:
            self._chat_path = "/chat/completions"
            self._models_path = "/models"
            if config.api_key:
                self._headers["Authorization"] = f"Bearer {config.api_key}"

        if "openrouter.ai" in self._base_url:
            self._headers["X-Title"] = "CodeSight"

    @property
    def name(self) -> str:
        return self._config.provider or "Custom"

    def _url(self, path: str) -> str:
        url = f"{self._base_url}{path}"
        if self._api_version:
            url += f"?api-version={self._api_version}"
        return url

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=None)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _revalidate_host(self) -> None:
        # Re-check before each request to catch DNS rebinding between init
        # and send (e.g. a TTL-0 record flipping to 169.254.169.254).
        _validate_base_url(self._base_url)

    async def complete(
        self,
        messages: list[Message],
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        self._revalidate_host()
        payload = {
            "model": self._config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        client = self._get_client()
        resp = await client.post(
            self._url(self._chat_path),
            headers=self._headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return LLMResponse(
            content=choice["content"],
            model=data.get("model", self._config.model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            provider=self.name,
        )

    async def health_check(self) -> bool:
        try:
            self._revalidate_host()
            client = self._get_client()
            resp = await client.get(
                self._url(self._models_path),
                headers=self._headers,
                timeout=10,
            )
            return resp.status_code in (200, 404)
        except Exception:
            return False
