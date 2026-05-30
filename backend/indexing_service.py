"""
Indexa os frames dos vídeos de uma sessão no AWS Rekognition.
Chamado em background após o agente completar o upload.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from db import SessionLocal, Session as SessionModel
from rekognition_service import RekognitionService, COLLECTION_ID
from frame_extractor import extrair_frames
import storage

logger = logging.getLogger(__name__)


async def indexar_sessao(session_id: str) -> None:
    """
    Background task: extrai frames dos vídeos da sessão e indexa no Rekognition.
    Cria sua própria sessão de DB (não pode reusar a do request).
    """
    logger.info("Iniciando indexação da sessão %s", session_id)
    async with SessionLocal() as db:
        result = await db.execute(
            select(SessionModel).where(SessionModel.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            logger.error("Sessão %s não encontrada para indexação", session_id)
            return

        # Prefer DB-stored cabine_ids (set by agent on complete) over S3 probing
        cabine_ids = session.cabine_ids_list
        session.indexing_status = "indexing"
        await db.commit()

    try:
        rekognition = RekognitionService()
        await rekognition.criar_colecao_se_nao_existir_async(COLLECTION_ID)

        # Fallback: probe S3 if agent didn't report cabine_ids
        if not cabine_ids:
            cabine_ids = await storage.available_cabine_ids_async(session_id)

        if not cabine_ids:
            raise ValueError(f"Nenhum vídeo disponível para a sessão {session_id}")

        # Build video URLs in parallel (async S3 presign)
        video_urls = await asyncio.gather(*[
            storage.public_url_async(session_id, c) for c in cabine_ids
        ])

        # Extract frames from all cabines in parallel
        logger.info("Extraindo frames de %d cabine(s) em paralelo", len(cabine_ids))
        frame_sets = await asyncio.gather(*[
            extrair_frames(url) for url in video_urls
        ], return_exceptions=True)

        total_indexed = 0
        for cabine_id, frames in zip(cabine_ids, frame_sets):
            if isinstance(frames, Exception):
                logger.warning("Falha ao extrair frames da cabine %d: %s", cabine_id, frames)
                continue
            if not frames:
                logger.warning("Nenhum frame extraído para cabine %d da sessão %s", cabine_id, session_id)
                continue

            external_id = f"{session_id}_c{cabine_id}"
            logger.info("Indexando %d frame(s) da cabine %d", len(frames), cabine_id)

            # Index frames for this cabine sequentially (Rekognition rate limits)
            for i, frame_bytes in enumerate(frames):
                try:
                    ok = await rekognition.indexar_face_async(frame_bytes, external_id, COLLECTION_ID)
                    if ok:
                        total_indexed += 1
                except Exception as e:
                    logger.warning("Falha ao indexar frame %d da cabine %d: %s", i, cabine_id, e)

        logger.info("Sessão %s: %d face(s) indexada(s)", session_id, total_indexed)

        async with SessionLocal() as db:
            result = await db.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                session.indexing_status = "indexed"
                session.indexed_at = datetime.utcnow()
                await db.commit()

    except Exception as e:
        logger.error("Erro ao indexar sessão %s: %s", session_id, e)
        async with SessionLocal() as db:
            result = await db.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                session.indexing_status = "error"
                session.indexing_error = str(e)
                await db.commit()
