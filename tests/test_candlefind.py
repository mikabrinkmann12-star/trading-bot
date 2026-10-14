import pytest

np = pytest.importorskip("numpy")

from replaybot.candlefind import (find_last_candle_x, legend_zone,  # noqa: E402
                                  locate_current_candle)

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


def test_gegenprobe_schiebt_nach_rechts():
    """Bilderkennung trifft 4 px zu weit links - Legende passt erst bei +4."""
    img = chart_img(CANDLES)
    target = CHART[0] + 684
    pos = {"x": 0}

    def grab(rect):
        return img if rect == list(CHART) or rect == CHART else "legende"

    def read(_img):
        return ((1.0, 2.0, 0.5, 1.5) if pos["x"] >= target else (9.0, 9.0, 9.0, 9.0)), ""

    def move(x, y):
        pos["x"] = x
    cfg = {"chart": CHART, "legende": LEGEND}
    x, why = locate_current_candle(cfg, (1.0, 2.0, 0.5, 1.5), grab=grab, read_ohlc=read,
                                   move=move, sleep=lambda s: None)
    assert x == target and why == ""


def test_gegenprobe_scheitert():
    img = chart_img(CANDLES)
    cfg = {"chart": CHART, "legende": LEGEND}
    x, why = locate_current_candle(
        cfg, (1.0, 2.0, 0.5, 1.5), grab=lambda r: img if r == CHART else None,
        read_ohlc=lambda i: (None, ""), move=lambda x, y: None, sleep=lambda s: None)
    assert x is None and "Legende" in why
