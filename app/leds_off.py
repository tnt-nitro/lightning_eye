"""Turn off all traffic-light LEDs — for systemd ExecStopPost or manual use."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")

from app.config_loader import get_gpio, load_config
from app.led_controller import LedController


def main() -> None:
    config = load_config(ROOT)
    gpio = get_gpio(config)
    LedController.force_all_off(gpio["led_red"], gpio["led_yellow"], gpio["led_green"])
    print("LEDs aus")


if __name__ == "__main__":
    main()
