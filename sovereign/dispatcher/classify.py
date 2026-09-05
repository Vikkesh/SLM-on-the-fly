"""Deterministic routing. No model is consulted - the decision must be explainable on stage."""

from __future__ import annotations

from dataclasses import dataclass

from .normalize import ImagePart, Part

WRITE_INTENT = (
    "draft", "write", "generate", "create", "prepare", "produce", "compose",
    "approval", "note", "report", "memo", "letter", "document", "docx", "word file",
    "summar", "spreadsheet", "xlsx", "excel",
)
CODE_INTENT = (
    "script", "code", "python", "run it", "execute", "calculate", "compute", "plot", "simulate",
)


@dataclass
class Route:
    stages: list[str]  # ["vision"], ["doc"], or ["vision", "doc"]
    reason: str
    code_intent: bool


def classify(prompt: str, parts: list[Part]) -> Route:
    has_image = any(isinstance(p, ImagePart) for p in parts)
    text = prompt.lower()
    wants_document = any(w in text for w in WRITE_INTENT)
    code = any(w in text for w in CODE_INTENT)

    if has_image and wants_document:
        return Route(["vision", "doc"], "image attached + document requested: read with Vision, write with Doc", code)
    if has_image:
        return Route(["vision"], "image attached: Vision Agent reads it", code)
    if code:
        return Route(["doc"], "code requested: Doc Agent with sandbox", code)
    return Route(["doc"], "text only: Doc Agent", code)
