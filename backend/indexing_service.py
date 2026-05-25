"""
Indexa os frames dos vídeos de uma sessão no AWS Rekognition.
Chamado em background após o agente completar o upload.
"""
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

        session.indexing_status = "indexing"
        await db.commit()

    try:
        rekognition = RekognitionService()
        rekognition.criar_colecao_se_nao_existir(COLLECTION_ID)

        cabine_ids = storage.available_cabine_ids(session_id)
        if not cabine_ids:
            raise ValueError(f"Nenhum vídeo disponível para a sessão {session_id}")

        total_indexed = 0
        for cabine_id in cabine_ids:
            video_url = storage.public_url(session_id, cabine_id)
            external_id = f"{session_id}_c{cabine_id}"

            logger.info("Extraindo frames de cabine %d (%s...)", cabine_id, video_url[:60])
            frames = await extrair_frames(video_url)

            if not frames:
                logger.warning("Nenhum frame extraído para cabine %d da sessão %s", cabine_id, session_id)
                continue

            for i, frame_bytes in enumerate(frames):
                try:
                    ok = rekognition.indexar_face(frame_bytes, external_id, COLLECTION_ID)
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
