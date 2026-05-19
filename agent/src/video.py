import asyncio, logging, subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def get_duration(path: Path) -> float:
    """Uses ffprobe to get video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    return float(out)


async def process_video(
    raw_video: Path,
    frame_png: Path,
    output: Path,
    ffmpeg_path: str = "ffmpeg",
    slowmo_factor: float = 4.0,
) -> Path:
    """
    Async wrapper around FFmpeg pipeline:
    - Split video in 3 thirds
    - Apply slowmo (4x) to middle third
    - Transpose (rotate 90° clockwise, portrait output)
    - Overlay frame PNG
    - Encode H.264 + AAC
    Returns output path.
    """
    output.parent.mkdir(parents=True, exist_ok=True)

    duration = await asyncio.to_thread(get_duration, raw_video)
    t1 = duration / 3
    t2 = 2 * duration / 3
    f  = slowmo_factor

    filter_complex = (
        f"[0:v]split=3[va][vb][vc];"
        f"[va]trim=0:{t1:.6f},setpts=PTS-STARTPTS[s1];"
        f"[vb]trim={t1:.6f}:{t2:.6f},setpts={f:.4f}*(PTS-STARTPTS)[s2];"
        f"[vc]trim={t2:.6f}:{duration:.6f},setpts=PTS-STARTPTS[s3];"
        f"[s1][s2][s3]concat=n=3:v=1:a=0[joined];"
        f"[joined]transpose=1,scale=1080:1920[geo];"
        f"[geo][1:v]overlay=0:0[outv];"
        f"[0:a]asplit=3[aa][ab][ac];"
        f"[aa]atrim=0:{t1:.6f},asetpts=PTS-STARTPTS[sa1];"
        f"[ab]atrim={t1:.6f}:{t2:.6f},asetpts=PTS-STARTPTS,atempo=0.25[sa2];"
        f"[ac]atrim={t2:.6f}:{duration:.6f},asetpts=PTS-STARTPTS[sa3];"
        f"[sa1][sa2][sa3]concat=n=3:v=0:a=1[outa]"
    )

    cmd = [
        ffmpeg_path, "-y", "-noautorotate",
        "-i", str(raw_video),
        "-i", str(frame_png),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output),
    ]

    logger.info("FFmpeg processing: %s → %s", raw_video.name, output.name)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg failed for {raw_video.name}:\n{stderr.decode()[-2000:]}")

    logger.info("FFmpeg done: %s", output.name)
    return output
