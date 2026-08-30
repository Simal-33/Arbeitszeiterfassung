# AGENTS.md — Arbeitszeiterfassung

Python-Projekt (`app.py`, stdlib-HTTP-Server). Kein Node, kein npm.

## Test commands

> **WARNUNG — niemals `python test_api.py` ohne `ZEIT_URL` starten.**
> Der Test zielt per Default auf `http://127.0.0.1:8765` — das ist der Default-Port
> von `app.py`. Er sendet `POST /api/import` mit `modus: "ersetzen"` und überschreibt
> damit **alle Einträge** des Servers, den er erreicht. Läuft die normale App
> (DB `zeiterfassung.db`), zerstört ein unachtsamer Testlauf echte Arbeitszeiten.
> Immer eigenen Port + eigene DB verwenden:

```bash
# 1. Syntax-Check (wie CI)
python -m compileall -q app.py test_api.py

# 2. Wegwerf-Server auf freiem Port mit eigener DB
python app.py --port 8791 --db /tmp/test.db --no-browser &

# 3. Tests explizit gegen diesen Port
ZEIT_URL=http://127.0.0.1:8791 python test_api.py

# 4. Server danach beenden, /tmp/test.db löschen
```

Erwartete Baseline (Stand 2026-08-30, Python 3.14 lokal): **258 ok, 0 Fehler, 4 übersprungen**.

### Lokal übersprungene Tests

4 Sommerzeit-Tests überspringen unter Windows mangels Zeitzonendatenbank
("keine Zeitzonendatenbank vorhanden"). In CI (Linux) laufen sie.
Behebung: `pip install tzdata`. **Lokal grün heißt ohne tzdata nicht CI-grün.**

### Nicht in CI abgedeckt

`.github/workflows/ci.yml` führt nur `test_api.py` aus. Diese Dateien laufen nie in CI:
`test_bestand.py`, `test_handy_umstieg.py`, `test_update.py`,
`test_lokal.py`, `test_oberflaeche.py` (letzte zwei laut Namen bewusst lokal/UI).

## Projekt-Notizen für Agents

- Einstiegspunkt: `app.py`. Frontend: `index.html` + `static/`.
- `*.db` sind Datenbanken (auch Testläufe) — nie committen, nie editieren.
- CI-Matrix: Python 3.9 / 3.11 / 3.13. Lokal liegt 3.14 — neuer als jede CI-Version.

## Loop conventions

- Report-only Woche eins (L1), erst danach Auto-Fix (L2).
- Cadence und Human Gates: siehe `LOOP.md`.
- Bindende Regeln: siehe `loop-constraints.md`.
