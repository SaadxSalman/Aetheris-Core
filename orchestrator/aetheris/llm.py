"""LLM client: OpenAI-compatible streaming + deterministic extractive fallback."""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from aetheris.config import settings
from aetheris.textutils import content_tokens, normalize_ws, sentences


def _endpoint() -> tuple[str, str, dict]:
    provider = settings.LLM_PROVIDER
    headers = {"Content-Type": "application/json"}
    if provider == "groq":
        return f"{settings.GROQ_BASE_URL.rstrip('/')}/chat/completions", settings.GROQ_API_KEY, headers
    if provider == "ollama":
        return f"{settings.OLLAMA_BASE_URL.rstrip('/')}/chat/completions", "ollama", headers
    # openai (or any openai-compatible gateway)
    return f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions", settings.OPENAI_API_KEY, headers


def llm_available() -> bool:
    if settings.LLM_PROVIDER == "none":
        return False
    if settings.LLM_PROVIDER == "ollama":
        return True
    if settings.LLM_PROVIDER == "groq":
        return bool(settings.GROQ_API_KEY)
    return bool(settings.OPENAI_API_KEY)


async def chat(messages: list[dict], temperature: float | None = None,
               max_tokens: int | None = None, json_mode: bool = False) -> str:
    """One-shot chat completion. Raises on failure (callers degrade gracefully)."""
    url, key, headers = _endpoint()
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers["Authorization"] = f"Bearer {key}"
    async with httpx.AsyncClient(timeout=float(settings.LLM_TIMEOUT_SECONDS)) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def stream_chat(messages: list[dict], temperature: float | None = None,
                      max_tokens: int | None = None) -> AsyncIterator[str]:
    """Streaming chat completion yielding text deltas."""
    url, key, headers = _endpoint()
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        "stream": True,
    }
    headers["Authorization"] = f"Bearer {key}"
    async with httpx.AsyncClient(timeout=float(settings.LLM_TIMEOUT_SECONDS)) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta


# --------------------------------------------------------------------------- #
# Extractive fallback generator (works with zero API keys)
# --------------------------------------------------------------------------- #
async def extractive_answer(query: str, chunks: list[dict], degraded: bool = False) -> AsyncIterator[str]:
    """Compose a coherent, fully-cited answer purely from retrieved context."""
    q_tokens = set(content_tokens(query))
    scored_sentences: list[tuple[float, int, str]] = []
    for idx, chunk in enumerate(chunks, start=1):
        text = chunk.get("text") or chunk.get("summary") or ""
        for sent in sentences(text):
            s_tokens = set(content_tokens(sent))
            if not s_tokens or len(sent) < 30:
                continue
            overlap = len(q_tokens & s_tokens) / max(len(q_tokens), 1)
            informativeness = min(len(s_tokens) / 18.0, 1.0)
            score = 0.65 * overlap + 0.35 * informativeness
            scored_sentences.append((score, idx, sent))
    scored_sentences.sort(key=lambda t: t[0], reverse=True)

    picked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for score, idx, sent in scored_sentences:
        key = " ".join(sorted(set(content_tokens(sent)))[:12])
        if key in seen:
            continue
        seen.add(key)
        picked.append((idx, sent))
        if len(picked) >= 5:
            break

    intro = f"Based on the retrieved knowledge mesh, here is what the evidence supports for “{normalize_ws(query)}”:"
    yield intro + "\n\n"
    if not picked:
        warn = ("⚠️ No internal context passed the confidence threshold"
                + (" and web fallback did not return usable results." if degraded
                   else " for this query."))
        yield warn
        return
    for i, (idx, sent) in enumerate(picked, start=1):
        yield f"{i}. {sent} [{idx}]\n"
    yield "\nAll statements above are grounded in the cited chunks (verifiable via citation attestations)."
