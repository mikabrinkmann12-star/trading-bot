"""Live-Modus: Legende vom Bildschirm lesen, Kerze für Kerze an die Engine geben.

Phase 2: Du klickst selbst auf 'Nächste Kerze', der Bot liest automatisch mit.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from typing import Callable

from . import config
from .journal import Journal
from .legend import check_plausible
from .models import Candle, m2t, t2m
from .strategy import EXIT_TIME, StrategyEngine

STATUS, CANDLE, DONE, ERROR = "status", "candle", "done", "error"


class LiveReader:
    """Eine Abfrage pro step(). Bildschirm/Maus kommen als Funktionen rein (testbar)."""

    def __init__(self, engine: StrategyEngine, journal: Journal, *,
                 read_fn: Callable[[], tuple], post: Callable[[str, object], None],
                 mouse_fn: Callable[[], tuple[int, int] | None] = lambda: None,
                 chart_rect=None, start: str = "09:00", retries: int = 3,
                 max_open_gap: float = 25.0, stable: int = 2,
                 save_img: Callable[[object], str] | None = None):
        self.engine = engine
        self.journal = journal
        self.read_fn = read_fn
        self.post = post
        self.mouse_fn = mouse_fn
        self.chart_rect = chart_rect
        self.minute = t2m(start)
        self.retries = retries
        self.max_open_gap = max_open_gap
        self.stable = stable
        self.save_img = save_img
        self.last_vals: tuple | None = None
        self.pending: tuple | None = None
        self.pending_count = 0
        self.fails = 0
        self.finished = False

    @property
    def next_time(self) -> str:
        return m2t(self.minute)

    def step(self) -> bool:
        """Liest einmal. Gibt False zurück, wenn der Lauf zu Ende ist (fertig oder Fehler)."""
        if self.finished:
            return False
        pos = self.mouse_fn()
        if pos and config.in_rect(pos[0], pos[1], self.chart_rect):
            self.post(STATUS, ("Maus aus dem Chart nehmen - die Legende zeigt sonst die Kerze "
                               "unter der Maus.", "warn"))
            return True

        vals, text, img = self.read_fn()
        prev_close = self.last_vals[3] if self.last_vals else None
        problem = None
        if vals is None:
            problem = f"Legende nicht lesbar (OCR: {text!r})"
        else:
            problem = check_plausible(*vals, prev_close=prev_close)
        if problem:
            self.fails += 1
            if self.fails > self.retries:
                where = self.save_img(img) if (self.save_img and img is not None) else "-"
                self._stop_error(f"{problem}. {self.fails}x hintereinander - gestoppt. "
                                 f"Bild: {where}")
                return False
            self.post(STATUS, (f"Lesefehler {self.fails}/{self.retries + 1}: {problem}", "warn"))
            return True
        self.fails = 0

        if vals == self.last_vals:
            self.pending, self.pending_count = None, 0
            self.post(STATUS, (f"Warte auf Kerze {self.next_time} ...", "info"))
            return True
        if vals != self.pending:          # erst übernehmen, wenn 'stable'-mal gleich gelesen
            self.pending, self.pending_count = vals, 1
        else:
            self.pending_count += 1
        if self.pending_count < self.stable:
            return True

        self.pending, self.pending_count = None, 0
        return self._accept(vals)

    def _accept(self, vals) -> bool:
        candle = Candle(self.next_time, *vals)
        if self.last_vals and abs(candle.o - self.last_vals[3]) > self.max_open_gap:
            self.post(STATUS, (f"Achtung {candle.time}: Open {candle.o:.2f} weit weg vom letzten "
                               f"Close {self.last_vals[3]:.2f} - Kerze übersprungen?", "warn"))
        self.journal.log_candle(self.engine.date, candle, "ocr")
        try:
            rep = self.engine.on_candle(candle)
        except ValueError as exc:
            self._stop_error(str(exc))
            return False
        self.last_vals = vals
        self.minute += 5
        self.post(CANDLE, (self.engine.snapshot(), rep.events))
        if self.engine.done or candle.minute >= EXIT_TIME:
            self.engine.end_of_data()
            self.journal.write_trade(self.engine.trade_row())
            self.finished = True
            self.post(DONE, self.engine.snapshot())
            return False
        return True

    def _stop_error(self, text: str):
        self.finished = True
        self.journal.log_action(f"FEHLER: {text}")
        self.post(ERROR, text)

    def run(self, stop: threading.Event, poll: float = 0.5):
        while not stop.is_set():
            try:
                if not self.step():
                    return
            except Exception as exc:  # unerwartet -> sichtbar machen statt still sterben
                self._stop_error(f"Unerwarteter Fehler: {exc!r}")
                return
            time.sleep(poll)


def install_f12(journal: Journal):
    try:
        import keyboard
    except ImportError:
        print("WARNUNG: Paket 'keyboard' fehlt - F12 funktioniert nicht. "
              "pip install -r requirements.txt")
        return

    def kill():
        journal.log_action("F12 gedrückt - sofortiger Abbruch")
        os._exit(1)

    keyboard.add_hotkey("f12", kill)


def run_live(date: str, start: str, out_dir: str, cfg_path: str = "config.json") -> int:
    from . import ocr, winutil
    from .window import StatusWindow

    cfg = config.load(cfg_path)
    if not cfg.get("legende"):
        print("Noch nicht kalibriert. Zuerst: python bot.py --kalibrieren")
        return 1
    ocr.setup_tesseract(cfg.get("tesseract"))
    journal = Journal(out_dir)
    journal.log_action(f"Start live: Datum {date}, Startkerze {start}")
    install_f12(journal)

    engine = StrategyEngine(date)
    q: queue.Queue = queue.Queue()
    stop = threading.Event()

    def read_fn():
        img = ocr.grab(cfg["legende"])
        vals, text = ocr.read_ohlc(img)
        return vals, text, img

    reader = LiveReader(
        engine, journal, read_fn=read_fn, post=lambda k, p: q.put((k, p)),
        mouse_fn=winutil.mouse_pos, chart_rect=cfg.get("chart"), start=start,
        max_open_gap=float(cfg.get("max_open_luecke", 25.0)),
        save_img=lambda img: str(ocr.save_debug(img, journal.out / "logs", "fehler")))

    win = StatusWindow(cfg, on_stop=stop.set)
    win.show(engine.snapshot())
    win.set_status(f"Lese Legende ... Replay muss auf {start} stehen. Maus nicht über den Chart.")

    def pump():
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == STATUS:
                    win.set_status(*payload)
                elif kind == CANDLE:
                    snap, events = payload
                    win.show(snap)
                    win.set_status(events[-1] if events else f"Kerze {snap['values'][1][1]} gelesen.")
                    for ev in events:
                        print(ev)
                elif kind == DONE:
                    win.show(payload)
                    win.set_status(f"Fertig. Ergebnis gespeichert in {journal.trades}", "ok")
                    print(f"Fertig: {payload['reason']}")
                elif kind == ERROR:
                    win.set_status(payload, "error")
                    print(f"FEHLER: {payload}")
        except queue.Empty:
            pass
        win.after(100, pump)

    threading.Thread(target=reader.run, args=(stop,), daemon=True).start()
    win.after(100, pump)
    win.mainloop()
    stop.set()
    config.save(cfg, cfg_path)  # Fensterposition merken
    journal.log_action("Ende live")
    return 0
