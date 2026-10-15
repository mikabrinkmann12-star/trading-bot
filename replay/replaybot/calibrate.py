"""Einmalige Kalibrierung: Bereiche und Buttons auf einem Bildschirmfoto markieren.

Bedienung im Vollbild:
  Rechteck-Schritt: mit gedrückter linker Maustaste ziehen
  Punkt-Schritt:    einmal klicken
  Enter = Schritt bestätigen,  nochmal ziehen/klicken = neu,  Esc = abbrechen (nichts speichern)
"""
from __future__ import annotations

import base64
import time

from . import config

STEPS = [
    ("rect", "legende",
     "Schritt 1/4: Ziehe ein Rechteck um die OHLC-Legende oben links (O... H... L... C...).\n"
     "Etwas Rand lassen, aber nichts anderes mit einschließen. Dann Enter."),
    ("rect", "chart",
     "Schritt 2/4: Ziehe ein Rechteck um den ganzen Kerzen-Bereich des Charts.\n"
     "(Ist die Maus dort, liest der Bot nicht - die Legende zeigt sonst die Kerze unter der Maus.) Enter."),
    ("point", "naechste_kerze",
     "Schritt 3/4: Klicke auf den Replay-Button VORWÄRTS  ▷|  (eine Kerze weiter).\n"
     "NICHT auf Play ▷ - Play spielt ab und überspringt Kerzen. Dann Enter."),
    ("rect", "preisachse",
     "Schritt 4/4: Ziehe ein Rechteck um die PREISACHSE rechts (die Zahlen-Spalte),\n"
     "von ganz oben bis ganz unten. Nur nötig zum Zoomen beim Einzeichnen - "
     "Enter ohne Rechteck = überspringen."),
]
OPTIONAL = {"preisachse"}


class Overlay:
    def __init__(self, shot_png: bytes, mon: dict, steps):
        import tkinter as tk
        self.tk = tk
        self.mon = mon
        self.steps = steps
        self.idx = 0
        self.result: dict = {}
        self.aborted = False
        self.start = None
        self.current = None  # (x1,y1,x2,y2) oder (x,y)

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
        self.root.attributes("-topmost", True)
        self.cv = tk.Canvas(self.root, width=mon["width"], height=mon["height"],
                            highlightthickness=0, cursor="crosshair")
        self.cv.pack()
        self.img = tk.PhotoImage(data=base64.b64encode(shot_png))
        self.cv.create_image(0, 0, anchor="nw", image=self.img)
        self.banner_bg = self.cv.create_rectangle(0, 0, 0, 0, fill="#202020", outline="#ffcc00")
        self.banner = self.cv.create_text(20, 20, anchor="nw", fill="white",
                                          font=("Segoe UI", 14, "bold"), text="")
        self.mark = None

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<Return>", self.on_enter)
        self.root.bind("<Escape>", self.on_escape)
        self.root.after(100, self.root.focus_force)
        self.show_step()

    def show_step(self):
        kind, key, text = self.steps[self.idx]
        self.cv.itemconfigure(self.banner, text=text)
        x1, y1, x2, y2 = self.cv.bbox(self.banner)
        self.cv.coords(self.banner_bg, x1 - 10, y1 - 10, x2 + 10, y2 + 10)
        self.cv.tag_raise(self.banner_bg)
        self.cv.tag_raise(self.banner)
        self.current = None
        if self.mark:
            self.cv.delete(self.mark)
            self.mark = None

    def on_press(self, ev):
        kind = self.steps[self.idx][0]
        if self.mark:
            self.cv.delete(self.mark)
        if kind == "point":
            r = 8
            self.mark = self.cv.create_oval(ev.x - r, ev.y - r, ev.x + r, ev.y + r,
                                            outline="red", width=3)
            self.current = (ev.x, ev.y)
        else:
            self.start = (ev.x, ev.y)
            self.mark = self.cv.create_rectangle(ev.x, ev.y, ev.x, ev.y, outline="red", width=2)
            self.current = None

    def on_drag(self, ev):
        if self.steps[self.idx][0] != "rect" or not self.start:
            return
        x0, y0 = self.start
        self.cv.coords(self.mark, x0, y0, ev.x, ev.y)
        self.current = (min(x0, ev.x), min(y0, ev.y), max(x0, ev.x), max(y0, ev.y))

    def on_enter(self, _ev=None):
        kind, key, _ = self.steps[self.idx]
        if self.current is None:
            if key not in OPTIONAL:
                return
            self.idx += 1                       # optionalen Schritt überspringen
            if self.idx >= len(self.steps):
                self.root.destroy()
            else:
                self.show_step()
            return
        ox, oy = self.mon["left"], self.mon["top"]
        if kind == "point":
            x, y = self.current
            self.result[key] = [x + ox, y + oy]
        else:
            x1, y1, x2, y2 = self.current
            if x2 - x1 < 10 or y2 - y1 < 5:
                return
            self.result[key] = [x1 + ox, y1 + oy, x2 - x1, y2 - y1]
        self.idx += 1
        if self.idx >= len(self.steps):
            self.root.destroy()
        else:
            self.show_step()

    def on_escape(self, _ev=None):
        self.aborted = True
        self.root.destroy()

    def run(self) -> dict | None:
        self.root.mainloop()
        return None if self.aborted else self.result


