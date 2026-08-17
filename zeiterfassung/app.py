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

ENTRY_TYPES = ("arbeit", "urlaub", "krank", "feiertag", "gleitzeit")
# Typen, die den Soll-Wert des Tages automatisch gutschreiben:
CREDIT_TYPES = ("urlaub", "krank", "feiertag", "gleitzeit")

DEFAULT_SETTINGS = {
    # Sollstunden je Wochentag, 1 = Montag ... 7 = Sonntag
    "soll": {"1": 8.0, "2": 8.0, "3": 8.0, "4": 8.0, "5": 8.0, "6": 0.0, "7": 0.0},
    # Startsaldo in Stunden (Uebertrag aus dem alten System)
    "startsaldo": 0.0,
    # Ab diesem Datum wird Soll gerechnet (leer = ab erstem Eintrag)
    "startdatum": "",
    "name": "",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


# --------------------------------------------------------------------------
# Datenbank
# --------------------------------------------------------------------------

class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
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
                    notiz   TEXT NOT NULL DEFAULT ''
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_entries_datum ON entries(datum)")
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
        return data

    def save_settings(self, patch):
        current = self.get_settings()
        if "soll" in patch:
            soll = {}
            for d in range(1, 8):
                raw = (patch["soll"] or {}).get(str(d), current["soll"][str(d)])
                soll[str(d)] = max(0.0, min(24.0, float(raw)))
            current["soll"] = soll
        if "startsaldo" in patch:
            current["startsaldo"] = float(patch["startsaldo"] or 0)
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
                "INSERT INTO entries(datum, typ, von, bis, pause, projekt, notiz) "
                "VALUES(?,?,?,?,?,?,?)",
                (e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"], e["notiz"]),
            )
            return cur.lastrowid

    def update_entry(self, entry_id, e):
        with self.lock, self._connect() as con:
            cur = con.execute(
                "UPDATE entries SET datum=?, typ=?, von=?, bis=?, pause=?, projekt=?, notiz=? "
                "WHERE id=?",
                (e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"],
                 e["notiz"], entry_id),
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
                "INSERT INTO entries(datum, typ, von, bis, pause, projekt, notiz) "
                "VALUES(?,?,?,?,?,?,?)",
                [(e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"], e["notiz"])
                 for e in entries],
            )

    def add_many(self, entries):
        with self.lock, self._connect() as con:
            con.executemany(
                "INSERT INTO entries(datum, typ, von, bis, pause, projekt, notiz) "
                "VALUES(?,?,?,?,?,?,?)",
                [(e["datum"], e["typ"], e["von"], e["bis"], e["pause"], e["projekt"], e["notiz"])
                 for e in entries],
            )

    def first_entry_date(self):
        with self.lock, self._connect() as con:
            row = con.execute("SELECT MIN(datum) AS d FROM entries").fetchone()
        return row["d"] if row and row["d"] else None


# --------------------------------------------------------------------------
# Validierung und Berechnung
# --------------------------------------------------------------------------

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


def clean_entry(raw):
    """Prueft und normalisiert einen Eintrag aus dem Frontend."""
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

    if typ == "arbeit":
        if not von or not bis:
            raise ValueError("Bei Arbeitszeit sind 'Von' und 'Bis' noetig.")
        dauer = duration_minutes(von, bis, pause)
        if dauer < 0:
            raise ValueError("Die Pause ist laenger als die erfasste Zeitspanne.")
    else:
        if von and bis:
            duration_minutes(von, bis, pause)  # nur validieren
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
    }


def duration_minutes(von, bis, pause):
    """Netto-Minuten. Ein 'Bis' vor dem 'Von' gilt als Nachtschicht ueber Mitternacht."""
    start = parse_time(von)
    end = parse_time(bis)
    if end <= start:
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

    # Soll nur bis heute (bzw. bis zum letzten erfassten Tag) zaehlen, damit der
    # laufende Monat nicht kuenstlich im Minus steht.
    grenze = date.today()
    if tage:
        grenze = max(grenze, max(date.fromisoformat(d) for d in tage))

    soll_gesamt = 0
    for d in daterange(d_von, d_bis):
        if d_start and d < d_start:
            continue
        if d > grenze:
            continue
        soll_gesamt += int(round(soll_map.get(d.isoweekday(), 0.0) * 60))

    ist_gesamt = sum(t["ist"] for t in tage.values())
    gutschrift_gesamt = sum(t["gutschrift"] for t in tage.values())

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
        if d_start and date.fromisoformat(d) < d_start:
            t_soll = 0
        tagesliste.append({
            "datum": d,
            "wochentag": wd,
            "ist": t["ist"],
            "gutschrift": t["gutschrift"],
            "soll": t_soll,
            "saldo": t["ist"] + t["gutschrift"] - t_soll,
            "typen": t["typen"],
            "eintraege": t["eintraege"],
        })

    return {
        "von": von,
        "bis": bis,
        "ist": ist_gesamt,
        "gutschrift": gutschrift_gesamt,
        "erfasst": ist_gesamt + gutschrift_gesamt,
        "soll": soll_gesamt,
        "saldo": ist_gesamt + gutschrift_gesamt - soll_gesamt,
        "tage": tagesliste,
        "projekte": [{"projekt": k, "minuten": v} for k, v in
                     sorted(projekte.items(), key=lambda kv: -kv[1])],
    }


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
    # Nur bis zum letzten erfassten Tag rechnen, damit kuenftige Tage keinen
    # Minus-Saldo erzeugen.
    bis = max(e["datum"] for e in entries)
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
            {k: e[k] for k in ("datum", "typ", "von", "bis", "pause", "projekt", "notiz")}
            for e in store.list_entries()
        ],
    }


