"""DHT22 temperature and humidity reader."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    from gpiozero import DHT22
except ImportError:
    DHT22 = None  # type: ignore


class DhtReader:
    def __init__(self, pin: int, interval: float = 5.0) -> None:
        self.pin = pin
        self.interval = interval
        self.temp_c: float | None = None
        self.humidity_pct: float | None = None
        self._sensor = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if DHT22 is None:
            logger.warning("gpiozero DHT22 unavailable")
            return
        try:
            self._sensor = DHT22(self.pin)
        except Exception as exc:
            logger.warning("DHT22 init failed: %s", exc)
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="dht22")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._sensor is not None:
            self._sensor.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._sensor is not None:
                    temp = self._sensor.temperature
                    hum = self._sensor.humidity
                    with self._lock:
                        if temp is not None:
                            self.temp_c = float(temp)
                        if hum is not None:
                            self.humidity_pct = float(hum)
            except Exception as exc:
                logger.debug("DHT22 read error: %s", exc)
            self._stop.wait(self.interval)

    def snapshot(self) -> tuple[float | None, float | None]:
        with self._lock:
            return self.temp_c, self.humidity_pct
