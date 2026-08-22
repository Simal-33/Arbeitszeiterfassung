#!/usr/bin/env python3
"""
Zeiterfassung - lokale Arbeitszeiterfassung mit SQLite.

Start:  python3 app.py
Danach: http://127.0.0.1:8765 im Browser oeffnen.

Es werden nur Module der Python-Standardbibliothek verwendet.
"""

import argparse
import csv
import io
import json
import mimetypes
import os
import re
import sqlite3
import threading
import webbrowser
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo, available_timezones   # ab Python 3.9
except ImportError:                        # pragma: no cover
    ZoneInfo = None
    available_timezones = lambda: set()

# Windows liefert Python keine Zeitzonendatenbank mit - dort kennt zoneinfo
# ohne das Zusatzpaket 'tzdata' keine einzige Zone. Ohne Datenbank wird die
# Zeitzone nur noch entgegengenommen statt geprueft: die Sommerzeitkorrektur
# faellt dann ohnehin still auf 0 zurueck, aber Einstellungen und Import
# duerfen daran nicht scheitern.
ZONEN_BEKANNT = bool(available_timezones())
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

ENTRY_TYPES = ("arbeit", "urlaub", "krank", "feiertag", "gleitzeit", "dienst", "ausfahrt")
# Anzeigenamen. Die Kennung 'gleitzeit' bleibt, damit bestehende Daten weiter
# lesbar sind - nach aussen heisst sie ueberall "Zeitausgleich".
TYP_NAMEN = {"arbeit": "Arbeit", "urlaub": "Urlaub", "krank": "Krank",
             "feiertag": "Feiertag", "gleitzeit": "Zeitausgleich",
             "dienst": "Dienst", "ausfahrt": "Ausfahrt"}
# Typen, die den Soll-Wert des Tages automatisch gutschreiben. Zeitausgleich
# gehoert bewusst nicht dazu: so ein Tag soll ja gerade Plusstunden abbauen.
CREDIT_TYPES = ("urlaub", "krank", "feiertag")
# Typen, die gesondert verrechnet werden und nie in Ist, Saldo oder
# Ueberstunden einfliessen:
SEPARATE_TYPES = ("dienst", "ausfahrt")

STANDARD_JOB = {
    "id": "standard",
    "name": "Mein Job",
    "farbe": "#2f6fd0",
    # Sollstunden je Wochentag, 1 = Montag ... 7 = Sonntag
    "soll": {"1": 8.0, "2": 8.0, "3": 8.0, "4": 8.0, "5": 8.0, "6": 0.0, "7": 0.0},
    "standardzeiten": {
        "1": {"von": "08:00", "bis": "16:30", "pause": 30},
        "2": {"von": "08:00", "bis": "16:30", "pause": 30},
        "3": {"von": "08:00", "bis": "16:30", "pause": 30},
        "4": {"von": "08:00", "bis": "16:30", "pause": 30},
        "5": {"von": "08:00", "bis": "16:30", "pause": 30},
        "6": None,
        "7": None,
    },
    "startsaldo": 0.0,
    "startdatum": "",
    # Urlaubsanspruch in Tagen pro Jahr, 0 = nicht gefuehrt
    "urlaubstage": 0.0,
}

DEFAULT_SETTINGS = {
    # Mehrere Arbeitsverhaeltnisse mit je eigenen Sollzeiten
    "jobs": [json.loads(json.dumps(STANDARD_JOB))],
    "aktiverJob": "standard",
    # Haeufige Notizen zum Auswaehlen beim Erfassen
    "notizvorlagen": [],
    # Sollstunden je Wochentag, 1 = Montag ... 7 = Sonntag
    "soll": {"1": 8.0, "2": 8.0, "3": 8.0, "4": 8.0, "5": 8.0, "6": 0.0, "7": 0.0},
    # Feste Arbeitszeiten je Wochentag; None = kein Standard hinterlegt
    "standardzeiten": {
        "1": {"von": "08:00", "bis": "16:30", "pause": 30},
        "2": {"von": "08:00", "bis": "16:30", "pause": 30},
        "3": {"von": "08:00", "bis": "16:30", "pause": 30},
        "4": {"von": "08:00", "bis": "16:30", "pause": 30},
        "5": {"von": "08:00", "bis": "16:30", "pause": 30},
        "6": None,
        "7": None,
    },
    # Behandlung von 24.12. und 31.12.: "keine", "halb" oder "ganz"
    "sondertage": "keine",
    # Zeitzone fuer die Sommerzeitumstellung bei Nachtschichten
    "zeitzone": "Europe/Vienna",
    # Rundung der Arbeitszeit je Eintrag: 0 = aus, sonst Minutenschritt
    "rundung": 0,
    "rundungsmodus": "kaufmaennisch",   # oder "auf" bzw. "ab"
    # Frei definierbare Dienste (Notdienst, Rufbereitschaft, ...).
    #
    # Jede Dienstart beschreibt einen festen Wochenrhythmus:
    #   modus "durchgehend" laeuft ohne Unterbrechung von starttag/startzeit bis
    #     endtag/endzeit, z. B. Montag 07:00 bis Montag 07:00 der Folgewoche.
    #   modus "taeglich" gilt an jedem Tag von starttag bis endtag jeweils
    #     zwischen startzeit und endzeit, z. B. Montag bis Samstag 07:00-20:00.
    # Die Dauer ist eine zeitliche Pauschale: sie wird gesondert verrechnet und
    # zaehlt nie als Arbeitszeit. "pauschale" dient nur noch als Rueckfallwert in
    # Minuten je Tag fuer Dienstarten ohne Wochenrhythmus.
    "dienstarten": [
        {"id": "dienst-1", "name": "1. Dienst", "modus": "durchgehend",
         "starttag": 1, "startzeit": "07:00", "endtag": 1, "endzeit": "07:00",
         "pauschale": 0, "farbe": "#b45309"},
        {"id": "dienst-2", "name": "2. Dienst", "modus": "taeglich",
         "starttag": 1, "startzeit": "07:00", "endtag": 6, "endzeit": "20:00",
         "pauschale": 0, "farbe": "#0f766e"},
        {"id": "dienst-3", "name": "3. Dienst", "modus": "taeglich",
         "starttag": 5, "startzeit": "07:00", "endtag": 6, "endzeit": "20:00",
         "pauschale": 0, "farbe": "#6d28d9"},
    ],
    # Startsaldo in Stunden (Uebertrag aus dem alten System)
    "startsaldo": 0.0,
    # Ab diesem Datum wird Soll gerechnet (leer = ab erstem Eintrag)
    "startdatum": "",
    "name": "",
}

def normiere_job(roh, nummer=0):
    """Ergaenzt fehlende Felder eines Jobs und prueft die Werte."""
    vorlage = json.loads(json.dumps(STANDARD_JOB))
    job = dict(vorlage, **{k: v for k, v in roh.items() if v is not None})
    # Eine bereits vergebene Kennung bleibt unveraendert - sonst verlieren die
    # Eintraege beim naechsten Laden ihre Zuordnung.
    vorhandene = str(roh.get("id") or "")
    job["id"] = vorhandene if re.match(r"^[a-z0-9-]{1,40}$", vorhandene) \
        else slugify(roh.get("name") or "job-%d" % (nummer + 1))
    job["name"] = str(roh.get("name") or vorlage["name"])[:60]
    farbe = str(roh.get("farbe") or "")
    job["farbe"] = farbe if re.match(r"^#[0-9a-fA-F]{6}$", farbe) else vorlage["farbe"]

    soll = {}
    for d in range(1, 8):
        try:
            soll[str(d)] = max(0.0, min(24.0, float((roh.get("soll") or {}).get(
                str(d), vorlage["soll"][str(d)]))))
        except (TypeError, ValueError):
            raise ValueError("Sollstunden für %s in Job '%s' sind keine Zahl."
                             % (WOCHENTAGE[d - 1], job["name"]))
    job["soll"] = soll

    std = {}
    for d in range(1, 8):
        eintrag = (roh.get("standardzeiten") or {}).get(str(d))
        if not isinstance(eintrag, dict) or not (eintrag.get("von") and eintrag.get("bis")):
            std[str(d)] = None
            continue
        pause = int(float(eintrag.get("pause") or 0))
        if pause < 0 or duration_minutes(eintrag["von"], eintrag["bis"], pause) <= 0:
            raise ValueError("Standardzeit für %s in Job '%s' ergibt keine Arbeitszeit."
                             % (WOCHENTAGE[d - 1], job["name"]))
        std[str(d)] = {"von": eintrag["von"], "bis": eintrag["bis"], "pause": pause}
    job["standardzeiten"] = std

    try:
        job["startsaldo"] = float(roh.get("startsaldo") or 0)
    except (TypeError, ValueError):
        raise ValueError("Startsaldo in Job '%s' ist keine Zahl." % job["name"])
    startdatum = str(roh.get("startdatum") or "").strip()
    if startdatum and not DATE_RE.match(startdatum):
        raise ValueError("Startdatum in Job '%s' muss JJJJ-MM-TT sein." % job["name"])
    job["startdatum"] = startdatum
    try:
        job["urlaubstage"] = max(0.0, float(roh.get("urlaubstage") or 0))
    except (TypeError, ValueError):
        raise ValueError("Urlaubsanspruch in Job '%s' ist keine Zahl." % job["name"])
    return {k: job[k] for k in ("id", "name", "farbe", "soll", "standardzeiten",
                                "startsaldo", "startdatum", "urlaubstage")}


def job_sicht(settings, job_id):
    """Einstellungen aus Sicht eines bestimmten Jobs."""
    job = next((j for j in settings["jobs"] if j["id"] == job_id), None)
    if job is None:
        raise ValueError("Unbekannter Job '%s'." % job_id)
    sicht = dict(settings)
    for feld in ("soll", "standardzeiten", "startsaldo", "startdatum", "urlaubstage"):
        sicht[feld] = job.get(feld, 0.0)
    return sicht


SONDERTAGE_MODI = ("keine", "halb", "ganz")
DIENST_MODI = ("durchgehend", "taeglich")

# Fruehere Fassungen lieferten genau eine Dienstart "Notdienstwoche" mit
# 120 Minuten je Tag aus.
ALTE_DIENSTART = {"id": "notdienstwoche", "name": "Notdienstwoche",
                  "pauschale": 120, "farbe": "#b45309"}


def migriere_dienstarten(arten):
    """Ersetzt die alte, unveraendert gebliebene Vorgabe durch die drei Dienste.

    Nur wenn genau die frueher ausgelieferte Dienstart unangetastet dasteht - wer
    selbst etwas angelegt oder geaendert hat, behaelt seine Liste.
    """
    if len(arten) == 1 and dict(arten[0]) == ALTE_DIENSTART:
        return json.loads(json.dumps(DEFAULT_SETTINGS["dienstarten"]))
    return arten
WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


# --------------------------------------------------------------------------
# Datenbank
# --------------------------------------------------------------------------

