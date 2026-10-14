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


class FakeGuardIn(FakeGuard):
    def click_in(self, region, x, y, what, double=False):
        self.calls.append(("dclick_in" if double else "click_in", region, x, y))


CHART_RECT = [60, 80, 1500, 800]


def test_anker_lenkt_nur_box_klicks_um():
    steps = full_long().validate()
    # Dialogfelder (900, 300..500) und OK (1000,700) liegen AUCH im Chart-Rechteck
    cfg = {"ablaeufe": {"long": steps}, "naechste_kerze": [900, 925], "chart": CHART_RECT}
    g = FakeGuardIn()
    Drawer(cfg, g, sleep=lambda s: None).draw("long", 30845.0, 30763.5, 31008.0,
                                              anchor=(1333, 555))
    assert g.calls[:3] == [("click", 700, 1010), ("click_in", "chart", 1333, 555),
                           ("dclick_in", "chart", 1333, 555)]
    assert ("click", 900, 300) in g.calls and ("click", 1000, 700) in g.calls


def test_anker_ohne_y_behaelt_aufgenommene_hoehe():
    cfg = {"ablaeufe": {"long": full_long().validate()}, "chart": CHART_RECT}
    g = FakeGuardIn()
    Drawer(cfg, g, sleep=lambda s: None).draw("long", 1, 0, 3, anchor=(1333, None))
    assert g.calls[1:3] == [("click_in", "chart", 1333, 400), ("dclick_in", "chart", 1333, 400)]


def test_anchor_steps_ohne_doppelklick():
    from replaybot.draw import anchor_steps
    steps = [{"punkt": [700, 1010], "doppel": False, "tippe": None},
             {"punkt": [1200, 400], "doppel": False, "tippe": None},
             {"punkt": [900, 300], "doppel": False, "tippe": "entry"}]
    assert anchor_steps(steps, CHART_RECT) == {1}
    assert anchor_steps(steps, None) == set()
