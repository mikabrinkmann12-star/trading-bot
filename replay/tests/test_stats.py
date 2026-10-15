from pathlib import Path

import pytest

import bot
from replaybot.journal import TRADE_COLS
from replaybot.stats import compute, format_report, load_trades

ROWS = [  # Datum, Richtung, BOS, Ergebnis, R
    ("2026-09-01", "long", "09:45", "Ziel", "2.00"),
    ("2026-09-02", "short", "09:50", "Stop", "-1.00"),
    ("2026-09-03", "long", "09:50", "Stop", "-1.00"),
    ("2026-09-04", "long", "", "Kein Trade", ""),
    ("2026-09-07", "short", "09:55", "Ziel", "2.00"),
    ("2026-09-08", "long", "09:45", "nicht gefüllt", ""),
    ("2026-09-09", "long", "09:45", "Zeit-Exit", "0.40"),
    ("2026-09-10", "short", "09:45", "Ziel", "2.00"),
]


def write(tmp_path, rows=ROWS):
    lines = [",".join(TRADE_COLS)]
    for d, rich, bos, erg, r in rows:
        lines.append(f"{d},{rich},{bos},1,1,1,1,{erg},{r}")
    (tmp_path / "trades.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path / "trades.csv"


def test_kennzahlen(tmp_path):
    s = compute(load_trades(write(tmp_path)))
    assert (s["tage"], s["trades"], s["kein_trade"], s["nicht_gefuellt"]) == (8, 6, 1, 1)
    assert (s["gewinner"], s["verlierer"]) == (4, 2)
    assert s["quote"] == pytest.approx(4 / 6)
    assert s["summe_r"] == pytest.approx(4.4)
    assert s["schnitt_r"] == pytest.approx(4.4 / 6)
    assert s["profit_faktor"] == pytest.approx(6.4 / 2)
    assert (s["gewinnserie"], s["verlustserie"]) == (3, 2)
    assert s["max_drawdown"] == pytest.approx(2.0)
    assert s["bester"] == ("2026-09-01", 2.0) and s["schlechtester"][1] == -1.0
    assert s["richtung"]["long"] == {"anzahl": 3, "gewinner": 2, "quote": pytest.approx(2 / 3),
                                     "summe_r": pytest.approx(1.4)}
    assert s["bos"]["09:50"]["summe_r"] == pytest.approx(-2.0)
    assert s["ergebnis"]["Zeit-Exit"]["anzahl"] == 1


def test_zeitraum(tmp_path):
    s = compute(load_trades(write(tmp_path)), von="2026-09-02", bis="2026-09-07")
    assert (s["tage"], s["trades"], s["summe_r"]) == (4, 3, pytest.approx(0.0))


def test_bericht(tmp_path):
    rep = format_report(compute(load_trades(write(tmp_path))))
    assert "Trefferquote           67 %" in rep
    assert "+4.40 R" in rep and "erst 6 Trades" in rep


def test_leer(tmp_path):
    assert load_trades(tmp_path / "gibtsnicht.csv") == []
    assert "Keine Tage" in format_report(compute([]))
    assert bot.main(["--auswertung", "--ausgabe", str(tmp_path)]) == 1


def test_ende_zu_ende(tmp_path, capsys):
    for day in ("2026-09-25", "2026-09-14"):
        assert bot.main(["--csv", str(Path(__file__).parent / "data" / f"{day}.csv"),
                         "--ausgabe", str(tmp_path)]) == 0
    assert bot.main(["--auswertung", "--ausgabe", str(tmp_path)]) == 0
    s = compute(load_trades(tmp_path / "trades.csv"))
    assert (s["trades"], s["gewinner"], s["summe_r"]) == (2, 1, pytest.approx(1.0))
    assert (tmp_path / "auswertung.txt").exists()
