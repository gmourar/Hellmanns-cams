import asyncio, base64, io, json, os, uuid, logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_

from db import init_db, get_db, Session as SessionModel, SessionLocal
import command_queue as q_module
import storage
from indexing_service import indexar_sessao
from rekognition_service import RekognitionService, COLLECTION_ID

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
    await _recover_pending_sessions()
    yield


async def _recover_pending_sessions():
    """
    Recupera sessões com estado inconsistente após crash/restart:
    - status='recording' → reenfileira o RECORD (agente nunca recebeu)
    - indexing_status='indexing' ou status='ready'+pending → relança indexação
    """
    _asyncio = asyncio
    async with SessionLocal() as db:
        result = await db.execute(
            select(SessionModel).where(
                or_(
                    SessionModel.status == "recording",
                    SessionModel.indexing_status == "indexing",
                    and_(
                        SessionModel.status == "ready",
                        SessionModel.indexing_status == "pending",
                    ),
                )
            )
        )
        sessions = result.scalars().all()

    for session in sessions:
        if session.status == "recording":
            if session.agent_acked_at is not None:
                # Agent already received the command — trust it to complete or timeout
                logger.warning(
                    "Sessão %s em 'recording' mas agente já deu ack em %s — aguardando conclusão",
                    session.session_id, session.agent_acked_at,
                )
                continue
            logger.warning("Recuperando sessão %s em 'recording' — reenfileirando RECORD", session.session_id)
            await q_module.push({"type": "RECORD", "session_id": session.session_id})
        elif session.status == "ready" and session.indexing_status in ("indexing", "pending"):
            logger.warning("Relançando indexação interrompida da sessão %s", session.session_id)
            _asyncio.create_task(indexar_sessao(session.session_id))

    if sessions:
        logger.info("Recuperação: %d sessão(ões) reprocessada(s)", len(sessions))
    else:
        logger.info("Nenhuma sessão pendente para recuperar")


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
    participants: list[str] = []


class CompleteSessionRequest(BaseModel):
    status: str                  # "ok" | "error"
    detail: str | None = None
    cabine_ids: list[int] = []   # cabines that uploaded successfully


class GalleryVideo(BaseModel):
    cabine_id: int
    video_url: str
    qr_url: str


class BuscarVideoRequest(BaseModel):
    imagem_base64: str  # JPEG/PNG em base64


class BuscarVideoResponse(BaseModel):
    session_id: str
    cabine_id: int
    video_url: str
    similarity: float


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

@app.post("/agent/sessions/{session_id}/ack")
async def agent_ack(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_agent),
):
    """Agent calls this immediately after receiving a RECORD command to prevent double-dispatch on restart."""
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.agent_acked_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


