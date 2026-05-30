import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "").lower()
VIDEO_DIR = Path(os.environ.get("VIDEO_DIR", "./videos"))
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
MAX_CABINES = int(os.environ.get("MAX_CABINES", "3"))

S3_BUCKET = os.environ.get("S3_BUCKET") or os.environ.get("AWS_BUCKET_NAME", "")
S3_REGION = os.environ.get("AWS_REGION", os.environ.get("S3_REGION", "us-east-1"))
S3_KEY_PREFIX = os.environ.get("S3_KEY_PREFIX", "videos").strip("/")
S3_PUBLIC_URL = (
    os.environ.get("S3_PUBLIC_URL") or os.environ.get("AWS_BUCKET_URL", "")
).rstrip("/")
S3_PRESIGN_URLS = os.environ.get("S3_PRESIGN_URLS", "true").lower() in (
    "1", "true", "yes",
)
S3_URL_EXPIRES_SECONDS = int(os.environ.get("S3_URL_EXPIRES_SECONDS", "86400"))

_s3_client = None


def _use_s3() -> bool:
    if STORAGE_BACKEND == "s3":
        return True
    if STORAGE_BACKEND == "local":
        return False
    # auto: bucket configurado sem STORAGE_BACKEND explícito
    return bool(S3_BUCKET)


def _s3():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client(
            "s3",
            region_name=S3_REGION,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )
    return _s3_client


def object_key(session_id: str, cabine_id: int) -> str:
    name = f"cabine_{cabine_id}.mp4"
    if S3_KEY_PREFIX:
        return f"{S3_KEY_PREFIX}/{session_id}/{name}"
    return f"{session_id}/{name}"


def video_dir(session_id: str) -> Path:
    return VIDEO_DIR / session_id


def video_path(session_id: str, cabine_id: int) -> Path:
    return video_dir(session_id) / f"cabine_{cabine_id}.mp4"


def public_url(session_id: str, cabine_id: int) -> str:
    if _use_s3():
        key = object_key(session_id, cabine_id)
        if S3_PRESIGN_URLS:
            return _s3().generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": S3_BUCKET,
                    "Key": key,
                    "ResponseContentDisposition": f"attachment; filename=bazuca-cabine-{cabine_id}.mp4",
                },
                ExpiresIn=S3_URL_EXPIRES_SECONDS,
            )
        if S3_PUBLIC_URL:
            return f"{S3_PUBLIC_URL}/{key}"
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
    return f"{BASE_URL}/videos/{session_id}/cabine_{cabine_id}.mp4"


def video_exists(session_id: str, cabine_id: int) -> bool:
    if _use_s3():
        if not S3_BUCKET:
            return False
        try:
            _s3().head_object(Bucket=S3_BUCKET, Key=object_key(session_id, cabine_id))
            return True
        except Exception:
            return False
    return video_path(session_id, cabine_id).exists()


def available_cabine_ids(session_id: str) -> list[int]:
    return [
        cabine_id
        for cabine_id in range(1, MAX_CABINES + 1)
        if video_exists(session_id, cabine_id)
    ]


# ── Async wrappers (never block the FastAPI event loop) ───────────────────────

async def video_exists_async(session_id: str, cabine_id: int) -> bool:
    return await asyncio.to_thread(video_exists, session_id, cabine_id)


async def public_url_async(session_id: str, cabine_id: int) -> str:
    return await asyncio.to_thread(public_url, session_id, cabine_id)


async def available_cabine_ids_async(session_id: str) -> list[int]:
    """Parallel S3 existence check — does not block the event loop."""
    cabine_range = range(1, MAX_CABINES + 1)
    results = await asyncio.gather(*[
        video_exists_async(session_id, c) for c in cabine_range
    ])
    return [c for c, exists in zip(cabine_range, results) if exists]
