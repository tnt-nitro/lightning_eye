"""Main Tkinter window for Lightning Eye."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from app.blocks import BlockManager
from app.database import Database
from app.dht_reader import DhtReader
from app.gui.menus.block_detail import open_block_detail
from app.gui.menus.export_dialog import open_export_dialog
from app.gui.menus.statistics import open_statistics
from app.gui.menus.system_info import open_system_info
from app.gui.sparkline import Sparkline
from app.stats import format_duration, snapshot


class MainWindow:
    def __init__(
        self,
        db: Database,
        block_mgr: BlockManager,
        dht: DhtReader,
        config: dict,
        version: str,
        get_app_state: Callable[[], dict[str, Any]],
        get_sensor_status: Callable[[], dict[str, Any]],
        sensor: Any = None,
    ) -> None:
        self.db = db
        self.block_mgr = block_mgr
        self.dht = dht
        self.config = config
        self.version = version
        self.get_app_state = get_app_state
        self.get_sensor_status = get_sensor_status
        self.sensor = sensor

        self.root = tk.Tk()
        self.root.title("Lightning Eye")
        self.root.configure(bg="#0f0f1a")
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.root.attributes(
            "-fullscreen", False))
        self.root.bind(
            "<F11>", lambda e: self.root.attributes("-fullscreen", True))

        self._build_menu()
        self._build_ui()
        self.refresh()

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        details = tk.Menu(menubar, tearoff=0)
        details.add_command(
            label="Statistik", command=lambda: open_statistics(self.root, self.db))
        details.add_command(
            label="Block-Details",
            command=lambda: open_block_detail(
                self.root, self.db, self.block_mgr),
        )
        details.add_command(
            label="System",
            command=lambda: open_system_info(
                self.root,
                self.config,
                self.get_sensor_status,
                self.version,
            ),
        )
        details.add_command(
            label="Export / QR",
            command=lambda: open_export_dialog(
                self.root,
                self.db,
                self.config,
                int(self.config.get("http", {}).get("port", 8765)),
            ),
        )
        details.add_separator()
        details.add_command(label="Beenden", command=self.root.quit)
        menubar.add_cascade(label="Details", menu=details)
        self.root.config(menu=menubar)

    def _build_ui(self) -> None:
        pad = {"padx": 20, "pady": 8}
        self.lbl_status = tk.Label(
            self.root, fg="#4caf50", bg="#0f0f1a", font=("Segoe UI", 22, "bold"))
        self.lbl_status.pack(anchor=tk.W, **pad)

        self.lbl_quiet = tk.Label(
            self.root, fg="#aaa", bg="#0f0f1a", font=("Segoe UI", 16))
        self.lbl_quiet.pack(anchor=tk.W, padx=20)

        sep = ttk.Separator(self.root, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=20, pady=4)

        self.lbl_counters = tk.Label(
            self.root, fg="#eee", bg="#0f0f1a", font=("Segoe UI", 16))
        self.lbl_counters.pack(anchor=tk.W, **pad)

        self.lbl_windows = tk.Label(
            self.root, fg="#ccc", bg="#0f0f1a", font=("Segoe UI", 14), justify=tk.LEFT)
        self.lbl_windows.pack(anchor=tk.W, **pad)

        self.lbl_block = tk.Label(self.root, fg="#eee", bg="#0f0f1a", font=(
            "Segoe UI", 14), justify=tk.LEFT)
        self.lbl_block.pack(anchor=tk.W, **pad)

        self.lbl_env = tk.Label(self.root, fg="#81d4fa",
                                bg="#0f0f1a", font=("Segoe UI", 16))
        self.lbl_env.pack(anchor=tk.W, **pad)

        self.lbl_sensor = tk.Label(
            self.root, fg="#aaa", bg="#0f0f1a", font=("Segoe UI", 14))
        self.lbl_sensor.pack(anchor=tk.W, padx=20)

        tk.Label(self.root, text="Entfernung (letzte 20 relevante)", fg="#888", bg="#0f0f1a", font=("Segoe UI", 12)).pack(
            anchor=tk.W, padx=20
        )
        self.sparkline = Sparkline(self.root, height=80)
        self.sparkline.pack(fill=tk.X, padx=20, pady=4)

        self.lbl_version = tk.Label(
            self.root, fg="#555", bg="#0f0f1a", font=("Segoe UI", 10))
        self.lbl_version.pack(side=tk.BOTTOM, anchor=tk.SE, padx=12, pady=8)

    def refresh(self) -> None:
        snap = snapshot(self.db, self.config)
        app_state = self.get_app_state()
        state_label = app_state.get("label", "BEREIT")
        color = app_state.get("color", "#4caf50")
        self.lbl_status.config(text=f"● {state_label}", fg=color)

        quiet = snap.get("quiet_since")
        self.lbl_quiet.config(text=f"Ruhe seit: {quiet or '—'}")

        c = snap["counters_today"]
        self.lbl_counters.config(
            text=f"Heute — Gesamt: {c['total']}   Relevant: {c['relevant']}   Störung/negativ: {c['negative']}"
        )

        w = snap["windows"]
        self.lbl_windows.config(
            text=(
                f"Relevanz-Anteil (positiv/gesamt)\n"
                f"  60 Min: {w['60m']}%    24 h: {w['24h']}%    7 Tage: {w['7d']}%    Jahr: {w['365d']}%"
            )
        )

        block = self.block_mgr.current_block_summary()
        last = snap.get("last_relevant")
        block_line = f"Block #{block.get('block_id', '-')}  ·  {block.get('relevant_count', 0)} relevant  ·  {format_duration(block.get('span_seconds', 0))}"
        if last:
            block_line += f"\nLetzte: {last.get('distance_km')} km · Energie {last.get('energy')} · {last.get('ts', '')[:19]}"
        self.lbl_block.config(text=block_line)

        temp, hum = self.dht.snapshot()
        temp_s = f"{temp:.1f}°C" if temp is not None else "—"
        hum_s = f"{hum:.0f}% rF" if hum is not None else "—"
        self.lbl_env.config(text=f"Umgebung: {temp_s}  ·  {hum_s}")

        sensor = self.get_sensor_status()
        sensor_color = "#4caf50" if sensor.get("ok") else "#ff9800"
        sensor_line = (
            f"AS3935 @ {sensor.get('i2c_address', '?')}: "
            f"{sensor.get('label', 'Unbekannt')}"
        )
        if sensor.get("tuning_status") and sensor.get("ok"):
            sensor_line += f" · Tuning: {sensor['tuning_status']}"
        if sensor.get("detail"):
            sensor_line += f" — {sensor['detail']}"
        self.lbl_sensor.config(text=sensor_line, fg=sensor_color)

        self.sparkline.set_values(snap.get("sparkline", []))
        self.lbl_version.config(text=f"v{self.version}")

        self.root.after(1000, self.refresh)

    def run(self) -> None:
        self.root.mainloop()
