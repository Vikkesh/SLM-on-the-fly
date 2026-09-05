"""FastAPI front door. Serves the thin operator page and the /api/ask endpoint."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, vision
from .normalize import UnsupportedFile
from .pipeline import Dispatcher
from .trueforge import TrueForgeError, ollama_reachable

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Sovereign AI Workbench - dispatcher")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
dispatcher = Dispatcher()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    return {
        "trueforge": dispatcher.tf.healthy(),
        "ollama": ollama_reachable(),
        "models": {"vision": config.VISION_MODEL_LABEL, "doc": config.DOC_MODEL_LABEL},
        "vision_mode": vision.mode(),
    }


@app.post("/api/ask")
async def ask(
    prompt: str = Form(""),
    client_session: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    client_id = client_session or uuid.uuid4().hex
    uploads = [(f.filename or "upload", await f.read()) for f in files if f.filename]
    if not prompt.strip() and not uploads:
        raise HTTPException(400, "Type a prompt or attach a file.")
    try:
        result = dispatcher.run(client_id, prompt.strip(), uploads)
    except UnsupportedFile as e:
        raise HTTPException(415, str(e)) from e
    except TrueForgeError as e:
        return JSONResponse(status_code=502, content={"error": str(e), "client_session": client_id})
    return {
        "client_session": client_id,
        "answer": result.answer,
        "extracted": result.extracted,
        "routed": [
            {"agent": h.agent, "model": h.model, "tool_calls": h.tool_calls, "seconds": h.seconds}
            for h in result.hops
        ],
        "banner": " -> ".join(f"{h.agent} ({h.model})" for h in result.hops),
        "route_reason": result.route_reason,
        "context_docs": result.context_docs,
        "files": [{"name": f, "url": f"/output/{f}"} for f in result.files],
        "trace": result.trace,
    }


@app.get("/output/{name}")
def output(name: str):
    path = (config.OUTPUT_DIR / name).resolve()
    if path.parent != config.OUTPUT_DIR.resolve() or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=name)


def main() -> None:
    import uvicorn

    uvicorn.run("dispatcher.app:app", host=config.DISPATCHER_HOST, port=config.DISPATCHER_PORT, reload=False)


if __name__ == "__main__":
    main()
