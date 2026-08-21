"""Bekommt eine bereits installierte App die neue Fassung?"""
import shutil, os, sys, threading, http.server, functools
from playwright.sync_api import sync_playwright

ORT = "/tmp/sw_stand"
shutil.rmtree(ORT, ignore_errors=True)
shutil.copytree(os.environ.get("ALT_STATIC", "/home/claude/gh-stand/static"), ORT)
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ORT)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8871), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

ok = fail = 0
def pruefe(name, bedingung, zusatz=""):
    global ok, fail
    if bedingung: ok += 1; print(f"  ok   {name} {zusatz}")
    else: fail += 1; print(f"  FAIL {name} {zusatz}")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(locale="de-AT").new_page()
    pg.goto("http://127.0.0.1:8871/"); pg.wait_for_timeout(2000)
    aktiv = pg.evaluate("async () => { const r = await navigator.serviceWorker.ready;"
                        " return !!r.active; }")
    pruefe("Service Worker installiert", aktiv)
    pruefe("alte Fassung laeuft", pg.evaluate("() => typeof LOKAL.ruf") == "function")
    hat_jobs_alt = pg.evaluate("async () => 'jobs' in (await LOKAL.ruf('/api/einstellungen'))")
    pruefe("alte Fassung kennt keine Jobs", hat_jobs_alt is False)

    # neue Fassung an dieselbe Adresse legen
    for f in os.listdir(ORT): os.remove(os.path.join(ORT, f))
    for f in os.listdir(os.environ.get("NEU_STATIC", "/home/claude/zeiterfassung/static")):
        shutil.copy(os.path.join(os.environ.get("NEU_STATIC", "/home/claude/zeiterfassung/static"), f), ORT)

    for versuch in range(1, 4):
        pg.reload(); pg.wait_for_timeout(2500)
        hat_jobs = pg.evaluate("async () => 'jobs' in (await LOKAL.ruf('/api/einstellungen'))")
        if hat_jobs: break
    pruefe(f"neue Fassung nach {versuch} Neuladen aktiv", hat_jobs)
    ver = pg.evaluate("async () => { const c = await caches.keys(); return c; }")
    pruefe("Cache traegt die neue Kennung", any("v9" in x for x in ver), str(ver))
    b.close()
srv.shutdown()
print(f"\n{ok} ok, {fail} Fehler")
sys.exit(1 if fail else 0)
