"""Register everything the dispatcher needs in a running TrueForge: the Ollama provider, the MCP
tool server, and both agents. Idempotent - re-run after any change.

    .venv/bin/python -m scripts.register --ollama http://<laptop-a>:11434

Skills are NOT registered: TrueForge only accepts github.com / gitlab.com skill URLs, which are
unreachable offline. The SKILL.md body is embedded in the Doc Agent's instructions instead.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from dispatcher import agents, config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trueforge", default=config.TRUEFORGE_URL)
    ap.add_argument("--ollama", default=config.OLLAMA_URL, help="Laptop A base URL, e.g. http://192.168.10.2:11434")
    ap.add_argument("--mcp", default=config.MCP_SERVER_URL)
    ap.add_argument("--vision-id", default=config.VISION_MODEL_ID, help="Ollama tag for the reader")
    ap.add_argument("--doc-id", default=config.DOC_MODEL_ID, help="Ollama tag for the writer")
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {config.TRUEFORGE_TOKEN}"} if config.TRUEFORGE_TOKEN else {}
    c = httpx.Client(base_url=args.trueforge, headers=headers, timeout=20)
    try:
        c.get("/healthz").raise_for_status()
    except httpx.HTTPError as e:
        print(f"TrueForge not reachable at {args.trueforge}: {e}")
        return 1

    provider(c, args)
    mcp_server(c, args)
    agent(c, agents.VISION_AGENT_NAME, agents.vision_spec())
    agent(c, agents.DOC_AGENT_NAME, agents.doc_spec("(context is injected per session by the dispatcher)"))
    print("\nDone. Models visible to TrueForge:")
    for m in c.get("/api/v1/models").json().get("data", []):
        print("  -", m.get("name") or m)
    return 0


def provider(c: httpx.Client, args) -> None:
    """Register every tag on the server (so the page's writer selector can pick any of them), always
    including the configured reader and writer even if the server is unreachable right now."""
    tags: list[str] = []
    try:
        tags = [m["name"] for m in httpx.get(f"{args.ollama.rstrip('/')}/api/tags", timeout=4).json().get("models", [])]
    except (httpx.HTTPError, ValueError, KeyError):
        print("    (model server unreachable - registering only the configured reader and writer)")
    for t in (args.vision_id, args.doc_id):
        if t not in tags:
            tags.append(t)
    seen: set[str] = set()
    models = []
    for t in tags:
        a = config.alias(t)
        if a in seen:
            continue
        seen.add(a)
        models.append({"model_id": t, "name": a, "properties": {"context_length": 32768, "max_output_tokens": 8192}})
    manifest = {"type": "custom", "name": config.PROVIDER_NAME, "base_url": f"{args.ollama.rstrip('/')}/v1", "models": models}
    print(f"    models: {', '.join(m['name'] for m in models)}")
    existing = _find(c.get("/api/v1/settings/model-providers").json(), config.PROVIDER_NAME)
    if existing:
        r = c.put("/api/v1/settings/model-providers", json={"manifest": manifest})
        _report(r, f"provider '{config.PROVIDER_NAME}' updated")
    else:
        r = c.post("/api/v1/settings/model-providers", json={"manifest": manifest})
        _report(r, f"provider '{config.PROVIDER_NAME}' created -> {manifest['base_url']}")


def mcp_server(c: httpx.Client, args) -> None:
    manifest = {
        "type": "remote",
        "name": config.MCP_SERVER_NAME,
        "url": args.mcp,
        "description": "Sovereign workbench tools: OCR a scan, generate .docx / .xlsx documents.",
    }
    existing = _find(c.get("/api/v1/settings/mcp-servers").json(), config.MCP_SERVER_NAME)
    r = c.put("/api/v1/settings/mcp-servers", json={"manifest": manifest}) if existing else c.post(
        "/api/v1/settings/mcp-servers", json={"manifest": manifest}
    )
    _report(r, f"mcp server '{config.MCP_SERVER_NAME}' {'updated' if existing else 'created'} -> {args.mcp}")
    tools = c.get(f"/api/v1/mcp-servers/{config.MCP_SERVER_NAME}/tools")
    if tools.status_code == 200:
        names = [t.get("name") for t in tools.json().get("data", [])]
        print(f"    tools discovered: {names or 'none - is the MCP server running?'}")
    else:
        print(f"    tools not listed ({tools.status_code}) - start the MCP server and re-run")


def agent(c: httpx.Client, name: str, spec: dict) -> None:
    listing = c.get("/api/v1/agents").json().get("data", [])
    match = next((a for a in listing if a.get("name") == name), None)
    if match:
        r = c.put(f"/api/v1/agents/{match['id']}", json={"manifest": spec})
        _report(r, f"agent '{name}' updated ({spec['model']['name']})")
    else:
        r = c.post("/api/v1/agents", json={"name": name, "manifest": spec})
        _report(r, f"agent '{name}' created ({spec['model']['name']})")


def _find(payload, name: str):
    items = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(items, dict):
        items = items.get("data", [])
    for it in items or []:
        m = it.get("manifest", it)
        if m.get("name") == name:
            return it
    return None


def _report(r: httpx.Response, ok: str) -> None:
    if r.status_code < 300:
        print("[ok]", ok)
    else:
        print(f"[!!] {ok} FAILED ({r.status_code}): {r.text[:400]}")


if __name__ == "__main__":
    sys.exit(main())
