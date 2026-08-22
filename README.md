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

Die App wird über GitHub Pages bereitgestellt. Dafür gibt es zwei Wege – einer davon kommt
ganz ohne Workflow aus:

- **Ohne Workflow (einfacher):** *Settings → Pages → Source: Deploy from a branch*,
  Branch `main`, Ordner `/ (root)`. Die Datei `index.html` in der Repo-Wurzel leitet auf
  `static/` weiter, wo die App liegt. Es muss keine Workflow-Datei angelegt werden.
- **Mit Workflow:** *Settings → Pages → Source: GitHub Actions*. Dann veröffentlicht
  `pages.yml` gezielt nur den Ordner `static/`, und die Dateien prüft er vorher auf
  Vollständigkeit.

Danach im Handy-Browser die Adresse `https://<konto>.github.io/<repo>/` öffnen:

- **iPhone (Safari):** Teilen-Symbol → *Zum Home-Bildschirm*
- **Android (Chrome):** Menü ⋮ → *App installieren*

Danach startet sie wie eine normale App, auch ohne Internet. Die erfassten Zeiten liegen
ausschließlich auf dem Gerät und werden nie hochgeladen – veröffentlicht wird nur der
Programmcode.

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

## Umstieg von der App „Arbeitszeit" (.worktimes)

Eine Sicherung der iOS-App „Arbeitszeit" lässt sich direkt übernehmen:

```bash
python3 import_worktimes.py Arbeitszeit.worktimes -o import.json
```

Die entstandene Datei über **Import** einlesen (ersetzend). Übernommen werden Arbeitszeiten
mit Von, Bis und Pause, Urlaub, Krankenstand, Feiertage, Zeitausgleich, die Sollstunden je
Wochentag sowie die Notdienst-Kennzeichnungen als Dienstarten.

Zwei Eigenheiten der Quelle behandelt das Programm eigens:

- Mehrtägige Abwesenheiten liegen dort als Folge gleicher Zeilen vor und werden wieder auf
  die einzelnen Tage verteilt.
- **Zeitausgleich** wirkt unterschiedlich: An einem freien Tag entsteht das Minus schon
  dadurch, dass die Sollzeit fehlt. Wurde am selben Tag zusätzlich gearbeitet, ist es eine
  echte Abbuchung und wird als negative Gutschrift übernommen.

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

## Aufbau der Oberfläche

Die App ist in fünf Ansichten geteilt, erreichbar über die Navigation – am Rechner als
Seitenleiste links, am Handy als Leiste am unteren Rand:

| Ansicht | Inhalt |
|---|---|
| **Stempeln** | Kommen/Gehen, laufende Messung, was heute schon erfasst ist |
| **Erfassen** | Zeitraum, Kennzahlen, Eingabemaske und Liste der Einträge |
| **Übersicht** | Kennzahlen des Zeitraums, Tage je Art, Dienste, Projekte |
| **Feiertage** | Feiertage eintragen, Dienstzeiträume, Arbeitstage auffüllen |
| **Einstellungen** | Jobs, Sollzeiten, Standardzeiten, Dienstarten, Notizvorlagen |

Die gewählte Ansicht steht in der Adresse (`…/#uebersicht`) und bleibt beim Neuladen erhalten.

## Speichern

Einstellungen speichern sich selbst: Nach einer kurzen Tippause wird der Stand gesichert,
die Zeile unten zeigt den Zeitpunkt an. Eine unsinnige Eingabe wird dort gemeldet und **nicht**
gespeichert – der bisherige Wert bleibt stehen, bis die Eingabe stimmt.

Einträge und Zeitmessungen speichern bewusst weiterhin per Knopfdruck: Eine halb getippte
Uhrzeit soll nicht als Arbeitszeit landen.

## Stempeluhr

Oben in der App: **Kommen** startet die Zeitmessung, **Gehen** beendet sie und legt den
Eintrag an. Dazwischen lässt sich die **Pause** an- und abschalten – sie wird mitgezählt und
vom Ergebnis abgezogen. **Verwerfen** bricht eine Messung ab, ohne etwas zu buchen.

Die laufende Messung liegt in der Datenbank, nicht im Browser: Sie übersteht das Schließen
der App, einen Neustart des Rechners und geht auch über Mitternacht – Pausen eingeschlossen.
Läuft eine Messung länger als 24 Stunden (vergessenes Ausstempeln), verweigert die App das
Buchen und sagt es, statt stillschweigend eine falsche Dauer einzutragen.

