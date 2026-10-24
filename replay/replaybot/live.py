"""Live-Modus: Legende vom Bildschirm lesen, Kerze für Kerze an die Engine geben.

Ohne --auto: Du klickst selbst auf 'Nächste Kerze', der Bot liest automatisch mit.
Mit --auto:  Der Bot klickt selbst und wartet nach jedem Klick auf genau eine neue Kerze.
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
                 save_img: Callable[[object], str] | None = None,
                 clicker: Callable[[], None] | None = None, click_timeout: float | None = None,
                 click_pause: float = 2.0,
                 on_fill: Callable[[StrategyEngine], None] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 safe_point: tuple[int, int] | None = None):
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
        self.seen: set[tuple] = set()       # alle schon übernommenen Kerzen
        self.clicker = clicker
        self.click_timeout = click_timeout
        self.click_pause = click_pause
        self.on_fill = on_fill
        self.clock = clock
        self.clicked_at: float | None = None
        self.safe_point = safe_point        # 'Nächste Kerze'-Button: Maus dort ist ok

    @property
    def next_time(self) -> str:
        return m2t(self.minute)

    def step(self) -> bool:
        """Liest einmal. Gibt False zurück, wenn der Lauf zu Ende ist (fertig oder Fehler)."""
        if self.finished:
            return False
        if self.clicked_at is not None and self.clock() - self.clicked_at < self.click_pause:
            return True                   # nach jedem Klick erst Pause, TradingView braucht Zeit
        pos = self.mouse_fn()
        at_button = (pos and self.safe_point and abs(pos[0] - self.safe_point[0]) <= 15
                     and abs(pos[1] - self.safe_point[1]) <= 15)
        if pos and not at_button and config.in_rect(pos[0], pos[1], self.chart_rect):
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
            waited = self.clock() - self.clicked_at if self.clicked_at is not None else 0.0
            if self.click_timeout and waited > self.click_timeout:
                self._stop_error(f"Nach dem Klick auf 'Nächste Kerze' kam {self.click_timeout:.0f} s "
                                 f"lang keine neue Kerze. Replay am Ende oder Button "
                                 f"verdeckt? Neu kalibrieren, falls sich das Layout geändert hat.")
                return False
            extra = f" (seit {waited:.0f} s)" if waited >= 3 else ""
            self.post(STATUS, (f"Warte auf Kerze {self.next_time} ...{extra}", "info"))
            return True
        if vals in self.seen:
            self.pending, self.pending_count = None, 0
            self.post(STATUS, ("Legende zeigt eine ältere Kerze - Maus über dem Chart? "
                               "Wird ignoriert.", "warn"))
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
            self._stop_error(
                f"Kerze {candle.time}: Open {candle.o:.2f} passt nicht zum letzten Close "
                f"{self.last_vals[3]:.2f} ({abs(candle.o - self.last_vals[3]):.2f} Punkte). "
                f"Entweder wurde eine Kerze übersprungen oder die Maus war über dem Chart - "
                f"dann stimmt die Uhrzeit nicht mehr. Replay zurück auf 9:00 und neu starten.")
            return False
        self.journal.log_candle(self.engine.date, candle, "ocr")
        try:
            rep = self.engine.on_candle(candle)
        except ValueError as exc:
            self._stop_error(str(exc))
            return False
        self.last_vals = vals
        self.seen.add(vals)
        self.minute += 5
        self.post(CANDLE, (self.engine.snapshot(), rep.events))
        if rep.filled and self.on_fill is not None:
            try:                          # Bot pausiert hier, bis fertig eingezeichnet ist
                self.on_fill(self.engine)
            except Exception as exc:
                if "gestoppt" in str(exc):
                    self._stop_error(str(exc))
                    return False
                # Zeichnen ist nur Anzeige - der Trade wird trotzdem zu Ende gerechnet
                self.journal.log_action(f"Einzeichnen fehlgeschlagen: {exc}")
                self.post(STATUS, (f"Einzeichnen fehlgeschlagen: {exc} - rechne den Trade "
                                   f"trotzdem zu Ende.", "error"))
        if self.engine.done or candle.minute >= EXIT_TIME:
            self.engine.end_of_data()
            self.saved_to = self.journal.write_trade(self.engine.trade_row())
            self.finished = True
            self.post(DONE, self.engine.snapshot())
            return False
        if self.clicker is not None:
            try:
                self.clicker()
            except Exception as exc:
                self._stop_error(f"Klick verweigert: {exc}")
                return False
            self.clicked_at = self.clock()
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


def make_painter(cfg: dict, guard, post: Callable[[str, str], None],
                 exclude_fn: Callable[[], list] = lambda: []):
    """Liefert paint(...): Position an der aktuellen Kerze einzeichnen + so zoomen,
    dass sie sichtbar ist."""
    from . import ocr
    from .candlefind import locate_current_candle
    from .chartnav import ChartNav
    from .draw import Drawer

    drawer = Drawer(cfg, guard, post=lambda t: post(t, "info"))
    nav = ChartNav(cfg, guard, post=lambda t: post(t, "info"))

    def paint(direction: str, entry: float, stop: float, target: float,
              current: tuple | None = None, previous: tuple | None = None):
        side = "Long" if direction == "long" else "Short"
        anchor = None
        if current is not None and cfg.get("chart"):
            post("Suche die aktuelle Kerze im Chart ...", "info")
            x, why = locate_current_candle(
                cfg, current, previous, grab=ocr.grab, read_ohlc=ocr.read_ohlc,
                move=lambda mx, my: guard.move_to(mx, my, "Kerze prüfen (Hover)"),
                sleep=time.sleep, exclude=exclude_fn())
            if x is None:
                # Lieber gar nicht zeichnen als an der falschen Stelle
                raise RuntimeError(f"Aktuelle Kerze nicht gefunden: {why}. Nichts gezeichnet.")
            anchor = (x, nav.price_to_y(entry))
            post(f"Aktuelle Kerze bei x={x} bestätigt.", "info")
        post(f"Zeichne {side}-Position (Entry {entry:.2f}) ...", "warn")
        drawer.draw(direction, entry, stop, target, anchor=anchor)
        if nav.ready():
            span = abs(target - stop)
            lo, hi = min(stop, target) - 0.1 * span, max(stop, target) + 0.1 * span
            if not nav.ensure_visible(lo, hi):
                post("Position evtl. nicht ganz sichtbar (Zoom hat nicht gereicht).", "warn")
            if cfg.get("naechste_kerze"):
                guard.move_to(*cfg["naechste_kerze"], "Maus aus dem Chart")
        else:
            post("Preisachse nicht kalibriert - kein Zoom.", "warn")

    return paint


def drawing_mode(cfg: dict, wanted: bool | None) -> tuple[bool | None, list[str], str]:
    """(an?, aufgenommene Richtungen, Info-Text). an? = None heißt: erzwungen, aber es fehlt was."""
    recorded = [d for d in ("long", "short") if (cfg.get("ablaeufe") or {}).get(d)]
    missing = [d for d in ("long", "short") if d not in recorded]
    if wanted and missing:
        return None, recorded, ("Einzeichnen ist noch nicht aufgenommen für: "
                                + ", ".join(missing) + "\nZuerst: "
                                + "  und  ".join(f"python bot.py --aufnehmen {d}" for d in missing))
    on = bool(recorded) if wanted is None else wanted
    if on:
        info = "Einzeichnen: AN (" + ", ".join(recorded) + " aufgenommen"
        info += f"; {', '.join(missing)} fehlt - wird übersprungen)" if missing else ")"
    elif recorded:
        info = "Einzeichnen: AUS (--ohne-zeichnen)"
    else:
        info = "Einzeichnen: AUS - noch nichts aufgenommen: python bot.py --aufnehmen long / short"
    return on, recorded, info


def run_live(date: str, start: str, out_dir: str, cfg_path: str = "config.json",
             auto: bool = False, zeichnen: bool | None = None) -> int:
    """zeichnen: True = erzwingen, False = aus, None = automatisch an, sobald aufgenommen."""
    from . import ocr, winutil
    from .safety import Guard
    from .window import StatusWindow

    cfg = config.load(cfg_path)
    if not cfg.get("legende"):
        print("Noch nicht kalibriert. Zuerst: python bot.py --kalibrieren")
        return 1
    ocr.setup_tesseract(cfg.get("tesseract"))
    journal = Journal(out_dir)
    journal.log_action(f"Start live: Datum {date}, Startkerze {start}, auto={auto}")
    if auto and not cfg.get("naechste_kerze"):
        print("'Nächste Kerze' ist nicht kalibriert. Zuerst: python bot.py --kalibrieren")
        return 1
    zeichnen, recorded, info = drawing_mode(cfg, zeichnen)
    print(info)
    if zeichnen is None:          # erzwungen, aber nicht vollständig aufgenommen
        return 1
    journal.log_action(info)
    engine = StrategyEngine(date, max_risk=float(cfg.get("max_risiko", 100)))
    q: queue.Queue = queue.Queue()
    stop = threading.Event()
    guard = Guard(cfg, journal, stop_event=stop)
    clicker = guard.click_next if auto else None
    install_f12(journal)

    def read_fn():
        img = ocr.grab(cfg["legende"])
        vals, text = ocr.read_ohlc(img)
        return vals, text, img

    ui = {"fenster": None}      # Rechteck des Bot-Fensters (beim Kerzensuchen ausblenden)
    drawn = {"ok": False, "grund": ""}

    def set_window_visible(visible: bool):
        """Aus dem Reader-Thread: Bot-Fenster aus-/einblenden und warten, bis es passiert ist
        (sonst verdeckt es evtl. die letzte Kerze oder Felder im Dialog)."""
        done = threading.Event()
        q.put(("fenster", (visible, done)))
        done.wait(2.0)
        time.sleep(0.3)
    on_fill = None
    if zeichnen:
        painter = make_painter(cfg, guard, lambda t, lvl: q.put((STATUS, (t, lvl))),
                               exclude_fn=lambda: [ui["fenster"]])

        def paint_fill(e: StrategyEngine):
            if e.direction not in recorded:
                drawn["grund"] = f"{e.direction} ist nicht aufgenommen"
                q.put((STATUS, (f"{e.direction}-Einzeichnen nicht aufgenommen - übersprungen "
                                f"(python bot.py --aufnehmen {e.direction}).", "warn")))
                return
            c = e.candles[-1]
            p = e.candles[-2] if len(e.candles) > 1 else None
            set_window_visible(False)
            try:
                painter(e.direction, e.entry, e.stop, e.target, current=(c.o, c.h, c.l, c.c),
                        previous=(p.o, p.h, p.l, p.c) if p else None)
            except Exception as exc:
                drawn["grund"] = f"das Einzeichnen fehlschlug ({exc})"
                raise
            finally:
                set_window_visible(True)
            drawn["ok"] = True
        on_fill = paint_fill

    reader = LiveReader(
        engine, journal, read_fn=read_fn, post=lambda k, p: q.put((k, p)),
        mouse_fn=winutil.mouse_pos, chart_rect=cfg.get("chart"), start=start,
        max_open_gap=float(cfg.get("max_open_luecke", 25.0)),
        save_img=lambda img: str(ocr.save_debug(img, journal.out / "logs", "fehler")),
        clicker=clicker, click_timeout=float(cfg.get("klick_timeout") or 0) or None,
        click_pause=float(cfg.get("klick_pause", 2.0)), on_fill=on_fill,
        safe_point=tuple(cfg["naechste_kerze"]) if cfg.get("naechste_kerze") else None)

    win = StatusWindow(cfg, on_stop=stop.set)
    win.show(engine.snapshot())
    if auto:
        win.set_status(f"AUTO: Bot klickt selbst. Replay muss auf {start} stehen und pausiert "
                       f"sein. Maus NICHT anfassen. F12 = sofort stoppen.", "warn")
    else:
        win.set_status(f"Lese Legende ... Replay muss auf {start} stehen. "
                       f"Maus nicht über den Chart.")

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
                    win.set_status(events[-1] if events else f"Kerze {snap['values'][1][1]} gelesen.")
                    for ev in events:
                        print(ev)
                elif kind == DONE:
                    win.show(payload)
                    saved = getattr(reader, "saved_to", None) or journal.trades
                    msg = f"Fertig. Ergebnis gespeichert in {saved}."
                    if zeichnen and not drawn["ok"]:
                        msg += (f" Nichts eingezeichnet, weil {drawn['grund']}." if drawn["grund"]
                                else f" Nichts eingezeichnet: {engine.reason}")
                    elif not zeichnen:
                        msg += " Einzeichnen war AUS."
                    win.set_status(msg, "ok")
                    print(f"Fertig: {payload['reason']}  {msg}")
                elif kind == ERROR:
                    win.set_status(payload, "error")
                    print(f"FEHLER: {payload}")
        except queue.Empty:
            pass
        win.after(100, pump)

    if auto:
        # Im Auto-Modus fasst du die Maus nicht an - also selbst aus dem Chart nehmen,
        # sonst zeigt die Legende evtl. die Kerze unter der Maus.
        guard.move_to(*cfg["naechste_kerze"], "Maus aus dem Chart (Start)")
    threading.Thread(target=reader.run, args=(stop,), daemon=True).start()
    win.after(100, pump)
    win.mainloop()
    stop.set()
    config.save(cfg, cfg_path)  # Fensterposition merken
    journal.log_action("Ende live")
    return 0


def run_draw_test(direction: str, out_dir: str, cfg_path: str = "config.json") -> int:
    """Einmal eine Box mit Beispielwerten um den aktuellen Kurs einzeichnen (ohne Replay-Lauf)."""
    from . import ocr
    from .safety import Guard

    cfg = config.load(cfg_path)
    if not cfg.get("legende"):
        print("Noch nicht kalibriert. Zuerst: python bot.py --kalibrieren")
        return 1
    if not (cfg.get("ablaeufe") or {}).get(direction):
        print(f"Noch nicht aufgenommen. Zuerst: python bot.py --aufnehmen {direction}")
        return 1
    ocr.setup_tesseract(cfg.get("tesseract"))
    journal = Journal(out_dir)
    install_f12(journal)
    vals, text = ocr.read_ohlc(ocr.grab(cfg["legende"]))
    if vals is None:
        print(f"Legende nicht lesbar ({text!r}) - Maus aus dem Chart nehmen und neu versuchen.")
        return 1
    entry = vals[3]
    if direction == "long":
        stop, target = entry - 20, entry + 40
    else:
        stop, target = entry + 20, entry - 40
    print(f"Test: {direction} Entry {entry:.2f}, Stop {stop:.2f}, Ziel {target:.2f}")
    print("In 3 Sekunden geht es los - Maus nicht anfassen. F12 = Abbruch.")
    time.sleep(3)
    journal.log_action(f"Zeichnen-Test {direction}")
    painter = make_painter(cfg, Guard(cfg, journal), lambda t, lvl: print(f"  {t}"))
    try:
        painter(direction, entry, stop, target, current=vals)
    except Exception as exc:
        print(f"FEHLER: {exc}")
        return 1
    print("Fertig. Prüfe im Chart: Box da? Entry/Stop/Ziel richtig? Alles sichtbar?")
    return 0
