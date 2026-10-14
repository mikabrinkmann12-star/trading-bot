# TradingView-Replay-Trainingsbot (NQ1!, 5 min)

**Nur Replay/Paper.** Kein echtes Geld, keine Broker-Verbindung, keine Zugangsdaten.
Der Bot rechnet deine Strategie Kerze für Kerze nach und fragt dich im Prüfmodus ab.

| Phase | Inhalt | Stand |
|---|---|---|
| 1 | Rechenkern + CSV-Testmodus + Prüfmodus (Konsole) | fertig |
| 2 | Screenshot + OCR der OHLC-Legende + Kalibrierung + Fenster | folgt |
| 3 | `--auto` (Klick „Nächste Kerze“), danach `--orders` | folgt |

## Strategie (alle Zeiten NY, 5 min)
1. **Richtung:** Close 9:40 > Open 9:30 heißt nur Long, Close < Open heißt nur Short, bei Gleichstand kein Trade.
2. **Swing-Hoch:** Hoch höher als bei der Kerze davor *und* danach (Swing-Tief analog mit dem Tief). Bestätigt ist es erst, wenn die Kerze danach da ist. Es zählen nur Kerzen ab 9:00, und gemeint ist immer das *zuletzt* bestätigte Swing.
3. **BOS** gibt es nur auf 9:45, 9:50 und 9:55: Der **Schlusskurs** liegt über dem Swing-Hoch (Long) bzw. unter dem Swing-Tief (Short). Ein Docht allein zählt nicht. Ohne BOS bis 9:55 gibt es keinen Trade.
4. **Leg** reicht von 9:30 bis einschließlich zur BOS-Kerze.
   - Entry = (Tief + Hoch) / 2
   - Stop Long = Tief − 4, Stop Short = Hoch + 4
   - Risiko = |Entry − Stop|, über 100 Punkte gibt es keinen Trade
   - Ziel = Entry ± 2 × Risiko
5. **Füllung** ab der Kerze nach dem BOS bis einschließlich 11:00.
   - Auf der Füll-Kerze zählt nur der Stop, das Ziel noch nicht.
   - Danach wird pro Kerze erst der Stop geprüft, dann das Ziel.
   - Spätestens um 11:55 wird zum Close ausgestiegen.
6. **Ergebnis:** Ziel +2R, Stop −1R, Zeit-Exit (Close − Entry) / Risiko (bei Short umgekehrt).

---

## Installation (Windows 11)

### 1. Python
1. Python 3.11 oder neuer von https://www.python.org/downloads/ installieren.
   **Wichtig:** Beim Installer den Haken bei **„Add python.exe to PATH“** setzen.
2. Eine neue Eingabeaufforderung öffnen (Startmenü → `cmd`) und prüfen:
   ```
   python --version
   ```

### 2. Projekt + Pakete
```
cd C:\Pfad\zu\trading-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
Ab jetzt bei jedem neuen Konsolenfenster zuerst `.venv\Scripts\activate` ausführen.

### 3. Tesseract (die OCR-Software, erst ab Phase 2 nötig)
`pytesseract` ist nur die Python-Brücke. Das eigentliche Programm Tesseract musst du extra installieren:
1. Öffne https://github.com/UB-Mannheim/tesseract/wiki (das ist der übliche Windows-Build der Uni Mannheim).
2. Lade den Installer `tesseract-ocr-w64-setup-....exe` (64 bit) herunter und starte ihn.
3. Lass den Installationsordner auf `C:\Program Files\Tesseract-OCR`. Zusätzliche Sprachen brauchst du nicht, weil wir nur Ziffern lesen.
4. Füge den Ordner zum PATH hinzu: Startmenü → „Umgebungsvariablen“ → „Systemumgebungsvariablen bearbeiten“ → Umgebungsvariablen → bei *Path* auf Bearbeiten → Neu → `C:\Program Files\Tesseract-OCR` eintragen → mit OK bestätigen.
5. Öffne eine **neue** Konsole und prüfe:
   ```
   tesseract --version
   ```
   Wenn eine Versionsnummer erscheint, passt alles. Falls nicht, trägt der Bot in Phase 2 den Pfad auch direkt in `config.json` ein.

---

## Phase 1 benutzen: CSV-Testmodus

### Tests laufen lassen
```
python -m pytest
```
Erwartet wird `39 passed`. Die Tests prüfen beide Beispieltage (25.9. und 14.9.) und alle Sonderfälle: kein BOS, Risiko > 100, Stop auf der Füll-Kerze, Zeit-Exit, Short, nicht gefüllt usw.

### Nur rechnen lassen
```
python bot.py --csv tests\data\2026-09-25.csv --ohne-pruefen
python bot.py --csv tests\data\2026-09-14.csv --ohne-pruefen
```
Am 25.9. muss Long herauskommen, mit BOS 9:50, Entry 30845, Stop 30763.5, Risiko 81.5, Ziel 31008, gefüllt um 10:00 und Stop = −1R.
Am 14.9. ergibt sich Long, BOS 9:45, Entry 28962.25, Stop 28874.75, Risiko 87.5, Ziel 29137.25, gefüllt um 10:35 und Ziel um 11:30 = +2R.

### Prüfmodus (Standard)
```
python bot.py --csv tests\data\2026-09-25.csv
```
- Mit **Enter** kommt die nächste Kerze.
- Bei jedem Schritt fragt der Bot dich vorher (Richtung, Swing, BOS, Leg/Entry/Stop/Risiko/Ziel, Füllung, Stop/Ziel, R).
- Zahlen darfst du mit Komma oder Punkt eingeben (`30845,5`, `30.845,50`, `30845.5`).
- Bei einer falschen Antwort sagt dir der Bot, was richtig ist und wo dein Denkfehler liegt.
- Tippst du nichts oder `kb`, zeigt er die Lösung (plus ein Zitat). `q` beendet den Lauf.
- Am Ende bekommst du die Trefferquote und eine Liste deiner Fehler.

### Eigene Tage üben
Lege eine CSV an, z. B. `meine_tage\2026-10-01.csv`:
```
Zeit,O,H,L,C
09:00,28880,28881.25,28836,28842.25
09:05,...
```
Semikolon mit Komma (deutsches Excel) geht auch: `09:00;28880;28881,25;28836;28842,25`.
Das Datum nimmt der Bot aus dem Dateinamen, sonst aus `--datum 2026-10-01`.

### Ausgabe-Dateien
- `trades.csv` enthält eine Zeile pro Tag (Datum, Richtung, BOS-Zeit, Entry, Stop, Ziel, Risiko, Ergebnis, R). Läuft derselbe Tag nochmal, wird seine Zeile ersetzt.
- `logs\kerzen_log.csv` enthält jede gelesene Kerze.
- `logs\pruefung_log.csv` enthält jede Prüfmodus-Antwort mit richtig/falsch.

Mit `--ausgabe ORDNER` legst du alles in einem anderen Ordner ab.

---

## Sicherheit (gilt ab Phase 3 für Klicks)
- Geklickt wird nur in kalibrierten Regionen und nur, wenn der aktive Fenstertitel „TradingView“ enthält.
- **F12** beendet den Bot sofort. Wenn du die Maus in die obere linke Bildschirmecke ziehst, greift der pyautogui-Notstopp.
- Pro Lauf sind höchstens 200 Klicks erlaubt, und jede Aktion landet in `logs\aktionen.log`.
- Orders gibt es nur mit `--orders`, und auch dann erst nach deiner Bestätigung mit Enter.
