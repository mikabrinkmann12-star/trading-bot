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
    Drawer(cfg, g, sleep=lambda s: None, snap=None).draw("long", 30845.0, 30763.5, 31008.0)
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
        Drawer({"ablaeufe": {}}, FakeGuard(), sleep=lambda s: None, snap=None).draw(
            "short", 1, 2, 3)


class FakeGuardIn(FakeGuard):
    def click_in(self, region, x, y, what, double=False):
        self.calls.append(("dclick_in" if double else "click_in", region, x, y))


CHART_RECT = [60, 80, 1500, 800]


def test_anker_box_an_kerze_doppelklick_daneben():
    steps = full_long().validate()
    # wie beim Nutzer: Doppelklick beim Vormachen 48 px neben dem Anlege-Klick
    steps[2]["punkt"] = [1248, 373]
    # Dialogfelder (900, 300..500) und OK (1000,700) liegen AUCH im Chart-Rechteck
    cfg = {"ablaeufe": {"long": steps}, "naechste_kerze": [900, 925], "chart": CHART_RECT}
    g = FakeGuardIn()
    Drawer(cfg, g, sleep=lambda s: None, snap=None).draw("long", 30845.0, 30763.5, 31008.0,
                                                         anchor=(1333, 555))
    assert g.calls[:3] == [("click", 700, 1010), ("click_in", "chart", 1333, 555),
                           ("dclick_in", "chart", 1345, 555)]
    assert ("click", 900, 300) in g.calls and ("click", 1000, 700) in g.calls


def test_anker_ohne_y_behaelt_aufgenommene_hoehe():
    cfg = {"ablaeufe": {"long": full_long().validate()}, "chart": CHART_RECT}
    g = FakeGuardIn()
    Drawer(cfg, g, sleep=lambda s: None, snap=None).draw("long", 1, 0, 3, anchor=(1333, None))
    assert g.calls[1:3] == [("click_in", "chart", 1333, 400), ("dclick_in", "chart", 1345, 400)]


def test_anchor_pair():
    from replaybot.draw import anchor_pair
    steps = full_long().validate()
    assert anchor_pair(steps, CHART_RECT) == (1, 2)
    assert anchor_pair(steps, None) == (None, None)


class Screen:
    """Fake-Bildschirm: Dialog geht nach dem Doppelklick auf (oder nicht), Felder zeigen,
    was getippt wurde (oder Müll)."""

    def __init__(self, guard, dialog_opens=True, field_text=None):
        self.guard, self.dialog_opens, self.field_text = guard, dialog_opens, field_text
        self.typed = []

    def snap(self, rect):
        np = pytest.importorskip("numpy")
        opened = self.dialog_opens and any(c[0] == "dclick_in" or c[0] == "dclick"
                                           for c in self.guard.calls)
        return np.full((rect[3], rect[2], 3), 200 if opened else 30, dtype=np.uint8)

    def read(self, img):
        typed = [c[2] for c in self.guard.calls if c[0] == "type"]
        if self.field_text is not None:
            return self.field_text(len(typed))
        return typed[-1] if typed else ""


def make_drawer(dialog_opens=True, field_text=None):
    cfg = {"ablaeufe": {"long": full_long().validate()}, "chart": CHART_RECT,
           "naechste_kerze": [900, 925]}
    g = FakeGuardIn()
    s = Screen(g, dialog_opens, field_text)
    t = [0.0]

    def sleep(sec):
        t[0] += sec
    dr = Drawer(cfg, g, sleep=sleep, snap=s.snap, field_reader=s.read, clock=lambda: t[0])
    return dr, g


def test_dialog_geht_nicht_auf_nichts_getippt():
    dr, g = make_drawer(dialog_opens=False)
    with pytest.raises(SafetyError, match="nicht aufgegangen"):
        dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert not any(c[0] == "type" for c in g.calls)
    assert g.calls[-1] == ("press", "esc")


def test_felder_werden_geprueft_alles_richtig():
    dr, g = make_drawer()
    dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert [c[2] for c in g.calls if c[0] == "type"] == ["30845,00", "31008,00", "30763,50"]


def test_falsche_zahl_wird_nochmal_getippt():
    # erstes Lesen nach dem 1. Tippen zeigt Müll, danach stimmt es
    dr, g = make_drawer(field_text=lambda n: "3084" if n == 1 else
                        ["30845,00", "30845,00", "31008,00", "30763,50"][n - 1])
    dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    typed = [c for c in g.calls if c[0] == "type"]
    assert [c[1] for c in typed] == ["entry", "entry (nochmal)", "ziel", "stop"]


def test_zweimal_falsch_bricht_ab():
    dr, g = make_drawer(field_text=lambda n: "12345")
    with pytest.raises(SafetyError, match="nach 2 Versuchen"):
        dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert g.calls[-1] == ("press", "esc")


def test_numbers_in():
    from replaybot.draw import numbers_in
    assert numbers_in("30.915,50") == [30915.5]
    assert numbers_in("30915.5") == [30915.5]
    assert numbers_in("Preis 30 915,50 USD") == [30915.5]
    assert numbers_in("") == []
