from urllib.parse import urlsplit

import httpx

from ..config import DEFAULT_ANTHROPIC_MODEL, ProviderConfig
from .base import BaseLLMProvider, LLMResponse, Message


def is_azure_url(url: str) -> bool:
    return ".services.ai.azure.com" in url or ".openai.azure.com" in url


_is_azure_url = is_azure_url


def normalize_azure_base_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if not cleaned:
        return cleaned
    if not cleaned.startswith(("http://", "https://")):
        return cleaned
    parsed = urlsplit(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return cleaned
    return f"{parsed.scheme}://{parsed.netloc}"


class AnthropicProvider(BaseLLMProvider):
    API_BASE = "https://api.anthropic.com/v1"

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._model = config.model or DEFAULT_ANTHROPIC_MODEL

        raw_base = (config.base_url or "").rstrip("/")
        custom_base = normalize_azure_base_url(raw_base) if is_azure_url(raw_base) else raw_base

        if custom_base and is_azure_url(custom_base):
            if not config.api_key:
                raise ValueError(
                    "Azure AI (Anthropic) requires an API key. "
                    "Set it via 'codesight config' or the provider config."
                )
            base = custom_base if custom_base.endswith("/anthropic") else f"{custom_base}/anthropic"
            self._base_url = f"{base}/v1"
            self._is_azure = True
            self._headers: dict[str, str] = {
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        else:
            if not config.api_key:
                raise ValueError(
                    "Missing Anthropic API key. Set ANTHROPIC_API_KEY or run: codesight config"
                )
            self._base_url = self.API_BASE
            self._is_azure = False
            self._headers = {
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }

        self._client: httpx.AsyncClient | None = None

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=None)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _error_message(resp: httpx.Response) -> str:
        try:
            data = resp.json()
            return data.get("error", {}).get("message") or resp.text
        except Exception:
            return resp.text

    async def _post_messages(self, payload: dict) -> dict:
        client = self._get_client()
        resp = await client.post(
            self._url("/messages"),
            headers=self._headers,
            json=payload,
            timeout=120,
        )

        if resp.status_code >= 400:
            message = self._error_message(resp)
            if (
                resp.status_code == 400
                and "temperature" in message.lower()
                and "deprecated" in message.lower()
                and "temperature" in payload
            ):
                retry_payload = dict(payload)
                retry_payload.pop("temperature", None)
                retry = await client.post(
                    self._url("/messages"),
                    headers=self._headers,
                    json=retry_payload,
                    timeout=120,
                )
                if retry.status_code < 400:
                    return retry.json()
                raise RuntimeError(
                    f"Anthropic API error ({retry.status_code}): {self._error_message(retry)}"
                )

            raise RuntimeError(f"Anthropic API error ({resp.status_code}): {message}")

        return resp.json()

    @property
    def name(self) -> str:
        return "Azure AI (Anthropic)" if self._is_azure else "Anthropic"

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

        data = await self._post_messages(payload)

        content_blocks = data.get("content") or []
        content = "".join(
            block.get("text", "")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
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
            client = self._get_client()
            if self._is_azure:
                resp = await client.post(
                    self._url("/messages"),
                    headers=self._headers,
                    json={
                        "model": self._model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=15,
                )
                return resp.status_code == 200
            resp = await client.get(
                self._url("/models"),
                headers=self._headers,
                timeout=15,
            )
            return resp.status_code == 200
        except Exception:
            return False