class Store:
    def __init__(self, path):
        self.path = path
        # RLock, damit save_settings lesen und schreiben in einer Sperre erledigen kann
        self.lock = threading.RLock()
        self._init_db()

    def _connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        with self.lock, self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    datum   TEXT NOT NULL,
                    typ     TEXT NOT NULL DEFAULT 'arbeit',
                    von     TEXT,
                    bis     TEXT,
                    pause   INTEGER NOT NULL DEFAULT 0,
                    projekt TEXT NOT NULL DEFAULT '',
                    notiz   TEXT NOT NULL DEFAULT '',
                    gutschrift INTEGER,
                    dienstart TEXT NOT NULL DEFAULT '',
                    job TEXT NOT NULL DEFAULT ''
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_entries_datum ON entries(datum)")
            # Migration aelterer Datenbanken
            spalten = [r["name"] for r in con.execute("PRAGMA table_info(entries)")]
            if "gutschrift" not in spalten:
                con.execute("ALTER TABLE entries ADD COLUMN gutschrift INTEGER")
            if "dienstart" not in spalten:
                con.execute("ALTER TABLE entries ADD COLUMN dienstart TEXT NOT NULL DEFAULT ''")
            if "job" not in spalten:
                con.execute("ALTER TABLE entries ADD COLUMN job TEXT NOT NULL DEFAULT ''")
            con.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            # Laufende Stempelung (hoechstens eine)
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS laufend (
                    id       INTEGER PRIMARY KEY CHECK (id = 1),
                    datum    TEXT NOT NULL,
                    von      TEXT NOT NULL,
                    pause    INTEGER NOT NULL DEFAULT 0,
                    pause_ab TEXT,
                    projekt  TEXT NOT NULL DEFAULT '',
                    notiz    TEXT NOT NULL DEFAULT '',
                    job      TEXT NOT NULL DEFAULT ''
                )
                """
            )

    # -- Einstellungen ----------------------------------------------------
    def get_settings(self):
        with self.lock, self._connect() as con:
            rows = con.execute("SELECT key, value FROM settings").fetchall()
        data = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
        gespeichert = {}
        for r in rows:
            try:
                gespeichert[r["key"]] = json.loads(r["value"])
            except json.JSONDecodeError:
                pass
        data.update(gespeichert)
        # Sollstunden auffuellen, falls unvollstaendig
        soll = {str(k): float(v) for k, v in (data.get("soll") or {}).items()}
        for d in range(1, 8):
            soll.setdefault(str(d), 0.0)
        data["soll"] = soll
        std = dict(data.get("standardzeiten") or {})
        for d in range(1, 8):
            std.setdefault(str(d), None)
        data["standardzeiten"] = {str(d): std[str(d)] for d in range(1, 8)}
        if data.get("sondertage") not in SONDERTAGE_MODI:
            data["sondertage"] = "keine"
        if not isinstance(data.get("dienstarten"), list):
            data["dienstarten"] = []
        # Einmalig: die frueher ausgelieferte einzelne "Notdienstwoche" wird
        # durch die drei Dienste ersetzt. Der Merker verhindert, dass eine
        # spaeter bewusst wieder so angelegte Dienstart erneut ersetzt wird.
        if not gespeichert.get("dienstartenMigriert"):
            data["dienstarten"] = migriere_dienstarten(data["dienstarten"])
            with self.lock, self._connect() as con:
                con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                            ("dienstartenMigriert", json.dumps(True)))
                con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                            ("dienstarten", json.dumps(data["dienstarten"])))
        data.pop("dienstartenMigriert", None)
        if not isinstance(data.get("notizvorlagen"), list):
            data["notizvorlagen"] = []
        data["notizvorlagen"] = [str(n)[:200] for n in data["notizvorlagen"] if str(n).strip()]

        # Jobs: aus aelteren Datenbanken den bisherigen Stand uebernehmen.
        # Entscheidend ist, ob in der Datenbank Jobs stehen - die Vorbelegung
        # enthaelt immer einen und wuerde die alten Sollzeiten sonst verdecken.
        jobs = gespeichert.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            jobs = [dict(json.loads(json.dumps(STANDARD_JOB)),
                         soll=data["soll"], standardzeiten=data["standardzeiten"],
                         startsaldo=data.get("startsaldo", 0.0),
                         startdatum=data.get("startdatum", ""),
                         name=data.get("name") or STANDARD_JOB["name"])]
        vergeben, eindeutig = set(), []
        for i, j in enumerate(jobs):
            if not isinstance(j, dict):
                continue
            fertig = normiere_job(j, i)
            grund, nummer = fertig["id"], 2
            while fertig["id"] in vergeben:      # nach dem Kuerzen koennen zwei
                fertig["id"] = "%s-%d" % (grund[:37], nummer)   # Namen gleich enden
                nummer += 1
            vergeben.add(fertig["id"])
            eindeutig.append(fertig)
        data["jobs"] = eindeutig
        if not data["jobs"]:
            data["jobs"] = [json.loads(json.dumps(STANDARD_JOB))]
        kennungen = [j["id"] for j in data["jobs"]]
        if data.get("aktiverJob") not in kennungen:
            data["aktiverJob"] = kennungen[0]

        # Der aktive Job bestimmt die Werte, mit denen die App standardmaessig rechnet
        aktiv = next(j for j in data["jobs"] if j["id"] == data["aktiverJob"])
        for feld in ("soll", "standardzeiten", "startsaldo", "startdatum", "urlaubstage"):
            data[feld] = json.loads(json.dumps(aktiv.get(feld)))
        return data

    def save_settings(self, patch):
        with self.lock:  # Lesen und Schreiben in einem Zug, sonst gehen parallele
            return self._save_settings(patch)  # Aenderungen aus zwei Tabs verloren

    def _save_settings(self, patch):
        if not isinstance(patch, dict):
            raise ValueError("Einstellungen müssen als Objekt übergeben werden.")
        current = self.get_settings()

        if "jobs" in patch:
            if not isinstance(patch["jobs"], list) or not patch["jobs"]:
                raise ValueError("Es muss mindestens ein Job vorhanden sein.")
            jobs, vergeben = [], set()
            for i, roh in enumerate(patch["jobs"]):
                if not isinstance(roh, dict):
                    raise ValueError("Jeder Job muss ein Objekt sein.")
                job = normiere_job(roh, i)
                grund, nummer = job["id"][:37], 2
                while job["id"] in vergeben:
                    job["id"] = "%s-%d" % (grund, nummer)
                    nummer += 1
                vergeben.add(job["id"])
                jobs.append(job)
            current["jobs"] = jobs
            if current.get("aktiverJob") not in vergeben:
                current["aktiverJob"] = jobs[0]["id"]
        if "aktiverJob" in patch:
            kennung = str(patch["aktiverJob"] or "")
            if kennung not in [j["id"] for j in current["jobs"]]:
                raise ValueError("Unbekannter Job '%s'." % kennung)
            current["aktiverJob"] = kennung
        if "notizvorlagen" in patch:
            roh = patch["notizvorlagen"] or []
            if not isinstance(roh, list):
                raise ValueError("Notizvorlagen müssen eine Liste sein.")
            current["notizvorlagen"] = [str(n).strip()[:200] for n in roh if str(n).strip()][:50]

        # Sollzeiten und Startwerte gehoeren zum jeweiligen Job
        angefragt = patch.get("job")
        ziel_id = angefragt or current["aktiverJob"]
        if ziel_id == "alle":
            ziel_id = current["aktiverJob"]
        ziel = next((j for j in current["jobs"] if j["id"] == ziel_id), None)
        if ziel is None:
            # Ein ausdruecklich genannter, aber unbekannter Job ist ein Fehler.
            # Wurde dagegen die Jobliste im selben Zug ersetzt, gilt der aktive Job.
            if angefragt and angefragt != "alle" and any(
                    f in patch for f in ("soll", "standardzeiten", "startsaldo",
                                         "startdatum", "urlaubstage")):
                raise ValueError("Unbekannter Job '%s'." % angefragt)
            ziel = next(j for j in current["jobs"] if j["id"] == current["aktiverJob"])

        if "soll" in patch:
            if patch["soll"] is not None and not isinstance(patch["soll"], dict):
                raise ValueError("Sollstunden müssen als Objekt übergeben werden.")
            soll = {}
            for d in range(1, 8):
                raw = (patch["soll"] or {}).get(str(d), current["soll"][str(d)])
                try:
                    soll[str(d)] = max(0.0, min(24.0, float(raw)))
                except (TypeError, ValueError):
                    raise ValueError("Sollstunden für %s sind keine Zahl." % WOCHENTAGE[d - 1])
            ziel["soll"] = soll
        if "standardzeiten" in patch:
            if patch["standardzeiten"] is not None and not isinstance(patch["standardzeiten"], dict):
                raise ValueError("Standardzeiten müssen als Objekt übergeben werden.")
            std = {}
            for d in range(1, 8):
                roh = (patch["standardzeiten"] or {}).get(str(d))
                if not isinstance(roh, dict) or not (roh.get("von") and roh.get("bis")):
                    std[str(d)] = None
                    continue
                pause = int(float(roh.get("pause") or 0))
                if pause < 0:
                    raise ValueError("Die Pause kann nicht negativ sein.")
                if duration_minutes(roh["von"], roh["bis"], pause) <= 0:
                    raise ValueError(
                        "Standardzeit für %s ergibt keine Arbeitszeit." % WOCHENTAGE[d - 1])
                std[str(d)] = {"von": roh["von"], "bis": roh["bis"], "pause": pause}
            ziel["standardzeiten"] = std
        if "dienstarten" in patch:
            roh_liste = patch["dienstarten"] or []
            if not isinstance(roh_liste, list):
                raise ValueError("Dienstarten müssen als Liste übergeben werden.")
            arten, vergeben = [], set()
            for roh in roh_liste:
                if not isinstance(roh, dict):
                    raise ValueError("Jede Dienstart muss ein Objekt sein.")
                name = str(roh.get("name") or "").strip()[:40]
                if not name:
                    continue
                kennung = slugify(roh.get("id") or name)
                grund = kennung
                nummer = 2
                while kennung in vergeben:
                    kennung = "%s-%d" % (grund, nummer)
                    nummer += 1
                vergeben.add(kennung)
                try:
                    pauschale = int(round(float(roh.get("pauschale") or 0)))
                except (TypeError, ValueError):
                    raise ValueError("Pauschale von '%s' ist keine Zahl." % name)
                if not 0 <= pauschale <= 24 * 60:
                    raise ValueError(
                        "Pauschale von '%s' muss zwischen 0 und 1440 Minuten liegen." % name)
                farbe = str(roh.get("farbe") or "").strip()
                if not re.match(r"^#[0-9a-fA-F]{6}$", farbe):
                    farbe = "#b45309"
                art = {"id": kennung, "name": name, "pauschale": pauschale,
                       "farbe": farbe}

                # Wochenrhythmus ist freiwillig; ohne ihn bleibt es bei der
                # festen Pauschale je Tag.
                modus = str(roh.get("modus") or "").strip().lower()
                if modus:
                    if modus not in DIENST_MODI:
                        raise ValueError(
                            "Modus von '%s' muss 'durchgehend' oder 'taeglich' sein." % name)
                    try:
                        starttag = int(roh.get("starttag") or 0)
                        endtag = int(roh.get("endtag") or 0)
                    except (TypeError, ValueError):
                        raise ValueError("Start- und Endtag von '%s' müssen Zahlen sein." % name)
                    if not (1 <= starttag <= 7 and 1 <= endtag <= 7):
                        raise ValueError(
                            "Start- und Endtag von '%s' müssen zwischen 1 (Montag) "
                            "und 7 (Sonntag) liegen." % name)
                    for feld, wert in (("Startzeit", roh.get("startzeit")),
                                       ("Endzeit", roh.get("endzeit"))):
                        if not TIME_RE.match(str(wert or "")):
                            raise ValueError(
                                "%s von '%s' muss im Format HH:MM sein." % (feld, name))
                        parse_time(str(wert))
                    art.update(modus=modus, starttag=starttag, endtag=endtag,
                               startzeit=str(roh["startzeit"]),
                               endzeit=str(roh["endzeit"]))
                    if not dienst_tage(art, date(2024, 1, 1)):
                        raise ValueError("'%s' ergibt keine Dienstzeit." % name)
                arten.append(art)
            current["dienstarten"] = arten
        if "zeitzone" in patch:
            zone = str(patch["zeitzone"] or "").strip() or "Europe/Vienna"
            if ZoneInfo is not None and ZONEN_BEKANNT:
                try:
                    ZoneInfo(zone)
                except Exception:
                    raise ValueError("Unbekannte Zeitzone '%s'." % zone)
            current["zeitzone"] = zone
        if "rundung" in patch:
            try:
                schritt = int(float(patch["rundung"] or 0))
            except (TypeError, ValueError):
                raise ValueError("Rundung muss eine Zahl in Minuten sein.")
            if schritt not in (0, 1, 5, 6, 10, 15, 30, 60):
                raise ValueError("Rundung muss 0, 5, 10, 15, 30 oder 60 Minuten sein.")
            current["rundung"] = schritt
        if "rundungsmodus" in patch:
            modus = str(patch["rundungsmodus"] or "kaufmaennisch").strip().lower()
            if modus not in ("kaufmaennisch", "auf", "ab"):
                raise ValueError("Rundungsrichtung muss „zur nächsten Stufe“, „auf“ oder „ab“ sein.")
            current["rundungsmodus"] = modus
        if "sondertage" in patch:
            modus = (patch["sondertage"] or "keine").strip().lower()
            if modus not in SONDERTAGE_MODI:
                raise ValueError("Sondertage muss 'keine', 'halb' oder 'ganz' sein.")
            current["sondertage"] = modus
        if "startsaldo" in patch:
            try:
                ziel["startsaldo"] = float(patch["startsaldo"] or 0)
            except (TypeError, ValueError):
                raise ValueError("Startsaldo muss eine Zahl sein.")
        if "startdatum" in patch:
            sd = (patch["startdatum"] or "").strip()
            if sd and not DATE_RE.match(sd):
                raise ValueError("Startdatum muss im Format JJJJ-MM-TT sein.")
            ziel["startdatum"] = sd
        if "name" in patch:
            current["name"] = str(patch["name"] or "")[:80]
        aktiv = next(j for j in current["jobs"] if j["id"] == current["aktiverJob"])
        for feld in ("soll", "standardzeiten", "startsaldo", "startdatum", "urlaubstage"):
            current[feld] = json.loads(json.dumps(aktiv.get(feld, 0.0)))

        with self.lock, self._connect() as con:
            for k, v in current.items():
                con.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k, json.dumps(v)),
                )
        return current

    # -- Eintraege --------------------------------------------------------
    def list_entries(self, von=None, bis=None, job=None):
        sql = "SELECT * FROM entries"
        params = []
        cond = []
        if job:
            cond.append("job = ?")
            params.append(job)
        if von:
            cond.append("datum >= ?")
            params.append(von)
        if bis:
            cond.append("datum <= ?")
            params.append(bis)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY datum ASC, COALESCE(von,'') ASC, id ASC"
        with self.lock, self._connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_entry(self, entry_id):
        with self.lock, self._connect() as con:
            row = con.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None

    def insert_entry(self, e):
        with self.lock, self._connect() as con:
            cur = con.execute(
                "INSERT INTO entries(datum, typ, von, bis, pause, projekt, notiz, "
                "gutschrift, dienstart, job) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                 e["notiz"], e.get("gutschrift"), e.get("dienstart") or "", e.get("job") or ""),
            )
            return cur.lastrowid

    def update_entry(self, entry_id, e):
        with self.lock, self._connect() as con:
            cur = con.execute(
                "UPDATE entries SET datum=?, typ=?, von=?, bis=?, pause=?, projekt=?, notiz=?, "
                "gutschrift=?, dienstart=?, job=? WHERE id=?",
                (e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                 e["notiz"], e.get("gutschrift"), e.get("dienstart") or "", e.get("job") or "",
                 entry_id),
            )
            return cur.rowcount > 0

    def delete_entry(self, entry_id):
        with self.lock, self._connect() as con:
            cur = con.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            return cur.rowcount > 0

    def replace_all(self, entries):
        with self.lock, self._connect() as con:
            con.execute("DELETE FROM entries")
            con.executemany(
                "INSERT INTO entries(datum, typ, von, bis, pause, projekt, notiz, "
                "gutschrift, dienstart, job) VALUES(?,?,?,?,?,?,?,?,?,?)",
                [(e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                  e["notiz"], e.get("gutschrift"), e.get("dienstart") or "", e.get("job") or "")
                 for e in entries],
            )

    def add_many(self, entries):
        with self.lock, self._connect() as con:
            con.executemany(
                "INSERT INTO entries(datum, typ, von, bis, pause, projekt, notiz, "
                "gutschrift, dienstart, job) VALUES(?,?,?,?,?,?,?,?,?,?)",
                [(e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                  e["notiz"], e.get("gutschrift"), e.get("dienstart") or "", e.get("job") or "")
                 for e in entries],
            )

    def first_entry_date(self, job=None):
        """Erster erfasster Tag, unabhaengig von der Art des Eintrags."""
        with self.lock, self._connect() as con:
            wo = " WHERE job = ?" if job else ""
            p = (job,) if job else ()
            row = con.execute("SELECT MIN(datum) AS d FROM entries" + wo, p).fetchone()
        return row["d"] if row and row["d"] else None


# --------------------------------------------------------------------------
# Validierung und Berechnung
# --------------------------------------------------------------------------

def slugify(text):
    """Macht aus 'Notdienstwoche Süd' die Kennung 'notdienstwoche-sued'."""
    text = str(text).strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text or "dienst")[:40]


def parse_time(value):
    """'8:30' -> Minuten seit Mitternacht."""
    if not TIME_RE.match(value):
        raise ValueError("Uhrzeit muss im Format HH:MM sein (z. B. 08:30).")
    h, m = value.split(":")
    h, m = int(h), int(m)
    if h > 23 or m > 59:
        raise ValueError("Ungültige Uhrzeit: %s" % value)
    return h * 60 + m


def fmt_time(minutes):
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def clean_entry(raw, dienstarten=None):
    """Prueft und normalisiert einen Eintrag aus dem Frontend.

    dienstarten: dict kennung -> Dienstart, noetig fuer Eintraege vom Typ 'dienst'.
    """
    datum = (raw.get("datum") or "").strip()
    if not DATE_RE.match(datum):
        raise ValueError("Bitte ein gültiges Datum angeben (JJJJ-MM-TT).")
    try:
        date.fromisoformat(datum)
    except ValueError:
        raise ValueError("Das Datum %s gibt es nicht." % datum)

    typ = (raw.get("typ") or "arbeit").strip().lower()
    if typ not in ENTRY_TYPES:
        raise ValueError("Unbekannte Art: %s" % typ)

    von = (raw.get("von") or "").strip()
    bis = (raw.get("bis") or "").strip()
    pause = raw.get("pause") or 0
    try:
        pause = int(float(pause))
    except (TypeError, ValueError):
        raise ValueError("Pause muss eine Zahl in Minuten sein.")
    if pause < 0:
        raise ValueError("Die Pause kann nicht negativ sein.")

    gutschrift = raw.get("gutschrift")
    if gutschrift in ("", None):
        gutschrift = None
    else:
        try:
            gutschrift = int(round(float(gutschrift)))
        except (TypeError, ValueError):
            raise ValueError("Gutschrift muss eine Zahl in Minuten sein.")
        if abs(gutschrift) > 24 * 60:
            raise ValueError("Die Gutschrift kann höchstens 24 Stunden betragen.")

    dienstart = str(raw.get("dienstart") or "").strip()
    if typ == "dienst":
        if dienstarten is None:
            dienstart = slugify(dienstart) if dienstart else ""
        else:
            if not dienstart:
                raise ValueError("Bitte eine Dienstart wählen.")
            if dienstart not in dienstarten:
                raise ValueError(
                    "Unbekannte Dienstart '%s'. Erst in den Einstellungen anlegen." % dienstart)
            if gutschrift is None:
                gutschrift = tagesanteil(dienstarten[dienstart], datum)
        if gutschrift is None:
            gutschrift = 0
    else:
        dienstart = ""

    if typ in ("arbeit", "ausfahrt"):
        if not von or not bis:
            was = "einer Ausfahrt" if typ == "ausfahrt" else "Arbeitszeit"
            raise ValueError("Bei %s sind 'Von' und 'Bis' nötig." % was)
        dauer = duration_minutes(von, bis, pause)
        if dauer < 0:
            raise ValueError("Die Pause ist länger als die erfasste Zeitspanne.")
        gutschrift = None  # Die Dauer ergibt sich aus Von/Bis
    else:
        if von and bis:
            if duration_minutes(von, bis, pause) < 0:
                raise ValueError("Die Pause ist länger als die erfasste Zeitspanne.")
        else:
            von, bis, pause = "", "", 0

    return {
        "job": str(raw.get("job") or "").strip()[:40],
        "datum": datum,
        "typ": typ,
        "von": von,
        "bis": bis,
        "pause": pause,
        "projekt": (raw.get("projekt") or "").strip()[:80],
        "notiz": (raw.get("notiz") or "").strip()[:500],
        "gutschrift": gutschrift,
        "dienstart": dienstart,
    }


def duration_minutes(von, bis, pause, datum=None, zone=None):
    """Netto-Minuten. Ein 'Bis' vor dem 'Von' gilt als Nachtschicht ueber Mitternacht.

    Mit Datum und Zeitzone wird die tatsaechlich verstrichene Zeit gerechnet. An den
    beiden Umstellungstagen im Jahr ist eine Schicht ueber 02:00/03:00 sonst um eine
    Stunde falsch.
    """
    start = parse_time(von)
    end = parse_time(bis)
    if end == start:
        raise ValueError("'Von' und 'Bis' dürfen nicht gleich sein.")
    spanne = end - start if end > start else end - start + 24 * 60
    spanne += sommerzeit_versatz(datum, von, bis, zone)
    return spanne - int(pause or 0)


def sommerzeit_versatz(datum, von, bis, zone):
    """Differenz zwischen echter und abgelesener Zeitspanne, in Minuten."""
    if not (datum and zone) or ZoneInfo is None:
        return 0
    try:
        tz = ZoneInfo(zone)
        tag = date.fromisoformat(datum)
        beginn = datetime.combine(tag, datetime.strptime(von, "%H:%M").time(), tz)
        ende_tag = tag if parse_time(bis) > parse_time(von) else tag + timedelta(days=1)
        ende = datetime.combine(ende_tag, datetime.strptime(bis, "%H:%M").time(), tz)
        echt = (ende.astimezone(timezone.utc) - beginn.astimezone(timezone.utc)).total_seconds() / 60
        abgelesen = (datetime.combine(ende_tag, ende.time())
                     - datetime.combine(tag, beginn.time())).total_seconds() / 60
        return int(round(echt - abgelesen))
    except Exception:
        return 0


def runde_minuten(minuten, schritt, modus="kaufmaennisch"):
    """Rundet eine Dauer auf volle Minutenschritte."""
    schritt = int(schritt or 0)
    if schritt <= 1:
        return minuten
    rest = minuten % schritt
    if rest == 0:
        return minuten
    if modus == "auf":
        return minuten + (schritt - rest)
    if modus == "ab":
        return minuten - rest
    return minuten - rest if rest * 2 < schritt else minuten + (schritt - rest)


def dienst_start(art, datum):
    """Legt den Beginn eines Dienstes auf den Starttag der Dienstart.

    Genommen wird der letzte passende Wochentag, der nicht nach 'datum' liegt -
    wer also mitten in der Woche einen Dienst anlegt, bekommt den Dienst, in dem
    er gerade steckt, und nicht den der Folgewoche.
    """
    d = date.fromisoformat(datum) if isinstance(datum, str) else datum
    starttag = int(art.get("starttag") or 0)
    if not 1 <= starttag <= 7:
        return d
    return d - timedelta(days=(d.isoweekday() - starttag) % 7)


def dienst_tage(art, datum):
    """Liefert [(datum, minuten), ...] fuer einen Dienst, der bei 'datum' liegt.

    Die Minuten sind der Anteil der Zeitpauschale, der auf den jeweiligen
    Kalendertag faellt. Ohne hinterlegten Wochenrhythmus bleibt es beim alten
    Verhalten: ein einzelner Tag mit der festen Pauschale.
    """
    d0 = dienst_start(art, datum)
    modus = str(art.get("modus") or "").strip().lower()
    starttag = int(art.get("starttag") or 0)
    endtag = int(art.get("endtag") or 0)
    if modus not in DIENST_MODI or not (1 <= starttag <= 7 and 1 <= endtag <= 7):
        return [(d0.isoformat(), int(art.get("pauschale") or 0))]

    beginn = parse_time(art.get("startzeit") or "00:00")
    ende = parse_time(art.get("endzeit") or "00:00")

    if modus == "taeglich":
        # An jedem Tag dasselbe Zeitfenster, z. B. Montag bis Samstag 07:00-20:00.
        laenge = ende - beginn
        if laenge <= 0:
            laenge += 24 * 60
        anzahl = (endtag - starttag) % 7 + 1
        return [((d0 + timedelta(days=i)).isoformat(), laenge) for i in range(anzahl)]

    # durchgehend, z. B. Montag 07:00 bis Montag 07:00: der erste und der letzte
    # Kalendertag sind angebrochen, die dazwischen zaehlen voll.
    spanne = (endtag - starttag) % 7
    if spanne == 0 and ende <= beginn:
        spanne = 7                      # gleicher Wochentag heisst eine volle Woche
    rest = spanne * 24 * 60 + (ende - beginn)
    if rest <= 0:
        return []
    tage, tag, platz = [], 0, 24 * 60 - beginn
    while rest > 0:
        anteil = min(platz, rest)
        tage.append(((d0 + timedelta(days=tag)).isoformat(), anteil))
        rest -= anteil
        tag += 1
        platz = 24 * 60
    return tage


def tagesanteil(art, datum):
    """Minuten, die ein einzelner Diensttag beitraegt.

    Bei einer Dienstart mit Wochenrhythmus ist das der Anteil, der auf genau
    dieses Datum faellt - beim 1. Dienst also 17:00 h am ersten Montag und
    24:00 h an den Tagen dazwischen. Liegt das Datum ausserhalb des Rhythmus,
    zaehlt der laengste Tag der Dienstart. Frueher stand hier das Feld
    'pauschale', das bei Diensten mit Rhythmus 0 ist - ein von Hand angelegter
    Diensttag wurde damit stillschweigend mit 0:00 gebucht.
    """
    if not art.get("modus"):
        return int(art.get("pauschale") or 0)
    plan = dict(dienst_tage(art, datum))
    if plan.get(datum):
        return plan[datum]
    return max(plan.values()) if plan else int(art.get("pauschale") or 0)


def dienst_pauschale(art):
    """Gesamte Zeitpauschale einer Dienstart in Minuten."""
    # Das Ergebnis haengt nur an der Definition, das Bezugsdatum ist beliebig.
    return sum(m for _, m in dienst_tage(art, date(2024, 1, 1)))


def mit_dauer(settings):
    """Einstellungen fuer die Anzeige: jede Dienstart bekommt ihre Gesamtdauer.

    So muss die Oberflaeche die Pauschale nicht selbst ausrechnen und kann in
    beiden Betriebsarten dieselbe Zahl zeigen.
    """
    kopie = dict(settings)
    kopie["dienstarten"] = [
        dict(a, dauer=dienst_pauschale(a), tage=len(dienst_tage(a, date(2024, 1, 1))))
        for a in (settings.get("dienstarten") or [])
    ]
    return kopie


def abgebaute_zeit(eintrag, soll_map):
    """Wie viel Zeit ein Zeitausgleichstag abbaut - nur fuer die Anzeige.

    Ohne eigene Angabe ist das die Sollzeit des Wochentags. Steht am Eintrag eine
    ausdrueckliche Gutschrift (z. B. abgebuchte Stunden aus dem Import), zaehlt
    deren Betrag.
    """
    if eintrag.get("gutschrift") is not None:
        return abs(int(eintrag["gutschrift"]))
    wd = date.fromisoformat(eintrag["datum"]).isoweekday()
    return int(round(soll_map.get(wd, 0.0) * 60))


def saldo_beginn(daten):
    """Beginn der Saldorechnung: der Monatserste des ersten erfassten Tages.

    Frueher zaehlte der erste Tag mit *Arbeitszeit*. Urlaub oder Krankenstand
    davor fielen damit aus dem Saldo und aus den Zaehlern der Uebersicht - ein
    Urlaubstag am Monatsanfang war schlicht nicht da. Der Monatserste nimmt den
    ganzen Anfangsmonat mit.
    """
    if not daten:
        return "9999-12-31"
    return min(daten)[:8] + "01"


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def compute(entries, settings, von, bis):
    """Berechnet Ist, Soll und Saldo fuer den Zeitraum [von, bis]."""
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    zone = settings.get("zeitzone") or None
    schritt = int(settings.get("rundung") or 0)
    modus = settings.get("rundungsmodus") or "kaufmaennisch"

    def arbeitsminuten(e):
        """Netto-Arbeitszeit eines Eintrags inklusive Sommerzeit und Rundung."""
        roh = duration_minutes(e["von"], e["bis"], e["pause"], e["datum"], zone)
        return runde_minuten(roh, schritt, modus)

    d_von = date.fromisoformat(von)
    d_bis = date.fromisoformat(bis)

    # Ein Tag zaehlt nur dann zum Soll, wenn er ab dem Startdatum liegt.
    startdatum = settings.get("startdatum") or ""
    d_start = date.fromisoformat(startdatum) if startdatum else None

    tage = {}
    for e in entries:
        tag = tage.setdefault(e["datum"], {
            "datum": e["datum"], "ist": 0, "gutschrift": 0,
            "pauschale": 0, "ausfahrt": 0,
            "typen": [], "eintraege": [],
        })
        minuten = 0
        if e["typ"] == "arbeit":
            minuten = arbeitsminuten(e)
            tag["ist"] += minuten
        elif e["typ"] == "dienst":
            # Die Zeitpauschale des Dienstes wird gesondert verrechnet und
            # bleibt aus Ist, Saldo und Ueberstunden heraus.
            minuten = int(e.get("gutschrift") or 0)
            tag["pauschale"] += minuten
        elif e["typ"] == "ausfahrt":
            # Ausfahrten waehrend eines Dienstes ebenso.
            minuten = arbeitsminuten(e)
            tag["ausfahrt"] += minuten
        elif e["typ"] == "gleitzeit":
            # Zeitausgleich baut Plusstunden ab: kein Ausgleich des Tagessolls,
            # der Tag geht also mit seinem Soll ins Minus. Nur eine ausdrueckliche
            # Gutschrift zaehlt - damit bleiben abgebuchte Stunden aus dem Import
            # (negative Gutschrift) weiterhin richtig.
            gut = int(e["gutschrift"]) if e.get("gutschrift") is not None else 0
            tag["gutschrift"] += gut
            # Angezeigt wird, wie viel Zeit der Tag abbaut - sonst stuende in der
            # Liste eine 0:00, obwohl der Saldo um das Tagessoll faellt.
            minuten = abgebaute_zeit(e, soll_map)
        elif e.get("gutschrift") is not None:
            # Explizite Gutschrift, z. B. halber Tag am 24.12.
            minuten = int(e["gutschrift"])
            tag["gutschrift"] += minuten
        elif e["von"] and e["bis"]:
            # Nicht-Arbeitstyp mit expliziter Zeitspanne (z. B. halber Urlaubstag)
            minuten = duration_minutes(e["von"], e["bis"], e["pause"], e["datum"], zone)
            tag["gutschrift"] += minuten
        else:
            wd = date.fromisoformat(e["datum"]).isoweekday()
            minuten = int(round(soll_map.get(wd, 0.0) * 60))
            tag["gutschrift"] += minuten
        if e["typ"] not in tag["typen"]:
            tag["typen"].append(e["typ"])
        tag["eintraege"].append(dict(e, minuten=minuten))

    # Kuenftige Tage zaehlen nur mit, wenn dort schon etwas erfasst ist (z. B. ein
    # geplanter Urlaub oder vorab eingetragene Feiertage). Sonst stuende der laufende
    # Monat kuenstlich im Minus.
    heute = date.today()

    soll_gesamt = 0
    for d in daterange(d_von, d_bis):
        if d_start and d < d_start:
            continue
        if d > heute:
            # Ein kuenftiger Tag zaehlt nur, wenn dort etwas steht, das den Tag
            # auch abdeckt. Eine vorab eingetragene Dienstwoche allein tut das
            # nicht - sie bringt nur ihre Pauschale.
            eintrag = tage.get(d.isoformat())
            if not eintrag or all(t in SEPARATE_TYPES for t in eintrag["typen"]):
                continue
        soll_gesamt += int(round(soll_map.get(d.isoweekday(), 0.0) * 60))

    # Tage vor dem Startdatum bleiben sichtbar, zaehlen aber nicht in den Saldo.
    def zaehlt(iso):
        return not d_start or date.fromisoformat(iso) >= d_start

    ist_gesamt = sum(t["ist"] for d, t in tage.items() if zaehlt(d))
    gutschrift_gesamt = sum(t["gutschrift"] for d, t in tage.items() if zaehlt(d))
    pauschale_gesamt = sum(t["pauschale"] for d, t in tage.items() if zaehlt(d))
    ausfahrt_gesamt = sum(t["ausfahrt"] for d, t in tage.items() if zaehlt(d))

    projekte = {}
    for e in entries:
        if e["typ"] != "arbeit" or not zaehlt(e["datum"]):
            continue
        p = e["projekt"] or "(ohne Projekt)"
        projekte[p] = projekte.get(p, 0) + arbeitsminuten(e)

    tagesliste = []
    for d in sorted(tage.keys()):
        t = tage[d]
        wd = date.fromisoformat(d).isoweekday()
        t_soll = int(round(soll_map.get(wd, 0.0) * 60))
        t_saldo = t["ist"] + t["gutschrift"] - t_soll
        if not zaehlt(d):
            t_soll, t_saldo = 0, 0
        tagesliste.append({
            "datum": d,
            "wochentag": wd,
            "ist": t["ist"],
            "gutschrift": t["gutschrift"],
            "pauschale": t["pauschale"],
            "ausfahrt": t["ausfahrt"],
            "soll": t_soll,
            "saldo": t_saldo,
            "typen": t["typen"],
            "eintraege": t["eintraege"],
        })

    # Kennzahlen je Art: Anzahl Tage und Minuten (fuer die Uebersicht)
    arten = {}
    for t in tage.values():
        for e in t["eintraege"]:
            if not zaehlt(e["datum"]):
                continue
            a = arten.setdefault(e["typ"], {"tage": set(), "minuten": 0})
            a["tage"].add(e["datum"])
            a["minuten"] += e["minuten"]
    arten = {k: {"tage": len(v["tage"]), "minuten": v["minuten"]} for k, v in arten.items()}

    namen = {a["id"]: a["name"] for a in (settings.get("dienstarten") or [])}
    # Welcher Dienst laeuft an welchem Tag? Damit bekommt jede Ausfahrt ihren
    # Dienst zugeordnet, ohne dass er am Eintrag mitgefuehrt werden muss.
    dienst_am_tag = {e["datum"]: (e.get("dienstart") or "")
                     for e in entries if e["typ"] == "dienst"}

    dienste = {}
    for e in entries:
        if e["typ"] != "dienst" or not zaehlt(e["datum"]):
            continue
        d = dienste.setdefault(e.get("dienstart") or "",
                               {"tage": 0, "minuten": 0, "ausfahrten": 0,
                                "ausfahrt_minuten": 0})
        d["tage"] += 1
        d["minuten"] += int(e.get("gutschrift") or 0)

    ausfahrten = []
    for e in entries:
        if e["typ"] != "ausfahrt" or not zaehlt(e["datum"]):
            continue
        kennung = dienst_am_tag.get(e["datum"], "")
        minuten = arbeitsminuten(e)
        ausfahrten.append({
            "id": e.get("id"),
            "datum": e["datum"],
            "wochentag": date.fromisoformat(e["datum"]).isoweekday(),
            "von": e["von"],
            "bis": e["bis"],
            "pause": e["pause"],
            "minuten": minuten,
            "notiz": e["notiz"],
            "projekt": e["projekt"],
            "dienstart": kennung,
            "dienst": namen.get(kennung, "") if kennung else "",
        })
        if kennung in dienste:
            dienste[kennung]["ausfahrten"] += 1
            dienste[kennung]["ausfahrt_minuten"] += minuten
    ausfahrten.sort(key=lambda a: (a["datum"], a["von"]))

    return {
        "von": von,
        "bis": bis,
        "arten": arten,
        "ist": ist_gesamt,
        "dienste": [{"id": k, "name": namen.get(k, k or "Dienst"), **v}
                    for k, v in sorted(dienste.items(), key=lambda kv: -kv[1]["minuten"])],
        "ausfahrten": ausfahrten,
        # Beides wird gesondert verrechnet und ist in 'erfasst' und 'saldo'
        # bewusst nicht enthalten.
        "pauschale": pauschale_gesamt,
        "ausfahrt": ausfahrt_gesamt,
        "gutschrift": gutschrift_gesamt,
        "erfasst": ist_gesamt + gutschrift_gesamt,
        "soll": soll_gesamt,
        "saldo": ist_gesamt + gutschrift_gesamt - soll_gesamt,
        "tage": tagesliste,
        "projekte": [{"projekt": k, "minuten": v} for k, v in
                     sorted(projekte.items(), key=lambda kv: -kv[1])],
    }


# --------------------------------------------------------------------------
# Feiertage Oesterreich
# --------------------------------------------------------------------------

def ostersonntag(jahr):
    """Gregorianischer Osteralgorithmus (Meeus/Jones/Butcher)."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def feiertage_at(jahr, sondertage="keine"):
    """Die 13 gesetzlichen Feiertage in Oesterreich (Arbeitsruhegesetz).

    Der Karfreitag ist seit 2019 kein allgemeiner Feiertag mehr, Landespatrone
    sind keine gesetzlichen Ruhetage - beide sind daher nicht enthalten.
    Der 24.12. und der 31.12. sind ebenfalls keine gesetzlichen Feiertage und
    werden nur beruecksichtigt, wenn 'sondertage' auf halb oder ganz steht.
    """
    ostern = ostersonntag(jahr)
    tage = [
        (date(jahr, 1, 1), "Neujahr"),
        (date(jahr, 1, 6), "Heilige Drei Koenige"),
        (ostern + timedelta(days=1), "Ostermontag"),
        (date(jahr, 5, 1), "Staatsfeiertag"),
        (ostern + timedelta(days=39), "Christi Himmelfahrt"),
        (ostern + timedelta(days=50), "Pfingstmontag"),
        (ostern + timedelta(days=60), "Fronleichnam"),
        (date(jahr, 8, 15), "Mariae Himmelfahrt"),
        (date(jahr, 10, 26), "Nationalfeiertag"),
        (date(jahr, 11, 1), "Allerheiligen"),
        (date(jahr, 12, 8), "Mariae Empfaengnis"),
        (date(jahr, 12, 25), "Christtag"),
        (date(jahr, 12, 26), "Stefanitag"),
    ]
    liste = [{"datum": d.isoformat(), "name": n, "anteil": 1.0, "gesetzlich": True}
             for d, n in tage]
    if sondertage in ("halb", "ganz"):
        anteil = 0.5 if sondertage == "halb" else 1.0
        liste.append({"datum": date(jahr, 12, 24).isoformat(), "name": "Heiliger Abend",
                      "anteil": anteil, "gesetzlich": False})
        liste.append({"datum": date(jahr, 12, 31).isoformat(), "name": "Silvester",
                      "anteil": anteil, "gesetzlich": False})
    return sorted(liste, key=lambda x: x["datum"])


