#!/usr/bin/env python3
"""Sicherer Lauf von test_api.py gegen einen Wegwerf-Server.

test_api.py schickt POST /api/import mit modus "ersetzen" an den Server, den es
erreicht - ohne ZEIT_URL ist das Port 8765, der Default-Port der echten App.
Dieses Skript laesst deshalb nie den Default zu:

  1. Syntax pruefen wie in CI (compileall app.py test_api.py)
  2. Zielport pruefen - belegt heisst abbrechen, nicht ausweichen
  3. app.py mit eigener DB in einem frischen Temp-Ordner starten
  4. test_api.py mit gesetztem ZEIT_URL gegen genau diesen Server laufen lassen
  5. Server beenden und Temp-Ordner samt DB loeschen - auch bei Fehlern

Aufruf aus dem Projektordner (laeuft unter Python 3.9 bis 3.14):
  python .claude/skills/sicherer-testlauf/scripts/testlauf.py [--port 8791] [--voll]

Exit-Code: 0 = alle Pruefungen ok, 1 = Testfehler, 2 = Lauf kam nicht zustande.
"""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ECHTER_PORT = 8765
ZUSAMMENFASSUNG = re.compile(r"^(\d+) ok, (\d+) Fehler(?:, (\d+) uebersprungen)?\s*$")

# Lokale Adressen nie ueber einen Proxy schicken - auch nicht im Testprozess.
_DIREKT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def abbruch(text):
    print("ABBRUCH: " + text)
    raise SystemExit(2)


def port_belegt(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def warte_auf_server(url, proc, sekunden=20):
    ende = time.time() + sekunden
    while time.time() < ende:
        if proc.poll() is not None:
            return False
        try:
            with _DIREKT.open(url + "/api/einstellungen", timeout=1) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.25)
    return False


def zeitzonen_bekannt():
    try:
        from zoneinfo import available_timezones
    except ImportError:
        return False
    return bool(available_timezones())


def main():
    ap = argparse.ArgumentParser(description="test_api.py sicher gegen einen Wegwerf-Server")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--voll", action="store_true", help="komplette Testausgabe zeigen")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass

    projekt = os.getcwd()
    for datei in ("app.py", "test_api.py"):
        if not os.path.isfile(os.path.join(projekt, datei)):
            abbruch("%s fehlt - bitte aus dem Projektordner starten." % datei)
    if args.port == ECHTER_PORT:
        abbruch("Port %d ist der Default-Port der echten App. Anderen Port waehlen."
                % ECHTER_PORT)

    tz = zeitzonen_bekannt()
    print("Python %s  (%s)" % (sys.version.split()[0], sys.executable))
    print("Zeitzonendatenbank: %s" % ("vorhanden" if tz else
          "FEHLT - die 4 Sommerzeit-Pruefungen werden uebersprungen (pip install tzdata)"))

    syntax = subprocess.run([sys.executable, "-m", "compileall", "-q", "app.py", "test_api.py"],
                            cwd=projekt)
    if syntax.returncode:
        abbruch("Syntaxpruefung (compileall) fehlgeschlagen.")

    if port_belegt(args.port):
        abbruch("Port %d ist belegt. Nicht ausweichen - erst klaeren, was dort laeuft."
                % args.port)

    url = "http://127.0.0.1:%d" % args.port
    ordner = tempfile.mkdtemp(prefix="zeit-test-")
    db = os.path.join(ordner, "test.db")
    kind_env = dict(os.environ, PYTHONIOENCODING="utf-8", ZEIT_URL=url)
    for name in ("NO_PROXY", "no_proxy"):
        kind_env[name] = ",".join(filter(None, [kind_env.get(name), "127.0.0.1", "localhost"]))

    server = None
    try:
        with open(os.path.join(ordner, "server.log"), "wb") as log:
            server = subprocess.Popen(
                [sys.executable, "app.py", "--port", str(args.port), "--db", db, "--no-browser"],
                cwd=projekt, stdout=log, stderr=subprocess.STDOUT, env=kind_env)
        print("Wegwerf-Server: %s  DB: %s" % (url, db))
        if not warte_auf_server(url, server):
            with open(os.path.join(ordner, "server.log"), encoding="utf-8",
                      errors="replace") as f:
                print(f.read()[-2000:])
            abbruch("Server ist nicht hochgekommen.")

        lauf = subprocess.run([sys.executable, "test_api.py"], cwd=projekt, env=kind_env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        ausgabe = lauf.stdout.decode("utf-8", errors="replace").splitlines()

        print("\n--- test_api.py (ZEIT_URL=%s) ---" % url)
        treffer = None
        for zeile in ausgabe:
            treffer = ZUSAMMENFASSUNG.match(zeile.strip()) or treffer
            if args.voll or "FAIL" in zeile or zeile.lstrip().startswith(("---", "Traceback")) \
                    or "Error" in zeile or ZUSAMMENFASSUNG.match(zeile.strip()):
                print(zeile)
        if not treffer:
            print("\n".join(ausgabe[-30:]))
            print("\nKeine Zusammenfassungszeile gefunden - der Test ist vorzeitig ausgestiegen.")
            return 1

        ok, fehler, ueber = int(treffer.group(1)), int(treffer.group(2)), int(treffer.group(3) or 0)
        print("\nERGEBNIS: %d ok, %d Fehler, %d uebersprungen (Exit-Code %d)"
              % (ok, fehler, ueber, lauf.returncode))
        if ueber:
            print("HINWEIS: Uebersprungene Pruefungen - lokal gruen ist damit nicht CI-gruen.")
        return 0 if (lauf.returncode == 0 and fehler == 0) else 1
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        shutil.rmtree(ordner, ignore_errors=True)
        print("Aufgeraeumt: Server beendet, %s geloescht." % ordner)


if __name__ == "__main__":
    raise SystemExit(main())
