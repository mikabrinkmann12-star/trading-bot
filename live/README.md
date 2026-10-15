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
- Steht der Kurs in dem Moment, in dem der Entry berührt wird, **schon hinter Stop oder Ziel** (schneller Sprung), schickt er **keine** Order (Ergebnis „ausgelassen“).

## Sicherheit (immer an)
- **Paper-Sperre:** Vor **jeder** Order, jedem Break-even und jedem Schließen liest er den Kontonamen im Handelspanel. Steht dort nicht „Paper“, klickt er **nichts** und meldet das rot.
- **Fehllesungen:**
  - Eine einzelne falsch gelesene Zahl löst nie eine Order aus. Die Entry-Berührung muss in **2 Lesungen hintereinander** auftauchen.
  - Zusätzlich liest er jede fertige Kerze per Maus-Hover genau nach. Wurde Entry, Stop oder Ziel nur in den letzten Sekunden einer Kerze berührt, merkt er es so trotzdem.
  - Geht beim Kaufen etwas schief, kauft er **nie ein zweites Mal**. Er meldet es, und du prüfst in TradingView.
- **Bestellfenster:** Nach jedem Feld liest er die Zahl nach. **Direkt vor dem Bestätigen** liest er alle Felder noch einmal. Steht TP oder SL nicht sicher richtig drin, bestätigt er **nicht** (keine Order ohne TP/SL).
- **Maus im Chart:** Dann zeigt die Legende die Kerze unter der Maus, nicht die aktuelle. Solange deine Maus im Chart steht, liest der Bot **nicht** und meldet „Maus aus dem Chart nehmen!“. Über dem Bot-Fenster ist sie erlaubt.
- Ein einzelner unerwarteter Fehler beendet den Lauf nicht. Erst nach 20 Fehlern in Folge stoppt er und meldet es rot.
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
   | `python live.py --aufnehmen kaufen` | „Markt kaufen“ → Menge-Feld → TP-Schalter → TP-Preisfeld → SL-Schalter → SL-Preisfeld → Bestätigen → **X** | Menge **F5**, TP **F8**, SL **F7** |
   | `python live.py --aufnehmen verkaufen` | dasselbe mit „Markt verkaufen“ | Menge **F5**, TP **F8**, SL **F7** |
   | `python live.py --aufnehmen breakeven` | im **Handelspanel unten** bei der Position „Bearbeiten“ → SL-Preisfeld → Ändern | SL-Feld **F6** (dort kommt der Entry rein) |
   | `python live.py --aufnehmen schliessen` | im **Handelspanel unten** bei der Position „Schließen“ (+ ggf. Bestätigen) | – |
   | `python live.py --aufnehmen long` | Long-Box zeichnen wie im Replay | Entry **F6**, Ziel **F8**, Stop **F7** |
   | `python live.py --aufnehmen short` | Short-Box | Entry **F6**, Ziel **F8**, Stop **F7** |

   Am Ende jeweils **F9** zum Speichern, **F10** zum Abbrechen. Beim Vormachen von kaufen/verkaufen darfst du im Paper-Konto wirklich kaufen. Schließ die Position danach selbst.

   **Nicht** im Chart auf die SL-Linie oder das X an der Positionslinie klicken: Diese Linien liegen jeden Tag woanders. Der Bot warnt, wenn ein Ablauf so einen Klick enthält.

## Benutzen
**Order-Abläufe einmal testen (Paper-Konto, echte Klicks):**
```
python live.py --aktion-test alle
```
Er macht nacheinander: kaufen → Break-even → schließen → verkaufen → Break-even → schließen, mit etwa 4 s Pause dazwischen. Vorher fragt er nach „JA“ und prüft das Paper-Konto. Einzeln geht auch: `--aktion-test kaufen` (oder `verkaufen`, `breakeven`, `schliessen`). Beispielwerte: TP/SL jeweils 50 Punkte vom aktuellen Kurs, Break-even-SL 20 Punkte darunter (Long) bzw. darüber (Short).

**Erst testen, ohne zu handeln:**
```
python live.py --ohne-orders
```
Er beobachtet, rechnet und zeichnet ein. Statt zu kaufen, schreibt er nur „Hier würde der Bot jetzt Markt kaufen“.

