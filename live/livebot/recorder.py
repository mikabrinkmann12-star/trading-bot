"""Abläufe vormachen und aufnehmen (python live.py --aufnehmen NAME).

Du machst es einmal echt in TradingView vor, der Bot merkt sich jeden Linksklick:
  F5 = in das zuletzt angeklickte Feld kommt später die MENGE
  F6 = ... der ENTRY      F7 = ... der STOP      F8 = ... das ZIEL
  F9 = fertig (speichern),  F10 = abbrechen
"""
from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field

from . import config

DOUBLE_TIME = 0.4   # s
DOUBLE_DIST = 6     # px
MARKS = {"f5": "menge", "f6": "entry", "f7": "stop", "f8": "ziel"}
NAMES = {"menge": "Menge", "entry": "Entry", "stop": "Stop", "ziel": "Ziel"}
KEYS = {"menge": "F5", "entry": "F6", "stop": "F7", "ziel": "F8"}

# Welche Felder muss welcher Ablauf haben?
REQUIRED = {
    "long": ("entry", "stop", "ziel"),
    "short": ("entry", "stop", "ziel"),
    "kaufen": ("menge", "stop", "ziel"),
    "verkaufen": ("menge", "stop", "ziel"),
    "breakeven": ("entry",),
    "schliessen": (),
    "meldungen": (),
}

ANLEITUNG = {
    "long": """  1. Klick auf das Long-Positions-Werkzeug
  2. Klick in den Chart (irgendwo rechts, wo Platz ist)
  3. Doppelklick auf die neue Box -> Einstellungen gehen auf
  4. Klick ins Feld Einstiegspreis -> F6
  5. Klick ins Preisfeld vom Gewinn-/Ziel-Niveau -> F8
  6. Klick ins Preisfeld vom Stopp-Niveau -> F7
  7. Klick auf OK""",
    "kaufen": """  1. Klick auf 'Markt kaufen' (oben links im Chart)
  2. Im Order-Fenster: Klick ins Feld MENGE -> F5
  3. Take Profit einschalten (Haken) und Klick ins TP-PREISFELD -> F8
  4. Stop Loss einschalten (Haken) und Klick ins SL-PREISFELD -> F7
  5. Klick auf den Bestätigen-/Kaufen-Knopf
  6. Bleibt das Order-Fenster offen: Klick auf das X oben (der Bot wartet vorher 2,5 s)
  WICHTIG: Klicke in Preisfelder immer auf die ZAHL links im Feld, NIE auf die Symbole rechts
  daneben (z.B. das Pfeil-Symbol 'Werte umschalten' oder 'Ticks').
  Am besten sind Take Profit und Stop Loss vor dem Vormachen AUS. Sind sie später schon AN,
  merkt der Bot das (Feld bleibt gesperrt/blass) und schaltet selbst richtig.
  (In der Paper-Übung darfst du dabei wirklich kaufen - danach die Position selbst schließen.)""",
    "breakeven": """  1. Unten im HANDELSPANEL bei der offenen Position auf 'Bearbeiten' (Stift) klicken
     - NICHT im Chart auf die SL-Linie: die liegt jeden Tag woanders.
  2. Klick ins SL-PREISFELD -> F6 (dort tippt der Bot später den Entry ein)
  3. Klick auf Ändern/Bestätigen (und ggf. das X, falls das Fenster offen bleibt)""",
    "schliessen": """  1. Unten im HANDELSPANEL bei der offenen Position auf 'Schließen' (X) klicken
     - NICHT das X an der Positionslinie im Chart: die liegt jeden Tag woanders.
  2. Falls eine Rückfrage kommt: Klick auf Bestätigen""",
}
ANLEITUNG["meldungen"] = """  ERST den Kauf von Hand machen (Paper-Konto), damit Meldungen da sind - und ERST DANACH
  diesen Befehl starten. In der Aufnahme darf KEIN Kauf mehr vorkommen!
  Aufgenommen wird nur das Wegklicken:
  1. Auf das Glocken-/Meldungs-Symbol klicken (Meldungen öffnen), falls nötig
  2. Auf 'Alle schließen / Alle löschen' klicken - so, wie du ALLE Meldungen auf einmal
     wegmachst (höchstens 5 Klicks)
  Danach F9. Position schließt du selbst.
  Der Bot klickt das nur, wenn er den Kontonamen nicht lesen kann. Klicks auf Kaufen/
  Verkaufen/Bestätigen werden abgelehnt."""
ANLEITUNG["short"] = ANLEITUNG["long"].replace("Long", "Short")
ANLEITUNG["verkaufen"] = ANLEITUNG["kaufen"].replace("kaufen", "verkaufen").replace(
    "Kaufen", "Verkaufen")


ORDER_FLOWS = ("kaufen", "verkaufen", "breakeven", "schliessen")


class RecordError(ValueError):
    pass


MAX_MELDUNGEN_KLICKS = 5


