"""EC2 instance metadata via IMDSv2. Falls back to 'local' outside AWS."""

from functools import lru_cache

import httpx

_BASE = "http://169.254.169.254/latest"


@lru_cache
def get_instance_info() -> dict:
    try:
        with httpx.Client(timeout=0.5) as c:
            token = c.put(
                f"{_BASE}/api/token", headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"}
            ).text
            h = {"X-aws-ec2-metadata-token": token}
            iid = c.get(f"{_BASE}/meta-data/instance-id", headers=h).text
            az = c.get(f"{_BASE}/meta-data/placement/availability-zone", headers=h).text
            return {"instance_id": iid, "az": az}
    except Exception:
        import socket

        return {"instance_id": socket.gethostname()[:63], "az": "local"}
