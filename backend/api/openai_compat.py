"""
OpenAI-compatible API layer for OpenWebUI integration.

Endpoints:
  GET  /v1/models                  — lists Gaia datasets as models
  POST /v1/chat/completions        — streams Gaia ask as OpenAI SSE

Authentication:
  OpenWebUI sends:  Authorization: Bearer <gaia-api-key>
  We extract the key and call Gaia directly (no session required).
"""

import json
import logging
import time
import uuid
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.settings import get_settings
from gaia_sdk import GaiaClient
from gaia_sdk.exceptions import GaiaAuthError, GaiaError

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Auth helper ───────────────────────────────────────────────────────────────

def _extract_api_key(authorization: str | None) -> str:
    """Pull the Gaia API key from an OpenAI-style Bearer token header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Use: Bearer <gaia-api-key>",
        )
    return authorization[7:].strip()


def _make_client(api_key: str) -> GaiaClient:
    s = get_settings()
    return GaiaClient(
        api_key=api_key,
        base_url=s.gaia_base_url,
        timeout=int(s.request_timeout_seconds),
        verify_ssl=s.gaia_verify_ssl,
    )


# ── Request / Response models ─────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str                          # dataset name (or comma-separated names)
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float | None = None    # ignored — passed through for compatibility
    max_tokens: int | None = None       # ignored


# ── Topic helpers ─────────────────────────────────────────────────────────────

async def _resolve_dataset_id_compat(dataset_name: str, api_key: str) -> str:
    """Resolve dataset name → internal ID (mirrors routes.py helper)."""
    s = get_settings()
    headers = {"apiKey": api_key, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(verify=s.gaia_verify_ssl, timeout=10) as client:
            resp = await client.get(f"{s.gaia_base_url}/datasets", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            datasets = data.get("datasets", data) if isinstance(data, dict) else data
            for ds in datasets:
                if ds.get("name") == dataset_name:
                    ds_id = ds.get("id") or ds.get("datasetId") or ds.get("uid")
                    if ds_id:
                        return str(ds_id)
    except Exception as exc:
        logger.debug("compat: could not resolve dataset ID for %r: %s", dataset_name, exc)
    return dataset_name


async def _fetch_topics_compat(dataset_name: str, api_key: str) -> list[dict]:
    """Fetch topics for a dataset. Returns empty list on any failure."""
    s = get_settings()
    headers = {"apiKey": api_key, "Accept": "application/json"}
    dataset_id = await _resolve_dataset_id_compat(dataset_name, api_key)
    url = f"{s.gaia_base_url}/dataset/{dataset_id}/discovery"
    try:
        async with httpx.AsyncClient(verify=s.gaia_verify_ssl, timeout=15) as client:
            resp = await client.get(url, headers=headers, params={"numLevels": 2, "level": 2})
        logger.info("compat: topic fetch dataset=%r id=%r → HTTP %d", dataset_name, dataset_id, resp.status_code)
        if resp.status_code == 200:
            data = resp.json()
            logger.info("compat: topic response keys=%s", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
            if isinstance(data, dict):
                for key in ("themes", "topics", "clusters", "categories", "nodes", "results", "items"):
                    if isinstance(data.get(key), list) and len(data[key]) > 0:
                        logger.info("compat: found %d topics at key=%r", len(data[key]), key)
                        return data[key]
            if isinstance(data, list) and len(data) > 0:
                return data
            logger.warning("compat: discovery returned 200 but no recognised topic key — raw: %s", str(data)[:300])
        else:
            logger.warning("compat: topic fetch HTTP %d — %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("compat: topic fetch failed for %r: %s", dataset_name, exc)
    return []


def _format_topics_markdown(topics: list[dict], dataset_name: str) -> str:
    """Format topic list as a compact markdown block for OpenWebUI."""
    if not topics:
        return ""
    lines = [f"### 🗂️ Topics in **{dataset_name}**\n"]
    for t in topics[:8]:  # cap at 8 to keep it readable
        name = t.get("name") or t.get("label") or t.get("title") or "Unknown"
        pct = t.get("percentage") or t.get("chunkCoveragePercentage")
        pct_str = f" *(~{pct:.0f}% of content)*" if pct is not None else ""
        lines.append(f"- **{name}**{pct_str}")
        # Sub-themes
        subs = t.get("subThemes") or t.get("children") or t.get("subtopics") or t.get("themes") or []
        for s in subs[:3]:
            sub_name = s.get("name") or s.get("label") or ""
            if sub_name:
                lines.append(f"  - {sub_name}")
        # Suggested questions
        questions = t.get("suggestedQuestions") or []
        if questions:
            lines.append(f"  > 💬 *{questions[0]}*")
    lines.append("\n---\n*Ask me anything about these topics, or type a specific question below.*\n\n---\n")
    return "\n".join(lines)


# Triggers that explicitly request a topic overview
_TOPIC_TRIGGERS = {"topics", "show topics", "list topics", "what topics", "/topics", "explore", "overview"}


def _is_topic_request(text: str) -> bool:
    return text.strip().lower() in _TOPIC_TRIGGERS


_SYSTEM_TASK_PREFIXES = ("### Task:", "### Instructions:", "Generate a concise", "Suggest 3-5", "Generate 1-3")

def _is_system_task(text: str) -> bool:
    """Detect OpenWebUI internal system tasks (title gen, tag gen, follow-up suggestions)."""
    stripped = text.strip()
    return any(stripped.startswith(p) for p in _SYSTEM_TASK_PREFIXES)

def _is_new_conversation(messages: list) -> bool:
    """True if there are no prior assistant turns (fresh conversation)."""
    return not any(m.role == "assistant" for m in messages)


# ── GET /v1/models ────────────────────────────────────────────────────────────

@router.get("/models")
async def list_models(authorization: str | None = Header(default=None)):
    """Return Gaia datasets as OpenAI-style model objects."""
    api_key = _extract_api_key(authorization)
    try:
        async with _make_client(api_key) as gaia:
            datasets = await gaia.list_datasets()
    except GaiaAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except GaiaError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": ds.name,
                "object": "model",
                "created": now,
                "owned_by": "gaia",
                "permission": [],
                "root": ds.name,
                "parent": None,
            }
            for ds in datasets
        ],
    }


# ── POST /v1/chat/completions ─────────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    authorization: str | None = Header(default=None),
):
    """Stream a Gaia RAG answer in OpenAI SSE format."""
    api_key = _extract_api_key(authorization)

    # Model field = dataset name (supports comma-separated for multi-dataset)
    dataset_names = [d.strip() for d in body.model.split(",") if d.strip()]
    if not dataset_names:
        raise HTTPException(status_code=400, detail="No dataset specified in 'model' field.")

    # Build query from the last user message; use prior turns as context
    user_messages = [m for m in body.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found.")
    query = user_messages[-1].content

    # Pass any prior assistant/user turns as conversation history
    # (Gaia handles this via conversationId — for simplicity we just use the last query)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    is_system_task = _is_system_task(query)
    is_new_chat = _is_new_conversation(body.messages) and not is_system_task
    is_topic_cmd = _is_topic_request(query) and not is_system_task
    primary_dataset = dataset_names[0]

    logger.info(
        "openai/chat → model=%r datasets=%s query=%r new_chat=%s topic_cmd=%s system_task=%s",
        body.model, dataset_names, query[:80], is_new_chat, is_topic_cmd, is_system_task,
    )

    def _sse_token(text: str) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": body.model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}],
        }
        return f"data: {json.dumps(payload)}\n\n"

    def _sse_done() -> str:
        finish = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": body.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        return f"data: {json.dumps(finish)}\n\ndata: [DONE]\n\n"

    async def event_stream() -> AsyncIterator[str]:
        try:
            chunk_count = 0

            # ── Topic overview block ───────────────────────────────────────
            # Show on: (a) explicit /topics command, or (b) first message in a new conversation
            if is_topic_cmd or is_new_chat:
                topics = await _fetch_topics_compat(primary_dataset, api_key)
                topic_md = _format_topics_markdown(topics, primary_dataset)
                if topic_md:
                    yield _sse_token(topic_md)
                    chunk_count += 1

            # ── If pure topic command, stop here (no RAG call) ─────────────
            if is_topic_cmd:
                yield _sse_done()
                logger.info("openai/chat ✓ topics-only response")
                return

            # ── Normal Gaia RAG answer ─────────────────────────────────────
            async with _make_client(api_key) as gaia:
                async for chunk in gaia.ask_stream_iter(
                    dataset_names=dataset_names,
                    query=query,
                ):
                    if not chunk.parsed:
                        continue
                    data = chunk.parsed.get("data") or {}
                    token: str | None = data.get("responseString")
                    if not token:
                        continue
                    chunk_count += 1
                    yield _sse_token(token)

            yield _sse_done()
            logger.info("openai/chat ✓ completed — %d tokens", chunk_count)

        except GaiaAuthError as exc:
            logger.error("openai/chat auth error: %s", exc)
            yield f"data: {json.dumps({'error': {'message': str(exc), 'type': 'authentication_error'}})}\n\n"
        except GaiaError as exc:
            logger.error("openai/chat GaiaError: %s", exc)
            yield f"data: {json.dumps({'error': {'message': str(exc), 'type': 'api_error'}})}\n\n"
        except Exception as exc:
            logger.error("openai/chat unexpected error: %s", exc)
            yield f"data: {json.dumps({'error': {'message': 'Internal error', 'type': 'server_error'}})}\n\n"

    if body.stream:
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming fallback (collect all tokens)
    full_text = ""
    async with _make_client(api_key) as gaia:
        async for chunk in gaia.ask_stream_iter(dataset_names=dataset_names, query=query):
            if chunk.parsed:
                token = (chunk.parsed.get("data") or {}).get("responseString")
                if token:
                    full_text += token

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": full_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
