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

from livebot.ocr import read_ohlc  # noqa: E402

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
    from livebot import chartnav, ocr
    monkeypatch.setattr(ocr, "grab", lambda rect: render_axis(30868.0, ppp, dark, cur=30868.25))
    a, b = chartnav.fit_scale(chartnav.read_axis_labels([1600, 80, 70, 800]))
    assert a == pytest.approx(-ppp, rel=0.01)
    assert a * 480 + b == pytest.approx(30868.0, abs=2)


@pytest.mark.parametrize("value", ["28962,25", "30915,50", "31008,00"])
def test_eingabefeld_mit_rahmen_lesen(value):
    """Wie ein Feld im TradingView-Dialog nach Tab: grauer Hintergrund, weißes Feld mit
    Rahmen, kein Cursor mehr."""
    from livebot.draw import _default_field_reader, numbers_in
    font = ImageFont.truetype(FONT, 13)
    img = Image.new("RGB", (220, 32), (217, 217, 217))
    d = ImageDraw.Draw(img)
    d.rectangle((60, 4, 210, 28), fill=(255, 255, 255), outline=(0, 0, 0))
    d.text((64, 8), value, font=font, fill=(0, 0, 0))
    text = _default_field_reader(np.array(img)[:, :, ::-1].copy())
    nums = numbers_in(text)
    assert nums and all(n == pytest.approx(float(value.replace(",", "."))) for n in nums), text


@pytest.mark.parametrize("value", ["1", "2", "7", "10", "1.5", "29053.50"])
@pytest.mark.parametrize("dark", [False, True])
def test_kleine_zahl_im_feld_lesen(value, dark):
    """Mengenfeld: eine einzelne Ziffer in einem breiten Feld, oben ragt eine Beschriftung
    hinein (wie 'KAUFEN' über dem Feld)."""
    from livebot.draw import _default_field_reader, numbers_loose
    font = ImageFont.truetype(FONT, 13)
    bg, field, fg = ((30, 34, 45), (19, 23, 34), (220, 220, 220)) if dark else (
        (217, 217, 217), (255, 255, 255), (0, 0, 0))
    img = Image.new("RGB", (220, 32), bg)
    d = ImageDraw.Draw(img)
    d.text((2, -9), "KAUFEN", font=font, fill=fg)
    d.rectangle((4, 6, 214, 30), fill=field, outline=(120, 120, 120))
    d.text((10, 10), value, font=font, fill=fg)
    text = _default_field_reader(np.array(img)[:, :, ::-1].copy())
    assert float(value) in numbers_loose(text), text


def test_mengenfeld_echter_ausschnitt_vom_nutzer():
    """Echter Ausschnitt (220x32) aus dem TradingView des Nutzers: links neben dem Feld steht
    blauer Fremdtext ('930,00'), in der Mitte das Pfeil-Symbol, im Feld die '1'."""
    import cv2
    from livebot.draw import _default_field_reader, pure_ints, tight_part
    img = cv2.imread(str(Path(__file__).parent / "data" / "menge_feld_tradingview.png"))
    assert img is not None
    text = _default_field_reader(img)
    assert 1 in pure_ints(text), text
    assert tight_part(text).strip() == "1", text            # nur das Feld, ohne Fremdtext


@pytest.mark.parametrize("value", ["1", "2", "5"])
def test_mengenfeld_mit_fremdtext_links_und_symbol(value):
    from livebot.draw import _default_field_reader, pure_ints, tight_part
    font = ImageFont.truetype(FONT, 13)
    img = Image.new("RGB", (220, 32), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((0, 6), "930,00", font=font, fill=(30, 60, 170))       # Fremdtext links
    d.rounded_rectangle((56, 2, 219, 26), radius=5, outline=(200, 200, 200))
    d.text((64, 6), value, font=font, fill=(30, 30, 30))
    d.rectangle((150, 10, 162, 20), outline=(110, 110, 110))        # Symbol
    text = _default_field_reader(np.array(img)[:, :, ::-1].copy())
    # Sicherheit: nie Fremdtext/falsche Zahl als Feldinhalt. Eine einzelne Ziffer in fremder
    # Schrift (z.B. Arial unter Windows) darf auch mal unlesbar sein -> 'nicht lesbar', kein
    # Abbruch. Die exakte '1' prüft test_mengenfeld_echter_ausschnitt_vom_nutzer.
    assert tight_part(text).strip() in (value, ""), text
    assert not [n for n in pure_ints(tight_part(text)) if n != int(value)], text


@pytest.mark.parametrize("label,kind", [("Stop-Loss Preis", "stop"), ("Take Profit Preis", "take"),
                                        ("Take-Profit Preis", "take")])
@pytest.mark.parametrize("dark", [False, True])
def test_beschriftung_ueber_dem_feld_lesen(label, kind, dark):
    """Wie im 'Position bearbeiten'-Fenster: Beschriftung links, darunter die obere Kante des
    Felds, Schaltersymbol rechts."""
    from livebot.draw import _default_label_reader, label_kind
    font = ImageFont.truetype(FONT, 13)
    bg, fg = ((19, 23, 34), (200, 200, 205)) if dark else ((255, 255, 255), (60, 60, 70))
    img = Image.new("RGB", (260, 36), bg)
    d = ImageDraw.Draw(img)
    d.text((150, 6), label, font=font, fill=fg)                    # Beschriftung beginnt links
    d.rounded_rectangle((148, 30, 259, 40), radius=5, outline=(120, 120, 120))
    d.ellipse((235, 8, 255, 26), outline=(120, 120, 120))          # Schalter
    text = _default_label_reader(np.array(img)[:, :, ::-1].copy())
    assert label_kind(text) == kind, text


def test_duenne_eins_wie_arial_symbol_naeher_an_der_mitte():
    """Fall vom Windows-PC des Nutzers (Arial): die '1' ist nur ein Strich, das Symbol liegt
    näher am Klickpunkt als die Zahl, links steht blauer Fremdtext."""
    from livebot.draw import _default_field_reader, tight_part
    font = ImageFont.truetype(FONT, 13)
    img = Image.new("RGB", (220, 32), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((0, 6), "930,00", font=font, fill=(30, 60, 170))       # blauer Fremdtext
    d.rounded_rectangle((56, 2, 219, 26), radius=5, outline=(200, 200, 200))
    d.line((64, 9, 64, 20), fill=(30, 30, 30), width=2)            # schmale '1'
    d.line((61, 12, 64, 9), fill=(30, 30, 30), width=1)
    d.rectangle((128, 10, 140, 20), outline=(110, 110, 110))        # Symbol nah an der Mitte
    text = _default_field_reader(np.array(img)[:, :, ::-1].copy())
    assert "930" not in tight_part(text), text                     # Fremdtext nie als Feldinhalt
    assert tight_part(text).strip() in ("1", ""), text             # nie eine FALSCHE Zahl
