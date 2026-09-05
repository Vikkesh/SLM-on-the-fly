# Architecture: Sovereign On-Premise Agentic AI Workbench

Companion to `PRD_sovereign_ai_workbench_v2.md`. The PRD says *what* and *why*; this document
says *how the pieces fit*. Every claim about TrueForge below was checked against the code in
`packages/`, not the docs — the docs lag the implementation in several places that matter.

---

## 1. One-paragraph summary

Two laptops on a bare ethernet cable. **Laptop A** runs nothing but Ollama, serving two
open-weight models over an OpenAI-compatible endpoint. **Laptop B** runs the whole agentic
stack — our dispatcher, an unmodified TrueForge harness with two agents, our MCP tool server,
and a local sandbox. An operator at Laptop B uploads a scanned inspection report; the
dispatcher routes it to the *reading* model, carries the extracted text to the *writing*
model, and the writing model calls our tools to produce a real `.docx` approval note.
The only bytes that ever cross the cable are model inference requests. Nothing touches the
internet.

---

## 2. Models on the server

| Role | Ollama tag | Purpose | Vision | Tools | VRAM (q4) |
| --- | --- | --- | --- | --- | --- |
| **Reader** → Vision Agent | `qwen2.5vl:7b` | OCR and understanding of scans, photos, dense tables | ✅ | ✅ | ~6 GB |
| **Writer** → Doc Agent | `qwen3:8b` | Formal prose, orchestration, tool calling | ✗ | ✅ | ~5 GB |

**~11 GB to keep both resident.** If Laptop A has 24 GB+ VRAM, upgrade the writer to
`qwen3:14b` — prose quality is the most visible output in the demo.

Why this pair, and why not the original `qwen2.5-coder:7b` + `llama3.2-vision:11b`:

- `llama3.2-vision` cannot call tools and is weak at dense document OCR — the two things the
  hero flow needs most. `qwen2.5vl` was trained for document understanding and supports tools.
- `qwen2.5-coder` writes code well and prose badly. Document creation is primary; a general
  instruct model writes the approval note a PSU officer would actually sign.
- Same model family on both sides: one prompting style, consistent instruction-following.

**Raise the context windows.** Ollama defaults to a few thousand tokens, which silently
truncates the system prompt plus tool schemas and makes the agent look broken:

```
# Modelfile.vision                   # Modelfile.doc
FROM qwen2.5vl:7b                    FROM qwen3:8b
PARAMETER num_ctx 16384              PARAMETER num_ctx 32768

ollama create vision-model -f Modelfile.vision
ollama create doc-model    -f Modelfile.doc
```

The agents bind to `vision-model` and `doc-model`, so a model swap later is one `ollama create`.

---

## 3. Topology

