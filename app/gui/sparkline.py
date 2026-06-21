"""Mini sparkline canvas widget."""

from __future__ import annotations

import tkinter as tk


class Sparkline(tk.Canvas):
    def __init__(self, master, width: int = 600, height: int = 80, **kwargs) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            bg="#1a1a2e",
            highlightthickness=0,
            **kwargs,
        )
        self._values: list[float] = []
        self.bind("<Configure>", lambda e: self._draw())

    def set_values(self, values: list[float]) -> None:
        self._values = values[:]
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w = self.winfo_width() or int(self["width"])
        h = self.winfo_height() or int(self["height"])
        if not self._values:
            self.create_text(w // 2, h // 2, text="Keine Daten",
                             fill="#666", font=("Segoe UI", 12))
            return
        pad = 8
        max_v = max(self._values) if self._values else 1
        min_v = min(self._values) if self._values else 0
        span = max(max_v - min_v, 1)
        n = len(self._values)
        step = (w - 2 * pad) / max(n - 1, 1)
        points = []
        for i, v in enumerate(self._values):
            x = pad + i * step
            y = h - pad - ((v - min_v) / span) * (h - 2 * pad)
            points.extend([x, y])
        if len(points) >= 4:
            self.create_line(*points, fill="#4fc3f7", width=2, smooth=True)
        for i in range(0, len(points), 2):
            self.create_oval(points[i] - 2, points[i + 1] - 2, points[i] +
                             2, points[i + 1] + 2, fill="#4fc3f7", outline="")
