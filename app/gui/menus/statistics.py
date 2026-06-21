"""Statistics detail window."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app import stats as stats_mod
from app.database import Database


def open_statistics(parent: tk.Tk, db: Database) -> None:
    win = tk.Toplevel(parent)
    win.title("Statistik")
    win.configure(bg="#16213e")
    win.geometry("700x500")

    frame = tk.Frame(win, bg="#16213e", padx=16, pady=16)
    frame.pack(fill=tk.BOTH, expand=True)

    rate = stats_mod.disturbance_rate(db)
    buckets = stats_mod.distance_buckets(db)
    heatmap = stats_mod.hourly_heatmap(db)
    max_h = max(heatmap) if heatmap else 1

    lines = [
        f"Störungsquote (7 Tage): {rate}%",
        "",
        "Entfernungs-Buckets (7 Tage):",
        f"  < 10 km:   {buckets['under_10']}",
        f"  10-20 km:  {buckets['10_20']}",
        f"  20-40 km:  {buckets['20_40']}",
        f"  > 40 km:   {buckets['over_40']}",
        "",
        "Tageszeit-Heatmap (relevant, 7 Tage):",
    ]
    tk.Label(frame, text="\n".join(lines), justify=tk.LEFT, fg="#eee",
             bg="#16213e", font=("Segoe UI", 14)).pack(anchor=tk.W)

    canvas = tk.Canvas(frame, height=120, bg="#1a1a2e", highlightthickness=0)
    canvas.pack(fill=tk.X, pady=12)
    bar_w = 24
    for hour, count in enumerate(heatmap):
        x0 = 10 + hour * (bar_w + 2)
        bar_h = (count / max_h) * 90 if max_h else 0
        canvas.create_rectangle(x0, 100 - bar_h, x0 +
                                bar_w, 100, fill="#e94560", outline="")
        canvas.create_text(x0 + bar_w // 2, 110, text=str(hour),
                           fill="#888", font=("Segoe UI", 8))

    ttk.Button(frame, text="Schließen", command=win.destroy).pack(pady=8)
