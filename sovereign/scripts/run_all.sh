#!/usr/bin/env bash
# One command to bring the whole workbench up on this laptop against a remote Ollama.
#
#   scripts/run_all.sh start  --ollama http://10.165.33.98:11434 [--model TAG] [--vision-model TAG]
#   scripts/run_all.sh status
#   scripts/run_all.sh stop
#
# start: creates the venv if missing, checks node/tesseract/bwrap, detects the model on the
# Ollama endpoint (auto when exactly one is present), launches TrueForge + MCP tools + dispatcher
# in the background with logs under sovereign/logs/, registers provider/tools/agents, and prints
# the test steps. Re-running start is safe: running services are reused, registration is idempotent.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$HERE/logs"; mkdir -p "$LOGS"
PIDS="$LOGS/pids"
TF_PORT="${TF_PORT:-8790}"; MCP_PORT="${MCP_PORT:-9000}"; DISP_PORT="${DISPATCHER_PORT:-8080}"

cmd="${1:-start}"; shift || true
OLLAMA="${OLLAMA_URL:-}"; MODEL="${MODEL:-}"; VMODEL="${VISION_MODEL:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ollama) OLLAMA="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --vision-model) VMODEL="$2"; shift 2;;
    *) echo "unknown arg: $1"; exit 1;;
  esac
done

say()  { printf '\033[1;36m>> %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32m%s\033[0m\n' "$*"; }
warn() { printf '   \033[33m%s\033[0m\n' "$*"; }
die()  { printf '   \033[31m%s\033[0m\n' "$*"; exit 1; }
up()   { curl -sf -m 3 "$1" >/dev/null 2>&1; }
wait_for() { local url=$1 what=$2 n=${3:-60}; for _ in $(seq 1 "$n"); do up "$url" && return 0; sleep 1; done; die "$what did not come up ($url) - see $LOGS"; }
running() { [[ -f "$PIDS" ]] && grep -q "^$1=" "$PIDS" && kill -0 "$(grep "^$1=" "$PIDS" | cut -d= -f2)" 2>/dev/null; }
record()  { touch "$PIDS"; grep -v "^$1=" "$PIDS" > "$PIDS.tmp" || true; echo "$1=$2" >> "$PIDS.tmp"; mv "$PIDS.tmp" "$PIDS"; }

case "$cmd" in
# ------------------------------------------------------------------------------------------------
stop)
  [[ -f "$PIDS" ]] || { echo "nothing recorded"; exit 0; }
  while IFS== read -r name pid; do
    if kill -0 "$pid" 2>/dev/null; then pkill -TERM -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; echo "stopped $name ($pid)"; fi
  done < "$PIDS"
  rm -f "$PIDS"; exit 0;;
# ------------------------------------------------------------------------------------------------
status)
  for s in "trueforge http://127.0.0.1:$TF_PORT/healthz" "mcp http://127.0.0.1:$MCP_PORT/mcp" "dispatcher http://127.0.0.1:$DISP_PORT/api/health"; do
    set -- $s; if up "$2" || { [[ $1 == mcp ]] && curl -s -m 3 -o /dev/null -w '%{http_code}' "$2" | grep -qE '^(405|406|400)$'; }; then ok "$1  up   $2"; else warn "$1  DOWN $2"; fi
  done
  [[ -n "$OLLAMA" ]] && { up "$OLLAMA/v1/models" && ok "ollama  up   $OLLAMA" || warn "ollama  DOWN $OLLAMA"; }
  exit 0;;
# ------------------------------------------------------------------------------------------------
start) ;;
*) echo "usage: $0 start|status|stop [--ollama URL] [--model TAG] [--vision-model TAG]"; exit 1;;
esac

[[ -n "$OLLAMA" ]] || die "pass --ollama http://<model-laptop>:11434 (or set OLLAMA_URL)"
OLLAMA="${OLLAMA%/}"; OLLAMA="${OLLAMA%/v1}"

say "1/7 model server $OLLAMA"
up "$OLLAMA/v1/models" || die "Ollama not reachable at $OLLAMA/v1/models - on that laptop run: OLLAMA_HOST=0.0.0.0:11434 ollama serve"
TAGS=$(curl -s -m 5 "$OLLAMA/api/tags" | python3 -c 'import sys,json;print("\n".join(m["name"] for m in json.load(sys.stdin)["models"]))')
ok "models: $(echo "$TAGS" | tr '\n' ' ')"
if [[ -z "$MODEL" ]]; then
  [[ $(echo "$TAGS" | wc -l) -eq 1 ]] && MODEL="$TAGS" || die "several models present - choose with --model TAG"
