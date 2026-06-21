"""System information window."""

from __future__ import annotations

import platform
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from app.boot_reason import read_boot_reason
from app.config_loader import get_data_dir
from app.sensor_as3935 import AS3935


def _cpu_temp() -> str:
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    if path.exists():
        try:
            return f"{int(path.read_text().strip()) / 1000:.1f} °C"
        except (ValueError, OSError):
            pass
    return "n/a"


def _wifi_signal() -> str:
    try:
        out = subprocess.run(
            ["iwconfig", "wlan0"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in out.stdout.splitlines():
            if "Signal level" in line:
                return line.split("Signal level=")[-1].strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    try:
        out = subprocess.run(
            ["nmcli", "-f", "SIGNAL", "dev", "wifi"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in out.stdout.splitlines()[1:]:
            val = line.strip()
            if val.isdigit():
                return f"{val}%"
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return "n/a"


def _uptime() -> str:
    try:
        sec = float(Path("/proc/uptime").read_text().split()[0])
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        return f"{h}h {m}m"
    except (OSError, ValueError, IndexError):
        return "n/a"


def open_system_info(
    parent: tk.Tk,
    config: dict,
    sensor: AS3935 | None,
    version: str,
) -> None:
    win = tk.Toplevel(parent)
    win.title("System")
    win.configure(bg="#16213e")
    win.geometry("550x400")

    tuning = sensor.get_tuning_status() if sensor else {
        "status": "n/a", "tuning_raw": None}
    boot = read_boot_reason(get_data_dir(config))

    lines = [
        f"Version:      {version}",
        f"Plattform:    {platform.machine()} / {platform.system()}",
        f"CPU-Temp:     {_cpu_temp()}",
        f"WLAN:         {_wifi_signal()}",
        f"Uptime:       {_uptime()}",
        f"Tuning AS3935: {tuning['status']} (raw={tuning.get('tuning_raw')})",
        f"Boot-Ursache: {boot.get('reason', 'unknown')}",
        f"Boot-Zeit:    {boot.get('ts', '-')}",
    ]

    frame = tk.Frame(win, bg="#16213e", padx=16, pady=16)
    frame.pack(fill=tk.BOTH, expand=True)
    tk.Label(frame, text="\n".join(lines), justify=tk.LEFT, fg="#eee",
             bg="#16213e", font=("Segoe UI", 14)).pack(anchor=tk.W)
    ttk.Button(frame, text="Schließen", command=win.destroy).pack(pady=8)
