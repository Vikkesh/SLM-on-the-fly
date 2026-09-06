"""The two agent specs. Saved to TrueForge by scripts/register.py; also passed inline per session by
the dispatcher (which is how per-request context gets into `instructions`)."""

from __future__ import annotations

import re

from . import config

VISION_AGENT_NAME = "vision-agent"
DOC_AGENT_NAME = "doc-agent"

# Everything a 7-8B model cannot afford in its prompt is switched off explicitly.
_LEAN_CONFIG = {
    "dynamic_sub_agents": {"enabled": False},
    "generative_ui": {"enabled": False},
    "ask_user_questions": {"enabled": False},
    # large_tool_response adds its own guidance block; our tools return one short line each.
    "context_management": {"compaction": {"enabled": True}, "large_tool_response": {"enabled": False}},
}

_TOOLS = {
    "name": config.MCP_SERVER_NAME,
    "enable_tools": ["@all"],
    "require_approval_for_tools": [],  # default gates @write tools behind Allow/Deny - fatal on stage
    "preload": True,
}

VISION_INSTRUCTIONS = """You are the Vision Agent of an on-premise industrial document workbench.
You read scanned documents, photographs of equipment, handwritten log sheets and forms.

When given an image:
1. Transcribe ALL legible text faithfully, preserving structure. Render tables as markdown tables.
2. Then add a short "Key findings" list: equipment IDs, dates, readings with units, defects, statuses, signatures.
3. Mark anything illegible as [illegible] instead of guessing.
Be exact and complete. Do not summarise away numbers. Do not add commentary beyond the findings."""

DOC_INSTRUCTIONS_BASE = """You are the Doc Agent of an on-premise industrial document workbench for a refinery.
You write formal documents for engineers and approving officers, and you answer technical questions
using the company context provided below.

Rules:
- Formal, precise register. Full sentences. No chat filler, no emojis, no markdown headings inside prose.
- Cite the SOP or manual section you relied on when the context contains one.
- Never invent readings, dates, names or asset IDs. If something is missing, leave a clearly marked placeholder.
- When asked for a document, call generate_docx (Word), generate_pdf (PDF) or generate_xlsx (Excel) - the
  one the user asked for, Word if unspecified - then report the returned path with a 2-3 line summary.
  Never paste the whole document into chat.
- Use a `table` in a section whenever there are readings to compare against limits."""

SANDBOX_NOTE = """
- When asked to write and run code, write plain Python using only the standard library or packages already
  installed in the sandbox; the sandbox has no internet access."""


def skill_body() -> str:
    """Body of SKILL.md without frontmatter. Embedded in the Doc Agent's instructions because TrueForge only
    accepts github.com/gitlab.com skill URLs, which are unreachable offline."""
    try:
        text = config.SKILL_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    return re.sub(r"^---.*?---\s*", "", text, count=1, flags=re.S).strip()


def _finish(instructions: str) -> str:
    return instructions + ("\n/no_think" if config.NO_THINK else "")


def vision_spec() -> dict:
    spec = {
        "model": {"name": config.VISION_MODEL_FQN, "params": {"temperature": 0.1}},
        "instructions": _finish(VISION_INSTRUCTIONS),
        "config": {**_LEAN_CONFIG, "sandbox": {"enabled": False}, "iteration_limit": 3},
    }
    if config.VISION_AGENT_TOOLS:
        spec["mcp_servers"] = [_TOOLS]
    return spec


def doc_spec(company_context: str = "") -> dict:
    instructions = DOC_INSTRUCTIONS_BASE + (SANDBOX_NOTE if config.ENABLE_SANDBOX else "")
    body = skill_body()
    if body:
        instructions += "\n\n## Procedure: scan-to-approval-note\n" + body
    if company_context:
        instructions += "\n\n## Company context (retrieved for this session)\n" + company_context
    else:
        instructions += "\n\n## Company context\n(no matching SOP found for this request)"
    return {
        "model": {"name": config.DOC_MODEL_FQN, "params": {"temperature": 0.3}},
        "instructions": _finish(instructions),
        "mcp_servers": [_TOOLS],
        "config": {
            **_LEAN_CONFIG,
            "sandbox": {"enabled": config.ENABLE_SANDBOX, "file_downloads": True},
            "iteration_limit": 8,
        },
    }
