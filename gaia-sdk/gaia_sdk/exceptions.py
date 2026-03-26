"""Custom exceptions for the Gaia SDK."""

from __future__ import annotations


class GaiaError(Exception):
    """Base exception for all Gaia SDK errors."""

    def __init__(self, message: str, status_code: int | None = None, response_body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}


class GaiaAuthError(GaiaError):
    """Raised when authentication fails (401/403)."""
    pass


class GaiaNotFoundError(GaiaError):
    """Raised when a resource is not found (404)."""
    pass


class GaiaRateLimitError(GaiaError):
    """Raised when the API rate limit is exceeded (429)."""
    pass


class GaiaServerError(GaiaError):
    """Raised when the Gaia server returns a 5xx error."""
    pass


class GaiaTimeoutError(GaiaError):
    """Raised when a request times out."""
    pass


def raise_for_status(status_code: int, body: dict | None = None) -> None:
    """Raise the appropriate GaiaError subclass for an HTTP error status code."""
    body = body or {}
    message = body.get("message", body.get("errorMessage", f"HTTP {status_code}"))

    if status_code in (401, 403):
        raise GaiaAuthError(message, status_code, body)
    if status_code == 404:
        raise GaiaNotFoundError(message, status_code, body)
    if status_code == 429:
        raise GaiaRateLimitError(message, status_code, body)
    if 500 <= status_code < 600:
        raise GaiaServerError(message, status_code, body)
    if status_code >= 400:
        raise GaiaError(message, status_code, body)
