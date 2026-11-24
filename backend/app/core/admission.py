"""Admission control: at most N API requests run at once per process; the rest queue here.

Why: sync FastAPI endpoints hop between worker threads (auth dependency, endpoint,
response validation, cleanup) and keep their DB connection across those hops. Under a
burst, all 40 threads could end up waiting for a connection while every connection
belonged to a request waiting for a thread: nothing moved until the 30 s pool timeout,
the health check starved, and the ALB killed healthy-but-stuck instances.

Requests now wait on the event loop *before* they take a thread or a connection. With
the limit below the pool size every admitted request gets a connection, so that
deadlock can't happen. Waiting too long gives a quick 503 instead of a pile-up, and CPU
(what the ASG scales on) reflects real work. Health checks and the static site skip
the queue.
"""

import asyncio
import json

EXEMPT = ("/api/health",)


class AdmissionLimit:
    def __init__(self, app, limit: int, timeout: float):
        self.app = app
        self.limit = limit
        self.timeout = timeout
        self._sem: asyncio.Semaphore | None = None

    def _semaphore(self) -> asyncio.Semaphore:
        if self._sem is None:  # created lazily, inside the server's event loop
            self._sem = asyncio.Semaphore(self.limit)
        return self._sem

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or path.startswith(EXEMPT):
            return await self.app(scope, receive, send)
        sem = self._semaphore()
        try:
            await asyncio.wait_for(sem.acquire(), self.timeout)
        except TimeoutError:
            return await _busy(send)
        try:
            await self.app(scope, receive, send)
        finally:
            sem.release()


async def _busy(send) -> None:
    body = json.dumps({"detail": "Server busy, please retry"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", b"1"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
