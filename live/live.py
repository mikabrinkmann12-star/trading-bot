"""TradingView-LIVE-Bot - NUR für ein PAPER-Trading-Konto.

  python live.py --kalibrieren                 # Legende, Chart, Preisachse, Kontoname, Parkplatz
  python live.py --aufnehmen kaufen            # vormachen: kaufen, verkaufen, breakeven,
                                               #            schliessen, meldungen, long, short
  python live.py --zeichnen-test long          # Einzeichnen einzeln testen
  python live.py --aktion-test alle            # kaufen, break-even, schliessen, verkaufen, ... einmal
  python live.py --ohne-orders                 # beobachten + einzeichnen, OHNE zu kaufen
  python live.py                               # richtig laufen lassen (Paper-Konto, vor 9:00 NY starten)
  python live.py --probelauf                   # kompletter Ablauf JETZT (Uhr verschoben, Paper-Konto)
  python live.py --auswertung                  # Statistik aus trades.csv
"""
from __future__ import annotations

import argparse
import sys

ABLAEUFE = ["kaufen", "verkaufen", "breakeven", "schliessen", "meldungen", "long", "short"]


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
    p.add_argument("--aktion-test", choices=["kaufen", "verkaufen", "breakeven", "schliessen", "alle"],
                   help="Order-Abläufe im Paper-Konto einmal testen (echte Klicks!)")
    p.add_argument("--ohne-orders", action="store_true",
                   help="nur beobachten, rechnen, einzeichnen - nichts kaufen/verkaufen")
    p.add_argument("--probelauf", action="store_true",
                   help="kompletter Ablauf sofort: Uhr wird so verschoben, dass jetzt 'kurz vor "
                        "9:00' ist (echte Kerzen, Paper-Konto, Ergebnisse in probelauf/)")
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
    if args.aktion_test:
        from livebot.runner import run_action_test
        return run_action_test(args.aktion_test, args.ausgabe, args.config)
    from livebot.runner import run_live
    if args.probelauf:
        from livebot.nyclock import ShiftClock, now_ny, probe_shift, sec_of_day
        real = now_ny()
        shift = probe_shift(sec_of_day(real))
        clock = ShiftClock(shift)
        out = args.ausgabe if args.ausgabe != "." else "probelauf"
        note = (f"PROBELAUF: Es ist {real:%H:%M} NY, der Bot tut so, als wäre es "
                f"{clock():%H:%M} NY (Uhr {shift // 60} min zurückgestellt). Echte Kerzen, "
                f"Orders {'AUS' if args.ohne_orders else 'AN (Paper-Konto)'}. "
                f"Ergebnisse im Ordner '{out}'.")
        return run_live(out, args.config, orders=not args.ohne_orders, clock=clock,
                        probe_note=note)
    if args.sim_start:
        from livebot.nyclock import SimClock
        return run_live(args.ausgabe, args.config, orders=not args.ohne_orders,
                        clock=SimClock(args.sim_start, args.sim_faktor),
                        sim_factor=args.sim_faktor)
    out = args.ausgabe if args.ausgabe != "." else ("ohne_orders" if args.ohne_orders else ".")
    if out == "ohne_orders":
        print("Ohne Orders: Ergebnisse kommen in den Ordner 'ohne_orders' (nicht in trades.csv).")
    return run_live(out, args.config, orders=not args.ohne_orders)


if __name__ == "__main__":
    sys.exit(main())
