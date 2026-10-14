import pytest

from livebot.recorder import Recording, RecordError, describe


def full_long():
    r = Recording()
    r.add_click(700, 1010, 0.0)      # Werkzeug
    r.add_click(1200, 400, 2.0)      # in den Chart
    r.add_click(1200, 400, 4.0)      # Doppelklick auf Box ...
    r.add_click(1201, 401, 4.2)      # ... zweiter Klick
    r.add_click(900, 300, 6.0)
    r.mark("entry")
    r.add_click(900, 400, 8.0)
    r.mark("ziel")
    r.add_click(900, 500, 10.0)
    r.mark("stop")
    r.add_click(1000, 700, 12.0)     # OK
    return r


def test_aufnahme_long():
    steps = full_long().validate()
    assert [s["punkt"] for s in steps] == [[700, 1010], [1200, 400], [1200, 400], [900, 300],
                                          [900, 400], [900, 500], [1000, 700]]
    assert [s["doppel"] for s in steps] == [False, False, True, False, False, False, False]
    assert [s["tippe"] for s in steps] == [None, None, None, "entry", "ziel", "stop", None]
    assert "Doppelklick" in describe(steps)


def test_zwei_langsame_klicks_sind_kein_doppelklick():
    r = Recording()
    r.add_click(10, 10, 0.0)
    r.add_click(10, 10, 1.0)
    assert len(r.steps) == 2 and not r.steps[0]["doppel"]


def test_dreifachklick_wird_nicht_zu_einem_schritt():
    r = Recording()
    for t in (0.0, 0.1, 0.2):
        r.add_click(10, 10, t)
    assert len(r.steps) == 2 and r.steps[0]["doppel"]


def test_fehlende_markierung():
    r = Recording()
    r.add_click(1, 1, 0)
    r.mark("entry")
    with pytest.raises(RecordError, match=r"Stop \(F7\), Ziel \(F8\)"):
        r.validate()


def test_markieren_ohne_klick():
    with pytest.raises(RecordError):
        Recording().mark("entry")
