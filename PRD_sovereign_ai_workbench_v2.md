# PRD v3: Sovereign On-Premise Agentic AI Workbench (Hackathon Build)

Companion: `ARCHITECTURE_sovereign_ai_workbench.md` — full diagrams, per-flow sequences, and setup detail. This PRD is scope, decisions, and acceptance; that document is how the pieces fit.

## 1. Problem & Goal

Build a demo of a fully offline, on-premise AI workbench for confidential industrial work (refinery/PSU context). Nothing may call the public internet. The system must demonstrate:
- Automatic selection between 2 local open-weight models based on task/input type
- A full agentic pipeline: read a scanned document → produce a real output file
- Proof, via visible network monitoring, that zero external calls occur at any point

Reading and creating documents — scans, photos, spreadsheets, Word files — is the primary capability. Code execution is a supporting demo, not the centre.

**Time budget:** 5 hours. **Foundation:** TrueForge (https://github.com/truefoundry/trueforge), an open-source agent harness. We build the thinnest possible layer on top of it — everything TrueForge already does, we use as-is.

## 2. What TrueForge Gives Us For Free (do not rebuild)

- **Agent execution loop** — planning, multi-step tool use, iteration until task completion
- **Sessions & turns** — persisted conversation state (SQLite in local/`STANDALONE` mode; no Postgres or Redis needed)
- **Context-window compaction** — automatically summarizes older turns as context fills up, model-aware
- **Sandbox-as-a-tool** — isolated code execution, provisioned on demand. In local mode this is a **host-local sandbox** built on Anthropic's `sandbox-runtime` (bubblewrap), *not* the cloud Daytona provider the docs describe. On Linux it needs `bwrap`, `socat`, and `rg` on the host.
- **MCP tool integration** — the standard way to plug in new capabilities. **Transport is remote HTTP only** (Streamable HTTP, or legacy SSE) — no stdio, so our tool server is an HTTP service.
- **Skills** — `SKILL.md` instruction packs loaded on demand. A skill is a **git repository** cloned into the sandbox, so skills require the sandbox to be enabled.
- **Bundled chat UI + HTTP API + TypeScript SDK**
- **Multimodal turn input** — user messages accept file parts as `data:` URIs; `image/*` is forwarded inline to the model as `image_url`

**What TrueForge does NOT give us:**
1. **A single agent that switches models by input type.** Each agent binds exactly **one** model. There is no content-based router (the docs list it as *planned*) — this is the one orchestration piece we build.
2. **Instruction templating.** The agent spec has no `{{variable}}` placeholders and no `variables` field. Per-session context is injected by our dispatcher instead — see §3.
3. **Any concept of a file at the model.** The models receive text and images only. Every other upload TrueForge either sends in a shape Ollama rejects (PDF) or drops into the sandbox as a filename stub the model must write code to read. Our dispatcher converts everything to text or PNG before TrueForge sees it.

## 3. Architecture

```
╔══════════════════════════╗        ╔════════════════════════════════════════════════╗
║ LAPTOP A — MODEL SERVER  ║        ║ LAPTOP B — ORCHESTRATOR  (identical on C, D …) ║
║                          ║        ║                                                ║
║  Ollama  0.0.0.0:11434   ║        ║  browser ─▶ DISPATCHER :8080 (ours)            ║
║   vision-model           ║        ║               normalize · classify · context   ║
║    = qwen2.5vl:7b        ║        ║               chain · inline spec · banner     ║
║    vision ✅  tools ✅   ║        ║                    │ TrueForge SDK             ║
║   doc-model              ║        ║             TRUEFORGE :8790 (upstream, as-is)  ║
║    = qwen3:8b            ║        ║              Vision Agent    Doc Agent         ║
║    vision ✗   tools ✅   ║  LAN   ║              vision-model    doc-model         ║
║                          ║  only  ║                    │ MCP/HTTP     │ exec       ║
║  OpenAI-compatible /v1 ◀─╫────────╫──────────────  MCP TOOLS :9000   SANDBOX       ║
║                          ║        ║              extract_from_scan   bubblewrap    ║
║  nothing else runs here  ║        ║              generate_docx       skills/ (git) ║
╚══════════════════════════╝        ╚════════════════════════════════════════════════╝
```

- **Laptop A runs Ollama and nothing else.** The only cross-machine traffic is `POST /v1/chat/completions`. Tool calls, sandbox execution, file I/O, and session state are all localhost on the client laptop.
- **Models.** `qwen2.5vl:7b` is the *reader* (document-trained vision, supports tools). `qwen3:8b` is the *writer* (general instruct, formal prose, strong tool calling). Both are registered under Ollama aliases `vision-model` / `doc-model` via Modelfiles that raise `num_ctx` (Ollama's default of a few thousand tokens silently truncates system prompt plus tool schemas). ~11 GB VRAM to keep both resident. If Laptop A has 24 GB+, upgrade the writer to `qwen3:14b`.
  - *Why not the original `qwen2.5-coder:7b` + `llama3.2-vision:11b`:* llama3.2-vision cannot call tools and is weak on dense document OCR — the two things the hero flow needs most; a coder-tuned writer produces terse, code-styled prose on the demo's most visible output.
- **Ollama is a `custom` model provider** in TrueForge — any OpenAI-compatible base URL plus an explicit model list. No wrapper API.
- **Two TrueForge agents.** "Vision Agent" → `vision-model`, "Doc Agent" → `doc-model`. Per-agent configuration is deliberate, not default:

  | Setting | Vision Agent | Doc Agent | Why |
  | --- | --- | --- | --- |
  | MCP servers | `sovereign-tools` (fallback) | `sovereign-tools` | Doc Agent drives the tools |
  | skills | none | `scan-to-approval-note` | procedure only matters where tools are called |
  | `config.sandbox.enabled` | `false` | `true` | skills + Flow 6 need it |
  | `dynamic_sub_agents`, `generative_ui`, `ask_user_questions` | `false` | `false` | on by default; each appends prompt + schema weight a 7–8B model can't afford; a paused question looks like a hang |
  | `mcp_servers[].preload` | — | `true` | three tools; skip discovery |
  | `require_approval_for_tools` | — | `[]` | default `["@write","@destructive"]` pauses for Allow/Deny mid-demo |
  | `iteration_limit` | `3` | `10` | fail fast |

- **Dispatcher = our router**, in front of TrueForge. Deterministic code, no LLM in the loop. Per request:
  1. **Normalize** — every attachment becomes text or PNG: images pass through; PDFs are rasterized (scanned) or text-extracted (digital); `.xlsx`/`.csv` → markdown table via `openpyxl`; `.docx` → text via `python-docx`. Large tables are capped (first N rows plus a shape line); multi-page PDFs are capped per turn.
  2. **Classify** — image present → Vision Agent first; text only → Doc Agent; code intent → Doc Agent with sandbox.
  3. **Resolve context** — keyword lookup against a small local set of SOP/manual files → short string. Explicitly NOT RAG.
  4. **Chain** — for anything needing both models, run the Vision Agent, carry its text into the Doc Agent's prompt.
  5. **Open session** — `sessions.create({ agent: { spec } })` with the agent passed **inline**; `instructions` composed here (base + context) because the spec has no templating. Saved agents remain the canonical definitions; the dispatcher clones and fills in.
  6. **Banner** — "Routed to: Vision Agent (qwen2.5vl:7b) → Doc Agent (qwen3:8b)".
- **Client access path.** The dispatcher serves its own minimal upload-plus-chat page. TrueForge's bundled UI posts straight to TrueForge's API with a user-picked agent, bypassing the router — which would delete automatic routing, a must-demo criterion. Reverse-proxying the bundled UI (intercepting session-create, passing SSE streams through) is possible but too risky for the time budget. The bundled UI stays available as a manual-pick fallback.
- **Custom MCP tool server** — an **HTTP** MCP server (FastMCP `streamable-http`) on `127.0.0.1:9000`, registered under Settings → Connectors as `sovereign-tools`:
  - `extract_from_scan(image_path) -> text` — Tesseract OCR; complements the vision model's read with exact characters
  - `generate_docx(title, sections, template=None) -> path` — `python-docx`, writes to `output/` on the host (not inside the sandbox)
  - (stretch) `generate_xlsx(rows) -> path` — `openpyxl`
  - Tools are annotated read-only or approval is disabled per server so nothing pauses.
- **Skill** `scan-to-approval-note` — on the Doc Agent only. Carries the approval-note structure, mandatory fields (asset ID, inspector, date, findings, risk rating, corrective actions, sign-off), and formal tone — exactly what the writer model is most likely to get wrong. Lives in a **local git repo on Laptop B**; the sandbox clones it from there, never from GitHub.
- **Sandbox** — TrueForge's local sandbox, on the Doc Agent only, for exactly two jobs: Flow 6 code execution, and hosting the skill. Not used for reading uploads. First init pip-installs `pydantic` from PyPI, so it is **warmed up while still online** (§8).
- **Multi-turn / follow-ups** — TrueForge's session and compaction handling; no custom state code.

## 4. Must-Build Flows

**Flow 1 — Text-only query → Doc Agent**
Prompt in, no file → dispatcher resolves context → inline-spec session on the Doc Agent with context in `instructions` → text response.
*Purpose:* validates dispatcher + context injection + agent call, in isolation.

**Flow 2 — Scan/image upload → Vision Agent extraction**
Image or scanned PDF in → dispatcher normalizes (PDF → PNG) → classifies by file type → session on Vision Agent → extracted text/findings returned. Optionally the Vision Agent calls `extract_from_scan` for exact-character OCR alongside its own read.
*Purpose:* validates multimodal input and correct agent selection — one of the two explicit "must demo" criteria.

**Flow 3 — Scan → extraction → document generation (HERO FLOW)**
Two stages, orchestrated by the dispatcher:
- *Stage A (read):* Vision Agent transcribes the scan → raw findings as text.
- *Stage B (write):* dispatcher resolves context and opens a Doc Agent session with findings + context → Doc Agent loads the skill, drafts the approval note, calls `generate_docx` → `.docx` path returned.
The chain is a **reliability choice, not a constraint**: both models support tools, so if the chain misbehaves the Vision Agent can complete the flow alone as a fallback. Chaining stays primary because two short single-purpose turns beat one long cross-modal turn on 7–8B models.
*Purpose:* the headline demo — agentic, multimodal, real output.

**Flow 4 — Visible agent/model selection**
A **display requirement**, rendered by the dispatcher's page. Every response carries the banner; chained flows show both hops with an arrow. Must be demonstrable across at least the two task types above.

**Flow 5 — Error/failure handling**
Laptop A unreachable or model call times out → dispatcher's bounded timeout catches it → one plain sentence to the user ("Model server unreachable at laptop-a:11434. Nothing was lost; retry when the link is back."), no hang, no crash.

**Flow 6 — Coding request → TrueForge sandbox**
Prompt asks for code to be written and run → Doc Agent generates the script → TrueForge's local sandbox executes it → result returned.
*Purpose:* near-free since the sandbox already exists. Constraint: offline, the sandbox cannot `pip install`; generated code must use the standard library or what was preinstalled during warm-up.

**Flow 7 — Multi-turn refinement**
Follow-up turn in the same session ("make the tone more formal," "add a corrective-actions section") → same session id, no re-routing → TrueForge retains context → Doc Agent regenerates → `generate_docx` produces the updated file.
*Purpose:* "iterate on a task." Rides on TrueForge's session handling — must be tested, not assumed.

## 5. Extra Flows (only if time remains)

- **Network isolation proof (continuous, passive)**: `tcpdump -i <eth> not host <laptop-a>` on a visible terminal shows zero packets for the whole demo. Supporting evidence, not core — cut first.
- **Image + code combo**: photo of handwritten readings → Vision Agent digitizes → Doc Agent scripts → sandbox runs. Attempt only after core flows are solid.
- **Mixed/ambiguous PDFs**: "if extracted text length < N chars, treat as scanned." Not demoed live.

## 6. Explicit Non-Goals
- No custom agent-loop, planning, or delegation logic — TrueForge provides this
- No custom session or context-window/compaction management — TrueForge provides this
- No reverse-proxying of TrueForge's bundled UI — the dispatcher serves its own minimal page; the bundled UI is a manual-pick fallback only
- No full RAG / vector DB / embeddings — keyword context injection is a deliberate scope decision
- No custom sandbox — TrueForge's local sandbox as-is
- No file reading via the sandbox — the dispatcher converts uploads to text/PNG up front
- No content-based model router inside TrueForge — it doesn't exist; our dispatcher fills this gap and nothing more
- No wrapper API around Ollama — it is a `custom` provider
- **No forking of TrueForge internals.** `packages/` is untouched. Every integration goes through a public seam: HTTP API/SDK, MCP, skills, agent spec. If something looks like it needs an upstream patch, change our design instead.

## 7. Tech Stack
- **Agent harness:** TrueForge (`npx @truefoundry/trueforge@latest`, `STANDALONE` mode, SQLite, port 8790). Needs Node ≥ 22.14.
- **Models (Laptop A, via Ollama):**
  - `qwen2.5vl:7b` → alias `vision-model` (`num_ctx 16384`) — Vision Agent
  - `qwen3:8b` → alias `doc-model` (`num_ctx 32768`) — Doc Agent; `qwen3:14b` if VRAM ≥ 24 GB
  - Ollama env: `OLLAMA_HOST=0.0.0.0:11434`, `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_MAX_LOADED_MODELS=2`
  - Registered in TrueForge as one `custom` provider (base URL = Laptop A's `/v1`, both aliases listed)
- **Custom pieces we write** (all under a top-level `sovereign/` directory, outside the pnpm workspace):
  - Dispatcher — file normalization, classification, context lookup, Vision→Doc chaining, inline-spec session calls via the TrueForge SDK, thin upload/chat page, routing banner
  - MCP tool server over **HTTP** (FastMCP `streamable-http`): `extract_from_scan`, `generate_docx`, (stretch) `generate_xlsx`
  - One `SKILL.md` (`scan-to-approval-note`) in a local git repo
  - `context/` — a handful of sample SOP/manual files for keyword lookup
- **File conversion (dispatcher):** `pdf2image`/`pypdfium2` + `poppler-utils` (PDF → PNG), `pypdf` (digital PDF text), `openpyxl` (xlsx), `python-docx` (docx read and write)
- **OCR:** `pytesseract` + `tesseract-ocr`
- **Sandbox host deps (Laptop B, Linux):** `bubblewrap`, `socat`, `ripgrep`
- **Networking:** direct Ethernet between the laptops, no WAN-capable device in path
- **Network proof tooling:** `tcpdump` or OS-native monitor

## 8. Build Order (fits 5-hour window)

**Laptop A — while online**
1. Ollama with `OLLAMA_HOST=0.0.0.0:11434`, `KEEP_ALIVE=-1`, `MAX_LOADED_MODELS=2`; pull both models; create `vision-model` / `doc-model` from Modelfiles; `ollama show` both and confirm `vision`/`tools` capabilities. Confirm image input works over `/v1` from Laptop B (`curl http://<A>:11434/v1/models` first). — 30 min

**Laptop B — while online**
2. `apt install bubblewrap socat ripgrep tesseract-ocr poppler-utils`; `bwrap --dev-bind / / true` must succeed; Node 22; `npx @truefoundry/trueforge@latest` and confirm the log line `Local sandbox fallback is available`. — 20 min
3. In TrueForge: register Ollama as `custom` provider; define both agents per the §3 table (sandbox on Doc only, capabilities off, preload on, approval off). — 20 min
4. Build the MCP tool server (`extract_from_scan`, `generate_docx`) as an HTTP MCP service; register as `sovereign-tools`; attach to both agents. — 75 min
5. Write `SKILL.md` in the local git repo; register and attach to the Doc Agent. — 20 min
6. **Warm the sandbox**: send the Doc Agent "run a python script that prints 2+2"; then `pip install openpyxl pandas` inside it. Verify the skill clones offline (disconnect briefly and re-trigger). — 15 min
7. Build the dispatcher: normalization → classification → context → chain → inline-spec session calls → thin page + banner. — 60 min
8. Wire and test Flows 1 → 2 → 3 end-to-end. — 30 min
9. Error handling (Flow 5) + banner polish (Flow 4). — 15 min
10. Flow 6 through the sandbox; Flow 7 multi-turn. — 20 min

**Unplug**
11. Disconnect WAN on both machines and run the full §9 script. Anything that breaks here is a missing step above. — 20 min
12. If time remains: network-proof capture through a full pass. — 15 min
13. Buffer for breakage / stretch flows. — remainder

## 9. Acceptance Criteria (demo script)
- [ ] Text-only prompt → Doc Agent visibly selected → coherent, context-aware answer
- [ ] Scanned inspection-style report uploaded → Vision Agent visibly selected → key findings extracted correctly
- [ ] Same scan → full pipeline produces a downloadable, correctly formatted `.docx` approval note
- [ ] Follow-up turn requesting a tone/content change updates the document correctly within the same session
- [ ] A coding request is generated and executed successfully in TrueForge's sandbox
- [ ] Simulated server disconnect produces a clean error message, not a crash/hang
- [ ] **The entire script above runs with both machines physically disconnected from the internet**
- [ ] (Stretch) Network capture, visible throughout, shows zero external (non-LAN) destinations across the entire demo

## 10. Known Risks
- **Sandbox bootstrap needs the internet exactly once.** First init pip-installs `pydantic`; the egress allowlist is PyPI + GitHub only. Skip the §8 step-6 warm-up and skills plus Flow 6 die at demo time with no recovery path. Highest severity.
- **VRAM.** Both models resident ≈ 11 GB. Under 16 GB they evict each other on every Vision→Doc handoff — a 15–30 s freeze that looks like a crash. Check Laptop A's VRAM now; `KEEP_ALIVE=-1`; pre-warm before each demo segment.
- **Vision-side tool calls may degrade once an image is in context.** The two-stage chain is primary and vision-side tools are fallback only. Test one image plus one tool call in a single turn early.
- **Harness defaults bloat a small model's prompt.** Subagents, generative UI, and clarifying questions are on by default and each adds guidance plus tool schemas. All three off on both agents.
- **Default approval gating pauses `generate_docx`** behind an Allow/Deny prompt. Set `require_approval_for_tools: []` or annotate read-only.
- **Skills need a git repo and a sandbox.** The skill is cloned, not read from disk; the agent must have `config.sandbox.enabled: true`. Test the offline clone explicitly.
- **Scanned PDFs are rejected by Ollama** — TrueForge sends them as an OpenAI `file` part. Dispatcher rasterizes to PNG; keep a PNG sample as the primary demo input regardless.
- **Ollama's default context window truncates prompts** silently. Modelfiles with `num_ctx` are mandatory, not optional.
- **Two-laptop link is a single point of failure** — direct cable plus a tested single-laptop fallback with both models on Laptop B.
- **Context injection is intentionally shallow (not RAG)** — state it as a scoping decision when asked.
- **TrueForge's docs lag its code** (sandbox providers, instruction variables, file handling). Verify against `packages/`, not `docs/`.