```
╔══════════════════════════════╗         ╔═════════════════════════════════════════════════════╗
║  LAPTOP A — MODEL SERVER     ║         ║  LAPTOP B — ORCHESTRATOR   (identical on C, D …)    ║
║                              ║         ║                                                     ║
║  Ollama   0.0.0.0:11434      ║         ║   operator's browser                                ║
║  KEEP_ALIVE=-1               ║         ║          │                                          ║
║  MAX_LOADED_MODELS=2         ║         ║          ▼                                          ║
║                              ║         ║   ┌───────────────────────────────────────────┐     ║
║  ┌────────────────────────┐  ║         ║   │  DISPATCHER  :8080              (ours)    │     ║
║  │ vision-model           │  ║         ║   │                                           │     ║
║  │  = qwen2.5vl:7b        │  ║         ║   │  normalize ─▶ classify ─▶ context ─▶ chain│     ║
║  │  vision ✅  tools ✅   │  ║         ║   │  serves the thin upload/chat page         │     ║
║  └────────────────────────┘  ║         ║   │  renders  "Routed to: …"                  │     ║
║  ┌────────────────────────┐  ║         ║   └─────────────────────┬─────────────────────┘     ║
║  │ doc-model              │  ║         ║                         │  TrueForge SDK (localhost)║
║  │  = qwen3:8b            │  ║         ║   ┌─────────────────────▼─────────────────────┐     ║
║  │  vision ✗   tools ✅   │  ║         ║   │  TRUEFORGE  :8790     (upstream, untouched)│     ║
║  └────────────────────────┘  ║         ║   │  sessions · compaction · SQLite · run loop│     ║
║                              ║         ║   │                                           │     ║
║  OpenAI-compatible  /v1  ◀───╫── LAN ──╫───┤   ┌──────────────┐    ┌──────────────┐    │     ║
║                              ║  only   ║   │   │ VISION AGENT │    │  DOC AGENT   │    │     ║
║  no TrueForge                ║ traffic ║   │   │ vision-model │    │  doc-model   │    │     ║
║  no dispatcher               ║ on the  ║   │   │ reads        │    │  writes      │    │     ║
║  no tools · no sandbox       ║  wire   ║   │   └──────────────┘    └──┬────────┬──┘    │     ║
║  no internet                 ║         ║   └──────────────────────────┼────────┼───────┘     ║
╚══════════════════════════════╝         ║                   MCP/HTTP   │        │ exec        ║
                                         ║   ┌──────────────────────────▼──┐  ┌──▼───────────┐ ║
                                         ║   │ MCP TOOL SERVER             │  │ SANDBOX      │ ║
                                         ║   │ 127.0.0.1:9000  (ours)      │  │ (bubblewrap, │ ║
                                         ║   │                             │  │  spawned by  │ ║
                                         ║   │  extract_from_scan  ← OCR   │  │  TrueForge)  │ ║
                                         ║   │  generate_docx      ← docx  │  │              │ ║
                                         ║   │  generate_xlsx      ← xlsx* │  │ .venv        │ ║
                                         ║   │                             │  │ skills/ (git)│ ║
                                         ║   │  approval gating: OFF       │  │  scan-to-    │ ║
                                         ║   └─────────────────────────────┘  │  approval/   │ ║
                                         ║                                    └──────────────┘ ║
                                         ║   output/   ← generated .docx land here             ║
                                         ╚═════════════════════════════════════════════════════╝
                                                                       * stretch
```

**What crosses the cable:** `POST /v1/chat/completions` from TrueForge to Ollama, and nothing
else. Tool calls, sandbox execution, file I/O, and session state are all localhost on Laptop B.

---

## 4. Components

### 4.1 Dispatcher (ours — the one piece TrueForge lacks)

TrueForge binds exactly one model per agent and has no way to choose a model per request.
The dispatcher is that missing router, plus the glue that TrueForge's lack of instruction
templating forces on us. It is deterministic code — no LLM in the loop.

```
   request in
       │
       ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ ① NORMALIZE  every attachment becomes text or PNG                │
  │      .png .jpg        → pass through                             │
  │      .pdf             → rasterize pages → PNG                    │
  │      .xlsx .csv       → openpyxl → markdown table (text)         │
  │      .txt .md .docx   → extract text                             │
  │      (nothing ever takes TrueForge's sandbox-upload path)        │
  ├─────────────────────────────────────────────────────────────────┤
  │ ② CLASSIFY   image present?  ──yes──▶  Vision Agent (stage A)    │
  │              text only?      ──yes──▶  Doc Agent                 │
  │              asks for code?  ──yes──▶  Doc Agent + sandbox       │
  ├─────────────────────────────────────────────────────────────────┤
  │ ③ CONTEXT    keyword match against context/*.md  → short string  │
  │              (deliberately not RAG — no vectors, no embeddings)  │
  ├─────────────────────────────────────────────────────────────────┤
  │ ④ CHAIN      Vision → Doc for anything that needs both           │
  │              carries extracted text from A into B's prompt       │
  ├─────────────────────────────────────────────────────────────────┤
  │ ⑤ SESSION    sessions.create({ agent: { spec: INLINE } })        │
  │              instructions = base + context (composed here,       │
  │              because the agent spec has no {{variables}})        │
  ├─────────────────────────────────────────────────────────────────┤
  │ ⑥ BANNER     "Routed to: Vision Agent (qwen2.5vl:7b)"            │
  └─────────────────────────────────────────────────────────────────┘
```

**Client access path.** The dispatcher serves its own minimal upload-plus-chat page. This is
deliberate: TrueForge's bundled chat UI posts straight to TrueForge's own API with a
user-picked agent, bypassing the dispatcher — which would delete automatic routing, a stated
must-demo criterion. Reverse-proxying the bundled UI is possible but requires passing SSE
streams through untouched; too risky for a five-hour build. The bundled UI remains the
panic-button fallback (manual agent pick, no auto-routing).

### 4.2 TrueForge (upstream, unmodified)

