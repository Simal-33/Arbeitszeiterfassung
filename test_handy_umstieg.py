"""Der Ernstfall: Daten der GitHub-Fassung im Browser, dann die neue Fassung darueber."""
import shutil, os, sys, threading, http.server, functools, json
from playwright.sync_api import sync_playwright

ORT = "/tmp/handy_stand"
shutil.rmtree(ORT, ignore_errors=True)
shutil.copytree(os.environ.get("ALT_STATIC", "/home/claude/gh-stand/static"), ORT)
class OhneCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
handler = functools.partial(OhneCache, directory=ORT)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8870), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

ok = fail = 0
def check(name, a, b):
    global ok, fail
    if a == b: ok += 1; print(f"  ok   {name}: {a}")
    else: fail += 1; print(f"  FAIL {name}: alt={a!r} neu={b!r}")

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(locale="de-AT", service_workers="block")
    pg = ctx.new_page()
    fehler = []
    pg.on("pageerror", lambda e: fehler.append(str(e)))
    pg.goto("http://127.0.0.1:8870/"); pg.wait_for_timeout(1500)

    # --- Stand anlegen, wie ihn die GitHub-Fassung schreibt ---
    alt_stand = pg.evaluate("""async () => {
      await LOKAL.ruf("/api/einstellungen", {method:"PUT", body: JSON.stringify({
        soll: {"1":8.25,"2":8.25,"3":8.25,"4":8.25,"5":5.5,"6":0,"7":0},
        startsaldo: 12.5, startdatum: "2026-01-01", name: "Markus"})});
      await LOKAL.ruf("/api/dienste", {method:"POST",
        body: JSON.stringify({dienstart:"dienst-1", von:"2026-03-07"})});
      await LOKAL.ruf("/api/dienste", {method:"POST",
        body: JSON.stringify({dienstart:"dienst-3", von:"2026-04-06"})});
      for (const e of [
        {datum:"2026-03-06",typ:"arbeit",von:"07:00",bis:"16:00",pause:45},
        {datum:"2026-03-06",typ:"ausfahrt",von:"22:00",bis:"23:30",pause:0,notiz:"Rohrbruch"},
        {datum:"2026-03-08",typ:"ausfahrt",von:"23:30",bis:"01:00",pause:0},
        {datum:"2026-03-09",typ:"urlaub"},
        {datum:"2026-04-07",typ:"arbeit",von:"08:00",bis:"12:00",pause:0}])
        await LOKAL.ruf("/api/eintraege", {method:"POST", body: JSON.stringify(e)});
      const a = await LOKAL.ruf("/api/auswertung?von=2026-03-01&bis=2026-04-30");
      return {ist:a.ist, gutschrift:a.gutschrift, soll:a.soll, saldo:a.saldo,
              pauschale:a.pauschale, ausfahrt:a.ausfahrt,
              dienste:a.dienste.map(d => [d.id,d.tage,d.minuten,d.ausfahrten,d.ausfahrt_minuten]),
              ausfahrten:a.ausfahrten.map(x => [x.datum,x.von,x.bis,x.minuten,x.dienst]),
              eintraege:(await LOKAL.ruf("/api/eintraege")).length};
    }""")
    print("Stand der GitHub-Fassung:", json.dumps(alt_stand)[:120], "...")

    # --- jetzt die neue Fassung auf dieselbe Adresse legen ---
    for f in os.listdir(ORT): os.remove(os.path.join(ORT, f))
    for f in os.listdir(os.environ.get("NEU_STATIC", "/home/claude/zeiterfassung/static")):
        shutil.copy(os.path.join(os.environ.get("NEU_STATIC", "/home/claude/zeiterfassung/static"), f), ORT)
    pg.goto("http://127.0.0.1:8870/?neu"); pg.wait_for_timeout(2500)
    probe = pg.evaluate("async () => { const s = await LOKAL.ruf('/api/einstellungen');"
                        " return Object.keys(s); }")
    print("Felder der Einstellungen:", probe)

    neu_stand = pg.evaluate("""async () => {
      const a = await LOKAL.ruf("/api/auswertung?von=2026-03-01&bis=2026-04-30");
      const s = await LOKAL.ruf("/api/einstellungen");
      return {ist:a.ist, gutschrift:a.gutschrift, soll:a.soll, saldo:a.saldo,
              pauschale:a.pauschale, ausfahrt:a.ausfahrt,
              dienste:a.dienste.map(d => [d.id,d.tage,d.minuten,d.ausfahrten,d.ausfahrt_minuten]),
              ausfahrten:a.ausfahrten.map(x => [x.datum,x.von,x.bis,x.minuten,x.dienst]),
              eintraege:(await LOKAL.ruf("/api/eintraege")).length,
              jobs:s.jobs.length, jobName:s.jobs[0].name, sollMo:s.jobs[0].soll["1"],
              sollFr:s.jobs[0].soll["5"], startsaldo:s.jobs[0].startsaldo,
              startdatum:s.jobs[0].startdatum,
              arten:s.dienstarten.map(x => [x.id,x.modus,x.starttag,x.startzeit,x.endtag,x.endzeit])};
    }""")

    for feld in ("eintraege","ist","gutschrift","soll","saldo","pauschale","ausfahrt",
                 "dienste","ausfahrten"):
        check(feld, alt_stand[feld], neu_stand[feld])
    check("ein Job aus dem alten Stand", neu_stand["jobs"], 1)
    check("Jobname", neu_stand["jobName"], "Markus")
    check("Sollzeiten", (neu_stand["sollMo"], neu_stand["sollFr"]), (8.25, 5.5))
    check("Startsaldo", neu_stand["startsaldo"], 12.5)
    check("Startdatum", neu_stand["startdatum"], "2026-01-01")
    check("Dienstarten unveraendert", neu_stand["arten"],
          [["dienst-1","durchgehend",1,"07:00",1,"07:00"],
           ["dienst-2","taeglich",1,"07:00",6,"20:00"],
           ["dienst-3","taeglich",5,"07:00",6,"20:00"]])
    print("JS-Fehler:", fehler or "keine")
    if fehler: fail += len(fehler)
    b.close()
srv.shutdown()
print(f"\n{ok} ok, {fail} Fehler")
sys.exit(1 if fail else 0)
