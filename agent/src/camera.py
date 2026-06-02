import os, ctypes, time, logging, threading
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Lock global: EDSDK/USB não suporta EdsOpenSession/EdsCloseSession simultâneos
# em múltiplas câmeras — serializar evita 0x000000C0 por contenção de barramento.
_session_lock = threading.Lock()

# ── EDSDK constants ──────────────────────────────────────────────────────────
EDS_ERR_OK                   = 0x00000000
EDS_ERR_DEVICE_BUSY          = 0x00000083
EDS_ERR_SESSION_ALREADY_OPEN = 0x00000021

kEdsPropID_BodyIDEx         = 0x00000015
kEdsPropID_Evf_OutputDevice = 0x00000500
kEdsPropID_Evf_Mode         = 0x00000501
kEdsPropID_Record           = 0x00000510

kEdsEvfOutputDevice_PC = 2
RECORD_BEGIN = 4
RECORD_END   = 0

EdsError   = ctypes.c_uint32
EdsBaseRef = ctypes.c_void_p

class EdsDeviceInfo(ctypes.Structure):
    _fields_ = [
        ("szPortName",          ctypes.c_char * 256),
        ("szDeviceDescription", ctypes.c_char * 256),
        ("deviceSubType",       ctypes.c_uint32),
        ("reserved",            ctypes.c_uint32),
    ]

class EdsDirectoryItemInfo(ctypes.Structure):
    _fields_ = [
        ("size",       ctypes.c_uint64),
        ("isFolder",   ctypes.c_int32),
        ("groupID",    ctypes.c_uint32),
        ("option",     ctypes.c_uint32),
        ("szFileName", ctypes.c_char * 256),
        ("format",     ctypes.c_uint32),
        ("dateTime",   ctypes.c_uint32),
    ]

VIDEO_EXTENSIONS = {".mov", ".avi", ".mp4", ".mts", ".m2ts"}

@dataclass
class Camera:
    name: str
    serial: str
    cabine_id: int


def load_sdk() -> ctypes.CDLL:
    edsdk_dir = Path(__file__).parent.parent / "edsdk"
    os.add_dll_directory(str(edsdk_dir))
    sdk = ctypes.CDLL(str(edsdk_dir / "EDSDK.dll"))
    setup_sdk_signatures(sdk)
    return sdk


def setup_sdk_signatures(sdk: ctypes.CDLL) -> None:
    sdk.EdsInitializeSDK.restype  = EdsError
    sdk.EdsTerminateSDK.restype   = EdsError
    sdk.EdsRelease.restype        = ctypes.c_uint32
    sdk.EdsRelease.argtypes       = [EdsBaseRef]
    sdk.EdsGetCameraList.restype  = EdsError
    sdk.EdsGetCameraList.argtypes = [ctypes.POINTER(EdsBaseRef)]
    sdk.EdsGetChildCount.restype  = EdsError
    sdk.EdsGetChildCount.argtypes = [EdsBaseRef, ctypes.POINTER(ctypes.c_int32)]
    sdk.EdsGetChildAtIndex.restype  = EdsError
    sdk.EdsGetChildAtIndex.argtypes = [EdsBaseRef, ctypes.c_int32, ctypes.POINTER(EdsBaseRef)]
    sdk.EdsGetDeviceInfo.restype  = EdsError
    sdk.EdsGetDeviceInfo.argtypes = [EdsBaseRef, ctypes.POINTER(EdsDeviceInfo)]
    sdk.EdsOpenSession.restype    = EdsError
    sdk.EdsOpenSession.argtypes   = [EdsBaseRef]
    sdk.EdsCloseSession.restype   = EdsError
    sdk.EdsCloseSession.argtypes  = [EdsBaseRef]
    sdk.EdsGetPropertySize.restype  = EdsError
    sdk.EdsGetPropertySize.argtypes = [EdsBaseRef, ctypes.c_uint32, ctypes.c_int32,
                                        ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
    sdk.EdsGetPropertyData.restype  = EdsError
    sdk.EdsGetPropertyData.argtypes = [EdsBaseRef, ctypes.c_uint32, ctypes.c_int32,
                                        ctypes.c_uint32, ctypes.c_void_p]
    sdk.EdsSetPropertyData.restype  = EdsError
    sdk.EdsSetPropertyData.argtypes = [EdsBaseRef, ctypes.c_uint32, ctypes.c_int32,
                                        ctypes.c_uint32, ctypes.c_void_p]
    sdk.EdsCreateMemoryStream.restype  = EdsError
    sdk.EdsCreateMemoryStream.argtypes = [ctypes.c_uint64, ctypes.POINTER(EdsBaseRef)]
    sdk.EdsCreateEvfImageRef.restype   = EdsError
    sdk.EdsCreateEvfImageRef.argtypes  = [EdsBaseRef, ctypes.POINTER(EdsBaseRef)]
    sdk.EdsDownloadEvfImage.restype    = EdsError
    sdk.EdsDownloadEvfImage.argtypes   = [EdsBaseRef, EdsBaseRef]
    sdk.EdsGetDirectoryItemInfo.restype  = EdsError
    sdk.EdsGetDirectoryItemInfo.argtypes = [EdsBaseRef, ctypes.POINTER(EdsDirectoryItemInfo)]
    sdk.EdsDownload.restype         = EdsError
    sdk.EdsDownload.argtypes        = [EdsBaseRef, ctypes.c_uint64, EdsBaseRef]
    sdk.EdsDownloadComplete.restype = EdsError
    sdk.EdsDownloadComplete.argtypes = [EdsBaseRef]
    sdk.EdsDownloadCancel.restype   = EdsError
    sdk.EdsDownloadCancel.argtypes  = [EdsBaseRef]
    sdk.EdsCreateFileStream.restype  = EdsError
    sdk.EdsCreateFileStream.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32,
                                         ctypes.POINTER(EdsBaseRef)]


