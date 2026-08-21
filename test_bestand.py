"""Prueft, ob Daten der GitHub-Fassung in der neuen Fassung gleich bleiben."""
import os, sys, json, shutil
sys.path.insert(0, os.environ.get("ALT_DIR", "/home/claude/gh-stand"))
import app as alt
sys.path.insert(0, "/home/claude/zeiterfassung")
del sys.modules["app"]
sys.path.insert(0, "/home/claude/zeiterfassung")
import importlib.util
spec = importlib.util.spec_from_file_location("neu_app", "/home/claude/zeiterfassung/app.py")
neu = importlib.util.module_from_spec(spec); spec.loader.exec_module(neu)

ok = fail = 0
def check(name, a, b):
    global ok, fail
    if a == b: ok += 1; print(f"  ok   {name}: {a}")
    else: fail += 1; print(f"  FAIL {name}: alt={a!r} neu={b!r}")

# --- Datenbank mit der ALTEN Fassung befuellen ---
p = "/tmp/bestand.db"
for f in (p, "/tmp/bestand-sicherungen"):
    shutil.rmtree(f, ignore_errors=True) if os.path.isdir(f) else (os.path.exists(f) and os.remove(f))
st = alt.Store(p)
st.save_settings({"soll": {"1":8.25,"2":8.25,"3":8.25,"4":8.25,"5":5.5,"6":0,"7":0},
                  "startsaldo": 12.5, "startdatum": "2026-01-01", "name": "Markus"})
alt.dienst_eintragen(st, "dienst-1", "2026-03-07")
alt.dienst_eintragen(st, "dienst-3", "2026-04-06")
arten = {a["id"]: a for a in st.get_settings()["dienstarten"]}
for e in [
    {"datum":"2026-03-06","typ":"arbeit","von":"07:00","bis":"16:00","pause":45},
    {"datum":"2026-03-06","typ":"ausfahrt","von":"22:00","bis":"23:30","pause":0,"notiz":"Rohrbruch"},
    {"datum":"2026-03-08","typ":"ausfahrt","von":"23:30","bis":"01:00","pause":0},
    {"datum":"2026-03-09","typ":"urlaub"},
    {"datum":"2026-04-07","typ":"arbeit","von":"08:00","bis":"12:00","pause":0},
]:
    st.insert_entry(alt.clean_entry(e, arten))

a_alt = alt.compute(st.list_entries("2026-03-01","2026-04-30"),
                    alt.effective_settings(st) if hasattr(alt,"effective_settings") else st.get_settings(),
                    "2026-03-01","2026-04-30")
sicherung_alt = alt.export_json(st)

# --- dieselbe Datei mit der NEUEN Fassung oeffnen ---
st2 = neu.Store(p)
s2 = st2.get_settings()
check("Anzahl Dienstarten", len(st.get_settings()["dienstarten"]), len(s2["dienstarten"]))
check("Dienstarten unveraendert",
      [(a["id"], a.get("modus"), a.get("starttag"), a.get("startzeit"), a.get("endtag"), a.get("endzeit"))
       for a in st.get_settings()["dienstarten"]],
      [(a["id"], a.get("modus"), a.get("starttag"), a.get("startzeit"), a.get("endtag"), a.get("endzeit"))
       for a in s2["dienstarten"]])
check("Sollzeiten uebernommen", (s2["jobs"][0]["soll"]["1"], s2["jobs"][0]["soll"]["5"]), (8.25, 5.5))
check("Startsaldo uebernommen", s2["jobs"][0]["startsaldo"], 12.5)
check("Startdatum uebernommen", s2["jobs"][0]["startdatum"], "2026-01-01")
check("Name wird Jobname", s2["jobs"][0]["name"], "Markus")
check("Eintragszahl gleich", len(st.list_entries()), len(st2.list_entries()))

a_neu = neu.auswertung(st2, "2026-03-01", "2026-04-30")
for feld in ("ist", "gutschrift", "soll", "saldo", "pauschale", "ausfahrt"):
    check("Auswertung " + feld, a_alt[feld], a_neu[feld])
check("Dienste gleich",
      [(d["id"], d["tage"], d["minuten"], d["ausfahrten"], d["ausfahrt_minuten"]) for d in a_alt["dienste"]],
      [(d["id"], d["tage"], d["minuten"], d["ausfahrten"], d["ausfahrt_minuten"]) for d in a_neu["dienste"]])
check("Ausfahrten gleich",
      [(x["datum"], x["von"], x["bis"], x["minuten"], x["dienst"]) for x in a_alt["ausfahrten"]],
      [(x["datum"], x["von"], x["bis"], x["minuten"], x["dienst"]) for x in a_neu["ausfahrten"]])

# --- Sicherung der alten Fassung in die neue importieren ---
p2 = "/tmp/bestand2.db"
for f in (p2, "/tmp/bestand2-sicherungen"):
    shutil.rmtree(f, ignore_errors=True) if os.path.isdir(f) else (os.path.exists(f) and os.remove(f))
st3 = neu.Store(p2)
anzahl = neu.import_data(st3, sicherung_alt, "ersetzen")
check("Sicherung importierbar", anzahl, len(st.list_entries()))
a_imp = neu.auswertung(st3, "2026-03-01", "2026-04-30")
for feld in ("ist", "gutschrift", "soll", "saldo", "pauschale", "ausfahrt"):
    check("nach Import " + feld, a_alt[feld], a_imp[feld])

print(f"\n{ok} ok, {fail} Fehler")
sys.exit(1 if fail else 0)
