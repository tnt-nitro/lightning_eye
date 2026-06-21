"""AMS AS3935 lightning sensor driver (DFRobot SEN0290)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

logger = logging.getLogger(__name__)

try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None  # type: ignore

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None  # type: ignore


class InterruptType(IntEnum):
    NOISE = 0
    DISTURBER = 1
    LIGHTNING = 2


@dataclass
class LightningEvent:
    event_type: str
    distance_km: float | None
    energy: int | None
    raw_distance: int | None
    raw_energy: int | None


# Register map (AMS AS3935)
_REG_SENSE_L = 0x00
_REG_SENSE_M = 0x01
_REG_FLAGS = 0x03
_REG_INT = 0x03
_REG_S_LIG_L = 0x04
_REG_S_LIG_M = 0x05
_REG_LIGHTNING = 0x07
_REG_DISTURBER = 0x01
_REG_LCO_FBD = 0x12
_REG_TUNING = 0x3D


class AS3935:
    def __init__(
        self,
        i2c_bus: int = 1,
        address: int = 0x03,
        irq_pin: int = 4,
        indoor: bool = True,
        on_event: Callable[[LightningEvent], None] | None = None,
    ) -> None:
        self.i2c_bus = i2c_bus
        self.address = address
        self.irq_pin = irq_pin
        self.indoor = indoor
        self.on_event = on_event
        self._bus: SMBus | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_heartbeat = time.monotonic()
        self._lock = threading.Lock()

    @property
    def last_heartbeat(self) -> float:
        return self._last_heartbeat

    def _read_reg(self, reg: int) -> int:
        if self._bus is None:
            raise RuntimeError("Sensor not connected")
        return self._bus.read_byte_data(self.address, reg)

    def _write_reg(self, reg: int, value: int) -> None:
        if self._bus is None:
            raise RuntimeError("Sensor not connected")
        self._bus.write_byte_data(self.address, reg, value & 0xFF)

    def _read_reg16(self, reg_low: int) -> int:
        low = self._read_reg(reg_low)
        high = self._read_reg(reg_low + 1)
        return (high << 8) | low

    def connect(self) -> None:
        if SMBus is None:
            raise RuntimeError("smbus2 not available")
        if self._bus is not None:
            self._bus.close()
        self._bus = SMBus(self.i2c_bus)
        self._init_sensor()
        self._last_heartbeat = time.monotonic()

    def close(self) -> None:
        self.stop()
        if self._bus is not None:
            self._bus.close()
            self._bus = None

    def _init_sensor(self) -> None:
        # Power up and clear disturber
        self._write_reg(_REG_DISTURBER, 0x00)
        time.sleep(0.01)
        # Set indoor/outdoor via REG_AFE_GB (0x00 bits) - use library approach
        # REG0x00: [7:6] AFE, [5:1] noise floor, [0] power
        afe_val = 0x12 if self.indoor else 0x0E  # indoor / outdoor preset
        self._write_reg(0x00, afe_val)
        # Minimum strikes 1, watchdog threshold
        self._write_reg(0x02, 0x24)
        self._write_reg(0x01, 0x40)  # clear disturbers
        logger.info("AS3935 initialized (indoor=%s)", self.indoor)

    def reinit(self) -> None:
        with self._lock:
            logger.warning("Re-initializing AS3935")
            self.connect()

    def ping(self) -> bool:
        try:
            with self._lock:
                val = self._read_reg(_REG_TUNING)
            self._last_heartbeat = time.monotonic()
            return val is not None
        except Exception as exc:
            logger.error("AS3935 ping failed: %s", exc)
            return False

    def get_tuning_status(self) -> dict:
        try:
            with self._lock:
                tuning = self._read_reg(_REG_TUNING) & 0x0F
            # Expected tuning capacitance nibble; 0x0F often means not tuned
            if tuning in (0x05, 0x06, 0x07, 0x08, 0x09):
                status = "OK"
            elif tuning == 0x0F:
                status = "Nicht abgestimmt"
            else:
                status = "Prüfen"
            return {"tuning_raw": tuning, "status": status}
        except Exception as exc:
            return {"tuning_raw": None, "status": f"Fehler: {exc}"}

    def _parse_interrupt(self) -> LightningEvent | None:
        with self._lock:
            flags = self._read_reg(_REG_INT)
            interrupt = (flags >> 4) & 0x01
            if not interrupt:
                return None
            int_type = (flags >> 4) & 0x03
            # Re-read with maskINT per datasheet flow
            int_val = self._read_reg(_REG_INT)
            reason = InterruptType(int_val & 0x03) if (
                int_val & 0x08) else None

        if reason == InterruptType.NOISE:
            return LightningEvent("noise", None, None, None, None)
        if reason == InterruptType.DISTURBER:
            return LightningEvent("disturber", None, None, None, None)

        with self._lock:
            raw_energy = self._read_reg16(_REG_S_LIG_L)
            raw_distance = self._read_reg(_REG_LIGHTNING) & 0x3F

        distance_km = self._raw_to_km(raw_distance)
        return LightningEvent(
            event_type="lightning",
            distance_km=distance_km,
            energy=raw_energy,
            raw_distance=raw_distance,
            raw_energy=raw_energy,
        )

    @staticmethod
    def _raw_to_km(raw: int) -> float:
        if raw == 0:
            return 0.0
        if raw == 1:
            return 0.0
        # AS3935 formula: d = (raw/2) - 1 km approximately for raw >= 2
        return max(0.0, (raw / 2.0) - 1.0)

    def _handle_irq(self, channel: int) -> None:
        try:
            event = self._parse_interrupt()
            self._last_heartbeat = time.monotonic()
            if event and self.on_event:
                self.on_event(event)
        except Exception as exc:
            logger.exception("IRQ handler error: %s", exc)

    def start(self) -> None:
        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available")
        if self._running:
            return
        self.connect()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.irq_pin, GPIO.IN)
        GPIO.add_event_detect(
            self.irq_pin,
            GPIO.RISING,
            callback=self._handle_irq,
            bouncetime=200,
        )
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="as3935-poll")
        self._thread.start()
        logger.info("AS3935 IRQ listener started on GPIO %s", self.irq_pin)

    def stop(self) -> None:
        self._running = False
        if GPIO is not None:
            try:
                GPIO.remove_event_detect(self.irq_pin)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _poll_loop(self) -> None:
        """Fallback polling to catch missed IRQs and refresh heartbeat."""
        while self._running:
            try:
                event = self._parse_interrupt()
                self._last_heartbeat = time.monotonic()
                if event and event.event_type != "noise" and self.on_event:
                    self.on_event(event)
            except Exception as exc:
                logger.debug("Poll error: %s", exc)
            time.sleep(2)


def is_relevant(event: LightningEvent, config: dict) -> bool:
    rel = config.get("relevance", {})
    if rel.get("require_lightning", True) and event.event_type != "lightning":
        return False
    if event.distance_km is None or event.energy is None:
        return False
    max_dist = float(rel.get("max_distance_km", 40))
    min_energy = int(rel.get("min_energy", 0))
    return event.distance_km <= max_dist and event.energy >= min_energy