def feiertags_uebersicht(store, jahr, job=None):
    settings = store.get_settings()
    if job in (None, "", "alle"):
        job = settings["aktiverJob"]
    if job:
        settings = job_sicht(settings, job)
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    standard_job = store.get_settings()["jobs"][0]["id"]
    vorhanden = {e["datum"] for e in store.list_entries("%d-01-01" % jahr, "%d-12-31" % jahr)
                 if job_von(e, standard_job) == job}
    liste = []
    for f in feiertage_at(jahr, settings.get("sondertage", "keine")):
        d = date.fromisoformat(f["datum"])
        soll = int(round(soll_map.get(d.isoweekday(), 0.0) * 60))
        liste.append(dict(
            f,
            wochentag=d.isoweekday(),
            soll=soll,
            gutschrift=int(round(soll * f["anteil"])),
            arbeitstag=soll > 0,
            erfasst=f["datum"] in vorhanden,
        ))
    return {"jahr": jahr, "sondertage": settings.get("sondertage", "keine"), "feiertage": liste}


def feiertage_eintragen(store, jahr, job=None):
    """Legt fuer alle Feiertage, die auf einen Arbeitstag fallen, Eintraege an."""
    settings = store.get_settings()
    if not job or job == "alle":
        job = settings["aktiverJob"]
    uebersicht = feiertags_uebersicht(store, jahr, job)
    neu, uebersprungen = [], []
    schon_geplant = set()
    for f in uebersicht["feiertage"]:
        if f["datum"] in schon_geplant:
            # Selten, aber moeglich: Christi Himmelfahrt faellt auf den Staatsfeiertag
            uebersprungen.append({"datum": f["datum"], "name": f["name"],
                                  "grund": "faellt auf denselben Tag"})
            continue
        if not f["arbeitstag"]:
            uebersprungen.append({"datum": f["datum"], "name": f["name"], "grund": "kein Arbeitstag"})
            continue
        if f["erfasst"]:
            uebersprungen.append({"datum": f["datum"], "name": f["name"],
                                  "grund": "bereits erfasst"})
            continue
        neu.append({
            "datum": f["datum"], "typ": "feiertag", "von": "", "bis": "", "pause": 0,
            "projekt": "", "notiz": f["name"], "dienstart": "", "job": job,
            "gutschrift": f["gutschrift"] if f["anteil"] < 1.0 else None,
        })
        schon_geplant.add(f["datum"])
    if neu:
        store.add_many(neu)
    return {"jahr": jahr, "angelegt": len(neu), "uebersprungen": len(uebersprungen),
            "tage": neu, "details": uebersprungen}