@app.get("/agent/sessions/current")
async def agent_current_session(db: AsyncSession = Depends(get_db), _=Depends(verify_agent)):
    """Retorna a sessão mais recente em status 'recording', sem consumir a fila."""
    result = await db.execute(
        select(SessionModel)
        .where(SessionModel.status == "recording")
        .order_by(SessionModel.created_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return Response(status_code=204)
    return {"session_id": session.session_id}


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
    background_tasks: BackgroundTasks,
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
        if body.cabine_ids:
            session.cabine_ids = json.dumps(sorted(body.cabine_ids))
        await db.commit()
        background_tasks.add_task(indexar_sessao, session_id)
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
    cabine_ids = session.cabine_ids_list
    if not cabine_ids:
        cabine_ids = await storage.available_cabine_ids_async(session_id)

    _asyncio = asyncio
    urls = await _asyncio.gather(*[
        storage.public_url_async(session_id, c) for c in cabine_ids
    ])
    videos = [
        GalleryVideo(
            cabine_id=c,
            video_url=url,
            qr_url=f"{storage.BASE_URL}/gallery/{session_id}/cabines/{c}/qr.svg",
        )
        for c, url in zip(cabine_ids, urls)
    ]

    return {
        "session_id": session_id,
        "participants": participants,
        "videos": videos,
        "video_urls": [video.video_url for video in videos],
        "status": session.status,
        "indexing_status": session.indexing_status or "pending",
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
    if not await storage.video_exists_async(session_id, cabine_id):
        raise HTTPException(status_code=404, detail="Video not found")

    import qrcode
    import qrcode.image.svg

    # Stable redirect URL — never expires, generates fresh presigned on each scan
    stable_url = f"{storage.BASE_URL}/videos/{session_id}/cabine_{cabine_id}.mp4"
    qr = qrcode.QRCode(border=2)
    qr.add_data(stable_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


# ── QR genérico do evento ─────────────────────────────────────────────────────

@app.get("/meu-video/qr.svg")
async def meu_video_qr():
    import qrcode
    import qrcode.image.svg
    import urllib.parse

    frontend_url = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")
    face_scan_url = f"{frontend_url}/meu-video"
    message = f"Acesse o link para resgatar seu vídeo: {face_scan_url}"
    whatsapp_url = f"https://wa.me/5511972936666?text={urllib.parse.quote(message)}"

    qr = qrcode.QRCode(border=2)
    qr.add_data(whatsapp_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ── Buscar vídeo por reconhecimento facial ────────────────────────────────────

@app.post("/buscar-video")
async def buscar_video(body: BuscarVideoRequest):
    try:
        image_bytes = base64.b64decode(body.imagem_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="imagem_base64 inválida")

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Imagem vazia. Tente tirar a foto novamente.")

    rekognition = RekognitionService()
    try:
        matches = await rekognition.buscar_rosto_async(image_bytes, COLLECTION_ID)
    except Exception:
        raise HTTPException(status_code=400, detail="Não foi possível detectar um rosto. Centralize seu rosto e tente novamente.")

    if not matches:
        raise HTTPException(status_code=404, detail="Rosto não encontrado. Tente novamente.")

    # Deduplica por external_image_id (vários frames da mesma cabine podem dar match)
    seen: set[str] = set()
    candidates: list[tuple[str, int, float]] = []
    for match in sorted(matches, key=lambda m: m["similarity"], reverse=True):
        external_id = match["external_image_id"]
        if external_id in seen:
            continue
        seen.add(external_id)
        try:
            parts = external_id.split("_c")
            s_id = parts[0]
            c_id = int(parts[1])
        except (IndexError, ValueError):
            continue
        candidates.append((s_id, c_id, match["similarity"]))

    # Check S3 existence and generate URLs in parallel
    _asyncio = asyncio
    exists_flags, urls = await _asyncio.gather(
        _asyncio.gather(*[storage.video_exists_async(s, c) for s, c, _ in candidates]),
        _asyncio.gather(*[storage.public_url_async(s, c) for s, c, _ in candidates]),
    )

    results = []
    for (s_id, c_id, similarity), ok, url in zip(candidates, exists_flags, urls):
        if not ok:
            continue
        results.append({
            "session_id": s_id,
            "cabine_id": c_id,
            "video_url": url,
            "similarity": similarity,
        })

    if not results:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado no storage")

    return results


# ── List all sessions ─────────────────────────────────────────────────────────

@app.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SessionModel)
        .where(SessionModel.status == "ready")
        .order_by(SessionModel.created_at.desc())
    )
    sessions = result.scalars().all()

    async def _session_videos(session: SessionModel) -> list[dict]:
        # Use DB-stored cabine_ids to avoid N+1 S3 head_object calls
        cabine_ids = session.cabine_ids_list
        if not cabine_ids:
            cabine_ids = await storage.available_cabine_ids_async(session.session_id)
        urls = await asyncio.gather(*[
            storage.public_url_async(session.session_id, c) for c in cabine_ids
        ])
        return [
            {
                "cabine_id": c,
                "video_url": url,
                "qr_url": f"{storage.BASE_URL}/gallery/{session.session_id}/cabines/{c}/qr.svg",
            }
            for c, url in zip(cabine_ids, urls)
        ]

    _asyncio = asyncio
    video_lists = await _asyncio.gather(*[_session_videos(s) for s in sessions])

    response = []
    for session, videos in zip(sessions, video_lists):
        response.append({
            "session_id": session.session_id,
            "operator_name": session.operator_name,
            "participants": session.participants_list,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "indexing_status": session.indexing_status or "pending",
            "videos": videos,
        })

    return response


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
        if cabine_id and await storage.video_exists_async(session_id, cabine_id):
            from fastapi.responses import RedirectResponse
            return RedirectResponse(await storage.public_url_async(session_id, cabine_id))
        raise HTTPException(status_code=404, detail="Video on S3 — use gallery URLs")
    path = storage.video_dir(session_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(path), media_type="video/mp4")
