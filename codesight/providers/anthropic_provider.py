import httpx

from .base import BaseLLMProvider, LLMResponse


class AnthropicProvider(BaseLLMProvider):

    API_BASE = "https://api.anthropic.com/v1"

    def __init__(self, config):
        if not config.api_key:
            raise ValueError("Missing ANTHROPIC_API_KEY")
        self._config = config
        self._model = config.model or "claude-opus-4-6-20251101"
        self._headers = {"x-api-key": config.api_key, "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"}

    @property
    def name(self):
        return "Anthropic"

    async def complete(self, messages, max_tokens=4096, temperature=0.2):
        system = ""
        conv = []
        for m in messages:
            if m.role == "system":
                system += m.content + "\n"
            else:
                conv.append({"role": m.role, "content": m.content})

        payload = {"model": self._model, "max_tokens": max_tokens,
                   "temperature": temperature, "messages": conv}
        if system.strip():
            payload["system"] = system.strip()

        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(f"{self.API_BASE}/messages", headers=self._headers, json=payload)
            r.raise_for_status()
            d = r.json()

        usage = d.get("usage", {})
        return LLMResponse(content=d["content"][0]["text"], model=d.get("model", self._model),
                          usage={"prompt_tokens": usage.get("input_tokens", 0),
                                 "completion_tokens": usage.get("output_tokens", 0)},
                          provider=self.name)

    async def health_check(self):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{self.API_BASE}/models",
                               headers={"x-api-key": self._config.api_key or "",
                                       "anthropic-version": "2023-06-01"})
                return r.status_code == 200
        except Exception:
            return False
