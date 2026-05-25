import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

S3_BUCKET = os.environ.get("S3_BUCKET") or os.environ.get("AWS_BUCKET_NAME", "")
S3_REGION = os.environ.get("AWS_REGION", os.environ.get("S3_REGION", "us-east-1"))
S3_KEY_PREFIX = os.environ.get("S3_KEY_PREFIX", "videos").strip("/")
S3_PUBLIC_URL = (
    os.environ.get("S3_PUBLIC_URL") or os.environ.get("AWS_BUCKET_URL", "")
).rstrip("/")
DELETE_LOCAL_AFTER_UPLOAD = os.environ.get("DELETE_LOCAL_AFTER_UPLOAD", "true").lower() in (
    "1", "true", "yes",
)


def _enabled() -> bool:
    flag = os.environ.get("UPLOAD_TO_S3", "").lower()
    if flag in ("0", "false", "no"):
        return False
    if flag in ("1", "true", "yes"):
        return True
    return bool(S3_BUCKET)


def object_key(session_id: str, cabine_id: int) -> str:
    name = f"cabine_{cabine_id}.mp4"
    if S3_KEY_PREFIX:
        return f"{S3_KEY_PREFIX}/{session_id}/{name}"
    return f"{session_id}/{name}"


def public_url(session_id: str, cabine_id: int) -> str:
    key = object_key(session_id, cabine_id)
    if S3_PUBLIC_URL:
        return f"{S3_PUBLIC_URL}/{key}"
    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"


def upload_video(local_path: Path, session_id: str, cabine_id: int) -> str:
    if not _enabled():
        return str(local_path)
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET não configurado no .env do agente")

    import boto3

    key = object_key(session_id, cabine_id)
    client = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    logger.info("S3 upload: %s → s3://%s/%s", local_path.name, S3_BUCKET, key)
    client.upload_file(
        str(local_path),
        S3_BUCKET,
        key,
        ExtraArgs={"ContentType": "video/mp4"},
    )
    url = public_url(session_id, cabine_id)
    if DELETE_LOCAL_AFTER_UPLOAD:
        local_path.unlink(missing_ok=True)
        logger.info("Arquivo local removido após upload: %s", local_path.name)
    return url
