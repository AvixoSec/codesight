import httpx

from ..config import ProviderConfig
from .base import BaseLLMProvider, LLMResponse, Message


class OpenAIProvider(BaseLLMProvider):

    API_BASE = "https://api.openai.com/v1"

    def __init__(self, config):
        if not config.api_key:
            raise ValueError("Missing OPENAI_API_KEY")
        self._config = config
        self._headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}

    @property
    def name(self):
        return "OpenAI"

    async def complete(self, messages, max_tokens=4096, temperature=0.2):
        payload = {"model": self._config.model,
                   "messages": [{"role": m.role, "content": m.content} for m in messages],
                   "max_tokens": max_tokens, "temperature": temperature}
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(f"{self.API_BASE}/chat/completions", headers=self._headers, json=payload)
            r.raise_for_status()
            d = r.json()
        usage = d.get("usage", {})
        return LLMResponse(content=d["choices"][0]["message"]["content"], model=d["model"],
                          usage={"prompt_tokens": usage.get("prompt_tokens", 0),
                                 "completion_tokens": usage.get("completion_tokens", 0)},
                          provider=self.name)

    async def health_check(self):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{self.API_BASE}/models", headers=self._headers)
                return r.status_code == 200
        except Exception:
            return False
