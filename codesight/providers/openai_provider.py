import asyncio

import httpx

from ..config import ProviderConfig
from .base import BaseLLMProvider, LLMResponse, Message

_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3


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
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "OpenAI"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # timeout=None so short health probes don't cap long completions
            self._client = httpx.AsyncClient(timeout=None)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _post_with_retry(
        self, url: str, payload: dict, timeout: float,
    ) -> httpx.Response:
        client = self._get_client()
        last: httpx.Response | None = None
        for attempt in range(_MAX_RETRIES):
            resp = await client.post(
                url, headers=self._headers, json=payload, timeout=timeout,
            )
            last = resp
            if resp.status_code not in _RETRY_STATUS or attempt == _MAX_RETRIES - 1:
                return resp
            # Honour Retry-After header if present, else exponential backoff.
            retry_after = resp.headers.get("retry-after")
            delay = 2 ** attempt
            if retry_after and retry_after.isdigit():
                delay = min(int(retry_after), 60)
            await asyncio.sleep(delay)
        return last  # type: ignore[return-value]

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
        resp = await self._post_with_retry(
            f"{self.API_BASE}/chat/completions", payload, timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        # Refusals return content=None; coerce to "" so callers don't crash.
        choices = data.get("choices") or []
        msg = (choices[0].get("message") if choices else {}) or {}
        content = msg.get("content") or ""
        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=data.get("model", self._config.model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            provider=self.name,
        )

    async def health_check(self) -> bool:
        try:
            client = self._get_client()
            resp = await client.get(
                f"{self.API_BASE}/models",
                headers=self._headers,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False
