# Selbstkritik des Loops

Append-only. Der Loop haengt nach jedem Lauf einen Absatz an und **loescht nie**.
Damit wird sichtbar, ob er ueber die Zeit besser wird oder dieselben Fehler wiederholt.

Wenn sich ein Eintrag drei Laeufe hintereinander wiederholt, gehoert das Thema
als High Priority in STATE.md — der Loop kommt allein nicht weiter.

---

## 2026-08-30 — Lauf 1 (manuell, lokal)

- 1 High Priority, 3 Watch, 0 Fehlalarme.
- Der Release-Fund kam nur zustande, weil beim Schreiben von `gate.yaml` die
  Denylist gegen `git ls-files` gegengeprueft wurde. Solche Gegenproben gehoeren
  in jeden Lauf, nicht nur ins Setup.
- Die Testbaseline war anfangs falsch dokumentiert (npm statt Python), weil sie
  aus einem Template uebernommen und nicht geprueft wurde. Lehre: keine
  Testbefehle uebernehmen, ohne sie einmal auszufuehren.

## 2026-08-30 — Lauf 2 (automatisch, scheduled)

- 0 neue Befunde, 4 uebernommene offene Befunde, 0 Fehlalarme, kein Testlauf
  ausgeloest.
- Das Wasserzeichen hat diesmal funktioniert wie gedacht: `git log
  <last_commit_sha>..origin/main` zeigte genau einen Commit, und der war der
  Loop-Setup-Commit selbst, der die Gedaechtnis-Dateien angelegt hat — kein
  Anwendungscode. Damit war klar, dass kein neuer Testlauf noetig war, ohne
  dass ich raten musste.
  Kein pauschales "letzte 24h" verwendet.
- `gh` CLI fehlt in dieser Umgebung; GitHub-MCP-Tools (actions_list,
  list_issues, list_pull_requests) haben denselben Zweck erfuellt. Sollte das
  beim naechsten Mal auch fehlen, gilt weiterhin: nicht still triagieren,
  sondern in STATE.md vermerken.
- Offener Punkt fuer L2: `loop-decisions.md` hat weiterhin nur den
  Platzhalter-Eintrag. Der High-Priority-Release-Fund von Lauf 1 wartet jetzt
  seit einem vollen Zyklus auf eine menschliche Entscheidung, ohne dass sich
  am Risiko etwas geaendert hat (weiterhin keine Tags/Releases). Falls das
  drei Laeufe in Folge so bleibt, gehoert laut eigener Regel ein Hinweis
  darauf in STATE.md, dass der Loop hier allein nicht weiterkommt — Lauf 2
  von potenziell 3, noch keine Eskalation noetig.

## 2026-08-31 — Lauf 3 (automatisch, scheduled)

- 0 neue Befunde, 4 uebernommene offene Befunde, 0 Fehlalarme, 1 Eskalation.
- Wasserzeichen-Diff war komplett leer: `origin/main` steht bit-identisch auf
  `0322d4b`, derselbe CI-Lauf, keine neuen Issues/PRs/Tags/Releases. Sauberer
  Fall dafuer, dass das Wasserzeichen-Verfahren funktioniert wie gedacht —
  ohne Wasserzeichen haette ein pauschaler "letzte 24h"-Blick vermutlich
  denselben leeren Befund gebracht, aber ohne die Sicherheit, dass wirklich
  nichts uebersehen wurde.
- Wie in Lauf 2 angekuendigt: Der Release-Fund (`workflows-duplikat-release`)
  steht jetzt den dritten Lauf in Folge ohne Eintrag in `loop-decisions.md`.
  Die eigene Regel aus Lauf 2 ("drei Laeufe in Folge -> explizite Eskalation
  in STATE.md") wurde diesmal tatsaechlich ausgeloest und umgesetzt: STATE.md
  enthaelt jetzt einen eigenen Eskalations-Punkt oben in High Priority, nicht
  nur den unveraenderten Fund selbst. Das ist der erste echte Beweis, dass der
  Loop seine eigene Drei-Laeufe-Regel nicht nur aufschreibt, sondern auch
  anwendet.
- `gh` CLI fehlt weiterhin in dieser Umgebung. GitHub-MCP-Tools haben erneut
  alle benoetigten Signale geliefert (Workflows, Issues, PRs, Tags, Releases).
  Das ist jetzt der zweite Lauf in Folge ohne `gh` — falls das dauerhaft so
  bleibt, waere es an der Zeit, `loop-constraints.md` oder `LOOP.md`
  entsprechend zu praezisieren, statt es jedes Mal neu als Ueberraschung zu
  behandeln.
- Offener Punkt: Auch mit der Eskalation in STATE.md loest der Loop die
  Entscheidung nicht selbst — das ist bewusst so (L1, nur Menschen schreiben
  `loop-decisions.md`). Sollte auch nach dieser expliziten Eskalation in
  STATE.md kein Mensch reagieren, bleibt fraglich, ob ein wiederholter
  STATE.md-Hinweis ueberhaupt noch etwas bewirkt oder ob ein staerkerer Kanal
  (z. B. Issue eroeffnen) noetig waere — aber das waere bereits ausserhalb
  des L1-Mandats (Communication: "immer sagen, bevor man etwas tut", kein
  eigenmaechtiges Issue-Erstellen ohne Ankuendigung).
