# Cohesity Gaia × Open WebUI — Local Setup

A working, no-Docker setup that exposes your **Cohesity Gaia** datasets inside
[Open WebUI](https://github.com/open-webui/open-webui) on this Mac. Two
integration patterns are wired up and verified:

| Pattern | What you get | Status |
|---------|--------------|--------|
| **Datasets-as-models** | Every Gaia dataset shows up as a selectable "model"; chatting with it runs live Gaia RAG with streaming answers + topic discovery. | ✅ verified end-to-end |
| **Knowledge collections + filter** | Datasets registered as `gaia:*` Knowledge collections; the *Gaia Knowledge Filter* injects live Gaia passages into any LLM chat (attach a collection or type `#gaia:<Dataset>`). | ✅ verified end-to-end |

> Branch: `feature/openwebui-integration` of `bharath2885/gaia-chat-app`.

---

## 1. Prerequisites (already provisioned in this repo)

- `venv/` — Python 3.13, backend + `gaia_sdk`
- `venv-webui/` — Python 3.11, `open-webui` 0.8.12
- `.env` — `GAIA_API_KEY`, `GAIA_BASE_URL=https://helios.cohesity.com/v2/mcm/gaia`, `GAIA_VERIFY_SSL=false`

Docker is **not** required (and isn't installed on this machine).

## 2. Start everything

```bash
cd examples/02-chat-app
./openwebui/start_openwebui_stack.sh
```

This launches:

- **Backend** → http://localhost:8000 (OpenAI-compatible `/v1`, Swagger at `/docs`)
- **Open WebUI** → http://localhost:8080

`Ctrl+C` stops both. Logs are in `logs/backend.log` and `logs/openwebui.log`.

## 3. Log in to Open WebUI

An admin account is already created in `webui_data/`:

| Field | Value |
|-------|-------|
| URL | http://localhost:8080 |
| Email | `admin@gaia.local` |
| Password | `gaia-admin-2026` |

> First-ever signup in Open WebUI becomes the admin. To create your own admin
> on a fresh `webui_data/`, just sign up in the browser.

## 4. Pattern A — Datasets as models (simplest)

Already wired: the start script sets `OPENAI_API_BASE_URL=http://localhost:8000/v1`
and `OPENAI_API_KEY=<your Gaia key>`, so Open WebUI lists all Gaia datasets as
models. Pick a dataset from the model dropdown and ask a question — answers are
grounded in that dataset via Gaia RAG.

Try: model `Airline_Demo` → *"What kind of information does this dataset contain? List key entities."*

## 5. Pattern B — Knowledge collections + live filter

**Register datasets as Knowledge collections** (already done for 5 datasets; re-run anytime):

```bash
# Get an Open WebUI admin token
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auths/signin \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@gaia.local","password":"gaia-admin-2026"}' | jq -r .token)

# Register a chosen subset (omit --only to register ALL datasets)
python openwebui/gaia_knowledge_setup.py \
  --gaia-backend http://localhost:8000 \
  --gaia-api-key "$(grep '^GAIA_API_KEY=' .env | cut -d= -f2-)" \
  --owui-url http://localhost:8080 --owui-token "$TOKEN" \
  --only "Airline_Demo,lanl_sec_host_logs,Berkshire_Automotive_Enhanced"
```

The **Gaia Knowledge Filter** function is already installed (Workspace →
Functions → *Gaia Knowledge*), enabled globally, with valves set to
`gaia_backend_url=http://localhost:8000`. To use it:

- Attach a `gaia:*` collection to a chat (paperclip / "Attach Knowledge"), **or**
- Type `#gaia:<DatasetName> <your question>` in the message box.

The filter retrieves live Gaia passages and injects them into the context.

> **Session refresh:** the filter authenticates with a Gaia *session ID* valve.
> Sessions are in-memory (60-min TTL, wiped when the backend restarts). After a
> restart, refresh it:
> ```bash
> SID=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
>   -H 'Content-Type: application/json' \
>   -d "{\"api_key\":\"$(grep '^GAIA_API_KEY=' .env | cut -d= -f2-)\"}" | jq -r .sessionId)
> curl -s -X POST http://localhost:8080/api/v1/functions/id/gaia_knowledge/valves/update \
>   -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
>   -d "{\"gaia_backend_url\":\"http://localhost:8000\",\"gaia_session_id\":\"$SID\",\"num_results\":5,\"collection_prefix\":\"gaia:\",\"inject_source_citations\":true,\"debug_logging\":false}"
> ```

> **Note on a base LLM:** the filter is most useful with a *general* LLM model
> (it injects Gaia context, then the LLM answers). Add an OpenAI/Anthropic/Ollama
> connection under Settings → Connections to use it that way. With only Gaia
> dataset-models present, the filter still fires and injects context.

---

## 6. Configuring Open WebUI in the browser (step by step)

The launcher pre-configures everything, but here's how to view/change it in the
UI — and exactly what to do when you add more datasets.

> Menu labels are for Open WebUI 0.8.x. Admin screens are reached from the
> **profile menu at the bottom-left → Admin Panel → Settings**.

### A. Verify the Gaia connection (Pattern A — datasets as models)

1. Bottom-left **profile menu → Admin Panel → Settings → Connections**.
2. Under **OpenAI API** you should see one connection:
   - **Base URL:** `http://localhost:8000/v1`
   - **API Key:** your Gaia API key
3. Click the **↻ refresh / verify** icon next to it — it should succeed and the
   connection lights up. (This is what makes every Gaia dataset appear as a model.)
4. To add it manually if it's ever missing: click **+**, enter the Base URL and
   key above, **Save**.

### B. Manage which datasets appear as models

With 167 datasets the model list is long. To curate it:

1. **Admin Panel → Settings → Models.**
2. Each model (= dataset) has a **visibility toggle** (show/hide) and a pencil to
   rename/describe. Hide the ones you don't use so the chat dropdown stays short.
3. Optionally set a **default model** here.

### C. Use a dataset in chat (Pattern A)

1. **New Chat → click the model name** at the top.
2. Type to filter (e.g. `Airline`) and pick the dataset.
3. Ask your question — the answer is grounded in that Gaia dataset.

### D. The Gaia Knowledge Filter (Pattern B)

1. **Workspace (left sidebar) → Functions.** You'll see **Gaia Knowledge**.
2. Confirm the toggle is **On** (green) and it's **Global** (applies to all models).
3. Click the **gear (Valves)** to view/edit:
   - `gaia_backend_url` = `http://localhost:8000`
   - `gaia_session_id` = (auto-refreshed by the launcher each start)
   - `num_results`, `collection_prefix` (`gaia:`), `debug_logging`
4. To use it in a chat: click **+ / paperclip → Knowledge** and select a `gaia:*`
   collection, **or** type `#gaia:<DatasetName>` in your message.

---

## Adding more datasets — the two cases

### Case 1: a dataset was newly created in Gaia
**No Open WebUI config needed** for Pattern A. The model list is read live from
Gaia. Just **reload the page** (or Admin → Settings → Connections → ↻ refresh)
and the new dataset appears in the model dropdown.

### Case 2: make a dataset attachable as Knowledge (Pattern B)

Either register via the script (recommended — handles the `gaia:` naming and the
metadata file):

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auths/signin \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@gaia.local","password":"gaia-admin-2026"}' | jq -r .token)

python openwebui/gaia_knowledge_setup.py \
  --gaia-backend http://localhost:8000 \
  --gaia-api-key "$(grep '^GAIA_API_KEY=' .env | cut -d= -f2-)" \
  --owui-url http://localhost:8080 --owui-token "$TOKEN" \
  --only "My_New_Dataset"          # or --limit N, or omit for ALL datasets
```

…**or** create it by hand in the UI:

1. **Workspace → Knowledge → + Create Knowledge Collection.**
2. **Name it exactly** `gaia:<DatasetName>` — the `gaia:` prefix is the trigger
   the filter matches. (Description is free text.)
3. Save. It now appears in **Attach Knowledge**; the filter does live retrieval —
   you do **not** need to upload any documents.

> The dataset name after `gaia:` must match the Gaia dataset name exactly
> (it's passed straight to the Gaia search).

### Optional: add a general LLM so Pattern B can synthesise

The filter injects Gaia passages, then a model answers. For a non-Gaia answerer:

1. **Admin Panel → Settings → Connections → +** (OpenAI or Ollama).
2. For OpenAI: Base URL `https://api.openai.com/v1`, paste your OpenAI key, Save.
3. In a chat, pick that model, attach a `gaia:` collection (or `#gaia:…`), and ask.

---

## What was changed to make this work

These fixes live on `feature/openwebui-integration`:

1. **`backend/api/routes.py`** — `/datasets/{name}/search` now calls Gaia's
   portable `/ask` endpoint and returns its cited `documents` as chunks (with a
   grounded-answer fallback). The previous `/search/similar-document-parts`
   endpoint **404s** on this Helios tenant.
2. **`openwebui/gaia_knowledge_setup.py`** —
   - reads `sessionId` (camelCase) from the login response (was `session_id`);
   - lists knowledge via `/api/v1/knowledge/` (trailing slash) and parses `{items:[…]}`;
   - new `--only` / `--limit` flags (there are 167 datasets — register a subset).
3. **Open WebUI config** — `BYPASS_EMBEDDING_AND_RETRIEVAL=true` so Open WebUI
   skips its own (unconfigured) embedding model; Gaia does all retrieval.
4. **`.gitignore`** — excludes `venv*/`, Open WebUI `data/`, `*.db` so the 2.2 GB
   `venv-webui` and runtime data are never committed.

## Ports & processes

| Service | Port | venv |
|---------|------|------|
| Backend (FastAPI) | 8000 | `venv` (3.13) |
| Open WebUI | 8080 | `venv-webui` (3.11) |
