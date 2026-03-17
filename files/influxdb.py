"""
Lightweight InfluxDB v2 Line-Protocol writer for MicroPython.
Sends data via HTTP POST to /api/v2/write.
Also supports InfluxDB v1 compatibility endpoint.
"""

import json
import time


class InfluxDBWriter:
    """
    Write time-series data to InfluxDB using the HTTP Line Protocol.

    Supports:
        - InfluxDB Cloud / OSS v2  (token auth, /api/v2/write)
        - InfluxDB v1 / Telegraf   (user:pass auth, /write)

    Parameters
    ----------
    host     : str   – hostname or IP, e.g. "192.168.1.50" or "us-east-1-1.aws.cloud2.influxdata.com"
    port     : int   – 8086 for OSS, 443 for Cloud (set ssl=True)
    token    : str   – InfluxDB v2 API token  (v2 mode)
    org      : str   – organisation name       (v2 mode)
    bucket   : str   – bucket / database name
    ssl      : bool  – use HTTPS (requires urequests with TLS support)
    username : str   – InfluxDB v1 username    (v1 mode, optional)
    password : str   – InfluxDB v1 password    (v1 mode, optional)
    """

    def __init__(
        self,
        host: str,
        bucket: str,
        port: int = 8086,
        token: str = None,
        org: str = None,
        ssl: bool = False,
        username: str = None,
        password: str = None,
        timeout: int = 10,
    ):
        self.host = host
        self.port = port
        self.bucket = bucket
        self.token = token
        self.org = org
        self.ssl = ssl
        self.username = username
        self.password = password
        self.timeout = timeout

        scheme = "https" if ssl else "http"

        if token:
            # InfluxDB v2 / Cloud
            self._url = f"{scheme}://{host}:{port}/api/v2/write?org={org}&bucket={bucket}&precision=s"
            self._headers = {
                "Authorization": f"Token {token}",
                "Content-Type": "text/plain; charset=utf-8",
                "Accept": "application/json",
            }
        else:
            # InfluxDB v1 compatibility
            auth = ""
            if username and password:
                auth = f"&u={username}&p={password}"
            self._url = f"{scheme}://{host}:{port}/write?db={bucket}{auth}&precision=s"
            self._headers = {"Content-Type": "text/plain; charset=utf-8"}

    # ── Line Protocol builder ────────────────────────────────────────────────

    @staticmethod
    def build_line(
        measurement: str,
        fields: dict,
        tags: dict = None,
        timestamp: int = None,
    ) -> str:
        """
        Build a single InfluxDB line-protocol string.

        Example output:
            air_quality,location=office,sensor=sps30 pm2_5=12.3,pm10=18.7 1710000000
        """
        # Tags (optional, sorted for consistency)
        tag_str = ""
        if tags:
            tag_str = "," + ",".join(
                f"{k}={v}" for k, v in sorted(tags.items())
            )

        # Fields (required)
        field_parts = []
        for k, v in fields.items():
            if isinstance(v, bool):
                field_parts.append(f"{k}={str(v).upper()}")
            elif isinstance(v, int):
                field_parts.append(f"{k}={v}i")
            else:
                field_parts.append(f"{k}={v:.6g}")
        field_str = ",".join(field_parts)

        # Timestamp (optional; use seconds since epoch)
        ts_str = f" {timestamp}" if timestamp is not None else ""

        return f"{measurement}{tag_str} {field_str}{ts_str}"

    # ── HTTP writer ──────────────────────────────────────────────────────────

    def write(
        self,
        measurement: str,
        fields: dict,
        tags: dict = None,
        timestamp: int = None,
    ) -> bool:
        """
        Write a single data point.  Returns True on success.
        timestamp defaults to current time (UTC epoch seconds).
        """
        if timestamp is None:
            timestamp = time.time()

        line = self.build_line(measurement, fields, tags, timestamp)
        return self._post(line)

    def write_batch(self, lines: list) -> bool:
        """Write multiple pre-built line-protocol strings at once."""
        body = "\n".join(lines)
        return self._post(body)

    def _post(self, body: str) -> bool:
        """Send an HTTP POST with line-protocol body. Returns True on HTTP 2xx."""
        try:
            import urequests as requests
        except ImportError:
            import requests  # fallback for testing on CPython

        try:
            resp = requests.post(
                self._url,
                data=body,
                headers=self._headers,
            )
            ok = 200 <= resp.status_code < 300
            if not ok:
                print(f"[InfluxDB] HTTP {resp.status_code}: {resp.text[:200]}")
            resp.close()
            return ok
        except Exception as e:
            print(f"[InfluxDB] Write error: {e}")
            return False
