"""Sensor watchdog for AS3935 heartbeat monitoring."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)


class Watchdog:
    def __init__(
        self,
        get_heartbeat: Callable[[], float],
        reinit: Callable[[], None],
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        on_offline: Callable[[], None] | None = None,
        on_recovered: Callable[[], None] | None = None,
    ) -> None:
        self.get_heartbeat = get_heartbeat
        self.reinit = reinit
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.on_offline = on_offline
        self.on_recovered = on_recovered
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failures = 0
        self._offline = False

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="watchdog")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            age = time.monotonic() - self.get_heartbeat()
            if age > self.timeout_seconds:
                self._failures += 1
                logger.warning(
                    "Sensor heartbeat stale (%.1fs), reinit attempt %s",
                    age,
                    self._failures,
                )
                try:
                    self.reinit()
                except Exception as exc:
                    logger.error("Watchdog reinit failed: %s", exc)
                if self._failures >= self.max_retries:
                    logger.critical("Watchdog max retries reached")
                    if not self._offline:
                        self._offline = True
                        if self.on_offline:
                            self.on_offline()
            else:
                if self._offline:
                    self._offline = False
                    if self.on_recovered:
                        self.on_recovered()
                self._failures = 0
            self._stop.wait(5)
