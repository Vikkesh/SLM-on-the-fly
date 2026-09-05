#!/usr/bin/env bash
# Laptop B - orchestrator. Prints/performs the ONLINE preparation steps. Read before running.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OLLAMA_URL="${1:-}"
[[ -z "$OLLAMA_URL" ]] && { echo "usage: $0 http://10.79.58.149:11434/v1"; exit 1; }

echo ">> 1. system packages (asks for sudo)"
sudo apt-get install -y bubblewrap tesseract-ocr        # sandbox isolation, OCR
echo ">> 2. sandbox prerequisite check"
bwrap --dev-bind / / true && echo "   bwrap OK" || { echo "   bwrap FAILED - sandbox (Flow 6) will be unavailable"; }
for b in socat rg tesseract; do command -v $b >/dev/null && echo "   $b OK" || echo "   $b MISSING"; done

echo ">> 3. node >= 22 for TrueForge"
node -v
echo ">> 4. python venv"
[[ -d "$HERE/.venv" ]] || python3 -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install -q -r "$HERE/requirements.txt"

echo ">> 5. reachability of Laptop A"
curl -sf "$OLLAMA_URL/v1/models" >/dev/null && echo "   Ollama reachable at $OLLAMA_URL" || { echo "   Ollama NOT reachable at $OLLAMA_URL"; exit 1; }

cat <<MSG

Next, in three terminals (all on this laptop):

  1) npx @truefoundry/trueforge@latest            # watch for: Local sandbox fallback is available
  2) $HERE/scripts/run_mcp.sh                     # tool server on 127.0.0.1:9000
  3) OLLAMA_URL=$OLLAMA_URL $HERE/scripts/run_dispatcher.sh

Then register everything (idempotent):
     cd $HERE && .venv/bin/python -m scripts.register --ollama $OLLAMA_URL

Then WARM THE SANDBOX while still online - open http://localhost:8790, pick doc-agent,
send: "run a python script that prints 2+2", then send: "pip install openpyxl pandas".
Only after that, unplug.
MSG
