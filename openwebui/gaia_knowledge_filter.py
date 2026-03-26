"""
title: Gaia Knowledge Filter
author: Gaia Chat App
version: 1.0.0
description: >
  Live retrieval from Cohesity Gaia datasets when knowledge collections
  prefixed with "gaia:" are attached to a chat.

  HOW IT WORKS
  ─────────────────────────────────────────────────────────────────────
  1. You (or the setup script) create OpenWebUI Knowledge collections
     named  "gaia:<DatasetName>"  — e.g. "gaia:Clinical_Trial_Data_1".
  2. A user attaches one of those collections to a chat via the
     "Attach Knowledge" button (or the # shortcut).
  3. This filter intercepts every inlet (pre-LLM) call, detects any
     attached gaia: collections, calls the Gaia backend search endpoint,
     and injects the top-N retrieved chunks into the system message.
  4. The LLM then answers using live Gaia data instead of stale
     ChromaDB embeddings.

  SETUP
  ─────────────────────────────────────────────────────────────────────
  • Upload this file in OpenWebUI → Workspace → Functions → "+"
  • Set the Valves (gear icon) in the function:
      gaia_backend_url  →  http://backend:8000   (inside Docker)
                           http://localhost:8000  (local dev)
      gaia_session_id   →  the session_id from POST /api/v1/auth/login
      num_results       →  number of chunks to retrieve (default 5)
  • Run  python openwebui/gaia_knowledge_setup.py  to auto-create the
    Knowledge collections in OpenWebUI.

license: MIT
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Valve configuration (shown in OpenWebUI function settings UI) ─────────────

class Filter:
    class Valves(BaseModel):
        gaia_backend_url: str = Field(
            default="http://backend:8000",
            description=(
                "Base URL of the Gaia backend service. "
                "Use http://backend:8000 when running inside Docker Compose, "
                "or http://localhost:8000 for local development."
            ),
        )
        gaia_session_id: str = Field(
            default="",
            description=(
                "Session ID obtained from POST /api/v1/auth/login on the Gaia backend. "
                "Run: curl -X POST http://localhost:8000/api/v1/auth/login "
                "-H 'Content-Type: application/json' "
                "-d '{\"api_key\": \"<your-gaia-api-key>\"}' | jq .session_id"
            ),
        )
        num_results: int = Field(
            default=5,
            description="Number of semantic chunks to retrieve from Gaia per query (1–20).",
        )
        collection_prefix: str = Field(
            default="gaia:",
            description=(
                "Prefix that marks an OpenWebUI Knowledge collection as a Gaia dataset. "
                "Collections named  '<prefix><DatasetName>'  trigger live Gaia retrieval."
            ),
        )
        inject_source_citations: bool = Field(
            default=True,
            description="Append source document name to each retrieved chunk in the context.",
        )
        debug_logging: bool = Field(
            default=False,
            description="Log retrieval details to the OpenWebUI server console.",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, *args) -> None:
        if self.valves.debug_logging:
            logger.info("[GaiaKnowledge] " + msg, *args)

    def _extract_user_query(self, messages: list[dict]) -> str:
        """Return the text of the most recent user message."""
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return part.get("text", "").strip()
        return ""

    def _find_gaia_collections(self, body: dict) -> list[str]:
        """Return dataset names for any attached Gaia knowledge collections.

        OpenWebUI passes attached knowledge/files in body["files"] as a list
        of dicts.  Each entry may contain:
          • collection_name  — the knowledge collection name
          • name             — fallback name field
          • type             — "collection" for knowledge bases
        """
        prefix = self.valves.collection_prefix
        dataset_names: list[str] = []
        seen: set[str] = set()

        files = body.get("files") or []
        for f in files:
            # knowledge collections may appear as file entries with a collection_name
            name = (
                f.get("collection_name")
                or f.get("name")
                or f.get("title")
                or ""
            )
            if name.startswith(prefix):
                dataset = name[len(prefix):]
                if dataset and dataset not in seen:
                    dataset_names.append(dataset)
                    seen.add(dataset)

        # Also check the messages for #gaia:DatasetName mentions (manual shortcut)
        messages = body.get("messages", [])
        query = self._extract_user_query(messages)
        import re
        for match in re.finditer(r"#" + re.escape(prefix) + r"(\S+)", query):
            dataset = match.group(1).rstrip(".,;:")
            if dataset and dataset not in seen:
                dataset_names.append(dataset)
                seen.add(dataset)

        return dataset_names

    async def _fetch_chunks(self, dataset_name: str, query: str) -> list[dict]:
        """Call the Gaia backend search endpoint and return normalised chunks."""
        url = f"{self.valves.gaia_backend_url.rstrip('/')}/api/v1/datasets/{dataset_name}/search"
        headers = {"X-SESSION-ID": self.valves.gaia_session_id, "Content-Type": "application/json"}
        payload = {"query": query, "limit": self.valves.num_results}

        self._log("search → %s  query=%r", url, query[:80])
        try:
            async with httpx.AsyncClient(timeout=30, verify=False) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                chunks = data.get("chunks", [])
                self._log("search ✓ dataset=%r → %d chunks", dataset_name, len(chunks))
                return chunks
            logger.warning("[GaiaKnowledge] search HTTP %d dataset=%r: %s", resp.status_code, dataset_name, resp.text[:200])
        except Exception as exc:
            logger.error("[GaiaKnowledge] search error dataset=%r: %s", dataset_name, exc)
        return []

    def _build_context_block(self, dataset_name: str, chunks: list[dict]) -> str:
        """Format retrieved chunks into a readable context block."""
        lines = [f"### Knowledge: {dataset_name}\n"]
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "").strip()
            source = chunk.get("source", "")
            if not text:
                continue
            lines.append(f"[{i}] {text}")
            if self.valves.inject_source_citations and source:
                lines.append(f"    ↳ Source: {source}")
            lines.append("")
        return "\n".join(lines)

    # ── OpenWebUI Filter interface ─────────────────────────────────────────────

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
        **kwargs,
    ) -> dict:
        """Pre-process: inject Gaia context before the LLM call."""

        # 1. Detect attached Gaia knowledge collections
        gaia_datasets = self._find_gaia_collections(body)
        if not gaia_datasets:
            return body  # nothing to do

        # 2. Extract the user query (used as the search string)
        messages: list[dict] = body.get("messages", [])
        user_query = self._extract_user_query(messages)
        if not user_query:
            return body

        self._log("inlet triggered — datasets=%s", gaia_datasets)

        # 3. Emit a status event so users see activity in the UI
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Searching Gaia: {', '.join(gaia_datasets)}…",
                        "done": False,
                    },
                }
            )

        # 4. Fetch chunks from Gaia for each dataset
        context_parts: list[str] = []
        for dataset_name in gaia_datasets:
            chunks = await self._fetch_chunks(dataset_name, user_query)
            if chunks:
                context_parts.append(self._build_context_block(dataset_name, chunks))

        if not context_parts:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "No Gaia results found.", "done": True}}
                )
            return body

        # 5. Build the context injection preamble
        context_header = (
            "## Context from Gaia Knowledge Bases\n\n"
            "The following passages were retrieved live from Cohesity Gaia "
            "based on the user's question. Use them to ground your answer.\n\n"
        )
        full_context = context_header + "\n---\n\n".join(context_parts)

        # 6. Prepend to the system message (create one if absent)
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = full_context + "\n\n---\n\n" + messages[0]["content"]
        else:
            messages.insert(0, {"role": "system", "content": full_context})
        body["messages"] = messages

        # 7. Emit completion status
        if __event_emitter__:
            total = sum(
                len(self._build_context_block("", await self._fetch_chunks(d, user_query)).split())
                for d in []  # don't re-fetch; just mark done
            )
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": (
                            f"Injected {sum(1 for p in context_parts)} Gaia dataset(s) into context."
                        ),
                        "done": True,
                    },
                }
            )

        return body

    async def outlet(self, body: dict, **kwargs) -> dict:
        """Post-process: pass through unchanged (no modifications needed)."""
        return body
