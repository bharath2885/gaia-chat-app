"""Cohesity Gaia Python SDK — a lightweight client for the Gaia RAG API."""

from gaia_sdk.client import GaiaClient
from gaia_sdk.models import (
    AskRequest,
    AskResponse,
    Dataset,
    DatasetDetails,
    Document,
    ExhaustiveSearchRequest,
    ExhaustiveSearchResponse,
    RefineRequest,
    RefineResponse,
    UploadSession,
)
from gaia_sdk.exceptions import (
    GaiaError,
    GaiaAuthError,
    GaiaNotFoundError,
    GaiaRateLimitError,
    GaiaServerError,
)

__version__ = "0.1.0"

__all__ = [
    "GaiaClient",
    "AskRequest",
    "AskResponse",
    "Dataset",
    "DatasetDetails",
    "Document",
    "ExhaustiveSearchRequest",
    "ExhaustiveSearchResponse",
    "RefineRequest",
    "RefineResponse",
    "UploadSession",
    "GaiaError",
    "GaiaAuthError",
    "GaiaNotFoundError",
    "GaiaRateLimitError",
    "GaiaServerError",
]
