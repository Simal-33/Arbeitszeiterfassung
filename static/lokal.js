/*
 * Lokaler Betrieb ohne Server.
 *
 * Bildet dieselbe API nach wie app.py, speichert aber im Browser (IndexedDB).
 * So laeuft dieselbe Oberflaeche am Handy als installierbare Web-App und am
 * Rechner gegen den Python-Server - die Rechenregeln stehen hier bewusst in
 * derselben Reihenfolge wie in app.py.
 */

const LOKAL = (() => {

const DB_NAME = "zeiterfassung", DB_VERSION = 3;
const SICHERUNG_MAX = 10;   // so viele Staende werden aufbewahrt
const ENTRY_TYPES = ["arbeit", "urlaub", "krank", "feiertag", "gleitzeit", "dienst", "ausfahrt"];
// Gesondert verrechnet - nie in Ist, Saldo oder Überstunden:
const SEPARATE_TYPES = ["dienst", "ausfahrt"];
// Anzeigenamen. Die Kennung "gleitzeit" bleibt, damit bestehende Daten
// weiter lesbar sind - nach aussen heisst sie ueberall "Zeitausgleich".
const TYP_NAMEN = {arbeit:"Arbeit", urlaub:"Urlaub", krank:"Krank", feiertag:"Feiertag",
                   gleitzeit:"Zeitausgleich", dienst:"Dienst", ausfahrt:"Ausfahrt"};
const DIENST_MODI = ["durchgehend", "taeglich"];
const SONDERTAGE_MODI = ["keine", "halb", "ganz"];
const WOCHENTAGE = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^\d{1,2}:\d{2}$/;

const STANDARD_JOB = () => ({
  id: "standard", name: "Mein Job", farbe: "#2f6fd0",
  soll: {"1":8,"2":8,"3":8,"4":8,"5":8,"6":0,"7":0},
  standardzeiten: {
    "1": {von:"08:00", bis:"16:30", pause:30}, "2": {von:"08:00", bis:"16:30", pause:30},
    "3": {von:"08:00", bis:"16:30", pause:30}, "4": {von:"08:00", bis:"16:30", pause:30},
    "5": {von:"08:00", bis:"16:30", pause:30}, "6": null, "7": null,
  },
  startsaldo: 0, startdatum: "", urlaubstage: 0,
});

const STANDARD = () => ({
  jobs: [STANDARD_JOB()],
  aktiverJob: "standard",
  notizvorlagen: [],
  soll: STANDARD_JOB().soll,
  standardzeiten: STANDARD_JOB().standardzeiten,
  sondertage: "keine",
  zeitzone: "Europe/Vienna",
  rundung: 0,
  rundungsmodus: "kaufmaennisch",
  // Jede Dienstart beschreibt einen festen Wochenrhythmus. "durchgehend" läuft
  // ohne Unterbrechung von starttag/startzeit bis endtag/endzeit, "taeglich"
  // gilt an jedem Tag der Spanne zwischen den beiden Uhrzeiten. Die Dauer ist
  // eine Zeitpauschale und zählt nie als Arbeitszeit; "pauschale" ist nur noch
  // Rückfallwert je Tag für Dienstarten ohne Rhythmus.
  dienstarten: [
    {id:"dienst-1", name:"1. Dienst", modus:"durchgehend",
     starttag:1, startzeit:"07:00", endtag:1, endzeit:"07:00",
     pauschale:0, farbe:"#b45309"},
    {id:"dienst-2", name:"2. Dienst", modus:"taeglich",
     starttag:1, startzeit:"07:00", endtag:6, endzeit:"20:00",
     pauschale:0, farbe:"#0f766e"},
    {id:"dienst-3", name:"3. Dienst", modus:"taeglich",
     starttag:5, startzeit:"07:00", endtag:6, endzeit:"20:00",
     pauschale:0, farbe:"#6d28d9"},
  ],
  startsaldo: 0, startdatum: "", name: "",
});

// Ergaenzt fehlende Felder eines Jobs und prueft die Werte - Gegenstueck zu app.py
function normiereJob(roh, nummer = 0){
  const vorlage = STANDARD_JOB();
  const job = {...vorlage};
  // Eine bereits vergebene Kennung bleibt unveraendert, sonst verlieren die
  // Eintraege beim naechsten Laden ihre Zuordnung.
  const vorhandene = String(roh.id || "");
  job.id = /^[a-z0-9-]{1,40}$/.test(vorhandene) ? vorhandene
         : slugify(roh.name || `job-${nummer + 1}`);
  job.name = String(roh.name || vorlage.name).slice(0, 60);
  job.farbe = /^#[0-9a-fA-F]{6}$/.test(roh.farbe || "") ? roh.farbe : vorlage.farbe;

  const soll = {};
  for (let d = 1; d <= 7; d++){
    const zahl = Number((roh.soll || {})[String(d)] ?? vorlage.soll[String(d)]);
    if (!isFinite(zahl))
      throw new Fehler(`Sollstunden für ${WOCHENTAGE[d-1]} in Job „${job.name}" sind keine Zahl.`);
    soll[String(d)] = Math.max(0, Math.min(24, zahl));
  }
  job.soll = soll;

  const std = {};
  for (let d = 1; d <= 7; d++){
    const e = (roh.standardzeiten || {})[String(d)];
    if (!e || !e.von || !e.bis){ std[String(d)] = null; continue; }
    const pause = Math.trunc(Number(e.pause) || 0);
    if (pause < 0 || dauerMinuten(e.von, e.bis, pause) <= 0)
      throw new Fehler(`Standardzeit für ${WOCHENTAGE[d-1]} in Job „${job.name}" ergibt keine Arbeitszeit.`);
    std[String(d)] = {von: e.von, bis: e.bis, pause};
  }
  job.standardzeiten = std;

  const saldo = Number(roh.startsaldo || 0);
  if (!isFinite(saldo)) throw new Fehler(`Startsaldo in Job „${job.name}" ist keine Zahl.`);
  job.startsaldo = saldo;
  const sd = String(roh.startdatum || "").trim();
  if (sd && !DATE_RE.test(sd))
    throw new Fehler(`Startdatum in Job „${job.name}" muss JJJJ-MM-TT sein.`);
  job.startdatum = sd;
  const urlaub = Number(roh.urlaubstage || 0);
  if (!isFinite(urlaub) || urlaub < 0)
    throw new Fehler(`Urlaubsanspruch in Job „${job.name}" ist keine Zahl.`);
  job.urlaubstage = urlaub;
  return job;
}

// Einstellungen aus Sicht eines bestimmten Jobs
function jobSicht(settings, jobId){
  const job = (settings.jobs || []).find(j => j.id === jobId);
  if (!job) throw new Fehler(`Unbekannter Job „${jobId}".`);
  return {...settings, soll: job.soll, standardzeiten: job.standardzeiten,
          startsaldo: job.startsaldo, startdatum: job.startdatum,
          urlaubstage: job.urlaubstage || 0};
}

// Eintraege ohne Jobangabe gehoeren zum ersten Job
const jobVon = (e, standardJob) => e.job || standardJob;

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
      if (!d.objectStoreNames.contains("laufend"))
        d.createObjectStore("laufend");
      if (!d.objectStoreNames.contains("sicherungen"))
        d.createObjectStore("sicherungen", {keyPath:"id", autoIncrement:true});
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
  // Einmalig: die früher ausgelieferte einzelne "Notdienstwoche" wird durch die
  // drei Dienste ersetzt. Der Merker verhindert, dass eine später bewusst wieder
  // so angelegte Dienstart erneut ersetzt wird.
  if (!gespeichert?.dienstartenMigriert){
    data.dienstarten = migriereDienstarten(data.dienstarten);
    await tx(["einstellungen"], "readwrite", t => {
      t.objectStore("einstellungen").put({...(gespeichert || {}), dienstartenMigriert: true,
                                          dienstarten: data.dienstarten}, "alle");
    });
  }
  delete data.dienstartenMigriert;
  if (!Array.isArray(data.notizvorlagen)) data.notizvorlagen = [];
  data.notizvorlagen = data.notizvorlagen.map(n => String(n).slice(0, 200)).filter(n => n.trim());

  // Wie in app.py: nur was wirklich gespeichert wurde zaehlt, sonst verdeckt
  // die Vorbelegung die alten Sollzeiten.
  let jobs = gespeichert?.jobs;
  if (!Array.isArray(jobs) || !jobs.length){
    jobs = [{...STANDARD_JOB(), soll: data.soll, standardzeiten: data.standardzeiten,
             startsaldo: data.startsaldo, startdatum: data.startdatum,
             name: data.name || STANDARD_JOB().name}];
  }
  const vergebeneKennungen = new Set();
  data.jobs = jobs.filter(j => j && typeof j === "object").map((j, i) => {
    const fertig = normiereJob(j, i);
    let grund = fertig.id.slice(0, 37), nummer = 2;
    while (vergebeneKennungen.has(fertig.id)) fertig.id = `${grund}-${nummer++}`;
    vergebeneKennungen.add(fertig.id);
    return fertig;
  });
  if (!data.jobs.length) data.jobs = [STANDARD_JOB()];
  const kennungen = data.jobs.map(j => j.id);
  if (!kennungen.includes(data.aktiverJob)) data.aktiverJob = kennungen[0];

  const aktiv = data.jobs.find(j => j.id === data.aktiverJob);
  for (const feld of ["soll", "standardzeiten", "startsaldo", "startdatum", "urlaubstage"])
    data[feld] = JSON.parse(JSON.stringify(aktiv[feld] ?? 0));
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

  if ("jobs" in patch){
    if (!Array.isArray(patch.jobs) || !patch.jobs.length)
      throw new Fehler("Es muss mindestens ein Job vorhanden sein.");
    const jobs = [], vergeben = new Set();
    patch.jobs.forEach((roh, i) => {
      if (!roh || typeof roh !== "object") throw new Fehler("Jeder Job muss ein Objekt sein.");
      const job = normiereJob(roh, i);
      let grund = job.id.slice(0, 37), nummer = 2;
      while (vergeben.has(job.id)) job.id = `${grund}-${nummer++}`;
      vergeben.add(job.id); jobs.push(job);
    });
    current.jobs = jobs;
    if (!vergeben.has(current.aktiverJob)) current.aktiverJob = jobs[0].id;
  }
  if ("aktiverJob" in patch){
    const kennung = String(patch.aktiverJob || "");
    if (!current.jobs.some(j => j.id === kennung))
      throw new Fehler(`Unbekannter Job „${kennung}".`);
    current.aktiverJob = kennung;
  }
  if ("notizvorlagen" in patch){
    if (!Array.isArray(patch.notizvorlagen))
      throw new Fehler("Notizvorlagen müssen eine Liste sein.");
    current.notizvorlagen = patch.notizvorlagen
      .map(n => String(n).trim().slice(0, 200)).filter(Boolean).slice(0, 50);
  }

  const zielId = (patch.job && patch.job !== "alle") ? patch.job : current.aktiverJob;
  // Ein ausdruecklich genannter, aber unbekannter Job ist ein Fehler
  if (patch.job && patch.job !== "alle" && !current.jobs.some(j => j.id === patch.job)
      && ["soll","standardzeiten","startsaldo","startdatum","urlaubstage"].some(f => f in patch))
    throw new Fehler(`Unbekannter Job „${patch.job}".`);
  const ziel = current.jobs.find(j => j.id === zielId)
             || current.jobs.find(j => j.id === current.aktiverJob);

  if ("soll" in patch){
    if (patch.soll && typeof patch.soll !== "object") throw new Fehler("Sollstunden sind ungültig.");
    const soll = {};
    for (let d = 1; d <= 7; d++){
      const roh = patch.soll?.[String(d)] ?? current.soll[String(d)];
      const zahl = Number(roh);
      if (!isFinite(zahl)) throw new Fehler(`Sollstunden für ${WOCHENTAGE[d-1]} sind keine Zahl.`);
      soll[String(d)] = Math.max(0, Math.min(24, zahl));
    }
    ziel.soll = soll;
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
    ziel.standardzeiten = std;
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
        for (const [feld, wert] of [["Startzeit", roh.startzeit], ["Endzeit", roh.endzeit]]){
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
  if ("zeitzone" in patch){
    const zone = String(patch.zeitzone || "").trim() || "Europe/Vienna";
    try { new Intl.DateTimeFormat("en-US", {timeZone: zone}); }
    catch(e){ throw new Fehler(`Unbekannte Zeitzone „${zone}".`); }
    current.zeitzone = zone;
  }
  if ("rundung" in patch){
    const schritt = Math.trunc(Number(patch.rundung || 0));
    if (![0,1,5,6,10,15,30,60].includes(schritt))
      throw new Fehler("Rundung muss 0, 5, 10, 15, 30 oder 60 Minuten sein.");
    current.rundung = schritt;
  }
  if ("rundungsmodus" in patch){
    const modus = String(patch.rundungsmodus || "kaufmaennisch").toLowerCase();
    if (!["kaufmaennisch","auf","ab"].includes(modus))
      throw new Fehler("Rundungsrichtung muss „zur nächsten Stufe“, „auf“ oder „ab“ sein.");
    current.rundungsmodus = modus;
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
    ziel.startsaldo = zahl;
  }
  if ("startdatum" in patch){
    const sd = String(patch.startdatum || "").trim();
    if (sd && !DATE_RE.test(sd)) throw new Fehler("Startdatum muss im Format JJJJ-MM-TT sein.");
    ziel.startdatum = sd;
  }
  if ("name" in patch) current.name = String(patch.name || "").slice(0, 80);

  const aktiv = current.jobs.find(j => j.id === current.aktiverJob);
  for (const feld of ["soll", "standardzeiten", "startsaldo", "startdatum"])
    current[feld] = JSON.parse(JSON.stringify(aktiv[feld]));

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

function dauerMinuten(von, bis, pause, datum, zone){
  const start = parseZeit(von);
  let ende = parseZeit(bis);
  if (ende === start) throw new Fehler("'Von' und 'Bis' dürfen nicht gleich sein.");
  const spanne = ende > start ? ende - start : ende - start + 24 * 60;
  return spanne + sommerzeitVersatz(datum, von, bis, zone) - Math.trunc(pause || 0);
}

// Wie weit die Ortszeit an einem Zeitpunkt von UTC abweicht, in Minuten
function zonenVersatz(zone, jahr, monat, tag, stunde, minute){
  const alsUTC = Date.UTC(jahr, monat - 1, tag, stunde, minute);
  const teile = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone: zone, hour12: false, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(new Date(alsUTC)).map(t => [t.type, t.value]));
  const abgelesen = Date.UTC(+teile.year, teile.month - 1, +teile.day,
                             (+teile.hour) % 24, +teile.minute, +teile.second);
  return (abgelesen - alsUTC) / 60000;
}

// Differenz zwischen echter und abgelesener Zeitspanne (Sommerzeitumstellung)
function sommerzeitVersatz(datum, von, bis, zone){
  if (!datum || !zone) return 0;
  try {
    const [j, m, t] = datum.split("-").map(Number);
    const [sh, sm] = von.split(":").map(Number);
    const [eh, em] = bis.split(":").map(Number);
    const ueberNacht = parseZeit(bis) <= parseZeit(von);
    const ende = new Date(Date.UTC(j, m - 1, t + (ueberNacht ? 1 : 0)));
    const vorher = zonenVersatz(zone, j, m, t, sh, sm);
    const nachher = zonenVersatz(zone, ende.getUTCFullYear(), ende.getUTCMonth() + 1,
                                 ende.getUTCDate(), eh, em);
    return Math.round(vorher - nachher);
  } catch(e){ return 0; }
}

// Rundet eine Dauer auf volle Minutenschritte
function rundeMinuten(minuten, schritt, modus = "kaufmaennisch"){
  schritt = Math.trunc(schritt || 0);
  if (schritt <= 1) return minuten;
  const rest = ((minuten % schritt) + schritt) % schritt;
  if (rest === 0) return minuten;
  if (modus === "auf") return minuten + (schritt - rest);
  if (modus === "ab") return minuten - rest;
  return rest * 2 < schritt ? minuten - rest : minuten + (schritt - rest);
}

const tagAus = iso => new Date(iso + "T00:00:00");
const isoWochentag = iso => ((tagAus(iso).getDay() + 6) % 7) + 1;
function isoVon(d){
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function plusTage(iso, n){ const d = tagAus(iso); d.setDate(d.getDate() + n); return isoVon(d); }
function heuteIso(){ return isoVon(new Date()); }

// Frühere Fassungen lieferten genau eine Dienstart "Notdienstwoche" mit
// 120 Minuten je Tag aus. Steht die unverändert im Gerät, wird sie durch die
// drei Notdienste ersetzt; wer selbst etwas angelegt oder geändert hat, behält
// seine Liste.
const ALTE_DIENSTART = {id:"notdienstwoche", name:"Notdienstwoche", pauschale:120,
                        farbe:"#b45309"};
function migriereDienstarten(arten){
  if (!Array.isArray(arten) || arten.length !== 1) return arten;
  const a = arten[0], b = ALTE_DIENSTART;
  const gleich = Object.keys(b).length === Object.keys(a).length
    && Object.keys(b).every(k => a[k] === b[k]);
  return gleich ? STANDARD().dienstarten : arten;
}

// Beginn eines Dienstes: der letzte passende Wochentag, der nicht nach 'datum'
// liegt - wer mitten in der Woche anlegt, bekommt den laufenden Dienst.
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

// Wie viel Zeit ein Zeitausgleichstag abbaut - nur für die Anzeige. Ohne eigene
// Angabe die Sollzeit des Wochentags, sonst der Betrag der Gutschrift.
function abgebauteZeit(eintrag, sollMap){
  if (eintrag.gutschrift != null) return Math.abs(Math.trunc(eintrag.gutschrift));
  return Math.round((sollMap[isoWochentag(eintrag.datum)] || 0) * 60);
}

// Beginn der Saldorechnung: der Monatserste des ersten erfassten Tages.
// Früher zählte der erste Tag mit Arbeitszeit - Urlaub oder Krankenstand davor
// fielen damit aus dem Saldo und aus den Zählern der Übersicht.
function saldoBeginn(daten){
  if (!daten || !daten.length) return "9999-12-31";
  return daten.slice().sort()[0].slice(0, 8) + "01";
}

// Minuten, die ein einzelner Diensttag beiträgt. Bei einer Dienstart mit
// Wochenrhythmus der Anteil genau dieses Datums; liegt es außerhalb, der
// längste Tag der Dienstart. Früher stand hier das Feld "pauschale", das bei
// Diensten mit Rhythmus 0 ist - ein von Hand angelegter Diensttag wurde damit
// stillschweigend mit 0:00 gebucht.
function tagesanteil(art, datum){
  if (!art.modus) return Math.trunc(Number(art.pauschale) || 0);
  const plan = Object.fromEntries(dienstTage(art, datum));
  if (plan[datum]) return plan[datum];
  const werte = Object.values(plan);
  return werte.length ? Math.max(...werte) : Math.trunc(Number(art.pauschale) || 0);
}

// Gesamte Zeitpauschale einer Dienstart in Minuten. Das Ergebnis hängt nur an
// der Definition, das Bezugsdatum ist beliebig.
function dienstPauschale(art){
  return dienstTage(art, "2024-01-01").reduce((s, [, m]) => s + m, 0);
}

// Einstellungen für die Anzeige: jede Dienstart bekommt ihre Gesamtdauer und
// die Zahl der Kalendertage.
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
    if (Math.abs(gutschrift) > 1440)
      throw new Fehler("Die Gutschrift kann höchstens 24 Stunden betragen.");
  }

  let dienstart = String(roh.dienstart || "").trim();
  if (typ === "dienst"){
    if (!dienstarten) dienstart = dienstart ? slugify(dienstart) : "";
    else {
      if (!dienstart) throw new Fehler("Bitte eine Dienstart wählen.");
      if (!dienstarten[dienstart])
        throw new Fehler(`Unbekannte Dienstart '${dienstart}'. Erst in den Einstellungen anlegen.`);
      if (gutschrift === null) gutschrift = tagesanteil(dienstarten[dienstart], datum);
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

  return {job: String(roh.job || "").trim().slice(0, 40),
          datum, typ, von, bis, pause,
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
  const zone = settings.zeitzone || null;
  const schritt = Math.trunc(settings.rundung || 0);
  const modus = settings.rundungsmodus || "kaufmaennisch";
  const arbeitsminuten = e =>
    rundeMinuten(dauerMinuten(e.von, e.bis, e.pause, e.datum, zone), schritt, modus);
  const start = settings.startdatum || "";

  const tage = {};
  for (const e of entries){
    const t = tage[e.datum] || (tage[e.datum] =
      {ist:0, gutschrift:0, pauschale:0, ausfahrt:0, typen:[], eintraege:[]});
    let minuten = 0;
    if (e.typ === "arbeit"){
      minuten = arbeitsminuten(e); t.ist += minuten;
    } else if (e.typ === "dienst"){
      // Die Zeitpauschale wird gesondert verrechnet und bleibt aus Ist,
      // Saldo und Überstunden heraus.
      minuten = Math.trunc(e.gutschrift || 0); t.pauschale += minuten;
    } else if (e.typ === "ausfahrt"){
      minuten = arbeitsminuten(e); t.ausfahrt += minuten;
    } else if (e.typ === "gleitzeit"){
      // Zeitausgleich baut Plusstunden ab: kein Ausgleich des Tagessolls. Nur
      // eine ausdrückliche Gutschrift zählt (abgebuchte Stunden aus dem Import).
      t.gutschrift += e.gutschrift != null ? Math.trunc(e.gutschrift) : 0;
      // Angezeigt wird, wie viel Zeit der Tag abbaut - sonst stünde in der Liste
      // eine 0:00, obwohl der Saldo um das Tagessoll fällt.
      minuten = abgebauteZeit(e, sollMap);
    } else if (e.gutschrift != null){
      minuten = Math.trunc(e.gutschrift); t.gutschrift += minuten;
    } else if (e.von && e.bis){
      minuten = dauerMinuten(e.von, e.bis, e.pause, e.datum, zone); t.gutschrift += minuten;
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
    if (d > heute){
      // Ein kuenftiger Tag zaehlt nur, wenn dort etwas steht, das ihn abdeckt.
      // Eine vorab eingetragene Dienstwoche bringt nur ihre Pauschale.
      const eintrag = tage[d];
      if (!eintrag || eintrag.typen.every(t => SEPARATE_TYPES.includes(t))) continue;
    }
    sollGesamt += Math.round(sollMap[isoWochentag(d)] * 60);
  }

  let ist = 0, gut = 0, pauschaleGesamt = 0, ausfahrtGesamt = 0;
  for (const [d, t] of Object.entries(tage)) if (zaehlt(d)){
    ist += t.ist; gut += t.gutschrift;
    pauschaleGesamt += t.pauschale; ausfahrtGesamt += t.ausfahrt;
  }

  const projekte = {};
  for (const e of entries){
    if (e.typ !== "arbeit" || !zaehlt(e.datum)) continue;
    const p = e.projekt || "(ohne Projekt)";
    projekte[p] = (projekte[p] || 0) + arbeitsminuten(e);
  }

  // Kennzahlen je Art: Anzahl Tage und Minuten
  const arten = {};
  for (const t of Object.values(tage))
    for (const e of t.eintraege){
      if (!zaehlt(e.datum)) continue;
      const a = arten[e.typ] || (arten[e.typ] = {tage: new Set(), minuten: 0});
      a.tage.add(e.datum); a.minuten += e.minuten;
    }
  for (const k of Object.keys(arten))
    arten[k] = {tage: arten[k].tage.size, minuten: arten[k].minuten};

  const namen = {};
  for (const a of (settings.dienstarten || [])) namen[a.id] = a.name;
  // Welcher Dienst läuft an welchem Tag? Damit bekommt jede Ausfahrt ihren
  // Dienst, ohne dass er am Eintrag mitgeführt werden muss.
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
    const minuten = arbeitsminuten(e);
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

  // Urlaubskonto: die Jahreszahlen liefert auswertung() nach, weil dort alle
  // Eintraege des Jahres vorliegen - hier zaehlt nur der uebergebene Ausschnitt.
  const anspruch = Number(settings.urlaubstage || 0);
  const jahr = bis.slice(0, 4);
  let verbraucht = 0;
  for (const e of entries){
    if (e.typ !== "urlaub" || !e.datum.startsWith(jahr)) continue;
    const tagessoll = sollMap[isoWochentag(e.datum)] * 60;
    if (e.gutschrift != null && tagessoll > 0)
      verbraucht += Math.min(1, Math.max(0, e.gutschrift / tagessoll));
    else if (e.von && e.bis && tagessoll > 0)
      verbraucht += Math.min(1, dauerMinuten(e.von, e.bis, e.pause, e.datum, zone) / tagessoll);
    else if (tagessoll > 0) verbraucht += 1;
    // An Tagen ohne Sollzeit wird kein Urlaub verbraucht
  }
  verbraucht = Math.round(verbraucht * 2) / 2;

  return {
    von, bis, arten, ist, gutschrift: gut, erfasst: ist + gut, soll: sollGesamt,
    // Beides wird gesondert verrechnet und ist in 'erfasst' und 'saldo'
    // bewusst nicht enthalten.
    pauschale: pauschaleGesamt, ausfahrt: ausfahrtGesamt, ausfahrten,
    urlaub: {jahr: Number(jahr), anspruch, verbraucht,
             rest: Math.round((anspruch - verbraucht) * 2) / 2, gefuehrt: anspruch > 0},
    saldo: ist + gut - sollGesamt, tage: tagesliste,
    dienste: Object.entries(dienste).sort((a,b) => b[1].minuten - a[1].minuten)
      .map(([k, v]) => ({id:k, name: namen[k] || k || "Dienst", ...v})),
    projekte: Object.entries(projekte).sort((a,b) => b[1] - a[1])
      .map(([k, v]) => ({projekt:k, minuten:v})),
  };
}

async function alleEintraege(von, bis, job){
  const alle = await tx(["eintraege"], "readonly", t => anfrage(t.objectStore("eintraege").getAll()));
  return alle
    .filter(e => (!von || e.datum >= von) && (!bis || e.datum <= bis))
    .filter(e => !job || e.job === job)
    .sort((a, b) => a.datum.localeCompare(b.datum) || (a.von || "").localeCompare(b.von || "")
                    || a.id - b.id);
}

async function gesamtsaldo(job){
  const settings = await getSettings();
  const standardJob = settings.jobs[0].id;
  const sicht = job ? jobSicht(settings, job) : settings;
  const alle = await alleEintraege();
  const entries = job ? alle.filter(e => jobVon(e, standardJob) === job) : alle;
  const startsaldo = Math.round(Number(sicht.startsaldo || 0) * 60);
  if (!entries.length) return startsaldo;
  const s = {...sicht, startdatum: sicht.startdatum || saldoBeginn(entries.map(e => e.datum))};
  const von = [s.startdatum, entries[0].datum].sort()[0];
  const bis = [entries[entries.length-1].datum, heuteIso()].sort().pop();
  return berechne(entries, s, von, bis).saldo + startsaldo;
}

async function wirksameEinstellungen(){
  const settings = await getSettings();
  if (!settings.startdatum){
    const entries = await alleEintraege();
    settings.startdatum = saldoBeginn(entries.map(e => e.datum));
  }
  return settings;
}

// ------------------------------------------------------------- Stempeluhr
const jetztZeit = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
};
const minutenSeit = (datum, zeit) =>
  Math.max(0, Math.floor((Date.now() - tagAus(datum).getTime()
    - (Number(zeit.slice(0,2)) * 60 + Number(zeit.slice(3))) * 60000) / 60000));

async function stempelLesen(){
  const lauf = await tx(["laufend"], "readonly", t => anfrage(t.objectStore("laufend").get("aktuell")));
  if (!lauf) return {laufend: null};
  let pause = Math.trunc(lauf.pause || 0);
  if (lauf.pause_ab){
    // Aeltere Eintraege enthalten nur die Uhrzeit; dann gilt der Starttag.
    const [tag, zeit] = lauf.pause_ab.includes(" ") ? lauf.pause_ab.split(" ")
                                                    : [lauf.datum, lauf.pause_ab];
    pause += minutenSeit(tag, zeit);
  }
  const brutto = minutenSeit(lauf.datum, lauf.von);
  return {laufend: {...lauf, pause_gesamt: pause, brutto, netto: Math.max(0, brutto - pause),
                    pausiert: !!lauf.pause_ab, beginn: `${lauf.datum} ${lauf.von}`}};
}

async function stempelStart(job = "", projekt = "", notiz = ""){
  if ((await stempelLesen()).laufend) throw new Fehler("Es läuft bereits eine Zeitmessung.");
  const lauf = {datum: heuteIso(), von: jetztZeit(), pause: 0, pause_ab: null,
                projekt: String(projekt || "").slice(0, 80),
                notiz: String(notiz || "").slice(0, 500), job: String(job || "").slice(0, 40)};
  await tx(["laufend"], "readwrite", t => anfrage(t.objectStore("laufend").put(lauf, "aktuell")));
  return stempelLesen();
}

async function stempelPause(){
  const z = (await stempelLesen()).laufend;
  if (!z) throw new Fehler("Es läuft keine Zeitmessung.");
  const neu = z.pause_ab ? {...z, pause: z.pause_gesamt, pause_ab: null}
                         : {...z, pause_ab: `${heuteIso()} ${jetztZeit()}`};
  delete neu.pause_gesamt; delete neu.brutto; delete neu.netto; delete neu.pausiert;
  delete neu.beginn;
  await tx(["laufend"], "readwrite", t => anfrage(t.objectStore("laufend").put(neu, "aktuell")));
  return stempelLesen();
}

async function stempelStop(verwerfen = false){
  const z = (await stempelLesen()).laufend;
  if (!z) throw new Fehler("Es läuft keine Zeitmessung.");
  if (verwerfen){
    await tx(["laufend"], "readwrite", t => anfrage(t.objectStore("laufend").delete("aktuell")));
    return {verworfen: true};
  }
  if (z.brutto < 1)
    throw new Fehler("Die Zeitmessung läuft erst seit weniger als einer Minute. "
                   + "Zum Abbrechen „Verwerfen“ benutzen.");
  if (z.brutto >= 24 * 60)
    throw new Fehler(`Die Zeitmessung läuft seit mehr als 24 Stunden (Beginn ${z.beginn}). `
      + "So ein Eintrag lässt sich nicht automatisch buchen - bitte den Tag von Hand erfassen "
      + "und die Messung verwerfen.");
  if (z.netto <= 0) throw new Fehler("Die Pause ist so lang wie die gesamte Zeitmessung.");

  const settings = await getSettings();
  const arten = Object.fromEntries((settings.dienstarten || []).map(a => [a.id, a]));
  const eintrag = pruefeEintrag({datum: z.datum, typ: "arbeit", von: z.von, bis: jetztZeit(),
                                 pause: z.pause_gesamt, projekt: z.projekt, notiz: z.notiz,
                                 job: z.job}, arten);
  const id = await tx(["eintraege"], "readwrite",
    t => anfrage(t.objectStore("eintraege").add(eintrag)));
  await tx(["laufend"], "readwrite", t => anfrage(t.objectStore("laufend").delete("aktuell")));
  return {eintrag: {...eintrag, id}};
}

// ------------------------------------------------------------------- API
async function auswertung(von, bis, job){
  if (!DATE_RE.test(von) || !DATE_RE.test(bis))
    throw new Fehler("Zeitraum bitte als JJJJ-MM-TT angeben.");
  if (bis < von) throw new Fehler("Das Ende des Zeitraums liegt vor dem Anfang.");
  const settings = await getSettings();
  const standardJob = settings.jobs[0].id;
  const alleKennungen = settings.jobs.map(j => j.id);
  let kennungen;
  if (!job || job === "alle") kennungen = alleKennungen;
  else {
    if (!alleKennungen.includes(job)) throw new Fehler(`Unbekannter Job „${job}".`);
    kennungen = [job];
  }

  const imZeitraum = await alleEintraege(von, bis);
  const gesamt = await alleEintraege();
  const teile = kennungen.map(kennung => {
    const sicht = jobSicht(settings, kennung);
    if (!sicht.startdatum){
      sicht.startdatum = saldoBeginn(gesamt.filter(e => jobVon(e, standardJob) === kennung)
                                           .map(e => e.datum));
    }
    const eigene = imZeitraum.filter(e => jobVon(e, standardJob) === kennung);
    const ergebnis = berechne(eigene, sicht, von, bis);
    // Der Urlaubsanspruch gilt fuers Jahr - dafuer alle Urlaubstage des Jahres
    const jahr = bis.slice(0, 4);
    const imJahr = gesamt.filter(e => jobVon(e, standardJob) === kennung
                                 && e.datum.startsWith(jahr));
    ergebnis.urlaub = berechne(imJahr, sicht, `${jahr}-01-01`, `${jahr}-12-31`).urlaub;
    ergebnis._daten = {};
    for (const e of eigene){
      if (sicht.startdatum && e.datum < sicht.startdatum) continue;
      (ergebnis._daten[e.typ] || (ergebnis._daten[e.typ] = new Set())).add(e.datum);
    }
    return ergebnis;
  });

  let res;
  if (teile.length === 1){ res = teile[0]; delete res._daten; }
  else {
    res = {von, bis, tage: [], projekte: [], dienste: [], ausfahrten: [], arten: {},
           urlaub: {jahr: Number(bis.slice(0, 4)),
                    anspruch: teile.reduce((s2, t) => s2 + t.urlaub.anspruch, 0),
                    verbraucht: teile.reduce((s2, t) => s2 + t.urlaub.verbraucht, 0),
                    rest: teile.reduce((s2, t) => s2 + t.urlaub.rest, 0),
                    gefuehrt: teile.some(t => t.urlaub.gefuehrt)}};
    for (const feld of ["ist", "gutschrift", "erfasst", "soll", "saldo",
                        "pauschale", "ausfahrt"])
      res[feld] = teile.reduce((sum, t) => sum + t[feld], 0);
    for (const teil of teile){
      res.tage.push(...teil.tage);
      res.ausfahrten.push(...teil.ausfahrten);
      for (const [k, v] of Object.entries(teil.arten)){
        const z = res.arten[k] || (res.arten[k] = {tage: 0, minuten: 0});
        z.minuten += v.minuten;
      }
      for (const [name, feld] of [["projekte","projekt"], ["dienste","id"]])
        for (const eintrag of teil[name]){
          const treffer = res[name].find(x => x[feld] === eintrag[feld]);
          if (treffer){
            for (const z of ["minuten","tage","ausfahrten","ausfahrt_minuten"])
              if (z in eintrag) treffer[z] += eintrag[z];
          }
          else res[name].push({...eintrag});
        }
    }
    // Ein Kalendertag zaehlt nur einmal, auch wenn zwei Jobs darauf gebucht sind
    const gesammelt = {};
    for (const teil of teile)
      for (const [typ, daten] of Object.entries(teil._daten || {})){
        if (!gesammelt[typ]) gesammelt[typ] = new Set();
        for (const d of daten) gesammelt[typ].add(d);
      }
    for (const [typ, daten] of Object.entries(gesammelt)){
      const z = res.arten[typ] || (res.arten[typ] = {tage: 0, minuten: 0});
      z.tage = daten.size;
    }
    res.tage.sort((a,b) => a.datum.localeCompare(b.datum));
    res.projekte.sort((a,b) => b.minuten - a.minuten);
    res.dienste.sort((a,b) => b.minuten - a.minuten);
    res.ausfahrten.sort((a,b) => a.datum.localeCompare(b.datum) || a.von.localeCompare(b.von));
  }
  res.job = job || "alle";
  res.gesamtsaldo = 0;
  for (const k of kennungen) res.gesamtsaldo += await gesamtsaldo(k);
  return res;
}

async function feiertagsUebersicht(jahr, job){
  let settings = await getSettings();
  if (!job || job === "alle") job = settings.aktiverJob;
  if (job) settings = jobSicht(settings, job);
  const standardJob = (await getSettings()).jobs[0].id;
  const vorhanden = new Set((await alleEintraege(`${jahr}-01-01`, `${jahr}-12-31`))
    .filter(e => !job || jobVon(e, standardJob) === job).map(e => e.datum));
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

async function feiertageEintragen(jahr, job){
  const settings = await getSettings();
  if (!job || job === "alle") job = settings.aktiverJob;
  const uebersicht = await feiertagsUebersicht(jahr, job);
  const neu = [], geplant = new Set();
  let uebersprungen = 0;
  for (const f of uebersicht.feiertage){
    if (geplant.has(f.datum) || !f.arbeitstag || f.erfasst){ uebersprungen++; continue; }
    neu.push({datum: f.datum, typ: "feiertag", von: "", bis: "", pause: 0, projekt: "",
              notiz: f.name, gutschrift: f.anteil < 1 ? f.gutschrift : null, dienstart: "",
              job});
    geplant.add(f.datum);
  }
  await anlegen(neu);
  return {jahr, angelegt: neu.length, uebersprungen, tage: neu};
}

// Hat die Dienstart einen Wochenrhythmus, ergeben sich Anfang, Ende und die
// Minuten je Tag aus ihrer Definition; 'bis' wird dann nicht gebraucht.
async function dienstEintragen(dienstart, von, bis, gutschrift, job){
  const settings = await getSettings();
  if (!job || job === "alle") job = settings.aktiverJob;
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
    const fest = gutschrift == null ? (Math.trunc(art.pauschale) || 0) : Math.trunc(gutschrift);
    plan = [];
    for (let d = von; d <= ende; d = plusTage(d, 1)) plan.push([d, fest]);
    if (plan.length > 367) throw new Fehler("Ein Dienstzeitraum darf höchstens ein Jahr umfassen.");
  }

  const erster = plan[0][0], letzter = plan[plan.length - 1][0];
  const standardJob = settings.jobs[0].id;
  const vorhanden = new Set((await alleEintraege(erster, letzter))
    .filter(e => e.typ === "dienst" && e.dienstart === dienstart
                 && jobVon(e, standardJob) === job).map(e => e.datum));
  const neu = plan.filter(([d]) => !vorhanden.has(d)).map(([d, minuten]) => pruefeEintrag(
    {datum: d, typ: "dienst", dienstart, job, gutschrift: minuten, notiz: art.name}, arten));
  await anlegen(neu);
  return {dienstart, name: art.name, angelegt: neu.length,
          von: erster, bis: letzter,
          uebersprungen: plan.length - neu.length,
          minuten: neu.reduce((s, e) => s + (e.gutschrift || 0), 0),
          pauschale: plan.reduce((s, [, m]) => s + m, 0)};
}

async function auffuellen(von, bis, job){
  let settings = await getSettings();
  if (!job || job === "alle") job = settings.aktiverJob;
  const standardJob = settings.jobs[0].id;
  settings = jobSicht(settings, job);
  const bisEcht = [bis, heuteIso()].sort()[0];
  const belegt = new Set((await alleEintraege(von, bis))
    .filter(e => !SEPARATE_TYPES.includes(e.typ) && jobVon(e, standardJob) === job)
    .map(e => e.datum));
  const feiertage = new Set();
  for (let j = Number(von.slice(0,4)); j <= Number(bisEcht.slice(0,4)); j++)
    for (const f of feiertageAT(j, settings.sondertage)) feiertage.add(f.datum);

  const neu = [], uebersprungen = {belegt:0, feiertag:0, kein_arbeitstag:0,
                                   ohne_standardzeit:0, vor_startdatum:0};
  for (let d = von; d <= bisEcht; d = plusTage(d, 1)){
    const wd = isoWochentag(d), vorlage = settings.standardzeiten[String(wd)];
    if (settings.startdatum && d < settings.startdatum){ uebersprungen.vor_startdatum++; continue; }
    else if (belegt.has(d)) uebersprungen.belegt++;
    else if (feiertage.has(d)) uebersprungen.feiertag++;
    else if (Number(settings.soll[String(wd)] || 0) <= 0) uebersprungen.kein_arbeitstag++;
    else if (!vorlage) uebersprungen.ohne_standardzeit++;
    else neu.push({datum: d, typ: "arbeit", von: vorlage.von, bis: vorlage.bis,
                   pause: Math.trunc(vorlage.pause || 0), projekt: "",
                   notiz: "automatisch aus Standardzeiten", gutschrift: null, dienstart: "",
                   job});
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
  // Wer eine Dienstart umbenennt oder löscht, hat weiterhin Einträge mit der
  // alten Kennung. Das darf das Zurückholen einer Sicherung nicht verhindern.
  for (const e of daten.eintraege){
    if (e && e.typ === "dienst"){
      const kennung = String(e.dienstart || "").trim();
      if (kennung && !arten[kennung]) arten[kennung] = {id: kennung, name: kennung, pauschale: 0};
    }
  }

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

function csvExport(entries, settings, jobs = [], job = null){
  const standardJob = jobs.length ? jobs[0].id : "";
  const namenJobs = Object.fromEntries(jobs.map(j => [j.id, j.name]));
  if (job && job !== "alle") entries = entries.filter(e => jobVon(e, standardJob) === job);
  const sollJeJob = Object.fromEntries(jobs.map(j => [j.id,
    Object.fromEntries(Object.entries(j.soll).map(([k, v]) => [Number(k), Number(v)]))]));
  const zone = settings.zeitzone || null;
  const schritt = Math.trunc(settings.rundung || 0);
  const modus = settings.rundungsmodus || "kaufmaennisch";
  const wtage = ["Mo","Di","Mi","Do","Fr","Sa","So"];
  const namen = Object.fromEntries((settings.dienstarten || []).map(a => [a.id, a.name]));
  const zeilen = [["Datum","Wochentag","Job","Art","Dienst","Von","Bis","Pause (Min)",
                   "Dauer (h)","Soll (h)","Verrechnung","Projekt","Notiz"]];
  // Ausfahrten führen ihren Dienst nicht mit - er ergibt sich aus dem Tag.
  const dienstAmTag = {};
  for (const e of entries) if (e.typ === "dienst") dienstAmTag[e.datum] = namen[e.dienstart] || "";
  const gesehen = new Set();
  for (const e of entries){
    const wd = isoWochentag(e.datum);
    let minuten;
    if (e.typ === "arbeit")
      minuten = rundeMinuten(dauerMinuten(e.von, e.bis, e.pause, e.datum, zone), schritt, modus);
    else if (e.typ === "dienst") minuten = Math.trunc(e.gutschrift || 0);
    else if (e.typ === "ausfahrt")
      minuten = rundeMinuten(dauerMinuten(e.von, e.bis, e.pause, e.datum, zone), schritt, modus);
    else if (e.typ === "gleitzeit")
      minuten = abgebauteZeit(e, {[wd]: Number(settings.soll[String(wd)] || 0)});
    else if (e.gutschrift != null) minuten = Math.trunc(e.gutschrift);
    else if (e.von && e.bis) minuten = dauerMinuten(e.von, e.bis, e.pause, e.datum, zone);
    else minuten = Math.round(Number(settings.soll[String(wd)] || 0) * 60);
    const soll = (sollJeJob[jobVon(e, standardJob)] || {})[wd]
      ?? Number(settings.soll[String(wd)] || 0);
    zeilen.push([e.datum, wtage[wd-1], namenJobs[jobVon(e, standardJob)] || "",
      TYP_NAMEN[e.typ] || (e.typ.charAt(0).toUpperCase() + e.typ.slice(1)),
      namen[e.dienstart] || (e.typ === "ausfahrt" ? (dienstAmTag[e.datum] || "") : ""),
      e.von, e.bis, e.pause,
      (minuten/60).toFixed(2).replace(".", ","),
      gesehen.has(e.datum) ? "" : soll.toFixed(2).replace(".", ","),
      SEPARATE_TYPES.includes(e.typ) ? "gesondert"
        : (e.typ === "gleitzeit" ? "Abbau" : "Arbeitszeit"),
      e.projekt, e.notiz]);
    gesehen.add(e.datum);
  }
  return "﻿" + zeilen.map(z => z.join(";")).join("\r\n") + "\r\n";
}

// Verteiler: bildet die Server-Endpunkte nach
// ------------------------------------------------------- Automatische Sicherung
// Browserdaten koennen verloren gehen. Darum liegen die letzten Staende
// zusaetzlich als eigene Kopien in der Datenbank - das rettet vor allem vor
// versehentlichem Ueberschreiben beim Import.
function zeitstempel(){
  const d = new Date(), z = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth()+1)}-${z(d.getDate())} ` +
         `${z(d.getHours())}:${z(d.getMinutes())}`;
}

async function sicherungenListe(){
  const alle = await tx(["sicherungen"], "readonly",
    t => anfrage(t.objectStore("sicherungen").getAll()));
  return alle.sort((a, b) => b.id - a.id).map(s => ({
    datei: String(s.id), zeit: s.zeit, grund: s.grund,
    eintraege: s.eintraege, groesse: s.groesse,
  }));
}

async function sicherungAnlegen(grund = "manuell", nurWennAelterAls = null){
  grund = ["manuell", "automatisch", "vorimport"].includes(grund) ? grund : "manuell";
  const vorhanden = await sicherungenListe();
  if (nurWennAelterAls && vorhanden.length){
    const letzte = new Date(vorhanden[0].zeit.replace(" ", "T") + ":00");
    if (!isNaN(letzte) && Date.now() - letzte.getTime() < nurWennAelterAls * 3600000)
      return {angelegt: false, sicherungen: vorhanden};
  }
  const daten = await exportDaten();
  const roh = JSON.stringify(daten);
  await tx(["sicherungen"], "readwrite", t => t.objectStore("sicherungen").add({
    zeit: zeitstempel(), grund, daten,
    eintraege: (daten.eintraege || []).length, groesse: roh.length,
  }));
  const jetzt = await sicherungenListe();
  const zuviel = jetzt.slice(SICHERUNG_MAX);
  if (zuviel.length)
    await tx(["sicherungen"], "readwrite",
      t => zuviel.forEach(s => t.objectStore("sicherungen").delete(Number(s.datei))));
  return {angelegt: true, sicherungen: await sicherungenListe()};
}

async function sicherungWiederherstellen(datei){
  const id = Number(datei);
  if (!Number.isInteger(id)) throw new Fehler("Diese Sicherung gibt es nicht.");
  const eintrag = await tx(["sicherungen"], "readonly",
    t => anfrage(t.objectStore("sicherungen").get(id)));
  if (!eintrag) throw new Fehler("Diese Sicherung gibt es nicht.");
  await sicherungAnlegen("vorimport");   // auch das Zurueckholen bleibt ruecknehmbar
  return importDaten(eintrag.daten, "ersetzen");
}

async function ruf(pfad, opts = {}){
  const [weg, abfrage] = pfad.split("?");
  const q = Object.fromEntries(new URLSearchParams(abfrage || ""));
  const methode = (opts.method || "GET").toUpperCase();
  const body = opts.body ? JSON.parse(opts.body) : {};
  const settings = await getSettings();
  const arten = Object.fromEntries((settings.dienstarten || []).map(a => [a.id, a]));
  const treffer = weg.match(/^\/api\/eintraege\/(\d+)$/);

  if (weg === "/api/eintraege" && methode === "GET") return alleEintraege(q.von, q.bis, q.job);
  if (weg === "/api/stempel" && methode === "GET") return stempelLesen();
  if (weg === "/api/stempel/start") return stempelStart(body.job, body.projekt, body.notiz);
  if (weg === "/api/stempel/pause") return stempelPause();
  if (weg === "/api/stempel/stop") return stempelStop(!!body.verwerfen);
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
    return auswertung(q.von || heuteIso().slice(0,8) + "01", q.bis || heuteIso(), q.job);
  if (weg === "/api/feiertage" && methode === "GET"){
    const jahr = Number(q.jahr || new Date().getFullYear());
    if (!Number.isInteger(jahr) || jahr < 1900 || jahr > 2200)
      throw new Fehler("Jahr bitte vierstellig zwischen 1900 und 2200 angeben.");
    return feiertagsUebersicht(jahr, q.job);
  }
  if (weg === "/api/feiertage" && methode === "POST"){
    const jahr = Number(body.jahr || new Date().getFullYear());
    if (!Number.isInteger(jahr) || jahr < 1900 || jahr > 2200)
      throw new Fehler("Jahr bitte zwischen 1900 und 2200 angeben.");
    return feiertageEintragen(jahr, body.job);
  }
  if (weg === "/api/dienste" && methode === "POST"){
    // Dienstarten mit Wochenrhythmus brauchen kein Ende - es ergibt sich aus
    // ihrer Definition.
    const von = String(body.von || "").trim(), bis = String(body.bis || "").trim();
    if (!DATE_RE.test(von)) throw new Fehler("Datum bitte als JJJJ-MM-TT angeben.");
    if (bis && !DATE_RE.test(bis)) throw new Fehler("Zeitraum bitte als JJJJ-MM-TT angeben.");
    if (bis && bis < von) throw new Fehler("Das Ende des Zeitraums liegt vor dem Anfang.");
    return dienstEintragen(String(body.dienstart || "").trim(), von, bis || null,
                           body.gutschrift, body.job);
  }
  if (weg === "/api/auffuellen" && methode === "POST"){
    const von = String(body.von || "").trim(), bis = String(body.bis || "").trim();
    if (!DATE_RE.test(von) || !DATE_RE.test(bis))
      throw new Fehler("Zeitraum bitte als JJJJ-MM-TT angeben.");
    if (bis < von) throw new Fehler("Das Ende des Zeitraums liegt vor dem Anfang.");
    return auffuellen(von, bis, body.job);
  }
  if (weg === "/api/sicherungen" && methode === "GET")
    return {sicherungen: await sicherungenListe(), ordner: ""};
  if (weg === "/api/sicherungen" && methode === "POST")
    return sicherungAnlegen(body.grund || "manuell",
                            body.nur_wenn_aelter_als ? Number(body.nur_wenn_aelter_als) : null);
  if (weg === "/api/sicherungen/wiederherstellen" && methode === "POST")
    return {ok: true, eintraege: (await sicherungWiederherstellen(body.datei)).importiert};
  if (weg === "/api/import" && methode === "POST"){
    const modus = body.modus || "ersetzen";
    // Vor dem Ersetzen den bisherigen Stand wegsichern
    if (modus === "ersetzen"){
      try { await sicherungAnlegen("vorimport"); }
      catch(e){ /* Sicherung darf den Import nicht blockieren */ }
    }
    return importDaten(body.daten || body, modus);
  }
  if (weg === "/api/export.json") return exportDaten();
  if (weg === "/api/export.csv")
    return csvExport(await alleEintraege(q.von, q.bis), settings, settings.jobs, q.job);
  throw new Fehler("Unbekannter Endpunkt: " + weg);
}

return {ruf, feiertageAT, ostersonntag, berechne, dauerMinuten, exportDaten,
        stempelLesen, dienstTage, dienstPauschale, Fehler};
})();
