# Changelog

All notable changes to the Gaia Chat Application are documented here.

---

## [1.1.0] — 2026-03-26

### Fixed
- Bundled `gaia-sdk` inside the `02-chat-app/gaia-sdk/` folder so the package
  is fully self-contained (no parent directory required at build time).
- `Dockerfile.backend`: changed build context from the repo root to `02-chat-app/`
  itself — resolves `COPY sdk/python` build error on clean installs.
- `docker-compose.yml`: updated backend `context` from `../..` to `.`.

### Added
- `setup.sh` first-time setup script.
- `docker-compose.yml` with optional OpenWebUI profile (`--profile openwebui`).
- `frontend/Dockerfile` and `frontend/nginx.conf` for containerised React app.
- `.env.example` root-level template (only `GAIA_API_KEY` required).
- `README.md` quick-reference.
- `Gaia_Installation_Guide.docx` — full installation and usage guide.

### Documentation
- Installation guide updated with Docker Desktop setup steps (macOS + Windows).
- Added extraction/folder-structure step to Section 3.
- Troubleshooting table extended with SDK build error and port-conflict entries.

---

## [1.0.0] — 2026-03-24

### Added
- Initial release of the Gaia Chat Application.
- React + FastAPI chat interface connected to the Cohesity Gaia RAG API.
- Topic Explorer sidebar and Topic Overview in main chat window.
- OpenAI-compatible API endpoint (`/v1/chat/completions`) for OpenWebUI integration.
- Topic overview auto-injected on new OpenWebUI conversations.
- Dataset Manager component wired into the chat sidebar.