Used strictly through its public seams: HTTP API / SDK, MCP, skills, agent spec. Runs in
`STANDALONE` mode — SQLite, no Postgres, no Redis. Provides the agent loop, sessions,
compaction, sandbox lifecycle, and file download.

### 4.3 Agents

| Setting | Vision Agent | Doc Agent | Why |
| --- | --- | --- | --- |
| model | `custom/vision-model` | `custom/doc-model` | |
| MCP servers | `sovereign-tools` (optional) | `sovereign-tools` | Doc Agent drives the tools; Vision Agent may, as fallback |
| skills | none | `scan-to-approval-note` | procedure only matters where tools are called |
| `config.sandbox.enabled` | `false` | `true` | skills + Flow 6 need it; Vision Agent has no use for it |
| `dynamic_sub_agents` | `false` | `false` | on by default; adds prompt + schema weight a 7–8B model can't afford |
| `generative_ui` | `false` | `false` | same |
| `ask_user_questions` | `false` | `false` | same — and a paused turn looks like a hang on stage |
| `mcp_servers[].preload` | — | `true` | three tools; skip the discovery hop |
| `require_approval_for_tools` | — | `[]` | default `["@write","@destructive"]` pauses for Allow/Deny mid-demo |
| `iteration_limit` | `3` | `10` | fail fast instead of looping |
| `compaction` | default | default | free |

### 4.4 MCP tool server (ours)

An **HTTP** MCP server — TrueForge's MCP client speaks Streamable HTTP and SSE only; there is
no stdio transport. FastMCP with `transport="streamable-http"` on `127.0.0.1:9000`, registered
under Settings → Connectors as a plain URL named `sovereign-tools`.

| Tool | Does | Library |
| --- | --- | --- |
| `extract_from_scan(image_path) → text` | Tesseract OCR; complements the vision model's read with exact characters | `pytesseract` |
| `generate_docx(title, sections, template?) → path` | Writes a real Word document to `output/` | `python-docx` |
| `generate_xlsx(rows) → path` | Stretch: tabular deliverable | `openpyxl` |

Tools are annotated read-only or approval is disabled per server, so nothing pauses.

### 4.5 Sandbox (TrueForge's, local)

Not Docker and not the cloud Daytona provider the docs describe. In `STANDALONE` mode
TrueForge spawns a **bubblewrap**-isolated subprocess on Laptop B via `@anthropic-ai/sandbox-
runtime`. Nothing to run; it is provisioned on demand the first time the Doc Agent needs it.

Hard prerequisites on Laptop B (Linux): `bwrap`, `socat`, `rg`. First init pip-installs
`pydantic` from PyPI and its egress allowlist is PyPI + GitHub only — **must be warmed up
online**. Anything the agent's code will import (`openpyxl`, `pandas`) must be installed in
the same online window.

### 4.6 Skill: `scan-to-approval-note`

A skill is a **git repository** cloned into the sandbox at `/opt/tfy/skills/{name}`; it needs
`config.sandbox.enabled: true`. Ours lives in a local repo on Laptop B and is never fetched
from GitHub. Attached to the Doc Agent only.

It carries what the writer model is most likely to get wrong: the approval-note structure,
mandatory fields (asset ID, inspector, date, findings, risk rating, corrective actions,
sign-off block), and the formal tone. The procedure itself is short:

1. Read the extracted findings and injected context.
2. Draft the note in the mandated structure.
3. Call `generate_docx`.
4. Return the path and a one-line summary.

---

## 5. File handling

TrueForge fans attachments out three ways, and only one reaches Ollama intact — which is why
the dispatcher normalizes everything first.

```
  attachment
      │
      ├─ image/*  ──────────▶ inline `image_url` ──▶ vision model sees pixels     ✅
      │
      ├─ application/pdf ───▶ inline OpenAI `file` part ──▶ Ollama rejects it    ✗
      │                        dispatcher rasterizes to PNG first
      │
      └─ anything else ─────▶ uploaded into the sandbox; model gets only a stub  ⚠
         .xlsx .csv .docx      "[file_1] filename … path … mime … size …"
                               and must write code to read it.
                               No sandbox → AgentSandboxRequiredError.
                               dispatcher converts to text first, so this path
                               is never exercised in the demo.
```

Generated files: `generate_docx` writes to `output/` on Laptop B and returns the path. The
dispatcher's page links it directly. If the bundled UI is used instead, TrueForge's turn
download endpoint serves sandbox-produced files.

