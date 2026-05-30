import asyncio, logging, os, subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Saída vertical 9:16 (câmera montada em retrato)
OUTPUT_WIDTH = int(os.environ.get("OUTPUT_WIDTH", "1080"))
OUTPUT_HEIGHT = int(os.environ.get("OUTPUT_HEIGHT", "1920"))
# FFmpeg transpose: 1 = 90° horário, 2 = 90° anti-horário (ajuste se a imagem ficar de cabeça)
VIDEO_TRANSPOSE = os.environ.get("VIDEO_TRANSPOSE", "1").strip()
FFMPEG_PRESET = os.environ.get("FFMPEG_PRESET", "veryfast")
FFMPEG_CRF = os.environ.get("FFMPEG_CRF", "24")

# Moldura PNG com transparência — sobreposta ao vídeo processado.
# Padrão: moldura_transparente.png na raiz do projeto (um nível acima de agent/).
_default_overlay = str(Path(__file__).parent.parent.parent / "moldura_transparente.png")
OVERLAY_PATH = os.environ.get("OVERLAY_PATH", _default_overlay)


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


def _atempo_chain(speed: float) -> str:
    """Build an atempo filter chain for the target playback speed.

    atempo range starts at 0.5, so very slow speeds need multiple stages:
    0.25x speed -> atempo=0.5,atempo=0.5.
    """
    stages: list[str] = []
    while speed < 0.5 - 1e-9:
        stages.append("atempo=0.5")
        speed /= 0.5
    stages.append(f"atempo={speed:.6f}")
    return ",".join(stages)


def _portrait_filter() -> str:
    """Rotate landscape raw to portrait 9:16 and scale/crop to target resolution."""
    w, h = OUTPUT_WIDTH, OUTPUT_HEIGHT
    if VIDEO_TRANSPOSE and VIDEO_TRANSPOSE.lower() not in ("0", "none", "off"):
        rotated = f"transpose={VIDEO_TRANSPOSE},"
    else:
        rotated = ""
    return (
        f"{rotated}"
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}"
    )


async def process_video(
    raw_video: Path,
    output: Path,
    ffmpeg_path: str = "ffmpeg",
    video_speed: float = 0.75,
    vflip: bool = False,
) -> Path:
    """
    Async wrapper around FFmpeg pipeline:
    - Apply playback speed to the full clip
    - Transpose (rotate 90° for vertical mount) + crop to 9:16
    - Optional vertical flip (vflip=True) for cameras mounted upside-down
    - Overlay moldura PNG on top (alpha blending) if OVERLAY_PATH exists
    - Encode H.264 + AAC
    Returns output path.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    if video_speed <= 0:
        raise ValueError("video_speed must be greater than zero")

    atempo = _atempo_chain(video_speed)
    pts_multiplier = 1.0 / video_speed
    portrait = _portrait_filter()
    flip = "vflip," if vflip else ""
    w, h = OUTPUT_WIDTH, OUTPUT_HEIGHT

    overlay_file = Path(OVERLAY_PATH) if OVERLAY_PATH else None
    use_overlay = bool(overlay_file and overlay_file.exists())

    if use_overlay:
        logger.info("Aplicando moldura: %s", overlay_file)
        filter_complex = (
            f"[0:v]setpts={pts_multiplier:.6f}*(PTS-STARTPTS),{flip}{portrait}[vid];"
            f"[1:v]scale={w}:{h}[frame];"
            f"[vid][frame]overlay=0:0:format=auto[outv];"
            f"[0:a]asetpts=PTS-STARTPTS,{atempo}[outa]"
        )
        cmd = [
            ffmpeg_path, "-y", "-noautorotate",
            "-i", str(raw_video),
            "-i", str(overlay_file),
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-crf", FFMPEG_CRF,
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(output),
        ]
    else:
        if OVERLAY_PATH:
            logger.warning("Moldura não encontrada em %s — processando sem overlay", OVERLAY_PATH)
        filter_complex = (
            f"[0:v]setpts={pts_multiplier:.6f}*(PTS-STARTPTS),{flip}{portrait}[outv];"
            f"[0:a]asetpts=PTS-STARTPTS,{atempo}[outa]"
        )
        cmd = [
            ffmpeg_path, "-y", "-noautorotate",
            "-i", str(raw_video),
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-crf", FFMPEG_CRF,
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
