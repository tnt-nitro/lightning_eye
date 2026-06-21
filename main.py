#!/usr/bin/env python3
"""
Lightning Eye bootstrap starter.

Upload this single file via WinSCP to /home/pi/main.py and run once:
    python3 ~/main.py

It clones/updates the GitHub repo, installs dependencies, configures autostart,
runs the boot LED sequence on first install, and reboots.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/tnt-nitro/lightning_eye"
INSTALL_DIR = Path.home() / "lightning_eye"
VENV_DIR = INSTALL_DIR / ".venv"
MARKER = INSTALL_DIR / ".bootstrap_done"
DATA_DIR = INSTALL_DIR / "data"
SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
AUTOSTART_DIR = Path.home() / ".config" / "autostart"


def log(msg: str) -> None:
    print(f"[lightning_eye] {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    log(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check)


def ensure_git_repo() -> None:
    if (INSTALL_DIR / ".git").exists():
        run(["git", "fetch", "origin"], cwd=INSTALL_DIR)
        run(["git", "reset", "--hard", "origin/main"], cwd=INSTALL_DIR)
    else:
        INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)
        if INSTALL_DIR.exists() and not any(INSTALL_DIR.iterdir()):
            INSTALL_DIR.rmdir()
        run(["git", "clone", REPO_URL, str(INSTALL_DIR)])


def ensure_venv() -> Path:
    python = VENV_DIR / "bin" / "python"
    if not python.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    pip = VENV_DIR / "bin" / "pip"
    run([str(pip), "install", "--upgrade", "pip"])
    run([str(pip), "install", "-r", "requirements.txt"], cwd=INSTALL_DIR)
    return python


def install_system_packages() -> None:
    packages = ["git", "python3-venv",
                "python3-pip", "python3-tk", "i2c-tools"]
    if shutil.which("apt-get"):
        try:
            run(["sudo", "apt-get", "update"], check=False)
            run(["sudo", "apt-get", "install", "-y", *packages], check=False)
        except (subprocess.CalledProcessError, FileNotFoundError):
            log("Hinweis: apt-Pakete manuell installieren (git, python3-venv, python3-tk, i2c-tools)")


def write_systemd(python: Path) -> None:
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    service = f"""[Unit]
Description=Lightning Eye Blitzsensor
After=network-online.target

[Service]
Type=simple
WorkingDirectory={INSTALL_DIR}
Environment=DISPLAY=:0
ExecStart={python} {INSTALL_DIR / 'app' / 'run.py'}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""
    service_path = SYSTEMD_DIR / "lightning-eye.service"
    service_path.write_text(service, encoding="utf-8")
    run(["systemctl", "--user", "daemon-reload"], check=False)
    run(["systemctl", "--user", "enable", "lightning-eye.service"], check=False)


def write_autostart(python: Path) -> None:
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    desktop = f"""[Desktop Entry]
Type=Application
Name=Lightning Eye
Exec={python} {INSTALL_DIR / 'app' / 'run.py'}
X-GNOME-Autostart-enabled=true
"""
    (AUTOSTART_DIR / "lightning-eye.desktop").write_text(desktop, encoding="utf-8")


def write_boot_reason(reason: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    import json
    from datetime import datetime, timezone

    payload = {"reason": reason, "ts": datetime.now(timezone.utc).isoformat()}
    (DATA_DIR / "last_boot.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_boot_led_sequence() -> None:
    try:
        sys.path.insert(0, str(INSTALL_DIR))
        from app.led_controller import LedController, LedState, run_boot_sequence

        led = LedController(17, 27, 22)
        led.start()
        progress = {"v": 0.0}
        led.set_progress_callback(lambda: progress["v"])

        for i in range(5):
            progress["v"] = (i + 1) / 5
            led.set_exclusive(LedState.INSTALL_STEP_OK)
            import time
            time.sleep(20)
            led.activate(LedState.BOOT_INSTALL)

        run_boot_sequence(led)
        led.stop()
    except Exception as exc:
        log(f"Boot-LED-Sequenz übersprungen: {exc}")


def reboot_system() -> None:
    log("Neustart in 3 Sekunden...")
    import time
    time.sleep(3)
    if shutil.which("systemctl"):
        run(["sudo", "systemctl", "reboot"], check=False)
    else:
        log("Bitte manuell neu starten.")


def main() -> None:
    log("Bootstrap startet")
    install_system_packages()
    ensure_git_repo()
    python = ensure_venv()

    first_install = not MARKER.exists()
    write_systemd(python)
    write_autostart(python)

    if first_install:
        log("Erstinstallation — Boot-Sequenz und Neustart")
        write_boot_reason("install")
        MARKER.write_text("ok", encoding="utf-8")
        run_boot_led_sequence()
        reboot_system()
        return

    log("Installation vorhanden — starte Anwendung")
    os.execv(str(python), [str(python), str(INSTALL_DIR / "app" / "run.py")])


if __name__ == "__main__":
    main()
