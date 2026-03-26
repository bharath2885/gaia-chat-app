"""API routes for the Gaia Chat App."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.dependencies import require_session
from backend.models.api_models import (
    AskRequest,
    AskResponse,
    LoginRequest,
    LoginResponse,
)
from backend.services.session_service import create_session, delete_session
from backend.settings import get_settings
from gaia_sdk import GaiaClient
from gaia_sdk.exceptions import GaiaAuthError, GaiaError

logger = logging.getLogger(__name__)
router = APIRouter()


def _make_client(api_key: str) -> GaiaClient:
    s = get_settings()
    return GaiaClient(
        api_key=api_key,
        base_url=s.gaia_base_url,
        timeout=int(s.request_timeout_seconds),
        verify_ssl=s.gaia_verify_ssl,
    )


# ── Auth ─────────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=LoginResponse, tags=["Auth"])
async def login(body: LoginRequest):
    """Validate the API key against Gaia and create a session."""
    async with _make_client(body.api_key) as gaia:
        try:
            await gaia.list_datasets()
        except GaiaAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"API key validation failed: {exc}",
            )

    settings = get_settings()
    session_id = create_session(body.api_key, ttl_minutes=settings.session_ttl_minutes)
    return LoginResponse(session_id=session_id)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["Auth"])
async def logout(
    x_session_id: Optional[str] = Header(default=None, alias="X-SESSION-ID"),
):
    if x_session_id:
        delete_session(x_session_id)


# ── Datasets ─────────────────────────────────────────────────────────

@router.get("/datasets", tags=["Datasets"])
async def list_datasets(api_key: str = Depends(require_session)):
    async with _make_client(api_key) as gaia:
        datasets = await gaia.list_datasets()
    return {"datasets": [d.model_dump(by_alias=True) for d in datasets]}


@router.post("/datasets", tags=["Datasets"])
async def create_dataset(body: dict, api_key: str = Depends(require_session)):
    """Create a new dataset."""
    async with _make_client(api_key) as gaia:
        result = await gaia.create_dataset(**body)
    logger.info("Dataset created: %s", body.get("name"))
    return result


@router.post("/datasets/{dataset_name}/index", tags=["Datasets"])
async def trigger_indexing(dataset_name: str, api_key: str = Depends(require_session)):
    """Trigger indexing for a dataset."""
    async with _make_client(api_key) as gaia:
        result = await gaia.trigger_indexing(dataset_name)
    logger.info("Indexing triggered for dataset: %s", dataset_name)
    return result


@router.get("/datasets/{dataset_name}/details", tags=["Datasets"])
async def get_dataset_details(dataset_name: str, api_key: str = Depends(require_session)):
    """Get dataset details including indexing stats."""
    async with _make_client(api_key) as gaia:
        details = await gaia.get_dataset(dataset_name)
    return details.model_dump(by_alias=True)


# ── Ask ──────────────────────────────────────────────────────────────

@router.post("/ask", response_model=AskResponse, tags=["Ask"])
async def ask(body: AskRequest, api_key: str = Depends(require_session)):
    async with _make_client(api_key) as gaia:
        result = await gaia.ask(
            dataset_names=body.dataset_names,
            query=body.query,
            conversation_id=body.conversation_id,
        )
    return result.model_dump(by_alias=True)


@router.post("/ask/stream", tags=["Ask"])
async def ask_stream(body: AskRequest, api_key: str = Depends(require_session)):
    """Streaming RAG query — proxies SSE from Gaia."""

    async def event_generator():
        try:
            logger.info("ask/stream → datasets=%s query=%r", body.dataset_names, body.query)
            async with _make_client(api_key) as gaia:
                chunk_count = 0
                async for chunk in gaia.ask_stream_iter(
                    dataset_names=body.dataset_names,
                    query=body.query,
                    conversation_id=body.conversation_id,
                ):
                    chunk_count += 1
                    if chunk_count <= 3:
                        logger.debug("chunk #%d event=%r data=%r parsed=%r", chunk_count, chunk.event, chunk.data[:120], chunk.parsed)
                    # Log any chunk that contains documents
                    if chunk.parsed:
                        docs = (chunk.parsed.get("data") or {}).get("documents")
                        if docs:
                            logger.info("chunk #%d contains %d document(s): %s", chunk_count, len(docs), docs)
                    if chunk.event and chunk.event != "message":
                        yield f"event: {chunk.event}\n"
                    yield f"data: {chunk.data}\n\n"
                logger.info("ask/stream ✓ completed — %d chunks", chunk_count)
        except GaiaError as exc:
            logger.error("ask/stream GaiaError — %s: %s", type(exc).__name__, exc)
            yield "data: [ERROR]\n\n"
        except Exception as exc:
            logger.error("ask/stream UNEXPECTED error — %s: %s", type(exc).__name__, exc)
            yield "data: [ERROR]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Discovery / Topic Explorer ───────────────────────────────────────

async def _resolve_dataset_id(dataset_name: str, api_key: str) -> str:
    """
    Look up the internal dataset ID for a given dataset name.
    The Gaia discovery API requires the dataset ID, not the human-readable name.
    Falls back to the name if the ID cannot be resolved.
    """
    import httpx
    s = get_settings()
    headers = {"apiKey": api_key, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(verify=s.gaia_verify_ssl, timeout=15) as client:
            resp = await client.get(f"{s.gaia_base_url}/datasets", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            datasets = data.get("datasets", data) if isinstance(data, dict) else data
            logger.debug("dataset list sample: %s", str(datasets[:1])[:400])
            for ds in datasets:
                if ds.get("name") == dataset_name:
                    # Try common ID field names
                    ds_id = ds.get("id") or ds.get("datasetId") or ds.get("uid") or ds.get("_id")
                    if ds_id:
                        logger.info("resolved dataset %r → id=%r", dataset_name, ds_id)
                        return str(ds_id)
    except Exception as exc:
        logger.warning("Could not resolve dataset ID for %r: %s", dataset_name, exc)
    logger.warning("Could not find ID for dataset %r, falling back to name", dataset_name)
    return dataset_name


@router.get("/datasets/{dataset_name}/discovery", tags=["Discovery"])
async def get_discovery(
    dataset_name: str,
    num_levels: int = 2,
    api_key: str = Depends(require_session),
):
    """Fetch topic hierarchy for a dataset.

    The Gaia API requires the internal dataset *ID* (not the name) for discovery.
    This endpoint automatically resolves the name → ID before calling the API.
    """
    import httpx, asyncio
    s = get_settings()
    headers = {"apiKey": api_key, "Accept": "application/json"}
    # The Gaia API validation is inconsistent — send both forms to satisfy either validator
    params = {"numLevels": num_levels, "level": num_levels}

    # Resolve name → ID (discovery API requires internal dataset ID, not the name)
    dataset_id = await _resolve_dataset_id(dataset_name, api_key)
    url = f"{s.gaia_base_url}/dataset/{dataset_id}/discovery"
    logger.info("discovery: dataset=%r resolved_id=%r level=%d", dataset_name, dataset_id, num_levels)

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            logger.info("discovery attempt %d url=%r params=%s", attempt, url, params)
            async with httpx.AsyncClient(verify=s.gaia_verify_ssl, timeout=30) as client:
                resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                payload = resp.json()
                logger.info("discovery ✓ dataset=%r keys=%s", dataset_name, list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__)
                return payload
            logger.warning("discovery attempt %d → HTTP %d body=%s", attempt, resp.status_code, resp.text[:300])
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except HTTPException:
            raise
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            logger.warning("discovery attempt %d timed out: %s", attempt, exc)
            if attempt < 3:
                await asyncio.sleep(2 ** (attempt - 1))

    logger.error("discovery failed after 3 attempts for %r: %s", dataset_name, last_exc)
    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail="Topic explorer timed out after 3 attempts. Try again shortly.",
    )


# ── Theme summary & questions ────────────────────────────────────────

@router.get("/datasets/{dataset_name}/themes/{theme_uuid}/summary", tags=["Discovery"])
async def get_theme_summary(
    dataset_name: str,
    theme_uuid: str,
    api_key: str = Depends(require_session),
):
    """Get the AI-generated text summary for a specific theme."""
    import httpx
    s = get_settings()
    headers = {"apiKey": api_key, "Accept": "application/json"}
    dataset_id = await _resolve_dataset_id(dataset_name, api_key)
    url = f"{s.gaia_base_url}/dataset/{dataset_id}/discovery/{theme_uuid}/summary"
    try:
        async with httpx.AsyncClient(verify=s.gaia_verify_ssl, timeout=30) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("theme summary → HTTP %d for dataset=%r theme=%r", resp.status_code, dataset_name, theme_uuid)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/datasets/{dataset_name}/themes/{theme_uuid}/questions", tags=["Discovery"])
async def get_theme_questions(
    dataset_name: str,
    theme_uuid: str,
    api_key: str = Depends(require_session),
):
    """Get suggested questions for a specific theme (generate-more-questions)."""
    import httpx
    s = get_settings()
    headers = {"apiKey": api_key, "Accept": "application/json"}
    dataset_id = await _resolve_dataset_id(dataset_name, api_key)
    url = f"{s.gaia_base_url}/dataset/{dataset_id}/discovery/{theme_uuid}/generate-more-questions"
    try:
        async with httpx.AsyncClient(verify=s.gaia_verify_ssl, timeout=30) as client:
            resp = await client.post(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("theme questions → HTTP %d for dataset=%r theme=%r", resp.status_code, dataset_name, theme_uuid)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ── Semantic Search (for OpenWebUI Knowledge integration) ────────────

class SearchRequest(BaseModel):
    query: str
    limit: int = 5


@router.post("/datasets/{dataset_name}/search", tags=["Search"])
async def semantic_search(
    dataset_name: str,
    body: SearchRequest,
    api_key: str = Depends(require_session),
):
    """Semantic chunk search — used by the OpenWebUI Gaia Knowledge Filter.

    Calls Gaia's similar-document-parts endpoint and returns ranked chunks
    ready for injection into an LLM context window.
    """
    import httpx
    s = get_settings()
    headers = {"apiKey": api_key, "Accept": "application/json", "Content-Type": "application/json"}
    payload = {
        "datasetName": dataset_name,
        "queryString": body.query,
        "pageSize": body.limit,
    }
    try:
        async with httpx.AsyncClient(verify=s.gaia_verify_ssl, timeout=30) as client:
            resp = await client.post(
                f"{s.gaia_base_url}/search/similar-document-parts",
                headers=headers,
                json=payload,
            )
        if resp.status_code == 200:
            data = resp.json()
            logger.info("search ✓ dataset=%r query=%r keys=%s", dataset_name, body.query[:60], list(data.keys()) if isinstance(data, dict) else type(data).__name__)
            # Normalise various response shapes into a flat list of chunks
            raw_chunks = (
                data.get("documentParts")
                or data.get("results")
                or data.get("chunks")
                or data.get("items")
                or (data if isinstance(data, list) else [])
            )
            chunks = []
            for part in raw_chunks:
                text = (
                    part.get("text")
                    or part.get("content")
                    or part.get("chunk")
                    or part.get("documentText")
                    or ""
                )
                source = (
                    part.get("documentName")
                    or part.get("source")
                    or part.get("fileName")
                    or part.get("title")
                    or ""
                )
                score = (
                    part.get("score")
                    or part.get("similarity")
                    or part.get("relevanceScore")
                    or 0.0
                )
                if text:
                    chunks.append({"text": text, "source": source, "score": score})
            return {"dataset": dataset_name, "query": body.query, "chunks": chunks}
        logger.warning("search → HTTP %d dataset=%r body=%s", resp.status_code, dataset_name, resp.text[:300])
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("search error dataset=%r: %s", dataset_name, exc)
        raise HTTPException(status_code=502, detail=str(exc))


# ── Documents ────────────────────────────────────────────────────────

@router.get("/documents/{document_uid}/download", tags=["Documents"])
async def get_document_download_url(
    document_uid: str,
    api_key: str = Depends(require_session),
):
    """Retrieve a download URL for a document by its UID.

    Tries multiple Gaia endpoint patterns since the exact path is undocumented.
    """
    import httpx
    s = get_settings()
    headers = {"apiKey": api_key, "Accept": "application/json"}

    candidate_urls = [
        f"{s.gaia_base_url}/document/{document_uid}/download-url",
        f"{s.gaia_base_url}/document/{document_uid}/download",
        f"{s.gaia_base_url}/documents/{document_uid}/download-url",
        f"{s.gaia_base_url}/documents/{document_uid}/download",
    ]

    for url in candidate_urls:
        try:
            async with httpx.AsyncClient(verify=s.gaia_verify_ssl, timeout=15) as client:
                resp = await client.get(url, headers=headers)
            logger.debug("document download probe %s → %d", url, resp.status_code)
            if resp.status_code == 200:
                data = resp.json()
                download_url = (
                    data.get("downloadUrl")
                    or data.get("url")
                    or data.get("signedUrl")
                    or data.get("presignedUrl")
                )
                if download_url:
                    logger.info("document %s → download URL found via %s", document_uid, url)
                    return {"downloadUrl": download_url}
                # Some endpoints return the URL as the body string directly
                if isinstance(data, str) and data.startswith("http"):
                    return {"downloadUrl": data}
        except Exception as exc:
            logger.debug("document download probe %s failed: %s", url, exc)

    logger.warning("document %s → no download URL found (tried %d endpoints)", document_uid, len(candidate_urls))
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Download URL not available for this document. The file may need to be accessed directly from its source.",
    )


# ── Conversations ────────────────────────────────────────────────────

@router.get("/conversations", tags=["Conversations"])
async def list_conversations(api_key: str = Depends(require_session)):
    async with _make_client(api_key) as gaia:
        return await gaia.list_conversations()


@router.get("/conversations/{conversation_id}/history", tags=["Conversations"])
async def get_chat_history(
    conversation_id: str, api_key: str = Depends(require_session)
):
    async with _make_client(api_key) as gaia:
        return await gaia.get_chat_history(conversation_id)
