"""Passive buzzer controller (KY-006)."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    from gpiozero import TonalBuzzer
except ImportError:
    TonalBuzzer = None  # type: ignore


class BuzzerController:
    def __init__(self, pin: int) -> None:
        self.pin = pin
        self._buzzer = None
        self._lock = threading.Lock()
        if TonalBuzzer is not None:
            try:
                self._buzzer = TonalBuzzer(pin)
            except Exception as exc:
                logger.warning("Buzzer init failed: %s", exc)

    def _beep(self, duration: float = 0.15, pause: float = 0.15) -> None:
        if self._buzzer is None:
            time.sleep(duration + pause)
            return
        self._buzzer.play(880)
        time.sleep(duration)
        self._buzzer.stop()
        time.sleep(pause)

    def _run_pattern(self, pattern: list[tuple[float, float]]) -> None:
        def worker() -> None:
            with self._lock:
                for duration, pause in pattern:
                    self._beep(duration, pause)

        threading.Thread(target=worker, daemon=True, name="buzzer").start()

    def boot_complete(self) -> None:
        self._run_pattern([(0.15, 0.15), (0.15, 0.15)])

    def zone_10_enter(self) -> None:
        self._run_pattern([(0.12, 0.12)] * 10)

    def zone_10_leave(self) -> None:
        self._run_pattern([(0.15, 0.05), (0.15, 0.05), (0.15, 0.8)])

    def close(self) -> None:
        if self._buzzer is not None:
            self._buzzer.close()