## Mehrere Jobs

Unter Einstellungen legst du beliebig viele Jobs an. **Sollstunden, feste Arbeitszeiten,
Startsaldo und Startdatum gehören zum jeweiligen Job** – so lässt sich eine Hauptanstellung
mit 38,5 Stunden neben einem Wochenendjob führen.

Oben wählst du den Job aus; alle Eingaben und Auswertungen beziehen sich darauf.
Mit **Alle Jobs zusammen** siehst du die Summe über alles, wobei ein Kalendertag nur einmal
gezählt wird, auch wenn an ihm für zwei Jobs gebucht wurde.

Wird ein Job umbenannt, bleiben die erfassten Zeiten zugeordnet. Feiertage, Dienste und das
Auffüllen wirken immer nur auf den gewählten Job; der CSV-Export enthält eine Job-Spalte und
folgt der Auswahl.

## Übersicht

Der Abschnitt **Übersicht im Zeitraum** fasst zusammen: gearbeitete Zeit, Gutschriften,
Sollzeit, Saldo und Gesamtüberstunden, dazu die Anzahl der Tage je Art – Urlaub, Krankenstand,
Feiertage, Zeitausgleich und Dienste.

## Notizvorlagen

Häufige Notizen einmal in den Einstellungen hinterlegen; beim Erfassen erscheinen sie als
Vorschlagsliste im Notizfeld.

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
- **Ausfahrten** erfasst du über das normale Formular mit der Art „Ausfahrt im Dienst",
  mit Von und Bis wie bei Arbeitszeit – auch über Mitternacht. Den Dienst bekommt jede
  Ausfahrt automatisch von dem Diensttag, an dem sie liegt.
- Der Abschnitt **Notdienst-Tage mit Ausfahrt** listet sie mit Tag, Dienst, Uhrzeit und
  Dauer; **Dienste im Zeitraum** zeigt je Dienstart Tage, Pauschale und die Zahl der
  Ausfahrten – zusammen die Grundlage für die gesonderte Abrechnung.
- Diensttage und Ausfahrten blockieren das Auffüllen nicht: während eines Dienstes wird
  ja weiterhin normal gearbeitet, „Arbeitstage auffüllen" trägt diese Zeiten also ein.
- Ein Dienst, der in der Zukunft liegt, erzeugt kein Tagessoll. Der laufende Monat steht
  dadurch nicht künstlich im Minus.
- Im CSV-Export sagt die Spalte **Verrechnung**, ob eine Zeile normale Arbeitszeit ist oder
  gesondert verrechnet wird.

## Feste Arbeitstage

Unter Einstellungen hinterlegst du je Wochentag feste Zeiten (Von, Bis, Pause). Diese werden
beim Erfassen automatisch vorgeschlagen, sobald du ein Datum wählst.

Der Knopf **Arbeitstage auffüllen** trägt im angezeigten Zeitraum alle Arbeitstage nach, die
noch keinen Eintrag haben. Übersprungen werden dabei: Tage mit vorhandenem Eintrag, Feiertage,
Wochentage ohne Sollzeit, Wochentage ohne hinterlegte Standardzeit und alles nach heute.

## Rechenregeln

**Sommerzeit.** Die App rechnet mit der tatsächlich verstrichenen Zeit, nicht mit der
Wanduhr. Eine Nachtschicht 22:00–06:00 ergibt in der Nacht der Umstellung im März sieben,
im Oktober neun Stunden. Die Zeitzone dafür steht in den Einstellungen.

> Dafür braucht Python eine Zeitzonendatenbank. macOS und Linux bringen sie mit, **Windows
> nicht** – dort liefert `pip install tzdata` sie nach. Fehlt sie, rechnet die App weiter
> mit der Wanduhr (an den beiden Umstellungstagen also um eine Stunde daneben) und der
> Testlauf überspringt die drei Sommerzeit-Prüfungen. Am Handy tritt das nicht auf, dort
> kommt die Zeitzone vom Browser.

**Rundung.** Optional wird die Arbeitszeit jedes Eintrags auf 5, 10, 15 oder 30 Minuten
gerundet – zur nächsten Stufe, immer auf oder immer ab. Standard ist minutengenau.

