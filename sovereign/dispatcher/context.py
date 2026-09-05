"""Keyword lookup over a small folder of SOP/manual excerpts. Deliberately not RAG."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from . import config

STOP = {
    "the", "and", "for", "with", "this", "that", "from", "are", "was", "were", "have", "has",
    "please", "can", "you", "what", "which", "into", "about", "give", "make", "using", "use",
}


@lru_cache(maxsize=1)
def _docs() -> list[tuple[str, str]]:
    folder: Path = config.CONTEXT_DIR
    if not folder.is_dir():
        return []
    return [(p.stem, p.read_text(encoding="utf-8", errors="replace")) for p in sorted(folder.glob("*.md"))]


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text.lower()) if t not in STOP}


def resolve(query: str) -> tuple[str, list[str]]:
    """Return (context string, matched doc names). Empty when nothing matches."""
    q = _tokens(query)
    if not q:
        return "", []
    scored = []
    for name, body in _docs():
        body_l = body.lower()
        title_bonus = 3 * sum(1 for t in q if t in name.lower())
        hits = sum(body_l.count(t) for t in q)
        if hits or title_bonus:
            scored.append((hits + title_bonus, name, body))
    scored.sort(reverse=True)
    chosen = scored[: config.MAX_CONTEXT_DOCS]
    blocks = [f"### {name}\n{body.strip()[: config.MAX_CONTEXT_CHARS_PER_DOC]}" for _, name, body in chosen]
    return "\n\n".join(blocks), [name for _, name, _ in chosen]
