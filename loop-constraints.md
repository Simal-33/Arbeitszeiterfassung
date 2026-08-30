# Loop Constraints

> Add rules below with `/constraints <rule>` in your agent.
> The `loop-constraints` skill reads this file at the start of every run.
> Constraints here are **binding** — the agent MUST follow them.

## Push & Merge
- Don't push before telling me
- Never auto-merge to main without human approval
- Always create a draft PR first; let me review before marking ready

## Paths
- Never edit .env, .env.*, auth/, payments/, secrets/, credentials/
- Never edit infrastructure configs without human approval

## Code
- Always run tests before proposing a fix
- Never disable tests to make CI green
- Never refactor unrelated code — one fix per run
- Max 3 fix attempts per item; escalate after
- Enforce the attempt limit mechanically: log each try to `loop-ledger.json` and run `loop-context --check` before retrying (see the `loop-guard` skill)

## Communication
- Always tell me what you're about to do before doing it
- Never close an issue or PR without my approval

## Budget
- If token spend hits 80% of daily cap, switch to report-only
- If loop-pause-all is active, exit immediately

---
<!-- Add your own rules below. Use plain English. The loop reads this verbatim. -->

## Gedaechtnis (bindend)
- Zu Beginn JEDES Laufs lesen: `loop-cursor.json`, `loop-decisions.md`, `loop-critique.md`, `STATE.md`
- Nur betrachten, was **neuer** ist als `last_commit_sha` / `last_ci_run_id` aus `loop-cursor.json`.
  Kein pauschales "letzte 24h" — das verliert oder wiederholt Befunde.
- Ein Befund, dessen `id` in `loop-decisions.md` auf `erledigt` oder `ignorieren` steht,
  wird NICHT erneut gemeldet, auch wenn die Ursache im Repo noch sichtbar ist.
- Ein Befund, der in `loop-cursor.json` schon als `offen` steht, wird in STATE.md
  uebernommen, aber nicht als neu ausgegeben.
- Am Ende jedes Laufs: `loop-cursor.json` fortschreiben (Wasserzeichen + Befundliste)
  und einen Absatz an `loop-critique.md` anhaengen. `loop-critique.md` wird nie gekuerzt.
- `loop-decisions.md` schreiben ausschliesslich Menschen. Der Loop liest sie nur.

## Projektspezifisch — Arbeitszeiterfassung
- Niemals `*.db` anfassen (Produktiv- und Testdatenbanken), niemals committen
- Niemals `__pycache__/` committen
- Tests sind Python: `python test_api.py` etc. — kein `npm test`
- **Niemals `test_api.py` ohne gesetztes `ZEIT_URL` starten.** Der Test macht
  `POST /api/import` mit `modus: "ersetzen"` und überschreibt alle Einträge des
  Servers, den er erreicht. Default-Ziel ist Port 8765 = Default-Port der echten App.
- Vor jedem Testlauf: freien Port wählen, eigene Wegwerf-DB, danach beenden und löschen.
  `python app.py --port 8791 --db /tmp/test.db --no-browser` +
  `ZEIT_URL=http://127.0.0.1:8791 python test_api.py`
- Vor dem Testlauf prüfen, ob der Zielport frei ist. Belegt = abbrechen, nicht ausweichen.
- Baseline ist 258 ok / 0 Fehler. Weniger als 258 ok = etwas übersprungen, nicht grün.
- Lokal fehlt `tzdata` → 4 Sommerzeit-Tests werden still übersprungen. Lokal grün
  ist kein Beweis für CI-grün.
