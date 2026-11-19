"""Identify which EC2 instance served a request (shown in X-Served-By)."""

import socket
import urllib.request
from functools import lru_cache

_IMDS = "http://169.254.169.254/latest"


@lru_cache
def instance_id() -> str:
    try:
        token_req = urllib.request.Request(
            f"{_IMDS}/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        )
        token = urllib.request.urlopen(token_req, timeout=0.5).read().decode()
        id_req = urllib.request.Request(
            f"{_IMDS}/meta-data/instance-id", headers={"X-aws-ec2-metadata-token": token}
        )
        return urllib.request.urlopen(id_req, timeout=0.5).read().decode()
    except OSError:
        return socket.gethostname()  # not on EC2 (local / container)
