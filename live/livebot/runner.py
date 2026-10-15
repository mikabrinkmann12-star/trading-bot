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
from .nyclock import now_ny, sec_of_day, start_problem
from .strategy import StrategyEngine

STATUS, CANDLE, DONE, ERROR = "status", "candle", "done", "error"
DAY_END = 16 * 3600


class LiveRunner:
    """Ein Durchgang pro step(now). Bildschirm-Zugriffe kommen als Funktionen rein (testbar)."""

    def __init__(self, engine: StrategyEngine, manager: TradeManager, journal: Journal, *,
                 date: str, read_fn: Callable[[], tuple], post: Callable[[str, object], None],
                 actions=None, exact_fn: Callable[[tuple], tuple | None] | None = None,
                 feed: LiveFeed | None = None,
                 mouse_fn: Callable[[], tuple[int, int] | None] = lambda: None,
                 chart_rect=None, ignore_fn: Callable[[], object] = lambda: None):
        self.engine, self.manager, self.journal = engine, manager, journal
        self.date, self.read_fn, self.post = date, read_fn, post
        self.actions, self.exact_fn = actions, exact_fn
        self.feed = feed or LiveFeed()
        self.mouse_fn, self.chart_rect, self.ignore_fn = mouse_fn, chart_rect, ignore_fn
        self.mouse_in = 0
        self.fails = 0
        self.finished = False
        self.saved_to = None            # Datei, in der das Tagesergebnis steht

    def step(self, now) -> bool:
        if self.finished:
            return False
        sec = sec_of_day(now)
        if self._mouse_in_chart():
            # Die Legende zeigt jetzt die Kerze UNTER DER MAUS, nicht die aktuelle -> nicht lesen
            self.mouse_in += 1
            if self.mouse_in == 1 or self.mouse_in % 60 == 0:
                self.post(STATUS, ("Maus aus dem Chart nehmen! Solange sie dort ist, liest der Bot "
                                   "nicht (die Legende zeigt sonst die Kerze unter der Maus).",
                                   "warn"))
            vals, text = None, "(Maus im Chart)"
        else:
            self.mouse_in = 0
            vals, text, _img = self.read_fn()
            if self._mouse_in_chart():                    # während des Lesens reingefahren
                self.mouse_in = 1
                vals, text = None, "(Maus im Chart)"
        last_c = self.actions.last_closed[3] if self.actions and self.actions.last_closed else None
        if vals is not None and check_plausible(*vals, prev_close=last_c):
            vals = None                                   # unplausibel -> wie unlesbar
        if vals is None and self.mouse_in:
            pass                                          # kein Lesefehler, nur gewartet
        elif vals is None:
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
        last = self.actions.last_closed if self.actions else None
        self.manager.on_time(sec, fresh[3] if fresh else (last[3] if last else None))
        if not self.manager.done and sec >= DAY_END and self.manager.state != IN_TRADE:
            self.manager._finish(self.manager.result or "Tagesende", None, None,
                                 "16:00 NY - Tag beendet.")
        if self.manager.done:
            self.saved_to = self.journal.write_trade(self.manager.row(self.date))
            self.finished = True
            self.post(DONE, self.manager.snapshot(self.engine.snapshot()))
            return False
        if fresh is not None and not closed:
            self.post(STATUS, (f"{now:%H:%M:%S} NY  Kerze {m2t(int(sec // 300) * 5)}: "
                               f"Kurs {fresh[3]:.2f}  ({self.manager.state})", "info"))
        return True

    def fresh_price(self) -> float | None:
        """Kurs JETZT aus der Legende (None, wenn die Maus im Chart steht oder die Lesung
        unplausibel/unlesbar ist)."""
        if self._mouse_in_chart():
            return None
        vals, _text, _img = self.read_fn()
        if vals is None:
            return None
        last = self.actions.last_closed[3] if self.actions and self.actions.last_closed else None
        return None if check_plausible(*vals, prev_close=last) else vals[3]

    def _mouse_in_chart(self) -> bool:
        """Steht die Maus (des Nutzers) im Chart? Über dem Bot-Fenster zählt nicht."""
        try:
            pos = self.mouse_fn()
        except Exception:
            return False
        if not pos or not config.in_rect(pos[0], pos[1], self.chart_rect):
            return False
        return not config.in_rect(pos[0], pos[1], self.ignore_fn())

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
        self.manager.on_bar_closed(minute, vals if exact else None)
        self.post(CANDLE, (self.manager.snapshot(self.engine.snapshot()), rep.events))

    def run(self, stop: threading.Event, clock: Callable = now_ny, poll: float = 0.5):
        """Läuft, bis der Tag erledigt ist. Ein einzelner unerwarteter Fehler beendet den Lauf
        NICHT (sonst würde ein offener Trade nicht mehr verwaltet) - erst 20 in Folge."""
        errors = 0
        while not stop.is_set():
            try:
                if not self.step(clock()):
                    return
                errors = 0
            except Exception as exc:
                errors += 1
                self.journal.log_action(f"FEHLER ({errors}x in Folge): {exc!r}")
                if errors >= 20:
                    self.finished = True
                    self.post(ERROR, f"Wiederholter Fehler, Bot gestoppt: {exc!r}. Bitte "
                                     f"offene Position in TradingView prüfen!")
                    return
                self.post(STATUS, (f"Fehler (läuft weiter): {exc!r}", "warn"))
            time.sleep(poll)


