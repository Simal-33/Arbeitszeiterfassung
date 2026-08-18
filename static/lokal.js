/*
 * Lokaler Betrieb ohne Server.
 *
 * Bildet dieselbe API nach wie app.py, speichert aber im Browser (IndexedDB).
 * So laeuft dieselbe Oberflaeche am Handy als installierbare Web-App und am
 * Rechner gegen den Python-Server - die Rechenregeln stehen hier bewusst in
 * derselben Reihenfolge wie in app.py.
 */

const LOKAL = (() => {

const DB_NAME = "zeiterfassung", DB_VERSION = 1;
const ENTRY_TYPES = ["arbeit", "urlaub", "krank", "feiertag", "gleitzeit", "dienst", "ausfahrt"];
// Gesondert verrechnet, also nie in Ist, Saldo oder Überstunden:
const SEPARATE_TYPES = ["dienst", "ausfahrt"];
const SONDERTAGE_MODI = ["keine", "halb", "ganz"];
const DIENST_MODI = ["durchgehend", "taeglich"];
const WOCHENTAGE = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^\d{1,2}:\d{2}$/;

const STANDARD = () => ({
  soll: {"1":8,"2":8,"3":8,"4":8,"5":8,"6":0,"7":0},
  standardzeiten: {
    "1": {von:"08:00", bis:"16:30", pause:30}, "2": {von:"08:00", bis:"16:30", pause:30},
    "3": {von:"08:00", bis:"16:30", pause:30}, "4": {von:"08:00", bis:"16:30", pause:30},
    "5": {von:"08:00", bis:"16:30", pause:30}, "6": null, "7": null,
  },
  sondertage: "keine",
  // Wochenrhythmus je Dienst; die Dauer ist eine Zeitpauschale und wird
  // gesondert verrechnet, zählt also nie als Arbeitszeit.
  dienstarten: [
    {id:"dienst-1", name:"1. Dienst", modus:"durchgehend",
     starttag:1, startzeit:"07:00", endtag:1, endzeit:"07:00", pauschale:0, farbe:"#b45309"},
    {id:"dienst-2", name:"2. Dienst", modus:"taeglich",
     starttag:1, startzeit:"07:00", endtag:6, endzeit:"20:00", pauschale:0, farbe:"#0f766e"},
    {id:"dienst-3", name:"3. Dienst", modus:"taeglich",
     starttag:5, startzeit:"07:00", endtag:6, endzeit:"20:00", pauschale:0, farbe:"#6d28d9"},
  ],
  startsaldo: 0, startdatum: "", name: "",
});

class Fehler extends Error {}

// ---------------------------------------------------------------- Datenbank
let dbP = null;
function db(){
  if (dbP) return dbP;
  dbP = new Promise((ok, fail) => {
    const anfrage = indexedDB.open(DB_NAME, DB_VERSION);
    anfrage.onupgradeneeded = () => {
      const d = anfrage.result;
      if (!d.objectStoreNames.contains("eintraege"))
        d.createObjectStore("eintraege", {keyPath:"id", autoIncrement:true})
         .createIndex("datum", "datum");
      if (!d.objectStoreNames.contains("einstellungen"))
        d.createObjectStore("einstellungen");
    };
    anfrage.onsuccess = () => ok(anfrage.result);
    anfrage.onerror = () => fail(new Fehler(
      "Der Browser erlaubt keinen lokalen Speicher. Im privaten Modus funktioniert das nicht."));
  });
  return dbP;
}

async function tx(stores, modus, arbeit){
  const d = await db();
  return new Promise((ok, fail) => {
    const t = d.transaction(stores, modus);
    let ergebnis;
    t.oncomplete = () => ok(ergebnis);
    t.onerror = () => fail(new Fehler("Speichern fehlgeschlagen: " + (t.error?.message || "")));
    Promise.resolve(arbeit(t)).then(r => { ergebnis = r; }, fail);
  });
}

const anfrage = req => new Promise((ok, fail) => {
  req.onsuccess = () => ok(req.result);
  req.onerror = () => fail(new Fehler(req.error?.message || "Datenbankfehler"));
});

// ------------------------------------------------------------ Einstellungen
async function getSettings(){
  const gespeichert = await tx(["einstellungen"], "readonly",
    t => anfrage(t.objectStore("einstellungen").get("alle")));
  const data = Object.assign(STANDARD(), gespeichert || {});
  const soll = {};
  for (let d = 1; d <= 7; d++) soll[String(d)] = Number(data.soll?.[String(d)] ?? 0);
  data.soll = soll;
  const std = {};
  for (let d = 1; d <= 7; d++) std[String(d)] = data.standardzeiten?.[String(d)] ?? null;
  data.standardzeiten = std;
  if (!SONDERTAGE_MODI.includes(data.sondertage)) data.sondertage = "keine";
  if (!Array.isArray(data.dienstarten)) data.dienstarten = [];
  return data;
}

function slugify(text){
  let s = String(text).trim().toLowerCase();
  for (const [a,b] of [["ä","ae"],["ö","oe"],["ü","ue"],["ß","ss"]]) s = s.split(a).join(b);
  s = s.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return (s || "dienst").slice(0, 40);
}

async function saveSettings(patch){
  if (!patch || typeof patch !== "object") throw new Fehler("Einstellungen fehlen.");
  const current = await getSettings();
  if ("soll" in patch){
    if (patch.soll && typeof patch.soll !== "object") throw new Fehler("Sollstunden sind ungültig.");
    const soll = {};
    for (let d = 1; d <= 7; d++){
      const roh = patch.soll?.[String(d)] ?? current.soll[String(d)];
      const zahl = Number(roh);
      if (!isFinite(zahl)) throw new Fehler(`Sollstunden für ${WOCHENTAGE[d-1]} sind keine Zahl.`);
      soll[String(d)] = Math.max(0, Math.min(24, zahl));
    }
    current.soll = soll;
  }
  if ("standardzeiten" in patch){
    const std = {};
    for (let d = 1; d <= 7; d++){
      const roh = patch.standardzeiten?.[String(d)];
      if (!roh || !roh.von || !roh.bis){ std[String(d)] = null; continue; }
      const pause = Math.trunc(Number(roh.pause) || 0);
      if (pause < 0) throw new Fehler("Die Pause kann nicht negativ sein.");
      if (dauerMinuten(roh.von, roh.bis, pause) <= 0)
        throw new Fehler(`Standardzeit für ${WOCHENTAGE[d-1]} ergibt keine Arbeitszeit.`);
      std[String(d)] = {von: roh.von, bis: roh.bis, pause};
    }
    current.standardzeiten = std;
  }
  if ("dienstarten" in patch){
    if (!Array.isArray(patch.dienstarten)) throw new Fehler("Dienstarten müssen eine Liste sein.");
    const arten = [], vergeben = new Set();
    for (const roh of patch.dienstarten){
      const name = String(roh?.name || "").trim().slice(0, 40);
      if (!name) continue;
      let kennung = slugify(roh.id || name), grund = kennung, nummer = 2;
      while (vergeben.has(kennung)) kennung = `${grund}-${nummer++}`;
      vergeben.add(kennung);
      const pauschale = Math.round(Number(roh.pauschale) || 0);
      if (!isFinite(pauschale) || pauschale < 0 || pauschale > 1440)
        throw new Fehler(`Pauschale von „${name}" muss zwischen 0 und 1440 Minuten liegen.`);
      const farbe = /^#[0-9a-fA-F]{6}$/.test(roh.farbe || "") ? roh.farbe : "#b45309";
      const art = {id: kennung, name, pauschale, farbe};

      // Wochenrhythmus ist freiwillig; ohne ihn bleibt es bei der festen
      // Pauschale je Tag.
      const modus = String(roh.modus || "").trim().toLowerCase();
      if (modus){
        if (!DIENST_MODI.includes(modus))
          throw new Fehler(`Modus von „${name}" muss 'durchgehend' oder 'taeglich' sein.`);
        const starttag = Math.trunc(Number(roh.starttag) || 0);
        const endtag = Math.trunc(Number(roh.endtag) || 0);
        if (!(starttag >= 1 && starttag <= 7 && endtag >= 1 && endtag <= 7))
          throw new Fehler(`Start- und Endtag von „${name}" müssen zwischen 1 (Montag) `
            + "und 7 (Sonntag) liegen.");
        for (const [feld, wert] of [["startzeit", roh.startzeit], ["endzeit", roh.endzeit]]){
          if (!TIME_RE.test(String(wert || "")))
            throw new Fehler(`${feld} von „${name}" muss im Format HH:MM sein.`);
          parseZeit(String(wert));
        }
        Object.assign(art, {modus, starttag, endtag,
          startzeit: String(roh.startzeit), endzeit: String(roh.endzeit)});
        if (!dienstTage(art, "2024-01-01").length)
          throw new Fehler(`„${name}" ergibt keine Dienstzeit.`);
      }
      arten.push(art);
    }
    current.dienstarten = arten;
  }
  if ("sondertage" in patch){
    const modus = String(patch.sondertage || "keine").toLowerCase();
    if (!SONDERTAGE_MODI.includes(modus))
      throw new Fehler("Sondertage muss 'keine', 'halb' oder 'ganz' sein.");
    current.sondertage = modus;
  }
  if ("startsaldo" in patch){
    const zahl = Number(patch.startsaldo || 0);
    if (!isFinite(zahl)) throw new Fehler("Startsaldo muss eine Zahl sein.");
    current.startsaldo = zahl;
  }
  if ("startdatum" in patch){
    const sd = String(patch.startdatum || "").trim();
    if (sd && !DATE_RE.test(sd)) throw new Fehler("Startdatum muss im Format JJJJ-MM-TT sein.");
    current.startdatum = sd;
  }
  if ("name" in patch) current.name = String(patch.name || "").slice(0, 80);

  await tx(["einstellungen"], "readwrite",
    t => anfrage(t.objectStore("einstellungen").put(current, "alle")));
  return current;
}

// ------------------------------------------------------------------ Zeiten
function parseZeit(wert){
  if (!TIME_RE.test(wert)) throw new Fehler("Uhrzeit muss im Format HH:MM sein (z. B. 08:30).");
  const [h, m] = wert.split(":").map(Number);
  if (h > 23 || m > 59) throw new Fehler("Ungültige Uhrzeit: " + wert);
  return h * 60 + m;
}

function dauerMinuten(von, bis, pause){
  const start = parseZeit(von);
  let ende = parseZeit(bis);
  if (ende === start) throw new Fehler("'Von' und 'Bis' dürfen nicht gleich sein.");
  if (ende < start) ende += 24 * 60;
  return ende - start - Math.trunc(pause || 0);
}

const tagAus = iso => new Date(iso + "T00:00:00");
const isoWochentag = iso => ((tagAus(iso).getDay() + 6) % 7) + 1;
function isoVon(d){
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function plusTage(iso, n){ const d = tagAus(iso); d.setDate(d.getDate() + n); return isoVon(d); }
function heuteIso(){ return isoVon(new Date()); }

// Legt den Beginn eines Dienstes auf den Starttag der Dienstart: genommen wird
// der letzte passende Wochentag, der nicht nach 'datum' liegt.
function dienstStart(art, datum){
  const starttag = Math.trunc(Number(art.starttag) || 0);
  if (!(starttag >= 1 && starttag <= 7)) return datum;
  return plusTage(datum, -((isoWochentag(datum) - starttag + 7) % 7));
}

// Liefert [[datum, minuten], ...] - den Anteil der Zeitpauschale je Kalendertag.
// Ohne Wochenrhythmus bleibt es bei einem Tag mit der festen Pauschale.
function dienstTage(art, datum){
  const d0 = dienstStart(art, datum);
  const modus = String(art.modus || "").trim().toLowerCase();
  const starttag = Math.trunc(Number(art.starttag) || 0);
  const endtag = Math.trunc(Number(art.endtag) || 0);
  if (!DIENST_MODI.includes(modus) || !(starttag >= 1 && starttag <= 7
      && endtag >= 1 && endtag <= 7))
    return [[d0, Math.trunc(Number(art.pauschale) || 0)]];

  const beginn = parseZeit(art.startzeit || "00:00");
  const ende = parseZeit(art.endzeit || "00:00");

  if (modus === "taeglich"){
    // An jedem Tag dasselbe Zeitfenster, z. B. Montag bis Samstag 07:00-20:00.
    let laenge = ende - beginn;
    if (laenge <= 0) laenge += 24 * 60;
    const anzahl = (endtag - starttag + 7) % 7 + 1;
    return Array.from({length: anzahl}, (_, i) => [plusTage(d0, i), laenge]);
  }

  // durchgehend, z. B. Montag 07:00 bis Montag 07:00: erster und letzter
  // Kalendertag sind angebrochen, die dazwischen zählen voll.
  let spanne = (endtag - starttag + 7) % 7;
  if (spanne === 0 && ende <= beginn) spanne = 7;   // gleicher Wochentag = volle Woche
  let rest = spanne * 24 * 60 + (ende - beginn);
  if (rest <= 0) return [];
  const tage = [];
  let tag = 0, platz = 24 * 60 - beginn;
  while (rest > 0){
    const anteil = Math.min(platz, rest);
    tage.push([plusTage(d0, tag), anteil]);
    rest -= anteil;
    tag += 1;
    platz = 24 * 60;
  }
  return tage;
}

// Gesamte Zeitpauschale einer Dienstart in Minuten. Das Ergebnis hängt nur an
// der Definition, das Bezugsdatum ist beliebig.
function dienstPauschale(art){
  return dienstTage(art, "2024-01-01").reduce((s, [, m]) => s + m, 0);
}

// Einstellungen für die Anzeige: jede Dienstart bekommt ihre Gesamtdauer und
// die Zahl der Kalendertage. So muss die Oberfläche nichts selbst rechnen und
// zeigt in beiden Betriebsarten dieselbe Zahl.
function mitDauer(settings){
  return {...settings, dienstarten: (settings.dienstarten || []).map(a =>
    ({...a, dauer: dienstPauschale(a), tage: dienstTage(a, "2024-01-01").length}))};
}

function pruefeEintrag(roh, dienstarten){
  const datum = String(roh.datum || "").trim();
  if (!DATE_RE.test(datum)) throw new Fehler("Bitte ein gültiges Datum angeben (JJJJ-MM-TT).");
  const probe = tagAus(datum);
  if (isNaN(probe) || isoVon(probe) !== datum) throw new Fehler(`Das Datum ${datum} gibt es nicht.`);

  const typ = String(roh.typ || "arbeit").trim().toLowerCase();
  if (!ENTRY_TYPES.includes(typ)) throw new Fehler("Unbekannte Art: " + typ);

  let von = String(roh.von || "").trim(), bis = String(roh.bis || "").trim();
  let pause = Math.trunc(Number(roh.pause) || 0);
  if (!isFinite(pause)) throw new Fehler("Pause muss eine Zahl in Minuten sein.");
  if (pause < 0) throw new Fehler("Die Pause kann nicht negativ sein.");

  let gutschrift = (roh.gutschrift === "" || roh.gutschrift == null) ? null : Math.round(Number(roh.gutschrift));
  if (gutschrift !== null){
    if (!isFinite(gutschrift)) throw new Fehler("Gutschrift muss eine Zahl in Minuten sein.");
    if (gutschrift < 0) throw new Fehler("Die Gutschrift kann nicht negativ sein.");
    if (gutschrift > 1440) throw new Fehler("Die Gutschrift kann höchstens 24 Stunden betragen.");
  }

  let dienstart = String(roh.dienstart || "").trim();
  if (typ === "dienst"){
    if (!dienstarten) dienstart = dienstart ? slugify(dienstart) : "";
    else {
      if (!dienstart) throw new Fehler("Bitte eine Dienstart wählen.");
      if (!dienstarten[dienstart])
        throw new Fehler(`Unbekannte Dienstart '${dienstart}'. Erst in den Einstellungen anlegen.`);
      if (gutschrift === null) gutschrift = Number(dienstarten[dienstart].pauschale) || 0;
    }
    if (gutschrift === null) gutschrift = 0;
  } else dienstart = "";

  if (typ === "arbeit" || typ === "ausfahrt"){
    if (!von || !bis)
      throw new Fehler(typ === "ausfahrt" ? "Bei einer Ausfahrt sind 'Von' und 'Bis' nötig."
                                          : "Bei Arbeitszeit sind 'Von' und 'Bis' nötig.");
    if (dauerMinuten(von, bis, pause) < 0)
      throw new Fehler("Die Pause ist länger als die erfasste Zeitspanne.");
    gutschrift = null;
  } else if (von && bis){
    if (dauerMinuten(von, bis, pause) < 0)
      throw new Fehler("Die Pause ist länger als die erfasste Zeitspanne.");
  } else { von = ""; bis = ""; pause = 0; }

  return {datum, typ, von, bis, pause,
          projekt: String(roh.projekt || "").trim().slice(0, 80),
          notiz: String(roh.notiz || "").trim().slice(0, 500),
          gutschrift, dienstart};
}

// -------------------------------------------------------------- Feiertage
function ostersonntag(jahr){
  const a = jahr % 19, b = Math.floor(jahr / 100), c = jahr % 100;
  const d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4), k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const monat = Math.floor((h + l - 7 * m + 114) / 31);
  const tag = ((h + l - 7 * m + 114) % 31) + 1;
  return `${jahr}-${String(monat).padStart(2,"0")}-${String(tag).padStart(2,"0")}`;
}

function feiertageAT(jahr, sondertage = "keine"){
  const o = ostersonntag(jahr), j = String(jahr);
  const feste = [
    [`${j}-01-01`, "Neujahr"], [`${j}-01-06`, "Heilige Drei Koenige"],
    [plusTage(o, 1), "Ostermontag"], [`${j}-05-01`, "Staatsfeiertag"],
    [plusTage(o, 39), "Christi Himmelfahrt"], [plusTage(o, 50), "Pfingstmontag"],
    [plusTage(o, 60), "Fronleichnam"], [`${j}-08-15`, "Mariae Himmelfahrt"],
    [`${j}-10-26`, "Nationalfeiertag"], [`${j}-11-01`, "Allerheiligen"],
    [`${j}-12-08`, "Mariae Empfaengnis"], [`${j}-12-25`, "Christtag"],
    [`${j}-12-26`, "Stefanitag"],
  ];
  const liste = feste.map(([datum, name]) => ({datum, name, anteil: 1, gesetzlich: true}));
  if (sondertage === "halb" || sondertage === "ganz"){
    const anteil = sondertage === "halb" ? 0.5 : 1;
    liste.push({datum: `${j}-12-24`, name: "Heiliger Abend", anteil, gesetzlich: false});
    liste.push({datum: `${j}-12-31`, name: "Silvester", anteil, gesetzlich: false});
  }
  return liste.sort((a, b) => a.datum.localeCompare(b.datum));
}

// -------------------------------------------------------------- Berechnung
function berechne(entries, settings, von, bis){
  const sollMap = {};
  for (let d = 1; d <= 7; d++) sollMap[d] = Number(settings.soll[String(d)] || 0);
  const start = settings.startdatum || "";

  const tage = {};
  for (const e of entries){
    const t = tage[e.datum] || (tage[e.datum] =
      {ist:0, gutschrift:0, pauschale:0, ausfahrt:0, typen:[], eintraege:[]});
    let minuten = 0;
    if (e.typ === "arbeit"){
      minuten = dauerMinuten(e.von, e.bis, e.pause); t.ist += minuten;
    } else if (e.typ === "dienst"){
      // Zeitpauschale des Dienstes: gesondert verrechnet, nie im Saldo.
      minuten = Math.trunc(e.gutschrift || 0); t.pauschale += minuten;
    } else if (e.typ === "ausfahrt"){
      minuten = dauerMinuten(e.von, e.bis, e.pause); t.ausfahrt += minuten;
    } else if (e.gutschrift != null){
      minuten = Math.trunc(e.gutschrift); t.gutschrift += minuten;
    } else if (e.von && e.bis){
      minuten = dauerMinuten(e.von, e.bis, e.pause); t.gutschrift += minuten;
    } else {
      minuten = Math.round(sollMap[isoWochentag(e.datum)] * 60); t.gutschrift += minuten;
    }
    if (!t.typen.includes(e.typ)) t.typen.push(e.typ);
    t.eintraege.push({...e, minuten});
  }

  const zaehlt = iso => !start || iso >= start;
  const heute = heuteIso();
  let sollGesamt = 0;
  for (let d = von; d <= bis; d = plusTage(d, 1)){
    if (start && d < start) continue;
    if (d > heute && !tage[d]) continue;
    sollGesamt += Math.round(sollMap[isoWochentag(d)] * 60);
  }

  let ist = 0, gut = 0, pauschaleGesamt = 0, ausfahrtGesamt = 0;
  for (const [d, t] of Object.entries(tage)) if (zaehlt(d)){
    ist += t.ist; gut += t.gutschrift;
    pauschaleGesamt += t.pauschale; ausfahrtGesamt += t.ausfahrt;
  }

  const projekte = {};
  for (const e of entries){
    if (e.typ !== "arbeit") continue;
    const p = e.projekt || "(ohne Projekt)";
    projekte[p] = (projekte[p] || 0) + dauerMinuten(e.von, e.bis, e.pause);
  }

  const namen = {};
  for (const a of (settings.dienstarten || [])) namen[a.id] = a.name;
  // Welcher Dienst läuft an welchem Tag? Damit bekommt jede Ausfahrt ihren
  // Dienst zugeordnet, ohne dass er am Eintrag mitgeführt werden muss.
  const dienstAmTag = {};
  for (const e of entries) if (e.typ === "dienst") dienstAmTag[e.datum] = e.dienstart || "";

  const dienste = {};
  for (const e of entries){
    if (e.typ !== "dienst" || !zaehlt(e.datum)) continue;
    const d = dienste[e.dienstart || ""] || (dienste[e.dienstart || ""] =
      {tage:0, minuten:0, ausfahrten:0, ausfahrt_minuten:0});
    d.tage += 1; d.minuten += Math.trunc(e.gutschrift || 0);
  }

  const ausfahrten = [];
  for (const e of entries){
    if (e.typ !== "ausfahrt" || !zaehlt(e.datum)) continue;
    const kennung = dienstAmTag[e.datum] || "";
    const minuten = dauerMinuten(e.von, e.bis, e.pause);
    ausfahrten.push({id: e.id, datum: e.datum, wochentag: isoWochentag(e.datum),
      von: e.von, bis: e.bis, pause: e.pause, minuten, notiz: e.notiz,
      projekt: e.projekt, dienstart: kennung,
      dienst: kennung ? (namen[kennung] || "") : ""});
    if (dienste[kennung]){
      dienste[kennung].ausfahrten += 1;
      dienste[kennung].ausfahrt_minuten += minuten;
    }
  }
  ausfahrten.sort((a, b) => a.datum.localeCompare(b.datum) || a.von.localeCompare(b.von));

  const tagesliste = Object.keys(tage).sort().map(d => {
    const t = tage[d], wd = isoWochentag(d);
    let tSoll = Math.round(sollMap[wd] * 60);
    let saldo = t.ist + t.gutschrift - tSoll;
    if (!zaehlt(d)){ tSoll = 0; saldo = 0; }
    return {datum:d, wochentag:wd, ist:t.ist, gutschrift:t.gutschrift,
            pauschale:t.pauschale, ausfahrt:t.ausfahrt, soll:tSoll,
            saldo, typen:t.typen, eintraege:t.eintraege};
  });

  return {
    von, bis, ist, gutschrift: gut, erfasst: ist + gut, soll: sollGesamt,
    saldo: ist + gut - sollGesamt, tage: tagesliste,
    // Beides wird gesondert verrechnet und steckt bewusst nicht in erfasst/saldo.
    pauschale: pauschaleGesamt, ausfahrt: ausfahrtGesamt, ausfahrten,
    dienste: Object.entries(dienste).sort((a,b) => b[1].minuten - a[1].minuten)
      .map(([k, v]) => ({id:k, name: namen[k] || k || "Dienst", ...v})),
    projekte: Object.entries(projekte).sort((a,b) => b[1] - a[1])
      .map(([k, v]) => ({projekt:k, minuten:v})),
  };
}

async function alleEintraege(von, bis){
  const alle = await tx(["eintraege"], "readonly", t => anfrage(t.objectStore("eintraege").getAll()));
  return alle
    .filter(e => (!von || e.datum >= von) && (!bis || e.datum <= bis))
    .sort((a, b) => a.datum.localeCompare(b.datum) || (a.von || "").localeCompare(b.von || "")
                    || a.id - b.id);
}

async function gesamtsaldo(){
  const settings = await getSettings();
  const entries = await alleEintraege();
  const startsaldo = Math.round(Number(settings.startsaldo || 0) * 60);
  if (!entries.length) return startsaldo;
  const arbeit = entries.filter(e => e.typ === "arbeit");
  const ersterTag = (arbeit.length ? arbeit : entries)[0].datum;
  const s = {...settings, startdatum: settings.startdatum || ersterTag};
  const von = [s.startdatum, entries[0].datum].sort()[0];
  const bis = [entries[entries.length-1].datum, heuteIso()].sort().pop();
  return berechne(entries, s, von, bis).saldo + startsaldo;
}

async function wirksameEinstellungen(){
  const settings = await getSettings();
  if (!settings.startdatum){
    const entries = await alleEintraege();
    const arbeit = entries.filter(e => e.typ === "arbeit");
    settings.startdatum = (arbeit[0] || entries[0])?.datum || "9999-12-31";
  }
  return settings;
}

// ------------------------------------------------------------------- API
async function auswertung(von, bis){
  if (!DATE_RE.test(von) || !DATE_RE.test(bis))
    throw new Fehler("Zeitraum bitte als JJJJ-MM-TT angeben.");
  if (bis < von) throw new Fehler("Das Ende des Zeitraums liegt vor dem Anfang.");
  const res = berechne(await alleEintraege(von, bis), await wirksameEinstellungen(), von, bis);
  res.gesamtsaldo = await gesamtsaldo();
  return res;
}

async function feiertagsUebersicht(jahr){
  const settings = await getSettings();
  const vorhanden = new Set((await alleEintraege(`${jahr}-01-01`, `${jahr}-12-31`)).map(e => e.datum));
  return {
    jahr, sondertage: settings.sondertage,
    feiertage: feiertageAT(jahr, settings.sondertage).map(f => {
      const wd = isoWochentag(f.datum);
      const soll = Math.round(Number(settings.soll[String(wd)] || 0) * 60);
      return {...f, wochentag: wd, soll, gutschrift: Math.round(soll * f.anteil),
              arbeitstag: soll > 0, erfasst: vorhanden.has(f.datum)};
    }),
  };
}

async function feiertageEintragen(jahr){
  const uebersicht = await feiertagsUebersicht(jahr);
  const neu = [], geplant = new Set();
  let uebersprungen = 0;
  for (const f of uebersicht.feiertage){
    if (geplant.has(f.datum) || !f.arbeitstag || f.erfasst){ uebersprungen++; continue; }
    neu.push({datum: f.datum, typ: "feiertag", von: "", bis: "", pause: 0, projekt: "",
              notiz: f.name, gutschrift: f.anteil < 1 ? f.gutschrift : null, dienstart: ""});
    geplant.add(f.datum);
  }
  await anlegen(neu);
  return {jahr, angelegt: neu.length, uebersprungen, tage: neu};
}

// Hat die Dienstart einen Wochenrhythmus, ergeben sich Anfang, Ende und die
// Minuten je Tag aus ihrer Definition; 'bis' wird dann nicht gebraucht.
async function dienstEintragen(dienstart, von, bis, gutschrift){
  const settings = await getSettings();
  const arten = Object.fromEntries((settings.dienstarten || []).map(a => [a.id, a]));
  if (!arten[dienstart]) throw new Fehler(`Unbekannte Dienstart '${dienstart}'.`);
  const art = arten[dienstart];

  let plan;
  if (art.modus){
    plan = dienstTage(art, von);
    if (!plan.length) throw new Fehler(`„${art.name}" ergibt keine Dienstzeit.`);
    if (gutschrift != null) plan = plan.map(([d]) => [d, Math.trunc(gutschrift)]);
  } else {
    const ende = bis || von;
    if (ende < von) throw new Fehler("Das Ende des Zeitraums liegt vor dem Anfang.");
    const fest = gutschrift == null ? Math.trunc(Number(art.pauschale) || 0)
                                    : Math.trunc(gutschrift);
    plan = [];
    for (let d = von; d <= ende; d = plusTage(d, 1)) plan.push([d, fest]);
  }

  const erster = plan[0][0], letzter = plan[plan.length - 1][0];
  const vorhanden = new Set((await alleEintraege(erster, letzter))
    .filter(e => e.typ === "dienst" && e.dienstart === dienstart).map(e => e.datum));
  const neu = plan.filter(([d]) => !vorhanden.has(d)).map(([d, minuten]) =>
    pruefeEintrag({datum: d, typ: "dienst", dienstart,
                   gutschrift: minuten, notiz: art.name}, arten));
  await anlegen(neu);
  return {dienstart, name: art.name, angelegt: neu.length, von: erster, bis: letzter,
          uebersprungen: plan.length - neu.length,
          minuten: neu.reduce((s, e) => s + (e.gutschrift || 0), 0),
          pauschale: plan.reduce((s, [, m]) => s + m, 0)};
}

async function auffuellen(von, bis){
  const settings = await getSettings();
  const bisEcht = [bis, heuteIso()].sort()[0];
  // Diensttage und Ausfahrten blockieren nicht: sie werden gesondert verrechnet,
  // gearbeitet wird an diesen Tagen ja trotzdem.
  const belegt = new Set((await alleEintraege(von, bis))
    .filter(e => !SEPARATE_TYPES.includes(e.typ))
    .map(e => e.datum));
  const feiertage = new Set();
  for (let j = Number(von.slice(0,4)); j <= Number(bisEcht.slice(0,4)); j++)
    for (const f of feiertageAT(j, settings.sondertage)) feiertage.add(f.datum);

  const neu = [], uebersprungen = {belegt:0, feiertag:0, kein_arbeitstag:0, ohne_standardzeit:0};
  for (let d = von; d <= bisEcht; d = plusTage(d, 1)){
    const wd = isoWochentag(d), vorlage = settings.standardzeiten[String(wd)];
    if (settings.startdatum && d < settings.startdatum) continue;
    else if (belegt.has(d)) uebersprungen.belegt++;
    else if (feiertage.has(d)) uebersprungen.feiertag++;
    else if (Number(settings.soll[String(wd)] || 0) <= 0) uebersprungen.kein_arbeitstag++;
    else if (!vorlage) uebersprungen.ohne_standardzeit++;
    else neu.push({datum: d, typ: "arbeit", von: vorlage.von, bis: vorlage.bis,
                   pause: Math.trunc(vorlage.pause || 0), projekt: "",
                   notiz: "automatisch aus Standardzeiten", gutschrift: null, dienstart: ""});
  }
  await anlegen(neu);
  return {angelegt: neu.length, von, bis: bisEcht, uebersprungen};
}

async function anlegen(liste){
  if (!liste.length) return;
  return tx(["eintraege"], "readwrite", t => {
    const store = t.objectStore("eintraege");
    for (const e of liste) store.add(e);
  });
}

async function exportDaten(){
  const eintraege = (await alleEintraege()).map(({id, ...rest}) => rest);
  return {app: "Zeiterfassung", version: 1, exportiert_am: new Date().toISOString().slice(0,19),
          einstellungen: await getSettings(), eintraege};
}

async function importDaten(daten, modus = "ersetzen"){
  if (!["ersetzen","anhaengen"].includes(modus))
    throw new Fehler("Modus muss 'ersetzen' oder 'anhaengen' sein.");
  if (!daten || !Array.isArray(daten.eintraege))
    throw new Fehler("Die Datei enthält kein Feld 'eintraege'.");
  const quelle = (daten.einstellungen && typeof daten.einstellungen === "object")
    ? daten.einstellungen : {};
  const liste = Array.isArray(quelle.dienstarten) ? quelle.dienstarten
    : (await getSettings()).dienstarten || [];
  const arten = Object.fromEntries(liste.filter(a => a && a.id).map(a => [a.id, a]));

  // Erst alles pruefen, dann schreiben
  const sauber = daten.eintraege.map((e, i) => {
    try { return pruefeEintrag(e, arten); }
    catch(err){ throw new Fehler(`Eintrag ${i+1} (${e?.datum || "ohne Datum"}): ${err.message}`); }
  });
  if (Object.keys(quelle).length) await saveSettings(quelle);
  await tx(["eintraege"], "readwrite", t => {
    const store = t.objectStore("eintraege");
    if (modus === "ersetzen") store.clear();
    for (const e of sauber) store.add(e);
  });
  return {ok: true, importiert: sauber.length};
}

function csvExport(entries, settings){
  const wtage = ["Mo","Di","Mi","Do","Fr","Sa","So"];
  const namen = Object.fromEntries((settings.dienstarten || []).map(a => [a.id, a.name]));
  const zeilen = [["Datum","Wochentag","Art","Dienst","Von","Bis","Pause (Min)",
                   "Dauer (h)","Soll (h)","Verrechnung","Projekt","Notiz"]];
  // Ausfahrten haben keine eigene Dienstart, sie gehören zum Dienst des Tages.
  const dienstAmTag = {};
  for (const e of entries) if (e.typ === "dienst") dienstAmTag[e.datum] = e.dienstart || "";
  const gesehen = new Set();
  for (const e of entries){
    const wd = isoWochentag(e.datum);
    let minuten;
    if (e.typ === "arbeit") minuten = dauerMinuten(e.von, e.bis, e.pause);
    else if (e.typ === "dienst") minuten = Math.trunc(e.gutschrift || 0);
    else if (e.typ === "ausfahrt") minuten = dauerMinuten(e.von, e.bis, e.pause);
    else if (e.gutschrift != null) minuten = Math.trunc(e.gutschrift);
    else if (e.von && e.bis) minuten = dauerMinuten(e.von, e.bis, e.pause);
    else minuten = Math.round(Number(settings.soll[String(wd)] || 0) * 60);
    const soll = Number(settings.soll[String(wd)] || 0);
    const kennung = e.dienstart || (e.typ === "ausfahrt" ? (dienstAmTag[e.datum] || "") : "");
    zeilen.push([e.datum, wtage[wd-1], e.typ.charAt(0).toUpperCase() + e.typ.slice(1),
      namen[kennung] || "", e.von, e.bis, e.pause,
      (minuten/60).toFixed(2).replace(".", ","),
      gesehen.has(e.datum) ? "" : soll.toFixed(2).replace(".", ","),
      SEPARATE_TYPES.includes(e.typ) ? "gesondert" : "Arbeitszeit",
      e.projekt, e.notiz]);
    gesehen.add(e.datum);
  }
  return "﻿" + zeilen.map(z => z.join(";")).join("\r\n") + "\r\n";
}

// Verteiler: bildet die Server-Endpunkte nach
async function ruf(pfad, opts = {}){
  const [weg, abfrage] = pfad.split("?");
  const q = Object.fromEntries(new URLSearchParams(abfrage || ""));
  const methode = (opts.method || "GET").toUpperCase();
  const body = opts.body ? JSON.parse(opts.body) : {};
  const settings = await getSettings();
  const arten = Object.fromEntries((settings.dienstarten || []).map(a => [a.id, a]));
  const treffer = weg.match(/^\/api\/eintraege\/(\d+)$/);

  if (weg === "/api/eintraege" && methode === "GET") return alleEintraege(q.von, q.bis);
  if (weg === "/api/eintraege" && methode === "POST"){
    const e = pruefeEintrag(body, arten);
    const id = await tx(["eintraege"], "readwrite",
      t => anfrage(t.objectStore("eintraege").add(e)));
    return {...e, id};
  }
  if (treffer && methode === "PUT"){
    const id = Number(treffer[1]);
    const e = pruefeEintrag(body, arten);
    const vorhanden = await tx(["eintraege"], "readonly",
      t => anfrage(t.objectStore("eintraege").get(id)));
    if (!vorhanden) throw new Fehler("Eintrag nicht gefunden.");
    await tx(["eintraege"], "readwrite", t => t.objectStore("eintraege").put({...e, id}));
    return {...e, id};
  }
  if (treffer && methode === "DELETE"){
    const id = Number(treffer[1]);
    const vorhanden = await tx(["eintraege"], "readonly",
      t => anfrage(t.objectStore("eintraege").get(id)));
    if (!vorhanden) throw new Fehler("Eintrag nicht gefunden.");
    await tx(["eintraege"], "readwrite", t => t.objectStore("eintraege").delete(id));
    return {ok: true};
  }
  if (weg === "/api/einstellungen")
    return methode === "GET" ? mitDauer(settings)
                             : saveSettings(body).then(mitDauer);
  if (weg === "/api/auswertung")
    return auswertung(q.von || heuteIso().slice(0,8) + "01", q.bis || heuteIso());
  if (weg === "/api/feiertage" && methode === "GET"){
    const jahr = Number(q.jahr || new Date().getFullYear());
    if (!Number.isInteger(jahr) || jahr < 1900 || jahr > 2200)
      throw new Fehler("Jahr bitte vierstellig zwischen 1900 und 2200 angeben.");
    return feiertagsUebersicht(jahr);
  }
  if (weg === "/api/feiertage" && methode === "POST"){
    const jahr = Number(body.jahr || new Date().getFullYear());
    if (!Number.isInteger(jahr) || jahr < 1900 || jahr > 2200)
      throw new Fehler("Jahr bitte zwischen 1900 und 2200 angeben.");
    return feiertageEintragen(jahr);
  }
  if (weg === "/api/dienste" && methode === "POST"){
    const von = String(body.von || "").trim();
    // 'bis' braucht nur, wer eine Dienstart ohne Wochenrhythmus nutzt.
    const bis = String(body.bis || "").trim();
    if (!DATE_RE.test(von) || (bis && !DATE_RE.test(bis)))
      throw new Fehler("Zeitraum bitte als JJJJ-MM-TT angeben.");
    if (bis && bis < von) throw new Fehler("Das Ende des Zeitraums liegt vor dem Anfang.");
    return dienstEintragen(String(body.dienstart || "").trim(), von, bis || null,
                           body.gutschrift);
  }
  if (weg === "/api/auffuellen" && methode === "POST"){
    const von = String(body.von || "").trim(), bis = String(body.bis || "").trim();
    if (!DATE_RE.test(von) || !DATE_RE.test(bis))
      throw new Fehler("Zeitraum bitte als JJJJ-MM-TT angeben.");
    if (bis < von) throw new Fehler("Das Ende des Zeitraums liegt vor dem Anfang.");
    return auffuellen(von, bis);
  }
  if (weg === "/api/import" && methode === "POST")
    return importDaten(body.daten || body, body.modus || "ersetzen");
  if (weg === "/api/export.json") return exportDaten();
  if (weg === "/api/export.csv")
    return csvExport(await alleEintraege(q.von, q.bis), settings);
  throw new Fehler("Unbekannter Endpunkt: " + weg);
}

return {ruf, feiertageAT, ostersonntag, berechne, dauerMinuten, exportDaten, Fehler};
})();
