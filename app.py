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
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

ENTRY_TYPES = ("arbeit", "urlaub", "krank", "feiertag", "gleitzeit", "dienst")
# Typen, die den Soll-Wert des Tages automatisch gutschreiben:
CREDIT_TYPES = ("urlaub", "krank", "feiertag", "gleitzeit")

DEFAULT_SETTINGS = {
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
    # Frei definierbare Dienste (Rufbereitschaft, Notdienstwoche, ...).
    # pauschale = Gutschrift in Minuten je Diensttag; Einsaetze werden zusaetzlich
    # als normale Arbeitszeit erfasst.
    "dienstarten": [
        {"id": "notdienstwoche", "name": "Notdienstwoche", "pauschale": 120,
         "farbe": "#b45309"},
    ],
    # Startsaldo in Stunden (Uebertrag aus dem alten System)
    "startsaldo": 0.0,
    # Ab diesem Datum wird Soll gerechnet (leer = ab erstem Eintrag)
    "startdatum": "",
    "name": "",
}

SONDERTAGE_MODI = ("keine", "halb", "ganz")
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
                    dienstart TEXT NOT NULL DEFAULT ''
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
            con.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    # -- Einstellungen ----------------------------------------------------
    def get_settings(self):
        with self.lock, self._connect() as con:
            rows = con.execute("SELECT key, value FROM settings").fetchall()
        data = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
        for r in rows:
            try:
                data[r["key"]] = json.loads(r["value"])
            except json.JSONDecodeError:
                pass
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
        return data

    def save_settings(self, patch):
        with self.lock:  # Lesen und Schreiben in einem Zug, sonst gehen parallele
            return self._save_settings(patch)  # Aenderungen aus zwei Tabs verloren

    def _save_settings(self, patch):
        if not isinstance(patch, dict):
            raise ValueError("Einstellungen muessen als Objekt uebergeben werden.")
        current = self.get_settings()
        if "soll" in patch:
            if patch["soll"] is not None and not isinstance(patch["soll"], dict):
                raise ValueError("Sollstunden muessen als Objekt uebergeben werden.")
            soll = {}
            for d in range(1, 8):
                raw = (patch["soll"] or {}).get(str(d), current["soll"][str(d)])
                try:
                    soll[str(d)] = max(0.0, min(24.0, float(raw)))
                except (TypeError, ValueError):
                    raise ValueError("Sollstunden fuer %s sind keine Zahl." % WOCHENTAGE[d - 1])
            current["soll"] = soll
        if "standardzeiten" in patch:
            if patch["standardzeiten"] is not None and not isinstance(patch["standardzeiten"], dict):
                raise ValueError("Standardzeiten muessen als Objekt uebergeben werden.")
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
                        "Standardzeit fuer %s ergibt keine Arbeitszeit." % WOCHENTAGE[d - 1])
                std[str(d)] = {"von": roh["von"], "bis": roh["bis"], "pause": pause}
            current["standardzeiten"] = std
        if "dienstarten" in patch:
            roh_liste = patch["dienstarten"] or []
            if not isinstance(roh_liste, list):
                raise ValueError("Dienstarten muessen als Liste uebergeben werden.")
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
                arten.append({"id": kennung, "name": name, "pauschale": pauschale,
                              "farbe": farbe})
            current["dienstarten"] = arten
        if "sondertage" in patch:
            modus = (patch["sondertage"] or "keine").strip().lower()
            if modus not in SONDERTAGE_MODI:
                raise ValueError("Sondertage muss 'keine', 'halb' oder 'ganz' sein.")
            current["sondertage"] = modus
        if "startsaldo" in patch:
            try:
                current["startsaldo"] = float(patch["startsaldo"] or 0)
            except (TypeError, ValueError):
                raise ValueError("Startsaldo muss eine Zahl sein.")
        if "startdatum" in patch:
            sd = (patch["startdatum"] or "").strip()
            if sd and not DATE_RE.match(sd):
                raise ValueError("Startdatum muss im Format JJJJ-MM-TT sein.")
            current["startdatum"] = sd
        if "name" in patch:
            current["name"] = str(patch["name"] or "")[:80]
        with self.lock, self._connect() as con:
            for k, v in current.items():
                con.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k, json.dumps(v)),
                )
        return current

    # -- Eintraege --------------------------------------------------------
    def list_entries(self, von=None, bis=None):
        sql = "SELECT * FROM entries"
        params = []
        cond = []
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
                "gutschrift, dienstart) VALUES(?,?,?,?,?,?,?,?,?)",
                (e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                 e["notiz"], e.get("gutschrift"), e.get("dienstart") or ""),
            )
            return cur.lastrowid

    def update_entry(self, entry_id, e):
        with self.lock, self._connect() as con:
            cur = con.execute(
                "UPDATE entries SET datum=?, typ=?, von=?, bis=?, pause=?, projekt=?, notiz=?, "
                "gutschrift=?, dienstart=? WHERE id=?",
                (e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                 e["notiz"], e.get("gutschrift"), e.get("dienstart") or "", entry_id),
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
                "gutschrift, dienstart) VALUES(?,?,?,?,?,?,?,?,?)",
                [(e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                  e["notiz"], e.get("gutschrift"), e.get("dienstart") or "") for e in entries],
            )

    def add_many(self, entries):
        with self.lock, self._connect() as con:
            con.executemany(
                "INSERT INTO entries(datum, typ, von, bis, pause, projekt, notiz, "
                "gutschrift, dienstart) VALUES(?,?,?,?,?,?,?,?,?)",
                [(e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                  e["notiz"], e.get("gutschrift"), e.get("dienstart") or "") for e in entries],
            )

    def first_entry_date(self):
        """Erster Tag mit Arbeitszeit. Vorab eingetragene Feiertage oder Urlaube
        verschieben den Beginn der Saldorechnung damit nicht nach hinten."""
        with self.lock, self._connect() as con:
            row = con.execute(
                "SELECT MIN(datum) AS d FROM entries WHERE typ = 'arbeit'").fetchone()
            if not (row and row["d"]):
                row = con.execute("SELECT MIN(datum) AS d FROM entries").fetchone()
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
        raise ValueError("Ungueltige Uhrzeit: %s" % value)
    return h * 60 + m


