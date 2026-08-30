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
