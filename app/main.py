"""FastAPI application entrypoint and middleware configuration."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Load .env with override=True so empty shell variables do not shadow file values.
load_dotenv(_PROJECT_ROOT / ".env", override=True)

from app.api.local_tts_routes import router as local_tts_router
from app.api.routes import router
from app.api.ws import ws_router
from app.database import init_db
from app.llm_errors import LlmConfigurationError, LlmUpstreamError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

if (os.getenv("DEEPSEEK_API_KEY") or "").strip():
    logger.info("DeepSeek configured")
else:
    logger.warning(
        "DEEPSEEK_API_KEY not set — configure the key in %s/.env and restart the server "
        "(or set DEV_STUB_LLM=true for local test-ui)",
        _PROJECT_ROOT,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if os.getenv("LOCAL_TTS_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        try:
            from local_tts import synthesize

            synthesize("Warm up.")
            logger.info("Local Piper TTS warmed up")
        except Exception as exc:
            logger.warning("Local Piper TTS warmup skipped: %s", exc)
    yield


app = FastAPI(title="AEGIS Medical AI Consultation Engine", lifespan=lifespan)


def _expose_error_detail() -> bool:
    env = os.getenv("ENV", os.getenv("APP_ENV", "development")).strip().lower()
    if env in ("production", "prod"):
        return False
    if os.getenv("EXPOSE_LLM_ERRORS", "").lower() in ("1", "true", "yes"):
        return True
    return env in ("development", "dev", "local", "test")


@app.exception_handler(LlmConfigurationError)
async def llm_configuration_handler(_request: Request, exc: LlmConfigurationError):
    detail = str(exc) if _expose_error_detail() else "LLM is not configured"
    return JSONResponse(status_code=503, content={"detail": detail})


@app.exception_handler(LlmUpstreamError)
async def llm_upstream_handler(_request: Request, exc: LlmUpstreamError):
    logger.error("LLM upstream error: %s", exc)
    detail = str(exc) if _expose_error_detail() else "LLM upstream error"
    return JSONResponse(status_code=502, content={"detail": detail})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(local_tts_router, prefix="/api/v1")
app.include_router(ws_router)

# Temporary manual test UI mount; remove test-ui/ and this block before production.
_TEST_UI_DIR = Path(__file__).resolve().parent.parent / "test-ui"


def _test_ui_enabled() -> bool:
    raw = os.getenv("TEST_UI_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes")


if _test_ui_enabled() and _TEST_UI_DIR.is_dir():
    app.mount(
        "/test-ui",
        StaticFiles(directory=str(_TEST_UI_DIR), html=True),
        name="test-ui",
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "aegis-medical-consultation-engine",
        "api_prefix": "/api/v1",
        "deepseek_configured": bool((os.getenv("DEEPSEEK_API_KEY") or "").strip()),
    }