def fmt_time(minutes):
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def clean_entry(raw, dienstarten=None):
    """Prueft und normalisiert einen Eintrag aus dem Frontend.

    dienstarten: dict kennung -> Dienstart, noetig fuer Eintraege vom Typ 'dienst'.
    """
    datum = (raw.get("datum") or "").strip()
    if not DATE_RE.match(datum):
        raise ValueError("Bitte ein gueltiges Datum angeben (JJJJ-MM-TT).")
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
        if gutschrift < 0:
            raise ValueError("Die Gutschrift kann nicht negativ sein.")
        if gutschrift > 24 * 60:
            raise ValueError("Die Gutschrift kann hoechstens 24 Stunden betragen.")

    dienstart = str(raw.get("dienstart") or "").strip()
    if typ == "dienst":
        if dienstarten is None:
            dienstart = slugify(dienstart) if dienstart else ""
        else:
            if not dienstart:
                raise ValueError("Bitte eine Dienstart waehlen.")
            if dienstart not in dienstarten:
                raise ValueError(
                    "Unbekannte Dienstart '%s'. Erst in den Einstellungen anlegen." % dienstart)
            if gutschrift is None:
                gutschrift = int(dienstarten[dienstart].get("pauschale") or 0)
        if gutschrift is None:
            gutschrift = 0
    else:
        dienstart = ""

    if typ == "arbeit":
        if not von or not bis:
            raise ValueError("Bei Arbeitszeit sind 'Von' und 'Bis' noetig.")
        dauer = duration_minutes(von, bis, pause)
        if dauer < 0:
            raise ValueError("Die Pause ist laenger als die erfasste Zeitspanne.")
        gutschrift = None  # Arbeitszeit ergibt sich aus Von/Bis
    else:
        if von and bis:
            if duration_minutes(von, bis, pause) < 0:
                raise ValueError("Die Pause ist laenger als die erfasste Zeitspanne.")
        else:
            von, bis, pause = "", "", 0

    return {
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


def duration_minutes(von, bis, pause):
    """Netto-Minuten. Ein 'Bis' vor dem 'Von' gilt als Nachtschicht ueber Mitternacht."""
    start = parse_time(von)
    end = parse_time(bis)
    if end == start:
        raise ValueError("'Von' und 'Bis' duerfen nicht gleich sein.")
    if end < start:
        end += 24 * 60
    return end - start - int(pause or 0)


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def compute(entries, settings, von, bis):
    """Berechnet Ist, Soll und Saldo fuer den Zeitraum [von, bis]."""
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    d_von = date.fromisoformat(von)
    d_bis = date.fromisoformat(bis)

    # Ein Tag zaehlt nur dann zum Soll, wenn er ab dem Startdatum liegt.
    startdatum = settings.get("startdatum") or ""
    d_start = date.fromisoformat(startdatum) if startdatum else None

    tage = {}
    for e in entries:
        tag = tage.setdefault(e["datum"], {
            "datum": e["datum"], "ist": 0, "gutschrift": 0,
            "typen": [], "eintraege": [],
        })
        minuten = 0
        if e["typ"] == "arbeit":
            minuten = duration_minutes(e["von"], e["bis"], e["pause"])
            tag["ist"] += minuten
        elif e["typ"] == "dienst":
            # Dienste bringen ihre Pauschale, niemals das Tagessoll
            minuten = int(e.get("gutschrift") or 0)
            tag["gutschrift"] += minuten
        elif e.get("gutschrift") is not None:
            # Explizite Gutschrift, z. B. halber Tag am 24.12.
            minuten = int(e["gutschrift"])
            tag["gutschrift"] += minuten
        elif e["von"] and e["bis"]:
            # Nicht-Arbeitstyp mit expliziter Zeitspanne (z. B. halber Urlaubstag)
            minuten = duration_minutes(e["von"], e["bis"], e["pause"])
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
        if d > heute and d.isoformat() not in tage:
            continue
        soll_gesamt += int(round(soll_map.get(d.isoweekday(), 0.0) * 60))

    # Tage vor dem Startdatum bleiben sichtbar, zaehlen aber nicht in den Saldo.
    def zaehlt(iso):
        return not d_start or date.fromisoformat(iso) >= d_start

    ist_gesamt = sum(t["ist"] for d, t in tage.items() if zaehlt(d))
    gutschrift_gesamt = sum(t["gutschrift"] for d, t in tage.items() if zaehlt(d))

    projekte = {}
    for e in entries:
        if e["typ"] != "arbeit":
            continue
        p = e["projekt"] or "(ohne Projekt)"
        projekte[p] = projekte.get(p, 0) + duration_minutes(e["von"], e["bis"], e["pause"])

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
            "soll": t_soll,
            "saldo": t_saldo,
            "typen": t["typen"],
            "eintraege": t["eintraege"],
        })

    namen = {a["id"]: a["name"] for a in (settings.get("dienstarten") or [])}
    dienste = {}
    for e in entries:
        if e["typ"] != "dienst" or not zaehlt(e["datum"]):
            continue
        d = dienste.setdefault(e.get("dienstart") or "", {"tage": 0, "minuten": 0})
        d["tage"] += 1
        d["minuten"] += int(e.get("gutschrift") or 0)

    return {
        "von": von,
        "bis": bis,
        "ist": ist_gesamt,
        "dienste": [{"id": k, "name": namen.get(k, k or "Dienst"), **v}
                    for k, v in sorted(dienste.items(), key=lambda kv: -kv[1]["minuten"])],
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


def feiertags_uebersicht(store, jahr):
    settings = store.get_settings()
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    vorhanden = {e["datum"] for e in store.list_entries("%d-01-01" % jahr, "%d-12-31" % jahr)}
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


def feiertage_eintragen(store, jahr):
    """Legt fuer alle Feiertage, die auf einen Arbeitstag fallen, Eintraege an."""
    uebersicht = feiertags_uebersicht(store, jahr)
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
            "projekt": "", "notiz": f["name"],
            "gutschrift": f["gutschrift"] if f["anteil"] < 1.0 else None,
        })
        schon_geplant.add(f["datum"])
    if neu:
        store.add_many(neu)
    return {"jahr": jahr, "angelegt": len(neu), "uebersprungen": len(uebersprungen),
            "tage": neu, "details": uebersprungen}


