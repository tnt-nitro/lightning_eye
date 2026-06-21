"""Minimal HTTP status server for QR code access."""

from __future__ import annotations

import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class StatusServer:
    def __init__(self, port: int, get_status: Callable[[], dict]) -> None:
        self.port = port
        self.get_status = get_status
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler_factory = self.get_status

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path not in ("/status", "/"):
                    self.send_response(404)
                    self.end_headers()
                    return
                payload = json.dumps(
                    handler_factory(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):  # noqa: A002
                logger.debug("HTTP %s", args[0] if args else "")

        try:
            self._httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        except OSError as exc:
            logger.error("HTTP server failed on port %s: %s", self.port, exc)
            return
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="http-status")
        self._thread.start()
        logger.info("Status server on http://%s:%s/status",
                    get_local_ip(), self.port)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()

    @property
    def url(self) -> str:
        return f"http://{get_local_ip()}:{self.port}/status"
