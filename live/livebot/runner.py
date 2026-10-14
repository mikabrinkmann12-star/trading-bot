"""Der Live-Lauf: Legende lesen, Kerzen abschließen, Strategie rechnen, Trade verwalten."""
from __future__ import annotations

import os
import queue
import threading
import time
from typing import Callable

from . import config
from .journal import Journal
from .legend import check_plausible
from .livefeed import LiveFeed, read_closed_exact
from .livetrade import ARMED, IN_TRADE, TradeManager
from .models import Candle, m2t
from .nyclock import now_ny, sec_of_day
from .strategy import StrategyEngine

STATUS, CANDLE, DONE, ERROR = "status", "candle", "done", "error"
DAY_END = 16 * 3600


class LiveRunner:
    """Ein Durchgang pro step(now). Bildschirm-Zugriffe kommen als Funktionen rein (testbar)."""

    def __init__(self, engine: StrategyEngine, manager: TradeManager, journal: Journal, *,
                 date: str, read_fn: Callable[[], tuple], post: Callable[[str, object], None],
                 actions=None, exact_fn: Callable[[tuple], tuple | None] | None = None,
                 feed: LiveFeed | None = None):
        self.engine, self.manager, self.journal = engine, manager, journal
        self.date, self.read_fn, self.post = date, read_fn, post
        self.actions, self.exact_fn = actions, exact_fn
        self.feed = feed or LiveFeed()
        self.fails = 0
        self.finished = False

    def step(self, now) -> bool:
        if self.finished:
            return False
        sec = sec_of_day(now)
        vals, text, _img = self.read_fn()
        last_c = self.actions.last_closed[3] if self.actions and self.actions.last_closed else None
        if vals is not None and check_plausible(*vals, prev_close=last_c):
            vals = None                                   # unplausibel -> wie unlesbar
        if vals is None:
            self.fails += 1
            if self.fails in (10, 60) or self.fails % 300 == 0:
                self.post(STATUS, (f"Legende {self.fails}x nicht lesbar (OCR: {text!r}). "
                                   f"Maus aus dem Chart? Chart sichtbar?", "warn"))
        else:
            self.fails = 0
        closed, fresh = self.feed.on_reading(now, vals)
        for minute, approx in closed:
            self._close_bar(minute, approx)
        if fresh is not None and self.manager.state in (ARMED, IN_TRADE):
            self.manager.on_tick(sec, fresh)
        self.manager.on_time(sec, fresh[3] if fresh else None)
        if not self.manager.done and sec >= DAY_END and self.manager.state != IN_TRADE:
            self.manager._finish(self.manager.result or "Tagesende", None, None,
                                 "16:00 NY - Tag beendet.")
        if self.manager.done:
            self.journal.write_trade(self.manager.row(self.date))
            self.finished = True
            self.post(DONE, self.manager.snapshot(self.engine.snapshot()))
            return False
        if fresh is not None and not closed:
            self.post(STATUS, (f"{now:%H:%M:%S} NY  Kerze {m2t(int(sec // 300) * 5)}: "
                               f"Kurs {fresh[3]:.2f}  ({self.manager.state})", "info"))
        return True

    def _close_bar(self, minute: int, approx: tuple):
        exact = None
        if self.exact_fn is not None and minute >= 9 * 60:
            try:
                exact = self.exact_fn(approx)
            except Exception as exc:
                self.journal.log_action(f"Genaues Lesen {m2t(minute)} fehlgeschlagen: {exc}")
        vals = exact or approx
        if exact is None and minute >= 9 * 60:
            self.journal.log_action(f"Kerze {m2t(minute)} nur genähert (letzte Lesung): {vals}")
        candle = Candle(m2t(minute), *vals)
        self.journal.log_candle(self.date, candle, "live" if exact else "live~")
        try:
            rep = self.engine.on_candle(candle)
        except ValueError as exc:
            self.post(STATUS, (f"Kerze {candle.time} übersprungen: {exc}", "warn"))
            return
        if self.actions is not None:
            self.actions.prev_closed, self.actions.last_closed = self.actions.last_closed, vals
        self.manager.on_bar_closed()
        self.post(CANDLE, (self.manager.snapshot(self.engine.snapshot()), rep.events))

    def run(self, stop: threading.Event, clock: Callable = now_ny, poll: float = 0.5):
        while not stop.is_set():
            try:
                if not self.step(clock()):
                    return
            except Exception as exc:
                self.finished = True
                self.journal.log_action(f"FEHLER: {exc!r}")
                self.post(ERROR, f"Unerwarteter Fehler: {exc!r}")
                return
            time.sleep(poll)


def install_f12(journal: Journal):
    try:
        import keyboard
    except ImportError:
        print("WARNUNG: Paket 'keyboard' fehlt - F12 funktioniert nicht.")
        return

    def kill():
        journal.log_action("F12 gedrückt - sofortiger Abbruch")
        os._exit(1)

    keyboard.add_hotkey("f12", kill)


