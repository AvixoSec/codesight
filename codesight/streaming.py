import asyncio
import json
import re
from collections.abc import AsyncIterator

import httpx

from .config import DEFAULT_GOOGLE_MODEL, AppConfig, get_provider_config

_GOOGLE_REGION_RE = re.compile(r"^[a-z]+-[a-z]+[0-9]+$")
_GOOGLE_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{5,29}$")
_GOOGLE_MODEL_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


async def _iter_sse_data(resp: httpx.Response) -> AsyncIterator[str]:
    async for line in resp.aiter_lines():
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        yield data


async def stream_openai(
    messages: list[dict],
    api_key: str,
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    async with (
        httpx.AsyncClient(timeout=120) as client,
        client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
        ) as resp,
    ):
        resp.raise_for_status()
        async for data in _iter_sse_data(resp):
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content", "")
            if text:
                yield text


async def stream_anthropic(
    messages: list[dict],
    api_key: str,
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    system_msg = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system_msg = m["content"]
        else:
            user_messages.append(m)

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "messages": user_messages,
    }
    if system_msg:
        payload["system"] = system_msg

    async with (
        httpx.AsyncClient(timeout=120) as client,
        client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        ) as resp,
    ):
        resp.raise_for_status()
        async for data in _iter_sse_data(resp):
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if chunk.get("type") == "content_block_delta":
                text = (chunk.get("delta") or {}).get("text", "")
                if text:
                    yield text


async def stream_google(
    messages: list[dict],
    project_id: str,
    region: str,
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    if not project_id or not _GOOGLE_PROJECT_RE.match(project_id):
        raise ValueError(f"Invalid Google Cloud project ID: {project_id!r}")
    if not _GOOGLE_REGION_RE.match(region):
        raise ValueError(f"Invalid Google Cloud region: {region!r}")
    model = model or DEFAULT_GOOGLE_MODEL
    if not _GOOGLE_MODEL_RE.match(model):
        raise ValueError(f"Invalid Google model name: {model!r}")

    try:
        import google.auth
        import google.auth.transport.requests
    except ImportError as err:
        raise ImportError(
            "google-auth is required for Vertex AI streaming. Install: pip install google-auth"
        ) from err

    def _token() -> str:
        credentials, _ = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())
        return str(credentials.token)

    token = await asyncio.to_thread(_token)

    system_instruction = None
    contents: list[dict] = []
    for m in messages:
        if m["role"] == "system":
            system_instruction = {"parts": [{"text": m["content"]}]}
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

    payload: dict = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system_instruction:
        payload["systemInstruction"] = system_instruction

    base_url = (
        f"https://{region}-aiplatform.googleapis.com/v1"
        f"/projects/{project_id}/locations/{region}"
        f"/publishers/google/models/{model}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with (
        httpx.AsyncClient(timeout=120) as client,
        client.stream(
            "POST",
            f"{base_url}:streamGenerateContent?alt=sse",
            headers=headers,
            json=payload,
        ) as resp,
    ):
        resp.raise_for_status()
        async for data in _iter_sse_data(resp):
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            candidates = chunk.get("candidates") or []
            if not candidates:
                continue
            parts = (candidates[0].get("content") or {}).get("parts") or []
            for part in parts:
                text = part.get("text", "") if isinstance(part, dict) else ""
                if text:
                    yield text


async def stream_ollama(
    messages: list[dict],
    model: str,
    base_url: str = "http://localhost:11434",
) -> AsyncIterator[str]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    async with (
        httpx.AsyncClient(timeout=300) as client,
        client.stream(
            "POST",
            f"{base_url}/api/chat",
            json=payload,
        ) as resp,
    ):
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = (chunk.get("message") or {}).get("content", "")
            if text:
                yield text


async def stream_analysis(
    config: AppConfig,
    messages: list[dict],
    provider_name: str | None = None,
) -> AsyncIterator[str]:
    pconfig = get_provider_config(config, provider_name)
    name = pconfig.provider

    if name == "openai":
        async for chunk in stream_openai(
            messages,
            pconfig.api_key,
            pconfig.model,
            pconfig.max_tokens,
            pconfig.temperature,
        ):
            yield chunk
    elif name == "anthropic":
        async for chunk in stream_anthropic(
            messages,
            pconfig.api_key,
            pconfig.model,
            pconfig.max_tokens,
            pconfig.temperature,
        ):
            yield chunk
    elif name == "ollama":
        async for chunk in stream_ollama(
            messages,
            pconfig.model,
            pconfig.base_url,
        ):
            yield chunk
    elif name == "google":
        async for chunk in stream_google(
            messages,
            pconfig.project_id,
            pconfig.region or "us-central1",
            pconfig.model,
            pconfig.max_tokens,
            pconfig.temperature,
        ):
            yield chunk
    else:
        raise ValueError(f"Streaming not supported for provider: {name}")