def dienst_eintragen(store, dienstart, von, bis=None, gutschrift=None, job=None):
    """Legt die Diensttage an.

    Hat die Dienstart einen Wochenrhythmus hinterlegt, ergeben sich Anfang, Ende
    und die Minuten je Tag aus ihrer Definition; 'bis' wird dann nicht gebraucht.
    Andernfalls bekommt jeder Tag im Zeitraum die feste Pauschale.
    """
    settings = store.get_settings()
    if not job or job == "alle":
        job = settings["aktiverJob"]
    arten = {a["id"]: a for a in (settings.get("dienstarten") or [])}
    if dienstart not in arten:
        raise ValueError("Unbekannte Dienstart '%s'." % dienstart)
    art = arten[dienstart]

    if art.get("modus"):
        plan = dienst_tage(art, von)
        if not plan:
            raise ValueError("'%s' ergibt keine Dienstzeit." % art["name"])
    else:
        d_von = date.fromisoformat(von)
        d_bis = date.fromisoformat(bis or von)
        if d_bis < d_von:
            raise ValueError("Das Ende des Zeitraums liegt vor dem Anfang.")
        if (d_bis - d_von).days > 366:
            raise ValueError("Ein Dienstzeitraum darf höchstens ein Jahr umfassen.")
        fest = int(art.get("pauschale") or 0) if gutschrift is None else int(gutschrift)
        plan = [(d.isoformat(), fest) for d in daterange(d_von, d_bis)]

    if gutschrift is not None and art.get("modus"):
        plan = [(d, int(gutschrift)) for d, _ in plan]

    erster, letzter = plan[0][0], plan[-1][0]
    standard_job = settings["jobs"][0]["id"]
    schon = {e["datum"] for e in store.list_entries(erster, letzter)
             if e["typ"] == "dienst" and e.get("dienstart") == dienstart
             and job_von(e, standard_job) == job}
    neu = [clean_entry({
        "datum": d, "typ": "dienst", "dienstart": dienstart, "job": job,
        "gutschrift": minuten, "notiz": art["name"],
    }, arten) for d, minuten in plan if d not in schon]
    if neu:
        store.add_many(neu)
    return {"dienstart": dienstart, "name": art["name"], "angelegt": len(neu),
            "von": erster, "bis": letzter,
            "uebersprungen": len(plan) - len(neu),
            "minuten": sum(e["gutschrift"] or 0 for e in neu),
            "pauschale": sum(m for _, m in plan)}


