# TradingView-Replay-Bot (NQ1!, 5 min)

**Nur Replay/Paper.** Kein echtes Geld, kein Broker, keine Zugangsdaten.
Der Bot liest die Kerzen vom Bildschirm, rechnet die Strategie und zeigt dir Entry, Stop und Ziel an.

| Phase | Was | Stand |
|---|---|---|
| 1 | Rechenkern + CSV-Test | fertig |
| 2 | Bildschirm lesen (OCR) + Kalibrierung + Fenster | fertig |
| 3a | `--auto`: Bot klickt „Nächste Kerze“ selbst | fertig, bitte testen |
| 3b | `--orders`: Bot setzt die Limit-Order | folgt |

---

## Einmalig einrichten

1. **Python** ist schon installiert. Prüfen kannst du das mit `python --version`.
2. **Tesseract** installieren (liest die Zahlen vom Bildschirm):
   - Google: „tesseract UB Mannheim“ → Seite auf github.com → `tesseract-ocr-w64-setup-....exe` herunterladen → installieren (immer „Weiter“, Ordner nicht ändern).
3. **Neuen Code holen:** Auf GitHub den Branch `claude/tradingview-replay-bot-e3heom` wählen → grüner Knopf „Code“ → „Download ZIP“ → entpacken (den alten Ordner kannst du löschen).
4. **Schwarzes Fenster im Bot-Ordner öffnen** (dort, wo `bot.py` liegt), z. B.:
   ```
   cd "C:\Users\mikab\Desktop\TRADING BOT\trading-bot-claude-tradingview-replay-bot-e3heom"
   ```
   Vor dem `>` muss danach der Bot-Ordner stehen.
5. **Pakete installieren:**
   ```
   pip install -r requirements.txt
   ```

---

## Benutzen

### A) Kalibrieren (einmalig, und wieder nach jeder Änderung am TradingView-Layout)
```
python bot.py --kalibrieren
```
- Du hast 5 Sekunden, um auf TradingView zu klicken (Replay offen, Fenster so groß wie beim Training).
- Dann wird ein Bildschirmfoto gemacht und es kommen 3 Schritte:
  1. Ein **Rechteck um die OHLC-Legende** oben links ziehen (O… H… L… C…), dann **Enter**.
  2. Ein **Rechteck um den Kerzenbereich** des Charts ziehen, dann **Enter**.
  3. Auf den Replay-Button **„Nächste Kerze“** klicken, dann **Enter**.
- `Esc` bricht ab. Zum Schluss steht im schwarzen Fenster „Test-OCR: O … H … L … C …“. **Vergleich das mit dem Chart.**

### B) Automatisch durchlaufen lassen (empfohlen)
1. Replay in TradingView auf die **9:00-Kerze** (NY-Zeit) stellen. Das Replay muss **pausiert** sein, also kein Abspielen.
2. Start:
   ```
   python bot.py --live --auto --datum 2026-09-25
   ```
3. **Maus und Tastatur nicht anfassen.** Der Bot klickt selbst Kerze für Kerze weiter, liest jede Kerze und rechnet.
4. Ist der Trade fertig (oder gibt es keinen Trade), hört er auf. Das Ergebnis steht im Fenster und in `trades.csv`.

**Not-Aus:** **F12**, oder die Maus in die **linke obere Bildschirmecke** schieben, oder der Knopf „Stop“.

Der Bot klickt nur auf den kalibrierten „Nächste Kerze“-Punkt und nur, wenn dort TradingView liegt. Pro Lauf sind es höchstens 200 Klicks, und jeder Klick steht in `logs\aktionen.log`.

### B2) Nur mitlesen, du klickst selbst
```
python bot.py --live --datum 2026-09-25
```
Klick langsam, **eine Kerze pro Sekunde**, und lass die Maus nicht über dem Chart. Überspringst du eine Kerze, **stoppt** der Bot, weil die Uhrzeit sonst falsch wäre. Dann das Replay zurück auf 9:00 stellen und neu starten.

