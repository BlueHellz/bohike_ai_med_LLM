"""Async SQLAlchemy engine and session factory."""

import os
from collections.abc import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///./aegis.db")

engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _ensure_schema_patches(sync_conn) -> None:
    """Apply lightweight SQLite patches for columns added after initial deploy."""
    insp = sa.inspect(sync_conn)
    if "sessions" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sessions")}
    if "citation_depth" not in cols:
        sync_conn.execute(
            sa.text("ALTER TABLE sessions ADD COLUMN citation_depth VARCHAR DEFAULT 'simple'")
        )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_schema_patches)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