def dienst_eintragen(store, dienstart, von, bis, gutschrift=None):
    """Legt fuer jeden Tag im Zeitraum einen Diensteintrag an (z. B. Notdienstwoche)."""
    settings = store.get_settings()
    arten = {a["id"]: a for a in (settings.get("dienstarten") or [])}
    if dienstart not in arten:
        raise ValueError("Unbekannte Dienstart '%s'." % dienstart)
    art = arten[dienstart]
    d_von, d_bis = date.fromisoformat(von), date.fromisoformat(bis)
    if (d_bis - d_von).days > 366:
        raise ValueError("Ein Dienstzeitraum darf hoechstens ein Jahr umfassen.")

    schon = {e["datum"] for e in store.list_entries(von, bis)
             if e["typ"] == "dienst" and e.get("dienstart") == dienstart}
    neu = []
    d = d_von
    while d <= d_bis:
        if d.isoformat() not in schon:
            neu.append(clean_entry({
                "datum": d.isoformat(), "typ": "dienst", "dienstart": dienstart,
                "gutschrift": art["pauschale"] if gutschrift is None else gutschrift,
                "notiz": art["name"],
            }, arten))
        d += timedelta(days=1)
    if neu:
        store.add_many(neu)
    return {"dienstart": dienstart, "name": art["name"], "angelegt": len(neu),
            "uebersprungen": (d_bis - d_von).days + 1 - len(neu),
            "minuten": sum(e["gutschrift"] or 0 for e in neu)}


