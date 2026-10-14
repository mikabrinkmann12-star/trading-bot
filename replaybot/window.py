"""Kleines Statusfenster (immer im Vordergrund), standardmäßig unten rechts."""
from __future__ import annotations

from typing import Callable

COLORS = {"info": "#555555", "ok": "#1a7f37", "warn": "#b35900", "error": "#c62828"}


class StatusWindow:
    WIDTH = 360

    def __init__(self, cfg: dict, on_stop: Callable[[], None]):
        import tkinter as tk
        self.tk = tk
        self.cfg = cfg
        self.on_stop = on_stop
        self.root = tk.Tk()
        self.root.title("Replay-Bot")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        pad = {"padx": 8, "pady": 1}
        self.head = tk.Label(self.root, text="Schritt -", font=("Segoe UI", 13, "bold"),
                             anchor="w")
        self.head.grid(row=0, column=0, columnspan=2, sticky="we", padx=8, pady=(8, 4))

        self.value_labels: dict[str, object] = {}
        self.names = ["Datum", "Kerze", "Richtung", "Swing-Hoch", "Swing-Tief", "BOS", "Leg",
                      "Entry", "Stop", "Ziel", "Risiko", "Gefüllt", "Ergebnis", "R"]
        for i, name in enumerate(self.names, start=1):
            tk.Label(self.root, text=name, font=("Segoe UI", 9), fg="#666666",
                     anchor="w").grid(row=i, column=0, sticky="w", **pad)
            lbl = tk.Label(self.root, text="-", font=("Consolas", 10, "bold"), anchor="w")
            lbl.grid(row=i, column=1, sticky="w", **pad)
            self.value_labels[name] = lbl

        n = len(self.names) + 1
        self.reason = tk.Label(self.root, text="", wraplength=self.WIDTH - 20, justify="left",
                               font=("Segoe UI", 10), anchor="w")
        self.reason.grid(row=n, column=0, columnspan=2, sticky="we", padx=8, pady=(6, 2))
        self.status = tk.Label(self.root, text="", wraplength=self.WIDTH - 20, justify="left",
                               font=("Segoe UI", 9), anchor="w", fg=COLORS["info"])
        self.status.grid(row=n + 1, column=0, columnspan=2, sticky="we", padx=8, pady=2)
        tk.Button(self.root, text="Stop (F12)", command=self.close).grid(
            row=n + 2, column=0, columnspan=2, sticky="we", padx=8, pady=(4, 8))
        self.root.columnconfigure(1, minsize=self.WIDTH - 110)
        self._place()

    def _place(self):
        self.root.update_idletasks()
        pos = self.cfg.get("fenster")
        if pos:
            x, y = pos
        else:
            w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
            x = self.root.winfo_screenwidth() - w - 20
            y = self.root.winfo_screenheight() - h - 80
        self.root.geometry(f"+{x}+{y}")

    def show(self, snap: dict):
        self.head.config(text=f"Schritt {snap['step']}: {snap['step_name']}")
        for name, value in snap["values"]:
            if name in self.value_labels:
                self.value_labels[name].config(text=value)
        self.reason.config(text=snap["reason"])

    def set_status(self, text: str, level: str = "info"):
        self.status.config(text=text, fg=COLORS.get(level, COLORS["info"]))

    def after(self, ms: int, fn):
        self.root.after(ms, fn)

    def close(self):
        try:
            self.cfg["fenster"] = [self.root.winfo_x(), self.root.winfo_y()]
        except Exception:
            pass
        self.on_stop()
        self.root.destroy()

    def mainloop(self):
        self.root.mainloop()
