#!/usr/bin/env bash
# =============================================================================
# start_openwebui_stack.sh — Run the Gaia + Open WebUI stack locally (no Docker)
#
#   1. Gaia FastAPI backend  → http://localhost:8000   (OpenAI-compatible /v1)
#   2. Open WebUI            → http://localhost:8080
#
# Open WebUI is pre-wired to the backend so every Gaia dataset shows up as a
# selectable model. The Gaia Knowledge Filter (live retrieval into any LLM) is
# installed separately — see openwebui/README.md.
#
# Prereqs (already provisioned in this repo):
#   - examples/02-chat-app/venv        (Python 3.13, backend + gaia_sdk)
#   - examples/02-chat-app/venv-webui  (Python 3.11, open-webui 0.8.x)
#   - examples/02-chat-app/.env        (GAIA_API_KEY, GAIA_BASE_URL, …)
#
# Usage:   ./openwebui/start_openwebui_stack.sh        # Ctrl+C stops both
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
LOG_DIR="$APP_DIR/logs"; mkdir -p "$LOG_DIR"

[ -f .env ] || { echo -e "${RED}Missing .env — copy .env.example and set GAIA_API_KEY${NC}"; exit 1; }
GAIA_API_KEY="$(grep '^GAIA_API_KEY=' .env | cut -d= -f2- || true)"
[ -n "$GAIA_API_KEY" ] || { echo -e "${RED}GAIA_API_KEY not set in .env${NC}"; exit 1; }

cleanup() {
  echo -e "\n${YELLOW}Shutting down…${NC}"
  kill "${BACKEND_PID:-}" "${WEBUI_PID:-}" 2>/dev/null || true
  wait 2>/dev/null || true
  echo -e "${GREEN}Stopped.${NC}"; exit 0
}
trap cleanup SIGINT SIGTERM

# ── 1. Backend ───────────────────────────────────────────────────────────────
echo -e "${GREEN}[1/2] Starting Gaia backend on :8000…${NC}"
"$APP_DIR/venv/bin/python" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
  > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
for i in $(seq 1 30); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs 2>/dev/null)" = "200" ] \
    && { echo -e "      ${GREEN}✓ backend ready${NC}"; break; }
  sleep 1
done

# ── 2. Open WebUI ────────────────────────────────────────────────────────────
echo -e "${GREEN}[2/2] Starting Open WebUI on :8080…${NC}"
export DATA_DIR="$APP_DIR/webui_data"
export OPENAI_API_BASE_URL="http://localhost:8000/v1"   # Gaia datasets → models
export OPENAI_API_KEY="$GAIA_API_KEY"                   # forwarded to the backend
export ENABLE_OLLAMA_API="false"
export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-gaia-openwebui-dev-secret}"
export BYPASS_EMBEDDING_AND_RETRIEVAL="true"            # retrieval is live via Gaia, not local embeddings
export ANONYMIZED_TELEMETRY="false"; export DO_NOT_TRACK="true"; export SCARF_NO_ANALYTICS="true"
"$APP_DIR/venv-webui/bin/open-webui" serve --port 8080 > "$LOG_DIR/openwebui.log" 2>&1 &
WEBUI_PID=$!
for i in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/health 2>/dev/null)" = "200" ] \
    && { echo -e "      ${GREEN}✓ Open WebUI ready${NC}"; break; }
  sleep 2
done

cat <<EOF

╔══════════════════════════════════════════════════════════╗
║  ✅  Gaia + Open WebUI running                            ║
║                                                          ║
║   🤖  Open WebUI    → http://localhost:8080              ║
║   🔧  Backend API   → http://localhost:8000/docs         ║
║                                                          ║
║   Each Gaia dataset appears as a selectable model.       ║
║   Ctrl+C stops both services.                            ║
╚══════════════════════════════════════════════════════════╝
EOF
command -v open >/dev/null 2>&1 && open http://localhost:8080 || true
wait "$BACKEND_PID" "$WEBUI_PID"
