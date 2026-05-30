"""FastAPI application entrypoint and middleware configuration."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.api.routes import router
from app.api.ws import ws_router
from app.database import init_db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AEGIS Medical AI Consultation Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "aegis-medical-consultation-engine",
        "api_prefix": "/api/v1",
    }
