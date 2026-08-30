# Entscheidungen

Was hier steht, ist **entschieden**. Der Loop meldet es nicht erneut.

Nur Menschen schreiben in diese Datei. Der Loop liest sie zu Beginn jedes Laufs
und behandelt jeden Eintrag mit Status `erledigt` oder `ignorieren` als
abgeschlossen — auch wenn die Ursache im Repo noch sichtbar ist.

## Format

```
### <finding-id>
- **Entschieden am:** YYYY-MM-DD
- **Status:** erledigt | ignorieren | vertagt bis YYYY-MM-DD
- **Begruendung:** ein bis zwei Saetze
```

`finding-id` ist die `id` aus `loop-cursor.json`.

---

<!-- Eintraege unterhalb dieser Zeile. Neueste oben. -->

### beispiel-eintrag
- **Entschieden am:** 2026-08-30
- **Status:** ignorieren
- **Begruendung:** Platzhalter, damit das Format sichtbar ist. Kann geloescht werden,
  sobald die erste echte Entscheidung eingetragen ist.
