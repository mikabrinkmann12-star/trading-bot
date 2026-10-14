# TradingView-Replay-Bot (NQ1!, 5 min)

> Dieser Ordner ist der **Replay-Bot**. Der Live-Bot für das Paper-Konto liegt in `../live/`. Starte alle Befehle hier im Ordner `replay`.

**Nur Replay/Paper.** Kein echtes Geld, kein Broker, keine Zugangsdaten.
Der Bot liest die Kerzen vom Bildschirm, rechnet die Strategie und zeigt dir Entry, Stop und Ziel an.

| Phase | Was | Stand |
|---|---|---|
| 1 | Rechenkern + CSV-Test | fertig |
| 2 | Bildschirm lesen (OCR) + Kalibrierung + Fenster | fertig |
| 3a | `--auto`: Bot klickt „Nächste Kerze“ selbst | fertig, bitte testen |
| 3b | Bot zeichnet die Long-/Short-Position bei Füllung ein und zoomt (automatisch an, sobald aufgenommen) | fertig |
| 4 | `--auswertung`: Statistik über viele Tage | fertig |

---

## Einmalig einrichten

1. **Python** ist schon installiert. Prüfen kannst du das mit `python --version`.
2. **Tesseract** installieren (liest die Zahlen vom Bildschirm):
   - Google: „tesseract UB Mannheim“ → Seite auf github.com → `tesseract-ocr-w64-setup-....exe` herunterladen → installieren (immer „Weiter“, Ordner nicht ändern).
