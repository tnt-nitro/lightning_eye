"""LED traffic light controller with pattern state machine."""

from __future__ import annotations

import atexit
import logging
import os
import threading
import time
from enum import Enum, auto

logger = logging.getLogger(__name__)

try:
    from gpiozero import LED, OutputDevice
except ImportError:
    LED = None  # type: ignore
    OutputDevice = None  # type: ignore

_active_controller: "LedController | None" = None


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
        self._red_led: LED | None = None
        self._yellow_led: LED | None = None
        self._green_led: LED | None = None
        self._states: set[LedState] = {LedState.READY}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._progress_callback: object | None = None

    def set_progress_callback(self, cb: object) -> None:
        self._progress_callback = cb

    @staticmethod
    def force_all_off(red: int, yellow: int, green: int) -> None:
        """Force traffic-light pins LOW (works even without a running app)."""
        os.environ.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")
        if OutputDevice is None:
            return
        for pin in (red, yellow, green):
            try:
                dev = OutputDevice(pin, active_high=True, initial_value=False)
                dev.off()
                dev.close()
            except Exception as exc:
                logger.debug("force_all_off pin %s: %s", pin, exc)

    def all_off(self) -> None:
        """Stop patterns and turn all LEDs off."""
        global _active_controller
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        for led in (self._red_led, self._yellow_led, self._green_led):
            if led is not None:
                try:
                    led.off()
                except Exception:
                    pass
        self.force_all_off(self.red, self.yellow, self.green)
        for led in (self._red_led, self._yellow_led, self._green_led):
            if led is not None:
                try:
                    led.close()
                except Exception:
                    pass
        self._red_led = None
        self._yellow_led = None
        self._green_led = None
        if _active_controller is self:
            _active_controller = None

    def start(self) -> None:
        global _active_controller
        if LED is None:
            logger.warning("GPIO unavailable, LED controller running in noop mode")
            return
        self._red_led = LED(self.red)
        self._yellow_led = LED(self.yellow)
        self._green_led = LED(self.green)
        self._stop.clear()
        _active_controller = self
        self._thread = threading.Thread(target=self._run, daemon=False, name="led-controller")
        self._thread.start()

    def stop(self) -> None:
        self.all_off()

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
        if self._red_led is None:
            return
        self._red_led.on() if red else self._red_led.off()
        self._yellow_led.on() if yellow else self._yellow_led.off()
        self._green_led.on() if green else self._green_led.off()

    def _sleep(self, seconds: float) -> bool:
        return not self._stop.wait(seconds)

    def _run(self) -> None:
        while not self._stop.is_set():
            state = self._active_state()
            if state == LedState.READY:
                if self._stop.is_set():
                    break
                self._set_pins(False, False, True)
                if not self._sleep(1.0):
                    break
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


def _atexit_leds_off() -> None:
    if _active_controller is not None:
        _active_controller.all_off()
    else:
        # Default Pi wiring — fallback if process dies without controller ref
        LedController.force_all_off(17, 27, 22)


atexit.register(_atexit_leds_off)


def run_boot_sequence(led: LedController, steps: int = 5) -> None:
    led.set_exclusive(LedState.BOOT_COMPLETE)
    time.sleep(20)