def arbeitstage_auffuellen(store, von, bis):
    """Fuellt vergangene Arbeitstage ohne Eintrag mit den Standardzeiten."""
    settings = store.get_settings()
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    std = settings.get("standardzeiten") or {}
    d_von = date.fromisoformat(von)
    d_bis = min(date.fromisoformat(bis), date.today())
    startdatum = settings.get("startdatum") or ""
    d_start = date.fromisoformat(startdatum) if startdatum else None

    # Reine Diensttage bleiben offen: waehrend einer Notdienstwoche wird ja
    # trotzdem normal gearbeitet.
    belegt = {e["datum"] for e in store.list_entries(von, bis) if e["typ"] != "dienst"}
    feiertage = set()
    for jahr in range(d_von.year, d_bis.year + 1):
        for f in feiertage_at(jahr, settings.get("sondertage", "keine")):
            feiertage.add(f["datum"])

    neu = []
    uebersprungen = {"belegt": 0, "feiertag": 0, "kein_arbeitstag": 0, "ohne_standardzeit": 0}
    d = d_von
    while d <= d_bis:
        iso = d.isoformat()
        vorlage = std.get(str(d.isoweekday()))
        if d_start and d < d_start:
            pass
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
            })
        d += timedelta(days=1)

    if neu:
        store.add_many(neu)
    return {"angelegt": len(neu), "von": von, "bis": d_bis.isoformat(),
            "uebersprungen": uebersprungen}


def effective_settings(store):
    """Einstellungen mit gesetztem Startdatum: ohne eigene Angabe zaehlt das Soll
    ab dem ersten erfassten Tag (und ohne Eintraege gar nicht)."""
    settings = store.get_settings()
    if not settings.get("startdatum"):
        settings["startdatum"] = store.first_entry_date() or "9999-12-31"
    return settings


def gesamtsaldo(store):
    """Saldo ueber den kompletten Erfassungszeitraum inkl. Startsaldo."""
    settings = effective_settings(store)
    entries = store.list_entries()
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
                               "notiz", "gutschrift", "dienstart")}
            for e in store.list_entries()
        ],
    }


def export_csv(store, von=None, bis=None):
    settings = store.get_settings()
    entries = store.list_entries(von, bis)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Datum", "Wochentag", "Art", "Dienst", "Von", "Bis", "Pause (Min)",
                "Dauer (h)", "Soll (h)", "Projekt", "Notiz"])
    wtage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    dienstnamen = {a["id"]: a["name"] for a in (settings.get("dienstarten") or [])}
    gesehen = set()
    for e in entries:
        d = date.fromisoformat(e["datum"])
        # Reihenfolge wie in compute(), sonst weicht der Export von der Auswertung ab
        if e["typ"] == "arbeit":
            minuten = duration_minutes(e["von"], e["bis"], e["pause"])
        elif e["typ"] == "dienst":
            minuten = int(e.get("gutschrift") or 0)
        elif e.get("gutschrift") is not None:
            minuten = int(e["gutschrift"])
        elif e["von"] and e["bis"]:
            minuten = duration_minutes(e["von"], e["bis"], e["pause"])
        else:
            minuten = int(round(soll_map.get(d.isoweekday(), 0.0) * 60))
        soll = soll_map.get(d.isoweekday(), 0.0)
        w.writerow([
            e["datum"], wtage[d.isoweekday() - 1], e["typ"].capitalize(),
            dienstnamen.get(e.get("dienstart") or "", ""),
            e["von"], e["bis"], e["pause"],
            ("%.2f" % (minuten / 60)).replace(".", ","),
            ("%.2f" % soll).replace(".", ",") if e["datum"] not in gesehen else "",
            e["projekt"], e["notiz"],
        ])
        gesehen.add(e["datum"])
    return "﻿" + buf.getvalue()


