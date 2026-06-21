"""Lightning Eye main application entry point."""

from __future__ import annotations
from app.watchdog import Watchdog
from app.updater import Updater
from app.stats import distance_trend, snapshot
from app.sensor_as3935 import AS3935, LightningEvent, is_relevant
from app.led_controller import LedController, LedState
from app.http_status import StatusServer
from app.gui.main_window import MainWindow
from app.dht_reader import DhtReader
from app.database import Database
from app.config_loader import get_data_dir, get_gpio, load_config
from app.buzzer_controller import BuzzerController
from app.boot_reason import read_boot_reason, write_boot_reason
from app.blocks import BlockManager

import logging
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lightning_eye")


class Application:
    def __init__(self) -> None:
        self.config = load_config(ROOT)
        self.install_dir = ROOT
        self.config["install_dir"] = str(ROOT)
        self.data_dir = get_data_dir(self.config)
        self.version = (self.install_dir /
                        "VERSION").read_text(encoding="utf-8").strip()
        self.db = Database(self.data_dir / "events.db")
        self.block_mgr = BlockManager(
            self.db,
            timeout_minutes=int(self.config.get(
                "blocks", {}).get("timeout_minutes", 5)),
        )
        gpio = get_gpio(self.config)
        self.led = LedController(
            gpio["led_red"], gpio["led_yellow"], gpio["led_green"])
        self.buzzer = BuzzerController(gpio["buzzer"])
        self.dht = DhtReader(gpio["dht"])
        self.sensor: AS3935 | None = None
        self._alert_until: datetime | None = None
        self._in_zone_10 = False
        self._in_zone_20 = False
        self._state_lock = threading.Lock()
        self._app_label = "BEREIT"
        self._app_color = "#4caf50"

    def _write_boot(self, reason: str) -> None:
        write_boot_reason(self.data_dir, reason)
        self.db.log_boot(reason)

    def _on_event(self, event: LightningEvent) -> None:
        relevant = is_relevant(event, self.config)
        block_id = self.block_mgr.on_event(relevant)
        temp, hum = self.dht.snapshot()
        self.db.insert_event(
            event.event_type,
            event.distance_km,
            event.energy,
            relevant,
            block_id,
            temp,
            hum,
        )
        if not relevant:
            return

        logger.info(
            "Relevant strike: %.1f km, energy=%s",
            event.distance_km or 0,
            event.energy,
        )
        self._handle_alert_states(event)

    def _handle_alert_states(self, event: LightningEvent) -> None:
        zones = self.config.get("zones", {})
        yellow_km = float(zones.get("yellow_km", 20))
        red_km = float(zones.get("red_km", 10))
        alert_min = int(self.config.get("alert", {}).get("active_minutes", 60))
        dist = event.distance_km or 999

        with self._state_lock:
            self._alert_until = datetime.now(
                timezone.utc) + timedelta(minutes=alert_min)
            self.led.deactivate(LedState.READY)
            self.led.activate(LedState.ALERT)

            trend = distance_trend(self.db)
            self.led.deactivate(LedState.RISING)
            self.led.deactivate(LedState.FALLING)
            if trend == "rising":
                self.led.activate(LedState.RISING)
            elif trend == "falling":
                self.led.activate(LedState.FALLING)

            was_10 = self._in_zone_10
            was_20 = self._in_zone_20
            self._in_zone_10 = dist <= red_km
            self._in_zone_20 = dist <= yellow_km

            if self._in_zone_10:
                self.led.activate(LedState.ZONE_10KM)
                self.led.deactivate(LedState.ZONE_20KM)
                if not was_10:
                    self.buzzer.zone_10_enter()
                    self._app_label = "GEWITTER < 10 km"
                    self._app_color = "#f44336"
            elif self._in_zone_20:
                self.led.deactivate(LedState.ZONE_10KM)
                self.led.activate(LedState.ZONE_20KM)
                if was_10 and not self._in_zone_10:
                    self.buzzer.zone_10_leave()
                self._app_label = "GEWITTER < 20 km"
                self._app_color = "#ff9800"
            else:
                self.led.deactivate(LedState.ZONE_10KM)
                self.led.deactivate(LedState.ZONE_20KM)
                if was_10:
                    self.buzzer.zone_10_leave()
                self._app_label = "ALERT"
                self._app_color = "#ffeb3b"

        threading.Thread(target=self._alert_timer_loop, daemon=True).start()

    def _alert_timer_loop(self) -> None:
        time.sleep(2)
        while True:
            with self._state_lock:
                if self._alert_until and datetime.now(timezone.utc) >= self._alert_until:
                    if not self._in_zone_10 and not self._in_zone_20:
                        self._clear_alert()
                    break
            time.sleep(5)

    def _clear_alert(self) -> None:
        self._alert_until = None
        for s in (
            LedState.ALERT,
            LedState.RISING,
            LedState.FALLING,
            LedState.ZONE_10KM,
            LedState.ZONE_20KM,
        ):
            self.led.deactivate(s)
        self.led.activate(LedState.READY)
        self._app_label = "BEREIT"
        self._app_color = "#4caf50"
        self._in_zone_10 = False
        self._in_zone_20 = False

    def get_app_state(self) -> dict:
        with self._state_lock:
            return {"label": self._app_label, "color": self._app_color}

    def _build_status(self) -> dict:
        snap = snapshot(self.db, self.config)
        temp, hum = self.dht.snapshot()
        return {
            **snap,
            "app_state": self.get_app_state(),
            "environment": {"temp_c": temp, "humidity_pct": hum},
            "version": self.version,
        }

    def start(self) -> None:
        boot = read_boot_reason(self.data_dir)
        reason = boot.get("reason", "manual")
        self.db.log_boot(str(reason))

        self.led.start()
        self.led.set_exclusive(LedState.READY)
        self.dht.start()

        gpio = get_gpio(self.config)
        sensor_cfg = self.config.get("sensor", {})
        self.sensor = AS3935(
            address=int(sensor_cfg.get("i2c_address", 0x03)),
            irq_pin=gpio["irq"],
            indoor=bool(sensor_cfg.get("indoor_mode", True)),
            on_event=self._on_event,
        )
        try:
            self.sensor.start()
        except Exception as exc:
            logger.error("Sensor start failed (simulation mode): %s", exc)
            self.sensor = None

        if self.sensor:
            Watchdog(
                get_heartbeat=lambda: self.sensor.last_heartbeat,
                reinit=self.sensor.reinit,
            ).start()

        http_port = int(self.config.get("http", {}).get("port", 8765))
        self._http = StatusServer(http_port, self._build_status)
        self._http.start()

        update_cfg = self.config.get("update", {})
        Updater(
            install_dir=self.install_dir,
            db=self.db,
            check_interval_hours=float(
                update_cfg.get("check_interval_hours", 6)),
            defer_minutes=int(update_cfg.get("defer_minutes", 60)),
            on_before_restart=lambda r: self._write_boot(r),
        ).start()

        if reason in ("install", "update"):
            self.buzzer.boot_complete()

        gui = MainWindow(
            db=self.db,
            block_mgr=self.block_mgr,
            dht=self.dht,
            config=self.config,
            version=self.version,
            get_app_state=self.get_app_state,
            sensor=self.sensor,
        )
        try:
            gui.run()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self.sensor:
            self.sensor.stop()
        self.dht.stop()
        self.led.stop()
        self.buzzer.close()


def main() -> None:
    app = Application()
    app.start()


if __name__ == "__main__":
    main()
