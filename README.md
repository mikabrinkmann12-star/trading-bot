# TradingView-Bot (NQ1!, 5 min) – zwei getrennte Bots

| Ordner | Wofür | Start |
|---|---|---|
| [`replay/`](replay/README.md) | **Replay-Training**: klickt sich durch vergangene Tage, rechnet, zeichnet ein | `cd replay` → `python bot.py --live --auto --datum 2026-09-25` |
| [`live/`](live/README.md) | **Live-Chart mit Paper-Trading-Konto**: beobachtet, kauft/verkauft per Markt-Order mit TP/SL, verwaltet den Trade | `cd live` → `python live.py` |

Jeder Ordner ist komplett eigenständig: eigene `config.json` (Kalibrierung), `trades.csv`, `logs\`.
Die Strategie ist in beiden gleich (Richtung 9:30/9:40, BOS 9:45–9:55, Entry = Leg-Mitte, Stop ±4, Ziel 2R).

**Wichtig nach dem Update:** Deine bisherige `config.json` und `trades.csv` gehören jetzt in den Ordner **`replay\`**.
