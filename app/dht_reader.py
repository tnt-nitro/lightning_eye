"""DHT22 temperature and humidity reader."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_BACKEND: str | None = None
_board = None
_adafruit_dht = None
_gpiozero_dht = None

try:
    import board as _board_mod
    import adafruit_dht as _adafruit_dht_mod

    _board = _board_mod
    _adafruit_dht = _adafruit_dht_mod
    _BACKEND = "adafruit"
except ImportError:
    try:
        from gpiozero import DHT22 as _gpiozero_dht_cls

        _gpiozero_dht = _gpiozero_dht_cls
        _BACKEND = "gpiozero"
    except ImportError:
        pass

# BCM GPIO number → board.Dxx name (Pi header)
_BCM_TO_BOARD = {
    4: "D4",
    17: "D17",
    18: "D18",
    22: "D22",
    23: "D23",
    24: "D24",
    27: "D27",
}


def _board_pin(bcm: int):
    name = _BCM_TO_BOARD.get(bcm)
    if _board is None or name is None:
        raise ValueError(f"No board pin mapping for GPIO {bcm}")
    return getattr(_board, name)


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
        if _BACKEND is None:
            logger.warning(
                "No DHT22 backend available (install adafruit-circuitpython-dht)")
            return
        try:
            if _BACKEND == "adafruit":
                # use_pulseio=True works reliably on Pi OS Trixie / Pi Zero WH
                self._sensor = _adafruit_dht.DHT22(
                    _board_pin(self.pin), use_pulseio=True)
            else:
                self._sensor = _gpiozero_dht(self.pin)
        except Exception as exc:
            logger.warning("DHT22 init failed: %s", exc)
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="dht22")
        self._thread.start()
        logger.info("DHT22 started on GPIO %s via %s", self.pin, _BACKEND)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._sensor is not None:
            try:
                if _BACKEND == "adafruit":
                    self._sensor.exit()
                else:
                    self._sensor.close()
            except Exception:
                pass
            self._sensor = None

    def _read_values(self) -> tuple[float | None, float | None]:
        if self._sensor is None:
            return None, None
        if _BACKEND == "adafruit":
            for _ in range(3):
                try:
                    return self._sensor.temperature, self._sensor.humidity
                except RuntimeError:
                    time.sleep(0.5)
            return None, None
        temp = self._sensor.temperature
        hum = self._sensor.humidity
        return temp, hum

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                temp, hum = self._read_values()
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
