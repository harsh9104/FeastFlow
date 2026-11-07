"""In-process request/resource collector for the local metrics provider.

Each gunicorn worker keeps small per-minute buckets and flushes them to Postgres every few
seconds (one row per instance/worker/minute), so the dashboard sees all workers. On AWS the
CloudWatch provider is used instead and this collector is not started.
"""

import logging
import os
import random
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text

from app.core.instance import get_instance_info
from app.db.session import SessionLocal
from app.models.metrics import AppMetric

log = logging.getLogger("app.metrics")
MAX_SAMPLES = 2000


@dataclass
class Bucket:
    n: int = 0
    err: int = 0
    lat_sum: float = 0.0
    lat: list[float] = field(default_factory=list)
    cpu_sum: float = 0.0
    mem_sum: float = 0.0
    res_n: int = 0


def _minute(ts: datetime | None = None) -> datetime:
    return (ts or datetime.now(UTC)).replace(second=0, microsecond=0)


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


class Collector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[datetime, Bucket] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.worker = os.getpid()

    def record(self, status: int, ms: float, now: datetime | None = None) -> None:
        with self._lock:
            b = self._buckets.setdefault(_minute(now), Bucket())
            b.n += 1
            b.err += 1 if status >= 500 else 0
            b.lat_sum += ms
            if len(b.lat) < MAX_SAMPLES:
                b.lat.append(ms)
            else:  # reservoir sampling keeps memory bounded under heavy load
                i = random.randrange(b.n)
                if i < MAX_SAMPLES:
                    b.lat[i] = ms

    def sample_resources(self, now: datetime | None = None) -> None:
        import psutil

        cpu, mem = psutil.cpu_percent(interval=None), psutil.virtual_memory().percent
        with self._lock:
            b = self._buckets.setdefault(_minute(now), Bucket())
            b.cpu_sum += cpu
            b.mem_sum += mem
            b.res_n += 1

    def flush(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        instance = get_instance_info()["instance_id"]
        with self._lock:
            rows = [
                {
                    "instance_id": instance,
                    "worker": self.worker,
                    "minute": minute,
                    "request_count": b.n,
                    "error_5xx": b.err,
                    "latency_sum_ms": b.lat_sum,
                    "p50_ms": _pct(b.lat, 0.5),
                    "p90_ms": _pct(b.lat, 0.9),
                    "cpu_pct": b.cpu_sum / b.res_n if b.res_n else None,
                    "mem_pct": b.mem_sum / b.res_n if b.res_n else None,
                }
                for minute, b in self._buckets.items()
            ]
            cutoff = _minute(now) - timedelta(minutes=3)
            self._buckets = {m: b for m, b in self._buckets.items() if m >= cutoff}
        if not rows:
            return
        with SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO app_metrics (instance_id, worker, minute, request_count, "
                    "error_5xx, "
                    "latency_sum_ms, p50_ms, p90_ms, cpu_pct, mem_pct) VALUES "
                    "(:instance_id, :worker, :minute, :request_count, :error_5xx, :latency_sum_ms, "
                    ":p50_ms, :p90_ms, :cpu_pct, :mem_pct) "
                    "ON CONFLICT (instance_id, worker, minute) DO UPDATE SET "
                    "request_count = EXCLUDED.request_count, error_5xx = EXCLUDED.error_5xx, "
                    "latency_sum_ms = EXCLUDED.latency_sum_ms, p50_ms = EXCLUDED.p50_ms, "
                    "p90_ms = EXCLUDED.p90_ms, cpu_pct = EXCLUDED.cpu_pct, "
                    "mem_pct = EXCLUDED.mem_pct"
                ),
                rows,
            )
            if now.minute % 10 == 0 and now.second < 20:  # retention: 25 h
                db.execute(delete(AppMetric).where(AppMetric.minute < now - timedelta(hours=25)))
            db.commit()

    # -- background thread ------------------------------------------------
    def start(self, interval: float = 10.0) -> None:
        if self._thread:
            return
        import psutil

        psutil.cpu_percent(interval=None)  # prime: the first call always returns 0

        def loop() -> None:
            while not self._stop.wait(interval):
                try:
                    self.sample_resources()
                    self.flush()
                except Exception:
                    log.exception("metrics flush failed")

        self._thread = threading.Thread(target=loop, name="metrics-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.flush()
        except Exception:
            log.exception("final metrics flush failed")


collector = Collector()
