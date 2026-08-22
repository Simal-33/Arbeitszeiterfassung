/* Service Worker: haelt die App offline verfuegbar.
   Bei jeder Aenderung VERSION erhoehen, damit der Cache erneuert wird. */
const VERSION = "zeiterfassung-v10";
const DATEIEN = ["./", "index.html", "lokal.js", "manifest.webmanifest",
                 "icon.svg", "icon-192.png", "icon-512.png", "icon-180.png"];

self.addEventListener("install", ev => {
  // cache:"reload" umgeht den HTTP-Cache des Browsers. Ohne das koennte eine
  // frisch veroeffentlichte Fassung bis zu zehn Minuten alt ausgeliefert werden.
  ev.waitUntil(caches.open(VERSION)
    .then(c => c.addAll(DATEIEN.map(d => new Request(d, {cache: "reload"}))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", ev => {
  ev.waitUntil(caches.keys()
    .then(namen => Promise.all(namen.filter(n => n !== VERSION).map(n => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", ev => {
  const url = new URL(ev.request.url);
  // API-Anfragen nie aus dem Cache beantworten
  if (ev.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  // Eigene Dateien immer frisch vom Server holen, damit ein Update sofort
  // ankommt; fremde Adressen bleiben unveraendert.
  const anfrage = url.origin === self.location.origin
    ? new Request(ev.request, {cache: "no-cache"}) : ev.request;
  ev.respondWith(
    fetch(anfrage)
      .then(res => {
        const kopie = res.clone();
        caches.open(VERSION).then(c => c.put(ev.request, kopie)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(ev.request).then(t => t || caches.match("index.html")))
  );
});
