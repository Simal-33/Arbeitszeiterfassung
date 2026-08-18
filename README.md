# Arbeitszeiterfassung

Kleine lokale Web-App zur Arbeitszeiterfassung: manuelle Einträge, Sollzeit je Wochentag,
automatische Überstundenberechnung, Export und Import als Datei.

Alles läuft auf deinem eigenen Rechner. Keine Cloud, keine Anmeldung, keine externen Bibliotheken –
nur Python 3 (ab 3.8), das auf macOS und Linux vorinstalliert ist und unter Windows von
python.org kommt.

Dieselbe Oberfläche läuft in zwei Betriebsarten:

- **Am Rechner** mit dem Python-Server, Daten in einer SQLite-Datei.
- **Am Handy** als installierbare Web-App ganz ohne Server, Daten im Browser des Geräts.

Welche Art aktiv ist, merkt die Seite beim Start selbst.

## Am Handy installieren

Die App liegt unter <https://simal-33.github.io/Arbeitszeiterfassung/> – diese Adresse
im Handy-Browser öffnen:

- **iPhone (Safari):** Teilen-Symbol → *Zum Home-Bildschirm*
- **Android (Chrome):** Menü ⋮ → *App installieren*

Danach startet sie wie eine normale App, auch ohne Internet. Die erfassten Zeiten liegen
ausschließlich auf dem Gerät und werden nie hochgeladen – veröffentlicht wird nur der
Programmcode.

Veröffentlicht wird über die Pages-Einstellung *Deploy from a branch* (`main`, Ordner `/`).
Die `index.html` in der Wurzel leitet auf `static/` weiter, wo die App liegt; `.nojekyll`
sorgt dafür, dass die Dateien unverändert ausgeliefert werden. Es ist kein eigener
Workflow nötig – nach jedem Push auf `main` ist die neue Fassung in etwa einer Minute
online.

