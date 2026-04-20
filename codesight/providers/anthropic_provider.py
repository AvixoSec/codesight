import httpx

from ..config import ProviderConfig
from .base import BaseLLMProvider, LLMResponse, Message


class AnthropicProvider(BaseLLMProvider):

    API_BASE = "https://api.anthropic.com/v1"

    def __init__(self, config: ProviderConfig) -> None:
        if not config.api_key:
            raise ValueError("Missing Anthropic API key. Set ANTHROPIC_API_KEY or run: codesight config")
        self._config = config
        self._model = config.model or "claude-opus-4-6-20251101"
        self._headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    @property
    def name(self) -> str:
        return "Anthropic"

    async def complete(
        self,
        messages: list[Message],
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        system_text = ""
        conversation = []
        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
            else:
                conversation.append({"role": m.role, "content": m.content})

        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.API_BASE}/messages",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["content"][0]["text"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self._model),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            },
            provider=self.name,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.API_BASE}/models",
                    headers={
                        "x-api-key": self._config.api_key or "",
                        "anthropic-version": "2023-06-01",
                    },
                )
                return resp.status_code == 200
        except Exception:
            return False
