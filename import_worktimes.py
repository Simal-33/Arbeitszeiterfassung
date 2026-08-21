#!/usr/bin/env python3
"""Wandelt eine Sicherung der iOS-App "Arbeitszeit" (.worktimes) in eine
Import-Datei fuer diese Zeiterfassung um.

    python3 import_worktimes.py Arbeitszeit.worktimes -o import.json

Die .worktimes-Datei ist ein ZIP mit einer Core-Data-Datenbank. Zeitstempel
liegen dort als Sekunden seit 2001-01-01 UTC vor und werden in die Ortszeit
des jeweiligen Eintrags umgerechnet.
"""

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

APPLE_EPOCHE = datetime(2001, 1, 1, tzinfo=timezone.utc)
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Aufzeichnungsarten der Quell-App -> Arten dieser App
ARTEN = {
    "recording.type.working-hours": "arbeit",
    "recording.type.home-office":   "arbeit",
    "recording.type.travel-time":   "arbeit",
    "recording.type.vacation":      "urlaub",
    "recording.type.special-leave": "urlaub",
    "recording.type.sick-day":      "krank",
    "recording.type.child-sick":    "krank",
    "recording.type.public-holiday": "feiertag",
    # Zeitausgleich: der Tag zaehlt zum Soll, wird aber nicht gutgeschrieben
    "recording.type.overtime":      "gleitzeit",
}
KLARNAMEN = {
    "recording.type.working-hours": "", "recording.type.home-office": "Homeoffice",
    "recording.type.travel-time": "Reisezeit", "recording.type.vacation": "Urlaub",
    "recording.type.special-leave": "Sonderurlaub", "recording.type.sick-day": "Krank",
    "recording.type.child-sick": "Kind krank", "recording.type.public-holiday": "Feiertag",
    "recording.type.overtime": "Zeitausgleich",
}


def oeffne(pfad, arbeitsordner):
    """Entpackt die Sicherung und gibt eine Verbindung zur Datenbank zurueck."""
    if zipfile.is_zipfile(pfad):
        with zipfile.ZipFile(pfad) as z:
            z.extractall(arbeitsordner)
        treffer = [os.path.join(arbeitsordner, n) for n in os.listdir(arbeitsordner)
                   if n.endswith(".db")]
        if not treffer:
            raise SystemExit("In der Sicherung ist keine .db-Datei enthalten.")
        db = treffer[0]
    else:
        db = shutil.copy(pfad, os.path.join(arbeitsordner, "worktimes.db"))
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con


def spanne_minuten(von, bis):
    a = int(von[:2]) * 60 + int(von[3:])
    b = int(bis[:2]) * 60 + int(bis[3:])
    return b - a if b > a else b - a + 24 * 60


def ortszeit(sekunden, zone):
    zeitpunkt = APPLE_EPOCHE + timedelta(seconds=float(sekunden))
    if ZoneInfo and zone:
        try:
            return zeitpunkt.astimezone(ZoneInfo(zone))
        except Exception:
            pass
    return zeitpunkt


