# Gaia Chat Application

A containerized chat application for querying Cohesity Gaia datasets with intelligent topic discovery.

## Quick Start

```bash
# 1. Run the setup script (one-time)
./setup.sh

# 2. Follow the prompts to configure your API key
# 3. Open your browser to http://localhost:5173
```

## What You Need

- **Docker Desktop** (install from https://www.docker.com/products/docker-desktop)
- **Gaia API Key** (contact your Cohesity administrator)

## Services

| Service | Port | Purpose |
|---------|------|---------|
| **Frontend** | 5173 | Chat interface (React + nginx) |
| **Backend** | 8000 | API (FastAPI + Gaia integration) |
| **OpenWebUI** | 8080 | ChatGPT-style UI (optional — add with `--profile openwebui`) |

## Common Commands

```bash
# Stop services
docker compose down

# View logs
docker compose logs -f

# Restart
docker compose restart

# Start with OpenWebUI
docker compose --profile openwebui up -d
```

## Documentation

See `Gaia_Installation_Guide.docx` for detailed setup and troubleshooting.

## Architecture

- **Backend**: Python FastAPI with Gaia SDK
- **Frontend**: React + Vite with TypeScript
- **Integration**: OpenAI-compatible API endpoint (`/v1/chat/completions`)
- **Orchestration**: Docker Compose

All services run in isolated Docker containers and communicate via internal networking.