3. **Neuen Code holen:** Auf GitHub den Branch `claude/tradingview-replay-bot-e3heom` wählen → grüner Knopf „Code“ → „Download ZIP“ → entpacken (den alten Ordner kannst du löschen).
4. **Schwarzes Fenster im Bot-Ordner öffnen** (dort, wo `bot.py` liegt), z. B.:
   ```
   cd "C:\Users\mikab\Desktop\TRADING BOT\trading-bot-claude-tradingview-replay-bot-e3heom\replay"
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
  3. Auf den Replay-Button **Vorwärts ▷|** klicken (rechts neben Play), dann **Enter**. **Nicht auf Play ▷**, denn Play spielt durch und überspringt Kerzen.
  4. Ein **Rechteck um die Preisachse** rechts ziehen (die Zahlen-Spalte, ganz oben bis ganz unten), dann **Enter**. Das brauchst du nur fürs Zoomen beim Einzeichnen. Enter ohne Rechteck überspringt den Schritt.
- `Esc` bricht ab. Zum Schluss steht im schwarzen Fenster „Test-OCR: O … H … L … C …“. **Vergleich das mit dem Chart.**

### B) Automatisch durchlaufen lassen (empfohlen)
1. Replay in TradingView auf die **9:00-Kerze** (NY-Zeit) stellen. Das Replay muss **pausiert** sein, also kein Abspielen.
2. Start:
   ```
   python bot.py --live --auto --datum 2026-09-25
   ```
3. **Maus und Tastatur nicht anfassen.** Der Bot schiebt die Maus beim Start selbst aus dem Chart und klickt Kerze für Kerze weiter (nach jedem Klick 2 s Pause, einstellbar in `config.json` bei `"klick_pause"`), liest jede Kerze und rechnet.
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

### D) Long/Short-Position einzeichnen lassen
Der Bot zeichnet bei der **Füllung** die Position mit dem TradingView-Werkzeug ein und zoomt so, dass Entry, Stop und Ziel sichtbar sind. Währenddessen klickt er nicht weiter.

**1. Einmal vormachen, je für Long und für Short:**
```
python bot.py --aufnehmen long
```
Dann machst du es in TradingView **einmal** vor:

| Schritt | Du machst | Taste danach |
|---|---|---|
| 1 | Klick auf das Long-Positions-Werkzeug | – |
| 2 | Klick in den Chart (rechts, wo Platz ist) | – |
| 3 | Doppelklick auf die neue Box (Einstellungen gehen auf) | – |
| 4 | Klick ins Feld **Einstiegspreis** | **F6** |
| 5 | Klick ins **Preis**-Feld vom Gewinn-/Ziel-Niveau | **F8** |
| 6 | Klick ins **Preis**-Feld vom Stopp-Niveau | **F7** |
| 7 | Klick auf **OK** | – |
| | fertig | **F9** (abbrechen: **F10**) |

Danach `python bot.py --aufnehmen short` genauso mit dem Short-Werkzeug. Die Boxen, die du beim Vormachen zeichnest, kannst du löschen.

**2. Einzeln testen**, ohne einen Replay-Lauf:
```
python bot.py --zeichnen-test long
```
Der Bot zeichnet eine Beispiel-Box: Entry = aktueller Kurs, Stop 20 Punkte drunter, Ziel 40 Punkte drüber. Prüf dann, ob die Box da ist, die Zahlen stimmen und alles sichtbar ist.

**Wo kommt die Box hin?** An die **aktuelle Kerze** (die Füll-Kerze), mit der Mittellinie auf dem Entry-Preis.

**Was der Bot dabei prüft**, bevor er weitermacht:
1. **Kerze finden:** Er sucht die rechteste blaue oder schwarze Kerze. Preisachse, Zeitachse, Legende und sein eigenes Fenster blendet er aus. Dann fährt er mit der Maus drauf: Die Legende muss die **aktuelle** Kerze zeigen, und eine Kerze weiter links die **vorherige**. Erst dann ist sie bestätigt. Findet er sie nicht, zeichnet er **nichts** und meldet es.
2. **Box anlegen:** Klick auf die Kerze, Doppelklick knapp rechts daneben auf die Entry-Linie.
3. **Dialog offen?** Erst wenn sich das Bild dort verändert hat, wo die Felder sind, wird getippt. Sonst drückt er Esc und bricht ab. Er tippt also nie in den Chart.
4. **Zahl richtig?** Nach jedem Feld liest er die Zahl zurück. Ist sie falsch, tippt er nochmal. Ist sie beim zweiten Mal wieder falsch, bricht er ab.
5. **Zoom:** Die Position (Stop bis Ziel) soll **etwa die Hälfte bis 80 %** der Chart-Höhe füllen. Ist sie zu klein, zieht er die Preisachse hoch (ran), ist sie zu groß, zieht er sie runter (raus). Danach richtet er sie mittig aus. Nach jedem Zug liest er die Achse neu.
6. **Nie Auto:** Doppelklicks an der Preisachse sind gesperrt, denn die würden den Chart auf „An Bildschirm anpassen“ stellen.

Einstellbar in `config.json`, falls TradingView bei dir langsamer ist:

| Eintrag | Standard | Bedeutung |
|---|---|---|
| `"zeichnen_pause"` | `1.0` | Sekunden Pause nach jedem Schritt beim Einzeichnen |
| `"dialog_wartezeit"` | `3.0` | So lange wartet er höchstens, bis der Dialog offen ist |
| `"zoom_pause"` | `1.0` | Pause nach jedem Zoom-Zug |
| `"doppelklick_versatz"` | `12` | So viele Pixel rechts vom Ankerpunkt macht er den Doppelklick |

**3. Im Auto-Lauf:** Das Einzeichnen ist **automatisch an**, sobald du Long/Short aufgenommen hast:
```
python bot.py --live --auto --datum 2026-09-25
```
Beim Start steht im schwarzen Fenster „Einzeichnen: AN“ oder „AUS“. Am Ende steht im Bot-Fenster, warum nichts eingezeichnet wurde, falls es keine Füllung gab (Kein Trade / nicht gefüllt). Ausschalten kannst du es mit `--ohne-zeichnen`.

- Während des Einzeichnens **verschwindet das Bot-Fenster kurz**, damit es keine Kerze und kein Feld im Dialog verdeckt.
- **Klappt das Einzeichnen nicht**, steht das rot im Fenster. Der Trade wird aber **trotzdem zu Ende gerechnet** und in `trades.csv` gespeichert. Nur „Stop“ oder F12 beenden den Lauf sofort.
- Vor jedem Einzeichnen drückt er zweimal Esc, damit kein alter Dialog mehr offen ist. Nach OK prüft er, ob der Dialog wirklich zu ist.
- Beim Vormachen (`--aufnehmen`) werden nur Klicks in TradingView aufgenommen. Klicks ins schwarze Fenster werden ignoriert.

Wichtig: Die Werkzeugleiste und der Einstellungsdialog müssen beim Lauf **an derselben Stelle** sein wie beim Vormachen. Wenn du das Layout änderst, musst du neu aufnehmen.
Das Dezimalzeichen beim Tippen ist `,`. Will TradingView bei dir einen Punkt, trag in `config.json` `"dezimal": "."` ein.

### E) Auswertung über viele Tage
```
python bot.py --auswertung
python bot.py --auswertung --von 2026-09-01 --bis 2026-09-30
```
Das liest `trades.csv` und zeigt:
- Trefferquote, Summe R und **R pro Trade (Erwartungswert)**
- Profit-Faktor (Gewinne ÷ Verluste), bester und schlechtester Trade
- längste Gewinn- und Verlustserie, **größter Rückgang in R**
- aufgeschlüsselt nach Long/Short, nach BOS-Zeit (9:45/9:50/9:55) und nach Ergebnis

Der Bericht wird zusätzlich in `auswertung.txt` gespeichert. Unter 20 Trades kommt ein Hinweis, dass das noch nichts aussagt.

**So liest du es:** Ist „Pro Trade“ über viele Tage positiv, verdient die Strategie im Schnitt. Bei 2R-Ziel und 1R-Stop reicht dafür schon eine Trefferquote über 33 %. Der „Max. Rückgang“ zeigt, wie viele R du zwischendurch aushalten musst.

## Wenn was nicht geht
| Meldung | Lösung |
|---|---|
| `Noch nicht kalibriert` | Zuerst `python bot.py --kalibrieren` |
| `Legende nicht lesbar` / `Test-OCR fehlgeschlagen` | Neu kalibrieren, das Rechteck enger um die Legende ziehen. Ist Tesseract installiert? |
| `tesseract is not installed` | Tesseract installieren. Liegt es nicht in `C:\Program Files\Tesseract-OCR`, den Pfad in `config.json` bei `"tesseract"` eintragen. |
| `Maus aus dem Chart nehmen` | Maus auf die Replay-Leiste oder neben den Chart bewegen |
| `Open ... passt nicht zum letzten Close` | Kerze übersprungen oder Maus über dem Chart. Replay zurück auf 9:00 und neu starten |
| Bot wartet ewig („Warte auf Kerze ... seit 30 s“) | Falscher Button kalibriert? Es muss **Vorwärts ▷|** sein, nicht Play ▷. Neu kalibrieren |
| `Klick verweigert: kein TradingView-Fenster` | Am „Nächste Kerze“-Punkt liegt ein anderes Fenster. TradingView nach vorne holen oder neu kalibrieren |
| `Einzeichnen ist noch nicht aufgenommen` | Zuerst `--aufnehmen long` und `--aufnehmen short` |
| Box falsch / Dialog geht nicht auf | Layout geändert? Neu aufnehmen. Mit `--zeichnen-test` prüfen. In `config.json` bei `"zeichnen_pause"` mehr Zeit geben (z.B. `1.0`) |
| `Position evtl. nicht ganz sichtbar` | Preisachse neu kalibrieren (Schritt 4), Rechteck nur um die Zahlen-Spalte |
| Box ohne richtige Zahlen / tippt nicht | Rote Zeile aus dem Bot-Fenster, die letzten Zeilen aus `logs\aktionen.log` (Zeilen mit „Diagnose“) und die Bilder `logs\ocr_zeichnen_*.png` schicken. Darauf ist zu sehen, was der Bot im Feld gelesen hat |
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
- Der Bot klickt nur auf kalibrierte oder aufgenommene Punkte, und nur, wenn dort TradingView liegt.
- Ziehen geht nur innerhalb des kalibrierten Chart- bzw. Preisachsen-Bereichs.
- Tippen geht nur, wenn TradingView im Vordergrund ist.
- Orders setzt er **keine**, er zeichnet nur ein.
- Pro Lauf sind höchstens 200 Aktionen erlaubt, jede steht in `logs\aktionen.log`.
- F12 stoppt sofort, Maus in die linke obere Ecke ebenfalls.
