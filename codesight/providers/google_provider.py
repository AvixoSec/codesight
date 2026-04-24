import asyncio
import re
import time

import httpx

from ..config import DEFAULT_GOOGLE_MODEL, ProviderConfig
from .base import BaseLLMProvider, LLMResponse, Message

_REGION_RE = re.compile(r"^[a-z]+-[a-z]+[0-9]+$")
_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{5,29}$")
_MODEL_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

# Google tokens are valid ~3600s; cache short to stay ahead of clock skew.
_TOKEN_CACHE_SECS = 1800


class GoogleVertexProvider(BaseLLMProvider):

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._project = config.project_id
        self._region = config.region or "us-central1"
        self._model = config.model or DEFAULT_GOOGLE_MODEL

        if not self._project:
            raise ValueError(
                "Missing Google Cloud project ID. "
                "Set GOOGLE_CLOUD_PROJECT or run: codesight config"
            )
        if not _PROJECT_RE.match(self._project):
            raise ValueError(f"Invalid Google Cloud project ID: {self._project!r}")
        if not _REGION_RE.match(self._region):
            raise ValueError(f"Invalid Google Cloud region: {self._region!r}")
        if not _MODEL_RE.match(self._model):
            raise ValueError(f"Invalid Google model name: {self._model!r}")

        self._base_url = (
            f"https://{self._region}-aiplatform.googleapis.com/v1"
            f"/projects/{self._project}/locations/{self._region}"
            f"/publishers/google/models/{self._model}"
        )
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._token_fetched_at: float = 0.0

    @property
    def name(self) -> str:
        return "Google Vertex AI"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=None)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _fetch_access_token_sync(self) -> str:
        try:
            import google.auth
            import google.auth.transport.requests
        except ImportError as err:
            raise ImportError(
                "google-auth is required for Vertex AI. "
                "Install it: pip install google-auth"
            ) from err

        credentials, _ = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())
        return str(credentials.token)

    async def _get_access_token(self) -> str:
        # google.auth.refresh() does blocking network I/O; offload to a thread
        # and cache the result so parallel requests don't each refresh.
        now = time.monotonic()
        if self._token and (now - self._token_fetched_at) < _TOKEN_CACHE_SECS:
            return self._token
        token = await asyncio.to_thread(self._fetch_access_token_sync)
        self._token = token
        self._token_fetched_at = now
        return token

    async def complete(
        self,
        messages: list[Message],
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        system_instruction = None
        contents = []
        for m in messages:
            if m.role == "system":
                system_instruction = {"parts": [{"text": m.content}]}
            else:
                role = "user" if m.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.content}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        client = self._get_client()
        resp = await client.post(
            f"{self._base_url}:generateContent",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        candidate = data["candidates"][0]["content"]["parts"][0]["text"]
        usage_meta = data.get("usageMetadata", {})

        return LLMResponse(
            content=candidate,
            model=self._model,
            usage={
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
            },
            provider=self.name,
        )

    async def health_check(self) -> bool:
        try:
            token = await self._get_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            client = self._get_client()
            resp = await client.get(
                f"{self._base_url}",
                headers=headers,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False
