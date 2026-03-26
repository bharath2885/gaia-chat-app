"""Unified Gaia API client."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from gaia_sdk.auth import GaiaAuth
from gaia_sdk.exceptions import GaiaTimeoutError, raise_for_status
from gaia_sdk.models import (
    AskRequest,
    AskResponse,
    Dataset,
    DatasetDetails,
    ExhaustiveSearchRequest,
    ExhaustiveSearchResponse,
    RefineRequest,
    RefineResponse,
    UploadSession,
)
from gaia_sdk.streaming import StreamChunk, StreamResult, async_accumulate_stream, parse_sse_line

DEFAULT_BASE_URL = "https://helios.cohesity.com/v2/mcm/gaia"
DEFAULT_TIMEOUT = 60


class GaiaClient:
    """Async HTTP client for the Cohesity Gaia API.

    Usage:
        async with GaiaClient(api_key="your-key") as gaia:
            datasets = await gaia.list_datasets()
            response = await gaia.ask(["my-dataset"], "What happened yesterday?")
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        verify_ssl: bool = True,
        security_context: str | None = None,
    ):
        self._auth = GaiaAuth(
            api_key=api_key or os.environ.get("GAIA_API_KEY", ""),
            security_context=security_context or os.environ.get("GAIA_SECURITY_CTX"),
        )
        if not self._auth.api_key:
            raise ValueError(
                "api_key is required. Pass it directly or set GAIA_API_KEY env var."
            )

        self._base_url = (base_url or os.environ.get("GAIA_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_env(cls) -> GaiaClient:
        """Create a GaiaClient using environment variables.

        Reads: GAIA_API_KEY, GAIA_BASE_URL, GAIA_VERIFY_SSL, GAIA_SECURITY_CTX
        """
        return cls(
            api_key=os.environ.get("GAIA_API_KEY"),
            base_url=os.environ.get("GAIA_BASE_URL"),
            verify_ssl=os.environ.get("GAIA_VERIFY_SSL", "true").lower() == "true",
            security_context=os.environ.get("GAIA_SECURITY_CTX"),
        )

    async def __aenter__(self) -> GaiaClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            verify=self._verify_ssl,
            headers={
                **self._auth.to_headers(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("GaiaClient must be used as an async context manager: async with GaiaClient(...) as gaia:")
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        """Make an HTTP request and handle errors."""
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise GaiaTimeoutError(f"Request timed out: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = {"message": response.text}
            raise_for_status(response.status_code, body)

        if response.status_code == 204:
            return {}
        return response.json()

    # ── Datasets ──────────────────────────────────────────────────────────

    async def list_datasets(self, prefix: str | None = None) -> list[Dataset]:
        """List available datasets, optionally filtered by name prefix."""
        params = {}
        if prefix:
            params["prefix"] = prefix
        data = await self._request("GET", "/datasets", params=params)
        datasets = data.get("datasets", data) if isinstance(data, dict) else data
        return [Dataset.model_validate(d) for d in datasets]

    async def get_dataset(self, name: str) -> DatasetDetails:
        """Get details of a specific dataset."""
        data = await self._request("GET", f"/dataset/{name}/details")
        return DatasetDetails.model_validate(data)

    async def create_dataset(self, name: str, **kwargs: Any) -> dict:
        """Create a new dataset."""
        payload = {"name": name, **kwargs}
        return await self._request("POST", "/datasets", json=payload)

    async def delete_dataset(self, name: str) -> dict:
        """Delete a dataset."""
        return await self._request("DELETE", f"/dataset/{name}")

    async def trigger_indexing(self, name: str) -> dict:
        """Trigger indexing for a dataset."""
        return await self._request("POST", f"/dataset/{name}/index")

    # ── Ask (RAG Query) ──────────────────────────────────────────────────

    async def ask(
        self,
        dataset_names: list[str],
        query: str,
        conversation_id: str | None = None,
        llm_name: str | None = None,
    ) -> AskResponse:
        """Send a synchronous RAG query to Gaia."""
        payload: dict[str, Any] = {
            "datasetNames": dataset_names,
            "queryString": query,
        }
        if conversation_id:
            payload["conversationId"] = conversation_id
        if llm_name:
            payload["llmName"] = llm_name

        data = await self._request("POST", "/ask", json=payload)
        return AskResponse.model_validate(data)

    async def ask_stream(
        self,
        dataset_names: list[str],
        query: str,
        conversation_id: str | None = None,
        llm_name: str | None = None,
    ) -> StreamResult:
        """Send a streaming RAG query and return the accumulated result."""
        payload: dict[str, Any] = {
            "datasetNames": dataset_names,
            "queryString": query,
        }
        if conversation_id:
            payload["conversationId"] = conversation_id
        if llm_name:
            payload["llmName"] = llm_name

        async with self.client.stream(
            "POST",
            "/ask/stream",
            json=payload,
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                try:
                    body = response.json()
                except Exception:
                    body = {"message": response.text}
                raise_for_status(response.status_code, body)

            return await async_accumulate_stream(response)

    async def ask_stream_iter(
        self,
        dataset_names: list[str],
        query: str,
        conversation_id: str | None = None,
        llm_name: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Send a streaming RAG query and yield individual SSE chunks.

        Caller is responsible for managing the streaming response lifecycle.
        """
        payload: dict[str, Any] = {
            "datasetNames": dataset_names,
            "queryString": query,
        }
        if conversation_id:
            payload["conversationId"] = conversation_id
        if llm_name:
            payload["llmName"] = llm_name

        import json

        async with self.client.stream(
            "POST",
            "/ask/stream",
            json=payload,
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                try:
                    body = response.json()
                except Exception:
                    body = {"message": response.text}
                raise_for_status(response.status_code, body)

            current_data_parts: list[str] = []
            current_event = "message"

            async for line in response.aiter_lines():
                field_name, value = parse_sse_line(line)
                if field_name is None:
                    if current_data_parts:
                        data = "\n".join(current_data_parts)
                        parsed = None
                        try:
                            parsed = json.loads(data)
                        except (json.JSONDecodeError, TypeError):
                            pass
                        yield StreamChunk(event=current_event, data=data, parsed=parsed)
                    current_event = "message"
                    current_data_parts = []
                elif field_name == "event":
                    current_event = value or "message"
                elif field_name == "data":
                    current_data_parts.append(value or "")

    # ── Exhaustive Search ─────────────────────────────────────────────────

    async def exhaustive_search(
        self,
        dataset_name: str,
        query: str,
        page_size: int = 20,
        pagination_token: str | None = None,
        conversation_id: str | None = None,
    ) -> ExhaustiveSearchResponse:
        """Run an exhaustive document search."""
        payload: dict[str, Any] = {
            "datasetName": dataset_name,
            "queryString": query,
            "pageSize": page_size,
        }
        if pagination_token:
            payload["paginationToken"] = pagination_token
        if conversation_id:
            payload["conversationId"] = conversation_id

        data = await self._request("PUT", "/ask/exhaustive", json=payload)
        return ExhaustiveSearchResponse.model_validate(data)

    # ── Refine ────────────────────────────────────────────────────────────

    async def refine(
        self,
        query_uid: str,
        dataset_names: list[str],
        query: str,
        doc_ids: list[str],
    ) -> RefineResponse:
        """Refine a previous answer using specific documents."""
        payload = {
            "queryUid": query_uid,
            "datasetNames": dataset_names,
            "queryString": query,
            "docIds": doc_ids,
        }
        data = await self._request("POST", "/ask/refine", json=payload)
        return RefineResponse.model_validate(data)

    # ── Feedback ──────────────────────────────────────────────────────────

    async def send_feedback(
        self,
        query_uid: str,
        is_good: bool,
        feedback_text: str | None = None,
    ) -> dict:
        """Send feedback on a query response."""
        payload: dict[str, Any] = {
            "queryUid": query_uid,
            "isGood": is_good,
        }
        if feedback_text:
            payload["feedbackText"] = feedback_text
        return await self._request("POST", "/query-feedback", json=payload)

    # ── Document Upload ───────────────────────────────────────────────────

    async def create_upload_session(self) -> UploadSession:
        """Create an upload session for grouping file uploads."""
        data = await self._request("POST", "/upload-session")
        return UploadSession.model_validate(data)

    async def upload_file(
        self,
        session_id: str,
        file_path: str | Path,
        file_name: str | None = None,
    ) -> dict:
        """Upload a file to an existing upload session."""
        path = Path(file_path)
        name = file_name or path.name
        size = path.stat().st_size

        with open(path, "rb") as f:
            response = await self.client.post(
                "/upload-file",
                content=f.read(),
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Upload-Session-ID": session_id,
                    "X-File-Name": name,
                    "X-File-Size": str(size),
                },
            )

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = {"message": response.text}
            raise_for_status(response.status_code, body)

        return response.json()

    # ── Dataset Discovery ─────────────────────────────────────────────────

    async def get_discovery(self, dataset_id: str) -> dict:
        """Get discovery results (hierarchy) for a dataset."""
        return await self._request("GET", f"/dataset/{dataset_id}/discovery")

    # ── Conversations ─────────────────────────────────────────────────────

    async def list_conversations(self) -> list[dict]:
        """List all conversations."""
        data = await self._request("GET", "/conversations")
        return data.get("conversations", data) if isinstance(data, dict) else data

    async def get_chat_history(self, conversation_id: str) -> list[dict]:
        """Get the chat history for a conversation."""
        data = await self._request(
            "GET", "/chat-history", params={"conversationId": conversation_id}
        )
        return data.get("messages", data) if isinstance(data, dict) else data

    async def delete_conversation(self, conversation_id: str) -> dict:
        """Delete a conversation and its messages."""
        return await self._request("DELETE", f"/conversations/{conversation_id}")

    # ── Sensitive Data ────────────────────────────────────────────────────

    async def list_sensitive_data_policies(self) -> list[dict]:
        """List sensitive data handling policies."""
        data = await self._request("GET", "/sensitive-data/policies")
        return data.get("policies", data) if isinstance(data, dict) else data

    # ── LLMs ──────────────────────────────────────────────────────────────

    async def list_llms(self) -> list[dict]:
        """List registered LLMs."""
        data = await self._request("GET", "/llms")
        return data.get("llms", data) if isinstance(data, dict) else data

    # ── Similar Document Parts ────────────────────────────────────────────

    async def search_similar_parts(
        self,
        dataset_name: str,
        query: str,
        **kwargs: Any,
    ) -> dict:
        """Search for similar document parts (semantic chunk retrieval)."""
        payload: dict[str, Any] = {
            "datasetName": dataset_name,
            "queryString": query,
            **kwargs,
        }
        return await self._request("POST", "/search/similar-document-parts", json=payload)
