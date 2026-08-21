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
  "einstellungen": {
    "zeitzone": "Europe/Vienna", "rundung": 15, "rundungsmodus": "kaufmaennisch","soll": {"1":8,"2":8,"3":8,"4":8,"5":8,"6":0,"7":0},
                    "standardzeiten": {str(d): {"von":"08:00","bis":"16:30","pause":30} for d in range(1,6)},
                    "sondertage": "halb", "startsaldo": 2.5, "startdatum": "2026-08-01",
                    "dienstarten": [
                      {"name":"1. Dienst","modus":"durchgehend",
                       "starttag":1,"startzeit":"07:00","endtag":1,"endzeit":"07:00"},
                      {"name":"2. Dienst","modus":"taeglich",
                       "starttag":1,"startzeit":"07:00","endtag":6,"endzeit":"20:00"},
                      {"name":"Wochenenddienst","pauschale":120,"farbe":"#b45309"}]},
  "eintraege": [
    {"datum":"2026-08-03","typ":"arbeit","von":"08:00","bis":"17:00","pause":45,"projekt":"Kunde A"},
    {"datum":"2026-08-04","typ":"urlaub"},
    {"datum":"2026-08-05","typ":"arbeit","von":"22:00","bis":"06:00","pause":30,"projekt":"Kunde B"},
    {"datum":"2026-08-06","typ":"urlaub","von":"08:00","bis":"12:00","pause":0},
    {"datum":"2026-08-08","typ":"arbeit","von":"10:00","bis":"13:00","pause":0},
    {"datum":"2026-08-10","typ":"dienst","dienstart":"1-dienst","gutschrift":1020},
    {"datum":"2026-08-11","typ":"dienst","dienstart":"1-dienst","gutschrift":1440},
    {"datum":"2026-08-15","typ":"dienst","dienstart":"wochenenddienst"},
    {"datum":"2026-08-10","typ":"arbeit","von":"23:00","bis":"01:30","pause":0,"notiz":"Einsatz"},
    {"datum":"2026-08-11","typ":"ausfahrt","von":"22:00","bis":"23:30","pause":0,"notiz":"Rohrbruch"},
    {"datum":"2026-08-12","typ":"ausfahrt","von":"23:30","bis":"01:00","pause":0},
    {"datum":"2026-12-24","typ":"feiertag","gutschrift":240,"notiz":"Heiliger Abend"},
    {"datum":"2026-03-28","typ":"arbeit","von":"22:00","bis":"06:00","pause":0},
    {"datum":"2026-10-24","typ":"arbeit","von":"22:00","bis":"06:00","pause":0},
    {"datum":"2026-09-07","typ":"arbeit","von":"07:00","bis":"16:07","pause":45},
    {"datum":"2026-05-04","typ":"urlaub"},
    {"datum":"2026-05-05","typ":"urlaub","gutschrift":240},
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
        if "urlaub" in pyr and "urlaub" in jsr:
            gleich = pyr["urlaub"] == jsr["urlaub"]
            fehlerhaft += 0 if gleich else 1
            print(f"  {'ok  ' if gleich else 'FAIL'} {von}..{bis} Urlaubskonto "
                  f"py={pyr['urlaub']} js={jsr['urlaub']}")
        for feld in ("ist","gutschrift","soll","saldo","gesamtsaldo",
                     "pauschale","ausfahrt"):
            gleich = pyr[feld] == jsr[feld]
            fehlerhaft += 0 if gleich else 1
            print(f"  {'ok  ' if gleich else 'FAIL'} {von}..{bis} {feld:12} py={pyr[feld]:7} js={jsr[feld]:7}")
        gleich = [t["saldo"] for t in pyr["tage"]] == [t["saldo"] for t in jsr["tage"]]
        fehlerhaft += 0 if gleich else 1
        print(f"  {'ok  ' if gleich else 'FAIL'} {von}..{bis} Tagessalden ({len(pyr['tage'])} Tage)")
        # Dienste und Ausfahrten muessen auf die Minute uebereinstimmen
        gleich = pyr["dienste"] == jsr["dienste"]
        fehlerhaft += 0 if gleich else 1
        print(f"  {'ok  ' if gleich else 'FAIL'} {von}..{bis} Dienste      {pyr['dienste']}")
        pa = [{k: v for k, v in a.items() if k != "id"} for a in pyr["ausfahrten"]]
        ja = [{k: v for k, v in a.items() if k != "id"} for a in jsr["ausfahrten"]]
        gleich = pa == ja
        fehlerhaft += 0 if gleich else 1
        print(f"  {'ok  ' if gleich else 'FAIL'} {von}..{bis} Ausfahrten   ({len(pa)})")

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

    # --- Mehrere Jobs, Kennzahlen und Stempeluhr ---------------------------
    JOBS = [{"id": "haupt", "name": "Haupt",
             "soll": {"1": 8.25, "2": 8.25, "3": 8.25, "4": 8.25, "5": 5.5, "6": 0, "7": 0}},
            {"id": "neben", "name": "Neben",
             "soll": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 5, "7": 0}}]
    ZUSATZ = [{"datum": "2026-11-02", "typ": "arbeit", "von": "07:00", "bis": "16:00",
               "pause": 45, "job": "haupt"},
              {"datum": "2026-11-02", "typ": "arbeit", "von": "18:00", "bis": "20:00",
               "job": "neben"},
              {"datum": "2026-11-07", "typ": "arbeit", "von": "09:00", "bis": "14:00",
               "job": "neben"}]
    store.save_settings({"jobs": JOBS})
    arten2 = {a["id"]: a for a in store.get_settings()["dienstarten"]}
    for e in ZUSATZ:
        store.insert_entry(py.clean_entry(e, arten2))
    pg.evaluate("""async ([jobs, eintraege]) => {
        await LOKAL.ruf("/api/einstellungen", {method:"PUT", body: JSON.stringify({jobs})});
        for (const e of eintraege)
            await LOKAL.ruf("/api/eintraege", {method:"POST", body: JSON.stringify(e)});
    }""", [JOBS, ZUSATZ])

    for job in ("haupt", "neben", "alle"):
        pyr = py.auswertung(store, "2026-11-01", "2026-11-30", None if job == "alle" else job)
        jsr = pg.evaluate("([v,b,j]) => LOKAL.ruf(`/api/auswertung?von=${v}&bis=${b}&job=${j}`)",
                          ["2026-11-01", "2026-11-30", job])
        for feld in ("ist", "gutschrift", "soll", "saldo", "gesamtsaldo",
                     "pauschale", "ausfahrt"):
            gleich = pyr[feld] == jsr[feld]
            fehlerhaft += 0 if gleich else 1
            print(f"  {'ok  ' if gleich else 'FAIL'} Job {job:5} {feld:12} "
                  f"py={pyr[feld]:6} js={jsr[feld]:6}")
        gleich = pyr["arten"] == jsr["arten"]
        fehlerhaft += 0 if gleich else 1
        print(f"  {'ok  ' if gleich else 'FAIL'} Job {job:5} Kennzahlen   "
              f"{pyr['arten']} | {jsr['arten']}")

    stempel = pg.evaluate("""async () => {
        await LOKAL.ruf("/api/stempel/start", {method:"POST",
            body: JSON.stringify({job:"haupt", projekt:"Probe"})});
        const laeuft = (await LOKAL.ruf("/api/stempel")).laufend;
        await LOKAL.ruf("/api/stempel/pause", {method:"POST", body:"{}"});
        const pausiert = (await LOKAL.ruf("/api/stempel")).laufend.pausiert;
        await LOKAL.ruf("/api/stempel/stop", {method:"POST",
            body: JSON.stringify({verwerfen:true})});
        return {job: laeuft.job, projekt: laeuft.projekt, pausiert,
                danach: (await LOKAL.ruf("/api/stempel")).laufend};
    }""")
    py.stempel_start(store, job="haupt", projekt="Probe")
    py_lauf = py.stempel_lesen(store)["laufend"]
    py.stempel_pause(store)
    py_pausiert = py.stempel_lesen(store)["laufend"]["pausiert"]
    py.stempel_stop(store, verwerfen=True)
    gleich = (stempel["job"], stempel["projekt"], stempel["pausiert"], stempel["danach"]) == \
             (py_lauf["job"], py_lauf["projekt"], py_pausiert, py.stempel_lesen(store)["laufend"])
    fehlerhaft += 0 if gleich else 1
    print(f"  {'ok  ' if gleich else 'FAIL'} Stempeluhr verhaelt sich gleich: {stempel}")

    # Migration: alter Stand ohne Jobs muss die Sollzeiten behalten
    mig = pg.evaluate("""async () => {
      const d = await new Promise((ok, fail) => {
        const a = indexedDB.open("zeiterfassung");
        a.onsuccess = () => ok(a.result); a.onerror = () => fail(a.error);
      });
      await new Promise((ok, fail) => {
        const t = d.transaction(["einstellungen"], "readwrite");
        t.objectStore("einstellungen").put({
          soll: {"1":8.25,"2":8.25,"3":8.25,"4":8.25,"5":5.5,"6":0,"7":0},
          standardzeiten: {"1":{von:"07:00",bis:"16:00",pause:45}},
          startsaldo: 12.5, startdatum: "2023-01-02", name: "Markus",
        }, "alle");
        t.oncomplete = ok; t.onerror = () => fail(t.error);
      });
      const s = await LOKAL.ruf("/api/einstellungen");
      return {sollMo: s.soll["1"], sollFr: s.soll["5"], startsaldo: s.startsaldo,
              startdatum: s.startdatum, name: s.jobs[0].name, jobs: s.jobs.length};
    }""")
    erwartet = {"sollMo": 8.25, "sollFr": 5.5, "startsaldo": 12.5,
                "startdatum": "2023-01-02", "name": "Markus", "jobs": 1}
    gleich = mig == erwartet
    fehlerhaft += 0 if gleich else 1
    print(f"  {'ok  ' if gleich else 'FAIL'} Migration alter Einstellungen: {mig}")

    # Automatische Sicherung: anlegen, veraendern, zurueckholen
    sich = pg.evaluate("""async () => {
      const vorher = (await LOKAL.ruf("/api/sicherungen")).sicherungen.length;
      const a = await LOKAL.ruf("/api/sicherungen", {method:"POST",
          body: JSON.stringify({grund:"manuell"})});
      const stand = a.sicherungen[0];
      const nochmal = await LOKAL.ruf("/api/sicherungen", {method:"POST",
          body: JSON.stringify({grund:"automatisch", nur_wenn_aelter_als:24})});
      const anzahl = (await LOKAL.ruf("/api/eintraege")).length;
      await LOKAL.ruf("/api/eintraege", {method:"POST", body: JSON.stringify(
          {datum:"2026-09-30", typ:"arbeit", von:"08:00", bis:"12:00", pause:0})});
      const mehr = (await LOKAL.ruf("/api/eintraege")).length;
      await LOKAL.ruf("/api/sicherungen/wiederherstellen", {method:"POST",
          body: JSON.stringify({datei: stand.datei})});
      const zurueck = (await LOKAL.ruf("/api/eintraege")).length;
      const liste = (await LOKAL.ruf("/api/sicherungen")).sicherungen;
      let abgelehnt = false;
      try { await LOKAL.ruf("/api/sicherungen/wiederherstellen", {method:"POST",
              body: JSON.stringify({datei:"gibtsnicht"})}); }
      catch(e){ abgelehnt = true; }
      return {angelegt: a.angelegt, mehrAlsVorher: a.sicherungen.length === vorher + 1,
              nichtDoppelt: nochmal.angelegt === false, wiederGleich: zurueck === anzahl,
              hatMehr: mehr === anzahl + 1,
              vorimport: liste.some(x => x.grund === "vorimport"),
              zeitFormat: /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(stand.zeit), abgelehnt};
    }""")
    erwartet = {"angelegt": True, "mehrAlsVorher": True, "nichtDoppelt": True,
                "wiederGleich": True, "hatMehr": True, "vorimport": True,
                "zeitFormat": True, "abgelehnt": True}
    gleich = sich == erwartet
    fehlerhaft += 0 if gleich else 1
    print(f"  {'ok  ' if gleich else 'FAIL'} Sicherungen verhalten sich wie am Server: {sich}")

    # Wochenrhythmus der Dienste: beide Seiten muessen dieselben Tage liefern
    rhythmen = [
        {"name":"1. Dienst","modus":"durchgehend","starttag":1,"startzeit":"07:00",
         "endtag":1,"endzeit":"07:00","pauschale":0},
        {"name":"2. Dienst","modus":"taeglich","starttag":1,"startzeit":"07:00",
         "endtag":6,"endzeit":"20:00","pauschale":0},
        {"name":"3. Dienst","modus":"taeglich","starttag":5,"startzeit":"07:00",
         "endtag":6,"endzeit":"20:00","pauschale":0},
        {"name":"ohne Rhythmus","pauschale":120},
    ]
    for art in rhythmen:
        for bezug in ("2026-10-07", "2026-01-01", "2027-12-31"):
            py_tage = [list(t) for t in py.dienst_tage(art, bezug)]
            js_tage = pg.evaluate("([a,d]) => LOKAL.dienstTage(a, d)", [art, bezug])
            gleich = py_tage == js_tage
            fehlerhaft += 0 if gleich else 1
            print(f"  {'ok  ' if gleich else 'FAIL'} {art['name']:14} ab {bezug}: "
                  f"{len(py_tage)} Tage, {sum(m for _, m in py_tage)//60} h")

    print("JS-Fehler:", fehler or "keine")
    print("\nAbweichungen:", fehlerhaft)
    b.close()
srv.shutdown()
sys.exit(1 if fehlerhaft else 0)
