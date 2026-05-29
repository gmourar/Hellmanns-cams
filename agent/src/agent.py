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
RECORD_DURATION  = float(os.environ.get("RECORD_DURATION", "5.0"))
RECORD_PREP_DELAY = float(os.environ.get("RECORD_PREP_DELAY", "4.0"))
RECORD_START_SETTLE = float(os.environ.get("RECORD_START_SETTLE", "3.5"))
VIDEO_SPEED      = float(os.environ.get("VIDEO_SPEED", "0.75"))
RAW_DIR          = Path(os.environ.get("RAW_DIR", "./processed"))

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


async def handle_record(sdk, session_id: str):
    from src.camera import detect_cameras, record_all_cameras
    from src.video import process_video

    cameras = detect_cameras(sdk, SERIAL_TO_CABINE)
    if not cameras:
        detail = (
            "Nenhuma câmera mapeada. Conecte as câmeras USB e atualize "
            "SERIAL_TO_CABINE em agent/.env (rode: python -m src.agent --smoke-test)."
        )
        logger.error("Session %s: %s", session_id, detail)
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{API_BASE_URL}/agent/sessions/{session_id}/complete",
                json={"status": "error", "detail": detail},
                headers=HEADERS,
                timeout=10,
            )
        return

    logger.info("Session %s: gravando com %d câmera(s)", session_id, len(cameras))

    work_dir = RAW_DIR / session_id
    raw_dir = work_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir = work_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Record all cameras in parallel
        results = await record_all_cameras(
            sdk, cameras, RECORD_DURATION, raw_dir,
            prep_delay=RECORD_PREP_DELAY,
            start_settle=RECORD_START_SETTLE,
        )

        errors = []
        for cabine_id, result in results.items():
            if isinstance(result, Exception):
                errors.append(f"cabine {cabine_id}: {result}")
                continue

            raw_path = result
            out_path = out_dir / f"cabine_{cabine_id}.mp4"
            try:
                await process_video(raw_path, out_path, FFMPEG_PATH, VIDEO_SPEED)
                raw_path.unlink(missing_ok=True)
                if not out_path.exists() or out_path.stat().st_size == 0:
                    errors.append(f"cabine {cabine_id}: vídeo de saída vazio ou ausente")
                else:
                    from src.s3_upload import upload_video
                    try:
                        url = await asyncio.to_thread(
                            upload_video, out_path, session_id, cabine_id,
                        )
                        logger.info("cabine %d disponível em %s", cabine_id, url)
                    except Exception as exc:
                        errors.append(f"cabine {cabine_id} s3: {exc}")
            except Exception as exc:
                errors.append(f"cabine {cabine_id} ffmpeg: {exc}")

        if not results:
            errors.append("nenhuma câmera gravou")

        async with httpx.AsyncClient() as client:
            if errors:
                detail = "; ".join(errors)
                logger.error("Session %s completed with errors: %s", session_id, detail)
                await client.post(
                    f"{API_BASE_URL}/agent/sessions/{session_id}/complete",
                    json={"status": "error", "detail": detail},
                    headers=HEADERS,
                    timeout=10,
                )
            else:
                logger.info("Session %s complete — all cameras OK", session_id)
                await client.post(
                    f"{API_BASE_URL}/agent/sessions/{session_id}/complete",
                    json={"status": "ok"},
                    headers=HEADERS,
                    timeout=10,
                )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.info("Arquivos temporários locais removidos: %s", work_dir)


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
                    continue
                if resp.status_code == 200:
                    command = resp.json()
                    logger.info("Received command: %s", command)
                    if command.get("type") == "RECORD":
                        await handle_record(sdk, command["session_id"])
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
    from src.camera import load_sdk, list_connected_cameras, detect_cameras, record_all_cameras

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
    results = await record_all_cameras(
        sdk, cameras, RECORD_DURATION, raw_dir,
        prep_delay=RECORD_PREP_DELAY,
        start_settle=RECORD_START_SETTLE,
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
            await process_video(result, mp4_path, FFMPEG_PATH, VIDEO_SPEED)
        except Exception as exc:
            logger.error("cabine %d: falha ao gerar MP4: %s", cabine_id, exc)

    sdk.EdsTerminateSDK()


def main():
    if "--smoke-test" in sys.argv:
        asyncio.run(smoke_test())
        return

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
        sdk.EdsTerminateSDK()


if __name__ == "__main__":
    main()