---

## 6. User flows

Legend: `op` operator · `D` dispatcher · `VA` Vision Agent · `DA` Doc Agent · `T` MCP tools ·
`SB` sandbox · `OL` Ollama on Laptop A. Every `VA`/`DA` step is one or more `OL` calls over
the cable.

### Flow 1 — Text-only query

```
  op ──"what's the max allowable pressure for V-102?"──▶ D
                                                          │ classify: text → Doc Agent
                                                          │ context:  "SOP-114 …"
                                                          │ inline spec, instructions+ctx
                                                          ▼
                                                         DA ──▶ OL ──▶ answer
  op ◀── answer + [Routed to: Doc Agent (qwen3:8b)] ◀──── D
```
*Validates:* dispatcher, context injection, agent call — in isolation.

### Flow 2 — Scan or image → extraction

```
  op ──scan.pdf──▶ D
                   │ normalize: pdf → page PNGs
                   │ classify:  image → Vision Agent
                   ▼
                  VA ──▶ OL (image_url) ──▶ extracted findings (markdown)
                   │  optionally: VA calls T.extract_from_scan for exact-character OCR
  op ◀── findings + [Routed to: Vision Agent (qwen2.5vl:7b)] ◀── D
```
*Validates:* multimodal input, correct agent selection by file type.

### Flow 3 — HERO: scan → approval note (.docx)

```
  op ──scan.pdf + "draft the approval note"──▶ D
                                                │ normalize → PNG
                                                │ classify → needs both
      ┌─────────────────────────────────────────┘
      │  STAGE A (read)
      ▼
     VA ──▶ OL ──▶ raw findings ──────────────┐
                                              │  D carries text across
      ┌───────────────────────────────────────┘
      │  context: "SOP-114 …"
      │  STAGE B (write)
      ▼
     DA ──loads skill scan-to-approval-note──▶ SB
     DA ──drafts note──▶ OL
     DA ──generate_docx(...)──▶ T ──▶ output/approval-note-V102.docx
      │
  op ◀── summary + download link
         + [Routed to: Vision Agent (qwen2.5vl:7b) → Doc Agent (qwen3:8b)]
```
The two-stage chain is a **design choice for reliability**, not a constraint: both models can
call tools, so if the chain misbehaves the Vision Agent can complete the flow alone as a
fallback. Chaining stays primary because two short single-purpose turns beat one long
cross-modal one on 7–8B models.

### Flow 4 — Visible routing (display requirement)

Every response carries the banner. For chained flows it shows both hops with an arrow. This
is rendered by the dispatcher's page — the reason the dispatcher owns the client surface.

### Flow 5 — Failure handling

```
  op ──prompt──▶ D ──▶ DA ──▶ OL ✗ (Laptop A unplugged / timeout)
                       │
                       └─ TrueForge surfaces the error on the turn stream
  op ◀── "Model server unreachable (laptop-a:11434). Nothing was lost;
          retry when the link is back." ◀── D   (bounded timeout, no hang)
```
The dispatcher wraps every SDK call in a timeout and maps errors to one plain sentence.

### Flow 6 — Coding request → sandbox

```
  op ──"write a script to compute flow rate from these readings and run it"──▶ D
                                                          │ classify: text, code intent
                                                          ▼
                                                         DA ──writes script──▶ OL
                                                         DA ──executes──▶ SB ──▶ stdout
  op ◀── code + result + [Routed to: Doc Agent (qwen3:8b)] ◀── D
```
Constraint: offline, the sandbox cannot `pip install`. Generated code must use the standard
library or what was preinstalled during warm-up.

### Flow 7 — Multi-turn refinement

```
  op ──"make the tone more formal, add a corrective-actions section"──▶ D
                                                          │ same session id → no re-routing
                                                          ▼
                                                         DA (context retained by TrueForge)
                                                         DA ──generate_docx──▶ T ──▶ new .docx
  op ◀── updated link ◀── D
```
Rides on TrueForge's session and compaction handling. Must be tested, not assumed.

### Extra flows (only if time remains)

- **Network isolation proof** — `tcpdump -i <eth> not host <laptop-a>` on a visible terminal
  shows zero packets for the whole demo. Cut first if short on time.
- **Image + code combo** — photo of handwritten readings → VA digitizes → DA scripts → SB runs.
- **Mixed PDFs** — "if extracted text < N chars, treat as scanned." Not demoed live.

