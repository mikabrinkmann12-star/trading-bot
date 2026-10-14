import pytest

from replaybot.legend import LegendError, check_plausible, normalize_number, parse_legend


@pytest.mark.parametrize("tok,val", [
    ("30.877,00", 30877.0),
    ("30877,00", 30877.0),
    ("30.877.00", 30877.0),   # Komma als Punkt gelesen
    ("30,877,00", 30877.0),
    ("28.962,25", 28962.25),
    ("30877", 30877.0),
])
def test_normalize_number(tok, val):
    assert normalize_number(tok) == pytest.approx(val)


@pytest.mark.parametrize("text", [
    "O30.877,00 H30.888,75 L30.847,50 C30.874,25",
    "O30.877,00 H30.888,75 L30.847,50 C30.874,25 -2,50 (-0,01%)",
    "O30.877,00H30.888,75L30.847,50C30.874,25",
    "030.877,00 H30.888,75 L30.847,50 C30.874,25",      # O als 0 gelesen
    "O 30.877,00  H 30.888,75\nL 30.847,50  C 30.874,25",
    "30.877,00 30.888,75 30.847,50 30.874,25 -2,50 (-0,01%)",  # Buchstaben verloren
    "O30877,00 H30888,75 L30847,50 C30874,25",
    "O30.877,00H30.888,75L30.847,50C30.874,25-2,50(-0,01%)",   # Leerzeichen verschluckt
    "030.877,00H30.888,75L30.847,50C30.874,252,50(+0,01%)",    # dazu Minus verloren
    "30.877,0030.888,7530.847,5030.874,25",
])
def test_parse_legend(text):
    assert parse_legend(text) == pytest.approx((30877.0, 30888.75, 30847.5, 30874.25))


@pytest.mark.parametrize("text", ["", "O H L C", "O30.877,00 H30.888,75"])
def test_parse_legend_fehler(text):
    with pytest.raises(LegendError):
        parse_legend(text)


def test_plausibel():
    assert check_plausible(30877, 30888.75, 30847.5, 30874.25) is None
    assert "verletzt" in check_plausible(30877, 30870, 30847.5, 30874.25)   # O > H
    assert check_plausible(30877, 30888.75, 30847.5, 30874.25, prev_close=30870) is None
    # verschluckte Ziffer: 3087.00 statt 30877.00
    assert "Ziffer" in check_plausible(30877, 30888.75, 30847.5, 30874.25, prev_close=3087)
    # Spanne unrealistisch (L als 16.85 statt 16859.75 gelesen) - auch ohne prev_close
    assert "Ziffer" in check_plausible(16861.25, 16878.25, 16.85, 16871.25)
