"""
Main agent loop.

Usage:
  python -m src.agent            # starts long-poll loop
  python -m src.agent --smoke-test
"""
import asyncio, logging, os, shutil, sys, time
from pathlib import Path
from dotenv import load_dotenv
import httpx

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

API_BASE_URL     = os.environ["API_BASE_URL"].rstrip("/")
AGENT_TOKEN      = os.environ["AGENT_TOKEN"]
FFMPEG_PATH      = os.environ.get("FFMPEG_PATH", "ffmpeg")
RECORD_DURATION  = float(os.environ.get("RECORD_DURATION", "3.0"))
RECORD_PREP_DELAY = float(os.environ.get("RECORD_PREP_DELAY", "4.0"))
RECORD_START_SETTLE = float(os.environ.get("RECORD_START_SETTLE", "3.5"))
VIDEO_SPEED      = float(os.environ.get("VIDEO_SPEED", "0.30"))
RAW_DIR          = Path(os.environ.get("RAW_DIR", "./processed"))
HANDLE_TIMEOUT   = float(os.environ.get("HANDLE_TIMEOUT", "180.0"))  # seconds
S3_UPLOAD_RETRIES = int(os.environ.get("S3_UPLOAD_RETRIES", "3"))

# Parse SERIAL_TO_CABINE=serial1:1,serial2:2,serial3:3
_serial_map_raw = os.environ.get("SERIAL_TO_CABINE", "")
SERIAL_TO_CABINE = {}
for part in _serial_map_raw.split(","):
    part = part.strip()
    if ":" in part:
        serial, cabine = part.rsplit(":", 1)
        SERIAL_TO_CABINE[serial.strip()] = int(cabine.strip())

HEADERS = {"Authorization": f"Bearer {AGENT_TOKEN}"}


def _load_cameras():
    from src.camera import load_sdk, detect_cameras
    sdk = load_sdk()
    sdk.EdsInitializeSDK()
    cameras = detect_cameras(sdk, SERIAL_TO_CABINE)
    return sdk, cameras


