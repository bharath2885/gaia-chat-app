"""Request/response logging middleware."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Logs every incoming request and its response status + duration."""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        start = time.perf_counter()

        logger.info(
            "[%s] → %s %s",
            request_id,
            request.method,
            request.url.path,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                "[%s] ✗ UNHANDLED %s %s — %.1fms — %s: %s",
                request_id,
                request.method,
                request.url.path,
                elapsed,
                type(exc).__name__,
                exc,
            )
            raise

        elapsed = (time.perf_counter() - start) * 1000
        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            "[%s] ← %s %s %d — %.1fms",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response
