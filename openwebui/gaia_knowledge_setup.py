#!/usr/bin/env python3
"""
gaia_knowledge_setup.py
────────────────────────────────────────────────────────────────────────────
Register Cohesity Gaia datasets as OpenWebUI Knowledge collections so they
appear in the "Attach Knowledge" dropdown.

Each collection is named  "gaia:<DatasetName>"  and contains a small
metadata file.  The Gaia Knowledge Filter function intercepts live queries
against these collections and routes them to Gaia's search API.

USAGE
─────
  python openwebui/gaia_knowledge_setup.py \\
    --gaia-backend  http://localhost:8000 \\
    --gaia-api-key  <your-gaia-api-key>  \\
    --owui-url      http://localhost:8080 \\
    --owui-token    <owui-admin-jwt>

  # Get an OpenWebUI admin token:
  #   curl -s -X POST http://localhost:8080/api/v1/auths/signin \\
  #        -H 'Content-Type: application/json' \\
  #        -d '{"email":"admin@example.com","password":"yourpassword"}' \\
  #        | jq -r .token

  # Or export as env vars:
  #   export GAIA_BACKEND=http://localhost:8000
  #   export GAIA_API_KEY=your-key
  #   export OWUI_URL=http://localhost:8080
  #   export OWUI_TOKEN=your-jwt-token

OPTIONS
  --gaia-backend    URL of the Gaia FastAPI backend   [env: GAIA_BACKEND]
  --gaia-api-key    Gaia API key                      [env: GAIA_API_KEY]
  --owui-url        OpenWebUI base URL                [env: OWUI_URL]
  --owui-token      OpenWebUI JWT (admin user)        [env: OWUI_TOKEN]
  --prefix          Collection name prefix            [default: gaia:]
  --dry-run         Print what would be done, don't actually create anything
  --update          Re-create collections that already exist
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import httpx


# ── Colour helpers ────────────────────────────────────────────────────────────

def green(s: str) -> str:   return f"\033[32m{s}\033[0m"
def yellow(s: str) -> str:  return f"\033[33m{s}\033[0m"
def red(s: str) -> str:     return f"\033[31m{s}\033[0m"
def bold(s: str) -> str:    return f"\033[1m{s}\033[0m"


# ── Gaia helpers ──────────────────────────────────────────────────────────────

def gaia_login(backend: str, api_key: str) -> str:
    """Authenticate with the Gaia backend and return a session ID."""
    resp = httpx.post(
        f"{backend}/api/v1/auth/login",
        json={"api_key": api_key},
        timeout=15,
        verify=False,
    )
    resp.raise_for_status()
    payload = resp.json()
    # Backend serialises LoginResponse with the camelCase alias "sessionId";
    # accept the snake_case form too for forward-compatibility.
    session_id = payload.get("sessionId") or payload.get("session_id") or ""
    if not session_id:
        raise ValueError(f"Login response did not contain a session id: {resp.text}")
    return session_id


def gaia_list_datasets(backend: str, session_id: str) -> list[dict]:
    """List all datasets from the Gaia backend."""
    resp = httpx.get(
        f"{backend}/api/v1/datasets",
        headers={"X-SESSION-ID": session_id},
        timeout=15,
        verify=False,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("datasets", data) if isinstance(data, dict) else data


# ── OpenWebUI helpers ─────────────────────────────────────────────────────────

def owui_list_knowledge(owui_url: str, token: str) -> list[dict]:
    """List existing OpenWebUI knowledge collections."""
    # NOTE: the trailing slash matters — without it OpenWebUI's SPA catch-all
    # returns HTML (200) instead of JSON.
    resp = httpx.get(
        f"{owui_url}/api/v1/knowledge/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    # Newer OpenWebUI returns {"items": [...], "total": N}; older used {"knowledge": [...]}.
    return data.get("items") or data.get("knowledge") or []


def owui_create_knowledge(owui_url: str, token: str, name: str, description: str) -> str | None:
    """Create an OpenWebUI knowledge collection. Returns the collection ID."""
    resp = httpx.post(
        f"{owui_url}/api/v1/knowledge/create",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": name, "description": description, "data": {}},
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    # Some OpenWebUI versions use a different path
    resp2 = httpx.post(
        f"{owui_url}/api/v1/knowledge",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": name, "description": description, "data": {}},
        timeout=15,
    )
    if resp2.status_code in (200, 201):
        return resp2.json().get("id")
    print(red(f"    ✗ Failed to create collection: HTTP {resp.status_code} — {resp.text[:200]}"))
    return None


def owui_add_file_to_knowledge(
    owui_url: str,
    token: str,
    collection_id: str,
    filename: str,
    content: str,
) -> bool:
    """Upload a text file to an OpenWebUI knowledge collection."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix="gaia_") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Step 1: upload the file to /api/v1/files
        with open(tmp_path, "rb") as f:
            upload_resp = httpx.post(
                f"{owui_url}/api/v1/files/",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (filename, f, "text/plain")},
                timeout=30,
            )
        if upload_resp.status_code not in (200, 201):
            print(red(f"    ✗ File upload failed: HTTP {upload_resp.status_code} — {upload_resp.text[:200]}"))
            return False

        file_id = upload_resp.json().get("id")
        if not file_id:
            print(red(f"    ✗ File upload response missing id: {upload_resp.text[:200]}"))
            return False

        # Step 2: add the file to the knowledge collection
        add_resp = httpx.post(
            f"{owui_url}/api/v1/knowledge/{collection_id}/file/add",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"file_id": file_id},
            timeout=30,
        )
        if add_resp.status_code in (200, 201):
            return True

        print(red(f"    ✗ Adding file to collection failed: HTTP {add_resp.status_code} — {add_resp.text[:200]}"))
        return False
    finally:
        os.unlink(tmp_path)


