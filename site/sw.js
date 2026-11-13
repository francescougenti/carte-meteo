/* Ventaglio: il sito si apre anche offline, con l'ultima previsione scaricata.
   - pagine, stili e script: subito dalla memoria, aggiornati in sottofondo
   - dati (data/): prima dalla rete, dalla memoria solo se la rete manca
   - carte (maps/): dalla memoria se già viste, al massimo le ultime 80 */
const SHELL = "ventaglio-pagine-v3";
const DATA = "ventaglio-dati-v1";
const MAPS = "ventaglio-carte-v1";
const SHELL_FILES = ["./", "citta.js", "citta.css", "radar.js", "icona.svg", "vendor/chart.umd.js", "manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => ![SHELL, DATA, MAPS].includes(k)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes("/data/")) e.respondWith(networkFirst(req));
  else if (url.pathname.includes("/maps/")) e.respondWith(cacheFirst(req));
  else e.respondWith(staleWhileRevalidate(req));
});

const bare = (req) => {  // i dati hanno ?t= o ?u= per evitare copie vecchie: in memoria si tengono senza
  const u = new URL(req.url);
  u.search = "";
  return new Request(u.toString());
};

async function networkFirst(req) {
  const cache = await caches.open(DATA);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(bare(req), res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(bare(req));
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(req) {
  const cache = await caches.open(MAPS);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) {
    await cache.put(req, res.clone());
    const keys = await cache.keys();
    for (const k of keys.slice(0, Math.max(0, keys.length - 80))) await cache.delete(k);
  }
  return res;
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(SHELL);
  const key = req.mode === "navigate" ? "./" : req;
  const hit = await cache.match(key, { ignoreSearch: req.mode === "navigate" });
  const fresh = fetch(req).then((res) => {
    if (res.ok) cache.put(key, res.clone());
    return res;
  }).catch(() => hit);
  return hit || fresh;
}
