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

# Provider name as registered in TrueForge (Settings -> Models). Model FQN is "<provider>/<model>".
PROVIDER_NAME = os.environ.get("PROVIDER_NAME", "ollama")
VISION_MODEL_ALIAS = os.environ.get("VISION_MODEL_ALIAS", "vision-model")
DOC_MODEL_ALIAS = os.environ.get("DOC_MODEL_ALIAS", "doc-model")
VISION_MODEL_FQN = f"{PROVIDER_NAME}/{VISION_MODEL_ALIAS}"
DOC_MODEL_FQN = f"{PROVIDER_NAME}/{DOC_MODEL_ALIAS}"
# Human-readable names shown in the "Routed to" banner.
VISION_MODEL_LABEL = os.environ.get("VISION_MODEL_LABEL", "qwen2.5vl:7b")
DOC_MODEL_LABEL = os.environ.get("DOC_MODEL_LABEL", "qwen3:8b")

MCP_SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "sovereign-tools")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:9000/mcp")
# Let the Vision Agent call tools too (fallback path). Off by default: chaining is primary.
VISION_AGENT_TOOLS = os.environ.get("VISION_AGENT_TOOLS", "0") == "1"

# Bounded so Flow 5 (server unreachable) fails cleanly instead of hanging.
TURN_TIMEOUT_S = float(os.environ.get("TURN_TIMEOUT_S", "240"))
CONNECT_TIMEOUT_S = float(os.environ.get("CONNECT_TIMEOUT_S", "5"))

# Normalization caps. Small models have small context windows.
MAX_TABLE_ROWS = int(os.environ.get("MAX_TABLE_ROWS", "40"))
MAX_PDF_PAGES = int(os.environ.get("MAX_PDF_PAGES", "4"))
PDF_RENDER_SCALE = float(os.environ.get("PDF_RENDER_SCALE", "2.0"))
SCANNED_PDF_CHARS_PER_PAGE = int(os.environ.get("SCANNED_PDF_CHARS_PER_PAGE", "200"))
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "12000"))
MAX_CONTEXT_DOCS = int(os.environ.get("MAX_CONTEXT_DOCS", "2"))
MAX_CONTEXT_CHARS_PER_DOC = int(os.environ.get("MAX_CONTEXT_CHARS_PER_DOC", "1500"))
