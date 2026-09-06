"""FastAPI front door. Serves the operator page, a streaming /api/ask/stream (SSE) and a plain
/api/ask (JSON) for scripts."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, vision
from .normalize import UnsupportedFile
from .pipeline import Dispatcher, Result
from .trueforge import TrueForgeError, ollama_reachable

STATIC = Path(__file__).parent / "static"
SAMPLES = config.ROOT / "samples"

app = FastAPI(title="Sovereign AI Workbench - dispatcher")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
if SAMPLES.is_dir():
    app.mount("/samples", StaticFiles(directory=SAMPLES), name="samples")
dispatcher = Dispatcher()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/ping")
def ping() -> dict:
    """Readiness only - no upstream probes, so scripts can poll it cheaply."""
    return {"ok": True}


@app.get("/api/health")
def health() -> dict:
    return {
        "trueforge": dispatcher.tf.healthy(),
        "ollama": ollama_reachable(),
        "models": {"vision": config.VISION_MODEL_LABEL, "doc": config.DOC_MODEL_LABEL},
        "vision_mode": vision.mode(),
        "sandbox": config.ENABLE_SANDBOX,
        "samples": sorted(p.name for p in SAMPLES.iterdir() if p.is_file()) if SAMPLES.is_dir() else [],
    }


async def _read_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    return [(f.filename or "upload", await f.read()) for f in files if f.filename]


def _payload(result: Result, client_id: str) -> dict:
    return {
        "client_session": client_id,
        "answer": result.answer,
        "extracted": result.extracted,
        "routed": [
            {"stage": h.stage, "agent": h.agent, "model": h.model, "tool_calls": h.tool_calls,
             "seconds": h.seconds, "timings": h.timings}
            for h in result.hops
        ],
        "banner": " -> ".join(f"{h.agent} ({h.model})" for h in result.hops),
        "route_reason": result.route_reason,
        "context_docs": result.context_docs,
        "files": [{"name": f, "url": f"/output/{f}"} for f in result.files],
        "trace": result.trace,
    }


@app.post("/api/ask")
async def ask(prompt: str = Form(""), client_session: str = Form(""), files: list[UploadFile] = File(default=[])):
    client_id = client_session or uuid.uuid4().hex
    uploads = await _read_uploads(files)
    if not prompt.strip() and not uploads:
        raise HTTPException(400, "Type a prompt or attach a file.")
    try:
        result = await asyncio.to_thread(dispatcher.run, client_id, prompt.strip(), uploads)
    except UnsupportedFile as e:
        raise HTTPException(415, str(e)) from e
    except TrueForgeError as e:
        return JSONResponse(status_code=502, content={"error": str(e), "client_session": client_id})
    return _payload(result, client_id)


@app.post("/api/ask/stream")
async def ask_stream(prompt: str = Form(""), client_session: str = Form(""), files: list[UploadFile] = File(default=[])):
    """SSE: `route`, `stage` (start/done), `delta` (text), `tool` (call/done), then `done` or `error`."""
    client_id = client_session or uuid.uuid4().hex
    uploads = await _read_uploads(files)
    if not prompt.strip() and not uploads:
        raise HTTPException(400, "Type a prompt or attach a file.")

    q: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            result = dispatcher.run(client_id, prompt.strip(), uploads, emit=q.put)
            q.put({"type": "done", **_payload(result, client_id)})
        except UnsupportedFile as e:
            q.put({"type": "error", "error": str(e), "client_session": client_id})
        except TrueForgeError as e:
            q.put({"type": "error", "error": str(e), "client_session": client_id})
        except Exception as e:  # keep the stream well-formed whatever happens
            q.put({"type": "error", "error": f"Dispatcher failure: {e}", "client_session": client_id})
        finally:
            q.put(None)

    threading.Thread(target=work, daemon=True).start()

    async def gen():
        loop = asyncio.get_running_loop()
        yield f"event: session\ndata: {json.dumps({'client_session': client_id})}\n\n"
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is None:
                break
            yield f"event: {item['type']}\ndata: {json.dumps(item)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