def konvertiere(con, standardzone="Europe/Vienna", kompatibel=False):
    warnungen = []

    typen = {r["Z_PK"]: r["ZNAME"] for r in con.execute("SELECT Z_PK, ZNAME FROM ZRECORDINGTYPE")}

    # -- Sollstunden je Wochentag; Wochentag-ID 1 = Sonntag ... 7 = Samstag
    soll = {str(d): 0.0 for d in range(1, 8)}
    for r in con.execute("""SELECT ZWEEKDAYID w, MAX(ZDURATION) d FROM ZREGULARHOURSDURATION
                            GROUP BY ZWEEKDAYID"""):
        unser = ((r["w"] - 2) % 7) + 1          # 2 -> 1 (Montag), 1 -> 7 (Sonntag)
        soll[str(unser)] = round((r["d"] or 0) / 3600, 4)

    pausen = {}
    for r in con.execute("SELECT ZWEEKDAYID w, ZDURATION d FROM ZWORKINGBREAKPRESET"):
        pausen[((r["w"] - 2) % 7) + 1] = int((r["d"] or 0) // 60)

    # -- Dienstarten aus den Tags der Quell-App
    tagnamen = {r["Z_PK"]: (r["ZNAME"] or "").strip() for r in con.execute("SELECT Z_PK, ZNAME FROM ZTAG")}
    zuordnung = defaultdict(set)               # Datum -> {Tagname}
    for r in con.execute("""SELECT x.ZTAG t, r.ZSTARTDATE s, r.ZTIMEZONE z
                            FROM ZTAGASSIGNMENT x JOIN ZRECORDING r ON r.Z_PK = x.ZRECORDING
                            WHERE r.ZISALLDAY = 0"""):
        name = tagnamen.get(r["t"], "").strip()
        if name:
            zuordnung[ortszeit(r["s"], r["z"] or standardzone).strftime("%Y-%m-%d")].add(name)

    # Die alte App kannte "Notdienst 1er/2er/3er" nur als Tagesmarkierung ohne
    # Zeit. Das sind dieselben drei Dienste, die die neue App voreingestellt hat -
    # die Kennungen werden darauf abgebildet, damit die Namen stimmen. Die
    # Pauschale bleibt 0: fuer die Vergangenheit wurde sie nie erfasst, und
    # nachtraeglich 168 Stunden zu buchen wuerde die Zahlen verfaelschen.
    BEKANNT = {"notdienst 1er": ("dienst-1", "1. Dienst", "#b45309"),
               "notdienst 2er": ("dienst-2", "2. Dienst", "#0f766e"),
               "notdienst 3er": ("dienst-3", "3. Dienst", "#6d28d9")}

    dienstarten, kennungen, vergeben = [], {}, set()
    for name in sorted({n for tage in zuordnung.values() for n in tage}):
        treffer = BEKANNT.get(name.strip().lower())
        if treffer:
            kennung, anzeige, farbe = treffer
        else:
            kennung = name.lower().replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
            kennung = "".join(c if c.isalnum() else "-" for c in kennung).strip("-")
            while "--" in kennung:
                kennung = kennung.replace("--", "-")
            anzeige, farbe = name, "#b45309"
        kennungen[name] = kennung
        if kennung in vergeben:
            continue
        vergeben.add(kennung)
        dienstarten.append({"id": kennung, "name": anzeige, "pauschale": 0, "farbe": farbe})

    # -- Mehrtaegige Abwesenheiten liegen als "Folge" vor: mehrere Zeilen mit
    #    identischem Start- und Enddatum, je eine pro Tag. Sie werden ab dem
    #    Startdatum auf aufeinanderfolgende Tage verteilt (Wurzelzeile zuerst).
    folgen = defaultdict(list)
    for r in con.execute("""SELECT * FROM ZRECORDING WHERE ZSEQUENCEID IS NOT NULL
                            AND ZISALLDAY = 1
                            ORDER BY (ZSEQUENCEROOTITEM IS NOT NULL), Z_PK"""):
        folgen[r["ZSEQUENCEID"]].append(r["Z_PK"])
    tag_versatz = {}
    for mitglieder in folgen.values():
        for i, pk in enumerate(mitglieder):
            tag_versatz[pk] = i

    # -- Eintraege. Zeitausgleich kommt zum Schluss, weil dafuer feststehen muss,
    #    ob am selben Tag auch gearbeitet wurde.
    eintraege, uebersprungen = [], []
    reihenfolge = sorted(
        con.execute("""SELECT * FROM ZRECORDING
                       ORDER BY ZSTARTDATE, (ZSEQUENCEROOTITEM IS NOT NULL), Z_PK""").fetchall(),
        key=lambda z: ARTEN.get(typen.get(z["ZRECORDINGTYPE"], ""), "") == "gleitzeit")
    for r in reihenfolge:
        quelle = typen.get(r["ZRECORDINGTYPE"], "")
        art = ARTEN.get(quelle)
        zone = r["ZTIMEZONE"] or standardzone
        beginn = ortszeit(r["ZSTARTDATE"], zone) + timedelta(days=tag_versatz.get(r["Z_PK"], 0))
        datum = beginn.strftime("%Y-%m-%d")
        dauer = int(round((r["ZDURATION"] or 0) / 60))
        notiz = (r["ZNOTE"] or "").strip() or KLARNAMEN.get(quelle, "")

        if art is None:
            uebersprungen.append((datum, "unbekannte Art: %s" % quelle))
            continue

        if art == "arbeit" and not r["ZISALLDAY"]:
            if dauer <= 0:
                uebersprungen.append((datum, "Arbeitszeit ohne Dauer"))
                continue
            ende = ortszeit(r["ZENDDATE"], zone)
            von, bis = beginn.strftime("%H:%M"), ende.strftime("%H:%M")
            spanne = (int(bis[:2]) * 60 + int(bis[3:])) - (int(von[:2]) * 60 + int(von[3:]))
            if spanne <= 0:
                spanne += 24 * 60
            pause = spanne - dauer          # so ergibt die Rechnung exakt die Quell-Dauer
            if pause < 0:
                uebersprungen.append((datum, "Dauer groesser als die Zeitspanne"))
                continue
            gemeldet = int(round((r["ZWORKINGBREAK"] or 0) / 60))
            if pause != gemeldet:
                warnungen.append(f"{datum}: Pause auf {pause} min gesetzt (Quelle: {gemeldet} min), "
                                 "damit die Dauer exakt stimmt - meist Sommerzeitumstellung.")
            eintraege.append({"datum": datum, "typ": "arbeit", "von": von, "bis": bis,
                              "pause": pause, "projekt": "", "notiz": notiz, "gutschrift": None,
                              "dienstart": ""})
        elif art == "gleitzeit":
            # Zeitausgleich. Wurde an dem Tag auch gearbeitet, ist es eine echte
            # Abbuchung vom Saldo (negative Gutschrift). An freien Tagen entsteht
            # das Minus bereits dadurch, dass die Sollzeit nicht gearbeitet wurde.
            abzug = int(round(abs(r["ZOVERTIME"] or 0) / 60))
            gearbeitet = [e for e in eintraege if e["datum"] == datum and e["typ"] == "arbeit"]
            if gearbeitet and kompatibel:
                # Aeltere Staende kennen keine negative Gutschrift: die abgebuchten
                # Stunden werden stattdessen von der Arbeitszeit des Tages abgezogen.
                # Der Saldo stimmt damit exakt, nur die ausgewiesene Ist-Zeit ist
                # um den abgebuchten Anteil kuerzer.
                rest = abzug
                for e in sorted(gearbeitet, key=lambda x: x["von"], reverse=True):
                    dauer_e = spanne_minuten(e["von"], e["bis"]) - e["pause"]
                    nimm = min(rest, max(0, dauer_e - 1))
                    e["pause"] += nimm
                    e["notiz"] = (e["notiz"] + " " if e["notiz"] else "") + \
                                 "(%d:%02d h abgebucht)" % (nimm // 60, nimm % 60)
                    rest -= nimm
                    if rest <= 0:
                        break
                if rest > 0:
                    warnungen.append(f"{datum}: {rest} min Zeitausgleich konnten nicht "
                                     "abgezogen werden.")
                gutschrift = 0
            else:
                gutschrift = -abzug if gearbeitet else 0
            eintraege.append({"datum": datum, "typ": art, "von": "", "bis": "", "pause": 0,
                              "projekt": "", "notiz": notiz, "gutschrift": gutschrift,
                              "dienstart": ""})
        else:
            # Ganztaegige Arten: die Gutschrift der Quelle wird uebernommen
            eintraege.append({"datum": datum, "typ": art, "von": "", "bis": "", "pause": 0,
                              "projekt": "", "notiz": notiz, "gutschrift": max(0, dauer),
                              "dienstart": ""})

    # -- Diensttage aus den Tags (ohne Zeitwirkung, Pauschale spaeter einstellbar)
    for datum, namen in sorted(zuordnung.items()):
        for name in sorted(namen):
            eintraege.append({"datum": datum, "typ": "dienst", "von": "", "bis": "", "pause": 0,
                              "projekt": "", "notiz": name, "gutschrift": 0,
                              "dienstart": kennungen[name]})

    eintraege.sort(key=lambda e: (e["datum"], e["von"], e["typ"]))

    konto = con.execute("SELECT ZNAME FROM ZACCOUNT LIMIT 1").fetchone()
    standardzeiten = typische_zeiten(eintraege, pausen, soll)
    einstellungen = {
        "soll": soll,
        "standardzeiten": standardzeiten,
        "sondertage": "keine",
        "dienstarten": dienstarten,
        "startsaldo": 0,
        "startdatum": eintraege[0]["datum"] if eintraege else "",
        "name": (konto["ZNAME"] if konto else "") or "",
    }
    return {"app": "Zeiterfassung", "version": 1,
            "exportiert_am": datetime.now().isoformat(timespec="seconds"),
            "einstellungen": einstellungen, "eintraege": eintraege}, uebersprungen, warnungen


def typische_zeiten(eintraege, pausen, soll):
    """Haeufigste Arbeitszeiten je Wochentag als Vorschlag fuer die Einstellungen."""
    proTag = defaultdict(list)
    for e in eintraege:
        if e["typ"] == "arbeit" and e["von"] and e["bis"]:
            wd = datetime.strptime(e["datum"], "%Y-%m-%d").isoweekday()
            proTag[wd].append((e["von"], e["bis"], e["pause"]))
    ergebnis = {}
    for d in range(1, 8):
        werte = proTag.get(d, [])
        # Nur fuer echte Arbeitstage und nur bei ausreichend vielen Beispielen
        if float(soll.get(str(d), 0)) <= 0 or len(werte) < 20:
            ergebnis[str(d)] = None
            continue
        von = Counter(v for v, _, _ in werte).most_common(1)[0][0]
        bis = Counter(b for _, b, _ in werte).most_common(1)[0][0]
        ergebnis[str(d)] = {"von": von, "bis": bis, "pause": pausen.get(d, 0)}
    return ergebnis


def main():
    ap = argparse.ArgumentParser(description="Sicherung der App 'Arbeitszeit' umwandeln")
    ap.add_argument("datei", help="Pfad zur .worktimes-Datei")
    ap.add_argument("-o", "--ausgabe", default="import.json")
    ap.add_argument("--zeitzone", default="Europe/Vienna")
    ap.add_argument("--kompatibel", action="store_true",
                    help="fuer aeltere App-Staende ohne negative Gutschrift")
    args = ap.parse_args()

    ordner = tempfile.mkdtemp(prefix="worktimes-")
    try:
        con = oeffne(args.datei, ordner)
        daten, uebersprungen, warnungen = konvertiere(con, args.zeitzone, args.kompatibel)
    finally:
        shutil.rmtree(ordner, ignore_errors=True)

    with open(args.ausgabe, "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=1)

    arten = Counter(e["typ"] for e in daten["eintraege"])
    print("Datei geschrieben: %s" % args.ausgabe)
    print("Eintraege: %d  (%s)" % (len(daten["eintraege"]),
          ", ".join("%s %d" % (k, v) for k, v in sorted(arten.items()))))
    if daten["eintraege"]:
        print("Zeitraum: %s bis %s" % (daten["eintraege"][0]["datum"], daten["eintraege"][-1]["datum"]))
    print("Sollstunden: " + ", ".join("%s %.2f" % (WOCHENTAGE[d-1], daten["einstellungen"]["soll"][str(d)])
                                      for d in range(1, 8)))
    for w in warnungen[:10]:
        print("Hinweis: " + w)
    if uebersprungen:
        print("Uebersprungen: %d" % len(uebersprungen))
        for datum, grund in uebersprungen[:10]:
            print("  %s: %s" % (datum, grund))


if __name__ == "__main__":
    main()