---

## 7. Setup order

### Laptop A — while online

```bash
export OLLAMA_HOST=0.0.0.0:11434          # default binds localhost; B could not reach it
export OLLAMA_KEEP_ALIVE=-1               # never unload — a reload mid-demo is a 20 s freeze
export OLLAMA_MAX_LOADED_MODELS=2
ollama serve

ollama pull qwen2.5vl:7b
ollama pull qwen3:8b
ollama create vision-model -f Modelfile.vision
ollama create doc-model    -f Modelfile.doc

ollama show vision-model | grep -i capabilities     # expect: vision, tools
ollama show doc-model    | grep -i capabilities     # expect: tools
```

### Laptop B — while online

```bash
sudo apt install -y bubblewrap socat ripgrep tesseract-ocr poppler-utils
bwrap --dev-bind / / true && echo SANDBOX_OK       # if this fails, the sandbox never will work

npx @truefoundry/trueforge@latest                  # log must say: Local sandbox fallback is available
```

Then in TrueForge at `http://localhost:8790`:

1. Settings → Models → **custom** provider `ollama`, base URL `http://<laptop-a>:11434/v1`,
   models `vision-model` and `doc-model`.
2. Settings → Connectors → add `sovereign-tools` at `http://127.0.0.1:9000/mcp`.
3. Settings → Skills → add the local repo path for `scan-to-approval-note`.
4. Create both agents per §4.3.
5. **Warm the sandbox**: send the Doc Agent "run a python script that prints 2+2". Then
   `pip install openpyxl pandas` inside it.
6. Verify from B: `curl http://<laptop-a>:11434/v1/models`.

### Unplug, then

7. Run the full demo script (§8) with the WAN physically disconnected. Anything that breaks
   here is a missing step above.

---

## 8. Demo script / acceptance

- [ ] Text prompt → Doc Agent banner → context-aware answer *(Flow 1)*
- [ ] Scan upload → Vision Agent banner → findings extracted correctly *(Flow 2)*
- [ ] Same scan → `.docx` approval note downloadable and correctly formatted *(Flow 3)*
- [ ] Follow-up tone/content change updates the document in the same session *(Flow 7)*
- [ ] Coding request generated and executed in the sandbox *(Flow 6)*
- [ ] Laptop A unplugged → clean error, no hang, no crash *(Flow 5)*
- [ ] **Entire script above runs with no internet on either machine**
- [ ] *(stretch)* Live packet capture shows zero external destinations throughout

---

## 9. Risks and mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Sandbox bootstrap needs PyPI exactly once | **Highest** | Warm-up in §7 step 5, before unplugging. No recovery path if skipped. |
| VRAM: both models ≈ 11 GB; under 16 GB they thrash | High | Check Laptop A's VRAM now; `KEEP_ALIVE=-1`; pre-warm before each segment. |
| Vision model tool calls degrade once an image is in context | High | Two-stage chain is primary; vision-side tools are fallback only. Test image + tool in one turn early. |
| Harness defaults (subagents, gen-UI, questions) bloat a small model's prompt | High | All three off on both agents. |
| Default approval gating pauses `generate_docx` | Medium | `require_approval_for_tools: []` or read-only annotations. |
| Skills need a git repo *and* a sandbox | Medium | Local repo; sandbox on Doc Agent; verify offline clone. |
| Scanned PDFs rejected by Ollama as `file` parts | Medium | Dispatcher rasterizes to PNG. Keep a PNG sample as the primary demo input. |
| Ollama default context truncates prompts | Medium | Modelfiles with `num_ctx` (§2). |
| Two-laptop link fails | Medium | Direct cable; tested single-laptop fallback with both models on B. |
| Shallow context injection (not RAG) | Low | State it as a deliberate scope decision when asked. |
| TrueForge docs contradict its code | Low | Trust `packages/`, not `docs/`. |

---

## 10. Open decisions

- **Writer size** — `qwen3:8b` vs `qwen3:14b`, decided by Laptop A's VRAM.
- **Vision-side tool use** — enable on the Vision Agent as a fallback, or keep it a pure
  extractor. Decide after the image-plus-tool test.
- **`generate_xlsx`** — stretch; only if Flows 1–7 are solid.
- **Network proof capture** — stretch; nice supporting evidence, not required for the core
  criteria.
