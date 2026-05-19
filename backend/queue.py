import asyncio

_q: asyncio.Queue = asyncio.Queue()


async def push(command: dict) -> None:
    await _q.put(command)


async def wait(timeout: float = 30.0) -> dict | None:
    try:
        return await asyncio.wait_for(_q.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
