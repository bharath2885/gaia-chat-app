"""Authentication helpers for the Gaia SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class GaiaAuth:
    """Holds authentication credentials for the Gaia API.

    The API key is the primary authentication mechanism. An optional security
    context can be provided for multi-tenant or privileged operations.
    """

    api_key: str
    security_context: str | None = None

    @classmethod
    def from_env(cls) -> GaiaAuth:
        """Create GaiaAuth from environment variables.

        Reads:
            GAIA_API_KEY (required)
            GAIA_SECURITY_CTX (optional)
        """
        api_key = os.environ.get("GAIA_API_KEY")
        if not api_key:
            raise ValueError(
                "GAIA_API_KEY environment variable is required. "
                "Set it to your Cohesity Gaia API key."
            )
        return cls(
            api_key=api_key,
            security_context=os.environ.get("GAIA_SECURITY_CTX"),
        )

    def to_headers(self) -> dict[str, str]:
        """Return HTTP headers for Gaia API authentication."""
        headers = {"apiKey": self.api_key}
        if self.security_context:
            headers["X-GAIA-SECURITY-CTX"] = self.security_context
        return headers
