import asyncio

from app.core.admission import AdmissionLimit


def _scope(path: str) -> dict:
    return {"type": "http", "path": path, "method": "GET", "headers": []}


async def _call(mw, path: str) -> int:
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw(_scope(path), receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def _app(gate: asyncio.Event, started: list):
    async def app(scope, receive, send):
        started.append(scope["path"])
        if scope["path"] == "/api/orders":
            await gate.wait()  # simulates a slow request holding its slot
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


def test_queue_full_gives_quick_503_and_health_still_answers():
    async def run():
        gate, started = asyncio.Event(), []
        mw = AdmissionLimit(_app(gate, started), limit=2, timeout=0.2)
        slow = [asyncio.create_task(_call(mw, "/api/orders")) for _ in range(2)]
        await asyncio.sleep(0.05)
        assert await _call(mw, "/api/orders") == 503  # third one: no slot within 0.2 s
        assert await _call(mw, "/api/health") == 200  # exempt, answers while saturated
        assert await _call(mw, "/cart") == 200  # the static site is exempt too
        assert await _call(mw, "/api/restaurants") == 503  # but every other API path queues
        gate.set()
        assert await asyncio.gather(*slow) == [200, 200]
        assert started.count("/api/orders") == 2  # the rejected request never reached the app

    asyncio.run(run())


def test_slots_are_released_after_each_request():
    async def run():
        gate, started = asyncio.Event(), []
        gate.set()
        mw = AdmissionLimit(_app(gate, started), limit=1, timeout=0.5)
        for _ in range(5):
            assert await _call(mw, "/api/restaurants") == 200

    asyncio.run(run())


def test_waiting_request_gets_in_when_a_slot_frees():
    async def run():
        gate, started = asyncio.Event(), []
        mw = AdmissionLimit(_app(gate, started), limit=1, timeout=2)
        first = asyncio.create_task(_call(mw, "/api/orders"))
        await asyncio.sleep(0.05)
        second = asyncio.create_task(_call(mw, "/api/orders"))
        await asyncio.sleep(0.05)
        assert started == ["/api/orders"]  # second is queued, not running
        gate.set()
        assert await first == 200 and await second == 200

    asyncio.run(run())


def test_app_wires_the_limit(client):
    res = client.get("/api/health")
    assert res.status_code == 200 and "x-served-by" in res.headers