def _open_session_with_retry(sdk, cam_ref, max_tries=5) -> bool:
    for attempt in range(max_tries):
        err = sdk.EdsOpenSession(cam_ref)
        if err == EDS_ERR_OK or err == EDS_ERR_SESSION_ALREADY_OPEN:
            return True
        logger.warning("EdsOpenSession attempt %d failed: 0x%08X", attempt + 1, err)
        time.sleep(2.0)
    return False


def _read_serial(sdk, cam_ref) -> str:
    prop_type = ctypes.c_uint32()
    prop_size = ctypes.c_uint32()
    err = sdk.EdsGetPropertySize(cam_ref, kEdsPropID_BodyIDEx, 0,
                                  ctypes.byref(prop_type), ctypes.byref(prop_size))
    if err != EDS_ERR_OK or prop_size.value == 0:
        return ""
    buf = ctypes.create_string_buffer(prop_size.value)
    err = sdk.EdsGetPropertyData(cam_ref, kEdsPropID_BodyIDEx, 0, prop_size.value, buf)
    if err != EDS_ERR_OK:
        return ""
    return buf.value.decode("ascii", errors="replace").strip("\x00")


def list_connected_cameras(sdk) -> list[tuple[str, str]]:
    """Returns (name, serial) for every camera reachable via USB."""
    camera_list_ref = EdsBaseRef()
    err = sdk.EdsGetCameraList(ctypes.byref(camera_list_ref))
    if err != EDS_ERR_OK:
        raise RuntimeError(f"EdsGetCameraList failed: 0x{err:08X}")

    count = ctypes.c_int32(0)
    sdk.EdsGetChildCount(camera_list_ref, ctypes.byref(count))

    found: list[tuple[str, str]] = []
    for i in range(count.value):
        cam_ref = EdsBaseRef()
        sdk.EdsGetChildAtIndex(camera_list_ref, i, ctypes.byref(cam_ref))

        info = EdsDeviceInfo()
        sdk.EdsGetDeviceInfo(cam_ref, ctypes.byref(info))
        name = info.szDeviceDescription.decode("ascii", errors="replace")

        if not _open_session_with_retry(sdk, cam_ref):
            logger.error("Could not open session for camera %d (%s)", i, name)
            sdk.EdsRelease(cam_ref)
            continue

        serial = _read_serial(sdk, cam_ref)
        sdk.EdsCloseSession(cam_ref)
        sdk.EdsRelease(cam_ref)
        found.append((name, serial))

    sdk.EdsRelease(camera_list_ref)
    return found


