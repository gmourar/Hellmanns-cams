"""
Process manager para o agente de câmeras Canon.

DESIGN:
  1. Detecta sessão pendente via GET /agent/sessions/current (lê o DB, NÃO consome a fila)
  2. Inicia o agente original (python -m src.agent — poll_loop normal)
     → O agente faz tudo: poll → gravar → processar → upload S3 → /complete
  3. Monitora GET /gallery/{session_id} até status virar "ready" ou "error"
  4. Mata o agente (kill) — a morte do processo libera todos os handles EDSDK/USB
     via EdsTerminateSDK() no bloco finally, e o Windows re-enumera o dispositivo
  5. Aguarda cooldown (USB settle) antes da próxima sessão
  6. Repete do passo 1

POR QUE MATAR O AGENTE:
  Canon EDSDK retorna 0x000000C0 (EDS_ERR_DEVICE_BUSY) na segunda sessão porque
  o estado interno USB acumula enquanto o processo vive. Reiniciar o processo
  força EdsInitializeSDK() limpo — sem estado stale.

USO:
  cd agent
  python runner.py
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

_AGENT_DIR = Path(__file__).parent
load_dotenv(_AGENT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("runner")

API_BASE_URL        = os.environ["API_BASE_URL"].rstrip("/")
AGENT_TOKEN         = os.environ["AGENT_TOKEN"]
COOLDOWN_SECONDS    = float(os.environ.get("RUNNER_COOLDOWN_SECONDS", "10.0"))
POLL_INTERVAL       = float(os.environ.get("RUNNER_POLL_INTERVAL", "3.0"))
SESSION_TIMEOUT     = float(os.environ.get("RUNNER_SESSION_TIMEOUT", "300.0"))

AGENT_HEADERS = {"Authorization": f"Bearer {AGENT_TOKEN}"}
AGENT_CMD     = [sys.executable, "-u", "-m", "src.agent"]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _pending_session(client: httpx.AsyncClient) -> str | None:
    """
    Consulta /agent/sessions/current — lê o DB sem consumir a fila.
    Retorna session_id ou None.
    """
    try:
        resp = await client.get(
            f"{API_BASE_URL}/agent/sessions/current",
            headers=AGENT_HEADERS,
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json().get("session_id")
        # 204 = sem sessão pendente
        return None
    except Exception as exc:
        logger.warning("Erro ao checar sessão pendente: %s", exc)
        return None


async def _session_status(client: httpx.AsyncClient, session_id: str) -> str | None:
    """
    Consulta /gallery/{session_id} (endpoint público, sem auth).
    Retorna status: 'recording' | 'ready' | 'error' | None
    """
    try:
        resp = await client.get(
            f"{API_BASE_URL}/gallery/{session_id}",
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json().get("status")
        return None
    except Exception as exc:
        logger.warning("Erro ao checar status da sessão %s: %s", session_id, exc)
        return None


def _start_agent() -> subprocess.Popen:
    """Inicia o agente original (poll_loop) como subprocesso."""
    return subprocess.Popen(AGENT_CMD, cwd=str(_AGENT_DIR))


def _kill_agent(proc: subprocess.Popen, session_id: str) -> None:
    """Encerra o subprocesso do agente de forma limpa."""
    if proc.poll() is not None:
        logger.info("Session %s: agente já havia encerrado (código %d)", session_id, proc.returncode)
        return
    logger.info("Session %s: matando agente (PID %d)...", session_id, proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=8.0)
        logger.info("Session %s: agente encerrado (código %d)", session_id, proc.returncode)
    except subprocess.TimeoutExpired:
        logger.warning("Session %s: agente não respondeu ao terminate, forçando kill...", session_id)
        proc.kill()
        proc.wait()
        logger.info("Session %s: agente morto (SIGKILL)", session_id)


# ── Loop principal ────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("=" * 60)
    logger.info("Runner iniciado")
    logger.info("API: %s", API_BASE_URL)
    logger.info("Cooldown USB após sessão: %.0fs", COOLDOWN_SECONDS)
    logger.info("Intervalo de poll: %.0fs", POLL_INTERVAL)
    logger.info("Timeout por sessão: %.0fs", SESSION_TIMEOUT)
    logger.info("=" * 60)

    async with httpx.AsyncClient() as client:
        while True:
            # ── 1. Aguarda sessão pendente ─────────────────────────────────
            session_id = await _pending_session(client)

            if session_id is None:
                logger.info("Sem sessões pendentes — verificando em %.0fs...", POLL_INTERVAL)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # ── 2. Sessão detectada: inicia o agente ──────────────────────
            logger.info("=" * 60)
            logger.info("Sessão detectada: %s", session_id)
            logger.info("Iniciando agente: %s", " ".join(AGENT_CMD))

            proc = _start_agent()
            logger.info("Agente iniciado (PID %d)", proc.pid)

            # ── 3. Monitora até conclusão ou timeout ──────────────────────
            logger.info("Monitorando sessão %s (timeout=%.0fs)...", session_id, SESSION_TIMEOUT)
            deadline = asyncio.get_event_loop().time() + SESSION_TIMEOUT

            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(POLL_INTERVAL)

                # Agente caiu sozinho?
                if proc.poll() is not None:
                    logger.warning(
                        "Session %s: agente encerrou espontaneamente (código %d)",
                        session_id, proc.returncode,
                    )
                    break

                status = await _session_status(client, session_id)
                logger.info("Session %s: status=%s", session_id, status)

                if status in ("ready", "error"):
                    logger.info("Session %s: concluída com status='%s'", session_id, status)
                    break
            else:
                logger.error("Session %s: TIMEOUT após %.0fs", session_id, SESSION_TIMEOUT)

            # ── 4. Mata o agente ──────────────────────────────────────────
            logger.info("=" * 60)
            _kill_agent(proc, session_id)

            # ── 5. Cooldown USB ───────────────────────────────────────────
            logger.info("Cooldown USB %.0fs (Windows libera handles do EDSDK)...", COOLDOWN_SECONDS)
            await asyncio.sleep(COOLDOWN_SECONDS)
            logger.info("Cooldown concluído. Voltando ao poll.")
            logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Runner interrompido pelo usuário.")