def import_data(store, payload, modus="ersetzen"):
    if modus not in ("ersetzen", "anhaengen"):
        raise ValueError("Modus muss 'ersetzen' oder 'anhaengen' sein.")
    if not isinstance(payload, dict):
        raise ValueError("Die Datei enthaelt keine gueltigen Daten.")
    roh = payload.get("eintraege")
    if not isinstance(roh, list):
        raise ValueError("Die Datei enthaelt kein Feld 'eintraege'.")

    # Dienstarten aus der Datei gelten fuer die Pruefung der Eintraege
    quelle = payload.get("einstellungen") if isinstance(payload.get("einstellungen"), dict) else {}
    liste = quelle.get("dienstarten")
    if not isinstance(liste, list):
        liste = store.get_settings().get("dienstarten") or []
    arten = {a.get("id"): a for a in liste if isinstance(a, dict) and a.get("id")}

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
            raise ValueError("Der Request-Body ist kein gueltiges JSON.")

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
            return self._json(self.store.list_entries(q.get("von"), q.get("bis")))
        if path == "/api/einstellungen":
            return self._json(self.store.get_settings())
        if path == "/api/auswertung":
            von = q.get("von") or date.today().replace(day=1).isoformat()
            bis = q.get("bis") or date.today().isoformat()
            if not (DATE_RE.match(von) and DATE_RE.match(bis)):
                raise ValueError("Zeitraum bitte als JJJJ-MM-TT angeben.")
            if bis < von:
                raise ValueError("Das Ende des Zeitraums liegt vor dem Anfang.")
            res = compute(self.store.list_entries(von, bis), effective_settings(self.store),
                          von, bis)
            res["gesamtsaldo"] = gesamtsaldo(self.store)
            return self._json(res)
        if path == "/api/feiertage":
            jahr = q.get("jahr") or str(date.today().year)
            if not re.match(r"^\d{4}$", str(jahr)) or not (1900 <= int(jahr) <= 2200):
                raise ValueError("Jahr bitte vierstellig zwischen 1900 und 2200 angeben.")
            return self._json(feiertags_uebersicht(self.store, int(jahr)))
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
                200, export_csv(self.store, q.get("von"), q.get("bis")),
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
        if method == "POST" and path == "/api/dienste":
            body = self._body()
            von = (body.get("von") or "").strip()
            bis = (body.get("bis") or von).strip()
            if not (DATE_RE.match(von) and DATE_RE.match(bis)):
                raise ValueError("Zeitraum bitte als JJJJ-MM-TT angeben.")
            if bis < von:
                raise ValueError("Das Ende des Zeitraums liegt vor dem Anfang.")
            return self._json(dienst_eintragen(
                self.store, (body.get("dienstart") or "").strip(), von, bis,
                body.get("gutschrift")))
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
            return self._json(self.store.save_settings(self._body()))
        if method == "POST" and path == "/api/feiertage":
            body = self._body()
            jahr = body.get("jahr") or date.today().year
            try:
                jahr = int(jahr)
            except (TypeError, ValueError):
                raise ValueError("Jahr bitte als Zahl angeben.")
            if not 1900 <= jahr <= 2200:
                raise ValueError("Jahr bitte zwischen 1900 und 2200 angeben.")
            return self._json(feiertage_eintragen(self.store, jahr))
        if method == "POST" and path == "/api/auffuellen":
            body = self._body()
            von = (body.get("von") or "").strip()
            bis = (body.get("bis") or "").strip()
            if not (DATE_RE.match(von) and DATE_RE.match(bis)):
                raise ValueError("Zeitraum bitte als JJJJ-MM-TT angeben.")
            if bis < von:
                raise ValueError("Das Ende des Zeitraums liegt vor dem Anfang.")
            return self._json(arbeitstage_auffuellen(self.store, von, bis))
        if method == "POST" and path == "/api/import":
            body = self._body()
            modus = body.get("modus") or "ersetzen"
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
            "Achtung: --host %s macht die Zeiterfassung ohne Passwort fuer alle im Netz\n"
            "erreichbar - jeder koennte deine Zeiten lesen, aendern und loeschen.\n"
            "Wenn das wirklich gewollt ist, zusaetzlich --im-netz-freigeben angeben."
            % args.host)

    Handler.store = Store(args.db)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.extra_host = None if lokal else args.host
    url = "http://%s:%d" % (args.host, args.port)
    print("Zeiterfassung laeuft auf %s" % url)
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