**Urlaubskonto.** Je Job lässt sich ein Urlaubsanspruch in Tagen hinterlegen. Die Übersicht
zeigt dann Anspruch, Verbrauch und Rest – immer bezogen auf das ganze Jahr, unabhängig vom
angezeigten Zeitraum. Halbe Urlaubstage zählen als halber Tag; an Tagen ohne Sollzeit
(Wochenende, freier Wochentag) wird kein Urlaub verbraucht.

**Bericht.** In der Übersicht erzeugt „Bericht drucken" eine Aufstellung des Zeitraums mit
Kopfdaten, allen Einträgen, Summen und Unterschriftszeile. Im Druckdialog lässt sie sich auf
jedem Gerät als PDF sichern.

**Rückgängig.** Ein gelöschter Eintrag lässt sich 20 Sekunden lang mit einem Klick
zurückholen; die Sicherheitsabfrage vor dem Löschen entfällt dadurch.

**Sicherung teilen.** Am Handy legt „Teilen" die Sicherungsdatei direkt in eine andere App –
Dateien, iCloud, Drive oder Mail – statt sie in den Download-Ordner zu legen.

## Wie gerechnet wird

- **Dauer** = Bis − Von − Pause. Liegt „Bis“ vor „Von“, wird eine Nachtschicht über Mitternacht
  angenommen (22:00–06:00 = 8 h).
- **Soll** = Summe der Sollstunden aller Tage im Zeitraum. Tage in der Zukunft zählen nur mit,
  wenn dort bereits etwas erfasst ist – vorab eingetragene Feiertage oder geplante Urlaube
  drücken den Saldo also nicht ins Minus, und der laufende Monat auch nicht.
- Ohne gesetztes **Startdatum** beginnt die Saldorechnung am **Monatsersten** des ersten
  erfassten Tages. Damit zählt der ganze Anfangsmonat mit – auch ein Urlaubs- oder
  Krankentag, der vor dem ersten Arbeitstag liegt. Tage davor bleiben sichtbar, zählen
  aber nicht mit.
- Die **Gutschrift** eines Eintrags darf auch negativ sein. So lassen sich ausbezahlte oder
  abgebuchte Stunden erfassen, ohne die geleistete Arbeitszeit zu verfälschen.
- **Urlaub, Krank und Feiertag** werden automatisch mit den Sollstunden des Tages
  gutgeschrieben – der Saldo bleibt an diesen Tagen neutral. Trägst du bei diesen Arten trotzdem
  eine Zeitspanne ein, zählt genau diese (praktisch für halbe Urlaubstage).
- **Zeitausgleich** wird bewusst *nicht* gutgeschrieben: so ein Tag baut ja gerade
  Plusstunden ab. Der Saldo fällt deshalb um die Sollzeit des Tages. In der Liste steht
  die abgebaute Zeit, damit der Tag nicht mit 0:00 dasteht. Eine ausdrückliche Gutschrift
  am Eintrag hat weiterhin Vorrang – so bleiben abgebuchte Stunden aus dem Import richtig.
- **Saldo** = Ist + Gutschrift − Soll. **Gesamtüberstunden** = Saldo über den kompletten
  Erfassungszeitraum plus Startsaldo.

## Daten, Sicherung, Umzug

Alle Daten liegen in `zeiterfassung.db` (SQLite) im Programmordner.

- **Sicherung (JSON)** lädt eine vollständige Kopie inklusive Einstellungen herunter.
- **Import** liest so eine Datei wieder ein – wahlweise ersetzend oder anhängend.
- **CSV** exportiert den angezeigten Zeitraum für Excel (Semikolon, Komma als Dezimaltrenner).

Für ein Backup reicht es, `zeiterfassung.db` oder die JSON-Sicherung zu kopieren.

### Automatische Kopien

Zusätzlich legt die App selbst Kopien an – einmal am Tag beim Öffnen, außerdem immer
bevor ein Import die vorhandenen Einträge ersetzt. Die letzten zehn Stände bleiben
erhalten, ältere werden automatisch entfernt.

- Mit Server liegen sie als JSON-Dateien im Ordner `zeiterfassung-sicherungen`
  neben der Datenbank.
- Ohne Server (Handy) liegen sie im Browser-Speicher der App.

Unter **Einstellungen → Sicherung & Speicher** stehen die Stände mit Zeitpunkt und
Anlass; „Zurückholen" ersetzt die aktuellen Einträge damit. Der Stand von vorher wird
dabei selbst noch einmal kopiert, das Zurückholen ist also umkehrbar.

