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
_default_overlay = str(Path(__file__).parent.parent.parent / "moldura_blur_03.png")
OVERLAY_PATH = os.environ.get("OVERLAY_PATH", _default_overlay)

# Trilha sonora — substitui o áudio da câmera. Deixe vazio para manter áudio original.
_default_soundtrack = str(Path(__file__).parent.parent.parent / "30s-Ariel-Shalom-Night-Ride-_mp3cut.net_.mp3.mp3")
SOUNDTRACK_PATH = os.environ.get("SOUNDTRACK_PATH", _default_soundtrack)


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
    hflip: bool = False,
) -> Path:
    """
    Async wrapper around FFmpeg pipeline:
    - Apply playback speed to the full clip
    - Transpose (rotate 90° for vertical mount) + crop to 9:16
    - Optional flip: vflip+hflip = 180° rotation
    - Overlay moldura PNG (alpha blending) if OVERLAY_PATH exists
    - Replace camera audio with SOUNDTRACK_PATH (trimmed to video length).
      Falls back to slowed original audio if soundtrack not found.
    - Encode H.264 + AAC
    Returns output path.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    if video_speed <= 0:
        raise ValueError("video_speed must be greater than zero")

    pts_multiplier = 1.0 / video_speed
    portrait = _portrait_filter()
    flip = ("vflip," if vflip else "") + ("hflip," if hflip else "")
    w, h = OUTPUT_WIDTH, OUTPUT_HEIGHT

    overlay_file = Path(OVERLAY_PATH) if OVERLAY_PATH else None
    use_overlay = bool(overlay_file and overlay_file.exists())

    soundtrack_file = Path(SOUNDTRACK_PATH) if SOUNDTRACK_PATH else None
    use_soundtrack = bool(soundtrack_file and soundtrack_file.exists())

    if not use_overlay and OVERLAY_PATH:
        logger.warning("Moldura não encontrada em %s — sem overlay", OVERLAY_PATH)
    if not use_soundtrack and SOUNDTRACK_PATH:
        logger.warning("Trilha não encontrada em %s — usando áudio original", SOUNDTRACK_PATH)

    # ── Build inputs list ──────────────────────────────────────────────────────
    inputs: list[str] = ["-i", str(raw_video)]
    if use_overlay:
        inputs += ["-i", str(overlay_file)]
    if use_soundtrack:
        inputs += ["-i", str(soundtrack_file)]

    # ── Index each input stream ────────────────────────────────────────────────
    overlay_idx = 1 if use_overlay else None
    soundtrack_idx = (2 if use_overlay else 1) if use_soundtrack else None

    # ── Video filter_complex ───────────────────────────────────────────────────
    if use_overlay:
        logger.info("Aplicando moldura: %s", overlay_file)
        video_filters = (
            f"[0:v]setpts={pts_multiplier:.6f}*(PTS-STARTPTS),{flip}{portrait}[vid];"
            f"[{overlay_idx}:v]scale={w}:{h}[frame];"
            f"[vid][frame]overlay=0:0:format=auto[outv]"
        )
    else:
        video_filters = (
            f"[0:v]setpts={pts_multiplier:.6f}*(PTS-STARTPTS),{flip}{portrait}[outv]"
        )

    # ── Audio mapping ──────────────────────────────────────────────────────────
    if use_soundtrack:
        # Soundtrack plays at normal speed; -shortest trims it when video ends
        audio_map = ["-map", f"{soundtrack_idx}:a"]
        extra_flags = ["-shortest"]
        filter_complex = video_filters
    else:
        # Fall back: slow down original camera audio
        atempo = _atempo_chain(video_speed)
        filter_complex = (
            video_filters
            + f";[0:a]asetpts=PTS-STARTPTS,{atempo}[outa]"
        )
        audio_map = ["-map", "[outa]"]
        extra_flags = []

    cmd = [
        ffmpeg_path, "-y", "-noautorotate",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", *audio_map,
        "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-crf", FFMPEG_CRF,
        "-c:a", "aac", "-b:a", "128k",
        *extra_flags,
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
