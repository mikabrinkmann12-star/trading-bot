"""Einzeichnen vormachen und aufnehmen (python bot.py --aufnehmen long|short).

Du zeichnest einmal echt in TradingView, der Bot merkt sich jeden Linksklick:
  F6 = in das zuletzt angeklickte Feld kommt später der ENTRY
  F7 = ... der STOP
  F8 = ... das ZIEL
  F9 = fertig (speichern),  F10 = abbrechen
"""
from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field

from . import config

DOUBLE_TIME = 0.4   # s
DOUBLE_DIST = 6     # px
MARKS = {"f6": "entry", "f7": "stop", "f8": "ziel"}
NAMES = {"entry": "Entry", "stop": "Stop", "ziel": "Ziel"}


class RecordError(ValueError):
    pass


@dataclass
class Recording:
    steps: list[dict] = field(default_factory=list)
    _last_t: float = -1.0

    def add_click(self, x: int, y: int, t: float):
        if self.steps:
            last = self.steps[-1]
            lx, ly = last["punkt"]
            if (t - self._last_t <= DOUBLE_TIME and abs(x - lx) <= DOUBLE_DIST
                    and abs(y - ly) <= DOUBLE_DIST and not last["doppel"]):
                last["doppel"] = True
                self._last_t = -1.0   # dritter Klick zählt wieder neu
                return
        self.steps.append({"punkt": [x, y], "doppel": False, "tippe": None})
        self._last_t = t

    def mark(self, what: str):
        if not self.steps:
            raise RecordError("Erst ins Feld klicken, dann F6/F7/F8 drücken.")
        last = self.steps[-1]
        if last["doppel"]:
            raise RecordError("Letzter Klick war ein Doppelklick - ins Feld bitte EINMAL klicken.")
        last["tippe"] = what

    def validate(self) -> list[dict]:
        marked = {s["tippe"] for s in self.steps if s["tippe"]}
        missing = [NAMES[k] for k in ("entry", "stop", "ziel") if k not in marked]
        if missing:
            raise RecordError(f"Es fehlt die Markierung für: {', '.join(missing)} "
                              f"(F6 Entry, F7 Stop, F8 Ziel).")
        return self.steps


def describe(steps: list[dict]) -> str:
    lines = []
    for i, s in enumerate(steps, 1):
        x, y = s["punkt"]
        act = "Doppelklick" if s["doppel"] else "Klick"
        typ = f"  -> tippt {NAMES[s['tippe']]}" if s["tippe"] else ""
        lines.append(f"  {i}. {act} auf ({x}, {y}){typ}")
    return "\n".join(lines)


def record(direction: str, cfg_path: str = "config.json") -> bool:
    import keyboard

    from . import winutil

    side = "Long" if direction == "long" else "Short"
    print(f"""
Aufnahme {side}-Position. Mach es jetzt EINMAL in TradingView vor:
  1. Klick auf das {side}-Positions-Werkzeug
  2. Klick in den Chart (irgendwo rechts, wo Platz ist)
  3. Doppelklick auf die neue Box -> Einstellungen gehen auf
  4. Klick ins Feld Einstiegspreis, dann F6
  5. Klick ins Preisfeld vom Gewinn-/Ziel-Niveau, dann F8
  6. Klick ins Preisfeld vom Stopp-Niveau, dann F7
  7. Klick auf OK
  F9 = fertig und speichern,  F10 = abbrechen
(Die Box, die du dabei zeichnest, kannst du danach löschen.)
""")
    events: queue.Queue = queue.Queue()
    for key in ("f6", "f7", "f8", "f9", "f10"):
        keyboard.add_hotkey(key, lambda k=key: events.put(k), suppress=True)

    rec = Recording()
    was_down = False
    try:
        while True:
            down = winutil.left_button_down()
            if down and not was_down:
                x, y = winutil.mouse_pos()
                n = len(rec.steps)
                rec.add_click(x, y, time.monotonic())
                if len(rec.steps) > n:
                    print(f"  Klick {len(rec.steps)} auf ({x}, {y})")
                else:
                    print("  -> Doppelklick")
            was_down = down
            try:
                key = events.get_nowait()
            except queue.Empty:
                time.sleep(0.01)
                continue
            if key == "f10":
                print("Abgebrochen - nichts gespeichert.")
                return False
            if key == "f9":
                try:
                    steps = rec.validate()
                except RecordError as exc:
                    print(f"  Noch nicht fertig: {exc}")
                    continue
                break
            try:
                rec.mark(MARKS[key])
                print(f"     markiert: hier wird {NAMES[MARKS[key]]} getippt")
            except RecordError as exc:
                print(f"  {exc}")
    finally:
        keyboard.unhook_all_hotkeys()

    print(f"\nAufgenommen ({side}):\n{describe(steps)}")
    bad = []
    for s in steps:
        title, exe = winutil.window_title_at(*s["punkt"]), winutil.window_exe_at(*s["punkt"])
        if "tradingview" not in (title + exe).lower():
            bad.append(f"({s['punkt'][0]}, {s['punkt'][1]}): '{title}' / '{exe}'")
    if bad:
        print("ACHTUNG - dort liegt jetzt kein TradingView-Fenster, der Bot würde dort "
              "nicht klicken:\n  " + "\n  ".join(bad))
        print("(Normal, wenn der Einstellungsdialog inzwischen zu ist und dahinter TradingView "
              "liegt - sonst neu aufnehmen.)")
    cfg = config.load(cfg_path)
    cfg.setdefault("ablaeufe", {})[direction] = steps
    config.save(cfg, cfg_path)
    print(f"Gespeichert in {cfg_path}. Testen mit:  python bot.py --zeichnen-test {direction}")
    return True
