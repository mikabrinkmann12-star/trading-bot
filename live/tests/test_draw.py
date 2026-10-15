import pytest

from livebot.draw import Drawer, format_price
from livebot.safety import SafetyError
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
    cfg = {"ablaeufe": {"long": full_long().validate()}, "parkplatz": [900, 925]}
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
    cfg = {"ablaeufe": {"long": steps}, "parkplatz": [900, 925], "chart": CHART_RECT}
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
    from livebot.draw import anchor_pair
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
           "parkplatz": [900, 925]}
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
    with pytest.raises(SafetyError, match="nicht sicher"):
        dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert g.calls[-1] == ("press", "esc")


def test_numbers_in():
    from livebot.draw import numbers_in
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
    from livebot.safety import SafetyError as SE

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
    with pytest.raises(SafetyError, match="OK wurde evtl. nicht getroffen"):
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
    from livebot.draw import anchor_pair
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
    dr, g = make_white(0.0, dialog_opens=False)
    dr.save_img = lambda img, tag: saved.append(tag) or tag
    with pytest.raises(SafetyError, match="nicht aufgegangen"):
        dr.draw("long", 30845.0, 30763.5, 31008.0, anchor=(1333, 555))
    assert saved == ["zeichnen_dialog_vorher", "zeichnen_dialog_nachher"]
    assert not any(c[0] == "type" for c in g.calls)


def test_play_mit_punkt_als_dezimalzeichen():
    dr, g = make_drawer()
    dr.cfg["ablaeufe"]["kaufen"] = [
        {"punkt": [900, 300], "doppel": False, "tippe": "ziel"},
        {"punkt": [900, 400], "doppel": False, "tippe": "stop"}]
    dr.snap = None
    dr.play("kaufen", {"ziel": 30189.25, "stop": 30089.25}, decimal=".")
    assert [c[2] for c in g.calls if c[0] == "type"] == ["30189.25", "30089.25"]


def test_zahl_neben_ticks_und_symbol_wird_getrennt_gelesen():
    from importlib import import_module
    mod = import_module("livebot.draw")
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