def export_csv(store, von=None, bis=None):
    settings = store.get_settings()
    entries = store.list_entries(von, bis)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Datum", "Wochentag", "Art", "Von", "Bis", "Pause (Min)",
                "Dauer (h)", "Soll (h)", "Projekt", "Notiz"])
    wtage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    soll_map = {int(k): float(v) for k, v in settings["soll"].items()}
    gesehen = set()
    for e in entries:
        d = date.fromisoformat(e["datum"])
        if e["typ"] == "arbeit" or (e["von"] and e["bis"]):
            minuten = duration_minutes(e["von"], e["bis"], e["pause"])
        else:
            minuten = int(round(soll_map.get(d.isoweekday(), 0.0) * 60))
        soll = soll_map.get(d.isoweekday(), 0.0)
        w.writerow([
            e["datum"], wtage[d.isoweekday() - 1], e["typ"].capitalize(),
            e["von"], e["bis"], e["pause"],
            ("%.2f" % (minuten / 60)).replace(".", ","),
            ("%.2f" % soll).replace(".", ",") if e["datum"] not in gesehen else "",
            e["projekt"], e["notiz"],
        ])
        gesehen.add(e["datum"])
    return "﻿" + buf.getvalue()


def import_data(store, payload, modus="ersetzen"):
    roh = payload.get("eintraege")
    if not isinstance(roh, list):
        raise ValueError("Die Datei enthaelt kein Feld 'eintraege'.")
    sauber = [clean_entry(e) for e in roh]
    if modus == "anhaengen":
        store.add_many(sauber)
    else:
        store.replace_all(sauber)
    if isinstance(payload.get("einstellungen"), dict):
        store.save_settings(payload["einstellungen"])
    return len(sauber)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "Zeiterfassung/1.0"
    store = None

    def log_message(self, fmt, *args):
        pass  # ruhige Konsole

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
        if method == "POST" and path == "/api/eintraege":
            e = clean_entry(self._body())
            new_id = self.store.insert_entry(e)
            return self._json(self.store.get_entry(new_id), 201)
        if method == "PUT" and m:
            e = clean_entry(self._body())
            if not self.store.update_entry(int(m.group(1)), e):
                return self._error("Eintrag nicht gefunden.", 404)
            return self._json(self.store.get_entry(int(m.group(1))))
        if method == "DELETE" and m:
            if not self.store.delete_entry(int(m.group(1))):
                return self._error("Eintrag nicht gefunden.", 404)
            return self._json({"ok": True})
        if method == "PUT" and path == "/api/einstellungen":
            return self._json(self.store.save_settings(self._body()))
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
        full = os.path.join(STATIC_DIR, rel)
        if not os.path.abspath(full).startswith(os.path.abspath(STATIC_DIR)) \
                or not os.path.isfile(full):
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
    args = ap.parse_args()

    Handler.store = Store(args.db)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
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