def arbeitstage_auffuellen(store, von, bis, job=None):
    """Fuellt vergangene Arbeitstage ohne Eintrag mit den Standardzeiten."""
    if job == "alle":
        job = None
    settings = effective_settings(store, job) if job else store.get_settings()
    job = job or settings["aktiverJob"]
    # Der eigene Startdatums-Ersatz aus effective_settings darf das Auffuellen
    # nicht blockieren - er dient nur der Saldorechnung.
    settings = dict(settings, startdatum=job_sicht(settings, job)["startdatum"])
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    std = settings.get("standardzeiten") or {}
    d_von = date.fromisoformat(von)
    d_bis = min(date.fromisoformat(bis), date.today())
    startdatum = settings.get("startdatum") or ""
    d_start = date.fromisoformat(startdatum) if startdatum else None

    # Diensttage und Ausfahrten bleiben offen: waehrend eines Dienstes wird ja
    # trotzdem normal gearbeitet.
    standard_job = store.get_settings()["jobs"][0]["id"]
    belegt = {e["datum"] for e in store.list_entries(von, bis)
              if e["typ"] not in SEPARATE_TYPES and job_von(e, standard_job) == job}
    feiertage = set()
    for jahr in range(d_von.year, d_bis.year + 1):
        for f in feiertage_at(jahr, settings.get("sondertage", "keine")):
            feiertage.add(f["datum"])

    neu = []
    uebersprungen = {"belegt": 0, "feiertag": 0, "kein_arbeitstag": 0,
                     "ohne_standardzeit": 0, "vor_startdatum": 0}
    d = d_von
    while d <= d_bis:
        iso = d.isoformat()
        vorlage = std.get(str(d.isoweekday()))
        if d_start and d < d_start:
            uebersprungen["vor_startdatum"] = uebersprungen.get("vor_startdatum", 0) + 1
        elif iso in belegt:
            uebersprungen["belegt"] += 1
        elif iso in feiertage:
            uebersprungen["feiertag"] += 1
        elif soll_map.get(d.isoweekday(), 0.0) <= 0:
            uebersprungen["kein_arbeitstag"] += 1
        elif not vorlage:
            uebersprungen["ohne_standardzeit"] += 1
        else:
            neu.append({
                "datum": iso, "typ": "arbeit", "von": vorlage["von"], "bis": vorlage["bis"],
                "pause": int(vorlage.get("pause") or 0), "projekt": "",
                "notiz": "automatisch aus Standardzeiten", "gutschrift": None,
                "dienstart": "", "job": job,
            })
        d += timedelta(days=1)

    if neu:
        store.add_many(neu)
    return {"angelegt": len(neu), "von": von, "bis": d_bis.isoformat(),
            "uebersprungen": uebersprungen}