**Kompletten Ablauf sofort ausprobieren (Probelauf, Paper-Konto):**
```
python live.py --probelauf
```
- Geht zu **jeder** Uhrzeit, zu der NQ handelt.
- Der Bot stellt seine Uhr in ganzen 5 Minuten zurück, so dass „jetzt“ für ihn kurz vor 9:00 ist. Die Kerzen im Chart sind echt, nur die Uhrzeiten sind verschoben.
- Danach läuft alles wie im echten Betrieb: Richtung, BOS, Entry, Order mit TP/SL, Box, 12:00-Regel.
- Ergebnisse landen im Ordner `probelauf\` und vermischen sich **nicht** mit deiner echten `trades.csv`.
- Mit `--ohne-orders` dahinter nur beobachten.

**Richtig laufen lassen (Paper-Konto):**
```
python live.py
```
- **Vor 9:04 NY** starten, am besten vor 9:00. Das ist normalerweise **15:00 deutscher Zeit**, vom **25.10. bis 31.10. aber 14:00**, weil Europa eine Woche früher die Uhr umstellt. Er braucht alle Kerzen ab 9:00.
- Startest du später, sagt er das sofort und hört auf. Dann geht für diesen Tag nur noch `--probelauf`.
- **Maus und Tastatur nicht anfassen.** Der Bot liest laufend die Legende.
- Er hört von selbst auf, wenn der Tag für ihn erledigt ist: kein Setup, nicht gefüllt oder Trade beendet.

**Auswertung:**
```
python live.py --auswertung
```

## Gut zu wissen
- **Bestellfenster:** Es nimmt nur den **Punkt** als Dezimalzeichen (der Bot tippt `30189.25`). Das stellt `"dezimal_order"` in `config.json` ein, Standard `"."`.
- **Meldung „Order ausgefüllt“ unten links:** Sie verdeckt kurz den Kontonamen. Der Bot wartet dann bis zu 20 s (`"paper_wartezeit"`), liest den Kontonamen neu und klickt in dieser Zeit **nichts**. Erst wenn danach immer noch kein „Papier…/Paper…“ lesbar ist, bricht er ab und speichert ein Bild nach `logs\ocr_konto_fehler_*.png`.
- **Bestellfenster bleibt offen:** Nach dem Bestätigen wartet der Bot **2,5 s** (`"bestaetigen_pause"`) und klickt dann das aufgenommene **X**.
- **Schalter für Take Profit / Stop Loss:** TradingView merkt sich, ob sie an sind. Waren sie schon **an**, schaltet der aufgenommene Klick sie aus. Dann bleibt das Feld gesperrt (blass). Der Bot merkt das, schaltet sie wieder **an** und tippt neu. Er prüft dabei, dass das Feld dadurch kräftiger und nicht blasser wird. Am besten nimmst du trotzdem mit ausgeschalteten Schaltern auf.
- **Klickpunkte in Preisfeldern:** immer die **Zahl links** im Feld anklicken, nie das ⇄-Symbol rechts daneben.
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
| `"bestaetigen_pause"` | `2.5` | Wartezeit nach dem Bestätigen der Order, bevor z. B. das X geklickt wird |
| `"dezimal_order"` | `"."` | Dezimalzeichen im Bestellfenster |
| `"genau_lesen"` | `true` | fertige Kerzen per Hover genau nachlesen |
| `"paper_wartezeit"` | `20` | so lange wartet die Paper-Sperre, wenn der Kontoname nicht lesbar ist (z. B. Meldung darüber) |

## Wenn was nicht geht
- **`trades.csv` in Excel offen:** Der Bot läuft weiter. Das Ergebnis steht dann vorerst in `trades_nachtragen.csv` und wird beim nächsten Mal automatisch in `trades.csv` übernommen.
- **„Es ist schon … NY“:** zu spät gestartet. Siehe oben, dann `--probelauf`.
- **„Einstellungsdialog ist nicht aufgegangen“:** Schau in `logs\aktionen.log` nach der Zeile „Dialog-Prüfung: Veränderung … %“. In `logs\` liegen dann zwei Bilder `ocr_zeichnen_dialog_vorher_*.png` und `ocr_zeichnen_dialog_nachher_*.png`. Schick sie mir, falls es wieder passiert. Daran sehe ich, ob die Box verfehlt wurde oder der Dialog nur schwer zu erkennen war.
Schick die rote Zeile aus dem Bot-Fenster, die letzten Zeilen aus `logs\aktionen.log` und, falls vorhanden, die Bilder `logs\ocr_*.png`.