def build_metadata_file(dataset: dict, backend_url: str) -> str:
    """Build the metadata text file content for a Gaia knowledge collection."""
    name = dataset.get("name", "unknown")
    ds_id = dataset.get("id") or dataset.get("datasetId") or "unknown"
    status = dataset.get("status", "")
    created = dataset.get("createdAt") or dataset.get("created_at") or ""

    return textwrap.dedent(f"""\
        GAIA KNOWLEDGE COLLECTION — LIVE RETRIEVAL
        ═══════════════════════════════════════════
        Dataset Name  : {name}
        Dataset ID    : {ds_id}
        Status        : {status}
        Created       : {created}
        Backend URL   : {backend_url}

        ───────────────────────────────────────────
        HOW THIS WORKS
        ───────────────────────────────────────────
        This collection is a placeholder. When you attach it to a chat,
        the "Gaia Knowledge Filter" function intercepts your query and
        retrieves the most relevant passages live from the Gaia dataset
        "{name}" via the Gaia semantic search API.

        No documents are stored here — retrieval is always live and
        up-to-date with the current state of your Gaia dataset.

        ───────────────────────────────────────────
        SETUP REMINDER
        ───────────────────────────────────────────
        Make sure the "Gaia Knowledge Filter" function is installed in
        OpenWebUI → Workspace → Functions and that its Valves are
        configured with:
          • gaia_backend_url  = {backend_url}
          • gaia_session_id   = <session from /api/v1/auth/login>

        Attach this knowledge to a chat using the paperclip icon or by
        typing  #gaia:{name}  in the message box.
    """)


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Register Gaia datasets as OpenWebUI Knowledge collections.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("USAGE")[1].split("OPTIONS")[0].strip() if "USAGE" in __doc__ else "",
    )
    p.add_argument("--gaia-backend",  default=os.getenv("GAIA_BACKEND", "http://localhost:8000"))
    p.add_argument("--gaia-api-key",  default=os.getenv("GAIA_API_KEY", ""))
    p.add_argument("--owui-url",      default=os.getenv("OWUI_URL", "http://localhost:8080"))
    p.add_argument("--owui-token",    default=os.getenv("OWUI_TOKEN", ""))
    p.add_argument("--prefix",        default="gaia:")
    p.add_argument("--dry-run",       action="store_true")
    p.add_argument("--update",        action="store_true", help="Re-create existing collections")
    p.add_argument("--only",          default="",
                   help="Comma-separated dataset names to register (default: all). "
                        "Useful when you have many datasets and only want a subset.")
    p.add_argument("--limit",         type=int, default=0,
                   help="Register at most N datasets (0 = no limit). Applied after --only.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Validate required args
    missing = []
    if not args.gaia_api_key:  missing.append("--gaia-api-key / GAIA_API_KEY")
    if not args.owui_token:    missing.append("--owui-token / OWUI_TOKEN")
    if missing:
        print(red(f"Error: missing required arguments: {', '.join(missing)}"))
        print(yellow("Run with --help for usage details."))
        sys.exit(1)

    print(bold("\n═══ Gaia → OpenWebUI Knowledge Setup ═══\n"))
    if args.dry_run:
        print(yellow("DRY RUN — no changes will be made.\n"))

    # 1. Authenticate with Gaia backend
    print(f"→ Authenticating with Gaia backend at {args.gaia_backend} …")
    try:
        session_id = gaia_login(args.gaia_backend, args.gaia_api_key)
        print(green(f"  ✓ Session established  ({session_id[:12]}…)"))
    except Exception as exc:
        print(red(f"  ✗ Authentication failed: {exc}"))
        sys.exit(1)

    # 2. List Gaia datasets
    print("\n→ Fetching Gaia datasets …")
    try:
        datasets = gaia_list_datasets(args.gaia_backend, session_id)
        print(green(f"  ✓ Found {len(datasets)} dataset(s)"))
    except Exception as exc:
        print(red(f"  ✗ Failed to list datasets: {exc}"))
        sys.exit(1)

    # Optional filtering: --only <names> then --limit <N>
    if args.only:
        wanted = {n.strip() for n in args.only.split(",") if n.strip()}
        datasets = [d for d in datasets if d.get("name") in wanted]
        missing = wanted - {d.get("name") for d in datasets}
        print(green(f"  ✓ --only filter → {len(datasets)} dataset(s)"))
        if missing:
            print(yellow(f"    ! not found on Gaia: {', '.join(sorted(missing))}"))
    if args.limit and len(datasets) > args.limit:
        datasets = datasets[: args.limit]
        print(green(f"  ✓ --limit applied → {len(datasets)} dataset(s)"))
    for ds in datasets:
        print(f"     • {ds.get('name', '?')}")

    # 3. List existing OpenWebUI knowledge collections
    print(f"\n→ Fetching existing OpenWebUI knowledge collections at {args.owui_url} …")
    try:
        existing = owui_list_knowledge(args.owui_url, args.owui_token)
        existing_names = {k.get("name", "") for k in existing}
        print(green(f"  ✓ Found {len(existing)} existing collection(s)"))
    except Exception as exc:
        print(red(f"  ✗ Failed to list knowledge: {exc}"))
        sys.exit(1)

    # 4. Create a knowledge collection for each dataset
    print(f"\n→ Registering datasets as Knowledge collections (prefix: {args.prefix!r}) …\n")
    created = skipped = failed = 0

    for dataset in datasets:
        name = dataset.get("name", "")
        if not name:
            continue

        collection_name = f"{args.prefix}{name}"
        print(f"  Dataset: {bold(name)}")
        print(f"    Collection: {collection_name!r}")

        if collection_name in existing_names and not args.update:
            print(yellow("    → Already exists, skipping (use --update to overwrite)\n"))
            skipped += 1
            continue

        if args.dry_run:
            print(green("    → [dry-run] Would create collection + upload metadata file\n"))
            created += 1
            continue

        # Create the collection
        description = (
            f"Live Gaia retrieval — dataset: {name}. "
            "Attach this knowledge to a chat; the Gaia Knowledge Filter "
            "will retrieve relevant passages in real time."
        )
        collection_id = owui_create_knowledge(args.owui_url, args.owui_token, collection_name, description)
        if not collection_id:
            failed += 1
            print()
            continue
        print(green(f"    ✓ Collection created  id={collection_id}"))

        # Upload metadata file
        metadata_content = build_metadata_file(dataset, args.gaia_backend)
        filename = f"gaia_{name}_metadata.txt"
        ok = owui_add_file_to_knowledge(
            args.owui_url, args.owui_token, collection_id, filename, metadata_content
        )
        if ok:
            print(green(f"    ✓ Metadata file uploaded: {filename}"))
            created += 1
        else:
            failed += 1
        print()

    # 5. Summary
    print(bold("═══ Summary ═══"))
    print(green(f"  Created : {created}"))
    print(yellow(f"  Skipped : {skipped}"))
    if failed:
        print(red(f"  Failed  : {failed}"))
    print()

    if not args.dry_run and created > 0:
        print(bold("Next steps:"))
        print(textwrap.dedent(f"""\
          1. Open OpenWebUI → Workspace → Functions
          2. Upload  openwebui/gaia_knowledge_filter.py  as a new Function
          3. Click the gear icon on the function and set:
               gaia_backend_url  →  {args.gaia_backend}
               gaia_session_id   →  <run the login curl above to get it>
          4. Enable the function globally or per-model
          5. In a chat, click "Attach Knowledge" and select a  gaia:*  collection
             OR type  #gaia:<DatasetName>  in the message box
        """))

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