def detect_cameras(sdk, serial_to_cabine: dict) -> list:
    """Returns list of (Camera, cam_ref) tuples for cameras whose serial is mapped."""
    camera_list_ref = EdsBaseRef()
    err = sdk.EdsGetCameraList(ctypes.byref(camera_list_ref))
    if err != EDS_ERR_OK:
        raise RuntimeError(f"EdsGetCameraList failed: 0x{err:08X}")

    count = ctypes.c_int32(0)
    sdk.EdsGetChildCount(camera_list_ref, ctypes.byref(count))

    cameras = []
    for i in range(count.value):
        cam_ref = EdsBaseRef()
        sdk.EdsGetChildAtIndex(camera_list_ref, i, ctypes.byref(cam_ref))

        info = EdsDeviceInfo()
        sdk.EdsGetDeviceInfo(cam_ref, ctypes.byref(info))
        name = info.szDeviceDescription.decode("ascii", errors="replace")

        if not _open_session_with_retry(sdk, cam_ref):
            logger.error("Could not open session for camera %d (%s)", i, name)
            sdk.EdsRelease(cam_ref)
            continue

        serial = _read_serial(sdk, cam_ref)
        sdk.EdsCloseSession(cam_ref)

        cabine_id = serial_to_cabine.get(serial)
        if cabine_id is None:
            logger.warning("Serial %s not in SERIAL_TO_CABINE map — skipping", serial)
            sdk.EdsRelease(cam_ref)
            continue

        cam = Camera(name=name, serial=serial, cabine_id=cabine_id)
        cameras.append((cam, cam_ref))
        logger.info("Camera %s (serial: %s) → cabine %d", name, serial, cabine_id)

    sdk.EdsRelease(camera_list_ref)
    return cameras


def _snapshot_sd_files(sdk, cam_ref) -> set:
    """Returns set of filenames currently on SD card."""
    files = set()
    vols_ref = EdsBaseRef()
    if sdk.EdsGetChildCount(cam_ref, ctypes.byref(ctypes.c_int32())) != EDS_ERR_OK:
        return files
    count = ctypes.c_int32(0)
    sdk.EdsGetChildCount(cam_ref, ctypes.byref(count))
    for i in range(count.value):
        vol_ref = EdsBaseRef()
        sdk.EdsGetChildAtIndex(cam_ref, i, ctypes.byref(vol_ref))
        for item_ref, fname, _ in walk_items(sdk, vol_ref):
            files.add(fname)
            sdk.EdsRelease(item_ref)
        sdk.EdsRelease(vol_ref)
    return files


def walk_items(sdk, parent_ref, depth=0):
    """Returns list of (item_ref, filename, size) for video files."""
    if depth > 8:
        return []
    count = ctypes.c_int32(0)
    sdk.EdsGetChildCount(parent_ref, ctypes.byref(count))
    results = []
    for i in range(count.value):
        item_ref = EdsBaseRef()
        sdk.EdsGetChildAtIndex(parent_ref, i, ctypes.byref(item_ref))
        info = EdsDirectoryItemInfo()
        if sdk.EdsGetDirectoryItemInfo(item_ref, ctypes.byref(info)) != EDS_ERR_OK:
            sdk.EdsRelease(item_ref)
            continue
        fname = info.szFileName.decode("ascii", errors="replace")
        if info.isFolder:
            results.extend(walk_items(sdk, item_ref, depth + 1))
            sdk.EdsRelease(item_ref)
        elif Path(fname).suffix.lower() in VIDEO_EXTENSIONS:
            results.append((item_ref, fname, info.size))
        else:
            sdk.EdsRelease(item_ref)
    return results


def _enable_liveview_and_wait_standby(sdk, cam_ref, timeout=5.0) -> bool:
    """Enables EVF mode, routes to PC, waits until a frame can be downloaded."""
    val_1 = ctypes.c_uint32(1)
    val_2 = ctypes.c_uint32(kEdsEvfOutputDevice_PC)
    sdk.EdsSetPropertyData(cam_ref, kEdsPropID_Evf_Mode, 0, 4, ctypes.byref(val_1))
    sdk.EdsSetPropertyData(cam_ref, kEdsPropID_Evf_OutputDevice, 0, 4, ctypes.byref(val_2))

    deadline = time.time() + timeout
    while time.time() < deadline:
        stream_ref = EdsBaseRef()
        evf_ref    = EdsBaseRef()
        ok = False
        try:
            if sdk.EdsCreateMemoryStream(0, ctypes.byref(stream_ref)) == EDS_ERR_OK:
                if sdk.EdsCreateEvfImageRef(stream_ref, ctypes.byref(evf_ref)) == EDS_ERR_OK:
                    err = sdk.EdsDownloadEvfImage(cam_ref, evf_ref)
                    ok = (err == EDS_ERR_OK)
        finally:
            if evf_ref:
                sdk.EdsRelease(evf_ref)
            if stream_ref:
                sdk.EdsRelease(stream_ref)
        if ok:
            return True
        time.sleep(0.5)
    return False


def _stop_recording_with_retry(sdk, cam_ref, max_tries=20) -> bool:
    val = ctypes.c_uint32(RECORD_END)
    for attempt in range(max_tries):
        err = sdk.EdsSetPropertyData(cam_ref, kEdsPropID_Record, 0, 4, ctypes.byref(val))
        if err == EDS_ERR_OK:
            return True
        logger.warning("Stop recording attempt %d failed: 0x%08X", attempt + 1, err)
        time.sleep(attempt * 0.5)
    return False


