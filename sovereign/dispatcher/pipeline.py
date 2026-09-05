"""One request end to end: normalize -> classify -> context -> chain -> session -> banner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import agents, config, context
from .classify import Route, classify
from .normalize import ImagePart, Part, TextPart, normalize
from .trueforge import TrueForgeClient, image_part, text_part


@dataclass
class Hop:
    agent: str
    model: str
    tool_calls: list[str]
    seconds: float


@dataclass
class Result:
    answer: str
    hops: list[Hop]
    route_reason: str
    context_docs: list[str]
    files: list[str]
    session_id: str
    extracted: str | None = None
    trace: list[str] = field(default_factory=list)


class SessionStore:
    """client session id -> {stage: TrueForge session id}. In-memory is fine for a single-operator demo."""

    def __init__(self) -> None:
        self._map: dict[str, dict[str, str]] = {}

    def get(self, client_id: str, stage: str) -> str | None:
        return self._map.get(client_id, {}).get(stage)

    def put(self, client_id: str, stage: str, session_id: str) -> None:
        self._map.setdefault(client_id, {})[stage] = session_id


class Dispatcher:
    def __init__(self, client: TrueForgeClient | None = None) -> None:
        self.tf = client or TrueForgeClient()
        self.sessions = SessionStore()

    def run(self, client_id: str, prompt: str, uploads: list[tuple[str, bytes]]) -> Result:
        trace: list[str] = []
        parts: list[Part] = []
        for name, data in uploads:
            got = normalize(name, data)
            parts.extend(got)
            trace.append(f"normalized {name} -> " + ", ".join(_kind(p) for p in got))

        route: Route = classify(prompt, parts)
        trace.append(f"route: {' -> '.join(route.stages)} ({route.reason})")

        images = [p for p in parts if isinstance(p, ImagePart)]
        texts = [p for p in parts if isinstance(p, TextPart)]
        before = _snapshot()
        hops: list[Hop] = []
        extracted: str | None = None
        answer = ""
        ctx_docs: list[str] = []

        if "vision" in route.stages:
            extracted, hop = self._vision(client_id, prompt, images, texts, chained="doc" in route.stages)
            hops.append(hop)
            answer = extracted
            trace.append(f"vision: {len(extracted)} chars extracted, tools={hop.tool_calls or '-'}")

        if "doc" in route.stages:
            answer, hop, ctx_docs = self._doc(client_id, prompt, texts, extracted)
            hops.append(hop)
            trace.append(f"doc: context={ctx_docs or '-'}, tools={hop.tool_calls or '-'}")

        files = _new_files(before)
        session_id = self.sessions.get(client_id, "doc") or self.sessions.get(client_id, "vision") or ""
        return Result(answer, hops, route.reason, ctx_docs, files, session_id, extracted, trace)

    # --- stages -------------------------------------------------------------------------------

    def _vision(self, client_id, prompt, images, texts, chained: bool) -> tuple[str, Hop]:
        sid = self.sessions.get(client_id, "vision")
        if sid is None:
            sid = self.tf.create_session(agents.vision_spec())
            self.sessions.put(client_id, "vision", sid)
        ask = (
            "Transcribe this document completely and list the key findings."
            if chained
            else prompt or "Transcribe this document completely and list the key findings."
        )
        if chained and prompt:
            ask += f"\n(The operator's overall request, for context only: {prompt})"
        content = [text_part(ask)]
        content += [text_part(f"Attached text from {t.label}:\n{t.text}") for t in texts]
        content += [image_part(f"{i + 1}-{_safe(img.label)}.png", img.png) for i, img in enumerate(images)]
        if config.VISION_AGENT_TOOLS:
            paths = ", ".join(str(i.saved_path) for i in images if i.saved_path)
            content.append(text_part(f"Image file paths for extract_from_scan (OCR): {paths}"))
        t0 = time.time()
        r = self.tf.run_turn(sid, content)
        return r.text, Hop("Vision Agent", config.VISION_MODEL_LABEL, r.tool_calls, round(time.time() - t0, 1))

    def _doc(self, client_id, prompt, texts, extracted) -> tuple[str, Hop, list[str]]:
        query = " ".join([prompt] + [t.text[:2000] for t in texts] + [extracted or ""])
        ctx, docs = context.resolve(query)
        sid = self.sessions.get(client_id, "doc")
        if sid is None:
            sid = self.tf.create_session(agents.doc_spec(ctx))
            self.sessions.put(client_id, "doc", sid)
        blocks = [prompt or "Proceed."]
        if extracted:
            blocks.append("## Findings extracted by the Vision Agent from the attached scan\n" + extracted)
        blocks += [f"## Attached: {t.label}\n{t.text}" for t in texts]
        t0 = time.time()
        r = self.tf.run_turn(sid, "\n\n".join(blocks))
        return r.text, Hop("Doc Agent", config.DOC_MODEL_LABEL, r.tool_calls, round(time.time() - t0, 1)), docs


# --- helpers ------------------------------------------------------------------------------------


def _kind(p: Part) -> str:
    return f"image({p.label})" if isinstance(p, ImagePart) else f"text({len(p.text)} chars)"


def _safe(label: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:40]


def _snapshot() -> set[str]:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return {p.name for p in config.OUTPUT_DIR.iterdir() if p.is_file() and not p.name.startswith(".")}


def _new_files(before: set[str]) -> list[str]:
    return sorted(_snapshot() - before)
