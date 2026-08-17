#!/usr/bin/env python3
"""Kleiner End-to-End-Test gegen den laufenden Server (python3 app.py --port 8765)."""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
ok, fail = 0, 0


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (json.loads(raw) if raw.strip().startswith("{") else raw)


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print("  ok   %-46s %s" % (name, got))
    else:
        fail += 1
        print("  FAIL %-46s got=%r want=%r" % (name, got, want))


print("Einstellungen")
s, r = call("PUT", "/api/einstellungen", {
    "soll": {"1": 8, "2": 8, "3": 8, "4": 8, "5": 8, "6": 0, "7": 0},
    "startsaldo": 2.5, "startdatum": "2026-08-01", "name": "Markus"})
check("PUT /api/einstellungen", s, 200)
check("Soll Montag", r["soll"]["1"], 8.0)
check("Startsaldo", r["startsaldo"], 2.5)

print("\nEintraege anlegen")
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-03", "typ": "arbeit",
                                       "von": "08:00", "bis": "17:00", "pause": 45,
                                       "projekt": "Kunde A"})
check("Arbeitstag Mo angelegt", s, 201)
id1 = r["id"]
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-04", "typ": "urlaub"})
check("Urlaubstag angelegt", s, 201)
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-05", "typ": "arbeit",
                                       "von": "22:00", "bis": "06:00", "pause": 30,
                                       "projekt": "Kunde B"})
check("Nachtschicht angelegt", s, 201)
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-06", "typ": "urlaub",
                                       "von": "08:00", "bis": "12:00", "pause": 0})
check("halber Urlaubstag angelegt", s, 201)
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-08", "typ": "arbeit",
                                       "von": "10:00", "bis": "13:00", "pause": 0})
check("Samstagsarbeit angelegt", s, 201)

print("\nFehlerfaelle")
s, r = call("POST", "/api/eintraege", {"datum": "2026-02-30", "typ": "arbeit",
                                       "von": "08:00", "bis": "16:00"})
check("ungueltiges Datum -> 400", s, 400)
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-10", "typ": "arbeit"})
check("Arbeit ohne Zeiten -> 400", s, 400)
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-10", "typ": "arbeit",
                                       "von": "08:00", "bis": "09:00", "pause": 120})
check("Pause > Zeitspanne -> 400", s, 400)
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-10", "typ": "quatsch",
                                       "von": "08:00", "bis": "09:00"})
check("unbekannte Art -> 400", s, 400)
s, r = call("PUT", "/api/eintraege/99999", {"datum": "2026-08-10", "typ": "arbeit",
                                            "von": "08:00", "bis": "09:00"})
check("Update unbekannte ID -> 404", s, 404)
s, r = call("GET", "/api/auswertung?von=2026-08-31&bis=2026-08-01")
check("verdrehter Zeitraum -> 400", s, 400)

print("\nAuswertung August 2026")
s, a = call("GET", "/api/auswertung?von=2026-08-01&bis=2026-08-31")
check("Status", s, 200)
# Ist: Mo 8:00-17:00 -45 = 495 ; Nachtschicht 22-06 -30 = 450 ; Sa 10-13 = 180
check("Ist gesamt (Minuten)", a["ist"], 495 + 450 + 180)
# Gutschrift: ganzer Urlaubstag 480 + halber 240
check("Gutschrift (Minuten)", a["gutschrift"], 480 + 240)
# Soll zaehlt nur Werktage bis heute (bzw. bis zum letzten Eintrag)
import datetime as _dt
_grenze = max(_dt.date.today(), _dt.date(2026, 8, 8))
_werktage = sum(
    1 for i in range(31)
    if (_d := _dt.date(2026, 8, 1) + _dt.timedelta(days=i)).isoweekday() <= 5 and _d <= _grenze
)
check("Soll (Minuten)", a["soll"], _werktage * 480)
check("Saldo", a["saldo"], (495 + 450 + 180) + (480 + 240) - _werktage * 480)
check("Tage mit Eintraegen", len(a["tage"]), 5)
tag = {t["datum"]: t for t in a["tage"]}
check("Mo 03.08. Saldo +15", tag["2026-08-03"]["saldo"], 15)
check("Urlaubstag Saldo 0", tag["2026-08-04"]["saldo"], 0)
check("Nachtschicht Dauer", tag["2026-08-05"]["ist"], 450)
check("halber Urlaub Saldo", tag["2026-08-06"]["saldo"], 240 - 480)
check("Samstag Soll 0", tag["2026-08-08"]["soll"], 0)
check("Samstag Saldo +180", tag["2026-08-08"]["saldo"], 180)
check("Projekte sortiert", [p["projekt"] for p in a["projekte"]],
      ["Kunde A", "Kunde B", "(ohne Projekt)"])
check("Projekt Kunde A", a["projekte"][0]["minuten"], 495)

print("\nGesamtsaldo (inkl. Startsaldo 2,5 h)")
# Zeitraum 01.08.-08.08.: Werktage Mo-Fr = 3.,4.,5.,6.,7. -> 5*480 = 2400
erwartet = (495 + 450 + 180 + 480 + 240) - 2400 + 150
check("Gesamtsaldo", a["gesamtsaldo"], erwartet)

print("\nBearbeiten und Loeschen")
s, r = call("PUT", "/api/eintraege/%d" % id1, {"datum": "2026-08-03", "typ": "arbeit",
                                               "von": "08:00", "bis": "16:00", "pause": 30,
                                               "projekt": "Kunde A", "notiz": "korrigiert"})
check("Update Status", s, 200)
check("Notiz gespeichert", r["notiz"], "korrigiert")
s, a2 = call("GET", "/api/auswertung?von=2026-08-03&bis=2026-08-03")
check("Tagesdauer nach Update", a2["ist"], 450)
s, r = call("DELETE", "/api/eintraege/%d" % id1)
check("Delete Status", s, 200)
s, a3 = call("GET", "/api/auswertung?von=2026-08-03&bis=2026-08-03")
check("nach Loeschen leer", a3["ist"], 0)
s, r = call("DELETE", "/api/eintraege/%d" % id1)
check("erneutes Delete -> 404", s, 404)

print("\nExport / Import")
s, exp = call("GET", "/api/export.json")
check("Export Status", s, 200)
check("Eintraege im Export", len(exp["eintraege"]), 4)
s, csv_text = call("GET", "/api/export.csv?von=2026-08-01&bis=2026-08-31")
check("CSV Status", s, 200)
check("CSV Zeilen", len(csv_text.strip().splitlines()), 5)
check("CSV Semikolon-Header", csv_text.strip().splitlines()[0].startswith("﻿Datum;"), True)
s, r = call("POST", "/api/import", {"modus": "ersetzen", "daten": exp})
check("Import Status", s, 200)
check("Importiert", r["importiert"], 4)
s, e = call("GET", "/api/eintraege")
check("Nach Import unveraendert", len(e), 4)
s, r = call("POST", "/api/import", {"modus": "anhaengen", "daten": exp})
s, e = call("GET", "/api/eintraege")
check("Nach Anhaengen verdoppelt", len(e), 8)
s, r = call("POST", "/api/import", {"modus": "ersetzen", "daten": {"quatsch": 1}})
check("Import ohne Eintraege -> 400", s, 400)

print("\nStatische Dateien")
s, html = call("GET", "/")
check("Index geladen", s, 200)
check("Index enthaelt Titel", "<title>Zeiterfassung</title>" in html, True)
s, r = call("GET", "/../app.py")
check("Pfad-Traversal blockiert", s, 404)

print("\n%d ok, %d Fehler" % (ok, fail))
raise SystemExit(1 if fail else 0)
