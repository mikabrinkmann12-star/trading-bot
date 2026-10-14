"""Dateien schreiben: trades.csv, Kerzen-Log, Prüfungs-Log, Aktions-Log."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import Candle

TRADE_COLS = ["Datum", "Richtung", "BOS-Zeit", "Entry", "Stop", "Ziel", "Risiko",
              "Füllzeit", "Füllkurs", "Ausstieg", "Ergebnis", "R"]
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


class Journal:
    def __init__(self, out_dir: str | Path = "."):
        self.out = Path(out_dir)
        self.trades = self.out / "trades.csv"
        self.candle_log = self.out / "logs" / "kerzen_log.csv"
        self.quiz_log = self.out / "logs" / "pruefung_log.csv"
        self.action_log = self.out / "logs" / "aktionen.log"

    def log_candle(self, date: str, c: Candle, source: str):
        _append(self.candle_log, CANDLE_COLS, {
            "Erfasst": _now(), "Datum": date, "Zeit": c.time,
            "O": c.o, "H": c.h, "L": c.l, "C": c.c, "Quelle": source})

    def log_quiz(self, date: str, candle_time: str, question: str, answer: str,
                 expected: str, correct: bool):
        _append(self.quiz_log, QUIZ_COLS, {
            "Erfasst": _now(), "Datum": date, "Kerze": candle_time, "Frage": question,
            "Antwort": answer, "Erwartet": expected, "Richtig": "ja" if correct else "nein"})

    def log_action(self, text: str):
        self.action_log.parent.mkdir(parents=True, exist_ok=True)
        with self.action_log.open("a", encoding="utf-8") as f:
            f.write(f"{_now()}  {text}\n")

    def write_trade(self, row: dict):
        """Eine Zeile pro Datum: ein erneuter Lauf am selben Tag ersetzt die alte Zeile."""
        rows = []
        if self.trades.exists():
            with self.trades.open(newline="", encoding="utf-8") as f:
                rows = [r for r in csv.DictReader(f) if r.get("Datum") != row["Datum"]
                        or not row["Datum"]]
        rows.append(row)
        self.trades.parent.mkdir(parents=True, exist_ok=True)
        with self.trades.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=TRADE_COLS)
            w.writeheader()
            w.writerows(rows)