def screenshot_all():
    import cv2
    import mss
    import numpy as np
    with (mss.MSS() if hasattr(mss, "MSS") else mss.mss()) as sct:   # neu: MSS, alt: mss
        mon = dict(sct.monitors[0])  # alle Bildschirme zusammen
        shot = np.array(sct.grab(mon))[:, :, :3]
    ok, png = cv2.imencode(".png", shot)
    return png.tobytes(), mon


def run(cfg_path: str = "config.json", steps=STEPS, countdown: int = 5) -> bool:
    from .ocr import grab, read_ohlc, setup_tesseract

    cfg = config.load(cfg_path)
    print("Kalibrierung: Klick JETZT auf TradingView, damit es vorne ist "
          "(Replay aktiv, Fenster so wie beim Training).")
    for i in range(countdown, 0, -1):
        print(f"  Bildschirmfoto in {i} ...", flush=True)
        time.sleep(1)
    png, mon = screenshot_all()
    result = Overlay(png, mon, steps).run()
    if result is None:
        print("Abgebrochen - nichts gespeichert.")
        return False
    cfg.update(result)
    cfg["bildschirm"] = [mon["left"], mon["top"], mon["width"], mon["height"]]
    config.save(cfg, cfg_path)
    print(f"Gespeichert in {cfg_path}.")

    if "naechste_kerze" in result:
        from . import winutil
        x, y = result["naechste_kerze"]
        title, exe = winutil.window_title_at(x, y), winutil.window_exe_at(x, y)
        ok = "tradingview" in (title + exe).lower()
        print(f"\nFenster am 'Nächste Kerze'-Button: Titel '{title}', Programm '{exe}'")
        print("  -> Bot darf dort klicken." if ok else
              "  -> ACHTUNG: kein TradingView-Fenster erkannt - --auto wird dort NICHT klicken.")

    if "legende" in result:
        setup_tesseract(cfg.get("tesseract"))
        try:
            vals, text = read_ohlc(grab(cfg["legende"]))
        except Exception as exc:  # meist: Tesseract nicht installiert/gefunden
            print(f"\nTest-OCR nicht möglich: {exc}")
            print("Ist Tesseract installiert? Pfad steht in config.json unter 'tesseract'.")
            return True
        if vals:
            o, h, l, c = vals
            print(f"\nTest-OCR: O {o:.2f}  H {h:.2f}  L {l:.2f}  C {c:.2f}")
            print("Vergleiche mit der Legende im Chart. Stimmt es nicht: nochmal kalibrieren "
                  "und das Rechteck enger/weiter ziehen.")
        else:
            print(f"\nTest-OCR fehlgeschlagen. Tesseract las: {text!r}")
            print("Rechteck neu ziehen (nur die Legende, etwas Rand) oder Tesseract-Pfad in "
                  "config.json prüfen.")
    return True
