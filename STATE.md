# Loop State — Arbeitszeiterfassung

Last run: 2026-08-30 16:34 UTC  ·  Level: L1 (report-only)

## High Priority (loop is acting or waiting on human)

_(keine)_ — CI grün, keine offenen Issues, keine offenen PRs.

## Watch List

- **5 von 6 Testdateien laufen nie in CI.**
  `.github/workflows/ci.yml` führt nur `test_api.py` aus (plus `compileall` auf `app.py`/`test_api.py`).
  Nicht abgedeckt: `test_bestand.py`, `test_handy_umstieg.py`, `test_update.py`,
  `test_lokal.py`, `test_oberflaeche.py`.
  Warum es zählt: Regressionen in Bestand, Handy-Umstieg und Update-Pfad fallen erst lokal auf.
  Hinweis: `test_lokal.py`/`test_oberflaeche.py` sind laut Namen bewusst lokal/UI — die drei
  anderen wirken CI-tauglich.
  Loop action: keine (L1). Vorschlag für Mensch: prüfen, welche der drei in CI gehören.
  Aufwand: klein (Workflow-Schritt ergänzen).

- **Repo seit 2026-08-22 ohne Commit** (8 Tage). Kein Problem, nur Kontext für die nächsten Läufe.

## Recent Noise (ignored this run)

- Letzte 10 CI-Läufe alle `success` — nichts zu tun.
- `pages-build-deployment` Läufe: automatisch, kein Signal.
- `.gitignore` deckt `*.db`, `__pycache__/`, Exporte korrekt ab — keine Leaks getrackt. Geprüft, sauber.

## Post-Run Critique

- Erster Lauf mit echten Signalquellen: 1 Watch-Item, 0 False Positives, 0 High Priority.
- Die CI-Lücke wurde nur gefunden, weil Workflow-Datei gegen `git ls-files test_*.py` geprüft wurde —
  dieser Abgleich gehört fest in den nächsten Lauf.
- Anpassung für nächsten Lauf: Watch-Item nicht erneut melden, solange `ci.yml` unverändert bleibt.

---
Run log: [loop-run-log.md](./loop-run-log.md)
