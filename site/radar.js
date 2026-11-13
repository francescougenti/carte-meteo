/* Ventaglio – radar della pioggia.
   Immagini: rete radar nazionale del Dipartimento della Protezione Civile (prodotto SRI, intensità di pioggia
   al suolo, ogni 5 minuti), servite a tessere WMS. Mappa di base: OpenStreetMap e CARTO.
   Leaflet si carica solo quando si apre il radar. */
(() => {
"use strict";
const WMS = "https://radar-geowebcache.protezionecivile.it/service/wms";
const API = "https://radar-api.protezionecivile.it/findLastProductByType?type=SRI";
const STEP = 10;     // minuti tra un fotogramma e l'altro
const FRAMES = 7;    // l'ultima ora
const ITALY = [[35.2, 6.4], [47.3, 18.8]];
const R = { map: null, layers: [], times: [], k: 0, timer: null, poll: null, root: null, place: null, base: null, labels: null, obs: null };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fTime = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome" });
const isoMin = (t) => new Date(t).toISOString().slice(0, 16) + ":00.000Z";
const dark = () => (document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark"
  : matchMedia("(prefers-color-scheme: dark)").matches);
const still = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (!R.loading) {
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = "vendor/leaflet/leaflet.css";
    document.head.append(css);
    R.loading = new Promise((ok, ko) => {
      const s = document.createElement("script");
      s.src = "vendor/leaflet/leaflet.js"; s.onload = ok; s.onerror = () => { R.loading = null; ko(new Error("leaflet")); };
      document.head.append(s);
    });
  }
  return R.loading;
}

/** Ora dell'ultima immagine pubblicata; se il servizio non risponde, circa dieci minuti fa. */
async function latest() {
  try {
    const r = await fetch(API, { cache: "no-store" });
    const t = Number((await r.json()).lastProducts?.[0]?.time);
    if (t > 0) return t;
  } catch (e) { /* si stima */ }
  const now = Date.now();
  return now - (now % 3e5) - 10 * 6e4;
}

function page(place) {
  return `<section class="radar">
    <div class="r-head">
      <div><h1>Radar</h1><p>Dove piove adesso, con l'ultima ora animata.</p></div>
      ${place ? `<a class="r-back" href="#citta/${esc(place.id)}">Torna a ${esc(place.nome)}</a>` : ""}
    </div>
    <div class="r-wrap">
      <div class="r-map" id="rMap" role="img" aria-label="Mappa del radar della pioggia"></div>
      <p class="r-msg" id="rMsg" hidden></p>
    </div>
    <div class="rd-bar">
      <button type="button" class="r-play" id="rPlay" aria-label="Ferma l'animazione">${PAUSE}</button>
      <input type="range" id="rSlide" min="0" max="${FRAMES - 1}" value="${FRAMES - 1}" step="1" aria-label="Momento del radar">
      <output id="rTime" class="r-time" for="rSlide">–</output>
    </div>
    <div class="r-legend" aria-label="Intensità della pioggia">
      <span>debole</span><i></i><span>molto forte</span>
    </div>
    <p class="r-src">Intensità della pioggia al suolo stimata dalla rete radar nazionale, un'immagine ogni 5 minuti.
      Fonte: <a href="https://radar.protezionecivile.it/" target="_blank" rel="noopener">Dipartimento della Protezione Civile</a>, licenza CC BY 4.0.
      Il radar può vedere echi che non sono pioggia, soprattutto vicino ai monti.</p>
  </section>`;
}
const PLAY = `<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M4 2v12l10-6z"/></svg>`;
const PAUSE = `<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3.5 2h3v12h-3zM9.5 2h3v12h-3z"/></svg>`;

function baseLayers() {
  const style = dark() ? "dark" : "light";
  const attribution = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, © <a href="https://carto.com/attributions">CARTO</a>';
  if (R.base) { R.base.remove(); R.labels.remove(); }
  R.base = L.tileLayer(`https://{s}.basemaps.cartocdn.com/${style}_nolabels/{z}/{x}/{y}{r}.png`, { subdomains: "abcd", maxZoom: 19, attribution }).addTo(R.map);
  R.labels = L.tileLayer(`https://{s}.basemaps.cartocdn.com/${style}_only_labels/{z}/{x}/{y}{r}.png`, { subdomains: "abcd", maxZoom: 19, pane: "labels" }).addTo(R.map);
}

function show(k) {
  R.k = k;
  R.layers.forEach((l, i) => l.setOpacity(i === k ? 0.82 : 0));
  const slide = R.root.querySelector("#rSlide"), out = R.root.querySelector("#rTime");
  if (!slide) return;
  slide.value = k;
  const t = R.times[k];
  const ago = Math.round((Date.now() - t) / 6e4);
  out.innerHTML = `<b>${fTime.format(new Date(t))}</b> <span>${ago <= 1 ? "adesso" : ago < 60 ? `${ago} min fa` : `${Math.floor(ago / 60)} h ${ago % 60} min fa`}</span>`;
}
function stop() {
  clearTimeout(R.timer); R.timer = null;
  const b = R.root && R.root.querySelector("#rPlay");
  if (b) { b.innerHTML = PLAY; b.setAttribute("aria-label", "Avvia l'animazione"); }
}
function play() {
  stop();
  const b = R.root.querySelector("#rPlay");
  b.innerHTML = PAUSE; b.setAttribute("aria-label", "Ferma l'animazione");
  const tick = () => {
    const next = R.k >= FRAMES - 1 ? 0 : R.k + 1;
    show(next);
    R.timer = setTimeout(tick, next === FRAMES - 1 ? 1800 : 650);
  };
  R.timer = setTimeout(tick, R.k === FRAMES - 1 ? 1200 : 650);
}

async function frames() {
  const t = await latest();
  if (!R.map) return;
  // l'immagine più recente compare sulle tessere qualche minuto dopo l'annuncio: si parte da quella prima
  const last = t - 5 * 6e4;
  if (R.times.length && R.times[FRAMES - 1] === last) return;
  R.times = Array.from({ length: FRAMES }, (_, i) => last - (FRAMES - 1 - i) * STEP * 6e4);
  const old = R.layers;
  R.layers = R.times.map((tt) => L.tileLayer.wms(WMS, {
    layers: "radar:sri", styles: "", format: "image/png", transparent: true, version: "1.1.1", tiled: true, time: isoMin(tt),
    pane: "radar", opacity: 0, maxNativeZoom: 10, maxZoom: 12, bounds: [[34, 4.5], [48.5, 21]],
    attribution: 'Radar: <a href="https://radar.protezionecivile.it/">Protezione Civile</a>',
  }).addTo(R.map));
  old.forEach((l) => l.remove());
  show(FRAMES - 1);
}

window.Radar = {
  async open(root, place) {
    this.close();
    R.root = root;
    R.place = place;
    root.innerHTML = page(place);
    document.title = "Radar della pioggia – Ventaglio";
    const msg = root.querySelector("#rMsg");
    try { await loadLeaflet(); }
    catch (e) { msg.hidden = false; msg.textContent = "Il radar non si è caricato. Controlla la connessione e riprova."; return; }
    if (R.root !== root || !root.querySelector("#rMap")) return;
    R.map = L.map("rMap", { minZoom: 5, maxZoom: 12, maxBounds: [[31, -1], [52, 27]], zoomSnap: 1, worldCopyJump: false });
    R.map.attributionControl.setPrefix(false);
    R.map.createPane("radar").style.zIndex = 350;
    const lp = R.map.createPane("labels");
    lp.style.zIndex = 450; lp.style.pointerEvents = "none";
    if (place && place.lat != null) R.map.setView([place.lat, place.lon], 8);
    else R.map.fitBounds(ITALY);
    baseLayers();
    if (place && place.lat != null) {
      L.circleMarker([place.lat, place.lon], { radius: 6, weight: 2.5, color: "#fff", fillColor: "#C8102E", fillOpacity: 1, pane: "labels" })
        .addTo(R.map).bindTooltip(esc(place.nome), { permanent: true, direction: "right", offset: [8, 0], className: "r-tip" });
    }
    if (!navigator.onLine) { msg.hidden = false; msg.textContent = "Sei offline: il radar ha bisogno della connessione."; }
    await frames();
    root.querySelector("#rSlide").addEventListener("input", (e) => { stop(); show(+e.target.value); });
    root.querySelector("#rPlay").addEventListener("click", () => (R.timer ? stop() : play()));
    if (still()) stop(); else play();
    R.poll = setInterval(() => { if (!document.hidden) frames(); }, 5 * 60e3);
    R.obs = new MutationObserver(() => R.map && baseLayers());
    R.obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  },
  close() {
    clearTimeout(R.timer); R.timer = null;
    clearInterval(R.poll); R.poll = null;
    if (R.obs) { R.obs.disconnect(); R.obs = null; }
    if (R.map) { R.map.remove(); R.map = null; }
    R.layers = []; R.times = []; R.base = null; R.labels = null; R.root = null;
  },
};
})();
