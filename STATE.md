# Loop State — Arbeitszeiterfassung

Last run: 2026-08-31 (Lauf 3, automatisch, scheduled)  ·  Level: L1 (report-only)

## High Priority (loop is acting or waiting on human)

- [ ] **ESKALATION: Release-Entscheidung steht seit 3 Laeufen in Folge aus.**
  Laut eigener Regel in `loop-critique.md` ("Wenn sich ein Eintrag drei Laeufe
  hintereinander wiederholt, gehoert das Thema als High Priority in STATE.md —
  der Loop kommt allein nicht weiter.") ist dieser Punkt jetzt erreicht.
  `loop-decisions.md` enthaelt weiterhin nur den Platzhalter-Eintrag, keine
  echte Entscheidung zu `workflows-duplikat-release`. Der Loop kann diesen
  Befund nicht selbst aufloesen — er braucht eine Entscheidung eines Menschen
  in `loop-decisions.md` (Status `erledigt` oder `ignorieren` oder `vertagt
  bis YYYY-MM-DD`), sonst wird er unveraendert weiter gemeldet.

- [ ] **Der aktive Release-Workflow ist die alte Version ohne Passwortschutz.** (unveraendert, id: `workflows-duplikat-release`)
  Es gibt zwei Verzeichnisse: `.github/workflows/` (von GitHub gelesen) und
  `workflows/` im Wurzelverzeichnis (**wird nie ausgefuehrt**).
  `workflows/release.yml` ist neuer (2026-08-21) und kann per Secret
  `PAKET_PASSWORT` ein AES-256-verschluesseltes .7z bauen statt eines offenen ZIP.
  `.github/workflows/release.yml` ist aelter (2026-08-17) und baut **immer** ein
  offenes ZIP. Sobald ein Tag `v*` gepusht wird, entsteht ein offenes ZIP, auch
  wenn `PAKET_PASSWORT` gesetzt ist. Repo ist oeffentlich.
  Aktuell nicht akut: weiterhin keine Tags, keine Releases (geprueft).
  Loop action: keine (L1). Mensch: entscheiden, welche Version gilt, und
  `workflows/` entweder loeschen oder nach `.github/workflows/` uebernehmen,
  und die Entscheidung in `loop-decisions.md` eintragen.
  Seit Lauf 1 (2026-08-30) keine Aenderung, keine Entscheidung.

## Watch List

- **`workflows/ci.yml` ist ein exaktes Duplikat**, `workflows/pages.yml` existiert nur dort
  und laeuft daher nie. Pages wird ueber den eingebauten Branch-Build ausgeliefert
  (`pages-build-deployment`, zuletzt gruen). Faellt mit dem High-Priority-Punkt zusammen.
  Unveraendert. (id: `workflows-duplikat-pages-ci`)

- **5 von 6 Testdateien laufen nie in CI.** `ci.yml` fuehrt nur `test_api.py` aus.
  Nicht abgedeckt: `test_bestand.py`, `test_handy_umstieg.py`, `test_update.py`
  (wirken CI-tauglich) sowie `test_lokal.py`, `test_oberflaeche.py` (laut Namen bewusst
  lokal/UI). Unveraendert. (id: `ci-testluecke`)

- **Lokal fehlt `tzdata`** → 4 Sommerzeit-Tests werden still uebersprungen.
  Lokal gruen ist damit kein Beweis fuer CI-gruen. Behebung: `pip install tzdata`.
  Unveraendert. (id: `tzdata-lokal-fehlt`)

## Recent Noise (ignored this run)

- Kein neuer Commit seit dem Wasserzeichen (`0322d4b`) — `origin/main` steht
  weiterhin exakt auf diesem Commit. `git log 0322d4b..origin/main` liefert
  keine Zeilen.
- Kein neuer CI-Lauf: der letzte Workflow-Run (`build`, id 33325327244) ist
  weiterhin derselbe wie im Wasserzeichen, Status **success**.
- Keine offenen Issues, keine offenen Pull Requests (GitHub MCP geprueft).
- Keine Tags, keine Releases (GitHub MCP geprueft).
- `loop-decisions.md` enthaelt weiterhin nur den Platzhalter-Eintrag — siehe
  Eskalation oben.

## Verifizierte Baseline (fuer L2, aus vorherigem Lauf uebernommen)

- `python test_api.py` gegen isolierten Port 8791 + Wegwerf-DB: **258 ok, 0 Fehler, 4 uebersprungen**, Exit 0.
- Dieser Lauf hat keinen neuen Testlauf ausgeloest — kein Anwendungscode hat sich
  seit dem letzten Lauf geaendert, ein erneuter Testlauf haette nichts Neues gezeigt.
- Bindende Regel bleibt: `test_api.py` **nie ohne gesetztes `ZEIT_URL`** starten
  (Default-Ziel Port 8765 = echter Server, `POST /api/import modus=ersetzen`
  ueberschreibt echte Daten).

## Post-Run Critique

- 0 neue Befunde, 4 uebernommene offene Befunde (unveraendert gemeldet, nicht als neu),
  0 Fehlalarme, 1 Eskalation (Release-Entscheidung, 3. Lauf in Folge ohne
  menschliche Entscheidung — siehe High Priority).
- Wasserzeichen-Diff (`git log <last_commit_sha>..origin/main`) war leer — kein
  pauschales "letzte 24h" noetig, das Ergebnis waere identisch, aber ohne die
  Garantie, nichts Aelteres zu wiederholen oder zu verlieren.
- `gh` CLI ist in dieser Umgebung nicht installiert (`gh: command not found`);
  GitHub-Signale kamen stattdessen vollstaendig ueber den GitHub-MCP-Server
  (actions_list, list_issues, list_pull_requests, list_tags, list_releases) —
  wie in Lauf 2, kein duenner Bericht ohne diesen Hinweis.

---
Run log: [loop-run-log.md](./loop-run-log.md)
