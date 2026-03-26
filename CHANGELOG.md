# Changelog

All notable changes to the Gaia Chat Application are documented here.

---

## [1.2.0] — 2026-03-27

### Added — Gaia Knowledge Provider for OpenWebUI
- **`openwebui/gaia_knowledge_filter.py`** — OpenWebUI Filter Function that intercepts
  chat requests, detects attached `gaia:*` knowledge collections, and injects live
  semantic search results from Gaia into the LLM context window before each call.
- **`openwebui/gaia_knowledge_setup.py`** — CLI script that authenticates with the Gaia
  backend, lists all available datasets, and auto-creates matching OpenWebUI Knowledge
  collections (named `gaia:<DatasetName>`) with metadata placeholder files.
- **`openwebui/README.md`** — step-by-step integration guide (function upload, valve
  configuration, collection attachment, and troubleshooting).
- **`backend/api/routes.py`** — new `POST /api/v1/datasets/{name}/search` endpoint:
  wraps Gaia's `similar-document-parts` semantic search API and normalises the response
  into a flat list of `{text, source, score}` chunks for easy context injection.

### How It Works
Gaia datasets now surface as live knowledge repositories in OpenWebUI's
"Attach Knowledge" dropdown.  When a user selects a `gaia:*` collection, the Filter
Function fires before the LLM, queries Gaia's semantic search API for the most relevant
passages, and prepends them to the system prompt.  No data duplication — retrieval is
always live and up-to-date.

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
