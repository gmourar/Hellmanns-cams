"""
Extrai frames de vídeo via ffmpeg para uso no Rekognition.
Baixa o vídeo para um arquivo temporário antes de extrair os frames,
garantindo compatibilidade com URLs S3 presigned no Windows.
"""
import asyncio
import logging
import os
import tempfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
FRAME_TIMESTAMPS = [0.5, 1.5, 2.5, 3.5, 4.5]  # 5 frames ao longo do vídeo


async def extrair_frames(video_source: str | Path) -> list[bytes]:
    """
    Extrai frames JPEG do vídeo nos timestamps configurados.
    video_source: URL HTTPS (presigned S3) ou caminho local absoluto.
    Retorna lista de bytes JPEG (pode ser vazia se algo falhar).
    """
    source = str(video_source)

    # Se for URL HTTP/HTTPS, baixa para arquivo temporário primeiro
    if source.startswith("http://") or source.startswith("https://"):
        return await _extrair_de_url(source)

    # Arquivo local: usa diretamente
    return await _extrair_de_arquivo(source)


async def _extrair_de_url(url: str) -> list[bytes]:
    """Baixa o vídeo via httpx e extrai frames do arquivo temporário."""
    logger.info("Baixando vídeo para extração de frames (%s...)", url[:80])
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(tmp_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 256):
                        f.write(chunk)

        size_mb = Path(tmp_path).stat().st_size / (1024 * 1024)
        logger.info("Vídeo baixado: %.1f MB → %s", size_mb, tmp_path)
        return await _extrair_de_arquivo(tmp_path)

    except Exception as e:
        logger.error("Falha ao baixar vídeo: %s", e)
        return []
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _extrair_de_arquivo(file_path: str) -> list[bytes]:
    """Extrai frames de um arquivo local via ffmpeg."""
    frames: list[bytes] = []
    for ts in FRAME_TIMESTAMPS:
        try:
            frame_bytes = await _extrair_frame(file_path, ts)
            if frame_bytes:
                frames.append(frame_bytes)
                logger.info("Frame extraído em %ss (%d bytes)", ts, len(frame_bytes))
            else:
                logger.warning("Frame vazio em %ss — nenhuma face nesse momento?", ts)
        except Exception as e:
            logger.warning("Falha ao extrair frame em %ss: %s", ts, e)
    return frames


async def _extrair_frame(file_path: str, timestamp: float) -> bytes | None:
    cmd = [
        FFMPEG_PATH,
        "-ss", str(timestamp),
        "-i", file_path,
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-q:v", "2",
        "pipe:1",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,  # captura erros para log
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    except asyncio.TimeoutError:
        proc.kill()
        logger.error("ffmpeg timeout ao extrair frame em %ss", timestamp)
        return None

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()[-300:]  # últimas 300 chars
        logger.error("ffmpeg falhou (code %d) em %ss: %s", proc.returncode, timestamp, err_msg)
        return None

    if not stdout:
        logger.warning("ffmpeg retornou stdout vazio em %ss", timestamp)
        return None

    return stdout
