# sovereign/ — SAI, the workbench layer

Everything SAI adds lives here. The agent engine under `packages/` is used as-is through its HTTP
API and MCP; nothing there is modified. Design: `../ARCHITECTURE_sovereign_ai_workbench.md`. Scope:
`../PRD_sovereign_ai_workbench_v2.md`.

```
dispatcher/     router: normalize files -> classify -> context -> chain Vision->Doc -> banner   (:8080)
mcp_server/     HTTP MCP tools: extract_from_scan (OCR), generate_docx / generate_pdf / generate_xlsx, list_outputs (:9000)
skills/         scan-to-approval-note/SKILL.md  (embedded into the Doc Agent's instructions)
context/        sample SOP / manual excerpts used for keyword context lookup
samples/        synthetic scan + spreadsheet for testing  (make with scripts/make_sample.py)
scripts/        laptop_a.sh, laptop_b.sh, register.py, Modelfiles, runners
output/         generated .docx / .xlsx land here            (gitignored)
uploads/        normalized PNGs, readable by extract_from_scan (gitignored)
```

## Run (Laptop B) — two commands

```bash
# on a good internet connection (no model server needed): node 22, venv, a local copy of the agent engine, samples
scripts/run_all.sh prepare

# on the network that reaches the model server (no internet needed)
scripts/run_all.sh start --ollama http://<model-laptop>:11434 --model qwen3:8b --vision-model qwen2.5vl:7b

scripts/run_all.sh restart      # after a code change: tools + dispatcher only, the agent engine stays up
scripts/run_all.sh status
scripts/run_all.sh stop
```

`--model` is the writer (Doc Agent), `--vision-model` the reader (Vision Agent). With one
text-only model on the server, images are read with local Tesseract OCR and the banner says so
(`OCR (tesseract) -> Doc Agent`). Logs land in `logs/`; `prepare` installs the engine locally so `start` needs no network.

## Run by hand

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python -m scripts.make_sample                              # optional test inputs

# three terminals
.trueforge/node_modules/.bin/trueforge             # the agent engine, standalone, :8790 (installed by prepare)
scripts/run_mcp.sh                                # tools, :9000
OLLAMA_URL=http://<laptop-a>:11434 scripts/run_dispatcher.sh   # :8080  -> open http://127.0.0.1:8080

# once the agent engine is up (idempotent):
.venv/bin/python -m scripts.register --ollama http://<laptop-a>:11434
```

`scripts/laptop_a.sh` prepares the model server; `scripts/laptop_b.sh <ollama-url>` walks the
orchestrator prep, including the sandbox warm-up that must happen **before unplugging**.

## How a request moves

1. `dispatcher/normalize.py` turns every upload into text or PNG (PDF → PNG if scanned, else text;
   xlsx/csv → markdown table; docx → text). The models never see a file.
2. `dispatcher/classify.py` picks the route by file type + intent words. Deterministic.
3. `dispatcher/context.py` keyword-matches `context/*.md` and returns a short excerpt.
4. `dispatcher/pipeline.py` runs the stages: the reader (`reader.py`, a direct streaming call to
   Ollama — the engine would attach a built-in tool and Ollama rejects that for `qwen2.5vl`) reads →
   text carried into the Doc Agent,
   which writes and calls `generate_docx`. Sessions are created with an **inline agent spec** so
   the context lands in `instructions` (the agent engine has no prompt templating).
5. `dispatcher/app.py` streams it all to the page over SSE (`/api/ask/stream`): route, each stage
   starting/finishing with timings, every token, every tool call, then the files. `/api/ask` is the
   same thing as one JSON response for scripts.

## Environment knobs

All in `dispatcher/config.py`; override by env var. The ones you will touch:
`OLLAMA_URL`, `TRUEFORGE_URL`, `PROVIDER_NAME` (default `ollama`), `VISION_AGENT_TOOLS=1` to let
the Vision Agent call tools (fallback path), `TURN_TIMEOUT_S`, `MAX_TABLE_ROWS`, `MAX_PDF_PAGES`.

Latency levers (all default to the fast setting): `NO_THINK=1` appends Qwen3's `/no_think` switch so
the writer does not spend hidden tokens reasoning before every answer; `ENABLE_SANDBOX=1` turns the
sandbox back on for the code-execution demo (it adds a large block of harness guidance to every
prompt, so it is off otherwise); `MAX_IMAGE_EDGE` (1024) caps scan resolution — vision cost scales
with pixels; `MAX_CONTEXT_CHARS_PER_DOC` (900). The "How this was handled" panel under every answer
shows first-word time, tool time and total per hop, so you can see where the seconds went.

## Known constraints (verified against the engine's code)

- Skills must come from `github.com`/`gitlab.com` — the API rejects other URLs. Offline, the
  skill mechanism is unusable, so `SKILL.md` is embedded into the Doc Agent prompt by `agents.py`.
- The local sandbox needs `bwrap`, `socat`, `rg` and a one-time online init (pip-installs pydantic).
  It is only used for Flow 6 (run code). File reading never goes through it.
- MCP tools default to approval gating on write tools; `agents.py` sets
  `require_approval_for_tools: []` so `generate_docx` never pauses the demo.
