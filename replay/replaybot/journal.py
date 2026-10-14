"""Dateien schreiben: trades.csv, Kerzen-Log, Prüfungs-Log, Aktions-Log."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import Candle

TRADE_COLS = ["Datum", "Richtung", "BOS-Zeit", "Entry", "Stop", "Ziel", "Risiko",
              "Ergebnis", "R"]
CANDLE_COLS = ["Erfasst", "Datum", "Zeit", "O", "H", "L", "C", "Quelle"]
QUIZ_COLS = ["Erfasst", "Datum", "Kerze", "Frage", "Antwort", "Erwartet", "Richtig"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append(path: Path, cols: list[str], row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerow(row)


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Journal:
    """Logs dürfen den Bot NIE stoppen: Ist eine Datei gesperrt (z.B. in Excel offen),
    wird die Zeile übersprungen bzw. trades.csv-Zeilen in trades_nachtragen.csv geparkt."""

    def __init__(self, out_dir: str | Path = "."):
        self.out = Path(out_dir)
        self.trades = self.out / "trades.csv"
        self.spare = self.out / "trades_nachtragen.csv"
        self.candle_log = self.out / "logs" / "kerzen_log.csv"
        self.quiz_log = self.out / "logs" / "pruefung_log.csv"
        self.action_log = self.out / "logs" / "aktionen.log"
        self._warned: set[str] = set()

    def _safe(self, path: Path, fn):
        try:
            fn()
        except OSError as exc:
            if path.name not in self._warned:
                self._warned.add(path.name)
                print(f"WARNUNG: {path} ist gesperrt (in Excel offen?) - Zeile übersprungen: {exc}")

    def log_candle(self, date: str, c: Candle, source: str):
        self._safe(self.candle_log, lambda: _append(self.candle_log, CANDLE_COLS, {
            "Erfasst": _now(), "Datum": date, "Zeit": c.time,
            "O": c.o, "H": c.h, "L": c.l, "C": c.c, "Quelle": source}))

    def log_quiz(self, date: str, candle_time: str, question: str, answer: str,
                 expected: str, correct: bool):
        self._safe(self.quiz_log, lambda: _append(self.quiz_log, QUIZ_COLS, {
            "Erfasst": _now(), "Datum": date, "Kerze": candle_time, "Frage": question,
            "Antwort": answer, "Erwartet": expected, "Richtig": "ja" if correct else "nein"}))

    def log_action(self, text: str):
        def write():
            self.action_log.parent.mkdir(parents=True, exist_ok=True)
            with self.action_log.open("a", encoding="utf-8") as f:
                f.write(f"{_now()}  {text}\n")
        self._safe(self.action_log, write)

    def write_trade(self, row: dict) -> Path:
        """Eine Zeile pro Datum: ein erneuter Lauf am selben Tag ersetzt die alte Zeile.
        Ist trades.csv gesperrt (in Excel offen), kommt die Zeile in trades_nachtragen.csv und
        wird beim nächsten Mal automatisch übernommen. -> Datei, in der die Zeile steht."""
        try:
            pending = [r for r in _read_rows(self.spare) if r.get("Datum")]
            new_rows = pending + [row]
            dates = {r["Datum"] for r in new_rows if r.get("Datum")}
            rows = [r for r in _read_rows(self.trades)
                    if not r.get("Datum") or r.get("Datum") not in dates]
            latest = {}
            for r in new_rows:                       # pro Datum gilt die neueste Zeile
                latest[r.get("Datum") or f"_{len(latest)}"] = r
            rows += list(latest.values())
            self.trades.parent.mkdir(parents=True, exist_ok=True)
            with self.trades.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=TRADE_COLS, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
        except OSError as exc:
            _append(self.spare, TRADE_COLS, row)
            print(f"WARNUNG: {self.trades} ist gesperrt (in Excel offen?) - Ergebnis steht "
                  f"vorerst in {self.spare} ({exc}).")
            return self.spare
        try:
            if self.spare.exists():
                self.spare.unlink()
        except OSError:
            pass
        return self.trades
