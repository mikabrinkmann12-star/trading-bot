"""TradingView-Replay-Trainingsbot - NUR Replay/Paper, kein echtes Geld, kein Broker.

Phase 1 (CSV-Testmodus):
  python bot.py --csv tests/data/2026-09-25.csv                 # Prüfmodus (Standard)
  python bot.py --csv tests/data/2026-09-25.csv --ohne-pruefen  # nur durchrechnen
"""
from __future__ import annotations

import argparse
import sys

from replaybot.csv_source import date_from_filename, read_candles
from replaybot.journal import Journal
from replaybot.quiz import Quiz, QuizAbort
from replaybot.strategy import StrategyEngine


def print_status(engine: StrategyEngine):
    snap = engine.snapshot()
    print(f"\n=== Schritt {snap['step']}: {snap['step_name']} ===")
    for label, value in snap["values"]:
        print(f"  {label:<11} {value}")
    print(f"  -> {snap['reason']}")


def run_csv(args) -> int:
    candles = read_candles(args.csv)
    if not candles:
        print(f"Keine Kerzen in {args.csv} gefunden.")
        return 1
    date = args.datum or date_from_filename(args.csv)
    engine = StrategyEngine(date=date)
    journal = Journal(args.ausgabe)
    quiz = None
    if not args.ohne_pruefen:
        quiz = Quiz(ask=lambda q: input(f"  ? {q} "), say=lambda t: print(f"    {t}"),
                    journal=journal, date=date)
        print("Prüfmodus: Nach jeder Kerze beantwortest du die Fragen zum aktuellen Schritt.")
        print("Zahlen mit Punkt oder Komma. Leer/'kb' = Lösung zeigen, 'q' = beenden.\n")

    print(f"Datum {date or '-'}, {len(candles)} Kerzen aus {args.csv}\n")
    try:
        for c in candles:
            if quiz is not None:
                if input("[Enter] nächste Kerze ").strip().lower() in ("q", "quit", "ende"):
                    raise QuizAbort()
            print(f"Kerze {c}")
            journal.log_candle(date, c, "csv")
            rep = engine.on_candle(c)
            if quiz is not None:
                quiz.run(engine, rep)
            for ev in rep.events:
                print(f"    * {ev}")
            if quiz is not None and not rep.ignored:
                print(f"    -> {engine.reason}")
            if engine.done:
                break
    except QuizAbort:
        print("\nAbgebrochen.")
        if quiz is not None:
            print(quiz.summary())
        return 0

    engine.end_of_data()
    print_status(engine)
    journal.write_trade(engine.trade_row())
    print(f"\nGespeichert: {journal.trades} und {journal.candle_log}")
    if quiz is not None:
        print("\n" + quiz.summary())
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    p = argparse.ArgumentParser(
        description="TradingView-Replay-Trainingsbot (nur Replay/Paper).")
    p.add_argument("--csv", help="Kerzen aus CSV lesen (Zeit,O,H,L,C) - Testmodus")
    p.add_argument("--datum", help="Datum des Replay-Tages, z.B. 2026-09-25")
    p.add_argument("--ohne-pruefen", action="store_true",
                   help="Prüfmodus aus: nur rechnen und anzeigen")
    p.add_argument("--ausgabe", default=".",
                   help="Ordner für trades.csv und logs/ (Standard: aktueller Ordner)")
    args = p.parse_args(argv)

    if args.csv:
        return run_csv(args)
    p.print_help()
    print("\nPhase 1: nur --csv ist verfügbar. Live-Modus (Bildschirm/OCR) kommt in Phase 2.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
