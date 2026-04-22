import httpx

from ..config import ProviderConfig
from .base import BaseLLMProvider, LLMResponse, Message

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
    """OpenAI-compatible provider."""

    def __init__(self, config: ProviderConfig) -> None:
        if not config.base_url:
            raise ValueError(
                "Custom provider requires a base_url. Run: codesight config"
            )
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        self._api_version: str | None = None

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

    async def complete(
        self,
        messages: list[Message],
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        payload = {
            "model": self._config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self._url(self._chat_path),
                headers=self._headers,
                json=payload,
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
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    self._url(self._models_path),
                    headers=self._headers,
                )
                return resp.status_code in (200, 404)
        except Exception:
            return False
