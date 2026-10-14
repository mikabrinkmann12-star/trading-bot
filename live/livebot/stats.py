"""Auswertung mehrerer Live-(Paper-)Tage aus trades.csv."""
from __future__ import annotations

import csv
from pathlib import Path

from .livetrade import NOT_FILLED, TRADE_RESULTS
from .strategy import NO_TRADE
MIN_SAMPLE = 20


def load_trades(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["R"] = float(r["R"]) if (r.get("R") or "").strip() else None
    return sorted(rows, key=lambda r: r.get("Datum") or "")


def _group(trades: list[dict]) -> dict:
    rs = [t["R"] for t in trades]
    wins = sum(1 for r in rs if r > 0)
    return {"anzahl": len(rs), "gewinner": wins,
            "quote": wins / len(rs) if rs else None, "summe_r": sum(rs)}


def _streaks(rs: list[float]) -> tuple[int, int]:
    best_w = best_l = cur_w = cur_l = 0
    for r in rs:
        if r > 0:
            cur_w, cur_l = cur_w + 1, 0
        elif r < 0:
            cur_w, cur_l = 0, cur_l + 1
        else:
            cur_w = cur_l = 0
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    return best_w, best_l


def _max_drawdown(rs: list[float]) -> float:
    peak = equity = dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return dd


def compute(rows: list[dict], von: str | None = None, bis: str | None = None) -> dict:
    days = [r for r in rows
            if (not von or (r.get("Datum") or "") >= von)
            and (not bis or (r.get("Datum") or "") <= bis)]
    trades = [r for r in days if r.get("Ergebnis") in TRADE_RESULTS and r["R"] is not None]
    rs = [t["R"] for t in trades]
    gains = sum(r for r in rs if r > 0)
    losses = -sum(r for r in rs if r < 0)
    win_streak, loss_streak = _streaks(rs)

    def by(key, values):
        return {v: _group([t for t in trades if t.get(key) == v]) for v in values
                if any(t.get(key) == v for t in trades)}

    best = max(trades, key=lambda t: t["R"]) if trades else None
    worst = min(trades, key=lambda t: t["R"]) if trades else None
    return {
        "von": days[0]["Datum"] if days else None,
        "bis": days[-1]["Datum"] if days else None,
        "tage": len(days),
        "trades": len(trades),
        "kein_trade": sum(1 for r in days if r.get("Ergebnis") == NO_TRADE),
        "nicht_gefuellt": sum(1 for r in days if r.get("Ergebnis") == NOT_FILLED),
        "sonstige": len(days) - len(trades)
                    - sum(1 for r in days if r.get("Ergebnis") in (NO_TRADE, NOT_FILLED)),
        "gewinner": sum(1 for r in rs if r > 0),
        "verlierer": sum(1 for r in rs if r < 0),
        "quote": sum(1 for r in rs if r > 0) / len(rs) if rs else None,
        "summe_r": sum(rs),
        "schnitt_r": sum(rs) / len(rs) if rs else None,
        "profit_faktor": (gains / losses) if losses > 0 else (None if not gains else float("inf")),
        "bester": (best["Datum"], best["R"]) if best else None,
        "schlechtester": (worst["Datum"], worst["R"]) if worst else None,
        "gewinnserie": win_streak,
        "verlustserie": loss_streak,
        "max_drawdown": _max_drawdown(rs),
        "richtung": by("Richtung", ("long", "short")),
        "bos": by("BOS-Zeit", ("09:45", "09:50", "09:55")),
        "ergebnis": by("Ergebnis", TRADE_RESULTS),
    }


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x * 100:.0f} %"


def _r(x: float | None) -> str:
    return "-" if x is None else f"{x:+.2f} R"


def format_report(s: dict) -> str:
    if s["tage"] == 0:
        return "Keine Tage in trades.csv gefunden (oder keine im gewählten Zeitraum)."
    pf = s["profit_faktor"]
    pf_txt = "-" if pf is None else ("unendlich (keine Verluste)" if pf == float("inf")
                                     else f"{pf:.2f}")
    lines = [
        f"AUSWERTUNG  {s['von']} bis {s['bis']}",
        "=" * 52,
        f"Tage gesamt            {s['tage']}",
        f"  davon Trades         {s['trades']}",
        f"  Kein Trade           {s['kein_trade']}",
        f"  nicht gefüllt        {s['nicht_gefuellt']}",
    ]
    if s["sonstige"]:
        lines.append(f"  offen/Fehler         {s['sonstige']}")
    lines += [
        "",
        f"Gewinner / Verlierer   {s['gewinner']} / {s['verlierer']}",
        f"Trefferquote           {_pct(s['quote'])}",
        f"Summe                  {_r(s['summe_r'])}",
        f"Pro Trade (Erwartung)  {_r(s['schnitt_r'])}",
        f"Profit-Faktor          {pf_txt}",
        f"Bester Trade           {_r(s['bester'][1]) if s['bester'] else '-'}"
        f"{'  (' + s['bester'][0] + ')' if s['bester'] else ''}",
        f"Schlechtester Trade    {_r(s['schlechtester'][1]) if s['schlechtester'] else '-'}"
        f"{'  (' + s['schlechtester'][0] + ')' if s['schlechtester'] else ''}",
        f"Längste Gewinnserie    {s['gewinnserie']}",
        f"Längste Verlustserie   {s['verlustserie']}",
        f"Max. Rückgang          {s['max_drawdown']:.2f} R",
    ]
    for title, key in (("Nach Richtung", "richtung"), ("Nach BOS-Zeit", "bos"),
                       ("Nach Ergebnis", "ergebnis")):
        if s[key]:
            lines += ["", title]
            for name, g in s[key].items():
                lines.append(f"  {name:<10} {g['anzahl']:>3} Trades   Quote {_pct(g['quote']):>5}"
                             f"   Summe {_r(g['summe_r'])}")
    if s["trades"] < MIN_SAMPLE:
        lines += ["", f"Achtung: erst {s['trades']} Trades. Unter {MIN_SAMPLE} sagt das noch "
                      f"nichts Verlässliches - weiter Tage sammeln."]
    return "\n".join(lines)
