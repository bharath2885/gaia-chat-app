# Gaia Knowledge Provider for OpenWebUI

Integrate Cohesity Gaia datasets as **live knowledge repositories** in OpenWebUI.
Datasets appear in the "Attach Knowledge" dropdown and are queried in real time — no data duplication, no stale embeddings.

## How It Works

```
User attaches "gaia:Clinical_Trial_Data_1" knowledge to a chat
             ↓
Gaia Knowledge Filter (inlet) fires before the LLM call
             ↓
Filter calls  POST /api/v1/datasets/Clinical_Trial_Data_1/search
  with the user's query  →  Gaia semantic search API
             ↓
Top-N relevant passages injected into the system message
             ↓
LLM answers grounded in live Gaia data
```

## Files

| File | Purpose |
|------|---------|
| `gaia_knowledge_filter.py` | OpenWebUI Filter Function — intercepts chat requests and injects Gaia context |
| `gaia_knowledge_setup.py` | CLI script — registers all Gaia datasets as OpenWebUI Knowledge collections |

---

## Quick Start

### Step 1 — Register datasets as Knowledge collections

```bash
python openwebui/gaia_knowledge_setup.py \
  --gaia-backend  http://localhost:8000 \
  --gaia-api-key  <your-gaia-api-key> \
  --owui-url      http://localhost:8080 \
  --owui-token    <owui-admin-jwt>
```

To get an OpenWebUI admin token:
```bash
curl -s -X POST http://localhost:8080/api/v1/auths/signin \
     -H 'Content-Type: application/json' \
     -d '{"email":"admin@example.com","password":"yourpassword"}' \
  | jq -r .token
```

### Step 2 — Install the Filter Function

1. Open OpenWebUI → **Workspace → Functions → +**
2. Paste the contents of `gaia_knowledge_filter.py`
3. Click the **gear icon** on the function and set the Valves:

   | Valve | Value |
   |-------|-------|
   | `gaia_backend_url` | `http://backend:8000` (Docker) or `http://localhost:8000` (local) |
   | `gaia_session_id` | output of the login curl below |
   | `num_results` | number of chunks to retrieve (default: 5) |

   To get a session ID:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/auth/login \
        -H 'Content-Type: application/json' \
        -d '{"api_key": "<your-gaia-api-key>"}' | jq -r .sessionId
   ```

4. **Enable** the function (toggle ON) — either globally or per-model

### Step 3 — Use Gaia Knowledge in a chat

Two ways to attach Gaia knowledge to a conversation:

**Option A — Attach Knowledge button:**
Click the paperclip / "+" icon → "Attach Knowledge" → select a `gaia:*` collection

**Option B — Type in message:**
```
#gaia:Clinical_Trial_Data_1 What are the dose adjustment guidelines?
```

---

## Advanced Options

```
python openwebui/gaia_knowledge_setup.py --help

  --dry-run     Preview what would be created without making changes
  --update      Re-create collections that already exist
  --prefix      Change the collection name prefix (default: "gaia:")
```

## Troubleshooting

**Collections not appearing in dropdown**
→ Wait a few seconds after running the setup script, then refresh OpenWebUI.

**"No Gaia results found" in chat**
→ Check that the Filter's `gaia_session_id` valve is set and not expired.
→ Enable `debug_logging` in the Filter valves and check the OpenWebUI server logs.

**HTTP 401 from backend**
→ Re-run the login curl and update `gaia_session_id` in the Filter valves.
Session tokens expire after the configured TTL (default: 60 minutes).

**Filter not firing**
→ Confirm the function is enabled (green toggle) in Workspace → Functions.
→ Ensure the knowledge collection name starts with the `collection_prefix` valve value (`gaia:` by default).
