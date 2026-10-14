"""Gesperrte Dateien (z.B. trades.csv in Excel offen) dürfen den Bot nicht stoppen."""
import csv

from livebot.journal import Journal
from livebot.models import Candle


def rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_trades_gesperrt_landet_in_nachtragen_und_wird_spaeter_uebernommen(tmp_path):
    j = Journal(tmp_path)
    j.write_trade({"Datum": "2026-10-01", "Ergebnis": "Ziel", "R": "2.00"})
    j.trades.rename(tmp_path / "weg.csv")
    j.trades.mkdir()                                  # "gesperrt": nicht beschreibbar
    where = j.write_trade({"Datum": "2026-10-02", "Ergebnis": "Stop", "R": "-1.00"})
    assert where == j.spare and rows(j.spare)[0]["Datum"] == "2026-10-02"
    j.trades.rmdir()
    (tmp_path / "weg.csv").rename(j.trades)           # Excel wieder zu
    where = j.write_trade({"Datum": "2026-10-03", "Ergebnis": "Ziel", "R": "2.00"})
    assert where == j.trades and not j.spare.exists()
    assert [r["Datum"] for r in rows(j.trades)] == ["2026-10-01", "2026-10-02", "2026-10-03"]


def test_gleicher_tag_ersetzt_alte_zeile(tmp_path):
    j = Journal(tmp_path)
    j.write_trade({"Datum": "2026-10-01", "Ergebnis": "Stop", "R": "-1.00"})
    j.write_trade({"Datum": "2026-10-01", "Ergebnis": "Ziel", "R": "2.00"})
    assert [(r["Datum"], r["Ergebnis"]) for r in rows(j.trades)] == [("2026-10-01", "Ziel")]


def test_gesperrtes_log_stoppt_nichts(tmp_path):
    j = Journal(tmp_path)
    j.candle_log.mkdir(parents=True)                  # Kerzen-Log "gesperrt"
    j.action_log.mkdir(parents=True)
    j.log_candle("2026-10-01", Candle("09:30", 1, 2, 0.5, 1.5), "live")
    j.log_action("Test")                              # darf nicht abstürzen
