import pytest

from replaybot.chartnav import ChartNav, fit_scale

AXIS = [1600, 80, 70, 800]
CHART = [60, 80, 1500, 800]


def labels_for(center, ppp, step=20.0):
    """Beschriftungen wie auf der TradingView-Preisachse."""
    y_mid = AXIS[1] + AXIS[3] / 2
    top_p = center + (y_mid - AXIS[1]) * ppp
    bot_p = center - (AXIS[1] + AXIS[3] - y_mid) * ppp
    out = []
    p = (bot_p // step + 1) * step
    while p < top_p:
        out.append((y_mid - (p - center) / ppp, p))
        p += step
    return out


def test_fit_scale_genau():
    a, b = fit_scale(labels_for(30868.25, 0.6))
    assert a == pytest.approx(-0.6)
    assert a * 480 + b == pytest.approx(30868.25)


def test_fit_scale_ignoriert_ausreisser():
    labels = labels_for(30868.25, 0.6) + [(300, 3087.0), (500, 99999.0)]
    a, b = fit_scale(labels)
    assert a == pytest.approx(-0.6)


def test_fit_scale_zu_wenig():
    assert fit_scale([(100, 30000.0)]) is None
    assert fit_scale([]) is None


class FakeChart:
    """Simuliert TradingView: Preisachse runterziehen = rauszoomen,
    Chart ziehen = verschieben (geht erst, wenn die Auto-Skala aus ist)."""

    def __init__(self, center, ppp, autoscale=True):
        self.center, self.ppp, self.autoscale = center, ppp, autoscale
        self.drags = []

    def labels(self):
        return labels_for(self.center, self.ppp)

    def drag(self, x1, y1, x2, y2, region, what):
        self.drags.append(region)
        dy = y2 - y1
        if region == "preisachse":
            self.ppp *= (1 + dy / 150) if dy > 0 else 1 / (1 - dy / 150)
            self.autoscale = False
        elif region == "chart" and not self.autoscale:
            self.center += dy * self.ppp


def nav(chart):
    return ChartNav({"preisachse": AXIS, "chart": CHART}, chart,
                    labels_fn=chart.labels, sleep=lambda s: None)


def test_schon_sichtbar_nichts_tun():
    ch = FakeChart(30868.0, 0.6)          # sichtbar ca. 30628 - 31108
    assert nav(ch).ensure_visible(30763.5 - 25, 31008 + 25)
    assert ch.drags == []


def test_zu_gross_zoomt_raus():
    ch = FakeChart(30868.0, 0.15)         # nur ca. 120 Punkte sichtbar
    assert nav(ch).ensure_visible(30740, 31030)
    assert "preisachse" in ch.drags


def test_versetzt_verschiebt_auch_mit_autoskala():
    ch = FakeChart(30500.0, 0.6)          # Position liegt oberhalb
    assert nav(ch).ensure_visible(30740, 31030)
    assert "chart" in ch.drags


def test_achse_unlesbar():
    n = ChartNav({"preisachse": AXIS, "chart": CHART}, None, labels_fn=lambda: [],
                 sleep=lambda s: None)
    assert n.ensure_visible(1, 2) is False
