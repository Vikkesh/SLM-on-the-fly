<p align="center"><img src="sovereign/dispatcher/static/logo.png" width="104" alt="SAI"></p>

<h1 align="center">SAI — Sovereign Agentic Intelligence</h1>

<p align="center">
  <img alt="offline" src="https://img.shields.io/badge/network-air--gapped-3ee6dc?style=for-the-badge&labelColor=161a1c">
  <img alt="models" src="https://img.shields.io/badge/models-qwen3%3A8b%20%2B%20qwen2.5vl%3A7b-ef5fa3?style=for-the-badge&labelColor=161a1c">
  <img alt="outputs" src="https://img.shields.io/badge/outputs-docx%20%C2%B7%20pdf%20%C2%B7%20xlsx-5ad38f?style=for-the-badge&labelColor=161a1c">
  <img alt="stack" src="https://img.shields.io/badge/python%203.12%20%C2%B7%20node%2022-f2b544?style=for-the-badge&labelColor=161a1c">
</p>

<p align="center">An on-premise, air-gapped AI workbench for confidential industrial documents.<br>
Reads scans, photos and spreadsheets. Writes approval notes as Word, PDF or Excel. Nothing leaves the building.</p>

## Purpose

Refineries and public-sector plants produce inspection reports, permits and readings that cannot be
sent to a cloud model. SAI runs two open-weight models on one laptop and an agentic pipeline on the
operator's laptop, so an engineer can drop in a scanned inspection report and get back a signed-off
approval note, with every byte staying on the LAN.

| | |
|---|---|
| **Automatic routing** | Each request goes to the model suited to it — a *reader* for images, a *writer* for text and documents — and the route is shown on every answer, with timings. |
| **Real deliverables** | `.docx`, `.pdf` and `.xlsx` files produced by tools, not text pasted into a chat. |
| **Provably offline** | The only network traffic is model inference to the server laptop. Tools, files and sessions never leave the operator's machine. |

## Architecture

```mermaid
flowchart LR
  classDef server fill:#1e2427,stroke:#3ee6dc,color:#eef2f3,stroke-width:2px
  classDef reader fill:#0f3a38,stroke:#3ee6dc,color:#eef2f3
  classDef writer fill:#3a1630,stroke:#ef5fa3,color:#eef2f3
  classDef ours   fill:#262d31,stroke:#f2b544,color:#eef2f3
  classDef engine fill:#262d31,stroke:#93a0a6,color:#eef2f3
  classDef out    fill:#0f3320,stroke:#5ad38f,color:#eef2f3
  classDef user   fill:#161a1c,stroke:#93a0a6,color:#eef2f3

  subgraph A["🖥  Model server — laptop A"]
    direction TB
    OL["Ollama · OpenAI-compatible /v1"]:::server
    R["qwen2.5vl:7b<br/>reader · vision"]:::reader
    W["qwen3:8b<br/>writer · tools"]:::writer
    OL --- R
    OL --- W
  end

  subgraph B["💻  Operator — laptop B (one per user)"]
    direction TB
    U(["operator's browser"]):::user
    D["SAI dispatcher :8080<br/>normalize files · route · add context · stream"]:::ours
    E["agent engine :8790<br/>sessions · tool calling"]:::engine
    T["document tools :9000<br/>OCR · Word · PDF · Excel"]:::ours
    O[("output/<br/>generated documents")]:::out
    U -->|prompt + files| D
    D -->|writer turn| E
    E -->|tool calls| T
    T --> O
    D -.->|download link| U
  end

  D ==>|"read: image → text"| OL
  E ==>|"write: text → text + tool calls"| OL
  linkStyle 6,7 stroke:#3ee6dc,stroke-width:3px
```

The two thick links are the **only** traffic that crosses the cable. Everything else is localhost on
the operator's laptop.
## Demo
![](https://github.com/Vikkesh/SLM-on-the-fly/blob/main/export-v103-b3f7-ezgif.com-speed.gif)

## How a request moves

```mermaid
sequenceDiagram
  autonumber
  participant U as Operator
  participant D as SAI dispatcher
  participant R as Reader (qwen2.5vl)
  participant W as Writer (qwen3)
  participant T as Document tools
  U->>D: scan.pdf + "draft the approval note"
  D->>D: pdf → png · route: image + document request
  D->>R: transcribe the scan
  R-->>D: findings (streamed to the page)
  D->>D: keyword match → SOP-114 excerpt
  D->>W: findings + context + procedure
  W->>T: generate_docx(title, metadata, sections, signoff)
  T-->>W: Saved: output/approval-note.docx
  W-->>D: two-line summary + path (streamed)
  D-->>U: answer · Routed to: Reader → Writer · download
```

## What gets routed where

```mermaid
flowchart TD
  classDef q fill:#262d31,stroke:#93a0a6,color:#eef2f3
  classDef reader fill:#0f3a38,stroke:#3ee6dc,color:#eef2f3
  classDef writer fill:#3a1630,stroke:#ef5fa3,color:#eef2f3
  classDef local fill:#262d31,stroke:#f2b544,color:#eef2f3

  IN["request"]:::q --> IMG{"image or<br/>scanned PDF?"}:::q
  IMG -->|no| TXT["xlsx → table · docx → text<br/>digital pdf → text"]:::local --> WR["Writer"]:::writer
  IMG -->|yes| CAP{"reader model<br/>has vision?"}:::q
  CAP -->|yes| RD["Reader transcribes"]:::reader
  CAP -->|no| OCR["local Tesseract OCR"]:::local
  RD --> DOC{"document<br/>requested?"}:::q
  OCR --> WR
  DOC -->|yes| WR
  DOC -->|no| ANS["findings returned"]:::reader
  WR --> TOOLS["generate_docx · generate_pdf · generate_xlsx"]:::writer
```

## Run it

```bash
cd sovereign
scripts/run_all.sh prepare                                     # once, with internet: node, venv, engine, samples
scripts/run_all.sh start --ollama http://<model-laptop>:11434 --model qwen3:8b --vision-model qwen2.5vl:7b
```

Open **http://127.0.0.1:8080**. The starter actions attach the sample scan and spreadsheet from
`sovereign/samples/`. `restart` reloads after a code change, `status` shows what is up, `stop` shuts down.

## Repository

```
sovereign/                     everything SAI adds
  dispatcher/                    router, file normalization, direct reader, streaming page
  mcp_server/                    extract_from_scan · generate_docx · generate_pdf · generate_xlsx · list_outputs
  skills/                        the approval-note procedure the writer follows
  context/                       SOP and manual excerpts used for context
  scripts/                       prepare / start / restart / stop, model-server setup
ARCHITECTURE_sovereign_ai_workbench.md    full design, per-flow diagrams, setup order
PRD_sovereign_ai_workbench_v2.md          scope, decisions, acceptance criteria
```

The agent engine (sessions, tool calling, sandbox) lives under `packages/` and is used as-is
through its HTTP API; SAI does not modify it.