def warn_price_dependent(cfg: dict, names: list[str]):
    from .recorder import price_dependent_clicks
    for name in names:
        for warn in price_dependent_clicks(cfg, name):
            print(f"ACHTUNG Ablauf '{name}': {warn} - Linien im Chart liegen jeden Tag woanders."
                  f" Besser neu aufnehmen: python live.py --aufnehmen {name}")


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
             clock: Callable = now_ny, sim_factor: float = 1.0,
             probe_note: str | None = None) -> int:
    """Der echte Live-Lauf. probe_note = Text für den Probelauf (verschobene Uhr)."""
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
    warn_price_dependent(cfg, need)
    if probe_note is None and (why := start_problem(clock())):
        print(why)
        return 1
    ocr.setup_tesseract(cfg.get("tesseract"))
    date = clock().strftime("%Y-%m-%d")
    journal = Journal(out_dir)
    journal.log_action(f"Start LIVE {date}, Orders {'AN' if orders else 'AUS (--ohne-orders)'}"
                       + (f", {probe_note}" if probe_note else ""))
    if probe_note:
        print(probe_note)
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
    paper = PaperLock(cfg, journal)
    actions = LiveActions(cfg, Drawer(cfg, guard, post=lambda t: post_status(t, "info")),
                          paper, painter=painter, enabled=orders,
                          post=post_status, around=hidden)
    paper.dismiss_fn = actions.dismiss_messages
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

    from . import winutil
    runner = LiveRunner(engine, manager, journal, date=date, read_fn=read_fn,
                        post=lambda k, p: q.put((k, p)), actions=actions,
                        exact_fn=exact_fn if cfg.get("genau_lesen", True) else None,
                        mouse_fn=winutil.mouse_pos, chart_rect=cfg["chart"],
                        ignore_fn=lambda: ui["fenster"])

    manager.price_fn = runner.fresh_price
    win = StatusWindow(cfg, on_stop=stop.set)
    win.show(manager.snapshot(engine.snapshot()))
    win.set_status(("PROBELAUF" if probe_note else "LIVE") + ": Maus NICHT anfassen. F12 = sofort "
                   "stoppen. Warte auf Kerzen ab 9:00 NY.", "warn")

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
                    win.set_status(f"Fertig: {manager.reason} Gespeichert in "
                                   f"{runner.saved_to or journal.trades}.", "ok")
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
    """Eine Beispiel-Box um den aktuellen Kurs an der aktuellen Kerze einzeichnen (Test)."""
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
    guard = Guard(cfg, journal)
    print("In 3 Sekunden geht es los - Maus nicht anfassen.")
    time.sleep(3)
    if cfg.get("parkplatz"):                     # Maus im Chart -> Legende zeigt falsche Kerze
        guard.move_to(*cfg["parkplatz"], "Maus parken")
        time.sleep(0.5)
    vals, text = ocr.read_ohlc(ocr.grab(cfg["legende"]))
    if vals is None:
        print(f"Legende nicht lesbar ({text!r}).")
        return 1
    entry = vals[3]
    stop, target = (entry - 20, entry + 40) if direction == "long" else (entry + 20, entry - 40)
    print(f"Test: {direction} Entry {entry:.2f}, Stop {stop:.2f}, Ziel {target:.2f}.")
    try:
        make_painter(cfg, guard, lambda t, l: print(f"  {t}"))(
            direction, entry, stop, target, last_closed=vals, on_given_candle=True)
    except Exception as exc:
        print(f"FEHLER: {exc}")
        return 1
    print("Fertig.")
    return 0


