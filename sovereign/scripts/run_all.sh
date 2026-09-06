#!/usr/bin/env bash
# Workbench bring-up on this laptop, split into an ONLINE phase and an OFFLINE phase so the
# downloads can happen on a good connection and the model-server connection on another.
#
#   scripts/run_all.sh prepare                                   # needs internet, no model server
#   scripts/run_all.sh start --ollama http://<model-laptop>:11434 --model TAG --vision-model TAG
# Personally : scripts/run_all.sh start --ollama http://10.165.33.98:11434 --model qwen3:8b --vision-model qwen2.5vl:7b
                                                                # needs the model server, no internet

#   scripts/run_all.sh restart                                   # after a code change: tools + dispatcher only,
#                                                                # TrueForge keeps running; agents re-registered
#   scripts/run_all.sh status [--ollama URL]
#   scripts/run_all.sh stop
#
# prepare: node 22 (via nvm), python venv + requirements, a local copy of TrueForge under
#          .trueforge/ (so start never calls npx), sample inputs, host-tool checks.
# start:   checks the model server and picks models, launches TrueForge + MCP tools + dispatcher
#          in the background (logs in logs/), registers provider/tools/agents, prints the tests.
#          Re-running is safe: running services are reused, registration is idempotent.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$HERE/logs"; mkdir -p "$LOGS"
PIDS="$LOGS/pids"
ENVF="$LOGS/env"        # model server + model choices from the last start, reused by restart
TF_DIR="$HERE/.trueforge"
TF_BIN="$TF_DIR/node_modules/.bin/trueforge"
TF_PORT="${TF_PORT:-8790}"; MCP_PORT="${MCP_PORT:-9000}"; DISP_PORT="${DISPATCHER_PORT:-8080}"

cmd="${1:-}"; shift || true
OLLAMA="${OLLAMA_URL:-}"; MODEL="${MODEL:-}"; VMODEL="${VISION_MODEL:-}"; VMODE="${VMODE:-}"
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
# Start a service detached: the subshell execs it with all three fds redirected, so $! is the
# service pid and it never holds our stdout (a pipe to `tee`/`sed` would otherwise never close).
launch() { local name=$1; shift; ( cd "$HERE" && exec setsid nohup "$@" > "$LOGS/$name.log" 2>&1 < /dev/null ) & record "$name" $!; }
load_nvm() { if [[ -s "$HOME/.nvm/nvm.sh" ]]; then . "$HOME/.nvm/nvm.sh"; nvm use 22 >/dev/null 2>&1 || nvm use default >/dev/null 2>&1 || true; fi; }
node_major() { node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/'; }

case "$cmd" in
# ================================================================================================
prepare)
  say "1/5 node 22"
  load_nvm
  if [[ "$(node_major)" -lt 22 ]] 2>/dev/null; then
    [[ -s "$HOME/.nvm/nvm.sh" ]] || die "node >= 22 needed and nvm not found - install nvm or node 22 manually"
    nvm install 22 >/dev/null && nvm alias default 22 >/dev/null && load_nvm && ok "installed node $(node -v)"
  else ok "node $(node -v)"; fi

  say "2/5 python venv + requirements"
  command -v python3 >/dev/null || die "python3 missing"
  [[ -x "$HERE/.venv/bin/python" ]] || { python3 -m venv "$HERE/.venv"; ok "created .venv"; }
  "$HERE/.venv/bin/pip" install -q -r "$HERE/requirements.txt" && ok "requirements satisfied ($("$HERE/.venv/bin/python" --version))"

  say "3/5 TrueForge (local copy under .trueforge/, so start never needs npm)"
  mkdir -p "$TF_DIR"; [[ -f "$TF_DIR/package.json" ]] || echo '{"name":"trueforge-local","private":true}' > "$TF_DIR/package.json"
  (cd "$TF_DIR" && npm install --no-audit --no-fund --loglevel=error @truefoundry/trueforge@latest) && ok "installed trueforge $(node -p "require('$TF_DIR/node_modules/@truefoundry/trueforge/package.json').version" 2>/dev/null || echo '?')"
  [[ -x "$TF_BIN" ]] || die "expected $TF_BIN after install"

  say "4/5 sample inputs"
  [[ -f "$HERE/samples/inspection-report-V102.png" ]] && ok "present" || (cd "$HERE" && .venv/bin/python -m scripts.make_sample >/dev/null && ok "generated")

  say "5/5 host tools (warnings only)"
  command -v tesseract >/dev/null && ok "tesseract $(tesseract --version 2>&1 | head -1 | awk '{print $2}')" || warn "tesseract missing:  sudo apt install tesseract-ocr   (needed for OCR fallback / extract_from_scan)"
  command -v bwrap >/dev/null && ok "bwrap present (sandbox available)" || warn "bwrap missing:      sudo apt install bubblewrap     (needed for Flow 6 code execution)"
  command -v socat >/dev/null && command -v rg >/dev/null && ok "socat + rg present" || warn "socat/rg missing:   sudo apt install socat ripgrep   (needed by the sandbox)"

  cat <<MSG

