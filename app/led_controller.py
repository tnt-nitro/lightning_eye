"""LED traffic light controller with pattern state machine."""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum, auto

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None  # type: ignore


class LedState(Enum):
    BOOT_INSTALL = auto()
    INSTALL_STEP_OK = auto()
    BOOT_COMPLETE = auto()
    READY = auto()
    ALERT = auto()
    RISING = auto()
    FALLING = auto()
    ZONE_20KM = auto()
    ZONE_10KM = auto()


# Priority: higher wins
_STATE_PRIORITY = {
    LedState.READY: 0,
    LedState.ALERT: 10,
    LedState.FALLING: 20,
    LedState.RISING: 20,
    LedState.ZONE_20KM: 30,
    LedState.ZONE_10KM: 40,
    LedState.BOOT_INSTALL: 100,
    LedState.INSTALL_STEP_OK: 100,
    LedState.BOOT_COMPLETE: 100,
}


class LedController:
    def __init__(self, red: int, yellow: int, green: int) -> None:
        self.red = red
        self.yellow = yellow
        self.green = green
        self._states: set[LedState] = {LedState.READY}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._progress_callback: object | None = None

    def set_progress_callback(self, cb: object) -> None:
        self._progress_callback = cb

    def start(self) -> None:
        if GPIO is None:
            logger.warning(
                "GPIO unavailable, LED controller running in noop mode")
            return
        GPIO.setmode(GPIO.BCM)
        for pin in (self.red, self.yellow, self.green):
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="led-controller")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if GPIO is not None:
            for pin in (self.red, self.yellow, self.green):
                GPIO.output(pin, GPIO.LOW)

    def activate(self, state: LedState) -> None:
        with self._lock:
            self._states.add(state)

    def deactivate(self, state: LedState) -> None:
        with self._lock:
            self._states.discard(state)
            if not self._states:
                self._states.add(LedState.READY)

    def set_exclusive(self, state: LedState) -> None:
        with self._lock:
            self._states = {state}

    def _active_state(self) -> LedState:
        with self._lock:
            if not self._states:
                return LedState.READY
            return max(self._states, key=lambda s: _STATE_PRIORITY.get(s, 0))

    def _set_pins(self, red: bool, yellow: bool, green: bool) -> None:
        if GPIO is None:
            return
        GPIO.output(self.red, GPIO.HIGH if red else GPIO.LOW)
        GPIO.output(self.yellow, GPIO.HIGH if yellow else GPIO.LOW)
        GPIO.output(self.green, GPIO.HIGH if green else GPIO.LOW)

    def _sleep(self, seconds: float) -> bool:
        return not self._stop.wait(seconds)

    def _run(self) -> None:
        while not self._stop.is_set():
            state = self._active_state()
            if state == LedState.READY:
                self._set_pins(False, False, True)
                self._sleep(1.0)
            elif state == LedState.BOOT_INSTALL:
                self._pattern_boot_install()
            elif state == LedState.INSTALL_STEP_OK:
                self._pattern_both_blink(10)
            elif state == LedState.BOOT_COMPLETE:
                self._pattern_boot_complete()
            elif state == LedState.ALERT:
                self._pattern_alert_entry()
            elif state == LedState.RISING:
                self._pattern_yellow_fast()
            elif state == LedState.FALLING:
                self._pattern_yellow_falling()
            elif state == LedState.ZONE_20KM:
                self._pattern_red_20km()
            elif state == LedState.ZONE_10KM:
                self._pattern_red_10km()

    def _pattern_boot_install(self) -> None:
        progress = 0.5
        if self._progress_callback is not None:
            # type: ignore[operator]
            progress = float(self._progress_callback())
        interval = max(0.2, 1.5 - progress)
        self._set_pins(False, True, False)
        if not self._sleep(interval):
            return
        self._set_pins(False, False, True)
        self._sleep(interval)

    def _pattern_both_blink(self, count: int) -> None:
        for _ in range(count):
            self._set_pins(True, True, False)
            if not self._sleep(1.0):
                return
            self._set_pins(False, False, False)
            if not self._sleep(1.0):
                return
        with self._lock:
            self._states.discard(LedState.INSTALL_STEP_OK)

    def _pattern_boot_complete(self) -> None:
        for _ in range(10):
            self._set_pins(True, True, False)
            if not self._sleep(1.0):
                return
            self._set_pins(False, False, True)
            if not self._sleep(1.0):
                return
        with self._lock:
            self._states.discard(LedState.BOOT_COMPLETE)

    def _pattern_alert_entry(self) -> None:
        self._set_pins(False, False, False)
        for _ in range(2):
            self._set_pins(False, True, False)
            if not self._sleep(0.25):
                return
            self._set_pins(False, False, False)
            if not self._sleep(0.25):
                return
        self._sleep(0.5)

    def _pattern_yellow_fast(self) -> None:
        self._set_pins(False, True, False)
        if not self._sleep(0.2):
            return
        self._set_pins(False, False, False)
        self._sleep(0.2)

    def _pattern_yellow_falling(self) -> None:
        self._set_pins(False, True, False)
        if not self._sleep(0.2):
            return
        self._set_pins(False, False, False)
        if not self._sleep(0.4):
            return

    def _pattern_red_20km(self) -> None:
        self._set_pins(True, False, False)
        if not self._sleep(0.2):
            return
        self._set_pins(True, False, False)
        if not self._sleep(0.2):
            return
        self._set_pins(False, False, False)
        if not self._sleep(0.2):
            return
        self._set_pins(False, False, False)
        self._sleep(0.2)
        # Yellow trend handled by parallel state in same loop iteration
        self._apply_yellow_overlay()

    def _pattern_red_10km(self) -> None:
        self._set_pins(True, False, False)
        if not self._sleep(0.5):
            return
        self._set_pins(False, False, False)
        self._sleep(0.5)

    def _apply_yellow_overlay(self) -> None:
        with self._lock:
            if LedState.RISING in self._states:
                self._set_pins(False, True, False)
                time.sleep(0.15)
                self._set_pins(False, False, False)
            elif LedState.FALLING in self._states:
                self._set_pins(False, True, False)
                time.sleep(0.15)
                self._set_pins(False, False, False)
                time.sleep(0.3)


def run_boot_sequence(led: LedController, steps: int = 5) -> None:
    """Run install boot LED patterns (blocking) — final phase only."""
    led.set_exclusive(LedState.BOOT_COMPLETE)
    time.sleep(20)
