"""Pydantic request/response models for the Chat App API."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    api_key: str = Field(..., alias="apiKey")
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("api_key", mode="before")
    @classmethod
    def strip_api_key(cls, v: str) -> str:
        return v.strip()


class LoginResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    model_config = ConfigDict(populate_by_name=True)


class AskRequest(BaseModel):
    query: str
    dataset_names: List[str] = Field(..., alias="datasetNames")
    conversation_id: Optional[str] = Field(default=None, alias="conversationId")
    model_config = ConfigDict(populate_by_name=True)


class AskResponse(BaseModel):
    """Thin pass-through of the Gaia /ask response."""

    response_string: str = Field(default="", alias="responseString")
    query_uid: str = Field(default="", alias="queryUid")
    conversation_id: Optional[str] = Field(default=None, alias="conversationId")
    documents: Optional[List[dict]] = None
    model_config = ConfigDict(populate_by_name=True)


class DatasetItem(BaseModel):
    name: str = ""
    dataset_id: str = Field(default="", alias="datasetId")
    description: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True)


class DatasetListResponse(BaseModel):
    datasets: List[DatasetItem] = Field(default_factory=list)
