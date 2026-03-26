"""FastAPI application for the Gaia Chat App example."""

import contextlib
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router
from backend.api.openai_compat import router as openai_router
from backend.middleware.request_logger import RequestLoggerMiddleware
from backend.services.session_service import cleanup_expired
from backend.settings import get_settings
from backend.utils.logger import configure_logging
from gaia_sdk.exceptions import GaiaAuthError, GaiaError, GaiaNotFoundError, GaiaRateLimitError

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging(level="DEBUG")
    settings = get_settings()
    logger.info("=== Gaia Chat App starting ===")
    logger.info("  GAIA_BASE_URL   = %s", settings.gaia_base_url)
    logger.info("  GAIA_VERIFY_SSL = %s", settings.gaia_verify_ssl)
    logger.info("  CORS origin     = %s", settings.allow_cors_origin)
    logger.info("  Session TTL     = %d min", settings.session_ttl_minutes)
    cleanup_expired()
    yield
    logger.info("=== Gaia Chat App shutting down ===")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Gaia Chat App",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allow_cors_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(GaiaError)
    async def gaia_error_handler(request: Request, exc: GaiaError) -> JSONResponse:
        if isinstance(exc, GaiaAuthError):
            status_code = exc.status_code or 401
        elif isinstance(exc, GaiaNotFoundError):
            status_code = 404
        elif isinstance(exc, GaiaRateLimitError):
            status_code = 429
        else:
            status_code = 502
        logger.error("GaiaError on %s %s — %s: %s", request.method, request.url.path, type(exc).__name__, exc)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    app.include_router(router, prefix="/api/v1")
    app.include_router(openai_router, prefix="/v1", tags=["OpenAI-compatible"])

    return app


app = create_app()
