import json, os
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./hellmanns.db")

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    session_id      = Column(String, primary_key=True)
    operator_name   = Column(String, nullable=False)
    participants    = Column(Text, nullable=False)   # JSON list
    status          = Column(String, nullable=False, default="recording")
    created_at      = Column(DateTime, default=datetime.utcnow)
    indexing_status = Column(String, default="pending")  # pending | indexing | indexed | error
    indexed_at      = Column(DateTime, nullable=True)
    indexing_error  = Column(Text, nullable=True)

    @property
    def participants_list(self) -> list:
        return json.loads(self.participants)


async def _run_migrations(conn):
    from sqlalchemy import text
    result = await conn.execute(text("PRAGMA table_info(sessions)"))
    existing_cols = {row[1] for row in result.fetchall()}
    if "indexing_status" not in existing_cols:
        await conn.execute(text("ALTER TABLE sessions ADD COLUMN indexing_status TEXT DEFAULT 'pending'"))
    if "indexed_at" not in existing_cols:
        await conn.execute(text("ALTER TABLE sessions ADD COLUMN indexed_at DATETIME"))
    if "indexing_error" not in existing_cols:
        await conn.execute(text("ALTER TABLE sessions ADD COLUMN indexing_error TEXT"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
        # WAL mode: leituras simultâneas durante writes (evita bloqueio durante indexação)
        from sqlalchemy import text
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
