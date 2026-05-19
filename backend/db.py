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

    session_id    = Column(String, primary_key=True)
    operator_name = Column(String, nullable=False)
    participants  = Column(Text, nullable=False)   # JSON list
    status        = Column(String, nullable=False, default="recording")
    created_at    = Column(DateTime, default=datetime.utcnow)

    @property
    def participants_list(self) -> list:
        return json.loads(self.participants)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
