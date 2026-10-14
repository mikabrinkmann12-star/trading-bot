import pytest

np = pytest.importorskip("numpy")

from livebot.candlefind import (bar_spacing, candle_candidates,  # noqa: E402
                                  exclusion_zones, find_last_candle_x, legend_zone,
                                  locate_current_candle, same_open)

BLUE = (255, 98, 41)      # BGR von #2962FF
BLACK = (0, 0, 0)
SHADE = (255, 238, 230)   # hellblauer Sitzungs-Hintergrund (BGR)
WHITE = (255, 255, 255)
CHART = (60, 80, 1000, 600)   # left, top, w, h auf dem Bildschirm


def chart_img(candles, shade_until=700, dotted_y=300, legend=True, botwin=None):
    """candles: Liste (x_mitte, y_oben, y_unten, körper_oben, körper_unten, farbe)."""
    w, h = CHART[2], CHART[3]
    img = np.full((h, w, 3), WHITE, dtype=np.uint8)
    img[:, :shade_until] = SHADE
    for x, top, bot, btop, bbot, col in candles:
        img[top:bot, x] = col                         # Docht
        img[btop:bbot, x - 4:x + 5] = col             # Körper 9 px
    img[dotted_y, ::4] = BLACK                        # gepunktete Kurslinie
    if legend:                                         # blauer/schwarzer Legenden-Text oben links
        img[12:24, 30:300:3] = BLUE
        img[45:60, 10:90] = BLUE                       # KAUF-Button
    if botwin:
        x1, y1, x2, y2 = botwin
        img[y1:y2, x1:x2] = (240, 240, 240)
        img[y1 + 10:y1 + 22, x1 + 10:x2 - 10:5] = BLACK  # schwarze Buchstaben (senkrechte Striche)
    return img


CANDLES = [(100 + 20 * i, 200 + i, 320 + i, 230 + i, 290 + i, BLUE if i % 2 else BLACK)
           for i in range(30)]       # letzte Kerze bei x = 100 + 20*29 = 680
LEGEND = (60 + 25, 80 + 8, 300, 20)


def test_letzte_kerze():
    img = chart_img(CANDLES)
    x = find_last_candle_x(img, origin=CHART[:2], exclude=[legend_zone(LEGEND, CHART)])
    assert x == CHART[0] + 680


def test_bot_fenster_und_kurslinie_werden_ignoriert():
    win_local = (850, 350, 1000, 600)
    img = chart_img(CANDLES, botwin=win_local)
    win_screen = (CHART[0] + 850 - 10, CHART[1] + 350 - 40, 170, 300)
    x = find_last_candle_x(img, origin=CHART[:2],
                           exclude=[legend_zone(LEGEND, CHART), win_screen])
    assert x == CHART[0] + 680


def test_ohne_ausblenden_wuerde_bot_fenster_stoeren():
    img = chart_img(CANDLES, botwin=(850, 350, 1000, 600))
    assert find_last_candle_x(img, origin=CHART[:2]) != CHART[0] + 680


def test_doji_wird_gefunden():
    doji = CANDLES + [(720, 250, 270, 260, 261, BLACK)]   # 1 px Körper, 20 px Docht
    img = chart_img(doji)
    assert find_last_candle_x(img, origin=CHART[:2],
                              exclude=[legend_zone(LEGEND, CHART)]) == CHART[0] + 720


def test_leerer_chart():
    img = chart_img([], legend=False)
    assert find_last_candle_x(img, origin=CHART[:2]) is None


def axis_text(img, x_local=960):
    """Schwarze Zahlen der Preisachse ganz rechts im Bild (senkrechte Striche, 9 px hoch)."""
    for y in range(40, 560, 40):
        img[y:y + 9, x_local:x_local + 30:3] = BLACK
    return img


AXIS = (CHART[0] + 950, CHART[1], 60, CHART[3])
CFG = {"chart": CHART, "legende": LEGEND, "preisachse": AXIS}


class FakeTV:
    """Hover-Legende wie in TradingView: über einer Kerze deren Werte, sonst (leere Fläche,
    Preisachse) die Werte der letzten Kerze."""

    def __init__(self, img, xs):
        self.img, self.xs, self.x = img, xs, 0

    def vals(self, i):
        return (float(i), float(i) + 1, float(i) - 1, float(i) + 0.5)

    def grab(self, rect):
        return self.img if tuple(rect) == CHART else "legende"

    def read(self, _img):
        near = min(range(len(self.xs)), key=lambda i: abs(self.xs[i] - self.x))
        if abs(self.xs[near] - self.x) <= 8:
            return self.vals(near), ""
        return self.vals(len(self.xs) - 1), ""

    def move(self, x, y):
        self.x = x


