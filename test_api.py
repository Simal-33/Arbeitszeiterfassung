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


_status, _vorhandene = call("GET", "/api/eintraege")
if _status != 200:
    raise SystemExit("Server nicht erreichbar auf %s - bitte zuerst 'python3 app.py' starten." % BASE)
if _vorhandene:
    raise SystemExit(
        "Der Test braucht eine leere Datenbank (gefunden: %d Eintraege).\n"
        "Server mit einer frischen Datei starten, z. B.:\n"
        "  python3 app.py --db test.db --no-browser" % len(_vorhandene))

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

print("\nFeiertage Oesterreich (Berechnung)")
import app as _app
_soll_2026 = {
    "2026-01-01": "Neujahr", "2026-01-06": "Heilige Drei Koenige",
    "2026-04-06": "Ostermontag", "2026-05-01": "Staatsfeiertag",
    "2026-05-14": "Christi Himmelfahrt", "2026-05-25": "Pfingstmontag",
    "2026-06-04": "Fronleichnam", "2026-08-15": "Mariae Himmelfahrt",
    "2026-10-26": "Nationalfeiertag", "2026-11-01": "Allerheiligen",
    "2026-12-08": "Mariae Empfaengnis", "2026-12-25": "Christtag",
    "2026-12-26": "Stefanitag",
}
_soll_2027 = ["2027-01-01", "2027-01-06", "2027-03-29", "2027-05-01", "2027-05-06",
              "2027-05-17", "2027-05-27", "2027-08-15", "2027-10-26", "2027-11-01",
              "2027-12-08", "2027-12-25", "2027-12-26"]
check("13 Feiertage 2026", len(_app.feiertage_at(2026)), 13)
check("Termine 2026 (Stadt Wien)",
      {f["datum"]: f["name"] for f in _app.feiertage_at(2026)}, _soll_2026)
check("Termine 2027 (Stadt Wien)", [f["datum"] for f in _app.feiertage_at(2027)], _soll_2027)
check("Ostersonntag 2026", _app.ostersonntag(2026).isoformat(), "2026-04-05")
check("Ostersonntag 2027", _app.ostersonntag(2027).isoformat(), "2027-03-28")
check("Ostersonntag 2024 (Kontrolle)", _app.ostersonntag(2024).isoformat(), "2024-03-31")
check("Karfreitag nicht enthalten",
      any(f["name"] == "Karfreitag" for f in _app.feiertage_at(2026)), False)
check("24./31.12. nur mit Sondertagen",
      [f["datum"] for f in _app.feiertage_at(2026, "ganz") if f["datum"].endswith(("12-24", "12-31"))],
      ["2026-12-24", "2026-12-31"])

print("\nFeiertage per API eintragen")
s, r = call("PUT", "/api/einstellungen", {"sondertage": "halb"})
check("Sondertage gesetzt", r["sondertage"], "halb")
s, r = call("GET", "/api/feiertage?jahr=2027")
check("Uebersicht Status", s, 200)
check("Feiertage 2027 inkl. Sondertage", len(r["feiertage"]), 15)
_fr = {f["datum"]: f for f in r["feiertage"]}
check("Allerheiligen 2027 ist Montag", _fr["2027-11-01"]["wochentag"], 1)
check("Staatsfeiertag 2027 faellt auf Samstag", _fr["2027-05-01"]["arbeitstag"], False)
check("Heiliger Abend halbe Gutschrift", _fr["2027-12-24"]["gutschrift"], 240)
s, r = call("POST", "/api/feiertage", {"jahr": 2027})
check("Eintragen Status", s, 200)
# Werktage (Mo-Fr) unter den 15 Terminen 2027
_werktags = [f for f in _fr.values() if f["arbeitstag"]]
check("angelegte Feiertage", r["angelegt"], len(_werktags))
s, r2 = call("POST", "/api/feiertage", {"jahr": 2027})
check("zweiter Lauf legt nichts doppelt an", r2["angelegt"], 0)
s, a = call("GET", "/api/auswertung?von=2027-12-01&bis=2027-12-31")
_tage = {t["datum"]: t for t in a["tage"]}
check("Mariae Empfaengnis saldoneutral", _tage["2027-12-08"]["saldo"], 0)
check("Heiliger Abend halber Tag", _tage["2027-12-24"]["saldo"], -240)
s, r = call("GET", "/api/feiertage?jahr=2027")
check("Status jetzt erfasst", all(f["erfasst"] for f in r["feiertage"] if f["arbeitstag"]), True)
s, r = call("GET", "/api/feiertage?jahr=abc")
check("ungueltiges Jahr -> 400", s, 400)

print("\nArbeitstage auffuellen")
s, r = call("PUT", "/api/einstellungen", {
    "standardzeiten": {str(d): {"von": "08:00", "bis": "16:30", "pause": 30} for d in range(1, 6)},
    "startdatum": "2026-08-01"})
check("Standardzeiten gespeichert", r["standardzeiten"]["1"]["bis"], "16:30")
check("Samstag ohne Standardzeit", r["standardzeiten"]["6"], None)
s, r = call("POST", "/api/auffuellen", {"von": "2026-08-01", "bis": "2026-08-14"})
check("Auffuellen Status", s, 200)
check("nur bis heute gefuellt", r["bis"] <= _dt.date.today().isoformat(), True)
s, r2 = call("POST", "/api/auffuellen", {"von": "2026-08-01", "bis": "2026-08-14"})
check("zweiter Lauf fuellt nichts doppelt", r2["angelegt"], 0)
check("belegte Tage erkannt", r2["uebersprungen"]["belegt"] > 0, True)
s, r = call("POST", "/api/auffuellen", {"von": "2026-08-31", "bis": "2026-08-01"})
check("verdrehter Zeitraum -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"sondertage": "quatsch"})
check("ungueltiger Sondertage-Modus -> 400", s, 400)

print("\nGutschrift-Feld")
s, r = call("POST", "/api/eintraege", {"datum": "2026-09-01", "typ": "urlaub", "gutschrift": 180})
check("Urlaub mit Gutschrift angelegt", s, 201)
check("Gutschrift gespeichert", r["gutschrift"], 180)
s, a = call("GET", "/api/auswertung?von=2026-09-01&bis=2026-09-01")
check("Gutschrift wirkt", a["gutschrift"], 180)
s, r = call("POST", "/api/eintraege", {"datum": "2026-09-02", "typ": "urlaub", "gutschrift": -5})
check("negative Gutschrift -> 400", s, 400)
s, r = call("POST", "/api/eintraege", {"datum": "2026-09-02", "typ": "arbeit",
                                       "von": "08:00", "bis": "12:00", "gutschrift": 500})
check("Gutschrift bei Arbeit ignoriert", r["gutschrift"], None)

print("\nStatische Dateien")
s, html = call("GET", "/")
check("Index geladen", s, 200)
check("Index enthaelt Titel", "<title>Zeiterfassung</title>" in html, True)
s, r = call("GET", "/../app.py")
check("Pfad-Traversal blockiert", s, 404)

print("\n%d ok, %d Fehler" % (ok, fail))
raise SystemExit(1 if fail else 0)
