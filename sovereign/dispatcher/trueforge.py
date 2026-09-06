"""Thin HTTP client for the TrueForge API. Sessions are created with an inline agent spec; turns are
streamed as SSE and re-emitted as small events (delta / tool) so the page can render live, and timed
so the trace can say where the seconds went (prefill vs generation vs tools)."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

from . import config

Emit = Callable[[dict], None]


class TrueForgeError(Exception):
    """Carries a one-sentence message safe to show the operator (Flow 5)."""


@dataclass
class TurnResult:
    text: str
    tool_calls: list[str] = field(default_factory=list)
    status: str = "done"
    error: str | None = None
    turn_id: str | None = None
    # first_token: seconds until the first visible character (prefill + any hidden reasoning);
    # tools: seconds spent inside tool calls; reasoning_chars: hidden thinking, should be 0 with /no_think.
    timings: dict = field(default_factory=dict)


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

    def healthy(self) -> bool:
        try:
            return self._http.get("/healthz", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    def create_session(self, spec: dict) -> str:
        try:
            r = self._http.post("/api/v1/sessions", json={"agent": {"spec": spec}})
        except httpx.ConnectError as e:
            raise TrueForgeError(f"TrueForge is not reachable at {config.TRUEFORGE_URL}. Is it running?") from e
        if r.status_code >= 400:
            raise TrueForgeError(f"TrueForge rejected the session ({r.status_code}): {_detail(r)}")
        return r.json()["data"]["id"]

    def run_turn(self, session_id: str, content: str | list[dict], emit: Emit | None = None) -> TurnResult:
        body = {"input": [{"type": "user.message", "content": content}], "stream": True}
        st = _TurnState(emit or (lambda _e: None))
        try:
            with self._http.stream("POST", f"/api/v1/sessions/{session_id}/turns", json=body) as r:
                if r.status_code >= 400:
                    r.read()
                    raise TrueForgeError(f"TrueForge rejected the turn ({r.status_code}): {_detail(r)}")
                for line in r.iter_lines():
                    if line.startswith("data:"):
                        st.consume(json.loads(line[5:].strip()))
        except httpx.ConnectError as e:
            raise TrueForgeError(f"TrueForge is not reachable at {config.TRUEFORGE_URL}. Is it running?") from e
        except httpx.ReadTimeout as e:
            raise TrueForgeError(
                f"The model did not answer within {int(config.TURN_TIMEOUT_S)}s. "
                "Check that the model server is reachable and the model is loaded."
            ) from e
        result = st.finish()
        if result.status == "error":
            raise TrueForgeError(_friendly(result.error or "unknown error"))
        return result


class _TurnState:
    def __init__(self, emit: Emit) -> None:
        self.emit = emit
        self.t0 = time.time()
        self.first_token: float | None = None
        self.tool_seconds = 0.0
        self.tool_started: dict[str, tuple[str, float]] = {}
        self.reasoning_chars = 0
        self.streamed = []  # deltas, joined as a fallback when turn.done carries no output
        self.result = TurnResult(text="")

    def consume(self, ev: dict) -> None:
        kind = ev.get("type")
        if ev.get("thread_id", "main") not in ("main", None):
            return  # subagent threads are off, but never render them if they appear
        if kind == "turn.created":
            self.result.turn_id = ev.get("turn_id") or ev.get("id")
        elif kind == "model.message.delta":
            if ev.get("reasoning_content"):
                self.reasoning_chars += len(ev["reasoning_content"])
            text = ev.get("content")
            if text:
                if self.first_token is None:
                    self.first_token = round(time.time() - self.t0, 2)
                self.streamed.append(text)
                self.emit({"type": "delta", "text": text})
        elif kind == "model.message":
            for call in ev.get("tool_calls") or []:
                name = (call.get("function") or {}).get("name") or call.get("name") or "tool"
                cid = call.get("id") or name
                self.result.tool_calls.append(name)
                self.tool_started[cid] = (name, time.time())
                self.emit({"type": "tool", "name": name, "status": "call"})
        elif kind == "tool.response":
            name, started = self.tool_started.pop(ev.get("tool_call_id", ""), ("tool", time.time()))
            secs = round(time.time() - started, 2)
            self.tool_seconds += secs
            self.emit({"type": "tool", "name": name, "status": "done", "seconds": secs, "preview": str(ev.get("content", ""))[:160]})
        elif kind == "turn.done":
            state = ev.get("state") or {}
            self.result.status = state.get("status", "done")
            if self.result.status == "error":
                self.result.error = state.get("message")
                return
            output = state.get("output") or {}
            self.result.text = _content_text(output.get("content")) or "".join(self.streamed)
            if not self.result.text and state.get("required_actions"):
                self.result.text = "(the agent paused waiting for an action - check approval settings)"

    def finish(self) -> TurnResult:
        total = round(time.time() - self.t0, 2)
        self.result.timings = {
            "first_token": self.first_token,
            "tools": round(self.tool_seconds, 2),
            "total": total,
            "reasoning_chars": self.reasoning_chars,
        }
        return self.result


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
        return "The model is not registered on Ollama. Re-run scripts/run_all.sh start."
    return f"The agent run failed: {message[:300]}"


_reach: tuple[float, bool] = (0.0, False)


def ollama_reachable() -> bool:
    """Cached for a few seconds: the health endpoint is polled, and a black-holed host costs a full timeout."""
    global _reach
    now = time.time()
    if now - _reach[0] < 5:
        return _reach[1]
    try:
        ok = httpx.get(f"{config.OLLAMA_URL}/v1/models", timeout=2).status_code == 200
    except httpx.HTTPError:
        ok = False
    _reach = (now, ok)
    return ok
