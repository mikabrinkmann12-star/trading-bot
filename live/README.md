# Live-Bot (NQ1!, 5 min) – nur PAPER-Trading-Konto

Der Bot beobachtet den **Live-Chart**, rechnet die Strategie und handelt **selbst** im **Paper-Trading-Konto** von TradingView:
- Nach dem BOS wartet er, bis der Kurs den **Entry** (Leg-Mitte) berührt (bis 11:05 NY).
- Dann drückt er sofort **Markt kaufen/verkaufen** und trägt **Menge, Take Profit und Stop Loss** ein.
- Danach zeichnet er die **Long-/Short-Box** an der aktuellen Kerze ein.
- **12:00 NY**, Position noch offen:
  - im Plus → **Stop auf Break-even** (Entry), weiterlaufen lassen
  - im Minus (oder genau Entry) → **Position schließen**
- Nach Break-even schließt er **spätestens um 15:55 NY**.
- Er macht **höchstens 1 Trade pro Tag**. Das Ergebnis landet in `trades.csv`, inklusive Füllzeit und Füllkurs.

## Sicherheit (immer an)
- **Paper-Sperre:** Vor **jeder** Order, jedem Break-even und jedem Schließen liest er den Kontonamen im Handelspanel. Steht dort nicht „Paper“, klickt er **nichts** und meldet das rot.
- **Fehllesungen:**
  - Eine einzelne falsch gelesene Zahl löst nie eine Order aus. Die Entry-Berührung muss in **2 Lesungen hintereinander** auftauchen.
  - Geht beim Kaufen etwas schief, kauft er **nie ein zweites Mal**. Er meldet es, und du prüfst in TradingView.
- F12 stoppt sofort, Maus in die linke obere Ecke ebenfalls. Pro Lauf sind höchstens 200 Aktionen erlaubt, jede steht in `logs\aktionen.log`.

## Einmalig einrichten
1. Im Ordner `live` das schwarze Fenster öffnen (Adresszeile → `cmd`) und Folgendes ausführen:
   ```
   pip install -r requirements.txt
   ```
   Das installiert unter anderem `tzdata` für die NY-Uhrzeit.
2. **In TradingView: „Ein-Klick-Handel“ AUSSCHALTEN.** Sonst kauft TradingView beim Klick sofort ohne TP/SL. Achte auch darauf, dass das **Paper-Trading-Konto** verbunden ist.
3. **Kalibrieren:**
   ```
   python live.py --kalibrieren
   ```
   Dabei markierst du nacheinander:
   1. die Legende
   2. den Chart-Bereich
   3. die Preisachse
   4. den **Kontonamen** im Handelspanel (dort muss „Paper Trading“ stehen)
   5. einen **Parkplatz** für die Maus außerhalb des Charts, z. B. am Rand der Watchlist

   Am Ende steht „Paper-Konto erkannt“.
4. **Abläufe vormachen**, jeden einmal. Die Klicks werden aufgenommen, die Tasten markieren die Felder.

   | Befehl | Was du vormachst | Tasten |
   |---|---|---|
   | `python live.py --aufnehmen kaufen` | „Markt kaufen“ → Menge-Feld → TP-Preisfeld → SL-Preisfeld → Bestätigen | Menge **F5**, TP **F8**, SL **F7** |
   | `python live.py --aufnehmen verkaufen` | dasselbe mit „Markt verkaufen“ | Menge **F5**, TP **F8**, SL **F7** |
   | `python live.py --aufnehmen breakeven` | Position bzw. SL bearbeiten → SL-Preisfeld → OK | SL-Feld **F6** (dort kommt der Entry rein) |
   | `python live.py --aufnehmen schliessen` | „Position schließen“ (+ ggf. Bestätigen) | – |
   | `python live.py --aufnehmen long` | Long-Box zeichnen wie im Replay | Entry **F6**, Ziel **F8**, Stop **F7** |
   | `python live.py --aufnehmen short` | Short-Box | Entry **F6**, Ziel **F8**, Stop **F7** |

   Am Ende jeweils **F9** zum Speichern, **F10** zum Abbrechen. Beim Vormachen von kaufen/verkaufen darfst du im Paper-Konto wirklich kaufen. Schließ die Position danach selbst.

## Benutzen
**Erst testen, ohne zu handeln:**
```
python live.py --ohne-orders
```
Er beobachtet, rechnet und zeichnet ein. Statt zu kaufen, schreibt er nur „Hier würde der Bot jetzt Markt kaufen“.

**Richtig laufen lassen (Paper-Konto):**
```
python live.py
```
- Am besten **vor 9:00 NY** starten (15:00 deutscher Zeit). Er braucht die Kerzen ab 9:00.
- **Maus und Tastatur nicht anfassen.** Der Bot liest laufend die Legende.
- Er hört von selbst auf, wenn der Tag für ihn erledigt ist: kein Setup, nicht gefüllt oder Trade beendet.

**Auswertung:**
```
python live.py --auswertung
```

## Gut zu wissen
- Füllkurs und Ergebnis sind die Rechnung des Bots aus der Legende. Was TradingView wirklich ausführt, kann wegen Slippage um ein paar Ticks abweichen.
- Zwischen Entry-Berührung und Order liegen einige Sekunden (Paper-Prüfung, Felder ausfüllen, Felder nachprüfen).
- TP und SL führt **TradingView** aus. Der Bot verfolgt nur mit, damit er um 12:00 weiß, ob die Position noch offen ist.

## Einstellungen in `config.json`
| Eintrag | Standard | Bedeutung |
|---|---|---|
| `"menge"` | `1` | Kontrakte pro Trade |
| `"dezimal"` | `","` | Dezimalzeichen beim Tippen |
| `"order_pause"` | `0.3` | Pause zwischen den Klicks beim Kaufen (schnell!) |
| `"zeichnen_pause"` | `1.0` | Pause beim Einzeichnen |
| `"dialog_wartezeit"` | `3.0` | so lange wartet er höchstens auf ein Fenster/Dialog |

## Wenn was nicht geht
Schick die rote Zeile aus dem Bot-Fenster, die letzten Zeilen aus `logs\aktionen.log` und, falls vorhanden, die Bilder `logs\ocr_*.png`.
