#!/usr/bin/env bash
# =============================================================================
# Gaia Chat App — First-time setup
# Run this once before `docker compose up`.
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }
error() { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ── Check Docker is available ─────────────────────────────────────────────────
info "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || error "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop"
docker info >/dev/null 2>&1     || error "Docker daemon is not running. Please start Docker Desktop."
info "Docker OK"

# ── Check we're in the right directory ───────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Create .env from template if it doesn't exist ────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from .env.example"
    warn ""
    warn "  *** ACTION REQUIRED ***"
    warn "  Open .env and set your GAIA_API_KEY before continuing."
    warn ""
    read -r -p "Press Enter after you have set GAIA_API_KEY in .env... "
fi

# ── Validate that GAIA_API_KEY is not still a placeholder ────────────────────
source .env 2>/dev/null || true
if [[ -z "${GAIA_API_KEY:-}" || "$GAIA_API_KEY" == "your-api-key-here" ]]; then
    error "GAIA_API_KEY is not set in .env. Please edit .env and re-run setup.sh."
fi
info "GAIA_API_KEY looks good"

# ── Create logs directory ─────────────────────────────────────────────────────
mkdir -p logs
info "Logs directory ready"

# ── Pull OpenWebUI image in the background (optional) ────────────────────────
read -r -p "Include OpenWebUI (ChatGPT-style interface) on port 8080? [y/N] " include_owui
COMPOSE_PROFILES=""
if [[ "$include_owui" =~ ^[Yy]$ ]]; then
    COMPOSE_PROFILES="--profile openwebui"
    info "Will start OpenWebUI alongside the Gaia Chat App"
fi

# ── Build and start ───────────────────────────────────────────────────────────
info "Building images (this may take a few minutes on first run)..."
# shellcheck disable=SC2086
docker compose $COMPOSE_PROFILES build

info "Starting services..."
# shellcheck disable=SC2086
docker compose $COMPOSE_PROFILES up -d

# ── Wait for backend health ───────────────────────────────────────────────────
info "Waiting for backend to be ready..."
attempts=0
until docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" 2>/dev/null; do
    attempts=$((attempts + 1))
    if [ $attempts -ge 20 ]; then
        warn "Backend is taking longer than expected. Check logs: docker compose logs backend"
        break
    fi
    sleep 3
done

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Gaia Chat App is running!${NC}"
echo ""
echo -e "  ${GREEN}Gaia Chat App →${NC}  http://localhost:5173"
echo -e "  ${GREEN}Backend API   →${NC}  http://localhost:8000"
if [[ "$include_owui" =~ ^[Yy]$ ]]; then
echo -e "  ${GREEN}OpenWebUI     →${NC}  http://localhost:8080"
fi
echo ""
echo -e "  To stop:  docker compose down"
echo -e "  Logs:     docker compose logs -f"
echo -e "${GREEN}============================================${NC}"
