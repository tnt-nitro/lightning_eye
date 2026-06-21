"""Block detail window."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.blocks import BlockManager
from app.database import Database
from app.stats import format_duration


def open_block_detail(parent: tk.Tk, db: Database, block_mgr: BlockManager) -> None:
    win = tk.Toplevel(parent)
    win.title("Block-Details")
    win.configure(bg="#16213e")
    win.geometry("600x400")

    block_id = block_mgr.current_block_id()
    if block_id is None:
        tk.Label(win, text="Kein aktiver Block", fg="#eee",
                 bg="#16213e", font=("Segoe UI", 14)).pack(pady=20)
        return

    stats = db.block_stats(block_id)
    events = db.events_in_block(block_id, relevant_only=True)

    lines = [
        f"Block #{stats.get('block_id', block_id)}",
        f"Start:     {stats.get('started_at', '-')}",
        f"Ende:      {stats.get('ended_at') or 'läuft'}",
        f"Spanne:    {format_duration(stats.get('span_seconds', 0))}",
        f"Relevant:  {stats.get('relevant_count', 0)}",
        "",
        f"Entfernung Min/Max/Ø: {stats.get('distance_min')} / {stats.get('distance_max')} / {round(stats.get('distance_avg') or 0, 1)} km",
        f"Energie Min/Max/Ø:    {stats.get('energy_min')} / {stats.get('energy_max')} / {round(stats.get('energy_avg') or 0, 0)}",
        "",
        "Relevante Messungen:",
    ]
    for e in events[-10:]:
        lines.append(
            f"  {e['ts'][:19]}  {e['distance_km']} km  E={e['energy']}  {e['temp_c']}°C {e['humidity_pct']}%"
        )

    frame = tk.Frame(win, bg="#16213e", padx=16, pady=16)
    frame.pack(fill=tk.BOTH, expand=True)
    tk.Label(frame, text="\n".join(lines), justify=tk.LEFT, fg="#eee",
             bg="#16213e", font=("Consolas", 11)).pack(anchor=tk.W)
    ttk.Button(frame, text="Schließen", command=win.destroy).pack(pady=8)
