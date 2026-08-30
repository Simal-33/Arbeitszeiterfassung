# Loop State — Arbeitszeiterfassung

Last run: 2026-08-30 16:51 UTC  ·  Level: L1 (report-only)

## High Priority (loop is acting or waiting on human)

- [ ] **Der aktive Release-Workflow ist die alte Version ohne Passwortschutz.**
  Es gibt zwei Verzeichnisse: `.github/workflows/` (von GitHub gelesen) und
  `workflows/` im Wurzelverzeichnis (**wird nie ausgefuehrt**).
  `workflows/release.yml` ist neuer (2026-08-21) und kann per Secret
  `PAKET_PASSWORT` ein AES-256-verschluesseltes .7z bauen statt eines offenen ZIP —
  inklusive Gegenprobe, dass die Verschluesselung greift.
  `.github/workflows/release.yml` ist aelter und baut **immer** ein offenes ZIP.
  Warum es zaehlt: Sobald ein Tag `v*` gepusht wird, entsteht ein offenes ZIP,
  auch wenn `PAKET_PASSWORT` gesetzt ist. Repo ist oeffentlich.
  Aktuell nicht akut: keine Tags, keine Releases, kein Secret gesetzt — noch ist
  nichts falsch veroeffentlicht worden.
  Loop action: keine (L1). Mensch: entscheiden, welche Version gilt, und
  `workflows/` entweder loeschen oder nach `.github/workflows/` uebernehmen.
  Aufwand: klein (Datei verschieben), aber Entscheidung noetig.

## Watch List

- **`workflows/ci.yml` ist ein exaktes Duplikat**, `workflows/pages.yml` existiert nur dort
  und laeuft daher nie. Pages wird ueber den eingebauten Branch-Build ausgeliefert
  (`pages-build-deployment`, zuletzt 2026-08-22 gruen) — pages.yml ist Altlast.
  Loop action: keine. Faellt mit dem High-Priority-Punkt zusammen.

- **5 von 6 Testdateien laufen nie in CI.** `ci.yml` fuehrt nur `test_api.py` aus.
  Nicht abgedeckt: `test_bestand.py`, `test_handy_umstieg.py`, `test_update.py`
  (wirken CI-tauglich) sowie `test_lokal.py`, `test_oberflaeche.py` (laut Namen bewusst lokal/UI).

- **Lokal fehlt `tzdata`** → 4 Sommerzeit-Tests werden still uebersprungen.
  Lokal gruen ist damit kein Beweis fuer CI-gruen. Behebung: `pip install tzdata`.

## Recent Noise (ignored this run)

- Letzte 10 CI-Laeufe alle `success`, keine offenen Issues, keine offenen PRs.
- `.gitignore` deckt `*.db`, `__pycache__/`, Exporte korrekt ab — nichts geleakt. Geprueft.
- Letzter Commit 2026-08-22, seither ruhig. Kein Problem, nur Kontext.

## Verifizierte Baseline (fuer L2)

- `python test_api.py` gegen isolierten Port 8791 + Wegwerf-DB: **258 ok, 0 Fehler, 4 uebersprungen**, Exit 0.
- Gefahr dabei entdeckt: `test_api.py` zielt per Default auf Port 8765 = Default-Port
  der echten App und macht `POST /api/import` mit `modus: "ersetzen"`.
  Ohne `ZEIT_URL` ueberschreibt ein Testlauf echte Arbeitszeiten.
  Als bindende Regel in `loop-constraints.md` und `AGENTS.md` hinterlegt.

## Post-Run Critique

- 1 High Priority, 3 Watch, 0 False Positives.
- Der Release-Fund kam nur zustande, weil beim Schreiben von `gate.yaml` die
  Denylist gegen `git ls-files` gegengeprueft wurde. Solche Gegenproben gehoeren
  in jeden Lauf, nicht nur beim Einrichten.
- Anpassung fuer naechsten Lauf: Watch-Items nicht erneut melden, solange
  `ci.yml` und `workflows/` unveraendert bleiben. High Priority bleibt offen,
  bis ein Mensch entschieden hat.

---
Run log: [loop-run-log.md](./loop-run-log.md)