fi
echo "$TAGS" | grep -qx "$MODEL" || die "model '$MODEL' is not on the server"
VMODEL="${VMODEL:-$MODEL}"
CAPS=$(curl -s -m 5 "$OLLAMA/api/show" -d "{\"name\":\"$VMODEL\"}" | python3 -c 'import sys,json;print(" ".join(json.load(sys.stdin).get("capabilities") or []))')
ok "doc model:    $MODEL"
if echo "$CAPS" | grep -qw vision; then ok "vision model: $VMODEL (vision + $CAPS)"; VMODE=model
else warn "vision model: $VMODEL has no vision capability ($CAPS) - images will be read with local Tesseract OCR"; VMODE=ocr; fi
echo "$CAPS" | grep -qw tools || warn "'$MODEL' does not advertise tool calling - generate_docx may not be invoked reliably"

say "2/7 host tools"
command -v python3 >/dev/null || die "python3 missing"
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then . "$HOME/.nvm/nvm.sh"; nvm use 22 >/dev/null 2>&1 || nvm use default >/dev/null 2>&1 || true; fi
NODE_MAJOR=$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/'); [[ "${NODE_MAJOR:-0}" -ge 22 ]] && ok "node $(node -v)" || die "node >= 22 required (have $(node -v 2>/dev/null || echo none)); run: nvm install 22"
command -v tesseract >/dev/null && ok "tesseract $(tesseract --version 2>&1 | head -1 | awk '{print $2}')" || warn "tesseract missing (apt install tesseract-ocr) - OCR fallback and extract_from_scan will not work"
command -v bwrap >/dev/null && ok "bwrap present (sandbox available)" || warn "bwrap missing (apt install bubblewrap) - Flow 6 code execution unavailable"

say "3/7 python venv"
[[ -x "$HERE/.venv/bin/python" ]] || { python3 -m venv "$HERE/.venv"; ok "created .venv"; }
"$HERE/.venv/bin/pip" install -q -r "$HERE/requirements.txt" && ok "requirements satisfied"
[[ -f "$HERE/samples/inspection-report-V102.png" ]] || (cd "$HERE" && .venv/bin/python -m scripts.make_sample >/dev/null && ok "samples generated")

say "4/7 TrueForge :$TF_PORT"
if up "http://127.0.0.1:$TF_PORT/healthz"; then ok "already running"
else
  (cd "$HERE" && nohup npx --yes @truefoundry/trueforge@latest > "$LOGS/trueforge.log" 2>&1 & echo $! > "$LOGS/.tf.pid")
  record trueforge "$(cat "$LOGS/.tf.pid")"; warn "starting (first run downloads the package - can take a few minutes) ..."
  wait_for "http://127.0.0.1:$TF_PORT/healthz" "TrueForge" 600
  ok "up"; grep -m1 -o "Local sandbox fallback is [a-z]*" "$LOGS/trueforge.log" | sed 's/^/   /' || true
fi

say "5/7 MCP tools :$MCP_PORT"
if running mcp; then ok "already running"
else
  (cd "$HERE" && nohup .venv/bin/python -m mcp_server.server > "$LOGS/mcp.log" 2>&1 & echo $! > "$LOGS/.mcp.pid")
  record mcp "$(cat "$LOGS/.mcp.pid")"; sleep 2; ok "up (log: logs/mcp.log)"
fi

say "6/7 dispatcher :$DISP_PORT"
if running dispatcher; then ok "already running (restart with: $0 stop && $0 start ...)"
else
  (cd "$HERE" && OLLAMA_URL="$OLLAMA" VISION_MODEL_ID="$VMODEL" DOC_MODEL_ID="$MODEL" VISION_MODE="$VMODE" \
     nohup .venv/bin/python -m dispatcher.app > "$LOGS/dispatcher.log" 2>&1 & echo $! > "$LOGS/.disp.pid")
  record dispatcher "$(cat "$LOGS/.disp.pid")"
  wait_for "http://127.0.0.1:$DISP_PORT/api/health" "dispatcher" 30; ok "up"
fi

say "7/7 registering provider, tools and agents in TrueForge"
(cd "$HERE" && VISION_MODEL_ID="$VMODEL" DOC_MODEL_ID="$MODEL" .venv/bin/python -m scripts.register --ollama "$OLLAMA" --vision-id "$VMODEL" --doc-id "$MODEL") 2>&1 | sed 's/^/   /'

cat <<MSG

$(printf '\033[1;32mReady.\033[0m')  Open  http://127.0.0.1:$DISP_PORT   (TrueForge's own UI: http://127.0.0.1:$TF_PORT)

Test, in this order:
  1. type:   what is the max allowable pressure for V-102?              -> "Routed to: Doc Agent"
  2. attach: samples/inspection-report-V102.png, no text                -> Vision Agent$( [[ $VMODE == ocr ]] && echo " (via OCR)" )
  3. attach the same file + type: draft the approval note               -> a .docx download link
  4. attach: samples/p301-readings.xlsx + type: summarise these against the pump limits

Logs: $LOGS/{trueforge,mcp,dispatcher}.log      Stop everything: $0 stop
MSG