Das ersetzt keine Sicherung außerhalb des Geräts: Wer das Handy verliert, verliert auch
die Kopien. Dafür sind „Sicherung (JSON)" und „Teilen" gedacht.

### Speicher am Handy

Android und iOS dürfen Browserdaten löschen, wenn der Speicher knapp wird. Die App
bittet beim Start um dauerhaften Speicher (`navigator.storage.persist()`); die Chance
darauf steigt deutlich, wenn die App zum Home-Bildschirm hinzugefügt wurde. Unter
**Einstellungen → Sicherung & Speicher** steht, ob das geklappt hat und wie viel Platz
belegt ist. Wird der freie Platz kleiner als 5 MB, warnt die App.

## Aufbau

```
app.py                     Server, API und Berechnungslogik (nur Standardbibliothek)
static/index.html          Oberfläche, läuft mit und ohne Server
static/lokal.js            dieselbe Rechenlogik in JavaScript, für den Betrieb ohne Server
static/sw.js               Service Worker, macht die Handy-App offlinefähig
static/manifest.webmanifest Angaben zur Installation am Handy
test_api.py                End-to-End-Test gegen den laufenden Server
test_lokal.py              vergleicht beide Rechenkerne Zeile für Zeile
test_oberflaeche.py        klickt die ganze Oberfläche durch (PC und Handy)
test_bestand.py            rechnet einen alten Datenstand gegen den neuen
test_handy_umstieg.py      dasselbe im Browser, mit echtem Gerätespeicher
test_update.py             prüft, ob eine installierte App die neue Fassung bekommt
zeiterfassung.db           wird beim ersten Start angelegt
zeiterfassung-sicherungen/ automatische Kopien, die letzten zehn Stände
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
| GET | `/api/auswertung?von=&bis=&job=` | Ist, Soll, Saldo, Tage, Projekte, Kennzahlen |
| GET | `/api/feiertage?jahr=` | Feiertage des Jahres mit Status |
| POST | `/api/feiertage` | Feiertage eines Jahres eintragen |
| POST | `/api/auffuellen` | Offene Arbeitstage mit Standardzeiten füllen |
| POST | `/api/dienste` | Dienst anlegen; `bis` nur bei Dienstarten ohne Wochenrhythmus |
| GET | `/api/stempel` | Laufende Zeitmessung abfragen |
| POST | `/api/stempel/start` | Zeitmessung starten |
| POST | `/api/stempel/pause` | Pause an- oder abschalten |
| POST | `/api/stempel/stop` | Zeitmessung beenden oder verwerfen |
| GET | `/api/sicherungen` | Liste der automatischen Kopien |
| POST | `/api/sicherungen` | Kopie anlegen (`nur_wenn_aelter_als` in Stunden) |
| POST | `/api/sicherungen/wiederherstellen` | Stand zurückholen |
| GET | `/api/export.json` / `/api/export.csv` | Export |
| POST | `/api/import` | Import |

## Tests

Der Test erwartet einen Server mit **leerer** Datenbank:

```bash
python3 app.py --db test.db --no-browser   # Terminal 1
python3 test_api.py                        # Terminal 2
```

Läuft der Server auf einem anderen Port: `ZEIT_URL=http://127.0.0.1:9000 python3 test_api.py`

249 Prüfungen: Anlegen, Ändern, Löschen, Fehlerfälle, Nachtschichten, halbe Urlaubstage,
Saldoberechnung, Jobs, Stempeluhr, Notizvorlagen, Dienste mit Wochenrhythmus, Ausfahrten,
automatische Sicherungen, Export und Import sowie die Feiertagstermine 2026 und 2027 gegen
die offizielle Liste der Stadt Wien.

Die übrigen Testdateien brauchen zusätzlich `playwright` und einen Browser:

```bash
pip install playwright && playwright install chromium
python3 test_lokal.py                      # beide Rechenkerne vergleichen
python3 test_oberflaeche.py http://127.0.0.1:8765 pc
python3 test_oberflaeche.py http://127.0.0.1:8765 handy
```

`test_bestand.py`, `test_handy_umstieg.py` und `test_update.py` vergleichen gegen eine
ältere Fassung; der Pfad dorthin kommt aus `ALT_DIR` bzw. `ALT_STATIC`.

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
