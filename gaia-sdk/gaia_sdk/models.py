"""Pydantic models for Gaia API requests and responses."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ── Datasets ──────────────────────────────────────────────────────────────────

class Dataset(BaseModel):
    name: str
    status: str | None = None
    description: str | None = None
    created_at: str | None = Field(None, alias="createdAt")
    updated_at: str | None = Field(None, alias="updatedAt")
    object_count: int | None = Field(None, alias="objectCount")

    model_config = {"populate_by_name": True}


class DatasetDetails(BaseModel):
    name: str
    status: str | None = None
    description: str | None = None
    data_sources: list[dict[str, Any]] | None = Field(None, alias="dataSources")
    indexing_stats: dict[str, Any] | None = Field(None, alias="indexingStats")
    object_count: int | None = Field(None, alias="objectCount")

    model_config = {"populate_by_name": True}


# ── Documents ─────────────────────────────────────────────────────────────────

class Document(BaseModel):
    """A document returned from a Gaia query."""
    doc_id: str | None = Field(None, alias="docId")
    filename: str | None = None
    filepath: str | None = None
    snippet: str | None = None
    score: float | None = None
    metadata: dict[str, Any] | None = None


# ── Ask (RAG Query) ──────────────────────────────────────────────────────────

class HistoryEntry(BaseModel):
    query: str
    response: str


class AskRequest(BaseModel):
    """Parameters for POST /ask and POST /ask/stream."""
    dataset_names: list[str] = Field(alias="datasetNames")
    query_string: str = Field(alias="queryString")
    llm_name: str | None = Field(None, alias="llmName")
    conversation_id: str | None = Field(None, alias="conversationId")
    history: list[HistoryEntry] | None = None

    model_config = {"populate_by_name": True}


class AskResponse(BaseModel):
    """Response from POST /ask."""
    response_string: str | None = Field(None, alias="responseString")
    query_uid: str | None = Field(None, alias="queryUid")
    conversation_id: str | None = Field(None, alias="conversationId")
    conversation_name: str | None = Field(None, alias="conversationName")
    documents: list[Document] | None = None
    finish_reason: str | None = Field(None, alias="finishReason")

    model_config = {"populate_by_name": True}


# ── Exhaustive Search ─────────────────────────────────────────────────────────

class ExhaustiveSearchRequest(BaseModel):
    query_string: str = Field(alias="queryString")
    dataset_name: str = Field(alias="datasetName")
    page_size: int = Field(20, alias="pageSize")
    pagination_token: str | None = Field(None, alias="paginationToken")
    conversation_id: str | None = Field(None, alias="conversationId")

    model_config = {"populate_by_name": True}


class ExhaustiveSearchResponse(BaseModel):
    query_uid: str | None = Field(None, alias="queryUid")
    documents: list[Document] | None = None
    total_count: int | None = Field(None, alias="totalCount")
    pagination_token: str | None = Field(None, alias="paginationToken")

    model_config = {"populate_by_name": True}


# ── Refine ────────────────────────────────────────────────────────────────────

class RefineRequest(BaseModel):
    query_uid: str = Field(alias="queryUid")
    dataset_names: list[str] = Field(alias="datasetNames")
    query_string: str = Field(alias="queryString")
    doc_ids: list[str] = Field(alias="docIds")

    model_config = {"populate_by_name": True}


class RefineResponse(BaseModel):
    response_string: str | None = Field(None, alias="responseString")
    query_uid: str | None = Field(None, alias="queryUid")
    documents: list[Document] | None = None

    model_config = {"populate_by_name": True}


# ── Upload ────────────────────────────────────────────────────────────────────

class UploadSession(BaseModel):
    upload_session_id: str = Field(alias="uploadSessionId")

    model_config = {"populate_by_name": True}


# ── Feedback ──────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    query_uid: str = Field(alias="queryUid")
    is_good: bool = Field(alias="isGood")
    feedback_text: str | None = Field(None, alias="feedbackText")

    model_config = {"populate_by_name": True}
