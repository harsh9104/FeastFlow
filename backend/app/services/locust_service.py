"""Control the Locust load generator (separate EC2) through its web API, so the admin
dashboard can start a 'normal' or 'festival' profile and watch it live."""

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings

PROFILES = ("normal", "festival")
_TIMEOUT = httpx.Timeout(5.0)


def _base() -> str:
    url = get_settings().locust_url
    if not url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Load generator not configured (set LOCUST_URL to the Locust EC2's :8089 address)",
        )
    return url.rstrip("/")


def _call(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        res = httpx.request(method, f"{_base()}{path}", timeout=_TIMEOUT, **kwargs)
        res.raise_for_status()
        return res
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Load generator unreachable: {exc}"
        ) from None


def start(profile: str) -> dict:
    # The profile is a custom Locust argument (see loadtest/locustfile.py); the shape
    # class reads it and drives the user count, so user_count/spawn_rate are placeholders.
    _call("POST", "/swarm", data={"user_count": 1, "spawn_rate": 1, "profile": profile})
    return status_()


def stop() -> dict:
    _call("GET", "/stop")
    return status_()


def status_() -> dict:
    data = _call("GET", "/stats/requests").json()
    total = next((s for s in data.get("stats", []) if s.get("name") == "Aggregated"), {})
    pct = data.get("current_response_time_percentiles") or {}
    return {
        "state": data.get("state"),  # ready | spawning | running | stopped
        "users": data.get("user_count", 0),
        "rps": round(data.get("total_rps", 0.0), 1),
        "failures_per_second": round(data.get("total_fail_per_sec", 0.0), 2),
        "fail_ratio": round(data.get("fail_ratio", 0.0), 4),
        "requests": total.get("num_requests", 0),
        "failures": total.get("num_failures", 0),
        "avg_ms": round(total.get("avg_response_time", 0.0)),
        "p50_ms": pct.get("response_time_percentile_0.5"),
        "p95_ms": pct.get("response_time_percentile_0.95"),
        "errors": [
            {"name": e.get("name"), "error": e.get("error"), "count": e.get("occurrences")}
            for e in data.get("errors", [])[:5]
        ],
    }