def order_drawer(field_text=None, toggle_on_before=False, grey_readable=True, grey_ink=170,
                 stray_to=None):
    """Bestellfenster: Kauf-Knopf (100,100) öffnet, Menge (900,300), TP-Schalter (950,350),
    TP-Feld (900,400), SL-Schalter (950,450), SL-Feld (900,500), Bestätigen (1000,700),
    X (1100,100). Schalter: aufgenommen als 'aus -> an'.
    Gesperrtes Feld (Schalter aus): Schrift blass (grey_ink), Tippen wirkt nicht (oder landet
    mit stray_to im falschen Feld). grey_readable=False: blasse Schrift ist für OCR unlesbar."""
    steps = [{"punkt": [100, 100], "doppel": False, "tippe": None},
             {"punkt": [900, 300], "doppel": False, "tippe": "menge"},
             {"punkt": [950, 350], "doppel": False, "tippe": None},
             {"punkt": [900, 400], "doppel": False, "tippe": "ziel"},
             {"punkt": [950, 450], "doppel": False, "tippe": None},
             {"punkt": [900, 500], "doppel": False, "tippe": "stop"},
             {"punkt": [1000, 700], "doppel": False, "tippe": None},
             {"punkt": [1100, 100], "doppel": False, "tippe": None}]
    cfg = {"ablaeufe": {"kaufen": steps}, "chart": CHART_RECT}
    g = FakeGuardIn()
    state = {"tp": toggle_on_before, "sl": toggle_on_before, "fields": {}, "focus": None,
             "open": False}
    slept = []

    def click(x, y, what, double=False):
        g.calls.append(("click", x, y))
        if (x, y) == (100, 100):
            state["open"] = True
        elif (x, y) == (950, 350):
            state["tp"] = not state["tp"]
        elif (x, y) == (950, 450):
            state["sl"] = not state["sl"]
        elif (x, y) == (1100, 100):
            state["open"] = False
        state["focus"] = (x, y)

    fields = ((900, 300), (900, 400), (900, 500))

    def enabled(f):
        return f == (900, 300) or (f == (900, 400) and state["tp"]) or (
            f == (900, 500) and state["sl"])

    def type_text(text, what):
        g.calls.append(("type", what, text))
        f = state["focus"]
        if f in fields and not enabled(f):           # Feld gesperrt (Schalter aus)
            if stray_to:
                state["fields"][stray_to] = text      # Tipper landet im falschen Feld
            return
        state["fields"][f] = text

    g.click = click
    g.type_text = type_text
    np = pytest.importorskip("numpy")
    shown = {}

    def snap(rect):
        center = (rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)
        if center in fields and rect[2] == 220:
            img = np.full((rect[3], rect[2], 3), 255, dtype=np.uint8)
            img[rect[3] // 2 - 6: rect[3] // 2 + 6, 20:120:3] = 0 if enabled(center) else grey_ink
            shown[id(img)] = (center, enabled(center))
            return img
        return np.full((rect[3], rect[2], 3), 200 if state["open"] else 30, dtype=np.uint8)

    def read(img):
        f, en = shown.get(id(img), (None, True))
        if f is None or (not en and not grey_readable):
            return ""
        return state["fields"].get(f, "1" if f == (900, 300) else "28000.00")

    t = [0.0]

    def sleep(s):
        slept.append(s)
        t[0] += s
    dr = Drawer(cfg, g, sleep=sleep, snap=snap, field_reader=field_text or read,
                clock=lambda: t[0])
    dr.save_img = lambda img, tag: tag
    return dr, g, state, slept


def test_order_wartet_nach_bestaetigen_vor_dem_x():
    dr, g, state, slept = order_drawer()
    dr.play("kaufen", {"menge": 1, "ziel": 30189.25, "stop": 30089.25}, final_esc=False,
            decimal=".", close_check="off", strict=("ziel", "stop"), confirm_pause=2.5)
    clicks = [c for c in g.calls if c[0] == "click"]
    i_ok = clicks.index(("click", 1000, 700))
    assert clicks[i_ok + 1] == ("click", 1100, 100)          # danach das X
    assert 2.5 in slept
    assert state["fields"][(900, 400)] == "30189.25" and state["fields"][(900, 500)] == "30089.25"


def test_schalter_schon_an_wird_wieder_eingeschaltet():
    """TP/SL waren von der letzten Order noch AN -> aufgenommener Klick schaltet sie AUS ->
    Bot merkt, dass die Zahl nicht übernommen wurde, schaltet wieder an und tippt neu."""
    dr, g, state, slept = order_drawer(toggle_on_before=True)
    dr.play("kaufen", {"menge": 1, "ziel": 30189.25, "stop": 30089.25}, final_esc=False,
            decimal=".", close_check="off", strict=("ziel", "stop"), confirm_pause=2.5)
    assert state["tp"] and state["sl"]
    assert state["fields"][(900, 400)] == "30189.25" and state["fields"][(900, 500)] == "30089.25"
    assert ("click", 1000, 700) in g.calls                   # erst dann bestätigt


def test_tp_unlesbar_wird_nicht_bestaetigt():
    dr, g, state, slept = order_drawer(field_text=lambda img: "")
    with pytest.raises(SafetyError, match="NICHT bestätigt"):
        dr.play("kaufen", {"menge": 1, "ziel": 30189.25, "stop": 30089.25}, final_esc=False,
                decimal=".", close_check="off", strict=("ziel", "stop"), confirm_pause=2.5)
    assert ("click", 1000, 700) not in g.calls               # KEINE Order ohne sicheres TP


def test_bestellfenster_schon_offen_geht_trotzdem():
    dr, g, state, slept = order_drawer()
    state["open"] = True                                      # Fenster steht schon offen
    dr.play("kaufen", {"menge": 1, "ziel": 30189.25, "stop": 30089.25}, final_esc=False,
            decimal=".", close_check="off", strict=("ziel", "stop"), confirm_pause=2.5)
    assert ("click", 1000, 700) in g.calls


def test_offenes_bestellfenster_menge_unlesbar_geht_weiter():
    """Bestellfenster stand schon offen; die '1' in Menge ist (wie beim Nutzer) nicht lesbar
    -> trotzdem weiter, TP/SL werden streng geprüft."""
    dr, g, state, slept = order_drawer()
    state["open"] = True
    base_read = dr.field_reader

    def read(img):
        return "" if state["focus"] == (900, 300) and any(
            c[0] == "type" for c in g.calls) else base_read(img)
    dr.field_reader = read
    dr.play("kaufen", {"menge": 1, "ziel": 30189.25, "stop": 30089.25}, final_esc=False,
            decimal=".", close_check="off", strict=("ziel", "stop"), confirm_pause=2.5)
    assert ("click", 1000, 700) in g.calls


ORDER = {"menge": 1, "ziel": 30189.25, "stop": 30089.25}
ORDER_KW = dict(final_esc=False, decimal=".", close_check="off", strict=("ziel", "stop"),
                confirm_pause=2.5)


def test_schalter_an_und_blasses_feld_unlesbar_wird_trotzdem_korrigiert():
    """Wie oben, aber das gesperrte (blasse) Feld ist für die OCR gar nicht lesbar."""
    dr, g, state, slept = order_drawer(toggle_on_before=True, grey_readable=False)
    dr.play("kaufen", ORDER, **ORDER_KW)
    assert state["tp"] and state["sl"]
    assert state["fields"][(900, 400)] == "30189.25" and state["fields"][(900, 500)] == "30089.25"
    assert ("click", 1000, 700) in g.calls


def test_zahl_nur_falsch_gelesen_schalter_wird_zurueckgeschaltet():
    """Schalter war richtig (AN), nur die OCR hat sich einmal verlesen -> der Bot schaltet um,
    merkt, dass das Feld blasser (gesperrt) wird, und schaltet sofort zurück."""
    dr, g, state, slept = order_drawer()
    base, n = dr.field_reader, [0]

    def read(img):
        text = base(img)
        if text == "30189.25" and n[0] == 0:
            n[0] += 1
            return "30189.75"                                 # einmal verlesen
        return text
    dr.field_reader = read
    dr.play("kaufen", ORDER, **ORDER_KW)
    assert state["tp"] and state["sl"]                        # TP ist AN geblieben
    assert g.calls.count(("click", 950, 350)) == 3            # an, um, zurück
    assert ("click", 1000, 700) in g.calls


def test_gesperrtes_feld_mit_alter_richtiger_zahl_wird_nicht_bestaetigt():
    """Schlimmster Fall: Blässe nicht messbar (grey_ink=0), Bot schaltet TP versehentlich AUS,
    im gesperrten Feld steht noch die richtige Zahl -> darf NICHT als Erfolg gelten."""
    dr, g, state, slept = order_drawer(grey_ink=0)
    base, n = dr.field_reader, [0]

    def read(img):
        text = base(img)
        if text == "30189.25" and n[0] == 0:
            n[0] += 1
            return "30189.75"
        return text
    dr.field_reader = read
    with pytest.raises(SafetyError, match="NICHT bestätigt"):
        dr.play("kaufen", ORDER, **ORDER_KW)
    assert ("click", 1000, 700) not in g.calls                # keine Order ohne TP


def test_verstellte_menge_wird_vor_dem_bestaetigen_erkannt():
    """Tippen in ein gesperrtes Feld landet in der Menge -> letzte Kontrolle stoppt."""
    dr, g, state, slept = order_drawer(toggle_on_before=True, stray_to=(900, 300))
    with pytest.raises(SafetyError, match="Letzte Kontrolle.*menge"):
        dr.play("kaufen", ORDER, **ORDER_KW)
    assert ("click", 1000, 700) not in g.calls


def test_ink_contrast_blass_gegen_kraeftig():
    np = pytest.importorskip("numpy")
    from livebot.draw import ink_contrast
    strong = np.full((32, 220, 3), 255, dtype=np.uint8)
    pale = strong.copy()
    strong[10:22, 20:120:3] = 0
    pale[10:22, 20:120:3] = 170
    assert ink_contrast(strong) > ink_contrast(pale) / 0.75
    assert ink_contrast(np.full((32, 220, 3), 255, dtype=np.uint8)) == 0.0


def test_pure_ints_und_tight_part():
    from livebot.draw import pure_ints, tight_part
    assert pure_ints("730,00 1 | 930,00 # 1") == [1, 1]
    assert pure_ints("930,00 | 730,004") == []
    assert tight_part("a | b # 1") == "1" and tight_part("nur voll") is None


def _menge_ok(text):
    dr, g = make_drawer(field_text=lambda n: "")
    dr.field_reader = lambda img: text
    dr.snap = lambda rect: object()
    return dr._field_ok(10, 10, 1.0, integer=True)


def test_menge_ganzzahl_modus():
    assert _menge_ok("730,00 1 # 1") is True                  # '1' sicher gelesen
    assert _menge_ok("930,00 | 730,004 # ") is None           # nur Müll von außerhalb -> unlesbar
    assert _menge_ok("930,00 | 730,004") is False             # ohne '#' zählt alles als Feld
    assert _menge_ok("930,00 # 3") is False                   # im Feld steht eine 3
    assert _menge_ok("30189.25 # 30189.25") is False          # Preis verirrt sich ins Mengenfeld


def test_breakeven_fenster_bleibt_offen_bricht_ab_und_schliesst_mit_esc():
    steps = [{"punkt": [100, 100], "doppel": False, "tippe": None},
             {"punkt": [900, 300], "doppel": False, "tippe": "entry"},
             {"punkt": [1000, 700], "doppel": False, "tippe": None}]
    cfg = {"ablaeufe": {"breakeven": steps}, "chart": CHART_RECT}
    g = FakeGuardIn()
    state = {"open": False}
    orig_click = g.click

    def click(x, y, what, double=False):
        orig_click(x, y, what, double)
        if (x, y) == (100, 100):
            state["open"] = True                      # öffnet; OK (1000,700) schließt NICHT

    g.click = click
    np = pytest.importorskip("numpy")
    dr = Drawer(cfg, g, sleep=lambda s: None,
                snap=lambda rect: np.full((rect[3], rect[2], 3), 200 if state["open"] else 30,
                                          dtype=np.uint8),
                field_reader=lambda img: "29000.00", clock=iter(range(0, 10000, 1)).__next__)
    dr.save_img = lambda img, tag: tag
    with pytest.raises(SafetyError, match="abgelehnt"):
        dr.play("breakeven", {"entry": 29000.0}, final_esc=False, close_check="fatal",
                strict=("entry",))
    ok_i = g.calls.index(("click", 1000, 700))
    after = [c for c in g.calls[ok_i:] if c == ("press", "esc")]
    assert len(after) == 2                               # Esc zweimal: Fenster wird geschlossen


def test_label_kind():
    from livebot.draw import label_kind
    assert label_kind("Take Profit Preis") == "take"
    assert label_kind("Take-Profit Preis | Take Profit") == "take"
    assert label_kind("Stop-Loss Preis") == "stop"
    assert label_kind("Stop Loss") == "stop"
    assert label_kind("xyz") is None and label_kind("") is None
    assert label_kind("Stop Loss Take Profit") is None          # beides: unklar


LABELS = {(900, 400): "Take Profit Preis", (900, 500): "Stop-Loss Preis"}


def _order_with_labels(labels):
    dr, g, state, slept = order_drawer()
    dr.label_reader = lambda img: labels.get(state["focus"], "")
    return dr, g, state


def test_beschriftung_stimmt_order_laeuft_durch():
    dr, g, state = _order_with_labels(LABELS)
    dr.play("kaufen", ORDER, **ORDER_KW)
    assert ("click", 1000, 700) in g.calls


def test_beschriftung_vertauscht_nichts_getippt_nicht_bestaetigt():
    # über dem 'ziel'-Feld steht Stop-Loss -> Ablauf passt nicht zum Fenster
    dr, g, state = _order_with_labels({(900, 400): "Stop-Loss Preis", (900, 500): "Take Profit Preis"})
    with pytest.raises(SafetyError, match="Über dem Feld 'ziel' steht Stop-Loss"):
        dr.play("kaufen", ORDER, **ORDER_KW)
    assert ("click", 1000, 700) not in g.calls
    assert [c for c in g.calls if c[0] == "type" and "ziel" in c[1]] == []   # nichts ins Feld getippt


def test_beschriftung_unlesbar_laeuft_weiter():
    dr, g, state = _order_with_labels({})
    dr.play("kaufen", ORDER, **ORDER_KW)
    assert ("click", 1000, 700) in g.calls


def test_breakeven_feld_mit_take_profit_beschriftung_wird_abgelehnt():
    """Der echte Fall des Nutzers: das aufgenommene 'entry'-Feld ist das Take-Profit-Feld."""
    steps = [{"punkt": [100, 100], "doppel": False, "tippe": None},
             {"punkt": [900, 300], "doppel": False, "tippe": "entry"},
             {"punkt": [1000, 700], "doppel": False, "tippe": None}]
    g = FakeGuardIn()
    np = pytest.importorskip("numpy")
    dr = Drawer({"ablaeufe": {"breakeven": steps}, "chart": CHART_RECT}, g, sleep=lambda s: None,
                snap=lambda rect: np.full((rect[3], rect[2], 3), 30, dtype=np.uint8),
                field_reader=lambda img: "29000.00", clock=iter(range(0, 10000)).__next__,
                label_reader=lambda img: "Take Profit Preis")
    dr.save_img = lambda img, tag: tag
    with pytest.raises(SafetyError, match="Take-Profit, erwartet wird Stop-Loss"):
        dr.play("breakeven", {"entry": 29000.0}, final_esc=False, close_check="fatal",
                strict=("entry",))
    assert [c for c in g.calls if c[0] == "type"] == []
    assert ("click", 1000, 700) not in g.calls


def test_esc_wird_uebersprungen_wenn_tradingview_nicht_vorne_ist():
    """Beim Aktions-Test ist zuerst das schwarze Fenster vorne: kein 'VERWEIGERT' im Log,
    sondern stilles Überspringen."""
    g = FakeGuardIn()
    g.tv_in_front = lambda: False
    logs = []
    dr = Drawer({}, g, sleep=lambda s: None, snap=None, field_reader=None)
    dr.log = logs.append
    dr._close_dialogs("offene Dialoge schließen (Start)")
    assert [c for c in g.calls if c[0] == "press"] == []
    assert any("übersprungen" in line for line in logs)
    g.tv_in_front = lambda: True
    dr._close_dialogs("x")
    assert [c for c in g.calls if c[0] == "press"] == [("press", "esc"), ("press", "esc")]
