from pathlib import Path

import pytest

from replaybot.csv_source import read_candles
from replaybot.quiz import Quiz, parse_number, questions_for
from replaybot.strategy import StrategyEngine

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize("text,thousands,expected", [
    ("30.845,00", True, 30845.0),
    ("30845,5", True, 30845.5),
    ("30845.5", True, 30845.5),
    ("30.845", True, 30845.0),
    ("-1", False, -1.0),
    ("+2", False, 2.0),
    ("0.27", False, 0.27),
])
def test_parse_number(text, thousands, expected):
    assert parse_number(text, thousands) == pytest.approx(expected)


def play(path, answer_fn):
    """Spielt einen Tag durch; answer_fn(question) liefert die Antwort."""
    e = StrategyEngine()
    out = []
    current = {}

    def ask(text):
        return answer_fn(current["q"])

    quiz = Quiz(ask=ask, say=out.append)
    for c in read_candles(path):
        rep = e.on_candle(c)
        for q in questions_for(e, rep):
            current["q"] = q
            quiz._ask_one(q, c.time)
        if e.done:
            break
    return quiz, out


def perfect(q):
    if q.kind == "choice":
        return q.expected
    return "keins" if q.expected is None else str(q.expected).replace(".", ",")


@pytest.mark.parametrize("day", ["2026-09-25.csv", "2026-09-14.csv"])
def test_perfekte_antworten_alle_richtig(day):
    quiz, out = play(DATA / day, perfect)
    assert quiz.total > 10
    assert quiz.correct == quiz.total, quiz.summary()


def test_fragen_tag_a():
    quiz, _ = play(DATA / "2026-09-25.csv", perfect)
    # Richtung, 2x(Swing+BOS), 7 Setup-Fragen, Füllung 9:55+10:00, Management 10:00+10:05, R
    assert quiz.total == 1 + 4 + 7 + 2 + 2 + 1


def test_stop_ohne_puffer_wird_erklaert():
    def ans(q):
        return "30767,5" if q.key == "Stop" else perfect(q)
    quiz, out = play(DATA / "2026-09-25.csv", ans)
    assert quiz.correct == quiz.total - 1
    assert any("Puffer vergessen" in o for o in out)


def test_unbestaetigtes_swing_wird_erklaert():
    # Auf 9:45 ist 30888.8 das Hoch der aktuellen Kerze -> noch nicht bestätigt
    def ans(q):
        if q.key == "Swing-Hoch" and q.expected == pytest.approx(30890.0):
            return "30888,8"
        return perfect(q)
    quiz, out = play(DATA / "2026-09-25.csv", ans)
    assert any("noch NICHT" in o for o in out)


def test_leg_ohne_bos_kerze_wird_erklaert():
    def ans(q):
        return "30890" if q.key == "Leg-Hoch" else perfect(q)
    quiz, out = play(DATA / "2026-09-25.csv", ans)
    assert any("BOS-Kerze vergessen" in o for o in out)


def test_ueberspringen_zeigt_zitat_und_loesung():
    def ans(q):
        return "kb" if q.key == "Entry" else perfect(q)
    quiz, out = play(DATA / "2026-09-25.csv", ans)
    assert any(o.startswith('"') for o in out)
    assert any("Lösung: 30845.00" in o for o in out)
