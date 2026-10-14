"""Ende-zu-Ende: nachgebaute TradingView-Legende -> Tesseract -> Zahlen.
Wird übersprungen, wenn Tesseract/OpenCV/Pillow fehlen."""
import shutil
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")
pytest.importorskip("pytesseract")
Image = pytest.importorskip("PIL.Image")
from PIL import ImageDraw, ImageFont  # noqa: E402

from replaybot.ocr import read_ohlc  # noqa: E402

FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", r"C:\Windows\Fonts\arial.ttf"]
FONT = next((f for f in FONTS if Path(f).exists()), None)
pytestmark = [
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract nicht im PATH"),
    pytest.mark.skipif(FONT is None, reason="keine Schrift zum Rendern"),
]


def de(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render(o, h, l, c, size=13, dark=False):
    font = ImageFont.truetype(FONT, size)
    bg = (19, 23, 34) if dark else (255, 255, 255)
    val = (41, 98, 255) if c >= o else ((220, 220, 220) if dark else (0, 0, 0))
    lab = (120, 123, 134)
    img = Image.new("RGB", (520, size + 12), bg)
    d = ImageDraw.Draw(img)
    x = 4
    sign = "+" if c >= o else "−"
    parts = [("O", lab), (de(o), val), (" H", lab), (de(h), val), (" L", lab), (de(l), val),
             (" C", lab), (de(c), val), (f" {sign}{de(abs(c - o))}", val)]
    for text, col in parts:
        d.text((x, 4), text, font=font, fill=col)
        x += d.textlength(text, font=font)
    return np.array(img)[:, :, ::-1].copy()


@pytest.mark.parametrize("ohlc", [
    (30877.0, 30888.75, 30847.5, 30874.25),
    (28962.25, 29045.75, 28878.75, 29032.0),
    (30819.0, 30852.0, 30767.5, 30848.75),
])
@pytest.mark.parametrize("size", [11, 13, 15])
@pytest.mark.parametrize("dark", [False, True])
def test_legende_lesen(ohlc, size, dark):
    vals, text = read_ohlc(render(*ohlc, size=size, dark=dark))
    assert vals == pytest.approx(ohlc), text


def render_axis(center, ppp, dark=False, cur=None, h=800, w=70):
    """Nachgebaute Preisachse (wie test_chartnav.AXIS: oben bei y=80, 800 px hoch)."""
    from test_chartnav import labels_for
    font = ImageFont.truetype(FONT, 11)
    bg = (19, 23, 34) if dark else (255, 255, 255)
    fg = (178, 181, 190) if dark else (19, 23, 34)
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    for y, p in labels_for(center, ppp):
        d.text((6, y - 80 - 7), de(p), font=font, fill=fg)
    if cur:
        yy = h / 2 - (cur - center) / ppp
        d.rectangle((0, yy - 9, w, yy + 9), fill=(41, 98, 255))
        d.text((6, yy - 7), de(cur), font=font, fill=(255, 255, 255))
    return np.array(img)[:, :, ::-1].copy()


@pytest.mark.parametrize("ppp", [0.25, 0.6, 1.5])
@pytest.mark.parametrize("dark", [False, True])
def test_preisachse_lesen(ppp, dark, monkeypatch):
    from replaybot import chartnav, ocr
    monkeypatch.setattr(ocr, "grab", lambda rect: render_axis(30868.0, ppp, dark, cur=30868.25))
    a, b = chartnav.fit_scale(chartnav.read_axis_labels([1600, 80, 70, 800]))
    assert a == pytest.approx(-ppp, rel=0.01)
    assert a * 480 + b == pytest.approx(30868.0, abs=2)
