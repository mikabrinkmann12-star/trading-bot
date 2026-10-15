# TradingView-Bot (NQ1!, 5 min) – zwei getrennte Bots

| Ordner | Wofür | Start |
|---|---|---|
| [`replay/`](replay/README.md) | **Replay-Training**: klickt sich durch vergangene Tage, rechnet, zeichnet ein | `cd replay` → `python bot.py --live --auto --datum 2026-09-25` |
| [`live/`](live/README.md) | **Live-Chart mit Paper-Trading-Konto**: beobachtet, kauft/verkauft per Markt-Order mit TP/SL, verwaltet den Trade | `cd live` → `python live.py` (vor 9:00 NY starten) oder sofort `python live.py --probelauf` |

Jeder Ordner ist komplett eigenständig: eigene `config.json` (Kalibrierung), `trades.csv`, `logs\`.
Die Strategie ist in beiden gleich (Richtung 9:30/9:40, BOS 9:45–9:55, Entry = Leg-Mitte, Stop ±4, Ziel 2R).
Unterschied beim Ausstieg: Replay steigt spätestens 11:55 zum Close aus. Live setzt um 12:00 den Stop auf Break-even (im Plus) oder schließt (im Minus), spätestens um 15:55.

**Neue Version einspielen:** ZIP entpacken. **Vorher aus dem alten Ordner in den neuen kopieren:** `live\config.json`, `live\trades.csv`, `replay\config.json`, `replay\trades.csv` (falls vorhanden auch `trades_nachtragen.csv`). Erst danach den alten Ordner löschen.

**Tests:** pro Ordner, also `cd live` → `python -m pytest -q` bzw. `cd replay` → `python -m pytest -q`. Im Hauptordner geht das nicht.

**trades.csv in Excel:** nicht doppelklicken (dann steht alles in Spalte A), sondern in Excel *Daten → Aus Text/CSV* und als Trennzeichen „Komma“ wählen.
