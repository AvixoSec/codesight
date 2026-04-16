import httpx

from .base import BaseLLMProvider, LLMResponse


class GoogleVertexProvider(BaseLLMProvider):

    def __init__(self, config):
        self._config = config
        self._project = config.project_id
        self._region = config.region or "us-central1"
        self._model = config.model or "gemini-3.1-pro"

        if not self._project:
            raise ValueError("Missing GOOGLE_CLOUD_PROJECT")

        self._base_url = (f"https://{self._region}-aiplatform.googleapis.com/v1"
                         f"/projects/{self._project}/locations/{self._region}"
                         f"/publishers/google/models/{self._model}")

    @property
    def name(self):
        return "Google Vertex AI"

    def _get_token(self):
        try:
            import google.auth
            import google.auth.transport.requests
            creds, _ = google.auth.default()
            creds.refresh(google.auth.transport.requests.Request())
            return str(creds.token)
        except ImportError as e:
            raise ImportError("pip install google-auth") from e

    async def complete(self, messages, max_tokens=4096, temperature=0.2):
        tok = self._get_token()
        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

        sys_inst = None
        contents = []
        for m in messages:
            if m.role == "system":
                sys_inst = {"parts": [{"text": m.content}]}
            else:
                role = "user" if m.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.content}]})

        payload = {"contents": contents,
                   "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}
        if sys_inst:
            payload["systemInstruction"] = sys_inst

        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(f"{self._base_url}:generateContent", headers=headers, json=payload)
            r.raise_for_status()
            d = r.json()

        usage = d.get("usageMetadata", {})
        return LLMResponse(content=d["candidates"][0]["content"]["parts"][0]["text"],
                          model=self._model,
                          usage={"prompt_tokens": usage.get("promptTokenCount", 0),
                                 "completion_tokens": usage.get("candidatesTokenCount", 0)},
                          provider=self.name)

    async def health_check(self):
        try:
            tok = self._get_token()
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(self._base_url, headers={"Authorization": f"Bearer {tok}"})
                return r.status_code == 200
        except Exception:
            return False
