"""Thin HTTP client for the TrueForge API. Sessions are created with an inline agent spec; turns are
streamed as SSE so tool calls can be shown in the trace."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

import httpx

from . import config


class TrueForgeError(Exception):
    """Carries a one-sentence message safe to show the operator (Flow 5)."""


@dataclass
class TurnResult:
    text: str
    tool_calls: list[str] = field(default_factory=list)
    status: str = "done"
    error: str | None = None
    turn_id: str | None = None


def image_part(name: str, png: bytes) -> dict:
    return {"type": "file", "name": name, "data": "data:image/png;base64," + base64.b64encode(png).decode()}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


class TrueForgeClient:
    def __init__(self, base_url: str = config.TRUEFORGE_URL, token: str | None = config.TRUEFORGE_TOKEN):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(config.TURN_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S),
        )

    # --- health -------------------------------------------------------------------------------

    def healthy(self) -> bool:
        try:
            return self._http.get("/healthz", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    # --- sessions -----------------------------------------------------------------------------

    def create_session(self, spec: dict) -> str:
        try:
            r = self._http.post("/api/v1/sessions", json={"agent": {"spec": spec}})
        except httpx.ConnectError as e:
            raise TrueForgeError(f"TrueForge is not reachable at {config.TRUEFORGE_URL}. Is it running?") from e
        if r.status_code >= 400:
            raise TrueForgeError(f"TrueForge rejected the session ({r.status_code}): {_detail(r)}")
        return r.json()["data"]["id"]

    def run_turn(self, session_id: str, content: str | list[dict]) -> TurnResult:
        body = {"input": [{"type": "user.message", "content": content}], "stream": True}
        result = TurnResult(text="")
        try:
            with self._http.stream("POST", f"/api/v1/sessions/{session_id}/turns", json=body) as r:
                if r.status_code >= 400:
                    r.read()
                    raise TrueForgeError(f"TrueForge rejected the turn ({r.status_code}): {_detail(r)}")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    self._consume(json.loads(line[5:].strip()), result)
        except httpx.ConnectError as e:
            raise TrueForgeError(f"TrueForge is not reachable at {config.TRUEFORGE_URL}. Is it running?") from e
        except httpx.ReadTimeout as e:
            raise TrueForgeError(
                f"The model did not answer within {int(config.TURN_TIMEOUT_S)}s. "
                "Check that the model server (Laptop A) is reachable and the model is loaded."
            ) from e
        if result.status == "error":
            raise TrueForgeError(_friendly(result.error or "unknown error"))
        return result

    def _consume(self, event: dict, result: TurnResult) -> None:
        kind = event.get("type")
        if kind == "turn.created":
            result.turn_id = event.get("turn_id") or event.get("id")
        elif kind == "model.message" and event.get("thread_id", "main") == "main":
            for call in event.get("tool_calls") or []:
                name = (call.get("function") or {}).get("name") or call.get("name")
                if name:
                    result.tool_calls.append(name)
        elif kind == "turn.done":
            state = event.get("state") or {}
            result.status = state.get("status", "done")
            if result.status == "error":
                result.error = state.get("message")
                return
            output = state.get("output") or {}
            result.text = _content_text(output.get("content"))
            if not result.text and state.get("required_actions"):
                result.text = "(the agent paused waiting for an action - check approval settings)"


def _content_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content if isinstance(p, dict))


def _detail(r: httpx.Response) -> str:
    try:
        return r.json().get("error", {}).get("message") or r.text[:300]
    except ValueError:
        return r.text[:300]


def _friendly(message: str) -> str:
    m = message.lower()
    if "econnrefused" in m or "fetch failed" in m or "connect" in m:
        return f"Model server unreachable ({config.OLLAMA_URL}). Nothing was lost - retry when the link is back."
    if "timeout" in m or "timed out" in m:
        return "The model server timed out. It may be loading a model; retry in a few seconds."
    if "model" in m and ("not found" in m or "404" in m):
        return "The model alias is not registered on Ollama. Run scripts/laptop_a.sh again."
    return f"The agent run failed: {message[:300]}"


def ollama_reachable() -> bool:
    try:
        return httpx.get(f"{config.OLLAMA_URL}/v1/models", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False
