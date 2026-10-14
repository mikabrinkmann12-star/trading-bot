import pytest

from replaybot.draw import Drawer, format_price
from replaybot.safety import SafetyError
from test_recorder import full_long


class FakeGuard:
    def __init__(self):
        self.calls = []

    def click(self, x, y, what, double=False):
        self.calls.append(("dclick" if double else "click", x, y))

    def type_text(self, text, what):
        self.calls.append(("type", what, text))

    def press(self, key, what):
        self.calls.append(("press", key))

    def move_to(self, x, y, what):
        self.calls.append(("move", x, y))


@pytest.mark.parametrize("v,dec,out", [
    (30845.0, ",", "30845,00"),
    (28962.25, ",", "28962,25"),
    (30845.125, ",", "30845,25"),
    (30845.1, ".", "30845.00"),
    (30763.5, ".", "30763.50"),
])
def test_format_price(v, dec, out):
    assert format_price(v, dec) == out


def test_zeichnet_long_mit_richtigen_werten():
    cfg = {"ablaeufe": {"long": full_long().validate()}, "naechste_kerze": [900, 925]}
    g = FakeGuard()
    Drawer(cfg, g, sleep=lambda s: None).draw("long", 30845.0, 30763.5, 31008.0)
    assert g.calls == [
        ("click", 700, 1010), ("click", 1200, 400), ("dclick", 1200, 400),
        ("click", 900, 300), ("type", "entry", "30845,00"),
        ("click", 900, 400), ("type", "ziel", "31008,00"),
        ("click", 900, 500), ("type", "stop", "30763,50"),
        ("click", 1000, 700),
        ("press", "esc"), ("move", 900, 925),
    ]


def test_ohne_aufnahme_fehler():
    with pytest.raises(SafetyError, match="aufnehmen short"):
        Drawer({"ablaeufe": {}}, FakeGuard(), sleep=lambda s: None).draw("short", 1, 2, 3)
