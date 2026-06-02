"""
Process manager para o agente de câmeras Canon.

DESIGN:
  O Runner comanda tudo. O Agente é "burro" e executa apenas UMA sessão.

  Loop do Runner:
    1. Detecta sessão pendente via GET /agent/sessions/current (lê DB, NÃO consome fila)
    2. Ack a sessão imediatamente (evita re-enfileiramento em restart do backend)
    3. Inicia subprocesso: python -m src.agent --session SESSION_ID
       → O agente: inicializa SDK, grava, processa, sobe para S3, chama /complete, morre
    4. Aguarda o subprocesso encerrar (proc.wait) — sem polling de status
    5. Kill forçado se timeout
    6. Cooldown USB (Windows libera handles do EDSDK)
    7. Volta ao passo 1

POR QUE MATAR O PROCESSO A CADA SESSÃO:
  Canon EDSDK acumula estado USB interno enquanto o processo vive.
  A morte do processo força EdsTerminateSDK() no finally → Windows re-enumera
  o dispositivo → próximo EdsInitializeSDK() começa com estado limpo.
  Sem isso, a 2ª sessão falha com 0x000000C0 (EDS_ERR_DEVICE_BUSY).

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

API_BASE_URL     = os.environ["API_BASE_URL"].rstrip("/")
AGENT_TOKEN      = os.environ["AGENT_TOKEN"]
COOLDOWN_SECONDS = float(os.environ.get("RUNNER_COOLDOWN_SECONDS", "10.0"))
POLL_INTERVAL    = float(os.environ.get("RUNNER_POLL_INTERVAL", "3.0"))
SESSION_TIMEOUT  = float(os.environ.get("RUNNER_SESSION_TIMEOUT", "300.0"))

AGENT_HEADERS = {"Authorization": f"Bearer {AGENT_TOKEN}"}


# ── Helpers de API ────────────────────────────────────────────────────────────

async def _pending_session(client: httpx.AsyncClient) -> str | None:
    """
    GET /agent/sessions/current — lê DB sem consumir a fila.
    Retorna session_id se há sessão em 'recording', senão None.
    """
    try:
        resp = await client.get(
            f"{API_BASE_URL}/agent/sessions/current",
            headers=AGENT_HEADERS,
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json().get("session_id")
        return None  # 204 = sem sessão pendente
    except Exception as exc:
        logger.warning("Erro ao checar sessão pendente: %s", exc)
        return None


async def _ack_session(client: httpx.AsyncClient, session_id: str) -> None:
    """
    POST /agent/sessions/{id}/ack — marca agent_acked_at no DB.
    Evita re-enfileiramento da sessão em caso de restart do backend.
    """
    try:
        resp = await client.post(
            f"{API_BASE_URL}/agent/sessions/{session_id}/ack",
            headers=AGENT_HEADERS,
            timeout=5.0,
        )
        if resp.status_code == 200:
            logger.info("Session %s: ack confirmado pelo backend", session_id)
        else:
            logger.warning("Session %s: ack retornou %d", session_id, resp.status_code)
    except Exception as exc:
        logger.warning("Session %s: ack falhou (não-fatal): %s", session_id, exc)


# ── Controle do subprocesso ───────────────────────────────────────────────────

def _start_agent(session_id: str) -> subprocess.Popen:
    """
    Inicia o agente em modo --session: executa UMA sessão e encerra.
    -u = output não-bufferizado (logs aparecem em tempo real).
    """
    cmd = [sys.executable, "-u", "-m", "src.agent", "--session", session_id]
    logger.info("Iniciando agente: %s", " ".join(cmd))
    return subprocess.Popen(cmd, cwd=str(_AGENT_DIR))


def _wait_or_kill(proc: subprocess.Popen, session_id: str) -> int:
    """
    Aguarda o subprocesso encerrar naturalmente (até SESSION_TIMEOUT).
    Se timeout: termina com SIGTERM, depois SIGKILL se necessário.
    Retorna o exit code.
    """
    try:
        proc.wait(timeout=SESSION_TIMEOUT)
        return proc.returncode
    except subprocess.TimeoutExpired:
        logger.error(
            "Session %s: TIMEOUT após %.0fs — enviando SIGTERM (PID %d)...",
            session_id, SESSION_TIMEOUT, proc.pid,
        )
        proc.terminate()
        try:
            proc.wait(timeout=8.0)
        except subprocess.TimeoutExpired:
            logger.warning("Session %s: SIGTERM ignorado — forçando SIGKILL...", session_id)
            proc.kill()
            proc.wait()
        return proc.returncode


# ── Loop principal ────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("=" * 60)
    logger.info("Runner iniciado")
    logger.info("API:              %s", API_BASE_URL)
    logger.info("Cooldown USB:     %.0fs  (RUNNER_COOLDOWN_SECONDS)", COOLDOWN_SECONDS)
    logger.info("Poll interval:    %.0fs  (RUNNER_POLL_INTERVAL)", POLL_INTERVAL)
    logger.info("Timeout sessão:   %.0fs  (RUNNER_SESSION_TIMEOUT)", SESSION_TIMEOUT)
    logger.info("=" * 60)

    async with httpx.AsyncClient() as client:
        while True:

            # ── 1. Aguarda sessão pendente (polling leve) ──────────────────
            session_id = await _pending_session(client)

            if session_id is None:
                logger.info("Sem sessões pendentes — verificando em %.0fs...", POLL_INTERVAL)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # ── 2. Sessão detectada ────────────────────────────────────────
            logger.info("=" * 60)
            logger.info("Sessão detectada: %s", session_id)

            # Ack antes de iniciar o agente: garante que o backend não
            # re-enfileire essa sessão mesmo que o agente crash imediatamente.
            await _ack_session(client, session_id)

            # ── 3. Inicia o subprocesso ────────────────────────────────────
            proc = _start_agent(session_id)
            logger.info("Agente iniciado (PID %d) — aguardando conclusão...", proc.pid)

            # ── 4. Aguarda o processo morrer (ou mata por timeout) ─────────
            # proc.wait() bloqueia — rodar em thread para não travar o event loop
            exit_code = await asyncio.to_thread(_wait_or_kill, proc, session_id)

            logger.info("=" * 60)
            if exit_code == 0:
                logger.info("Session %s: agente encerrou com SUCESSO (código 0)", session_id)
            else:
                logger.error("Session %s: agente encerrou com ERRO (código %d)", session_id, exit_code)
            logger.info("=" * 60)

            # ── 5. Cooldown USB ───────────────────────────────────────────
            logger.info(
                "Cooldown USB %.0fs — Windows liberando handles EDSDK do PID %d...",
                COOLDOWN_SECONDS, proc.pid,
            )
            await asyncio.sleep(COOLDOWN_SECONDS)
            logger.info("Cooldown concluído. Voltando ao poll.")
            logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Runner interrompido pelo usuário.")
