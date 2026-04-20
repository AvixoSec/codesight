import httpx
import json
from collections.abc import AsyncIterator

from .config import AppConfig, get_provider_config


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
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {})
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

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = json.loads(line[6:])
                if chunk.get("type") == "content_block_delta":
                    text = chunk.get("delta", {}).get("text", "")
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
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{base_url}/api/chat",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                text = chunk.get("message", {}).get("content", "")
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
            messages, pconfig.api_key, pconfig.model,
            pconfig.max_tokens, pconfig.temperature,
        ):
            yield chunk
    elif name == "anthropic":
        async for chunk in stream_anthropic(
            messages, pconfig.api_key, pconfig.model,
            pconfig.max_tokens, pconfig.temperature,
        ):
            yield chunk
    elif name == "ollama":
        async for chunk in stream_ollama(
            messages, pconfig.model, pconfig.base_url,
        ):
            yield chunk
    else:
        raise ValueError(f"Streaming not supported for provider: {name}")
