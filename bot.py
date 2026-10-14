"""TradingView-Replay-Bot - NUR Replay/Paper, kein echtes Geld, kein Broker.

  python bot.py --csv tests/data/2026-09-25.csv            # Tag aus CSV durchrechnen
  python bot.py --csv tests/data/2026-09-25.csv --pruefen  # optional: Prüfmodus
  python bot.py --kalibrieren                              # einmalig: Legende/Buttons markieren
  python bot.py --live --datum 2026-09-25                  # Bildschirm mitlesen
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
    if args.pruefen:
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
    p.add_argument("--pruefen", action="store_true",
                   help="Prüfmodus an: vor jedem Schritt deine Antwort abfragen (nur --csv)")
    p.add_argument("--kalibrieren", action="store_true",
                   help="Legende, Chart-Bereich und 'Nächste Kerze' markieren -> config.json")
    p.add_argument("--live", action="store_true",
                   help="Legende vom Bildschirm lesen (du klickst 'Nächste Kerze')")
    p.add_argument("--start", default="09:00",
                   help="Uhrzeit der Kerze, auf der das Replay beim Start steht (Standard 09:00)")
    p.add_argument("--config", default="config.json", help="Pfad zur config.json")
    p.add_argument("--ausgabe", default=".",
                   help="Ordner für trades.csv und logs/ (Standard: aktueller Ordner)")
    args = p.parse_args(argv)

    if args.csv:
        return run_csv(args)
    if args.kalibrieren or args.live:
        from replaybot import winutil
        winutil.set_dpi_aware()
    if args.kalibrieren:
        from replaybot import calibrate
        return 0 if calibrate.run(args.config) else 1
    if args.live:
        from replaybot.live import run_live
        date = args.datum or input("Datum des Replay-Tages (z.B. 2026-09-25): ").strip()
        return run_live(date, args.start, args.ausgabe, args.config)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
