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
        ("press", "esc"), ("press", "esc"),
        ("click", 700, 1010), ("click", 1200, 400), ("dclick", 1200, 400),
        ("click", 900, 300), ("type", "entry", "30845,00"), ("press", "tab"),
        ("click", 900, 400), ("type", "ziel", "31008,00"), ("press", "tab"),
        ("click", 900, 500), ("type", "stop", "30763,50"), ("press", "tab"),
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
    assert g.calls[2:5] == [("click", 700, 1010), ("click_in", "chart", 1333, 555),
                           ("dclick_in", "chart", 1345, 555)]
    assert ("click", 900, 300) in g.calls and ("click", 1000, 700) in g.calls


def test_anker_ohne_y_behaelt_aufgenommene_hoehe():
    cfg = {"ablaeufe": {"long": full_long().validate()}, "chart": CHART_RECT}
    g = FakeGuardIn()
    Drawer(cfg, g, sleep=lambda s: None, snap=None).draw("long", 1, 0, 3, anchor=(1333, None))
    assert g.calls[3:5] == [("click_in", "chart", 1333, 400), ("dclick_in", "chart", 1345, 400)]


def test_anchor_pair():
    from replaybot.draw import anchor_pair
    steps = full_long().validate()
    assert anchor_pair(steps, CHART_RECT) == (1, 2)
    assert anchor_pair(steps, None) == (None, None)


class Screen:
    """Fake-Bildschirm: Dialog geht nach dem Doppelklick auf (oder nicht) und beim Klick auf
    OK (1000, 700) wieder zu; Felder zeigen, was getippt wurde (vorher den Standardwert)."""

    def __init__(self, guard, dialog_opens=True, field_text=None, ok_closes=True):
        self.guard, self.dialog_opens, self.field_text = guard, dialog_opens, field_text
        self.ok_closes = ok_closes

    def is_open(self):
        calls = self.guard.calls
        opened = self.dialog_opens and any(c[0] in ("dclick_in", "dclick") for c in calls)
        closed = self.ok_closes and ("click", 1000, 700) in calls
        return opened and not closed

    def snap(self, rect):
        np = pytest.importorskip("numpy")
        return np.full((rect[3], rect[2], 3), 200 if self.is_open() else 30, dtype=np.uint8)

    def read(self, img):
        if not self.is_open():
            return ""
        typed = [c[2] for c in self.guard.calls if c[0] == "type"]
        if self.field_text is not None:
            return self.field_text(len(typed))
        return typed[-1] if typed else "29000.00"


def make_drawer(dialog_opens=True, field_text=None, ok_closes=True):
    cfg = {"ablaeufe": {"long": full_long().validate()}, "chart": CHART_RECT,
           "naechste_kerze": [900, 925]}
    g = FakeGuardIn()
    s = Screen(g, dialog_opens, field_text, ok_closes)
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
    assert g.calls[-2:] == [("press", "esc"), ("press", "esc")]


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


def test_krummer_entry_wird_gerundet_und_trotzdem_bestaetigt():
    """Fall vom Nutzer: Entry 29419.125 -> getippt 29419,25, TradingView zeigt 29419.25."""
    dr, g = make_drawer(field_text=lambda n: ["29419.25", "29519.00", "29369.25"][n - 1])
    dr.draw("long", 29419.125, 29369.25, 29518.875, anchor=(1333, 555))
    typed = [c for c in g.calls if c[0] == "type"]
    assert [c[2] for c in typed] == ["29419,25", "29519,00", "29369,25"]


def test_esc_ohne_tradingview_vorne_wird_uebersprungen():
    """--zeichnen-test: am Anfang ist die Konsole vorne -> Aufräum-Esc still auslassen."""
    from replaybot.safety import SafetyError as SE

    class G(FakeGuardIn):
        def press(self, key, what):
            if "Start" in what:
                raise SE("Konsole vorne")
            super().press(key, what)
    cfg = {"ablaeufe": {"long": full_long().validate()}, "chart": CHART_RECT}
    g = G()
    Drawer(cfg, g, sleep=lambda s: None, snap=None).draw("long", 1, 0, 3, anchor=(1333, 555))
    assert g.calls[0] == ("click", 700, 1010)


def test_ok_nicht_getroffen_wird_erkannt():
    dr, g = make_drawer(ok_closes=False)
    with pytest.raises(SafetyError, match="OK wurde nicht getroffen"):
        dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))


