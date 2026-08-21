#!/usr/bin/env python3
"""Kleiner End-to-End-Test gegen den laufenden Server (python3 app.py --port 8765)."""
import json
import os
import urllib.error
import urllib.request

# Adresse des laufenden Servers; abweichender Port per Umgebungsvariable:
#   ZEIT_URL=http://127.0.0.1:9000 python3 test_api.py
BASE = os.environ.get("ZEIT_URL", "http://127.0.0.1:8765")
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
# Rechnet ab Startdatum bis heute, damit nicht erfasste Werktage nicht unter den
# Tisch fallen. _werktage stammt aus der Auswertung oben (gleicher Zeitraum).
erwartet = (495 + 450 + 180 + 480 + 240) - _werktage * 480 + 150
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
s, r = call("POST", "/api/eintraege", {"datum": "2026-09-02", "typ": "gleitzeit",
                                       "gutschrift": -90, "notiz": "ausbezahlt"})
check("Abzug erlaubt (ausbezahlte Stunden)", r["gutschrift"], -90)
s, a = call("GET", "/api/auswertung?von=2026-09-02&bis=2026-09-02")
check("Abzug wirkt auf den Saldo", a["gutschrift"], -90)
s, r = call("POST", "/api/eintraege", {"datum": "2026-09-03", "typ": "urlaub", "gutschrift": -5000})
check("Abzug groesser als 24 h -> 400", s, 400)
s, r = call("POST", "/api/eintraege", {"datum": "2026-09-02", "typ": "arbeit",
                                       "von": "08:00", "bis": "12:00", "gutschrift": 500})
check("Gutschrift bei Arbeit ignoriert", r["gutschrift"], None)

print("\nSchutz vor fremden Webseiten")


def roh(method, path, body="", ctype="application/json", origin=None, host=None):
    """Anfrage mit frei waehlbaren Kopfzeilen, wie sie ein Browser senden wuerde."""
    kopf = {"Content-Type": ctype}
    if origin:
        kopf["Origin"] = origin
    req = urllib.request.Request(BASE + path, data=body.encode(), method=method, headers=kopf)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


_eintrag = json.dumps({"datum": "2026-08-20", "typ": "arbeit", "von": "08:00", "bis": "12:00"})
check("Formular-POST einer fremden Seite -> 403 (Origin)",
      roh("POST", "/api/eintraege", _eintrag, ctype="text/plain;charset=UTF-8",
          origin="https://boese-seite.example"), 403)
check("JSON-POST mit fremdem Origin -> 403",
      roh("POST", "/api/eintraege", _eintrag, origin="https://boese-seite.example"), 403)
check("Import einer fremden Seite -> 403",
      roh("POST", "/api/import", '{"modus":"ersetzen","daten":{"eintraege":[]}}',
          ctype="text/plain", origin="https://boese-seite.example"), 403)
# Zweite Verteidigungslinie: auch ohne Origin-Kopfzeile kommt ein Formular-POST
# nicht durch, weil Browser fuer application/json einen Preflight brauchen.
check("Formular-POST ohne Origin -> 415",
      roh("POST", "/api/eintraege", _eintrag, ctype="text/plain;charset=UTF-8"), 415)
check("Import ohne Origin, falscher Content-Type -> 415",
      roh("POST", "/api/import", '{"modus":"ersetzen","daten":{"eintraege":[]}}',
          ctype="application/x-www-form-urlencoded"), 415)
check("fremder Host-Header (DNS-Rebinding) -> 421",
      roh("GET", "/api/export.json", host="boese-seite.example"), 421)
check("eigener Origin bleibt erlaubt",
      roh("POST", "/api/eintraege", _eintrag, origin=BASE), 201)
s, e = call("GET", "/api/eintraege?von=2026-08-20&bis=2026-08-20")
check("dabei genau ein Eintrag entstanden", len(e), 1)
for _x in e:
    call("DELETE", "/api/eintraege/%d" % _x["id"])

print("\nImport zerstoert keine Daten")
s, _vorher = call("GET", "/api/eintraege")
s, r = call("POST", "/api/import", {"modus": "ersetzen", "daten": {
    "eintraege": [{"datum": "2026-08-03", "typ": "arbeit", "von": "08:00", "bis": "16:00"}],
    "einstellungen": {"sondertage": "quatsch"}}})
