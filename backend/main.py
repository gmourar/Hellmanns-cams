import io, json, os, uuid, logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db import init_db, get_db, Session as SessionModel
import command_queue as q_module
import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "changeme")

_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")
    if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialized")
    yield


app = FastAPI(title="Hellmann's Cam Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class GalleryVideo(BaseModel):
    cabine_id: int
    video_url: str
    qr_url: str


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
    videos = [
        GalleryVideo(
            cabine_id=cabine_id,
            video_url=storage.public_url(session_id, cabine_id),
            qr_url=f"{storage.BASE_URL}/gallery/{session_id}/cabines/{cabine_id}/qr.svg",
        )
        for cabine_id in storage.available_cabine_ids(session_id)
    ]

    return {
        "session_id": session_id,
        "participants": participants,
        "videos": videos,
        "video_urls": [video.video_url for video in videos],
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


# ── QR endpoint ───────────────────────────────────────────────────────────────

@app.get("/gallery/{session_id}/cabines/{cabine_id}/qr.svg")
async def cabine_qr(session_id: str, cabine_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not storage.video_exists(session_id, cabine_id):
        raise HTTPException(status_code=404, detail="Video not found")

    import qrcode
    import qrcode.image.svg

    video_url = storage.public_url(session_id, cabine_id)
    qr = qrcode.QRCode(border=2)
    qr.add_data(video_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


# ── Video file serving ────────────────────────────────────────────────────────

@app.get("/videos/{session_id}/{filename}")
async def serve_video(session_id: str, filename: str):
    if storage.STORAGE_BACKEND == "s3":
        cabine_id = None
        if filename.startswith("cabine_") and filename.endswith(".mp4"):
            try:
                cabine_id = int(filename.removeprefix("cabine_").removesuffix(".mp4"))
            except ValueError:
                pass
        if cabine_id and storage.video_exists(session_id, cabine_id):
            from fastapi.responses import RedirectResponse
            return RedirectResponse(storage.public_url(session_id, cabine_id))
        raise HTTPException(status_code=404, detail="Video on S3 — use gallery URLs")
    path = storage.video_dir(session_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(path), media_type="video/mp4")