def job_von(eintrag, standard_job):
    """Eintraege aus aelteren Datenbanken ohne Jobangabe gehoeren zum ersten Job."""
    return eintrag.get("job") or standard_job


def stempel_lesen(store):
    with store.lock, store._connect() as con:
        row = con.execute("SELECT * FROM laufend WHERE id = 1").fetchone()
    if not row:
        return {"laufend": None}
    lauf = dict(row)
    jetzt = datetime.now()
    beginn = datetime.strptime(lauf["datum"] + " " + lauf["von"], "%Y-%m-%d %H:%M")
    pause = int(lauf["pause"] or 0)
    if lauf["pause_ab"]:
        # Aeltere Eintraege enthalten nur die Uhrzeit; dann gilt der Starttag.
        seit = lauf["pause_ab"] if " " in lauf["pause_ab"] \
            else lauf["datum"] + " " + lauf["pause_ab"]
        pause += max(0, int((jetzt - datetime.strptime(seit, "%Y-%m-%d %H:%M"))
                            .total_seconds() // 60))
    brutto = max(0, int((jetzt - beginn).total_seconds() // 60))
    lauf["pause_gesamt"] = pause
    lauf["brutto"] = brutto
    lauf["netto"] = max(0, brutto - pause)
    lauf["pausiert"] = bool(lauf["pause_ab"])
    lauf["beginn"] = beginn.strftime("%Y-%m-%d %H:%M")
    return {"laufend": lauf}


def stempel_start(store, job="", projekt="", notiz=""):
    if stempel_lesen(store)["laufend"]:
        raise ValueError("Es läuft bereits eine Zeitmessung.")
    jetzt = datetime.now()
    with store.lock, store._connect() as con:
        con.execute("INSERT OR REPLACE INTO laufend(id, datum, von, pause, pause_ab, "
                    "projekt, notiz, job) VALUES(1,?,?,0,NULL,?,?,?)",
                    (jetzt.strftime("%Y-%m-%d"), jetzt.strftime("%H:%M"),
                     str(projekt or "")[:80], str(notiz or "")[:500], str(job or "")[:40]))
    return stempel_lesen(store)


def stempel_pause(store):
    """Schaltet die Pause an oder aus."""
    zustand = stempel_lesen(store)["laufend"]
    if not zustand:
        raise ValueError("Es läuft keine Zeitmessung.")
    jetzt = datetime.now().strftime("%Y-%m-%d %H:%M")   # mit Datum, sonst geht
    with store.lock, store._connect() as con:            # eine Pause nach Mitternacht schief
        if zustand["pause_ab"]:
            con.execute("UPDATE laufend SET pause = ?, pause_ab = NULL WHERE id = 1",
                        (zustand["pause_gesamt"],))
        else:
            con.execute("UPDATE laufend SET pause_ab = ? WHERE id = 1", (jetzt,))
    return stempel_lesen(store)


def stempel_stop(store, verwerfen=False):
    zustand = stempel_lesen(store)["laufend"]
    if not zustand:
        raise ValueError("Es läuft keine Zeitmessung.")

    if verwerfen:
        with store.lock, store._connect() as con:
            con.execute("DELETE FROM laufend WHERE id = 1")
        return {"verworfen": True}

    if zustand["brutto"] < 1:
        raise ValueError("Die Zeitmessung läuft erst seit weniger als einer Minute. "
                         "Zum Abbrechen 'Verwerfen' benutzen.")
    if zustand["brutto"] >= 24 * 60:
        raise ValueError(
            "Die Zeitmessung läuft seit mehr als 24 Stunden (Beginn %s). So ein Eintrag "
            "lässt sich nicht automatisch buchen - bitte den Tag von Hand erfassen und die "
            "Messung verwerfen." % zustand["beginn"])
    if zustand["netto"] <= 0:
        raise ValueError("Die Pause ist so lang wie die gesamte Zeitmessung.")

    # Erst den Eintrag bauen, dann die Messung loeschen - sonst waere sie bei
    # einem Fehler verloren.
    eintrag = clean_entry({
        "datum": zustand["datum"], "typ": "arbeit", "von": zustand["von"],
        "bis": datetime.now().strftime("%H:%M"), "pause": zustand["pause_gesamt"],
        "projekt": zustand["projekt"], "notiz": zustand["notiz"], "job": zustand["job"],
    })
    neu = store.insert_entry(eintrag)
    with store.lock, store._connect() as con:
        con.execute("DELETE FROM laufend WHERE id = 1")
    return {"eintrag": store.get_entry(neu)}


def eigene_alle(store, kennung, standard_job):
    return [e for e in store.list_entries() if job_von(e, standard_job) == kennung]


def auswertung(store, von, bis, job=None):
    """Auswertung fuer einen Job oder - ohne Angabe - fuer alle zusammen."""
    settings = store.get_settings()
    standard_job = settings["jobs"][0]["id"]
    alle_kennungen = [j["id"] for j in settings["jobs"]]
    if job in (None, "", "alle"):
        kennungen = alle_kennungen
    else:
        if job not in alle_kennungen:
            raise ValueError("Unbekannter Job '%s'." % job)
        kennungen = [job]

    im_zeitraum = store.list_entries(von, bis)
    teile = []
    for kennung in kennungen:
        sicht = job_sicht(settings, kennung)
        if not sicht.get("startdatum"):
            sicht["startdatum"] = saldo_beginn(
                [e["datum"] for e in eigene_alle(store, kennung, standard_job)])
        eigene = [e for e in im_zeitraum if job_von(e, standard_job) == kennung]
        ergebnis = compute(eigene, sicht, von, bis)
        # Der Urlaubsanspruch gilt fuers Jahr - dafuer braucht es alle Urlaubstage
        # des Jahres, nicht nur die des angezeigten Zeitraums.
        jahr = bis[:4]
        im_jahr = [e for e in store.list_entries("%s-01-01" % jahr, "%s-12-31" % jahr)
                   if job_von(e, standard_job) == kennung]
        ergebnis["urlaub"] = urlaubskonto(
            im_jahr, sicht, {int(k): float(v) for k, v in sicht["soll"].items()}, von, bis)
        # Fuer die Zusammenfassung: welche Kalendertage zaehlen je Art?
        ergebnis["_daten"] = {}
        for e in eigene:
            if sicht["startdatum"] and e["datum"] < sicht["startdatum"]:
                continue
            ergebnis["_daten"].setdefault(e["typ"], set()).add(e["datum"])
        teile.append(ergebnis)

    if len(teile) == 1:
        res = teile[0]
        res.pop("_daten", None)
    else:
        res = {"von": von, "bis": bis, "tage": [], "projekte": [], "dienste": [],
               "ausfahrten": [], "arten": {},
               "urlaub": {"jahr": int(bis[:4]),
                          "anspruch": sum(t["urlaub"]["anspruch"] for t in teile),
                          "verbraucht": sum(t["urlaub"]["verbraucht"] for t in teile),
                          "rest": sum(t["urlaub"]["rest"] for t in teile),
                          "gefuehrt": any(t["urlaub"]["gefuehrt"] for t in teile)}}
        for feld in ("ist", "gutschrift", "erfasst", "soll", "saldo",
                     "pauschale", "ausfahrt"):
            res[feld] = sum(t[feld] for t in teile)
        for teil in teile:
            res["tage"].extend(teil["tage"])
            res["ausfahrten"].extend(teil["ausfahrten"])
            for schluessel, wert in teil["arten"].items():
                z = res["arten"].setdefault(schluessel, {"tage": 0, "minuten": 0})
                z["minuten"] += wert["minuten"]
            for name, feld in (("projekte", "projekt"), ("dienste", "id")):
                for eintrag in teil[name]:
                    treffer = next((x for x in res[name] if x[feld] == eintrag[feld]), None)
                    if treffer:
                        for zahl in ("minuten", "tage", "ausfahrten", "ausfahrt_minuten"):
                            if zahl in eintrag:
                                treffer[zahl] += eintrag[zahl]
                    else:
                        res[name].append(dict(eintrag))
        # Ein Kalendertag zaehlt nur einmal, auch wenn zwei Jobs darauf gebucht sind
        gesammelt = {}
        for teil in teile:
            for typ, daten in teil.get("_daten", {}).items():
                gesammelt.setdefault(typ, set()).update(daten)
        for typ, daten in gesammelt.items():
            res["arten"].setdefault(typ, {"tage": 0, "minuten": 0})["tage"] = len(daten)
        res["tage"].sort(key=lambda t: t["datum"])
        res["projekte"].sort(key=lambda p: -p["minuten"])
        res["dienste"].sort(key=lambda d: -d["minuten"])
        res["ausfahrten"].sort(key=lambda a: (a["datum"], a["von"]))

    res["job"] = job or "alle"
    res["gesamtsaldo"] = sum(gesamtsaldo(store, k) for k in kennungen)
    return res


def urlaubskonto(entries, settings, soll_map, von, bis):
    """Urlaubsanspruch und Verbrauch des Jahres, in dem der Zeitraum endet."""
    anspruch = float(settings.get("urlaubstage") or 0)
    jahr = bis[:4]
    verbraucht = 0.0
    for e in entries:
        if e["typ"] != "urlaub" or not e["datum"].startswith(jahr):
            continue
        tagessoll = soll_map.get(date.fromisoformat(e["datum"]).isoweekday(), 0.0) * 60
        if e.get("gutschrift") is not None and tagessoll > 0:
            verbraucht += min(1.0, max(0.0, int(e["gutschrift"]) / tagessoll))
        elif e["von"] and e["bis"] and tagessoll > 0:
            verbraucht += min(1.0, duration_minutes(e["von"], e["bis"], e["pause"]) / tagessoll)
        elif tagessoll > 0:
            verbraucht += 1.0
        # An Tagen ohne Sollzeit (Wochenende, freier Tag) wird kein Urlaub verbraucht
    verbraucht = round(verbraucht * 2) / 2          # auf halbe Tage
    return {"jahr": int(jahr), "anspruch": anspruch, "verbraucht": verbraucht,
            "rest": round((anspruch - verbraucht) * 2) / 2, "gefuehrt": anspruch > 0}


def effective_settings(store, job=None):
    """Einstellungen mit gesetztem Startdatum: ohne eigene Angabe zaehlt das Soll
    ab dem ersten erfassten Tag (und ohne Eintraege gar nicht)."""
    settings = store.get_settings()
    if job:
        settings = job_sicht(settings, job)
    if not settings.get("startdatum") and job:
        alle = store.get_settings()["jobs"]
        settings["startdatum"] = saldo_beginn(
            [e["datum"] for e in eigene_alle(store, job, alle[0]["id"])])
    elif not settings.get("startdatum"):
        erster = store.first_entry_date()
        settings["startdatum"] = saldo_beginn([erster] if erster else [])
    return settings


def gesamtsaldo(store, job=None):
    """Saldo ueber den kompletten Erfassungszeitraum inkl. Startsaldo."""
    settings = effective_settings(store, job)
    alle = store.get_settings()["jobs"]
    standard_job = alle[0]["id"]
    entries = store.list_entries()
    if job:
        entries = [e for e in entries if job_von(e, standard_job) == job]
    if not entries:
        return int(round(float(settings.get("startsaldo") or 0) * 60))
    von = min(settings["startdatum"], entries[0]["datum"])
    # Bis heute rechnen, auch wenn seit Tagen nichts erfasst wurde - sonst wuerden
    # nicht erfasste Werktage aus dem Soll fallen. Kuenftige Tage ohne Eintrag
    # laesst compute() ohnehin aus.
    bis = max(max(e["datum"] for e in entries), date.today().isoformat())
    res = compute(entries, settings, von, bis)
    return res["saldo"] + int(round(float(settings.get("startsaldo") or 0) * 60))


# --------------------------------------------------------------------------
# Export / Import
# --------------------------------------------------------------------------

def export_json(store):
    return {
        "app": "Zeiterfassung",
        "version": 1,
        "exportiert_am": datetime.now().isoformat(timespec="seconds"),
        "einstellungen": store.get_settings(),
        "eintraege": [
            {k: e[k] for k in ("datum", "typ", "von", "bis", "pause", "projekt",
                               "notiz", "gutschrift", "dienstart", "job")}
            for e in store.list_entries()
        ],
    }


def export_csv(store, von=None, bis=None, job=None):
    settings = store.get_settings()
    standard_job = settings["jobs"][0]["id"]
    namen_jobs = {j["id"]: j["name"] for j in settings["jobs"]}
    entries = store.list_entries(von, bis)
    if job and job != "alle":
        if job not in namen_jobs:
            raise ValueError("Unbekannter Job '%s'." % job)
        entries = [e for e in entries if job_von(e, standard_job) == job]
        settings = job_sicht(settings, job)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Datum", "Wochentag", "Job", "Art", "Dienst", "Von", "Bis", "Pause (Min)",
                "Dauer (h)", "Soll (h)", "Verrechnung", "Projekt", "Notiz"])
    wtage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    soll_je_job = {j["id"]: {int(k): float(v) for k, v in j["soll"].items()}
                   for j in store.get_settings()["jobs"]}
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    zone = settings.get("zeitzone") or None
    schritt = int(settings.get("rundung") or 0)
    modus = settings.get("rundungsmodus") or "kaufmaennisch"
    dienstnamen = {a["id"]: a["name"] for a in (settings.get("dienstarten") or [])}
    # Ausfahrten fuehren ihren Dienst nicht mit - er ergibt sich aus dem Tag.
    dienst_am_tag = {e["datum"]: dienstnamen.get(e.get("dienstart") or "", "")
                     for e in entries if e["typ"] == "dienst"}
    gesehen = set()
    for e in entries:
        d = date.fromisoformat(e["datum"])
        # Reihenfolge wie in compute(), sonst weicht der Export von der Auswertung ab
        if e["typ"] == "arbeit":
            minuten = runde_minuten(
                duration_minutes(e["von"], e["bis"], e["pause"], e["datum"], zone), schritt, modus)
        elif e["typ"] == "dienst":
            minuten = int(e.get("gutschrift") or 0)
        elif e["typ"] == "ausfahrt":
            minuten = runde_minuten(
                duration_minutes(e["von"], e["bis"], e["pause"], e["datum"], zone), schritt, modus)
        elif e["typ"] == "gleitzeit":
            minuten = abgebaute_zeit(e, soll_map)
        elif e.get("gutschrift") is not None:
            minuten = int(e["gutschrift"])
        elif e["von"] and e["bis"]:
            minuten = duration_minutes(e["von"], e["bis"], e["pause"], e["datum"], zone)
        else:
            minuten = int(round(soll_map.get(d.isoweekday(), 0.0) * 60))
        soll = soll_je_job.get(job_von(e, standard_job), soll_map).get(d.isoweekday(), 0.0)
        w.writerow([
            e["datum"], wtage[d.isoweekday() - 1],
            namen_jobs.get(job_von(e, standard_job), ""),
            TYP_NAMEN.get(e["typ"], e["typ"].capitalize()),
            dienstnamen.get(e.get("dienstart") or "", "")
            or (dienst_am_tag.get(e["datum"], "") if e["typ"] == "ausfahrt" else ""),
            e["von"], e["bis"], e["pause"],
            ("%.2f" % (minuten / 60)).replace(".", ","),
            ("%.2f" % soll).replace(".", ",") if e["datum"] not in gesehen else "",
            "gesondert" if e["typ"] in SEPARATE_TYPES
            else ("Abbau" if e["typ"] == "gleitzeit" else "Arbeitszeit"),
            e["projekt"], e["notiz"],
        ])
        gesehen.add(e["datum"])
    return "﻿" + buf.getvalue()


def import_data(store, payload, modus="ersetzen"):
    if modus not in ("ersetzen", "anhaengen"):
        raise ValueError("Modus muss 'ersetzen' oder 'anhaengen' sein.")
    if not isinstance(payload, dict):
        raise ValueError("Die Datei enthaelt keine gültigen Daten.")
    roh = payload.get("eintraege")
    if not isinstance(roh, list):
        raise ValueError("Die Datei enthaelt kein Feld 'eintraege'.")

    # Dienstarten aus der Datei gelten fuer die Pruefung der Eintraege
    quelle = payload.get("einstellungen") if isinstance(payload.get("einstellungen"), dict) else {}
    liste = quelle.get("dienstarten")
    if not isinstance(liste, list):
        liste = store.get_settings().get("dienstarten") or []
    arten = {a.get("id"): a for a in liste if isinstance(a, dict) and a.get("id")}
    # Wer eine Dienstart umbenennt oder loescht, hat weiterhin Eintraege, die auf
    # die alte Kennung zeigen. Beim Zurueckholen einer Sicherung darf das nicht
    # scheitern - die Kennung bleibt erhalten, die Zeit steht ohnehin am Eintrag.
    for e in roh:
        if isinstance(e, dict) and e.get("typ") == "dienst":
            kennung = str(e.get("dienstart") or "").strip()
            if kennung and kennung not in arten:
                arten[kennung] = {"id": kennung, "name": kennung, "pauschale": 0}

    # Erst alles pruefen, dann schreiben. Sonst waeren die alten Eintraege bereits
    # geloescht, wenn eine kaputte Datei erst bei den Einstellungen auffaellt.
    sauber = []
    for nummer, e in enumerate(roh, 1):
        if not isinstance(e, dict):
            raise ValueError("Eintrag %d ist kein Objekt." % nummer)
        try:
            sauber.append(clean_entry(e, arten))
        except ValueError as exc:
            raise ValueError("Eintrag %d (%s): %s" % (nummer, e.get("datum", "ohne Datum"), exc))
    einstellungen = payload.get("einstellungen")
    if einstellungen is not None and not isinstance(einstellungen, dict):
        raise ValueError("Das Feld 'einstellungen' ist beschaedigt.")

    with store.lock:
        if einstellungen:
            store.save_settings(einstellungen)  # validiert, bevor Eintraege fallen
        if modus == "anhaengen":
            store.add_many(sauber)
        else:
            store.replace_all(sauber)
    return len(sauber)


# --------------------------------------------------------------------------
# Automatische Sicherungen
# --------------------------------------------------------------------------

SICHERUNG_MAX = 10                     # so viele Staende werden aufbewahrt
SICHERUNG_RE = re.compile(r"^sicherung-\d{8}-\d{9}-[a-z]+\.json$")


def sicherungs_ordner(store):
    """Ordner neben der Datenbank, in dem die Sicherungen liegen."""
    basis = os.path.splitext(os.path.abspath(store.path))[0]
    return basis + "-sicherungen"


def sicherungen_liste(store):
    ordner = sicherungs_ordner(store)
    if not os.path.isdir(ordner):
        return []
    ergebnis = []
    for name in sorted(os.listdir(ordner), reverse=True):
        if not SICHERUNG_RE.match(name):
            continue
        pfad = os.path.join(ordner, name)
        try:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
            anzahl = len(daten.get("eintraege") or [])
        except (OSError, ValueError):
            continue
        ergebnis.append({
            "datei": name,
            "zeit": "%s-%s-%s %s:%s" % (name[10:14], name[14:16], name[16:18],
                                        name[19:21], name[21:23]),
            "grund": name[29:-5],
            "eintraege": anzahl,
            "groesse": os.path.getsize(pfad),
        })
    return ergebnis


def sicherung_anlegen(store, grund="manuell", nur_wenn_aelter_als=None):
    """Legt eine Sicherung an. nur_wenn_aelter_als = Stunden seit der letzten."""
    grund = grund if grund in ("manuell", "automatisch", "vorimport") else "manuell"
    with store.lock:
        vorhanden = sicherungen_liste(store)
        if nur_wenn_aelter_als and vorhanden:
            try:
                letzte = datetime.strptime(vorhanden[0]["zeit"], "%Y-%m-%d %H:%M")
                if datetime.now() - letzte < timedelta(hours=nur_wenn_aelter_als):
                    return {"angelegt": False, "sicherungen": vorhanden}
            except ValueError:
                pass
        ordner = sicherungs_ordner(store)
        os.makedirs(ordner, exist_ok=True)
        # Millisekunden im Namen: so kollidieren auch zwei Sicherungen
        # in derselben Sekunde nicht miteinander
        name = "sicherung-%s-%s.json" % (
            datetime.now().strftime("%Y%m%d-%H%M%S%f")[:-3], grund)
        pfad = os.path.join(ordner, name)
        # erst vollstaendig danebenschreiben, dann umbenennen - so entsteht
        # nie eine halbe Sicherung, wenn der Rechner mittendrin ausgeht
        temp = pfad + ".teil"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(export_json(store), f, ensure_ascii=False, indent=2)
        os.replace(temp, pfad)
        for alt in sicherungen_liste(store)[SICHERUNG_MAX:]:
            try:
                os.remove(os.path.join(ordner, alt["datei"]))
            except OSError:
                pass
        return {"angelegt": True, "sicherungen": sicherungen_liste(store)}


def sicherung_wiederherstellen(store, datei):
    datei = str(datei or "")
    if not SICHERUNG_RE.match(datei):
        raise ValueError("Diese Sicherung gibt es nicht.")
    pfad = os.path.join(sicherungs_ordner(store), datei)
    if not os.path.isfile(pfad):
        raise ValueError("Diese Sicherung gibt es nicht.")
    with open(pfad, encoding="utf-8") as f:
        daten = json.load(f)
    # Der aktuelle Stand wird vorher gesichert, damit auch das ruecknehmbar ist
    sicherung_anlegen(store, "vorimport")
    return import_data(store, daten, "ersetzen")


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "Zeiterfassung/1.0"
    store = None

    def log_message(self, fmt, *args):
        pass  # ruhige Konsole

    # -- Schutz gegen fremde Webseiten -------------------------------------
    def _erlaubte_hosts(self):
        port = self.server.server_address[1]
        namen = ["127.0.0.1", "localhost", "[::1]", "::1"]
        if getattr(self.server, "extra_host", None):
            namen.append(self.server.extra_host)
        erlaubt = set()
        for n in namen:
            erlaubt.add(n)
            erlaubt.add("%s:%d" % (n, port))
        return erlaubt

    def _pruefe_herkunft(self, schreibend):
        """Verhindert, dass eine beliebige offene Webseite die Zeiterfassung
        fernsteuert (CSRF) oder sie per DNS-Rebinding ausliest."""
        host = (self.headers.get("Host") or "").strip()
        if host and host not in self._erlaubte_hosts():
            self._error("Ungueltiger Host-Header.", 421)
            return False

        origin = self.headers.get("Origin")
        if origin:
            rest = origin.split("//", 1)[-1]
            if rest not in self._erlaubte_hosts():
                self._error("Anfragen von fremden Webseiten sind nicht erlaubt.", 403)
                return False

        if schreibend:
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                self._error("Schreibende Anfragen brauchen Content-Type: application/json.", 415)
                return False
        return True

    # -- Hilfen -----------------------------------------------------------
    def _send(self, code, body=b"", content_type="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False))

    def _error(self, msg, code=400):
        self._json({"fehler": str(msg)}, code)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Der Request-Body ist kein gültiges JSON.")

    def _query(self):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        return {k: v[0] for k, v in q.items()}

    def _path(self):
        from urllib.parse import urlparse
        return urlparse(self.path).path

    # -- Routen -----------------------------------------------------------
    def do_GET(self):
        path = self._path()
        try:
            if not self._pruefe_herkunft(schreibend=False):
                return
            if path.startswith("/api/"):
                return self._api_get(path)
            return self._static(path)
        except ValueError as exc:
            self._error(exc)
        except Exception as exc:  # pragma: no cover
            self._error("Serverfehler: %s" % exc, 500)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self._write("POST")

    def do_PUT(self):
        self._write("PUT")

    def do_DELETE(self):
        self._write("DELETE")

    def _write(self, method):
        path = self._path()
        try:
            if not self._pruefe_herkunft(schreibend=True):
                return
            if not path.startswith("/api/"):
                return self._error("Unbekannter Endpunkt.", 404)
            self._api_write(method, path)
        except ValueError as exc:
            self._error(exc)
        except Exception as exc:  # pragma: no cover
            self._error("Serverfehler: %s" % exc, 500)

    def _api_get(self, path):
        q = self._query()
        if path == "/api/eintraege":
            return self._json(self.store.list_entries(q.get("von"), q.get("bis"), q.get("job")))
        if path == "/api/stempel":
            return self._json(stempel_lesen(self.store))
        if path == "/api/einstellungen":
            return self._json(mit_dauer(self.store.get_settings()))
        if path == "/api/auswertung":
            von = q.get("von") or date.today().replace(day=1).isoformat()
            bis = q.get("bis") or date.today().isoformat()
            if not (DATE_RE.match(von) and DATE_RE.match(bis)):
                raise ValueError("Zeitraum bitte als JJJJ-MM-TT angeben.")
            if bis < von:
                raise ValueError("Das Ende des Zeitraums liegt vor dem Anfang.")
            return self._json(auswertung(self.store, von, bis, q.get("job")))
        if path == "/api/feiertage":
            jahr = q.get("jahr") or str(date.today().year)
            if not re.match(r"^\d{4}$", str(jahr)) or not (1900 <= int(jahr) <= 2200):
                raise ValueError("Jahr bitte vierstellig zwischen 1900 und 2200 angeben.")
            return self._json(feiertags_uebersicht(self.store, int(jahr), q.get("job")))
        if path == "/api/sicherungen":
            return self._json({"sicherungen": sicherungen_liste(self.store),
                               "ordner": sicherungs_ordner(self.store)})
        if path == "/api/export.json":
            name = "zeiterfassung-%s.json" % date.today().isoformat()
            return self._send(
                200, json.dumps(export_json(self.store), ensure_ascii=False, indent=2),
                "application/json; charset=utf-8",
                {"Content-Disposition": 'attachment; filename="%s"' % name},
            )
        if path == "/api/export.csv":
            name = "zeiterfassung-%s.csv" % date.today().isoformat()
            return self._send(
                200, export_csv(self.store, q.get("von"), q.get("bis"), q.get("job")),
                "text/csv; charset=utf-8",
                {"Content-Disposition": 'attachment; filename="%s"' % name},
            )
        return self._error("Unbekannter Endpunkt.", 404)

    def _api_write(self, method, path):
        m = re.match(r"^/api/eintraege/(\d+)$", path)
        arten = {a["id"]: a for a in (self.store.get_settings().get("dienstarten") or [])}
        if method == "POST" and path == "/api/eintraege":
            e = clean_entry(self._body(), arten)
            new_id = self.store.insert_entry(e)
            return self._json(self.store.get_entry(new_id), 201)
        if method == "POST" and path == "/api/stempel/start":
            body = self._body()
            return self._json(stempel_start(self.store, body.get("job"),
                                            body.get("projekt"), body.get("notiz")), 201)
        if method == "POST" and path == "/api/stempel/pause":
            return self._json(stempel_pause(self.store))
        if method == "POST" and path == "/api/stempel/stop":
            return self._json(stempel_stop(self.store, bool(self._body().get("verwerfen"))))
        if method == "POST" and path == "/api/dienste":
            body = self._body()
            von = (body.get("von") or "").strip()
            # Dienstarten mit Wochenrhythmus brauchen kein Ende - es ergibt sich
            # aus ihrer Definition.
            bis = (body.get("bis") or "").strip()
            if not DATE_RE.match(von):
                raise ValueError("Datum bitte als JJJJ-MM-TT angeben.")
            if bis and not DATE_RE.match(bis):
                raise ValueError("Zeitraum bitte als JJJJ-MM-TT angeben.")
            if bis and bis < von:
                raise ValueError("Das Ende des Zeitraums liegt vor dem Anfang.")
            return self._json(dienst_eintragen(
                self.store, (body.get("dienstart") or "").strip(), von, bis or None,
                body.get("gutschrift"), body.get("job")))
        if method == "PUT" and m:
            e = clean_entry(self._body(), arten)
            if not self.store.update_entry(int(m.group(1)), e):
                return self._error("Eintrag nicht gefunden.", 404)
            return self._json(self.store.get_entry(int(m.group(1))))
        if method == "DELETE" and m:
            if not self.store.delete_entry(int(m.group(1))):
                return self._error("Eintrag nicht gefunden.", 404)
            return self._json({"ok": True})
        if method == "PUT" and path == "/api/einstellungen":
            return self._json(mit_dauer(self.store.save_settings(self._body())))
        if method == "POST" and path == "/api/feiertage":
            body = self._body()
            jahr = body.get("jahr") or date.today().year
            try:
                jahr = int(jahr)
            except (TypeError, ValueError):
                raise ValueError("Jahr bitte als Zahl angeben.")
            if not 1900 <= jahr <= 2200:
                raise ValueError("Jahr bitte zwischen 1900 und 2200 angeben.")
            return self._json(feiertage_eintragen(self.store, jahr, body.get("job")))
        if method == "POST" and path == "/api/auffuellen":
            body = self._body()
            von = (body.get("von") or "").strip()
            bis = (body.get("bis") or "").strip()
            if not (DATE_RE.match(von) and DATE_RE.match(bis)):
                raise ValueError("Zeitraum bitte als JJJJ-MM-TT angeben.")
            if bis < von:
                raise ValueError("Das Ende des Zeitraums liegt vor dem Anfang.")
            return self._json(arbeitstage_auffuellen(self.store, von, bis, body.get("job")))
        if method == "POST" and path == "/api/sicherungen":
            body = self._body()
            stunden = body.get("nur_wenn_aelter_als")
            return self._json(sicherung_anlegen(
                self.store, body.get("grund") or "manuell",
                float(stunden) if stunden else None))
        if method == "POST" and path == "/api/sicherungen/wiederherstellen":
            body = self._body()
            anzahl = sicherung_wiederherstellen(self.store, body.get("datei"))
            return self._json({"ok": True, "eintraege": anzahl})
        if method == "POST" and path == "/api/import":
            body = self._body()
            modus = body.get("modus") or "ersetzen"
            # Vor dem Ersetzen den bisherigen Stand wegsichern
            if modus == "ersetzen":
                try:
                    sicherung_anlegen(self.store, "vorimport")
                except OSError:
                    pass                      # Sicherung darf den Import nicht blockieren
            anzahl = import_data(self.store, body.get("daten") or body, modus)
            return self._json({"ok": True, "importiert": anzahl})
        return self._error("Unbekannter Endpunkt.", 404)

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        rel = os.path.normpath(path.lstrip("/"))
        wurzel = os.path.realpath(STATIC_DIR)
        full = os.path.realpath(os.path.join(STATIC_DIR, rel))
        # commonpath statt startswith: sonst waere auch ein Nachbarordner wie
        # "static_backup" erreichbar. realpath loest zusaetzlich Symlinks auf.
        if os.path.commonpath([full, wurzel]) != wurzel or not os.path.isfile(full):
            return self._send(404, "Nicht gefunden", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".webmanifest"):
            ctype = "application/manifest+json"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)


def main():
    ap = argparse.ArgumentParser(description="Lokale Arbeitszeiterfassung")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=os.path.join(BASE_DIR, "zeiterfassung.db"))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--im-netz-freigeben", action="store_true",
                    help="Bestaetigt einen Start ausserhalb von 127.0.0.1")
    args = ap.parse_args()

    lokal = args.host in ("127.0.0.1", "localhost", "::1")
    if not lokal and not args.im_netz_freigeben:
        raise SystemExit(
            "Achtung: --host %s macht die Zeiterfassung ohne Passwort für alle im Netz\n"
            "erreichbar - jeder koennte deine Zeiten lesen, aendern und loeschen.\n"
            "Wenn das wirklich gewollt ist, zusaetzlich --im-netz-freigeben angeben."
            % args.host)

    Handler.store = Store(args.db)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.extra_host = None if lokal else args.host
    url = "http://%s:%d" % (args.host, args.port)
    print("Zeiterfassung läuft auf %s" % url)
    print("Datenbank: %s" % args.db)
    print("Beenden mit Strg+C")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
