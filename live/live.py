"""TradingView-LIVE-Bot - NUR für ein PAPER-Trading-Konto.

  python live.py --kalibrieren                 # Legende, Chart, Preisachse, Kontoname, Parkplatz
  python live.py --aufnehmen kaufen            # vormachen: kaufen, verkaufen, breakeven,
                                               #            schliessen, long, short
  python live.py --zeichnen-test long          # Einzeichnen einzeln testen
  python live.py --ohne-orders                 # beobachten + einzeichnen, OHNE zu kaufen
  python live.py                               # richtig laufen lassen (Paper-Konto)
  python live.py --auswertung                  # Statistik aus trades.csv
"""
from __future__ import annotations

import argparse
import sys

ABLAEUFE = ["kaufen", "verkaufen", "breakeven", "schliessen", "long", "short"]


def run_stats(args) -> int:
    from pathlib import Path

    from livebot.stats import compute, format_report, load_trades
    path = Path(args.ausgabe) / "trades.csv"
    rows = load_trades(path)
    if not rows:
        print(f"{path} fehlt oder ist leer - erst ein paar Tage laufen lassen.")
        return 1
    report = format_report(compute(rows, args.von, args.bis))
    print(report)
    (Path(args.ausgabe) / "auswertung.txt").write_text(report + "\n", encoding="utf-8")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    p = argparse.ArgumentParser(description="TradingView-Live-Bot (nur Paper-Trading-Konto).")
    p.add_argument("--kalibrieren", action="store_true",
                   help="Legende, Chart, Preisachse, Kontoname und Maus-Parkplatz markieren")
    p.add_argument("--aufnehmen", choices=ABLAEUFE, help="einen Ablauf einmal vormachen")
    p.add_argument("--zeichnen-test", choices=["long", "short"],
                   help="eine Beispiel-Box einzeichnen (ohne Handel)")
    p.add_argument("--ohne-orders", action="store_true",
                   help="nur beobachten, rechnen, einzeichnen - nichts kaufen/verkaufen")
    p.add_argument("--auswertung", action="store_true", help="Statistik aus trades.csv")
    p.add_argument("--von", help="mit --auswertung: ab Datum")
    p.add_argument("--bis", help="mit --auswertung: bis Datum")
    p.add_argument("--config", default="config.json", help="Pfad zur config.json")
    p.add_argument("--ausgabe", default=".", help="Ordner für trades.csv und logs/")
    p.add_argument("--sim-start", help=argparse.SUPPRESS)       # nur für Tests (Zeitraffer)
    p.add_argument("--sim-faktor", type=float, default=1.0, help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    if args.auswertung:
        return run_stats(args)
    from livebot import winutil
    winutil.set_dpi_aware()
    if args.kalibrieren:
        from livebot import calibrate
        return 0 if calibrate.run(args.config) else 1
    if args.aufnehmen:
        from livebot import recorder
        return 0 if recorder.record(args.aufnehmen, args.config) else 1
    if args.zeichnen_test:
        from livebot.runner import run_draw_test
        return run_draw_test(args.zeichnen_test, args.ausgabe, args.config)
    from livebot.runner import run_live
    if args.sim_start:
        from livebot.nyclock import SimClock
        return run_live(args.ausgabe, args.config, orders=not args.ohne_orders,
                        clock=SimClock(args.sim_start, args.sim_faktor),
                        sim_factor=args.sim_faktor)
    return run_live(args.ausgabe, args.config, orders=not args.ohne_orders)


if __name__ == "__main__":
    sys.exit(main())