def keepalive(sdk, cam_ref) -> None:
    """Envia um comando PTP leve para evitar que a câmera feche a sessão por inatividade.
    Chamado pelo poll_loop a cada resposta 204 (sem comando pendente).
    Falhas são ignoradas silenciosamente (sessão pode não estar aberta ainda).
    """
    prop_type = ctypes.c_uint32()
    prop_size = ctypes.c_uint32()
    sdk.EdsGetPropertySize(cam_ref, kEdsPropID_BodyIDEx, 0,
                           ctypes.byref(prop_type), ctypes.byref(prop_size))


def _find_new_video(sdk, cam_ref, known_files: set):
    """Returns (item_ref, filename, size) for the first new video file found."""
    count = ctypes.c_int32(0)
    sdk.EdsGetChildCount(cam_ref, ctypes.byref(count))
    for i in range(count.value):
        vol_ref = EdsBaseRef()
        sdk.EdsGetChildAtIndex(cam_ref, i, ctypes.byref(vol_ref))
        items = walk_items(sdk, vol_ref)
        sdk.EdsRelease(vol_ref)
        for item_ref, fname, size in items:
            if fname not in known_files:
                return item_ref, fname, size
            sdk.EdsRelease(item_ref)
    return None, None, None


def record_one_camera(
    sdk,
    cam_ref,
    camera: Camera,
    duration_s: float,
    dest_dir: Path,
    prep_delay: float = 0.0,
    start_settle: float = 0.0,
) -> Path:
    """
    Blocking. Runs in a thread. Returns path to downloaded raw video.
    Raises on unrecoverable error.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Serializar close+open: EDSDK não suporta operações de sessão simultâneas
    # em múltiplas câmeras — sem o lock, 3 câmeras em paralelo causam 0x000000C0.
    logger.info("cabine %d: aguardando lock de sessão...", camera.cabine_id)
    with _session_lock:
        logger.info("cabine %d: lock adquirido — fechando sessão...", camera.cabine_id)
        err_close = sdk.EdsCloseSession(cam_ref)
        if err_close == 0x00000000:
            logger.info("cabine %d: EdsCloseSession → OK (0x00000000) — aguardando 2s...", camera.cabine_id)
        else:
            logger.warning("cabine %d: EdsCloseSession → 0x%08X (sessão já fechada?) — aguardando 2s...", camera.cabine_id, err_close)
        time.sleep(2.0)
        import gc; gc.collect()
        logger.info("cabine %d: abrindo sessão...", camera.cabine_id)
        if not _open_session_with_retry(sdk, cam_ref):
            raise RuntimeError(f"cabine {camera.cabine_id}: cannot open session")
        logger.info("cabine %d: sessão aberta — liberando lock", camera.cabine_id)

    try:
        # Enable live view and wait for Movie Standby
        logger.info("cabine %d: habilitando EVF / aguardando standby de vídeo...", camera.cabine_id)
        result_holder = [False]
        def _evf():
            result_holder[0] = _enable_liveview_and_wait_standby(sdk, cam_ref, timeout=5.0)
        t = threading.Thread(target=_evf)
        t.start()
        t.join(timeout=8.0)
        if not result_holder[0]:
            logger.warning("cabine %d: EVF standby timeout — prosseguindo mesmo assim", camera.cabine_id)
        else:
            logger.info("cabine %d: EVF standby OK", camera.cabine_id)

        # Snapshot existing SD files
        logger.info("cabine %d: mapeando arquivos existentes no SD...", camera.cabine_id)
        known_files = _snapshot_sd_files(sdk, cam_ref)
        logger.info("cabine %d: SD mapeado (%d arquivo(s) existentes)", camera.cabine_id, len(known_files))

        if prep_delay > 0:
            logger.info(
                "cabine %d: aguardando %.1fs antes de iniciar gravação",
                camera.cabine_id, prep_delay,
            )
            time.sleep(prep_delay)

        # Start recording
        val_begin = ctypes.c_uint32(RECORD_BEGIN)
        err = sdk.EdsSetPropertyData(cam_ref, kEdsPropID_Record, 0, 4, ctypes.byref(val_begin))
        if err != EDS_ERR_OK:
            raise RuntimeError(f"cabine {camera.cabine_id}: Record=4 failed 0x{err:08X}")
        logger.info("Gravação iniciada: cabine %d", camera.cabine_id)

        if start_settle > 0:
            logger.info(
                "cabine %d: aguardando %.1fs para câmera entrar em modo vídeo",
                camera.cabine_id, start_settle,
            )
            time.sleep(start_settle)

        logger.info("cabine %d: gravando %.1fs", camera.cabine_id, duration_s)
        time.sleep(duration_s)

        # Stop recording with retry
        if not _stop_recording_with_retry(sdk, cam_ref):
            raise RuntimeError(f"cabine {camera.cabine_id}: could not stop recording")
        logger.info("Gravação parada: cabine %d", camera.cabine_id)

        # Wait for SD card to finalize the video file internally.
        # 8 s cobre o caso da T5i ainda estar escrevendo o footer do MOV/MP4.
        logger.info("cabine %d: aguardando 8s para SD finalizar escrita do arquivo...", camera.cabine_id)
        time.sleep(8.0)
        logger.info("cabine %d: SD pronto para leitura", camera.cabine_id)

    finally:
        with _session_lock:
            logger.info("cabine %d: fechando sessão pós-gravação...", camera.cabine_id)
            sdk.EdsCloseSession(cam_ref)

    # Reopen to read the new file from SD (serializado para evitar contenção)
    logger.info("cabine %d: aguardando 1.5s e reabrindo sessão para download...", camera.cabine_id)
    time.sleep(1.5)
    with _session_lock:
        logger.info("cabine %d: abrindo sessão para download...", camera.cabine_id)
        if not _open_session_with_retry(sdk, cam_ref):
            raise RuntimeError(f"cabine {camera.cabine_id}: cannot reopen session for download")
        logger.info("cabine %d: sessão de download aberta", camera.cabine_id)

    try:
        logger.info("cabine %d: procurando novo arquivo de vídeo no SD...", camera.cabine_id)
        item_ref, fname, size = _find_new_video(sdk, cam_ref, known_files)
        if item_ref is None:
            raise RuntimeError(f"cabine {camera.cabine_id}: new video file not found on SD")
        logger.info("cabine %d: arquivo encontrado: %s (%.1f MB)", camera.cabine_id, fname, size / 1_048_576)

        out_path = dest_dir / f"cabine_{camera.cabine_id}_raw{Path(fname).suffix}"
        stream_ref = EdsBaseRef()
        # EdsCreateFileStream flags: kEdsFileCreateDisposition_CreateAlways=1, kEdsAccess_ReadWrite=2
        err = sdk.EdsCreateFileStream(str(out_path).encode(), 1, 2, ctypes.byref(stream_ref))
        if err != EDS_ERR_OK:
            sdk.EdsRelease(item_ref)
            raise RuntimeError(f"cabine {camera.cabine_id}: EdsCreateFileStream failed 0x{err:08X}")

        try:
            logger.info("cabine %d: baixando %s para disco...", camera.cabine_id, fname)
            err = sdk.EdsDownload(item_ref, size, stream_ref)
            if err != EDS_ERR_OK:
                sdk.EdsDownloadCancel(item_ref)
                raise RuntimeError(f"cabine {camera.cabine_id}: EdsDownload failed 0x{err:08X}")
            sdk.EdsDownloadComplete(item_ref)
        finally:
            sdk.EdsRelease(stream_ref)
            sdk.EdsRelease(item_ref)

        size_mb = out_path.stat().st_size / 1_048_576
        logger.info("Download completo: cabine_%d_raw%s (%.1f MB)",
                    camera.cabine_id, Path(fname).suffix, size_mb)
        return out_path
    finally:
        with _session_lock:
            # Fechar é obrigatório: completa o handshake PTP do download.
            sdk.EdsCloseSession(cam_ref)
            # Reabrir para segurar o dispositivo antes do Windows MTP reivindicá-lo.
            _open_session_with_retry(sdk, cam_ref)


async def record_all_cameras(
    sdk,
    cameras: list,
    duration_s: float,
    dest_dir: Path,
    prep_delay: float = 0.0,
    start_settle: float = 0.0,
) -> dict:
    """
    Runs record_one_camera for each camera in parallel threads.
    Returns dict {cabine_id: Path | Exception}.
    """
    import asyncio

    async def _one(sdk, cam_ref, cam):
        try:
            path = await asyncio.to_thread(
                record_one_camera, sdk, cam_ref, cam, duration_s, dest_dir,
                prep_delay, start_settle,
            )
            return cam.cabine_id, path
        except Exception as exc:
            logger.error("cabine %d failed: %s", cam.cabine_id, exc)
            return cam.cabine_id, exc

    tasks = [_one(sdk, cam_ref, cam) for cam, cam_ref in cameras]
    results_list = await asyncio.gather(*tasks)
    return dict(results_list)
