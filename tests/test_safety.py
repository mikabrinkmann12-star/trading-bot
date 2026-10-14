import pytest

from replaybot.journal import Journal
from replaybot.safety import Guard, SafetyError

CFG = {"naechste_kerze": [900, 925]}


def make(tmp_path, title="NQ1! - TradingView", exe="TradingView.exe", **kw):
    clicks = []
    g = Guard(CFG, Journal(tmp_path), click_fn=lambda x, y: clicks.append((x, y)),
              window_fn=lambda x, y: (title, exe), **kw)
    return g, clicks


def test_klick_erlaubt(tmp_path):
    g, clicks = make(tmp_path)
    g.click_next()
    assert clicks == [(900, 925)]
    assert "Klick 1/200" in (tmp_path / "logs" / "aktionen.log").read_text(encoding="utf-8")


def test_desktop_app_ohne_tradingview_im_titel(tmp_path):
    g, clicks = make(tmp_path, title="NQ1! 30.222,25 -1,85% / TJR", exe="TradingView.exe")
    g.click_next()
    assert clicks


def test_falsches_fenster(tmp_path):
    g, clicks = make(tmp_path, title="Editor", exe="notepad.exe")
    with pytest.raises(SafetyError):
        g.click_next()
    assert clicks == []
    assert "VERWEIGERT" in (tmp_path / "logs" / "aktionen.log").read_text(encoding="utf-8")


def test_punkt_nicht_kalibriert(tmp_path):
    g, clicks = make(tmp_path)
    with pytest.raises(SafetyError):
        g.click(500, 500, "irgendwo")
    assert clicks == []


def test_max_klicks(tmp_path):
    g, clicks = make(tmp_path, max_clicks=3)
    for _ in range(3):
        g.click_next()
    with pytest.raises(SafetyError):
        g.click_next()
    assert len(clicks) == 3