def run_live(out_dir: str, cfg_path: str = "config.json", orders: bool = True,
             clock: Callable = now_ny, sim_factor: float = 1.0) -> int:
    from . import ocr
    from .account import PaperLock
    from .draw import Drawer
    from .orders import LiveActions
    from .painter import make_painter
    from .safety import Guard
    from .window import StatusWindow

    cfg = config.load(cfg_path)
    missing = [k for k in ("legende", "chart", "preisachse", "konto", "parkplatz") if not cfg.get(k)]
    if missing:
        print("Noch nicht (vollständig) kalibriert, es fehlt: " + ", ".join(missing))
        print("Zuerst: python live.py --kalibrieren")
        return 1
    abl = cfg.get("ablaeufe") or {}
    need = ["kaufen", "verkaufen", "breakeven", "schliessen"] if orders else []
    if [n for n in need if not abl.get(n)]:
        print("Diese Abläufe fehlen noch: " + ", ".join(n for n in need if not abl.get(n)))
        print("Vormachen mit: python live.py --aufnehmen NAME   (oder erst --ohne-orders testen)")
        return 1
    ocr.setup_tesseract(cfg.get("tesseract"))
    date = clock().strftime("%Y-%m-%d")
    journal = Journal(out_dir)
    journal.log_action(f"Start LIVE {date}, Orders {'AN' if orders else 'AUS (--ohne-orders)'}")
    print("WICHTIG: In TradingView muss 'Ein-Klick-Handel' AUS sein und das PAPER-Konto aktiv.")
    print("Orders: " + ("AN (nur Paper-Konto)" if orders else "AUS - nur beobachten/einzeichnen"))

    q: queue.Queue = queue.Queue()
    stop = threading.Event()
    guard = Guard(cfg, journal, stop_event=stop)
    install_f12(journal)
    post_status = lambda t, lvl: q.put((STATUS, (t, lvl)))   # noqa: E731

    def set_window_visible(visible: bool):
        done = threading.Event()
        q.put(("fenster", (visible, done)))
        done.wait(2.0)
        time.sleep(0.3)

    def hidden(fn):
        set_window_visible(False)
        try:
            fn()
        finally:
            set_window_visible(True)

    ui = {"fenster": None}
    painter = make_painter(cfg, guard, post_status, exclude_fn=lambda: [ui["fenster"]])
    actions = LiveActions(cfg, Drawer(cfg, guard, post=lambda t: post_status(t, "info")),
                          PaperLock(cfg, journal), painter=painter, enabled=orders,
                          post=post_status, around=hidden)
    engine = StrategyEngine(date)
    manager = TradeManager(engine, actions, post=post_status)

    def read_fn():
        img = ocr.grab(cfg["legende"])
        vals, text = ocr.read_ohlc(img)
        return vals, text, img

    def exact_fn(approx):
        try:
            return read_closed_exact(
                cfg, approx, grab=ocr.grab, read_ohlc=ocr.read_ohlc,
                move=lambda x, y: guard.move_to(x, y, "Kerze genau lesen (Hover)"),
                sleep=time.sleep, exclude=[ui["fenster"]])
        finally:
            guard.move_to(*cfg["parkplatz"], "Maus parken")

    runner = LiveRunner(engine, manager, journal, date=date, read_fn=read_fn,
                        post=lambda k, p: q.put((k, p)), actions=actions,
                        exact_fn=exact_fn if cfg.get("genau_lesen", True) else None)

    win = StatusWindow(cfg, on_stop=stop.set)
    win.show(manager.snapshot(engine.snapshot()))
    win.set_status("LIVE: Maus NICHT anfassen. F12 = sofort stoppen. Warte auf Kerzen ab 9:00 NY.",
                   "warn")

    def pump():
        ui["fenster"] = win.rect()
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == STATUS:
                    win.set_status(*payload)
                elif kind == "fenster":
                    visible, done = payload
                    win.set_visible(visible)
                    done.set()
                elif kind == CANDLE:
                    snap, events = payload
                    win.show(snap)
                    for ev in events:
                        print(ev)
                elif kind == DONE:
                    win.show(payload)
                    win.set_status(f"Fertig: {manager.reason} Gespeichert in {journal.trades}.",
                                   "ok")
                    print(f"Fertig: {manager.result} - {manager.reason}")
                elif kind == ERROR:
                    win.set_status(payload, "error")
                    print(f"FEHLER: {payload}")
        except queue.Empty:
            pass
        win.after(100, pump)

    guard.move_to(*cfg["parkplatz"], "Maus parken (Start)")
    threading.Thread(target=runner.run, args=(stop, clock, 0.5 / sim_factor),
                     daemon=True).start()
    win.after(100, pump)
    win.mainloop()
    stop.set()
    config.save(cfg, cfg_path)
    journal.log_action("Ende live")
    return 0


def run_draw_test(direction: str, out_dir: str, cfg_path: str = "config.json") -> int:
    """Eine Beispiel-Box um den aktuellen Kurs einzeichnen (an der aufgenommenen Stelle)."""
    from . import ocr
    from .painter import make_painter
    from .safety import Guard

    cfg = config.load(cfg_path)
    if not cfg.get("legende") or not (cfg.get("ablaeufe") or {}).get(direction):
        print(f"Erst kalibrieren und '--aufnehmen {direction}' machen.")
        return 1
    ocr.setup_tesseract(cfg.get("tesseract"))
    journal = Journal(out_dir)
    install_f12(journal)
    vals, text = ocr.read_ohlc(ocr.grab(cfg["legende"]))
    if vals is None:
        print(f"Legende nicht lesbar ({text!r}) - Maus aus dem Chart nehmen.")
        return 1
    entry = vals[3]
    stop, target = (entry - 20, entry + 40) if direction == "long" else (entry + 20, entry - 40)
    print(f"Test: {direction} Entry {entry:.2f}, Stop {stop:.2f}, Ziel {target:.2f} - "
          f"in 3 Sekunden, Maus nicht anfassen.")
    time.sleep(3)
    try:
        make_painter(cfg, Guard(cfg, journal), lambda t, l: print(f"  {t}"))(
            direction, entry, stop, target)
    except Exception as exc:
        print(f"FEHLER: {exc}")
        return 1
    print("Fertig.")
    return 0
