"""Klickt die komplette Oberflaeche durch - jede Ansicht, jede Funktion."""
import sys
from playwright.sync_api import sync_playwright

BASIS = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8902"
GERAET = sys.argv[2] if len(sys.argv) > 2 else "pc"
ok = fail = 0
fehler = []

def pruefe(name, bedingung, zusatz=""):
    global ok, fail
    if bedingung:
        ok += 1; print(f"  ok   {name} {zusatz}")
    else:
        fail += 1; print(f"  FAIL {name} {zusatz}")

with sync_playwright() as p:
    b = p.chromium.launch()
    if GERAET == "handy":
        ctx = b.new_context(**p.devices["iPhone 13"], locale="de-AT")
    else:
        ctx = b.new_context(viewport={"width":1250,"height":1000}, locale="de-AT")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: fehler.append(str(e)))
    pg.on("console", lambda m: fehler.append("console: " + m.text) if m.type == "error" else None)
    pg.on("dialog", lambda d: d.accept())
    def navigiere(ziel):
        """Am Handy sitzt die Leiste fest am unteren Rand - dort wie ein Nutzer tippen."""
        if GERAET == "handy":
            r = pg.evaluate("""(ziel) => {
                const k = document.querySelector(`nav#nav button[data-ziel=${ziel}]`);
                const b = k.getBoundingClientRect();
                return {x: b.left + b.width/2, y: b.top + b.height/2};
            }""", ziel)
            pg.mouse.click(r["x"], r["y"])
        else:
            pg.click(f"nav#nav button[data-ziel={ziel}]")
        pg.wait_for_timeout(450)

    pg.goto(BASIS, wait_until="domcontentloaded"); pg.wait_for_timeout(1500)
    pg.evaluate("window.print = () => { window.__gedruckt = true; }")

    print(f"\n--- {GERAET}: Navigation ---")
    for ziel in ["stempeln","erfassen","uebersicht","planung","einstellungen"]:
        navigiere(ziel)
        pruefe(f"Ansicht {ziel}", pg.evaluate("ansicht") == ziel,
               f"| Adresse {pg.url.split('#')[-1]}")

    print(f"\n--- {GERAET}: Einstellungen ---")
    navigiere("einstellungen")
    pg.fill("#soll-1", "8:15"); pg.wait_for_timeout(1600)
    g = pg.evaluate("api('/api/einstellungen')")
    pruefe("Soll 8:15 gespeichert", g["soll"]["1"] == 8.25, f"= {g['soll']['1']}")
    pruefe("automatisch gespeichert", "Gespeichert" in pg.inner_text("#speicherStand"))
    pg.select_option("#s-rundung", "15"); pg.wait_for_timeout(1600)
    pg.locator("#jobListe input[type=text]").nth(1).fill("25"); pg.wait_for_timeout(1700)
    g = pg.evaluate("api('/api/einstellungen')")
    pruefe("Rundung gespeichert", g["rundung"] == 15)
    pruefe("Urlaubsanspruch gespeichert", g["jobs"][0]["urlaubstage"] == 25)
    # Notizvorlagen ueber die Liste
    pg.click("button:has-text('+ Vorlage')"); pg.wait_for_timeout(200)
    pg.locator("#notizListe input[type=text]").last.fill("Kundendienst"); pg.wait_for_timeout(1700)
    g = pg.evaluate("api('/api/einstellungen')")
    pruefe("Notizvorlage gespeichert", g["notizvorlagen"] == ["Kundendienst"], str(g["notizvorlagen"]))
    pruefe("Vorschlagsliste gefuellt",
           pg.locator("#notizvorlagen option").count() == 1)
    # Zweiter Job
    pg.click("button:has-text('+ Job')"); pg.wait_for_timeout(200)
    felder = pg.locator("#jobListe input[type=text]")
    print(f"       (Textfelder in der Jobliste: {felder.count()})")
    felder.nth(2).fill("Nebenjob"); pg.wait_for_timeout(2000)
    g = pg.evaluate("api('/api/einstellungen')")
    pruefe("zweiter Job angelegt", len(g["jobs"]) == 2, str([j["name"] for j in g["jobs"]]))

    print(f"\n--- {GERAET}: Erfassen ---")
    navigiere("erfassen")
    pg.fill("#f-datum", "2026-08-19"); pg.dispatch_event("#f-datum","change"); pg.wait_for_timeout(400)
    pruefe("Standardzeiten vorbelegt", pg.input_value("#f-von") == "08:00")
    pg.fill("#f-von","7"); pg.locator("#f-von").blur()
    pg.fill("#f-bis","1607"); pg.locator("#f-bis").blur(); pg.wait_for_timeout(300)
    pruefe("Kurzeingabe der Zeiten", pg.input_value("#f-von") == "07:00" and pg.input_value("#f-bis") == "16:07")
    pg.fill("#f-pause","45"); pg.click("#submitBtn"); pg.wait_for_timeout(900)
    pruefe("Eintrag gespeichert", "gespeichert" in pg.inner_text("#msg").lower(), pg.inner_text("#msg")[:40])
    a = pg.evaluate("api('/api/auswertung?von=2026-08-19&bis=2026-08-19&job=alle')")
    pruefe("Rundung wirkt (502 -> 495)", a["ist"] == 495, f"= {a['ist']}")
    # Urlaub mit halbem Tag
    pg.select_option("#f-typ","urlaub"); pg.wait_for_timeout(300)
    pg.fill("#f-datum","2026-08-20"); pg.dispatch_event("#f-datum","change")
    pg.fill("#f-gutschrift","240"); pg.click("#submitBtn"); pg.wait_for_timeout(900)
    # Dienst
    pg.select_option("#f-typ","dienst"); pg.wait_for_timeout(300)
    pruefe("Dienstart-Auswahl erscheint", pg.is_visible("#f-dienst-wrap"))
    pg.fill("#f-datum","2026-08-21"); pg.dispatch_event("#f-datum","change")
    pg.click("#submitBtn"); pg.wait_for_timeout(900)
    # Bearbeiten
    pg.locator("#tabelle button[title=Bearbeiten]").first.click(); pg.wait_for_timeout(500)
    pruefe("Bearbeiten fuellt das Formular", pg.input_value("#f-id") != "")
    pg.click("#submitBtn"); pg.wait_for_timeout(800)
    # Loeschen und Rueckgaengig
    vorher = pg.locator("#tabelle tbody tr").count()
    pg.locator("#tabelle button.danger").first.click(); pg.wait_for_timeout(900)
    nachher = pg.locator("#tabelle tbody tr").count()
    pruefe("Eintrag geloescht", nachher == vorher - 1, f"{vorher} -> {nachher}")
    pg.locator("#rueckgaengig button").click(); pg.wait_for_timeout(1000)
    pruefe("Rueckgaengig stellt wieder her", pg.locator("#tabelle tbody tr").count() == vorher)

    print(f"\n--- {GERAET}: Stempeluhr ---")
    navigiere("stempeln")
    pg.click("#stempelKnopf"); pg.wait_for_timeout(900)
    pruefe("Messung laeuft", "Gehen" in pg.inner_text("#stempelKnopf"), pg.inner_text("#stempelKnopf"))
    pg.click("#stempelPause"); pg.wait_for_timeout(600)
    pruefe("Pause laeuft", "Pause beenden" in pg.inner_text("#stempelPause"), pg.inner_text("#stempelPause"))
    pg.click("#stempelPause"); pg.wait_for_timeout(600)
    pg.click("#stempelKnopf"); pg.wait_for_timeout(1200)
    meldung = pg.inner_text("#msg")
    pruefe("kurze Messung wird abgefangen",
           "weniger als einer Minute" in meldung or "Pause ist so lang" in meldung, meldung[:60])
    pg.click("#stempelWeg"); pg.wait_for_timeout(1000)
    pruefe("Verwerfen beendet die Messung", "Kommen" in pg.inner_text("#stempelKnopf"),
           pg.inner_text("#stempelKnopf").strip())
    # Fuer die Heute-Liste einen Eintrag von heute anlegen
    pg.evaluate("""async () => {
        const heuteTag = new Date().toISOString().slice(0,10);
        await api("/api/eintraege", {method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({datum: heuteTag, typ:"arbeit", von:"07:00", bis:"12:00", pause:0})});
    }""")
    pg.wait_for_timeout(600); navigiere("erfassen")
    navigiere("stempeln")
    pruefe("Heute-Liste gefuellt", "Saldo heute" in pg.inner_text("#heuteListe"))

    print(f"\n--- {GERAET}: Uebersicht und Bericht ---")
    navigiere("uebersicht")
    pruefe("Kennzahlen sichtbar", "Gearbeitet" in pg.inner_text("#uebersichtListe"))
    pruefe("Urlaubskonto sichtbar", pg.is_visible("#urlaubPanel"))
    pruefe("Dienste sichtbar", pg.is_visible("#dienstPanel"))
    pg.click("button:has-text('Bericht drucken')"); pg.wait_for_timeout(700)
    html = pg.eval_on_selector("#bericht", "el => el.innerHTML")
    pruefe("Bericht erzeugt", "Arbeitszeitnachweis" in html and "Unterschrift" in html, f"{len(html)} Zeichen")
    pruefe("Druck ausgeloest", pg.evaluate("window.__gedruckt === true"))

    print(f"\n--- {GERAET}: Feiertage und Dienste ---")
    navigiere("planung")
    pruefe("Feiertagsliste geladen", pg.locator("#feiertagsListe tbody tr").count() >= 13,
           f"{pg.locator('#feiertagsListe tbody tr').count()} Zeilen")
    pg.click("button:has-text('Feiertage eintragen')"); pg.wait_for_timeout(1500)
    pruefe("Feiertage eingetragen", "eingetragen" in pg.inner_text("#msg"), pg.inner_text("#msg")[:50])
    # Dienst mit Wochenrhythmus: Mittwoch gewaehlt, Beginn zieht auf Montag
    pg.select_option("#d-art", "dienst-1")
    pg.fill("#d-von", "2026-08-26"); pg.wait_for_timeout(400)
    vorschau = pg.inner_text("#dienstVorschau")
    pruefe("Dienstvorschau zeigt den Zeitraum", "24.08.2026" in vorschau and "168" in vorschau,
           vorschau[:80])
    pruefe("Enddatum bei Rhythmus verborgen",
           pg.eval_on_selector("#d-bis-wrap", "e => getComputedStyle(e).display") == "none")
    pg.click("button:has-text('Dienst anlegen')"); pg.wait_for_timeout(1200)
    pruefe("Dienstwoche angelegt", "Tage eingetragen" in pg.inner_text("#msg"), pg.inner_text("#msg")[:60])
    # Ausfahrt im Dienst erfassen
    navigiere("erfassen")
    pg.fill("#f-datum", "2026-08-26"); pg.dispatch_event("#f-datum", "change")
    pg.select_option("#f-typ", "ausfahrt"); pg.wait_for_timeout(200)
    pruefe("Ausfahrt braucht keine Gutschrift",
           pg.eval_on_selector("#f-gutschrift-wrap", "e => getComputedStyle(e).display") == "none")
    pg.fill("#f-von", "22:00"); pg.fill("#f-bis", "23:30"); pg.fill("#f-pause", "0")
    pg.fill("#f-notiz", "Rohrbruch")
    pg.click("#form button.primary"); pg.wait_for_timeout(1200)
    a = pg.evaluate("api('/api/auswertung?von=2026-08-24&bis=2026-08-31')")
    pruefe("Ausfahrt gesondert verrechnet", a["ausfahrt"] == 90 and a["ist"] == 0,
           f"ausfahrt={a['ausfahrt']} ist={a['ist']}")
    pruefe("Pauschale gesondert verrechnet", a["pauschale"] == 168 * 60, f"= {a['pauschale']}")
    pruefe("Kachel Dienstpauschale sichtbar",
           pg.eval_on_selector("#kpi-pauschale", "e => getComputedStyle(e).display") != "none")
    pruefe("Ausfahrtenliste sichtbar", pg.locator("#ausfahrtListe tbody tr").count() == 1,
           f"{pg.locator('#ausfahrtListe tbody tr').count()} Zeilen")
    navigiere("planung")
    pg.click("button:has-text('Arbeitstage auffüllen')"); pg.wait_for_timeout(1800)
    pruefe("Auffuellen gelaufen", "Arbeitstage" in pg.inner_text("#msg") or "Nichts" in pg.inner_text("#msg"),
           pg.inner_text("#msg")[:60])

    print(f"\n--- {GERAET}: Export ---")
    exp = pg.evaluate("api('/api/export.json')")
    pruefe("Export enthaelt Eintraege", len(exp["eintraege"]) > 5, f"{len(exp['eintraege'])} Eintraege")
    pruefe("Export enthaelt Jobs", len(exp["einstellungen"]["jobs"]) == 2)

    print(f"\nJS-Fehler: {fehler if fehler else 'keine'}")
    print(f"\n{GERAET}: {ok} ok, {fail} Fehler, {len(fehler)} JS-Fehler")
    b.close()
sys.exit(1 if (fail or fehler) else 0)