async def _ack_session(session_id: str) -> None:
    """Ack the RECORD command so the backend won't re-enqueue it on restart."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{API_BASE_URL}/agent/sessions/{session_id}/ack",
                headers=HEADERS,
                timeout=10,
            )
        logger.info("Session %s: acked", session_id)
    except Exception as exc:
        logger.warning("Session %s: ack failed (non-fatal): %s", session_id, exc)


async def _upload_with_retry(upload_fn, out_path, session_id, cabine_id):
    """Upload to S3 with exponential backoff retries. Returns URL or raises."""
    last_exc = None
    for attempt in range(1, S3_UPLOAD_RETRIES + 1):
        try:
            url = await asyncio.to_thread(upload_fn, out_path, session_id, cabine_id)
            return url
        except Exception as exc:
            last_exc = exc
            if attempt < S3_UPLOAD_RETRIES:
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "cabine %d upload attempt %d/%d failed: %s — retrying in %ds",
                    cabine_id, attempt, S3_UPLOAD_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "cabine %d upload failed after %d attempts: %s",
                    cabine_id, S3_UPLOAD_RETRIES, exc,
                )
    raise last_exc


async def handle_record(session_id: str):
    """
    Roda toda a operação EDSDK (detect + gravar + download) em UMA ÚNICA thread
    via asyncio.to_thread. Garante thread affinity do EDSDK.
    """
    from src.camera import load_sdk, detect_cameras, record_all_cameras_sync
    from src.video import process_video

    work_dir = RAW_DIR / session_id
    raw_dir = work_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir = work_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _sdk_work():
        """Tudo que usa EDSDK roda nesta função — garante mesma thread."""
        sdk = load_sdk()
        sdk.EdsInitializeSDK()
        try:
            cameras = detect_cameras(sdk, SERIAL_TO_CABINE)
            if not cameras:
                return None, (
                    "Nenhuma câmera mapeada. Conecte as câmeras USB e atualize "
                    "SERIAL_TO_CABINE em agent/.env."
                )
            logger.info("Session %s: gravando com %d câmera(s)", session_id, len(cameras))
            results = record_all_cameras_sync(
                sdk, cameras, RECORD_DURATION, raw_dir,
                prep_delay=RECORD_PREP_DELAY,
                start_settle=RECORD_START_SETTLE,
            )
            return results, None
        finally:
            sdk.EdsTerminateSDK()

    results, sdk_error = await asyncio.to_thread(_sdk_work)

    upload_errors: list[str] = []
    successful_cabine_ids: list[int] = []

    if sdk_error:
        logger.error("Session %s: %s", session_id, sdk_error)
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{API_BASE_URL}/agent/sessions/{session_id}/complete",
                json={"status": "error", "detail": sdk_error},
                headers=HEADERS,
                timeout=10,
            )
        shutil.rmtree(work_dir, ignore_errors=True)
        return

    try:
        errors = []
        for cabine_id, result in results.items():
            if isinstance(result, Exception):
                errors.append(f"cabine {cabine_id}: {result}")
                continue

            raw_path = result
            out_path = out_dir / f"cabine_{cabine_id}.mp4"
            try:
                await process_video(
                    raw_path, out_path, FFMPEG_PATH, VIDEO_SPEED,
                    vflip=(cabine_id == 3),
                    hflip=(cabine_id == 3),
                )

                if not out_path.exists() or out_path.stat().st_size == 0:
                    errors.append(f"cabine {cabine_id}: vídeo de saída vazio ou ausente")
                    continue

                from src.s3_upload import upload_video
                try:
                    url = await _upload_with_retry(upload_video, out_path, session_id, cabine_id)
                    raw_path.unlink(missing_ok=True)
                    successful_cabine_ids.append(cabine_id)
                    logger.info("cabine %d disponível em %s", cabine_id, url)
                except Exception as exc:
                    upload_errors.append(f"cabine {cabine_id} s3: {exc}")
                    errors.append(f"cabine {cabine_id} s3: {exc}")

            except Exception as exc:
                errors.append(f"cabine {cabine_id} ffmpeg: {exc}")

        async with httpx.AsyncClient() as client:
            if errors and not successful_cabine_ids:
                # Total failure — nothing uploaded
                detail = "; ".join(errors)
                logger.error("Session %s completed with errors: %s", session_id, detail)
                await client.post(
                    f"{API_BASE_URL}/agent/sessions/{session_id}/complete",
                    json={"status": "error", "detail": detail},
                    headers=HEADERS,
                    timeout=10,
                )
            elif errors:
                # Partial success — some cabines uploaded
                detail = "; ".join(errors)
                logger.warning("Session %s partial: %s", session_id, detail)
                await client.post(
                    f"{API_BASE_URL}/agent/sessions/{session_id}/complete",
                    json={
                        "status": "ok",
                        "detail": detail,
                        "cabine_ids": successful_cabine_ids,
                    },
                    headers=HEADERS,
                    timeout=10,
                )
            else:
                logger.info("Session %s complete — all cameras OK", session_id)
                await client.post(
                    f"{API_BASE_URL}/agent/sessions/{session_id}/complete",
                    json={"status": "ok", "cabine_ids": successful_cabine_ids},
                    headers=HEADERS,
                    timeout=10,
                )
    finally:
        # Only remove work_dir if all uploads succeeded (no upload failures)
        if not upload_errors:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.info("Arquivos temporários locais removidos: %s", work_dir)
        else:
            logger.warning(
                "Mantendo %s devido a falhas de upload (%d erro(s)) — arquivos preservados para recuperação manual",
                work_dir, len(upload_errors),
            )


async def poll_loop(sdk, cameras):
    logger.info("Agent started. Polling %s/agent/poll ...", API_BASE_URL)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(
                    f"{API_BASE_URL}/agent/poll",
                    headers=HEADERS,
                    timeout=35.0,
                )
                if resp.status_code == 204:
                    # Keepalive: leitura leve para evitar timeout de sessão PTP
                    # na câmera (~30-40 s na T5i). Falhas ignoradas silenciosamente.
                    from src.camera import keepalive
                    for _, cam_ref in cameras:
                        try:
                            keepalive(sdk, cam_ref)
                        except Exception:
                            pass
                    continue
                if resp.status_code == 200:
                    command = resp.json()
                    logger.info("Received command: %s", command)
                    if command.get("type") == "RECORD":
                        session_id = command["session_id"]
                        # Ack immediately so backend won't re-enqueue on restart
                        await _ack_session(session_id)
                        try:
                            await asyncio.wait_for(
                                handle_record(session_id),
                                timeout=HANDLE_TIMEOUT,
                            )
                        except asyncio.TimeoutError:
                            logger.error(
                                "Session %s: handle_record timed out after %.0fs",
                                session_id, HANDLE_TIMEOUT,
                            )
                            try:
                                async with httpx.AsyncClient() as c:
                                    await c.post(
                                        f"{API_BASE_URL}/agent/sessions/{session_id}/complete",
                                        json={"status": "error", "detail": "timeout"},
                                        headers=HEADERS,
                                        timeout=10,
                                    )
                            except Exception:
                                pass
                    else:
                        logger.warning("Unknown command type: %s", command.get("type"))
                else:
                    logger.warning("Unexpected poll response: %s", resp.status_code)
            except httpx.ReadTimeout:
                pass
            except Exception as exc:
                logger.error("Poll error: %s", exc)
                await asyncio.sleep(5.0)


async def smoke_test():
    from src.camera import load_sdk, list_connected_cameras, detect_cameras, record_all_cameras_sync

    sdk = load_sdk()
    sdk.EdsInitializeSDK()

    connected = list_connected_cameras(sdk)
    if not connected:
        logger.error("Nenhuma câmera USB detectada. Verifique cabos e drivers Canon.")
        sdk.EdsTerminateSDK()
        sys.exit(1)

    logger.info("Câmeras conectadas (%d):", len(connected))
    for idx, (name, serial) in enumerate(connected, start=1):
        mapped = SERIAL_TO_CABINE.get(serial)
        cabine = f"cabine {mapped}" if mapped else "não mapeada"
        logger.info("  [%d] %s | serial: %s | %s", idx, name, serial, cabine)

    suggested = ",".join(
        f"{serial}:{idx}" for idx, (_, serial) in enumerate(connected, start=1)
    )
    logger.info("SERIAL_TO_CABINE sugerido: %s", suggested)

    cameras = detect_cameras(sdk, SERIAL_TO_CABINE)

    if not cameras:
        logger.error(
            "Nenhuma câmera mapeada em SERIAL_TO_CABINE. "
            "Copie a linha sugerida acima para agent/.env e rode o smoke-test de novo."
        )
        sdk.EdsTerminateSDK()
        sys.exit(1)

    logger.info("EDSDK: %d câmera(s) prontas para gravação", len(cameras))

    raw_dir = RAW_DIR / "smoke_test"
    results = await asyncio.to_thread(
        record_all_cameras_sync,
        sdk, cameras, RECORD_DURATION, raw_dir,
        RECORD_PREP_DELAY,
        RECORD_START_SETTLE,
    )

    ok_count = sum(1 for v in results.values() if not isinstance(v, Exception))
    if ok_count == len(cameras):
        logger.info("SMOKE TEST OK — %d câmeras funcionando", ok_count)
    else:
        logger.error("SMOKE TEST PARTIAL — %d/%d cameras OK", ok_count, len(cameras))

    from src.video import process_video

    for cabine_id, result in results.items():
        if isinstance(result, Exception):
            continue
        mp4_path = raw_dir / f"cabine_{cabine_id}.mp4"
        try:
            await process_video(result, mp4_path, FFMPEG_PATH, VIDEO_SPEED, vflip=(cabine_id == 3), hflip=(cabine_id == 3))
        except Exception as exc:
            logger.error("cabine %d: falha ao gerar MP4: %s", cabine_id, exc)

    sdk.EdsTerminateSDK()


def main():
    if "--smoke-test" in sys.argv:
        asyncio.run(smoke_test())
        return

    # ── Modo --session: executa UMA sessão e encerra ──────────────────────────
    # Chamado pelo runner.py. Agente é "burro": recebe session_id, grava, sobe
    # para S3, chama /complete e morre. O runner cuida do ciclo de vida.
    if "--session" in sys.argv:
        idx = sys.argv.index("--session")
        session_id = sys.argv[idx + 1]

        logger.info("=" * 60)
        logger.info("[AGENT] Modo --session: %s", session_id)
        logger.info("[AGENT] Este processo executa UMA sessão e encerra.")
        logger.info("=" * 60)

        # handle_record gerencia SDK internamente (detect + gravar + download em uma thread)
        exit_code = 0
        try:
            asyncio.run(handle_record(session_id))
            logger.info("[AGENT] Sessão %s concluída.", session_id)
        except Exception as exc:
            logger.error("[AGENT] Sessão %s falhou: %s", session_id, exc)
            exit_code = 1
        logger.info("[AGENT] Processo encerrando (código %d).", exit_code)
        sys.exit(exit_code)

    # ── Modo poll_loop: loop eterno (uso standalone sem runner) ───────────────
    sdk, cameras = _load_cameras()
    if not cameras:
        logger.error(
            "Nenhuma câmera pronta. Rode: python -m src.agent --smoke-test "
            "e configure SERIAL_TO_CABINE no .env com os seriais reais."
        )
        sdk.EdsTerminateSDK()
        sys.exit(1)
    logger.info("Agente pronto com %d câmera(s) mapeada(s)", len(cameras))
    try:
        asyncio.run(poll_loop(sdk, cameras))
    finally:
        for _, cam_ref in cameras:
            sdk.EdsCloseSession(cam_ref)
            sdk.EdsRelease(cam_ref)
        sdk.EdsTerminateSDK()


if __name__ == "__main__":
    main()
