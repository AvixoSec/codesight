import httpx

from ..config import ProviderConfig
from .base import BaseLLMProvider, LLMResponse, Message


class OpenAIProvider(BaseLLMProvider):

    API_BASE = "https://api.openai.com/v1"

    def __init__(self, config: ProviderConfig) -> None:
        if not config.api_key:
            raise ValueError("Missing OpenAI API key. Set OPENAI_API_KEY or run: codesight config")
        self._config = config
        self._headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

    @property
    def name(self) -> str:
        return "OpenAI"

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
                f"{self.API_BASE}/chat/completions",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return LLMResponse(
            content=choice["content"],
            model=data["model"],
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
                    f"{self.API_BASE}/models",
                    headers=self._headers,
                )
                return resp.status_code == 200
        except Exception:
            return False
