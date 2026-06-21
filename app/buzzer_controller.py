"""Passive buzzer controller (KY-006)."""

from __future__ import annotations

import atexit
import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    from gpiozero import TonalBuzzer
except ImportError:
    TonalBuzzer = None  # type: ignore

# Lower frequency = less piercing on KY-006
_BEEP_HZ = 660


class BuzzerController:
    def __init__(self, pin: int) -> None:
        self.pin = pin
        self._buzzer: TonalBuzzer | None = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        if TonalBuzzer is not None:
            try:
                self._buzzer = TonalBuzzer(pin)
            except Exception as exc:
                logger.warning("Buzzer init failed: %s", exc)
        atexit.register(self.silence)

    def silence(self) -> None:
        """Force buzzer off — safe to call anytime."""
        self._cancel.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._buzzer is not None:
            try:
                self._buzzer.stop()
            except Exception:
                pass

    def _beep(self, duration: float = 0.12, pause: float = 0.15) -> None:
        if self._cancel.is_set():
            return
        if self._buzzer is None:
            time.sleep(duration + pause)
            return
        try:
            self._buzzer.play(_BEEP_HZ)
            time.sleep(duration)
        finally:
            try:
                self._buzzer.stop()
            except Exception:
                pass
        if not self._cancel.is_set():
            time.sleep(pause)

    def _run_pattern(self, pattern: list[tuple[float, float]]) -> None:
        if self._thread and self._thread.is_alive():
            return

        def worker() -> None:
            with self._lock:
                for duration, pause in pattern:
                    if self._cancel.is_set():
                        break
                    self._beep(duration, pause)
            self.silence()

        self._cancel.clear()
        self._thread = threading.Thread(
            target=worker, daemon=False, name="buzzer")
        self._thread.start()

    def boot_complete(self) -> None:
        # Single very short tick at startup (~50 ms total)
        self._run_pattern([(0.05, 0.0)])

    def zone_10_enter(self) -> None:
        self._run_pattern([(0.10, 0.12)] * 10)

    def zone_10_leave(self) -> None:
        self._run_pattern([(0.12, 0.06), (0.12, 0.06), (0.12, 0.5)])

    def close(self) -> None:
        self.silence()
        if self._buzzer is not None:
            try:
                self._buzzer.close()
            except Exception:
                pass
            self._buzzer = None
