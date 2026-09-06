"""All tunables in one place. Override any of them with an environment variable of the same name."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTEXT_DIR = Path(os.environ.get("CONTEXT_DIR", ROOT / "context"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output"))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", ROOT / "uploads"))
SKILL_FILE = ROOT / "skills" / "scan-to-approval-note" / "SKILL.md"

# Where the dispatcher listens; the operator's browser talks to this.
DISPATCHER_HOST = os.environ.get("DISPATCHER_HOST", "127.0.0.1")
DISPATCHER_PORT = int(os.environ.get("DISPATCHER_PORT", "8080"))

# TrueForge runs on the same laptop in STANDALONE mode.
TRUEFORGE_URL = os.environ.get("TRUEFORGE_URL", "http://127.0.0.1:8790").rstrip("/")
TRUEFORGE_TOKEN = os.environ.get("TRUEFORGE_TOKEN")  # only when OIDC login is enabled

# Ollama on Laptop A, reached only through TrueForge. The dispatcher pings it for the health pill.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

# Provider name as registered in the engine (Settings -> Models). Model FQN is "<provider>/<alias>".
PROVIDER_NAME = os.environ.get("PROVIDER_NAME", "ollama")
# Ollama tags. With a single model, both are the same tag.
VISION_MODEL_ID = os.environ.get("VISION_MODEL_ID", "qwen2.5vl:7b")
DOC_MODEL_ID = os.environ.get("DOC_MODEL_ID", "qwen3:8b")


def alias(tag: str) -> str:
    """Engine resource name for an Ollama tag: lowercase, [a-z0-9._-], starts with a letter."""
    import re

    a = re.sub(r"[^a-z0-9._-]+", "-", tag.lower()).strip("-.")
    if not a or not a[0].isalpha():
        a = "m-" + a
    return a[:64].rstrip("-.") or "model"


def fqn(tag: str) -> str:
    return f"{PROVIDER_NAME}/{alias(tag)}"


VISION_MODEL_ALIAS = alias(VISION_MODEL_ID)
DOC_MODEL_ALIAS = alias(DOC_MODEL_ID)
VISION_MODEL_FQN = fqn(VISION_MODEL_ID)
DOC_MODEL_FQN = fqn(DOC_MODEL_ID)
# Human-readable names shown in the "Routed to" banner.
VISION_MODEL_LABEL = os.environ.get("VISION_MODEL_LABEL", VISION_MODEL_ID)
DOC_MODEL_LABEL = os.environ.get("DOC_MODEL_LABEL", DOC_MODEL_ID)
# How images are read: "auto" asks Ollama whether VISION_MODEL_ID has the vision capability and
# falls back to local Tesseract OCR when it does not; "model" / "ocr" force one.
VISION_MODE = os.environ.get("VISION_MODE", "auto")

MCP_SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "sovereign-tools")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:9000/mcp")
# Let the Vision Agent call tools too (fallback path). Off by default: chaining is primary.
VISION_AGENT_TOOLS = os.environ.get("VISION_AGENT_TOOLS", "0") == "1"
# "direct": the reader calls Ollama itself (required for models Ollama marks as not supporting tools -
# the engine always attaches a built-in tool). "engine": run the reader as an engine agent.
VISION_BACKEND = os.environ.get("VISION_BACKEND", "engine" if VISION_AGENT_TOOLS else "direct")

# Bounded so Flow 5 (server unreachable) fails cleanly instead of hanging.
TURN_TIMEOUT_S = float(os.environ.get("TURN_TIMEOUT_S", "240"))
CONNECT_TIMEOUT_S = float(os.environ.get("CONNECT_TIMEOUT_S", "5"))

# Normalization caps. Small models have small context windows, and prefill is the slow direction
# on a laptop: every token here is paid for on every call.
MAX_TABLE_ROWS = int(os.environ.get("MAX_TABLE_ROWS", "40"))
MAX_PDF_PAGES = int(os.environ.get("MAX_PDF_PAGES", "4"))
PDF_RENDER_SCALE = float(os.environ.get("PDF_RENDER_SCALE", "1.3"))
MAX_IMAGE_EDGE = int(os.environ.get("MAX_IMAGE_EDGE", "1024"))  # ~1k visual tokens; 2x edge = 4x tokens
SCANNED_PDF_CHARS_PER_PAGE = int(os.environ.get("SCANNED_PDF_CHARS_PER_PAGE", "200"))
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "12000"))
MAX_CONTEXT_DOCS = int(os.environ.get("MAX_CONTEXT_DOCS", "2"))
MAX_CONTEXT_CHARS_PER_DOC = int(os.environ.get("MAX_CONTEXT_CHARS_PER_DOC", "900"))

# Latency levers.
# Qwen3 "thinks" before every answer unless told not to; that is hidden tokens before the first
# visible word. The /no_think soft switch turns it off. Harmless on models that do not support it.
NO_THINK = os.environ.get("NO_THINK", "1") == "1"
# The sandbox adds several KB of harness guidance plus tools to every prompt. Only Flow 6 needs it.
ENABLE_SANDBOX = os.environ.get("ENABLE_SANDBOX", "0") == "1"