Weil Browserdaten verloren gehen können (iOS räumt Speicher selten genutzter Web-Apps auf,
und „Browserdaten löschen" trifft auch diese App), erinnert die App alle zwei Wochen an eine
Sicherung. Ein Tipp auf **Jetzt sichern** legt eine JSON-Datei ab, die sich über **Import**
auf jedem Gerät wieder einlesen lässt – so wandern die Daten auch zwischen Handy und Rechner.

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

## Feiertage (Österreich)

Die App berechnet die 13 gesetzlichen Feiertage nach dem Arbeitsruhegesetz selbst – über die
Osterformel, also ohne Internetverbindung und für jedes beliebige Jahr:

Neujahr, Heilige Drei Könige, Ostermontag, Staatsfeiertag, Christi Himmelfahrt, Pfingstmontag,
Fronleichnam, Mariä Himmelfahrt, Nationalfeiertag, Allerheiligen, Mariä Empfängnis,
Christtag, Stefanitag.

Bewusst **nicht** enthalten:

- **Karfreitag** – seit 2019 kein allgemeiner Feiertag mehr, sondern über den persönlichen
  Feiertag (ein einseitig wählbarer Urlaubstag) geregelt.
- **Landespatrone** (z. B. Leopold in Wien, Florian in Oberösterreich) – keine gesetzlichen
  Ruhetage im Sinne des Arbeitsruhegesetzes.
- **24.12. und 31.12.** – ebenfalls keine gesetzlichen Feiertage. In den Einstellungen lässt
  sich wählen, ob sie als normale Arbeitstage, halbe oder ganze freie Tage gelten sollen; das
  richtet sich nach deinem Kollektivvertrag.

Im Bereich „Feiertage & Standardtage“ wählst du ein Jahr und trägst mit einem Klick alle
Feiertage ein, die auf einen Arbeitstag fallen. Bereits erfasste Tage bleiben unangetastet,
mehrfaches Klicken legt also nichts doppelt an.

## Notdienst, Pauschalen und Ausfahrten

Die Zeit eines Notdienstes ist eine **zeitliche Pauschale**. Sie wird gesondert verrechnet
und fließt deshalb **nicht** in Ist, Saldo oder Überstunden ein – sie steht in eigenen
Kacheln und einem eigenen Abschnitt. Dasselbe gilt für Ausfahrten während eines Dienstes.

Voreingestellt sind drei Dienste:

| Dienst | Zeitraum | Pauschale |
|---|---|---|
| 1. Dienst | Montag 07:00 bis Montag 07:00, durchgehend | 168:00 h |
| 2. Dienst | Montag bis Samstag, je 07:00–20:00 | 78:00 h |
| 3. Dienst | Freitag bis Samstag, je 07:00–20:00 | 26:00 h |

- Unter Einstellungen ist je Dienstart ein Wochenrhythmus hinterlegt: Starttag und -zeit,
  Endtag und -zeit sowie die Art des Fensters. *durchgehend* läuft ohne Unterbrechung vom
  Anfang bis zum Ende, *täglich im Zeitfenster* gilt an jedem Tag der Spanne zwischen den
  beiden Uhrzeiten. Die Gesamtpauschale rechnet das Programm daraus selbst aus.
- Wer keinen Rhythmus braucht, stellt *fester Wert je Tag* ein und gibt wie bisher Minuten
  je Diensttag an. Dann wird zusätzlich ein Enddatum abgefragt.
- Im Bereich **Dienst eintragen** genügen Dienstart und ein Datum. Der Beginn rutscht
  automatisch auf den Starttag der Dienstart, eine Zeile darunter steht der genaue Zeitraum
  vor dem Anlegen. Ein zweiter Klick legt nichts doppelt an.
- Die Pauschale wird auf die Kalendertage aufgeteilt, angebrochene Tage anteilig: beim
  1. Dienst also 17:00 h am ersten Montag, 24:00 h an den sechs Tagen dazwischen und
  07:00 h am letzten Montag.
- **Ausfahrten** erfasst du über das normale Formular mit der Art „Ausfahrt im Dienst“,
  mit Von und Bis wie bei Arbeitszeit – auch über Mitternacht. Den Dienst bekommt jede
  Ausfahrt automatisch von dem Diensttag, an dem sie liegt.
- Der Abschnitt **Notdienst-Tage mit Ausfahrt** listet sie mit Tag, Dienst, Uhrzeit und
  Dauer; **Dienste im Zeitraum** zeigt je Dienstart Tage, Pauschale und die Zahl der
  Ausfahrten – zusammen die Grundlage für die gesonderte Abrechnung.
- Diensttage und Ausfahrten blockieren das Auffüllen nicht: während eines Dienstes wird
  ja weiterhin normal gearbeitet, „Arbeitstage auffüllen" trägt diese Zeiten also ein.
- Im CSV-Export sagt die Spalte **Verrechnung**, ob eine Zeile normale Arbeitszeit ist oder
  gesondert verrechnet wird.

## Feste Arbeitstage

Unter Einstellungen hinterlegst du je Wochentag feste Zeiten (Von, Bis, Pause). Diese werden
beim Erfassen automatisch vorgeschlagen, sobald du ein Datum wählst.

Der Knopf **Arbeitstage auffüllen** trägt im angezeigten Zeitraum alle Arbeitstage nach, die
noch keinen Eintrag haben. Übersprungen werden dabei: Tage mit vorhandenem Eintrag, Feiertage,
Wochentage ohne Sollzeit, Wochentage ohne hinterlegte Standardzeit und alles nach heute.

## Wie gerechnet wird

- **Dauer** = Bis − Von − Pause. Liegt „Bis“ vor „Von“, wird eine Nachtschicht über Mitternacht
  angenommen (22:00–06:00 = 8 h).
- **Soll** = Summe der Sollstunden aller Tage im Zeitraum. Tage in der Zukunft zählen nur mit,
  wenn dort bereits etwas erfasst ist – vorab eingetragene Feiertage oder geplante Urlaube
  drücken den Saldo also nicht ins Minus, und der laufende Monat auch nicht.
- Ohne gesetztes **Startdatum** beginnt die Saldorechnung mit dem ersten Tag, an dem
  Arbeitszeit erfasst wurde. Tage davor bleiben sichtbar, zählen aber nicht mit.
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
app.py                     Server, API und Berechnungslogik (nur Standardbibliothek)
static/index.html          Oberfläche, läuft mit und ohne Server
static/lokal.js            dieselbe Rechenlogik in JavaScript, für den Betrieb ohne Server
static/sw.js               Service Worker, macht die Handy-App offlinefähig
static/manifest.webmanifest Angaben zur Installation am Handy
test_api.py                End-to-End-Test gegen den laufenden Server
zeiterfassung.db           wird beim ersten Start angelegt
```

Die Rechenregeln stehen zweimal da – einmal in Python, einmal in JavaScript. Damit sie nicht
auseinanderlaufen, vergleicht `test_lokal.py` beide Implementierungen: dieselben Szenarien
werden durch beide geschickt und die Ergebnisse müssen auf die Minute übereinstimmen.

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
| GET | `/api/feiertage?jahr=` | Feiertage des Jahres mit Status |
| POST | `/api/feiertage` | Feiertage eines Jahres eintragen |
| POST | `/api/auffuellen` | Offene Arbeitstage mit Standardzeiten füllen |
| POST | `/api/dienste` | Dienst anlegen; `bis` nur bei Dienstarten ohne Wochenrhythmus |
| GET | `/api/export.json` / `/api/export.csv` | Export |
| POST | `/api/import` | Import |

## Tests

Der Test erwartet einen Server mit **leerer** Datenbank:

```bash
python3 app.py --db test.db --no-browser   # Terminal 1
python3 test_api.py                        # Terminal 2
```

130 Prüfungen: Anlegen, Ändern, Löschen, Fehlerfälle, Nachtschichten, halbe Urlaubstage,
Saldoberechnung, Export und Import sowie die Feiertagstermine 2026 und 2027 gegen die
offizielle Liste der Stadt Wien.

## Download-Paket bauen (GitHub)

Der Workflow `.github/workflows/release.yml` schnürt ein fertiges ZIP:

- **Ohne Tag:** Im Reiter *Actions* den Workflow „Download-Paket" wählen und *Run workflow*
  klicken. Das ZIP hängt danach unten am Lauf unter *Artifacts* (90 Tage abrufbar).
- **Mit Tag:** `git tag v1.0.0 && git push origin v1.0.0` erzeugt zusätzlich ein Release,
  in dem das ZIP dauerhaft unter *Releases* liegt und sich direkt verlinken lässt.

In beiden Fällen laufen vorher die Tests; schlagen sie fehl, entsteht kein Paket.

### Wer das Paket herunterladen darf

- **Privates Repository:** Artefakte und Release-Dateien sind nur mit Login und Zugriff auf das
  Repository abrufbar. Das ist der einfachste Schutz und braucht keine weitere Einstellung.
- **Öffentliches Repository:** Release-Dateien und Artefakte kann jeder laden. Einen
  Passwortschutz bietet GitHub dafür nicht – der Workflow kann aber ein verschlüsseltes Paket
  bauen: unter *Settings → Secrets and variables → Actions* ein Secret namens `PAKET_PASSWORT`
  anlegen. Dann entsteht statt des offenen ZIP ein mit AES-256 verschlüsseltes `.7z`, bei dem
  auch die Dateinamen verschlüsselt sind. Der Workflow prüft selbst nach, dass sich das Archiv
  mit einem falschen Passwort nicht öffnen lässt.

Zum Öffnen des geschützten Pakets: 7-Zip (Windows), Keka oder The Unarchiver (macOS),
`7z x datei.7z` (Linux).

## Sicherheit

Die App hat bewusst keine Anmeldung – dafür schützt sie sich gegen die Wege, auf denen ein
lokaler Server sonst angreifbar ist:

- Schreibende Anfragen brauchen `Content-Type: application/json`, ein fremder `Origin` wird
  abgelehnt. Eine beliebige Webseite im selben Browser kann damit keine Einträge anlegen oder
  löschen (CSRF).
- Ein fremder `Host`-Header wird abgewiesen, was DNS-Rebinding verhindert.
- Statische Dateien werden nur aus `static/` ausgeliefert, Symlinks und Nachbarordner
  eingeschlossen geprüft.
- Notizen und Projektnamen landen nie als Text in HTML-Attributen.

Bekannte Einschränkung: Zeiten werden als reine Wanduhrzeit gerechnet. Eine Nachtschicht, die
über die Sommerzeitumstellung läuft (zweimal im Jahr), ist deshalb um eine Stunde falsch und
muss von Hand korrigiert werden.

## Hinweise

- Der Server hört bewusst nur auf `127.0.0.1`, ist also nicht aus dem Netzwerk erreichbar.
  Ein Start mit `--host 0.0.0.0` verlangt zusätzlich `--im-netz-freigeben`, weil dann jeder
  im selben Netz ohne Passwort mitlesen und ändern könnte.
- Die App erhebt keinen Anspruch auf Rechtskonformität nach ArbZG oder dem EuGH-Urteil zur
  Arbeitszeiterfassung; sie ist ein persönliches Werkzeug.
