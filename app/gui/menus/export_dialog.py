"""CSV export and QR code dialog."""

from __future__ import annotations

import csv
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, ttk

try:
    import qrcode
    from PIL import ImageTk
except ImportError:
    qrcode = None  # type: ignore
    ImageTk = None  # type: ignore

from app.config_loader import get_logs_dir
from app.database import Database
from app.http_status import get_local_ip


def export_csv(db: Database, logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = logs_dir / f"export_{ts}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["id", "ts", "event_type", "distance_km", "energy",
                "relevant", "block_id", "temp_c", "humidity_pct"]
        )
        for row in db.all_events():
            writer.writerow(
                [
                    row["id"],
                    row["ts"],
                    row["event_type"],
                    row["distance_km"],
                    row["energy"],
                    row["relevant"],
                    row["block_id"],
                    row["temp_c"],
                    row["humidity_pct"],
                ]
            )
    return path


def open_export_dialog(parent: tk.Tk, db: Database, config: dict, http_port: int) -> None:
    win = tk.Toplevel(parent)
    win.title("Export")
    win.configure(bg="#16213e")
    win.geometry("420x480")

    logs_dir = get_logs_dir(config)
    status_url = f"http://{get_local_ip()}:{http_port}/status"

    frame = tk.Frame(win, bg="#16213e", padx=16, pady=16)
    frame.pack(fill=tk.BOTH, expand=True)

    path_var = tk.StringVar(value=str(logs_dir))

    def do_export() -> None:
        try:
            out = export_csv(db, logs_dir)
            path_var.set(str(out))
            messagebox.showinfo("Export", f"Gespeichert:\n{out}")
        except OSError as exc:
            messagebox.showerror("Export", str(exc))

    tk.Label(frame, text="CSV nach logs/ exportieren", fg="#eee",
             bg="#16213e", font=("Segoe UI", 12)).pack(anchor=tk.W)
    ttk.Button(frame, text="Export starten",
               command=do_export).pack(anchor=tk.W, pady=8)
    tk.Label(frame, textvariable=path_var, fg="#aaa", bg="#16213e",
             font=("Consolas", 9), wraplength=380).pack(anchor=tk.W)

    tk.Label(frame, text=f"\nStatus-URL:\n{status_url}", fg="#eee",
             bg="#16213e", font=("Consolas", 10)).pack(anchor=tk.W, pady=8)

    if qrcode is not None and ImageTk is not None:
        qr = qrcode.make(status_url)
        img = ImageTk.PhotoImage(qr.resize((200, 200)))
        lbl = tk.Label(frame, image=img, bg="#16213e")
        lbl.image = img  # keep reference
        lbl.pack(pady=8)
    else:
        tk.Label(frame, text="QR: qrcode/Pillow nicht installiert",
                 fg="#888", bg="#16213e").pack()

    ttk.Button(frame, text="Schließen", command=win.destroy).pack(pady=8)