$(printf '\033[1;32mPrepared.\033[0m')  Everything the laptop needs is downloaded. You can switch networks now.
Next (no internet required):
  $0 start --ollama http://<model-laptop>:11434 --model qwen3:8b --vision-model qwen2.5vl:7b
MSG
  exit 0;;
# ================================================================================================
restart)
  [[ -f "$ENVF" ]] || die "nothing to restart from - run start first"
  # shellcheck disable=SC1090
  . "$ENVF"
  for svc in mcp dispatcher; do
    if running "$svc"; then pid=$(grep "^$svc=" "$PIDS" | cut -d= -f2); pkill -TERM -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; fi
  done
  # anything else squatting on our ports (an earlier run without a pids file)
  for port in "$MCP_PORT" "$DISP_PORT"; do for pid in $(ss -ltnp 2>/dev/null | awk -v p=":$port " '$0 ~ p {print $0}' | grep -o 'pid=[0-9]*' | cut -d= -f2); do kill "$pid" 2>/dev/null || true; done; done
  sleep 1
  exec "$0" start --ollama "$OLLAMA" --model "$MODEL" --vision-model "$VMODEL";;
# ================================================================================================
stop)
  [[ -f "$PIDS" ]] || { echo "nothing recorded"; exit 0; }
  while IFS== read -r name pid; do
    if kill -0 "$pid" 2>/dev/null; then kill -TERM -- "-$pid" 2>/dev/null || pkill -TERM -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; echo "stopped $name ($pid)"; fi
  done < "$PIDS"
  rm -f "$PIDS"; exit 0;;
# ================================================================================================
status)
  for s in "trueforge http://127.0.0.1:$TF_PORT/healthz" "mcp http://127.0.0.1:$MCP_PORT/mcp" "dispatcher http://127.0.0.1:$DISP_PORT/api/health"; do
    set -- $s; if up "$2" || { [[ $1 == mcp ]] && curl -s -m 3 -o /dev/null -w '%{http_code}' "$2" | grep -qE '^(405|406|400)$'; }; then ok "$1  up   $2"; else warn "$1  DOWN $2"; fi
  done
  [[ -n "$OLLAMA" ]] && { up "${OLLAMA%/}/v1/models" && ok "ollama  up   $OLLAMA" || warn "ollama  DOWN $OLLAMA"; }
  [[ -x "$TF_BIN" ]] && ok "trueforge prepared ($TF_BIN)" || warn "trueforge not prepared - run: $0 prepare (needs internet)"
  exit 0;;
# ================================================================================================
start) ;;
*) echo "usage: $0 prepare | start --ollama URL --model TAG [--vision-model TAG] | status [--ollama URL] | stop"; exit 1;;
esac

# ---- start ---------------------------------------------------------------------------------------
[[ -n "$OLLAMA" ]] || die "pass --ollama http://<model-laptop>:11434 (or set OLLAMA_URL)"
OLLAMA="${OLLAMA%/}"; OLLAMA="${OLLAMA%/v1}"

say "0/6 prepared?"
load_nvm
[[ "$(node_major)" -ge 22 ]] 2>/dev/null && ok "node $(node -v)" || die "node >= 22 missing - run: $0 prepare (needs internet)"
[[ -x "$HERE/.venv/bin/python" ]] && ok "venv present" || die "venv missing - run: $0 prepare (needs internet)"
[[ -x "$TF_BIN" ]] && ok "trueforge present" || die "TrueForge not downloaded - run: $0 prepare (needs internet)"

