"""One request end to end: normalize -> classify -> context -> chain -> session -> banner.
Optionally streams progress through `emit` so the page can render stages and tokens live."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from . import agents, config, context, vision
from .classify import Route, classify
from .normalize import ImagePart, Part, TextPart, normalize
from .trueforge import TrueForgeClient, image_part, text_part

Emit = Callable[[dict], None]


@dataclass
class Hop:
    stage: str  # ocr | vision | doc
    agent: str
    model: str
    tool_calls: list[str]
    seconds: float
    timings: dict = field(default_factory=dict)


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

    def run(self, client_id: str, prompt: str, uploads: list[tuple[str, bytes]], emit: Emit | None = None) -> Result:
        emit = emit or (lambda _e: None)
        trace: list[str] = []
        parts: list[Part] = []
        for name, data in uploads:
            got = normalize(name, data)
            parts.extend(got)
            trace.append(f"normalized {name} -> " + ", ".join(_kind(p) for p in got))

        before = _snapshot()
        hops: list[Hop] = []
        extracted: str | None = None
        answer = ""
        ctx_docs: list[str] = []

        # Text-only model: read images locally with Tesseract and continue as a text request.
        if vision.mode() == "ocr" and any(isinstance(p, ImagePart) for p in parts):
            emit({"type": "stage", "stage": "ocr", "agent": "OCR (tesseract)", "model": "local", "status": "start"})
            t0 = time.time()
            parts = [TextPart(f"{p.label} (OCR)", vision.ocr(p.png)) if isinstance(p, ImagePart) else p for p in parts]
            hop = Hop("ocr", "OCR (tesseract)", "local", [], round(time.time() - t0, 1))
            hops.append(hop)
            emit({"type": "stage", "stage": "ocr", "status": "done", "seconds": hop.seconds})
            trace.append(f"vision model unavailable ({config.VISION_MODEL_ID} has no vision capability): images OCR'd locally")

        route: Route = classify(prompt, parts)
        trace.append(f"route: {' -> '.join(route.stages)} ({route.reason})")
        emit({"type": "route", "stages": route.stages, "reason": route.reason})

        images = [p for p in parts if isinstance(p, ImagePart)]
        texts = [p for p in parts if isinstance(p, TextPart)]

        if "vision" in route.stages:
            extracted, hop = self._vision(client_id, prompt, images, texts, chained="doc" in route.stages, emit=emit)
            hops.append(hop)
            answer = extracted
            trace.append(f"vision: {len(extracted)} chars in {hop.seconds}s (first token {hop.timings.get('first_token')}s), tools={hop.tool_calls or '-'}")

        if "doc" in route.stages:
            answer, hop, ctx_docs = self._doc(client_id, prompt, texts, extracted, emit=emit)
            hops.append(hop)
            trace.append(
                f"doc: {hop.seconds}s (first token {hop.timings.get('first_token')}s, tools {hop.timings.get('tools')}s), "
                f"context={ctx_docs or '-'}, tools={hop.tool_calls or '-'}"
            )
            if hop.timings.get("reasoning_chars"):
                trace.append(f"note: model emitted {hop.timings['reasoning_chars']} hidden reasoning chars - /no_think not honoured")

        files = _new_files(before)
        session_id = self.sessions.get(client_id, "doc") or self.sessions.get(client_id, "vision") or ""
        return Result(answer, hops, route.reason, ctx_docs, files, session_id, extracted, trace)

    # --- stages -------------------------------------------------------------------------------

    def _vision(self, client_id, prompt, images, texts, chained: bool, emit: Emit) -> tuple[str, Hop]:
        emit({"type": "stage", "stage": "vision", "agent": "Vision Agent", "model": config.VISION_MODEL_LABEL, "status": "start"})
        sid = self.sessions.get(client_id, "vision")
        if sid is None:
            sid = self.tf.create_session(agents.vision_spec())
            self.sessions.put(client_id, "vision", sid)
        ask = "Transcribe this document completely and list the key findings." if chained or not prompt else prompt
        if chained and prompt:
            ask += f"\n(The operator's overall request, for context only: {prompt})"
        content = [text_part(ask)]
        content += [text_part(f"Attached text from {t.label}:\n{t.text}") for t in texts]
        content += [image_part(f"{i + 1}-{_safe(img.label)}.png", img.png) for i, img in enumerate(images)]
        if config.VISION_AGENT_TOOLS:
            paths = ", ".join(str(i.saved_path) for i in images if i.saved_path)
            content.append(text_part(f"Image file paths for extract_from_scan (OCR): {paths}"))
        t0 = time.time()
        r = self.tf.run_turn(sid, content, emit=lambda e: emit({**e, "stage": "vision"}))
        hop = Hop("vision", "Vision Agent", config.VISION_MODEL_LABEL, r.tool_calls, round(time.time() - t0, 1), r.timings)
        emit({"type": "stage", "stage": "vision", "status": "done", "seconds": hop.seconds, "timings": r.timings})
        return r.text, hop

    def _doc(self, client_id, prompt, texts, extracted, emit: Emit) -> tuple[str, Hop, list[str]]:
        emit({"type": "stage", "stage": "doc", "agent": "Doc Agent", "model": config.DOC_MODEL_LABEL, "status": "start"})
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
        r = self.tf.run_turn(sid, "\n\n".join(blocks), emit=lambda e: emit({**e, "stage": "doc"}))
        hop = Hop("doc", "Doc Agent", config.DOC_MODEL_LABEL, r.tool_calls, round(time.time() - t0, 1), r.timings)
        emit({"type": "stage", "stage": "doc", "status": "done", "seconds": hop.seconds, "timings": r.timings})
        return r.text, hop, docs


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