def test_preisachse_ist_keine_kerze():
    img = axis_text(chart_img(CANDLES))
    assert find_last_candle_x(img, origin=CHART[:2]) > CHART[0] + 950    # ohne Ausblenden: Achse
    cands = candle_candidates(img, origin=CHART[:2], exclude=exclusion_zones(CFG))
    assert cands[0] == CHART[0] + 680
    assert bar_spacing(cands) == 20


def test_gegenprobe_verwirft_falschen_kandidaten():
    """Auch wenn ein falscher Kandidat rechts liegt (hier: nicht ausgeblendete Achse), wird er
    verworfen, weil links daneben nicht die vorherige Kerze kommt."""
    img = axis_text(chart_img(CANDLES))
    xs = [CHART[0] + 100 + 20 * i for i in range(30)]
    tv = FakeTV(img, xs)
    cfg = {"chart": CHART, "legende": LEGEND}          # ohne Preisachse -> Achse ist Kandidat
    x, why = locate_current_candle(cfg, tv.vals(29), tv.vals(28), grab=tv.grab,
                                   read_ohlc=tv.read, move=tv.move, sleep=lambda s: None)
    assert x == CHART[0] + 680 and why == ""


def test_gegenprobe_ohne_vorherige_kerze():
    img = chart_img(CANDLES)
    xs = [CHART[0] + 100 + 20 * i for i in range(30)]
    tv = FakeTV(img, xs)
    x, _ = locate_current_candle(CFG, tv.vals(29), None, grab=tv.grab, read_ohlc=tv.read,
                                 move=tv.move, sleep=lambda s: None)
    assert x == CHART[0] + 680


def test_gegenprobe_scheitert():
    img = chart_img(CANDLES)
    x, why = locate_current_candle(
        CFG, (1.0, 2.0, 0.5, 1.5), None, grab=lambda r: img if tuple(r) == CHART else None,
        read_ohlc=lambda i: (None, ""), move=lambda x, y: None, sleep=lambda s: None)
    assert x is None and "Legende" in why


def test_waagerechte_level_linie_verschmiert_kerze_nicht():
    img = chart_img(CANDLES)
    img[250:252, :] = BLUE          # 2 px dicke blaue Level-Linie quer durch alle Kerzen
    cands = candle_candidates(img, origin=CHART[:2], exclude=exclusion_zones(CFG))
    assert cands[0] == CHART[0] + 680
    assert cands[1] == CHART[0] + 660


def test_vorherige_kerze_doji_wird_trotzdem_bestaetigt():
    """Die vorletzte Kerze ist so flach, dass sie kein Kandidat ist -> Gegenprobe nutzt den
    typischen Abstand."""
    candles = [c for c in CANDLES if c[0] != 660] + [(660, 260, 262, 261, 262, BLACK)]
    img = chart_img(candles)
    xs = [CHART[0] + 100 + 20 * i for i in range(30)]
    tv = FakeTV(img, xs)
    x, why = locate_current_candle(CFG, tv.vals(29), tv.vals(28), grab=tv.grab,
                                   read_ohlc=tv.read, move=tv.move, sleep=lambda s: None)
    assert x == CHART[0] + 680, why


class TickingTV(FakeTV):
    """Die letzte Kerze entsteht noch: jede Lesung hat ein anderes Hoch/Close."""

    def __init__(self, img, xs):
        super().__init__(img, xs)
        self.n = 0

    def read(self, img):
        vals, text = super().read(img)
        if vals == self.vals(len(self.xs) - 1):
            self.n += 1
            vals = (vals[0], vals[1] + self.n, vals[2], vals[3] + self.n * 0.25)
        return vals, text


def test_entstehende_kerze_nur_ueber_open_gefunden():
    """--zeichnen-test: die gelesene Kerze ist die ENTSTEHENDE - H/C ändern sich beim Hovern."""
    img = chart_img(CANDLES)
    xs = [CHART[0] + 100 + 20 * i for i in range(30)]
    tv = TickingTV(img, xs)
    current = tv.read("legende")[0]
    x, _ = locate_current_candle(CFG, current, None, grab=tv.grab, read_ohlc=tv.read,
                                 move=tv.move, sleep=lambda s: None)
    assert x is None                                   # voller Vergleich scheitert
    x, why = locate_current_candle(CFG, current, None, grab=tv.grab, read_ohlc=tv.read,
                                   move=tv.move, sleep=lambda s: None, same=same_open)
    assert x == CHART[0] + 680, why