check("kaputte Einstellungen -> 400", s, 400)
s, _nachher = call("GET", "/api/eintraege")
check("Eintraege trotzdem unveraendert", len(_nachher), len(_vorher))
s, r = call("POST", "/api/import", {"modus": "anhängen", "daten": {"eintraege": []}})
check("unbekannter Modus -> 400", s, 400)
s, _nachher = call("GET", "/api/eintraege")
check("nichts geloescht", len(_nachher), len(_vorher))
s, r = call("POST", "/api/import", {"modus": "ersetzen", "daten": {
    "eintraege": [{"datum": "2026-08-03", "typ": "arbeit", "von": "25:00", "bis": "16:00"}]}})
check("kaputter Eintrag -> 400", s, 400)
s, _nachher = call("GET", "/api/eintraege")
check("auch dann nichts geloescht", len(_nachher), len(_vorher))

print("\nWeitere Randfaelle")
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-21", "typ": "arbeit",
                                       "von": "08:00", "bis": "08:00"})
check("Von gleich Bis -> 400", s, 400)
s, r = call("POST", "/api/eintraege", {"datum": "2026-08-21", "typ": "urlaub",
                                       "von": "08:00", "bis": "12:00", "pause": 600})
check("negative Gutschrift ueber Pause -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"soll": "quatsch"})
check("Sollstunden als Text -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"standardzeiten": {"1": {"von": "08:00", "bis": "08:00"}}})
check("Standardzeit ohne Dauer -> 400", s, 400)
s, r = call("GET", "/api/einstellungen")
check("Einstellungen nach Fehlversuchen intakt", r["soll"]["1"], 8.0)
# Christi Himmelfahrt faellt 2008 auf den Staatsfeiertag
check("doppelter Feiertagstermin 2008",
      len({f["datum"] for f in _app.feiertage_at(2008)}), 12)

print("\nDienste / Notdienstwochen")
s, r = call("PUT", "/api/einstellungen", {"dienstarten": [
    {"name": "Notdienstwoche", "pauschale": 120, "farbe": "#b45309"},
    {"name": "Wochenenddienst Süd", "pauschale": 240},
    {"name": "Notdienstwoche", "pauschale": 60},          # gleicher Name -> eigene Kennung
    {"name": "", "pauschale": 999},                        # ohne Namen -> faellt weg
]})
check("Dienstarten gespeichert", s, 200)
check("Anzahl Dienstarten", len(r["dienstarten"]), 3)
check("Kennungen eindeutig", [a["id"] for a in r["dienstarten"]],
      ["notdienstwoche", "wochenenddienst-sued", "notdienstwoche-2"])
check("Umlaute in der Kennung", r["dienstarten"][1]["id"], "wochenenddienst-sued")
check("Farbe ergaenzt", r["dienstarten"][1]["farbe"], "#b45309")
s, r = call("PUT", "/api/einstellungen", {"dienstarten": [{"name": "X", "pauschale": 5000}]})
check("zu grosse Pauschale -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"dienstarten": "quatsch"})
check("Dienstarten als Text -> 400", s, 400)
s, r = call("GET", "/api/einstellungen")
check("Dienstarten nach Fehlversuch intakt", len(r["dienstarten"]), 3)

s, r = call("POST", "/api/dienste", {"dienstart": "notdienstwoche",
                                     "von": "2026-09-07", "bis": "2026-09-13"})
check("Notdienstwoche angelegt", r["angelegt"], 7)
check("Pauschale gesamt", r["minuten"], 7 * 120)
s, r2 = call("POST", "/api/dienste", {"dienstart": "notdienstwoche",
                                      "von": "2026-09-07", "bis": "2026-09-13"})
check("zweiter Lauf legt nichts doppelt an", r2["angelegt"], 0)
s, r = call("POST", "/api/dienste", {"dienstart": "gibtsnicht",
                                     "von": "2026-09-07", "bis": "2026-09-13"})
check("unbekannte Dienstart -> 400", s, 400)
s, r = call("POST", "/api/eintraege", {"datum": "2026-09-08", "typ": "dienst"})
check("Dienst ohne Dienstart -> 400", s, 400)

# Einsatz waehrend der Rufbereitschaft zaehlt zusaetzlich
s, r = call("POST", "/api/eintraege", {"datum": "2026-09-08", "typ": "arbeit",
                                       "von": "23:00", "bis": "01:30", "pause": 0,
                                       "notiz": "Einsatz"})
check("Einsatz angelegt", s, 201)
s, a = call("GET", "/api/auswertung?von=2026-09-07&bis=2026-09-13")
_t = {t["datum"]: t for t in a["tage"]}
# Die Zeitpauschale wird gesondert verrechnet: sie steht in einem eigenen Feld
# und darf Ist, Saldo und Ueberstunden nicht beruehren.
check("Diensttag Pauschale getrennt", _t["2026-09-07"]["pauschale"], 120)
check("Diensttag ohne Gutschrift", _t["2026-09-07"]["gutschrift"], 0)
check("Diensttag Saldo (Soll 8 h)", _t["2026-09-07"]["saldo"], -480)
check("Einsatz zaehlt zusaetzlich", _t["2026-09-08"]["ist"], 150)
check("Einsatztag gesamt", _t["2026-09-08"]["saldo"], 150 - 480)
check("Sonntag im Dienst bleibt neutral", _t["2026-09-13"]["saldo"], 0)
check("Pauschale im Zeitraum", a["pauschale"], 840)
check("Pauschale nicht im Saldo", a["erfasst"], a["ist"] + a["gutschrift"])
check("Dienstauswertung Tage", a["dienste"][0]["tage"], 7)
check("Dienstauswertung Minuten", a["dienste"][0]["minuten"], 840)
check("Dienstauswertung Name", a["dienste"][0]["name"], "Notdienstwoche")

# Auffuellen darf Diensttage weiterhin mit Arbeitszeit versehen
s, r = call("POST", "/api/auffuellen", {"von": "2026-09-07", "bis": "2026-09-11"})
check("Arbeitstage trotz Dienst gefuellt", r["angelegt"], 0 if r["bis"] < "2026-09-07" else 5)
s, csv_text = call("GET", "/api/export.csv?von=2026-09-07&bis=2026-09-07")
check("CSV kennt die Dienstspalte", "Dienst" in csv_text.splitlines()[0], True)
check("CSV nennt den Dienstnamen", "Notdienstwoche" in csv_text, True)
s, exp = call("GET", "/api/export.json")
check("Export enthaelt dienstart",
      any(e.get("dienstart") == "notdienstwoche" for e in exp["eintraege"]), True)
s, r = call("POST", "/api/import", {"modus": "ersetzen", "daten": exp})
check("Reimport mit Diensten", s, 200)
s, a = call("GET", "/api/auswertung?von=2026-09-07&bis=2026-09-13")
check("Dienste nach Reimport unveraendert", a["dienste"][0]["minuten"], 840)

print("\nJobs")
s, r = call("PUT", "/api/einstellungen", {"jobs": [
    {"id": "haupt", "name": "Kältetechniker",
     "soll": {"1": 8.25, "2": 8.25, "3": 8.25, "4": 8.25, "5": 5.5, "6": 0, "7": 0}},
    {"name": "Nebenjob", "soll": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 5, "7": 0}}]})
check("Jobs gespeichert", s, 200)
check("Kennungen", [j["id"] for j in r["jobs"]], ["haupt", "nebenjob"])
check("aktiver Job folgt der Liste", r["aktiverJob"], "haupt")
check("Sollzeiten des aktiven Jobs gespiegelt", r["soll"]["5"], 5.5)
s, r = call("PUT", "/api/einstellungen", {"aktiverJob": "nebenjob"})
check("Jobwechsel", (r["aktiverJob"], r["soll"]["6"]), ("nebenjob", 5.0))
s, r = call("PUT", "/api/einstellungen", {"aktiverJob": "gibtsnicht"})
check("unbekannter Job -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"jobs": []})
check("leere Jobliste -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"soll": {str(d): 4 for d in range(1, 8)}})
check("Sollzeit trifft nur den aktiven Job",
      [j["soll"]["1"] for j in r["jobs"]], [8.25, 4.0])

s, r = call("POST", "/api/eintraege", {"datum": "2026-10-05", "typ": "arbeit",
                                       "von": "08:00", "bis": "12:00", "job": "haupt"})
check("Eintrag mit Job", r["job"], "haupt")
s, r = call("POST", "/api/eintraege", {"datum": "2026-10-05", "typ": "arbeit",
                                       "von": "13:00", "bis": "15:00", "job": "nebenjob"})
check("zweiter Job am selben Tag", s, 201)
s, a = call("GET", "/api/auswertung?von=2026-10-05&bis=2026-10-05&job=haupt")
check("Auswertung Job haupt", a["ist"], 240)
s, a = call("GET", "/api/auswertung?von=2026-10-05&bis=2026-10-05&job=nebenjob")
check("Auswertung Job nebenjob", a["ist"], 120)
s, a = call("GET", "/api/auswertung?von=2026-10-05&bis=2026-10-05&job=alle")
check("Auswertung alle Jobs", a["ist"], 360)
check("Kennzahlen je Art", a["arten"]["arbeit"], {"tage": 1, "minuten": 360})
s, a = call("GET", "/api/auswertung?von=2026-10-05&bis=2026-10-05&job=quatsch")
check("unbekannter Job in der Auswertung -> 400", s, 400)
s, e = call("GET", "/api/eintraege?job=nebenjob")
check("Eintraege nach Job gefiltert", len(e), 1)

print("\nNotizvorlagen")
s, r = call("PUT", "/api/einstellungen", {"notizvorlagen": ["Montage", "Service", "   "]})
check("Vorlagen gespeichert", r["notizvorlagen"], ["Montage", "Service"])
s, r = call("PUT", "/api/einstellungen", {"notizvorlagen": "quatsch"})
check("Vorlagen als Text -> 400", s, 400)

print("\nStempeluhr")
s, r = call("GET", "/api/stempel")
check("nichts laeuft", r["laufend"], None)
s, r = call("POST", "/api/stempel/start", {"job": "haupt", "projekt": "Kunde X"})
check("Start", s, 201)
check("laeuft mit Job", r["laufend"]["job"], "haupt")
s, r = call("POST", "/api/stempel/start", {})
check("zweiter Start -> 400", s, 400)
s, r = call("POST", "/api/stempel/pause", {})
check("Pause an", r["laufend"]["pausiert"], True)
s, r = call("POST", "/api/stempel/pause", {})
check("Pause aus", r["laufend"]["pausiert"], False)
s, r = call("POST", "/api/stempel/stop", {})
check("Stoppen unter einer Minute -> 400", s, 400)
s, r = call("GET", "/api/stempel")
check("Messung laeuft nach dem Fehler weiter", bool(r["laufend"]), True)
s, r = call("POST", "/api/stempel/stop", {"verwerfen": True})
check("Verwerfen", r, {"verworfen": True})
s, r = call("GET", "/api/stempel")
check("danach nichts mehr", r["laufend"], None)
s, r = call("POST", "/api/stempel/stop", {})
check("Stoppen ohne Messung -> 400", s, 400)

print("\nSommerzeit, Rundung, Urlaub")
s, r = call("PUT", "/api/einstellungen", {"zeitzone": "Europe/Vienna", "rundung": 15,
                                          "rundungsmodus": "kaufmaennisch",
                                          "jobs": [{"id": "standard", "name": "Mein Job",
                                                    "soll": {str(d): 8 for d in range(1, 6)},
                                                    "urlaubstage": 25}]})
check("Rechenregeln gespeichert", (r["zeitzone"], r["rundung"], r["jobs"][0]["urlaubstage"]),
      ("Europe/Vienna", 15, 25.0))
s, r = call("PUT", "/api/einstellungen", {"rundung": 7})
check("krumme Rundung -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"zeitzone": "Mond/Krater"})
check("unbekannte Zeitzone -> 400", s, 400)

s, r = call("POST", "/api/eintraege", {"datum": "2027-03-27", "typ": "arbeit",
                                       "von": "22:00", "bis": "06:00", "pause": 0})
check("Nacht vor der Umstellung angelegt", s, 201)
s, a = call("GET", "/api/auswertung?von=2027-03-27&bis=2027-03-27")
check("Sommerzeit: 8 Wanduhrstunden sind 7 echte", a["ist"], 420)
s, r = call("POST", "/api/eintraege", {"datum": "2027-10-30", "typ": "arbeit",
                                       "von": "22:00", "bis": "06:00", "pause": 0})
s, a = call("GET", "/api/auswertung?von=2027-10-30&bis=2027-10-30")
check("Winterzeit: 8 Wanduhrstunden sind 9 echte", a["ist"], 540)
s, r = call("POST", "/api/eintraege", {"datum": "2027-09-06", "typ": "arbeit",
                                       "von": "07:00", "bis": "16:07", "pause": 45})
s, a = call("GET", "/api/auswertung?von=2027-09-06&bis=2027-09-06")
check("502 Minuten auf 15 gerundet", a["ist"], 495)

s, r = call("POST", "/api/eintraege", {"datum": "2027-05-03", "typ": "urlaub"})
s, r = call("POST", "/api/eintraege", {"datum": "2027-05-04", "typ": "urlaub", "gutschrift": 240})
s, a = call("GET", "/api/auswertung?von=2027-01-01&bis=2027-12-31")
check("Urlaub verbraucht (ganzer + halber Tag)", a["urlaub"]["verbraucht"], 1.5)
check("Urlaub offen", a["urlaub"]["rest"], 23.5)
check("Urlaub wird gefuehrt", a["urlaub"]["gefuehrt"], True)
s, r = call("PUT", "/api/einstellungen", {"rundung": 0,
                                          "jobs": [{"id": "standard", "name": "Mein Job",
                                                    "soll": {str(d): 8 for d in range(1, 6)}}]})
s, a = call("GET", "/api/auswertung?von=2027-09-06&bis=2027-09-06")
check("ohne Rundung wieder minutengenau", a["ist"], 502)
check("ohne Anspruch nicht gefuehrt", a["urlaub"]["gefuehrt"], False)

print("\nMehrere Jobs: Zuordnung und Abgrenzung")
s, r = call("PUT", "/api/einstellungen", {"jobs": [
    {"id": "haupt", "name": "Haupt", "soll": {**{str(d): 8 for d in range(1, 6)}, "6": 0, "7": 0},
     "standardzeiten": {str(d): {"von": "08:00", "bis": "16:30", "pause": 30} for d in range(1, 6)},
     "urlaubstage": 25},
    {"id": "neben", "name": "Neben", "soll": {**{str(d): 4 for d in range(1, 6)}, "6": 0, "7": 0},
     "standardzeiten": {str(d): {"von": "17:00", "bis": "21:00", "pause": 0} for d in range(1, 6)},
     "urlaubstage": 10}], "aktiverJob": "haupt"})
check("zwei Jobs angelegt", [j["id"] for j in r["jobs"]], ["haupt", "neben"])
s, r = call("POST", "/api/auffuellen", {"von": "2025-11-03", "bis": "2025-11-07", "job": "neben"})
check("Auffuellen legt an", r["angelegt"], 5)
s, e = call("GET", "/api/eintraege?von=2025-11-03&bis=2025-11-07")
check("Eintraege gehoeren dem gewaehlten Job", {x["job"] for x in e}, {"neben"})
s, a = call("GET", "/api/auswertung?von=2025-11-03&bis=2025-11-07&job=haupt")
check("anderer Job bleibt leer", a["ist"], 0)
s, a = call("GET", "/api/auswertung?von=2025-11-03&bis=2025-11-07&job=neben")
check("Zeiten liegen im richtigen Job", a["ist"], 1200)
s, r1 = call("POST", "/api/feiertage", {"jahr": 2028, "job": "haupt"})
s, r2 = call("POST", "/api/feiertage", {"jahr": 2028, "job": "neben"})
check("Feiertage je Job getrennt", (r1["angelegt"] > 0, r2["angelegt"] > 0), (True, True))
s, r = call("PUT", "/api/einstellungen", {"job": "gibtsnicht", "soll": {"1": 3}})
check("unbekannter Job beim Speichern -> 400", s, 400)
s, csv_text = call("GET", "/api/export.csv?von=2025-11-03&bis=2025-11-07&job=neben")
check("CSV hat eine Job-Spalte", csv_text.splitlines()[0].split(";")[2], "Job")
check("CSV filtert nach Job", all("Neben" in z for z in csv_text.strip().splitlines()[1:]), True)

print("\nUrlaubskonto")
for _tag in ["2028-05-01", "2028-05-06", "2028-05-07"]:      # Mo, Sa, So
    call("POST", "/api/eintraege", {"datum": _tag, "typ": "urlaub", "job": "haupt"})
s, a = call("GET", "/api/auswertung?von=2028-08-01&bis=2028-08-31&job=haupt")
check("Urlaub zaehlt fuers ganze Jahr, nicht nur den Monat", a["urlaub"]["verbraucht"], 1.0)
check("Urlaub am Wochenende zaehlt nicht", a["urlaub"]["rest"], 24.0)
s, a = call("GET", "/api/auswertung?von=2028-08-01&bis=2028-08-31&job=alle")
check("Urlaubskonto auch ueber alle Jobs", a["urlaub"]["anspruch"], 35.0)

print("\nKuenftige Diensttage")
s, a1 = call("GET", "/api/auswertung?von=2028-01-01&bis=2028-12-31&job=haupt")
s, r = call("POST", "/api/dienste", {"dienstart": "notdienstwoche", "von": "2029-10-01",
                                     "bis": "2029-10-07", "job": "haupt"})
s, a2 = call("GET", "/api/auswertung?von=2029-10-01&bis=2029-10-07&job=haupt")
check("Dienstwoche in der Zukunft bringt kein Tagessoll", a2["soll"], 0)
check("nur die Pauschale zaehlt", a2["pauschale"], r["minuten"])
check("kuenftige Dienstwoche ohne Saldowirkung", a2["saldo"], 0)

print("\nMigration alter Datenbanken")
import json as _json, os as _os, sqlite3 as _sqlite, tempfile as _tempfile
_pfad = _os.path.join(_tempfile.mkdtemp(), "alt.db")
_con = _sqlite.connect(_pfad)
_con.execute("""CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, datum TEXT NOT NULL,
  typ TEXT NOT NULL DEFAULT 'arbeit', von TEXT, bis TEXT, pause INTEGER NOT NULL DEFAULT 0,
  projekt TEXT NOT NULL DEFAULT '', notiz TEXT NOT NULL DEFAULT '')""")
_con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
_con.execute("INSERT INTO entries(datum,typ,von,bis,pause) VALUES('2026-08-03','arbeit','07:00','16:00',45)")
_con.execute("INSERT INTO settings VALUES('soll', ?)",
             (_json.dumps({"1": 8.25, "2": 8.25, "3": 8.25, "4": 8.25, "5": 5.5, "6": 0, "7": 0}),))
_con.execute("INSERT INTO settings VALUES('startsaldo', '12.5')")
_con.execute("INSERT INTO settings VALUES('startdatum', '\"2023-01-02\"')")
_con.execute("INSERT INTO settings VALUES('name', '\"Markus\"')")
_con.commit(); _con.close()

_st = _app.Store(_pfad)
_s = _st.get_settings()
_job = _s["jobs"][0]
check("alte Sollzeiten bleiben erhalten", (_job["soll"]["1"], _job["soll"]["5"]), (8.25, 5.5))
check("alter Startsaldo bleibt erhalten", _job["startsaldo"], 12.5)
check("altes Startdatum bleibt erhalten", _job["startdatum"], "2023-01-02")
check("alter Name wird zum Jobnamen", _job["name"], "Markus")
check("nur ein Job nach der Migration", len(_s["jobs"]), 1)
check("Eintrag weiterhin lesbar", len(_st.list_entries()), 1)
check("neue Felder ergaenzt",
      (_s["zeitzone"], _s["rundung"], _job["urlaubstage"]), ("Europe/Vienna", 0, 0.0))
_e = _st.list_entries()[0]
check("Eintrag um neue Spalten ergaenzt",
      (_e["gutschrift"], _e["dienstart"], _e["job"]), (None, "", ""))
_a = _app.compute(_st.list_entries(), _app.effective_settings(_st), "2026-08-03", "2026-08-03")
check("Migration rechnet richtig", (_a["ist"], _a["soll"]), (495, 495))
_os.remove(_pfad)

print("\nNotdienst mit Wochenrhythmus")
# 1. Dienst laeuft Montag 07:00 bis Montag 07:00 durchgehend, der 2. und der
# 3. Dienst gelten an jedem Tag zwischen 07:00 und 20:00.
s, r = call("PUT", "/api/einstellungen", {"dienstarten": [
    {"name": "1. Dienst", "modus": "durchgehend",
     "starttag": 1, "startzeit": "07:00", "endtag": 1, "endzeit": "07:00"},
    {"name": "2. Dienst", "modus": "taeglich",
     "starttag": 1, "startzeit": "07:00", "endtag": 6, "endzeit": "20:00"},
    {"name": "3. Dienst", "modus": "taeglich",
     "starttag": 5, "startzeit": "07:00", "endtag": 6, "endzeit": "20:00"},
]})
check("drei Dienstarten gespeichert", s, 200)
_dauer = {a["name"]: a["dauer"] for a in r["dienstarten"]}
check("1. Dienst = 168 h", _dauer["1. Dienst"], 168 * 60)
check("2. Dienst = 78 h", _dauer["2. Dienst"], 78 * 60)
check("3. Dienst = 26 h", _dauer["3. Dienst"], 26 * 60)
_tage = {a["name"]: a["tage"] for a in r["dienstarten"]}
check("1. Dienst deckt acht Kalendertage", _tage["1. Dienst"], 8)
check("2. Dienst deckt sechs Tage", _tage["2. Dienst"], 6)
check("3. Dienst deckt zwei Tage", _tage["3. Dienst"], 2)

s, r = call("PUT", "/api/einstellungen", {"dienstarten": [
    {"name": "Kaputt", "modus": "quer", "starttag": 1, "startzeit": "07:00",
     "endtag": 2, "endzeit": "20:00"}]})
check("unbekannter Modus -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"dienstarten": [
    {"name": "Kaputt", "modus": "taeglich", "starttag": 9, "startzeit": "07:00",
     "endtag": 2, "endzeit": "20:00"}]})
check("Wochentag 9 -> 400", s, 400)
s, r = call("PUT", "/api/einstellungen", {"dienstarten": [
    {"name": "Kaputt", "modus": "taeglich", "starttag": 1, "startzeit": "sieben",
     "endtag": 2, "endzeit": "20:00"}]})
check("Startzeit als Wort -> 400", s, 400)

# Mittwoch gewaehlt: der Dienst zieht auf seinen Starttag zurueck
s, r = call("POST", "/api/dienste", {"dienstart": "1-dienst", "von": "2026-10-07", "job": "haupt"})
check("1. Dienst beginnt am Montag", r["von"], "2026-10-05")
check("1. Dienst endet am Montag darauf", r["bis"], "2026-10-12")
check("1. Dienst legt acht Tage an", r["angelegt"], 8)
check("1. Dienst Pauschale 168 h", r["pauschale"], 168 * 60)

s, a = call("GET", "/api/auswertung?von=2026-10-05&bis=2026-10-12")
_t = {t["datum"]: t for t in a["tage"]}
check("erster Tag ab 07:00", _t["2026-10-05"]["pauschale"], 17 * 60)
check("Tag dazwischen voll", _t["2026-10-07"]["pauschale"], 24 * 60)
check("letzter Tag bis 07:00", _t["2026-10-12"]["pauschale"], 7 * 60)
check("Pauschale gesamt 168 h", a["pauschale"], 168 * 60)
check("Pauschale nicht im Saldo", _t["2026-10-06"]["saldo"], -480)

print("\nAusfahrten im Dienst")
s, r = call("POST", "/api/eintraege", {"datum": "2026-10-06", "typ": "ausfahrt",
                                       "von": "22:00", "bis": "23:30", "pause": 0,
                                       "notiz": "Rohrbruch"})
check("Ausfahrt angelegt", s, 201)
_ausfahrt_id = r["id"]
s, r = call("POST", "/api/eintraege", {"datum": "2026-10-06", "typ": "ausfahrt"})
check("Ausfahrt ohne Uhrzeit -> 400", s, 400)

s, a = call("GET", "/api/auswertung?von=2026-10-05&bis=2026-10-12")
_t = {t["datum"]: t for t in a["tage"]}
check("Ausfahrt im eigenen Topf", _t["2026-10-06"]["ausfahrt"], 90)
check("Ausfahrt nicht im Ist", _t["2026-10-06"]["ist"], 0)
check("Ausfahrt nicht im Saldo", _t["2026-10-06"]["saldo"], -480)
check("Ausfahrten gesamt", a["ausfahrt"], 90)
check("Ausfahrt in der Liste", len(a["ausfahrten"]), 1)
check("Ausfahrt kennt ihren Dienst", a["ausfahrten"][0]["dienst"], "1. Dienst")
check("Ausfahrt am Dienst gezaehlt", a["dienste"][0]["ausfahrten"], 1)
check("Ausfahrtzeit am Dienst", a["dienste"][0]["ausfahrt_minuten"], 90)
check("Ausfahrt nicht in erfasst", a["erfasst"], a["ist"] + a["gutschrift"])

# Ohne Diensttag darunter bleibt die Ausfahrt sichtbar, nur ohne Zuordnung
s, r = call("POST", "/api/eintraege", {"datum": "2026-11-04", "typ": "ausfahrt",
                                       "von": "09:00", "bis": "10:00", "pause": 0})
check("Ausfahrt ohne Dienst angelegt", s, 201)
s, a = call("GET", "/api/auswertung?von=2026-11-04&bis=2026-11-04")
check("Ausfahrt ohne Dienst gelistet", len(a["ausfahrten"]), 1)
check("Ausfahrt ohne Dienstnamen", a["ausfahrten"][0]["dienst"], "")

s, csv_text = call("GET", "/api/export.csv?von=2026-10-06&bis=2026-10-06")
check("CSV kennt die Verrechnungsspalte", "Verrechnung" in csv_text.splitlines()[0], True)
check("CSV markiert Ausfahrt als gesondert", "Ausfahrt" in csv_text and "gesondert" in csv_text, True)

print("\nAutomatische Sicherungen")
s, r = call("GET", "/api/sicherungen")
check("Sicherungsliste erreichbar", s, 200)
_vorher = len(r["sicherungen"])
s, r = call("POST", "/api/sicherungen", {"grund": "manuell"})
check("Kopie angelegt", (s, r["angelegt"]), (200, True))
check("Kopie in der Liste", len(r["sicherungen"]), _vorher + 1)
_stand = r["sicherungen"][0]
check("Kopie hat Zeitpunkt", bool(__import__("re").match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$",
                                                        _stand["zeit"])), True)
_anzahl = _stand["eintraege"]
s, r = call("POST", "/api/sicherungen", {"grund": "automatisch", "nur_wenn_aelter_als": 24})
check("Tageskopie legt nicht doppelt an", (s, r["angelegt"]), (200, False))
# Einen Eintrag loeschen und wieder zurueckholen
s, _neu = call("POST", "/api/eintraege", {"datum": "2026-09-30", "typ": "arbeit",
                                          "von": "08:00", "bis": "12:00", "pause": 0})
check("Eintrag zum Verwerfen angelegt", s, 201)
s, r = call("GET", "/api/eintraege")
check("ein Eintrag mehr", len(r), _anzahl + 1)
s, r = call("POST", "/api/sicherungen/wiederherstellen", {"datei": _stand["datei"]})
check("Stand zurueckgeholt", (s, r["eintraege"]), (200, _anzahl))
s, r = call("GET", "/api/eintraege")
check("Eintrag ist wieder weg", len(r), _anzahl)
s, r = call("GET", "/api/sicherungen")
check("Stand vor dem Zurueckholen gesichert",
      any(x["grund"] == "vorimport" for x in r["sicherungen"]), True)
# Eine Sicherung mit einer inzwischen entfernten Dienstart muss sich trotzdem
# zurueckholen lassen - sonst waere der Stand verloren.
s, r = call("PUT", "/api/einstellungen", {"dienstarten": [{"name": "Nur einer", "pauschale": 60}]})
check("Dienstarten ausgetauscht", s, 200)
s, r = call("POST", "/api/sicherungen", {"grund": "manuell"})
_mit_alter_art = r["sicherungen"][0]["datei"]
s, r = call("POST", "/api/sicherungen/wiederherstellen", {"datei": _mit_alter_art})
check("Sicherung mit entfernter Dienstart zurueckholbar", s, 200)

s, r = call("POST", "/api/sicherungen/wiederherstellen", {"datei": "../../app.py"})
check("Fremde Datei abgelehnt", s, 400)
s, r = call("POST", "/api/sicherungen/wiederherstellen", {"datei": "sicherung-20200101-000000000-manuell.json"})
check("Unbekannte Sicherung abgelehnt", s, 400)

print("\nStatische Dateien")
s, html = call("GET", "/")
check("Index geladen", s, 200)
check("Index enthaelt Titel", "<title>Zeiterfassung</title>" in html, True)
s, r = call("GET", "/../app.py")
check("Pfad-Traversal blockiert", s, 404)

print("\n%d ok, %d Fehler" % (ok, fail))
raise SystemExit(1 if fail else 0)
