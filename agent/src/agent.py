"""
Main agent loop.

Usage:
  python -m src.agent            # starts long-poll loop
  python -m src.agent --smoke-test
"""
import asyncio, logging, os, sys, time
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
FRAME_PNG        = Path(os.environ.get("FRAME_PNG", "./assets/frame.png"))
FFMPEG_PATH      = os.environ.get("FFMPEG_PATH", "ffmpeg")
RECORD_DURATION  = float(os.environ.get("RECORD_DURATION", "5.0"))
VIDEO_OUTPUT_DIR = Path(os.environ.get("VIDEO_OUTPUT_DIR", "./videos"))
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


async def handle_record(sdk, cameras, session_id: str):
    from src.camera import record_all_cameras
    from src.video import process_video

    raw_dir = RAW_DIR / session_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir = VIDEO_OUTPUT_DIR / session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Record all cameras in parallel
    results = await record_all_cameras(cameras, RECORD_DURATION, raw_dir)

    errors = []
    for cabine_id, result in results.items():
        if isinstance(result, Exception):
            errors.append(f"cabine {cabine_id}: {result}")
            continue

        raw_path = result
        out_path = out_dir / f"cabine_{cabine_id}.mp4"
        try:
            await process_video(raw_path, FRAME_PNG, out_path, FFMPEG_PATH)
            raw_path.unlink(missing_ok=True)
        except Exception as exc:
            errors.append(f"cabine {cabine_id} ffmpeg: {exc}")

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
                        await handle_record(sdk, cameras, command["session_id"])
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
    from src.camera import load_sdk, detect_cameras, record_all_cameras

    sdk = load_sdk()
    sdk.EdsInitializeSDK()
    cameras = detect_cameras(sdk, SERIAL_TO_CABINE)

    if not cameras:
        logger.error("No cameras detected! Check SERIAL_TO_CABINE and USB connections.")
        sdk.EdsTerminateSDK()
        sys.exit(1)

    logger.info("EDSDK detected %d camera(s)", len(cameras))

    raw_dir = RAW_DIR / "smoke_test"
    results = await record_all_cameras(cameras, RECORD_DURATION, raw_dir)

    ok_count = sum(1 for v in results.values() if not isinstance(v, Exception))
    if ok_count == len(cameras):
        logger.info("SMOKE TEST OK — %d câmeras funcionando", ok_count)
    else:
        logger.error("SMOKE TEST PARTIAL — %d/%d cameras OK", ok_count, len(cameras))

    sdk.EdsTerminateSDK()


def main():
    if "--smoke-test" in sys.argv:
        asyncio.run(smoke_test())
        return

    sdk, cameras = _load_cameras()
    try:
        asyncio.run(poll_loop(sdk, cameras))
    finally:
        sdk.EdsTerminateSDK()


if __name__ == "__main__":
    main()
