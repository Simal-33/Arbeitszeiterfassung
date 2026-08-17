# Arbeitszeiterfassung

Kleine lokale Web-App zur Arbeitszeiterfassung: manuelle Einträge, Sollzeit je Wochentag,
automatische Überstundenberechnung, Export und Import als Datei.

Alles läuft auf deinem eigenen Rechner. Keine Cloud, keine Anmeldung, keine externen Bibliotheken –
nur Python 3 (ab 3.8), das auf macOS und Linux vorinstalliert ist und unter Windows von
python.org kommt.

## Starten

```bash
python3 app.py
```

Der Browser öffnet sich automatisch auf <http://127.0.0.1:8765>.
Zum Beenden im Terminal `Strg+C` drücken.

Unter Windows alternativ per Doppelklick auf `start.bat`, unter macOS/Linux auf `start.sh`.

Optionen:

```bash
python3 app.py --port 9000          # anderer Port
python3 app.py --db /pfad/zeit.db   # anderer Speicherort der Datenbank
python3 app.py --no-browser         # Browser nicht automatisch öffnen
```

## Erste Schritte

1. Unten unter **Einstellungen** die Sollstunden je Wochentag eintragen (Standard: 8 h Mo–Fr).
2. Optional einen **Startsaldo** setzen, falls du Überstunden aus einem alten System übernimmst.
3. Optional ein Datum bei **Soll zählt ab** setzen – davor werden keine Sollstunden gerechnet.
4. Oben Einträge erfassen. Fertig.

## Eingabe

Die Oberfläche ist durchgehend deutsch und zeigt Datum und Uhrzeit unabhängig von der
Browsersprache im deutschen Format (`Mo, 03.08.2026`, 24-Stunden-Zeiten).

Bei „Von“ und „Bis“ genügt eine Kurzform, die beim Verlassen des Feldes ergänzt wird:
`9` → `09:00`, `830` → `08:30`, `17.45` → `17:45`.

## Wie gerechnet wird

- **Dauer** = Bis − Von − Pause. Liegt „Bis“ vor „Von“, wird eine Nachtschicht über Mitternacht
  angenommen (22:00–06:00 = 8 h).
- **Soll** = Summe der Sollstunden aller Tage im Zeitraum, aber nur bis einschließlich heute.
  Der laufende Monat steht dadurch nicht künstlich im Minus.
- **Urlaub, Krank, Feiertag, Gleitzeittag** werden automatisch mit den Sollstunden des Tages
  gutgeschrieben – der Saldo bleibt an diesen Tagen neutral. Trägst du bei diesen Arten trotzdem
  eine Zeitspanne ein, zählt genau diese (praktisch für halbe Urlaubstage).
- **Saldo** = Ist + Gutschrift − Soll. **Gesamtüberstunden** = Saldo über den kompletten
  Erfassungszeitraum plus Startsaldo.

## Daten, Sicherung, Umzug

Alle Daten liegen in `zeiterfassung.db` (SQLite) im Programmordner.

- **Sicherung (JSON)** lädt eine vollständige Kopie inklusive Einstellungen herunter.
- **Import** liest so eine Datei wieder ein – wahlweise ersetzend oder anhängend.
- **CSV** exportiert den angezeigten Zeitraum für Excel (Semikolon, Komma als Dezimaltrenner).

Für ein Backup reicht es, `zeiterfassung.db` oder die JSON-Sicherung zu kopieren.

## Aufbau

```
app.py              Server, API und Berechnungslogik (nur Standardbibliothek)
static/index.html   komplette Oberfläche (HTML, CSS, JS in einer Datei)
test_api.py         End-to-End-Test gegen den laufenden Server
zeiterfassung.db    wird beim ersten Start angelegt
```

### API

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/eintraege?von=&bis=` | Einträge im Zeitraum |
| POST | `/api/eintraege` | Eintrag anlegen |
| PUT | `/api/eintraege/{id}` | Eintrag ändern |
| DELETE | `/api/eintraege/{id}` | Eintrag löschen |
| GET | `/api/einstellungen` | Einstellungen lesen |
| PUT | `/api/einstellungen` | Einstellungen speichern |
| GET | `/api/auswertung?von=&bis=` | Ist, Soll, Saldo, Tage, Projekte |
| GET | `/api/export.json` / `/api/export.csv` | Export |
| POST | `/api/import` | Import |

## Tests

Server starten, dann in einem zweiten Terminal:

```bash
python3 test_api.py
```

Prüft Anlegen, Ändern, Löschen, Fehlerfälle, Nachtschichten, halbe Urlaubstage,
Saldoberechnung, Export und Import.

## Hinweise

- Der Server hört bewusst nur auf `127.0.0.1`, ist also nicht aus dem Netzwerk erreichbar.
  Wer ihn im Heimnetz nutzen möchte, startet mit `--host 0.0.0.0` – dann gibt es allerdings
  keine Zugriffsbeschränkung, das also nur in einem vertrauenswürdigen Netz tun.
- Die App erhebt keinen Anspruch auf Rechtskonformität nach ArbZG oder dem EuGH-Urteil zur
  Arbeitszeiterfassung; sie ist ein persönliches Werkzeug.