def order_points(cfg: dict) -> list[tuple[int, int, str]]:
    """Gefährliche Klickpunkte aus den Order-Abläufen: der Kaufen-/Verkaufen-Knopf (1. Klick),
    jeder Klick direkt nach dem letzten Tipp-Feld (Bestätigen) und der Schließen-Knopf."""
    out = []
    for name in ("kaufen", "verkaufen", "breakeven", "schliessen"):
        steps = (cfg.get("ablaeufe") or {}).get(name) or []
        if not steps:
            continue
        idx = {0} if name != "breakeven" else set()
        typed = [i for i, s in enumerate(steps) if s.get("tippe")]
        if typed and typed[-1] + 1 < len(steps):
            idx.add(typed[-1] + 1)
        for i in idx:
            x, y = steps[i]["punkt"]
            out.append((x, y, f"'{name}' Schritt {i + 1}"))
    return out


def meldungen_problem(cfg: dict, steps: list[dict]) -> str | None:
    """Warum ein Ablauf 'meldungen' NICHT erlaubt ist (oder None). Er darf nie etwas kaufen,
    verkaufen, bestätigen oder schließen."""
    if len(steps) > MAX_MELDUNGEN_KLICKS:
        return (f"{len(steps)} Klicks sind zu viel (höchstens {MAX_MELDUNGEN_KLICKS}) - das sieht "
                f"nach einem Kauf in der Aufnahme aus")
    if any(s.get("tippe") for s in steps):
        return "enthält ein Tipp-Feld"
    for i, s in enumerate(steps):
        sx, sy = s["punkt"]
        for ox, oy, what in order_points(cfg):
            if abs(sx - ox) <= 15 and abs(sy - oy) <= 15:
                return f"Klick {i + 1} ({sx}, {sy}) liegt auf {what} (Kaufen/Verkaufen/Bestätigen)"
    return None


def price_dependent_clicks(cfg: dict, name: str) -> list[str]:
    """Order-Abläufe: Klicks VOR dem ersten Tipp-Feld mitten im Chart (z.B. auf die SL-Linie
    oder das X an der Positionslinie) hängen vom Kurs ab und treffen morgen nichts mehr.
    Ausgenommen ist der Bereich oben links (Legende, Kaufen/Verkaufen-Knöpfe)."""
    from .candlefind import legend_zone
    steps = (cfg.get("ablaeufe") or {}).get(name) or []
    chart = cfg.get("chart")
    if name not in ORDER_FLOWS or not chart:
        return []
    zone = legend_zone(cfg.get("legende"), chart)
    first_type = next((i for i, s in enumerate(steps) if s.get("tippe")), len(steps))
    out = []
    for i, s in enumerate(steps[:max(first_type, 1)]):
        x, y = s["punkt"]
        if config.in_rect(x, y, chart) and not config.in_rect(x, y, zone):
            out.append(f"Schritt {i + 1} ({x}, {y}) liegt mitten im Chart")
    return out


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
            raise RecordError("Erst ins Feld klicken, dann F5/F6/F7/F8 drücken.")
        last = self.steps[-1]
        if last["doppel"]:
            raise RecordError("Letzter Klick war ein Doppelklick - ins Feld bitte EINMAL klicken.")
        last["tippe"] = what

    def validate(self, required=("entry", "stop", "ziel")) -> list[dict]:
        if not self.steps:
            raise RecordError("Noch kein Klick aufgenommen.")
        marked = {s["tippe"] for s in self.steps if s["tippe"]}
        missing = [k for k in required if k not in marked]
        if missing:
            raise RecordError("Es fehlt die Markierung für: "
                              + ", ".join(f"{NAMES[k]} ({KEYS[k]})" for k in missing))
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

    side = direction
    print(f"""
Aufnahme '{direction}'. Mach es jetzt EINMAL in TradingView vor:
{ANLEITUNG[direction]}
  F9 = fertig und speichern,  F10 = abbrechen
""")
    events: queue.Queue = queue.Queue()
    for key in ("f5", "f6", "f7", "f8", "f9", "f10"):
        keyboard.add_hotkey(key, lambda k=key: events.put(k), suppress=True)

    rec = Recording()
    was_down = False
    try:
        while True:
            down = winutil.left_button_down()
            if down and not was_down:
                x, y = winutil.mouse_pos()
                title, exe = winutil.window_title_at(x, y), winutil.window_exe_at(x, y)
                if "tradingview" not in (title + exe).lower():
                    print(f"  (Klick auf ({x}, {y}) ignoriert - kein TradingView-Fenster)")
                    was_down = down
                    continue
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
                    steps = rec.validate(REQUIRED[direction])
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
    if direction == "meldungen" and (why := meldungen_problem(cfg, steps)):
        print(f"\nNICHT gespeichert: {why}.")
        print("Mach den Kauf von Hand VOR dem Befehl und nimm danach nur das Wegklicken auf.")
        return False
    cfg.setdefault("ablaeufe", {})[direction] = steps
    config.save(cfg, cfg_path)
    for warn in price_dependent_clicks(cfg, direction):
        print(f"ACHTUNG: {warn} - Linien im Chart liegen jeden Tag woanders. Besser über das "
              f"Handelspanel unten neu aufnehmen.")
    test = (f"python live.py --zeichnen-test {direction}" if direction in ("long", "short")
            else f"python live.py --aktion-test {direction}")
    print(f"Gespeichert in {cfg_path}. Testen mit:  {test}")
    return True