def test_feld_vor_dem_tippen_unlesbar_wird_trotzdem_getippt():
    """Regression: OCR liest das frisch geöffnete Feld nicht -> trotzdem tippen."""
    saved = []
    dr, g = make_drawer(field_text=lambda n: "" if n == 0 else
                        ["30845,00", "31008,00", "30763,50"][n - 1])
    dr.save_img = lambda img, tag: saved.append(tag) or tag
    dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert [c[2] for c in g.calls if c[0] == "type"] == ["30845,00", "31008,00", "30763,50"]
    assert saved == ["zeichnen_vorher_entry"]


def test_felder_nie_lesbar_tippt_trotzdem_alles():
    dr, g = make_drawer(field_text=lambda n: "")
    dr.save_img = lambda img, tag: tag
    dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert [c[2] for c in g.calls if c[0] == "type"] == ["30845,00", "31008,00", "30763,50"]


def test_falsche_zahl_gibt_diagnosebild():
    saved = []
    dr, g = make_drawer(field_text=lambda n: "12345")
    dr.save_img = lambda img, tag: saved.append(tag) or tag
    with pytest.raises(SafetyError):
        dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert "zeichnen_falsch_30845.00" in saved


def test_fokus_klick_vorher_wird_nicht_zum_anlege_klick():
    from replaybot.draw import anchor_pair
    steps = full_long().validate()
    focus = {"punkt": [300, 300], "doppel": False, "tippe": None}   # Klick in den Chart zum Fokus
    steps = [focus] + steps
    assert anchor_pair(steps, CHART_RECT) == (2, 3)


class WhiteScreen(Screen):
    """Weißer Dialog auf weißem Chart: es ändern sich nur Text/Rahmen (ca. 'share' der Pixel)."""

    def __init__(self, guard, share, **kw):
        super().__init__(guard, **kw)
        self.share = share

    def snap(self, rect):
        np = pytest.importorskip("numpy")
        img = np.full((rect[3], rect[2], 3), 255, dtype=np.uint8)
        if self.is_open():
            n = int(img.shape[0] * img.shape[1] * self.share)
            flat = img.reshape(-1, 3)
            flat[:n:1] = 0
        return img


def make_white(share, **kw):
    cfg = {"ablaeufe": {"long": full_long().validate()}, "chart": CHART_RECT,
           "naechste_kerze": [900, 925], "parkplatz": [900, 925], "dialog_wartezeit": 1.0}
    g = FakeGuardIn()
    s = WhiteScreen(g, share, **kw)
    t = [0.0]

    def sleep(sec):
        t[0] += sec
    dr = Drawer(cfg, g, sleep=sleep, snap=s.snap, field_reader=s.read, clock=lambda: t[0])
    dr.save_img = lambda img, tag: tag
    return dr, g


def test_weisser_dialog_auf_weissem_chart_wird_erkannt():
    dr, g = make_white(0.05)           # nur 5 % der Pixel ändern sich
    dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert [c[2] for c in g.calls if c[0] == "type"] == ["30845,00", "31008,00", "30763,50"]


def test_schwach_erkannt_und_zahl_steht_im_feld_laeuft_durch():
    dr, g = make_white(0.01)           # 1 %: nur "schwach"
    dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert len([c for c in g.calls if c[0] == "type"]) == 3


def test_schwach_erkannt_aber_zahl_nicht_im_feld_bricht_ab():
    dr, g = make_white(0.01, field_text=lambda n: "")
    with pytest.raises(SafetyError, match="schwach"):
        dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert len([c for c in g.calls if c[0] == "type"]) == 1    # nur der erste Versuch


def test_gar_keine_veraenderung_speichert_diagnosebilder():
    saved = []
    dr, g = make_white(0.0)
    dr.save_img = lambda img, tag: saved.append(tag) or tag
    with pytest.raises(SafetyError, match="nicht aufgegangen"):
        dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert saved == ["zeichnen_dialog_vorher", "zeichnen_dialog_nachher"]
    assert not any(c[0] == "type" for c in g.calls)


def test_zahl_neben_ticks_und_symbol_wird_getrennt_gelesen():
    from importlib import import_module
    mod = import_module("replaybot.draw")
    assert 30089.25 in mod.numbers_loose("30089.25 245 Ticks")
    assert 30089.25 in mod.numbers_loose("30089.25 245")
    assert 30189.25 in mod.numbers_loose("30189.25 ~ 345 Ticks")
    assert 30915.5 in mod.numbers_loose("Preis 30 915,50 USD")
    # Verschmelzung bleibt bei numbers_in wie gehabt (nur loose liefert die Einzelteile)


def test_feld_mit_ticks_daneben_gilt_als_richtig():
    dr, g = make_drawer(field_text=lambda n: ["30845.00 11955098 Ticks", "31008.00 245 Ticks",
                                              "30763.50 245"][n - 1])
    dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert len([c for c in g.calls if c[0] == "type"]) == 3       # kein Nachtippen nötig
