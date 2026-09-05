#!/usr/bin/env bash
# Laptop A - model server. Run once while ONLINE; afterwards only `ollama serve` is needed.
set -euo pipefail
cd "$(dirname "$0")"

export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"   # default binds localhost; Laptop B could not reach it
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"   # never unload - a reload mid-demo is a 20 s freeze
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-2}"

if ! pgrep -x ollama >/dev/null; then
  echo ">> starting ollama serve (OLLAMA_HOST=$OLLAMA_HOST)"; nohup ollama serve >/tmp/ollama.log 2>&1 &
  sleep 3
fi

echo ">> pulling base models (needs internet, ~11 GB)"
ollama pull qwen2.5vl:7b
ollama pull qwen3:8b

echo ">> creating aliases with raised context windows"
ollama create vision-model -f Modelfile.vision
ollama create doc-model    -f Modelfile.doc

echo ">> capabilities (expect: vision + tools / tools)"
ollama show vision-model | grep -iA3 capabilities || true
ollama show doc-model    | grep -iA3 capabilities || true

echo ">> pre-warming both models so the first demo turn is not a cold load"
curl -s http://127.0.0.1:11434/api/generate -d '{"model":"doc-model","prompt":"ok","stream":false,"keep_alive":-1}' >/dev/null
curl -s http://127.0.0.1:11434/api/generate -d '{"model":"vision-model","prompt":"ok","stream":false,"keep_alive":-1}' >/dev/null
echo ">> loaded:"; ollama ps
echo
echo "Laptop A ready. From Laptop B verify:  curl http://$(hostname -I | awk '{print $1}'):11434/v1/models"