say "1/6 model server $OLLAMA"
if up "$OLLAMA/v1/models"; then
  TAGS=$(curl -s -m 5 "$OLLAMA/api/tags" | python3 -c 'import sys,json;print("\n".join(m["name"] for m in json.load(sys.stdin)["models"]))')
  ok "models: $(echo "$TAGS" | tr '\n' ' ')"
  if [[ -z "$MODEL" ]]; then
    [[ $(echo "$TAGS" | wc -l) -eq 1 ]] && MODEL="$TAGS" || die "several models present - choose with --model TAG (writer) and --vision-model TAG (reader)"
  fi
  echo "$TAGS" | grep -qx "$MODEL" || die "model '$MODEL' is not on the server"
  VMODEL="${VMODEL:-$MODEL}"
  echo "$TAGS" | grep -qx "$VMODEL" || die "vision model '$VMODEL' is not on the server"
  caps_of() { curl -s -m 5 "$OLLAMA/api/show" -d "{\"name\":\"$1\"}" | python3 -c 'import sys,json;print(" ".join(json.load(sys.stdin).get("capabilities") or []))'; }
  VCAPS=$(caps_of "$VMODEL"); DCAPS=$(caps_of "$MODEL")
  ok "doc model:    $MODEL ($DCAPS)"
  if echo "$VCAPS" | grep -qw vision; then ok "vision model: $VMODEL ($VCAPS)"; VMODE=model
  else warn "vision model: $VMODEL has no vision capability ($VCAPS) - images will be read with local Tesseract OCR"; VMODE=ocr; fi
  echo "$DCAPS" | grep -qw tools || warn "'$MODEL' does not advertise tool calling - generate_docx may not be invoked reliably"
elif [[ -n "$MODEL" ]]; then
  VMODEL="${VMODEL:-$MODEL}"; VMODE="${VMODE:-model}"
  warn "not reachable right now - starting anyway with $MODEL / $VMODEL (requests will fail cleanly until it is back)"
else
  die "Ollama not reachable at $OLLAMA/v1/models and no --model given - on that laptop run: OLLAMA_HOST=0.0.0.0:11434 ollama serve"
fi
printf 'OLLAMA=%q\nMODEL=%q\nVMODEL=%q\nVMODE=%q\n' "$OLLAMA" "$MODEL" "$VMODEL" "$VMODE" > "$ENVF"

say "2/6 TrueForge :$TF_PORT"
if up "http://127.0.0.1:$TF_PORT/healthz"; then ok "already running"
else
  launch trueforge "$TF_BIN"; warn "starting ..."
  wait_for "http://127.0.0.1:$TF_PORT/healthz" "TrueForge" 120
  ok "up"; grep -m1 -o "Local sandbox fallback is [a-z]*" "$LOGS/trueforge.log" | sed 's/^/   /' || true
fi

say "3/6 MCP tools :$MCP_PORT"
if running mcp; then ok "already running"
else
  launch mcp .venv/bin/python -m mcp_server.server; sleep 2; ok "up (log: logs/mcp.log)"
fi

say "4/6 dispatcher :$DISP_PORT"
if running dispatcher; then ok "already running (restart with: $0 stop && $0 start ...)"
else
  OLLAMA_URL="$OLLAMA" VISION_MODEL_ID="$VMODEL" DOC_MODEL_ID="$MODEL" VISION_MODE="$VMODE" \
    launch dispatcher .venv/bin/python -m dispatcher.app
  wait_for "http://127.0.0.1:$DISP_PORT/api/ping" "dispatcher" 60; ok "up"
fi

say "5/6 registering provider, tools and agents in TrueForge"
(cd "$HERE" && VISION_MODEL_ID="$VMODEL" DOC_MODEL_ID="$MODEL" .venv/bin/python -m scripts.register --ollama "$OLLAMA" --vision-id "$VMODEL" --doc-id "$MODEL") 2>&1 | sed 's/^/   /'

say "6/6 ready"
cat <<MSG
$(printf '\033[1;32mOpen  http://127.0.0.1:%s\033[0m' "$DISP_PORT")   (TrueForge's own UI: http://127.0.0.1:$TF_PORT)

Test, in this order:
  1. type:   what is the max allowable pressure for V-102?              -> "Routed to: Doc Agent"
  2. attach: samples/inspection-report-V102.png, no text                -> Vision Agent$( [[ $VMODE == ocr ]] && echo " (via OCR)" )
  3. attach the same file + type: draft the approval note               -> a .docx download link
  4. attach: samples/p301-readings.xlsx + type: summarise these against the pump limits

Logs: $LOGS/{trueforge,mcp,dispatcher}.log      After a code change: $0 restart      Stop everything: $0 stop
MSG
