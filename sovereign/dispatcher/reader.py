"""Reading stage that talks to Ollama directly (OpenAI-compatible, streaming).

The agent engine attaches at least one built-in tool to every agent, and Ollama rejects any request
carrying tool definitions for models whose template lacks tool syntax (qwen2.5vl among them). The
reader never needs tools - it transcribes and lists findings - so it calls the model straight."""

from __future__ import annotations

import base64
import json
import time

import httpx

from . import agents, config
from .trueforge import Emit, TrueForgeError, TurnResult


def read(ask: str, images: list[bytes], notes: list[str], emit: Emit | None = None) -> TurnResult:
    emit = emit or (lambda _e: None)
    content: list[dict] = [{"type": "text", "text": ask}]
    content += [{"type": "text", "text": n} for n in notes]
    content += [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}} for png in images]
    body = {
        "model": config.VISION_MODEL_ID,
        "messages": [{"role": "system", "content": agents.VISION_INSTRUCTIONS}, {"role": "user", "content": content}],
        "stream": True,
        "temperature": 0.1,
    }
    t0 = time.time()
    first: float | None = None
    parts: list[str] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(config.TURN_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S)) as http:
            with http.stream("POST", f"{config.OLLAMA_URL}/v1/chat/completions", json=body) as r:
                if r.status_code >= 400:
                    r.read()
                    raise TrueForgeError(f"The model server rejected the request ({r.status_code}): {r.text[:300]}")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        delta = json.loads(payload)["choices"][0].get("delta") or {}
                    except (ValueError, KeyError, IndexError):
                        continue
                    text = delta.get("content")
                    if text:
                        if first is None:
                            first = round(time.time() - t0, 2)
                        parts.append(text)
                        emit({"type": "delta", "text": text})
    except httpx.ConnectError as e:
        raise TrueForgeError(f"Model server unreachable ({config.OLLAMA_URL}). Nothing was lost - retry when the link is back.") from e
    except httpx.ReadTimeout as e:
        raise TrueForgeError(f"The model did not answer within {int(config.TURN_TIMEOUT_S)}s. It may be loading; retry in a few seconds.") from e
    total = round(time.time() - t0, 2)
    return TurnResult(text="".join(parts).strip(), timings={"first_token": first, "tools": 0, "total": total, "reasoning_chars": 0})
