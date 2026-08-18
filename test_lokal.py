#!/usr/bin/env python3
"""Vergleicht die Handy-Version (static/lokal.js) mit der Server-Logik (app.py).

Dieselben Szenarien laufen durch beide Implementierungen; die Ergebnisse muessen
auf die Minute uebereinstimmen. Braucht playwright:

    pip install playwright && playwright install chromium
    python3 test_lokal.py
"""
import os, sys, threading, http.server, functools
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as py

# statischer Server ohne /api -> die Seite schaltet in den lokalen Modus
handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                            directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8850), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

SZENARIO = {
  "einstellungen": {"soll": {"1":8,"2":8,"3":8,"4":8,"5":8,"6":0,"7":0},
                    "standardzeiten": {str(d): {"von":"08:00","bis":"16:30","pause":30} for d in range(1,6)},
                    "sondertage": "halb", "startsaldo": 2.5, "startdatum": "2026-08-01",
                    "dienstarten": [
                      {"id":"notdienstwoche","name":"Notdienstwoche","pauschale":120,"farbe":"#b45309"},
                      {"id":"dienst-1","name":"1. Dienst","modus":"durchgehend",
                       "starttag":1,"startzeit":"07:00","endtag":1,"endzeit":"07:00"},
                      {"id":"dienst-2","name":"2. Dienst","modus":"taeglich",
                       "starttag":1,"startzeit":"07:00","endtag":6,"endzeit":"20:00"}]},
  "eintraege": [
    {"datum":"2026-08-03","typ":"arbeit","von":"08:00","bis":"17:00","pause":45,"projekt":"Kunde A"},
    {"datum":"2026-08-04","typ":"urlaub"},
    {"datum":"2026-08-05","typ":"arbeit","von":"22:00","bis":"06:00","pause":30,"projekt":"Kunde B"},
    {"datum":"2026-08-06","typ":"urlaub","von":"08:00","bis":"12:00","pause":0},
    {"datum":"2026-08-08","typ":"arbeit","von":"10:00","bis":"13:00","pause":0},
    {"datum":"2026-08-10","typ":"dienst","dienstart":"notdienstwoche"},
    {"datum":"2026-08-10","typ":"arbeit","von":"23:00","bis":"01:30","pause":0,"notiz":"Einsatz"},
    {"datum":"2026-12-24","typ":"feiertag","gutschrift":240,"notiz":"Heiliger Abend"},
    # Zeitpauschale und Ausfahrt: beide werden gesondert verrechnet und duerfen
    # in keiner der beiden Fassungen im Saldo landen.
    {"datum":"2026-08-17","typ":"dienst","dienstart":"dienst-1","gutschrift":1020},
    {"datum":"2026-08-18","typ":"dienst","dienstart":"dienst-1","gutschrift":1440},
    {"datum":"2026-08-18","typ":"ausfahrt","von":"22:00","bis":"23:30","pause":0,
     "notiz":"Rohrbruch"},
    {"datum":"2026-08-19","typ":"ausfahrt","von":"02:00","bis":"04:15","pause":0},
  ],
}

# --- Python-Referenz ---
if os.path.exists("/tmp/ref.db"): os.remove("/tmp/ref.db")
store = py.Store("/tmp/ref.db")
store.save_settings(SZENARIO["einstellungen"])
arten = {a["id"]: a for a in store.get_settings()["dienstarten"]}
for e in SZENARIO["eintraege"]:
    store.insert_entry(py.clean_entry(e, arten))
def py_auswertung(von, bis):
    r = py.compute(store.list_entries(von, bis), py.effective_settings(store), von, bis)
    r["gesamtsaldo"] = py.gesamtsaldo(store)
    return r

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(locale="de-AT")
    fehler = []
    pg.on("pageerror", lambda e: fehler.append(str(e)))
    pg.goto("http://127.0.0.1:8850/index.html", wait_until="networkidle")
    pg.wait_for_timeout(500)
    js_modus = pg.evaluate("LOKAL_MODUS")
    print("Browser im lokalen Modus:", js_modus)

    pg.evaluate("""async (sz) => {
        await LOKAL.ruf("/api/einstellungen", {method:"PUT", body: JSON.stringify(sz.einstellungen)});
        for (const e of sz.eintraege)
            await LOKAL.ruf("/api/eintraege", {method:"POST", body: JSON.stringify(e)});
    }""", SZENARIO)

    fehlerhaft = 0
    for von, bis in [("2026-08-01","2026-08-31"), ("2026-12-01","2026-12-31"),
                     ("2026-08-10","2026-08-10"), ("2026-01-01","2026-12-31")]:
        pyr = py_auswertung(von, bis)
        jsr = pg.evaluate("([v,b]) => LOKAL.ruf(`/api/auswertung?von=${v}&bis=${b}`)", [von, bis])
        for feld in ("ist","gutschrift","soll","saldo","gesamtsaldo",
                     "pauschale","ausfahrt"):
            gleich = pyr[feld] == jsr[feld]
            fehlerhaft += 0 if gleich else 1
            print(f"  {'ok  ' if gleich else 'FAIL'} {von}..{bis} {feld:12} py={pyr[feld]:7} js={jsr[feld]:7}")
        gleich = [t["saldo"] for t in pyr["tage"]] == [t["saldo"] for t in jsr["tage"]]
        fehlerhaft += 0 if gleich else 1
        print(f"  {'ok  ' if gleich else 'FAIL'} {von}..{bis} Tagessalden ({len(pyr['tage'])} Tage)")

    # Feiertage beider Implementierungen vergleichen
    for jahr in (2026, 2027, 2008, 2038):
        pyf = [(f["datum"], f["name"]) for f in py.feiertage_at(jahr, "halb")]
        jsf = [(f["datum"], f["name"]) for f in pg.evaluate("j => LOKAL.feiertageAT(j,'halb')", jahr)]
        gleich = pyf == jsf
        fehlerhaft += 0 if gleich else 1
        print(f"  {'ok  ' if gleich else 'FAIL'} Feiertage {jahr}: {len(jsf)} Termine identisch={gleich}")

    # Fehlerfaelle muessen ebenfalls gleich reagieren
    for roh, erwartet in [({"datum":"2026-02-30","typ":"arbeit","von":"08:00","bis":"16:00"}, "Datum"),
                          ({"datum":"2026-08-20","typ":"arbeit"}, "Von"),
                          ({"datum":"2026-08-20","typ":"arbeit","von":"08:00","bis":"08:00"}, "gleich"),
                          ({"datum":"2026-08-20","typ":"dienst"}, "Dienstart")]:
        try:
            py.clean_entry(roh, arten); py_ok = True
        except ValueError: py_ok = False
        js_ok = pg.evaluate("""async (e) => {
            try { await LOKAL.ruf("/api/eintraege", {method:"POST", body: JSON.stringify(e)});
                  return true; } catch(err){ return false; } }""", roh)
        gleich = py_ok == js_ok == False
        fehlerhaft += 0 if gleich else 1
        print(f"  {'ok  ' if gleich else 'FAIL'} beide lehnen ab ({erwartet}): py={py_ok} js={js_ok}")

    print("JS-Fehler:", fehler or "keine")
    print("\nAbweichungen:", fehlerhaft)
    b.close()
srv.shutdown()
sys.exit(1 if fehlerhaft else 0)
