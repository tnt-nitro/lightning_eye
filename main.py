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


def safe_cwd() -> None:
    """Always use a valid working directory (avoids git errors after rmdir)."""
    home = Path.home()
    home.mkdir(parents=True, exist_ok=True)
    os.chdir(home)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    log(f"$ {' '.join(cmd)}")
    if cwd is None:
        cwd = Path.home()
    return subprocess.run(cmd, cwd=cwd, check=check)


def _preserve_user_files() -> dict[str, Path]:
    """Backup data/logs before re-cloning a broken install."""
    preserved: dict[str, Path] = {}
    backup_root = Path.home() / ".lightning_eye_backup"
    if backup_root.exists():
        shutil.rmtree(backup_root, ignore_errors=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    for name in ("data", "logs", ".bootstrap_done"):
        src = INSTALL_DIR / name
        if not src.exists():
            continue
        dest = backup_root / name
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        preserved[name] = dest
    return preserved


def _restore_user_files(preserved: dict[str, Path]) -> None:
    for name, src in preserved.items():
        dest = INSTALL_DIR / name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    backup_root = Path.home() / ".lightning_eye_backup"
    if backup_root.exists():
        shutil.rmtree(backup_root, ignore_errors=True)


def ensure_git_repo() -> None:
    safe_cwd()
    if (INSTALL_DIR / ".git").exists():
        run(["git", "fetch", "origin"], cwd=INSTALL_DIR)
        run(["git", "reset", "--hard", "origin/main"], cwd=INSTALL_DIR)
        return

    INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)
    preserved: dict[str, Path] = {}
    if INSTALL_DIR.exists():
        log("WARN: ~/lightning_eye existiert ohne .git — Klone neu (Daten werden behalten)")
        preserved = _preserve_user_files()
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)

    run(["git", "clone", REPO_URL, str(INSTALL_DIR)], cwd=Path.home())
    if preserved:
        _restore_user_files(preserved)


def ensure_venv() -> Path:
    python = VENV_DIR / "bin" / "python"
    if not python.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    pip = VENV_DIR / "bin" / "pip"
    run([str(pip), "install", "--upgrade", "pip"])
    run([str(pip), "install", "-r", "requirements.txt"], cwd=INSTALL_DIR)
    return python


def install_system_packages() -> None:
    packages = [
        "git", "python3-venv", "python3-pip", "python3-tk", "i2c-tools", "x11-utils",
        "gpiod", "libgpiod3", "python3-libgpiod",
    ]
    if shutil.which("apt-get"):
        try:
            run(["sudo", "apt-get", "update"], check=False)
            result = run(["sudo", "apt-get", "install",
                         "-y", *packages], check=False)
            if result.returncode != 0:
                run(["sudo", "apt-get", "install", "-y",
                    "gpiod", "libgpiod2"], check=False)
        except (subprocess.CalledProcessError, FileNotFoundError):
            log("Hinweis: apt-Pakete manuell installieren (git, python3-venv, python3-tk, i2c-tools, gpiod)")


def setup_pi_permissions() -> None:
    """Add pi user to gpio/i2c groups and enable systemd user linger."""
    user = os.environ.get("USER", "pi")
    for group in ("gpio", "i2c", "spi"):
        run(["sudo", "usermod", "-aG", group, user], check=False)
    run(["sudo", "loginctl", "enable-linger", user], check=False)


def write_start_script() -> Path:
    src = INSTALL_DIR / "start.sh"
    if not src.exists():
        log("WARN: start.sh fehlt im Repo")
        return src
    run(["chmod", "+x", str(src)], check=False)
    return src


def write_systemd(start_script: Path) -> None:
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    service = f"""[Unit]
Description=Lightning Eye Blitzsensor
After=network-online.target graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
WorkingDirectory={INSTALL_DIR}
Environment=DISPLAY=:0
Environment=XAUTHORITY={Path.home()}/.Xauthority
ExecStart={start_script}
ExecStopPost={INSTALL_DIR / ".venv/bin/python"} -m app.leds_off
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""
    service_path = SYSTEMD_DIR / "lightning-eye.service"
    service_path.write_text(service, encoding="utf-8")
    run(["systemctl", "--user", "daemon-reload"], check=False)
    run(["systemctl", "--user", "enable", "lightning-eye.service"], check=False)


def write_autostart(start_script: Path) -> None:
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    desktop = f"""[Desktop Entry]
Type=Application
Name=Lightning Eye
Comment=Blitzsensor Station
Exec={start_script}
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=8
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
    safe_cwd()
    log("Bootstrap startet")
    install_system_packages()
    ensure_git_repo()
    python = ensure_venv()

    first_install = not MARKER.exists()
    setup_pi_permissions()
    start_script = write_start_script()
    write_systemd(start_script)
    write_autostart(start_script)

    if first_install:
        log("Erstinstallation — Boot-Sequenz und Neustart")
        write_boot_reason("install")
        MARKER.write_text("ok", encoding="utf-8")
        run_boot_led_sequence()
        reboot_system()
        return

    log("Installation vorhanden — starte Anwendung")
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", str(Path.home() / ".Xauthority"))
    env.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")
    os.chdir(INSTALL_DIR)
    os.execve(str(python), [str(python), "-m", "app.run"], env)


if __name__ == "__main__":
    main()
