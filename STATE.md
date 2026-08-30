# Loop State — Arbeitszeiterfassung

Last run: 2026-08-30 17:30 UTC  ·  Level: L1 (report-only)

## High Priority (loop is acting or waiting on human)

- [ ] **Der aktive Release-Workflow ist die alte Version ohne Passwortschutz.** (bereits bekannt, unveraendert)
  Es gibt zwei Verzeichnisse: `.github/workflows/` (von GitHub gelesen) und
  `workflows/` im Wurzelverzeichnis (**wird nie ausgefuehrt**).
  `workflows/release.yml` ist neuer (2026-08-21) und kann per Secret
  `PAKET_PASSWORT` ein AES-256-verschluesseltes .7z bauen statt eines offenen ZIP.
  `.github/workflows/release.yml` ist aelter (2026-08-17) und baut **immer** ein
  offenes ZIP. Sobald ein Tag `v*` gepusht wird, entsteht ein offenes ZIP, auch
  wenn `PAKET_PASSWORT` gesetzt ist. Repo ist oeffentlich.
  Aktuell nicht akut: weiterhin keine Tags, keine Releases (geprueft).
  Loop action: keine (L1). Mensch: entscheiden, welche Version gilt, und
  `workflows/` entweder loeschen oder nach `.github/workflows/` uebernehmen.
  Seit dem letzten Lauf keine Aenderung, keine Entscheidung in `loop-decisions.md`.

## Watch List

- **`workflows/ci.yml` ist ein exaktes Duplikat**, `workflows/pages.yml` existiert nur dort
  und laeuft daher nie. Pages wird ueber den eingebauten Branch-Build ausgeliefert
  (`pages-build-deployment`, zuletzt gruen). Faellt mit dem High-Priority-Punkt zusammen.
  Unveraendert.

- **5 von 6 Testdateien laufen nie in CI.** `ci.yml` fuehrt nur `test_api.py` aus.
  Nicht abgedeckt: `test_bestand.py`, `test_handy_umstieg.py`, `test_update.py`
  (wirken CI-tauglich) sowie `test_lokal.py`, `test_oberflaeche.py` (laut Namen bewusst
  lokal/UI). Unveraendert.

- **Lokal fehlt `tzdata`** → 4 Sommerzeit-Tests werden still uebersprungen.
  Lokal gruen ist damit kein Beweis fuer CI-gruen. Behebung: `pip install tzdata`.
  Unveraendert.

## Recent Noise (ignored this run)

- Einziger neuer Commit seit dem letzten Wasserzeichen (`9211a00`) ist
  `0322d4b` "Daily-Triage Loop einrichten (L1 report-only) (#1)" — genau der Merge,
  der die Loop-Dateien selbst angelegt hat. Kein Anwendungscode betroffen.
- Dazugehoeriger CI-Lauf (`build`, run 33325327244) auf `main`: **success**.
- Keine offenen Issues, keine offenen Pull Requests (GitHub MCP geprueft).
- Keine Tags, keine Releases seit letztem Lauf.
- `loop-decisions.md` enthaelt nur den Platzhalter-Eintrag — noch keine echte
  Entscheidung eines Menschen zu einem der offenen Befunde.

## Verifizierte Baseline (fuer L2, aus letztem Lauf uebernommen)

- `python test_api.py` gegen isolierten Port 8791 + Wegwerf-DB: **258 ok, 0 Fehler, 4 uebersprungen**, Exit 0.
- Dieser Lauf hat keinen neuen Testlauf ausgeloest — kein Anwendungscode hat sich
  seit dem letzten Lauf geaendert, ein erneuter Testlauf haette nichts Neues gezeigt.
- Bindende Regel bleibt: `test_api.py` **nie ohne gesetztes `ZEIT_URL`** starten
  (Default-Ziel Port 8765 = echter Server, `POST /api/import modus=ersetzen`
  ueberschreibt echte Daten).

## Post-Run Critique

- 0 neue Befunde, 4 uebernommene offene Befunde (unveraendert gemeldet, nicht als neu),
  0 Fehlalarme.
- Wasserzeichen-Diff (`git log <last_commit_sha>..origin/main`) hat sauber nur einen
  Commit gezeigt, und der war der Loop-Setup-Commit selbst — kein pauschales
  "letzte 24h" noetig, das haette denselben Commit gezeigt, aber ohne die Garantie,
  nichts Aelteres zu wiederholen.
- `gh` CLI ist in dieser Umgebung nicht installiert; GitHub-Signale kamen stattdessen
  ueber den GitHub-MCP-Server (Actions, Issues, PRs) — funktioniert, aber CI-Job-Logs
  wurden diesmal nicht einzeln gepruegt, da der einzige neue Lauf ohnehin gruen war.

---
Run log: [loop-run-log.md](./loop-run-log.md)
