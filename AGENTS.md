# AGENTS.md — Arbeitszeiterfassung

Python-Projekt (Flask-artig, `app.py`). Kein Node, kein npm.

## Test commands

```bash
# Syntax-Check (wie in CI)
python -m compileall -q app.py test_api.py

# API-Tests: Server muss laufen
python app.py --port 8765 --db ci.db --no-browser &
python test_api.py

# Weitere Testdateien im Root
python test_bestand.py
python test_handy_umstieg.py
python test_update.py
```

CI-Referenz: `.github/workflows/ci.yml` (Matrix: Python 3.9 / 3.11 / 3.13).

## Projekt-Notizen für Agents

- Einstiegspunkt: `app.py`. Frontend: `index.html` + `static/`.
- `*.db` sind Datenbanken (auch `ci.db` aus Testläufen) — nie committen, nie editieren.
- `test_lokal.py` und `test_oberflaeche.py` sind lokale/UI-Tests, laufen nicht in CI.

## Loop conventions

- Report-only Woche eins (L1), erst danach Auto-Fix (L2).
- Cadence und Human Gates: siehe `LOOP.md`.
- Bindende Regeln: siehe `loop-constraints.md`.
