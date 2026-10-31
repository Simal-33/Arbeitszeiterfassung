---
name: sicherer-testlauf
description: >
  Startet die API-Tests der Arbeitszeiterfassung (test_api.py) sicher gegen einen
  Wegwerf-Server mit eigener DB, damit echte Arbeitszeiten nie überschrieben werden,
  und bewertet das Ergebnis gegen die Baseline. Verwende diesen Skill IMMER, bevor du
  test_api.py oder app.py zum Testen startest, also auch bei "lass die Tests laufen",
  "ist das noch grün?", "prüf meine Änderung", vor Commit, Push oder PR, nach einer
  Änderung an app.py, wenn CI rot ist oder wenn jemand nach Port 8765, ZEIT_URL,
  tzdata oder übersprungenen Tests fragt. Auch dann, wenn niemand "Skill" sagt.
---

# Sicherer Testlauf

## Warum das wichtig ist

`test_api.py` schickt `POST /api/import` mit `modus: "ersetzen"` an den Server, den es
erreicht. Ohne `ZEIT_URL` ist das `http://127.0.0.1:8765`, also genau der Default-Port
der echten App mit `zeiterfassung.db`. Ein unachtsamer Lauf ersetzt damit alle Einträge
des Nutzers.

Zwar bricht `test_api.py` selbst ab, wenn der Server schon Einträge hat. Diese Sperre
schaut aber nur auf Einträge: Die Einstellungen (Soll, Startsaldo, Name, Jobs) würden
trotzdem per `PUT /api/einstellungen` überschrieben. Verlass dich also nicht darauf.

## Standardweg: das Skript

Aus dem Projektordner:

```bash
python .claude/skills/sicherer-testlauf/scripts/testlauf.py
```

Das Skript erledigt in einem Durchgang, was `AGENTS.md` als vier Handschritte beschreibt:

1. Syntaxcheck wie in CI (`compileall app.py test_api.py`)
2. Prüft, ob der Port (Default 8791) frei ist. Port 8765 lehnt es grundsätzlich ab.
3. Startet `app.py --no-browser` mit einer DB in einem frischen Temp-Ordner
   (`tempfile`, funktioniert auch unter Windows, wo es kein `/tmp` gibt)
4. Lässt `test_api.py` mit gesetztem `ZEIT_URL` gegen genau diesen Server laufen
5. Beendet den Server und löscht den Temp-Ordner, auch wenn etwas schiefgeht

Optionen: `--port N` für einen anderen Port, `--voll` für die komplette Testausgabe
(sonst nur FAIL-Zeilen, Übersprungenes und die Zusammenfassung).

Exit-Code: `0` alles ok, `1` Testfehler, `2` der Lauf kam gar nicht zustande
(Port belegt, Server startet nicht, Syntaxfehler).

**Port belegt:** abbrechen und dem Menschen melden, was dort läuft. Nicht still auf
einen anderen Port ausweichen (so steht es bindend in `loop-constraints.md`). Ein
belegter Port kann die laufende echte App sein, und die soll jemand bewusst sehen.

## Ergebnis bewerten

Die Baseline steht in `AGENTS.md`. Lies sie dort nach, statt eine Zahl aus dem Kopf zu
nehmen. Was die Zahlen bedeuten:

| Zeitzonendatenbank | Erwartung bei grünem Stand |
|---|---|
| fehlt (Windows ohne `tzdata`) | Baseline-ok, 0 Fehler, **4 übersprungen** |
| vorhanden (Linux, CI) | Baseline-ok **+ 4**, 0 Fehler, 0 übersprungen |

Das Skript zeigt am Anfang, ob die Zeitzonendatenbank da ist.

- **Übersprungen > 0** heißt: lokal grün ist nicht CI-grün. Das gehört in jede
  Erfolgsmeldung. Behebung: `pip install tzdata`.
- **Weniger ok als erwartet bei 0 Fehlern** heißt: Prüfungen sind verloren gegangen,
  das ist nicht grün.
- **Fehler gefunden?** Bevor du sie deiner Änderung zuschreibst, lass denselben Lauf auf
  dem unveränderten Stand laufen (`git stash`, testen, `git stash pop`). Ein Teil der
  Tests rechnet "bis heute" und kann allein durch das Datum kippen.
  Stand 2026-10-21 schlagen auf unverändertem `main` `Gesamtsaldo` und
  `Arbeitstage trotz Dienst gefuellt` fehl (260 ok, 2 Fehler mit tzdata). Prüf, ob das
  noch stimmt, statt es blind zu übernehmen.

## Python-Version

CI testet mit Python 3.9, 3.11 und 3.13. Lokal kann eine neuere Version laufen. Das
Skript nimmt den Interpreter, mit dem du es startest, für Server und Tests. Wenn eine
Änderung neue Syntax oder neue Stdlib-Funktionen nutzt, starte es zusätzlich mit einer
alten Version (z. B. `py -3.9 ...` unter Windows, `python3.9 ...` oder, falls `uv` da
ist, `$(uv python find 3.9) ...`). Wenn keine alte Version da ist, sag dazu, dass die
3.9-Kompatibilität ungeprüft ist.

## Von Hand (falls das Skript nicht passt)

```bash
python -m compileall -q app.py test_api.py
python app.py --port 8791 --db /tmp/test.db --no-browser &   # Windows: DB in %TEMP%
ZEIT_URL=http://127.0.0.1:8791 python test_api.py
# danach Server beenden und die Test-DB löschen
```

## Was nie passieren darf

- `python test_api.py` ohne `ZEIT_URL` starten
- Tests gegen Port 8765 oder gegen `zeiterfassung.db` laufen lassen
- `*.db` (auch Test-DBs) editieren oder committen
- Tests deaktivieren oder überspringen, damit es grün wird

## Andere Testdateien

Nur `test_api.py` läuft in CI. `test_lokal.py`, `test_oberflaeche.py`,
`test_handy_umstieg.py` und `test_update.py` brauchen Playwright. `test_bestand.py`
hat feste Pfade (`/home/claude/...`) und läuft außerhalb dieser Umgebung nicht. Starte
sie nur, wenn jemand ausdrücklich danach fragt, und nenne sie nie als Beleg für "CI grün".

## Rückmeldung an den Menschen

Kurz und ehrlich, etwa so:

```
Testlauf (Python 3.13, tzdata vorhanden, Port 8791, Wegwerf-DB):
260 ok, 2 Fehler, 0 übersprungen. Erwartet: 262 ok.
FAIL Gesamtsaldo, FAIL Arbeitstage trotz Dienst gefuellt.
Auf unverändertem main gleich, also nicht durch diese Änderung.
```
