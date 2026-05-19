import os
from pathlib import Path

VIDEO_DIR = Path(os.environ.get("VIDEO_DIR", "./videos"))
BASE_URL   = os.environ.get("BASE_URL", "http://localhost:8000")


def video_dir(session_id: str) -> Path:
    return VIDEO_DIR / session_id


def video_path(session_id: str, cabine_id: int) -> Path:
    return video_dir(session_id) / f"cabine_{cabine_id}.mp4"


def public_url(session_id: str, cabine_id: int) -> str:
    return f"{BASE_URL}/videos/{session_id}/cabine_{cabine_id}.mp4"
