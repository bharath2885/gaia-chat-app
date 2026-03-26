"""Utilities for parsing Server-Sent Events (SSE) from Gaia streaming endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import AsyncIterator, Iterator

import httpx


@dataclass
class StreamChunk:
    """A single chunk from a Gaia SSE stream."""
    event: str = "message"
    data: str = ""
    parsed: dict | None = None


@dataclass
class StreamResult:
    """Accumulated result from a complete SSE stream."""
    full_text: str = ""
    documents: list[dict] = field(default_factory=list)
    query_uid: str | None = None
    conversation_id: str | None = None
    finish_reason: str | None = None


def parse_sse_line(line: str) -> tuple[str | None, str | None]:
    """Parse a single SSE line into (field, value) or (None, None) for empty lines."""
    line = line.rstrip("\n\r")
    if not line:
        return None, None
    if line.startswith(":"):
        return "comment", line[1:]
    if ":" in line:
        field_name, _, value = line.partition(":")
        return field_name.strip(), value.lstrip(" ")
    return line, ""


def iter_sse_events(lines: Iterator[str]) -> Iterator[StreamChunk]:
    """Yield StreamChunk objects from an iterator of SSE text lines."""
    current_event = "message"
    current_data_parts: list[str] = []

    for line in lines:
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
            continue

        if field_name == "event":
            current_event = value or "message"
        elif field_name == "data":
            current_data_parts.append(value or "")


async def aiter_sse_events(lines: AsyncIterator[str]) -> AsyncIterator[StreamChunk]:
    """Async version of iter_sse_events."""
    current_event = "message"
    current_data_parts: list[str] = []

    async for line in lines:
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
            continue

        if field_name == "event":
            current_event = value or "message"
        elif field_name == "data":
            current_data_parts.append(value or "")


def accumulate_stream(chunks: Iterator[StreamChunk]) -> StreamResult:
    """Process all chunks from a stream and return an accumulated result."""
    result = StreamResult()
    text_parts: list[str] = []

    for chunk in chunks:
        if chunk.parsed:
            p = chunk.parsed
            if "responseString" in p:
                text_parts.append(p["responseString"])
            if "documents" in p and p["documents"]:
                result.documents.extend(p["documents"])
            if "queryUid" in p:
                result.query_uid = p["queryUid"]
            if "conversationId" in p:
                result.conversation_id = p["conversationId"]
            if "finishReason" in p:
                result.finish_reason = p["finishReason"]
        elif chunk.data and chunk.event == "message":
            text_parts.append(chunk.data)

    result.full_text = "".join(text_parts)
    return result


async def async_accumulate_stream(
    response: httpx.Response,
) -> StreamResult:
    """Read a streaming httpx response as SSE and return the accumulated result."""
    result = StreamResult()
    text_parts: list[str] = []

    current_event = "message"
    current_data_parts: list[str] = []

    async for line in response.aiter_lines():
        field_name, value = parse_sse_line(line)

        if field_name is None:
            if current_data_parts:
                data = "\n".join(current_data_parts)
                try:
                    parsed = json.loads(data)
                    if "responseString" in parsed:
                        text_parts.append(parsed["responseString"])
                    if "documents" in parsed and parsed["documents"]:
                        result.documents.extend(parsed["documents"])
                    if "queryUid" in parsed:
                        result.query_uid = parsed["queryUid"]
                    if "conversationId" in parsed:
                        result.conversation_id = parsed["conversationId"]
                    if "finishReason" in parsed:
                        result.finish_reason = parsed["finishReason"]
                except (json.JSONDecodeError, TypeError):
                    text_parts.append(data)
            current_event = "message"
            current_data_parts = []
            continue

        if field_name == "event":
            current_event = value or "message"
        elif field_name == "data":
            current_data_parts.append(value or "")

    result.full_text = "".join(text_parts)
    return result