SEQUENZEN = {
    "kaufen": ["kaufen"], "verkaufen": ["verkaufen"], "breakeven": ["breakeven"],
    "schliessen": ["schliessen"],
    "alle": ["kaufen", "breakeven", "schliessen", "verkaufen", "breakeven", "schliessen"],
}


def run_sequence(actions, price: float, steps: list[str], *, say=print, sleep=time.sleep,
                 pause: float = 4.0) -> bool:
    """Spielt die Schritte nacheinander ab. Beispielwerte um den aktuellen Kurs:
    Long: SL -50 / TP +50, Break-even-SL -20; Short spiegelbildlich. Bricht beim ersten
    Fehler ab (dann ist unklar, was offen ist)."""
    side = None
    for i, name in enumerate(steps, 1):
        say(f"[{i}/{len(steps)}] {name} ...")
        try:
            if name == "kaufen":
                side = "long"
                actions.market("long", price - 50, price + 50)
            elif name == "verkaufen":
                side = "short"
                actions.market("short", price + 50, price - 50)
            elif name == "breakeven":
                actions.breakeven(price - 20 if side != "short" else price + 20)
            elif name == "schliessen":
                actions.close()
        except Exception as exc:
            say(f"FEHLER bei '{name}': {exc}")
            say("Abgebrochen. Prüfe in TradingView, was offen ist.")
            return False
        say(f"    '{name}' ausgeführt. Schau im Chart, ob es geklappt hat.")
        if i < len(steps):
            sleep(pause)
    return True


def run_action_test(action: str, out_dir: str, cfg_path: str = "config.json",
                    confirm=input) -> int:
    """Kaufen/Verkaufen/Break-even/Schließen einzeln oder nacheinander im PAPER-Konto testen."""
    from . import ocr
    from .account import PaperLock
    from .draw import Drawer
    from .orders import LiveActions
    from .safety import Guard

    cfg = config.load(cfg_path)
    steps = SEQUENZEN[action]
    missing = [s for s in dict.fromkeys(steps)
               if not (cfg.get("ablaeufe") or {}).get(s)]
    for k in ("legende", "konto", "parkplatz"):
        if not cfg.get(k):
            missing.append(f"Kalibrierung '{k}'")
    if missing:
        print("Es fehlt noch: " + ", ".join(missing) + "\nErst kalibrieren/aufnehmen (siehe README).")
        return 1
    warn_price_dependent(cfg, list(dict.fromkeys(steps)))
    ocr.setup_tesseract(cfg.get("tesseract"))
    journal = Journal(out_dir)
    stop = threading.Event()
    guard = Guard(cfg, journal, stop_event=stop)
    install_f12(journal)
    guard.move_to(*cfg["parkplatz"], "Maus parken")
    time.sleep(0.5)
    vals, text = ocr.read_ohlc(ocr.grab(cfg["legende"]))
    if vals is None:
        print(f"Legende nicht lesbar ({text!r}) - Kurs unbekannt.")
        return 1
    price = vals[3]
    paper = PaperLock(cfg, journal)
    try:
        paper.check("Aktions-Test")
    except Exception as exc:
        print(f"STOPP: {exc}")
        return 1
    print(f"Paper-Konto erkannt. Kurs ca. {price:.2f}, Menge {int(cfg.get('menge', 1))}.")
    print("Ablauf: " + " -> ".join(steps))
    print("Das sind ECHTE Klicks im Paper-Konto (Ein-Klick-Handel muss AUS sein).")
    if confirm("Zum Starten JA tippen: ").strip().lower() != "ja":
        print("Abgebrochen.")
        return 0
    print("Los in 5 Sekunden - Maus nicht anfassen. F12 = Abbruch.")
    time.sleep(5)
    actions = LiveActions(cfg, Drawer(cfg, guard, post=lambda t: print(f"    {t}")), paper)
    paper.dismiss_fn = actions.dismiss_messages
    ok = run_sequence(actions, price, steps)
    journal.log_action(f"Aktions-Test {action}: {'OK' if ok else 'FEHLER'}")
    print("Fertig." if ok else "Mit Fehler beendet.")
    return 0 if ok else 1