Startet das Replay nicht bei 9:00: `--start 09:10`.

### C) Tag aus einer CSV durchrechnen (ohne Bildschirm)
```
python bot.py --csv tests\data\2026-09-25.csv
```
Optional mit Abfrage: `--pruefen`.

---

## Wenn was nicht geht
| Meldung | Lösung |
|---|---|
| `Noch nicht kalibriert` | Zuerst `python bot.py --kalibrieren` |
| `Legende nicht lesbar` / `Test-OCR fehlgeschlagen` | Neu kalibrieren, das Rechteck enger um die Legende ziehen. Ist Tesseract installiert? |
| `tesseract is not installed` | Tesseract installieren. Liegt es nicht in `C:\Program Files\Tesseract-OCR`, den Pfad in `config.json` bei `"tesseract"` eintragen. |
| `Maus aus dem Chart nehmen` | Maus auf die Replay-Leiste oder neben den Chart bewegen |
| `Open ... passt nicht zum letzten Close` | Kerze übersprungen oder Maus über dem Chart. Replay zurück auf 9:00 und neu starten |
| `keine neue Kerze` (bei --auto) | Replay pausiert/am Ende oder Button verdeckt. Bei geändertem Layout neu kalibrieren |
| `Klick verweigert: kein TradingView-Fenster` | Am „Nächste Kerze“-Punkt liegt ein anderes Fenster. TradingView nach vorne holen oder neu kalibrieren |
| Zahlen falsch | Screenshot vom Bot-Fenster und der Legende schicken. Fehlerbilder liegen in `logs\` |

## Dateien
- `trades.csv`: eine Zeile pro Tag (Datum, Richtung, BOS-Zeit, Entry, Stop, Ziel, Risiko, Ergebnis, R)
- `logs\kerzen_log.csv`: jede gelesene Kerze, zum Vergleichen mit dem Chart
- `logs\aktionen.log`: Start, Stopp, Fehler
- `config.json`: deine Kalibrierung

## Strategie (alle Zeiten NY, 5 min)
1. **Richtung:** Close 9:40 > Open 9:30 heißt nur Long, Close < Open heißt nur Short, bei Gleichstand kein Trade.
2. **Swing-Hoch/-Tief:** Hoch höher (bzw. Tief tiefer) als bei der Kerze davor und danach. Bestätigt ist es erst, wenn die Kerze danach da ist. Es zählen nur Kerzen ab 9:00, und gemeint ist immer das zuletzt bestätigte.
3. **BOS** gibt es nur auf 9:45, 9:50 und 9:55: Der **Schlusskurs** liegt über dem Swing-Hoch (Long) bzw. unter dem Swing-Tief (Short). Ohne BOS gibt es keinen Trade.
4. **Leg** von 9:30 bis inklusive zur BOS-Kerze.
   - Entry = Mitte des Legs
   - Stop = Tief − 4 (Long) bzw. Hoch + 4 (Short)
   - Risiko > 100 heißt kein Trade
   - Ziel = 2R
5. **Füllung** ab der Kerze nach dem BOS bis 11:00.
   - Auf der Füll-Kerze zählt nur der Stop.
   - Danach erst Stop prüfen, dann Ziel.
   - Spätestens um 11:55 wird zum Close ausgestiegen.
6. **Ergebnis:** Ziel +2R, Stop −1R, Zeit-Exit (Close − Entry) / Risiko.

## Sicherheit
- Phase 2 klickt **nichts**.
- Ab Phase 3 klickt der Bot nur in kalibrierten Punkten und nur, wenn dort ein Fenster „TradingView“ liegt.
- Orders setzt er nur, wenn im Handelspanel „Paper“ oder „Replay“ steht.
- Pro Lauf sind höchstens 200 Klicks erlaubt. F12 stoppt sofort, Maus in die linke obere Ecke ebenfalls.
