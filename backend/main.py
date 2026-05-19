import json, os, uuid, logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db import init_db, get_db, Session as SessionModel
import queue as q_module
import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "changeme")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialized")
    yield


app = FastAPI(title="Hellmann's Cam Backend", lifespan=lifespan)


# ── Auth ─────────────────────────────────────────────────────────────────────

def verify_agent(authorization: str = Header(...)):
    if authorization != f"Bearer {AGENT_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid agent token")


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    operator_name: str
    participants: list[str]


class CompleteSessionRequest(BaseModel):
    status: str          # "ok" | "error"
    detail: str | None = None


# ── Operator endpoints ────────────────────────────────────────────────────────

@app.post("/operator/sessions", status_code=201)
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    session_id = str(uuid.uuid4())[:8]
    session = SessionModel(
        session_id=session_id,
        operator_name=body.operator_name,
        participants=json.dumps(body.participants),
        status="recording",
        created_at=datetime.utcnow(),
    )
    db.add(session)
    await db.commit()
    await q_module.push({"type": "RECORD", "session_id": session_id})
    logger.info("Session %s created by %s", session_id, body.operator_name)
    return {"session_id": session_id, "status": "recording"}


# ── Agent endpoints ───────────────────────────────────────────────────────────

@app.get("/agent/poll")
async def agent_poll(_=Depends(verify_agent)):
    command = await q_module.wait(timeout=30.0)
    if command is None:
        from fastapi.responses import Response
        return Response(status_code=204)
    return command


@app.post("/agent/sessions/{session_id}/complete")
async def agent_complete(
    session_id: str,
    body: CompleteSessionRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_agent),
):
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.status == "ok":
        session.status = "ready"
    else:
        session.status = "error"
        logger.error("Session %s error: %s", session_id, body.detail)

    await db.commit()
    logger.info("Session %s → %s", session_id, session.status)
    return {"ok": True}


# ── Gallery endpoint ──────────────────────────────────────────────────────────

@app.get("/gallery/{session_id}")
async def gallery(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    participants = session.participants_list
    video_urls = []
    for i in range(1, 4):
        path = storage.video_path(session_id, i)
        if path.exists():
            video_urls.append(storage.public_url(session_id, i))

    return {
        "session_id": session_id,
        "participants": participants,
        "video_urls": video_urls,
        "status": session.status,
    }


# ── Video file serving ────────────────────────────────────────────────────────

@app.get("/videos/{session_id}/{filename}")
async def serve_video(session_id: str, filename: str):
    path = storage.video_dir(session_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(path), media_type="video/mp4")
