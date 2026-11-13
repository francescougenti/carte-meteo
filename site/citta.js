/* Ventaglio – "La tua città": previsione per luogo, incertezza, quando lo saprai, cosa è cambiato.
   Dati: data/citta/indice.json e data/citta/<id>.json (formato in docs/formato-dati.md). */
(() => {
"use strict";

const STORE = "ventaglio.";
const W = { "ecmwf-ens": "modello europeo", gefs: "modello americano" };
const MODELS = { ecmwf: "ECMWF IFS", aifs: "ECMWF AIFS (intelligenza artificiale)", gfs: "GFS (NOAA)", "icon-eu": "ICON-EU (DWD)" };
const LABEL = {
  sereno: "Sereno", "poco-nuvoloso": "Poco nuvoloso", nuvoloso: "Nuvoloso", coperto: "Coperto",
  rovesci: "Possibili piogge", pioggia: "Pioggia", "pioggia-forte": "Pioggia forte", temporale: "Temporali",
  neve: "Neve", "pioggia-neve": "Pioggia e neve",
};
const STATE = { deciso: "Ventaglio chiuso", quasi: "Ventaglio socchiuso", aperto: "Ventaglio aperto" };
const SURE = { deciso: "previsione sicura", quasi: "abbastanza sicura", aperto: "ancora incerta" };
const MOTTO = "Ventaglio chiuso, con il tempo stai al sicuro.";
const RISK = { idraulico: "rischio idraulico", temporali: "temporali", idrogeologico: "rischio idrogeologico" };
const LEVEL = ["", "gialla", "arancione", "rossa"];
const DOUGLAS = ["calmo", "quasi calmo", "poco mosso", "mosso", "molto mosso", "agitato", "molto agitato", "grosso", "molto grosso", "tempestoso"];
const AVALANCHE = ["", "debole", "moderato", "marcato", "forte", "molto forte"];
// chiave gratuita della Webcams API di Windy (pubblica: viaggia in ogni richiesta). Vuota = webcam spente.
const WINDY_KEY = "";
const FASCE = ["Notte", "Mattina", "Pomeriggio", "Sera"];

const C = { index: null, comuni: null, data: null, day: 0, root: null, go: null, loading: null, alerts: null, more: false };
const ARTICLE = { Tramontana: "la", Grecale: "il", Levante: "il", Scirocco: "lo", Ostro: "l'", Libeccio: "il", Ponente: "il", Maestrale: "il" };
const CARD = ["nord", "nord-est", "est", "sud-est", "sud", "sud-ovest", "ovest", "nord-ovest"];
const ORIGIN = ["dal Nord Europa", "dai Balcani", "dall'Europa dell'Est", "dal Mediterraneo orientale", "dall'Africa",
  "dal Nord Africa e dalla Spagna", "dall'Atlantico", "dal Nord Atlantico"];
const RAINY = ["pioggia", "pioggia-forte", "neve", "pioggia-neve"];

// ---------- piccoli aiuti ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const deg = (v) => (v == null ? "–" : `${Math.round(v)}°`);
const num = (v) => (v == null ? "–" : Math.round(v).toLocaleString("it-IT"));
function store(k, v) {
  try { if (v === undefined) return JSON.parse(localStorage.getItem(STORE + k)); localStorage.setItem(STORE + k, JSON.stringify(v)); }
  catch (e) { return null; }
}
function session(k, v) {
  try { if (v === undefined) return JSON.parse(sessionStorage.getItem(STORE + k)); sessionStorage.setItem(STORE + k, JSON.stringify(v)); }
  catch (e) { return null; }
}
const romeDate = (t = Date.now()) => new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Rome" }).format(new Date(t));
const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const fWeek = new Intl.DateTimeFormat("it-IT", { weekday: "long", timeZone: "UTC" });
const fShort = new Intl.DateTimeFormat("it-IT", { weekday: "short", timeZone: "UTC" });
const fDayMonth = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", timeZone: "UTC" });
const fClock = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome" });
const dateObj = (iso) => new Date(iso + "T12:00:00Z");
/** "oggi alle 12:05", "ieri alle 18:00", "lunedì alle 9:10" */
function whenText(t) {
  const d = romeDate(t), today = romeDate();
  const day = d === today ? "oggi" : d === addDays(today, -1) ? "ieri" : fWeek.format(dateObj(d));
  return `${day} alle ${fClock.format(new Date(t))}`;
}
function dayName(iso, today = romeDate()) {
  if (iso === today) return "oggi";
  if (iso === addDays(today, 1)) return "domani";
  if (iso === addDays(today, -1)) return "ieri";
  const w = fWeek.format(dateObj(iso));
  return iso > addDays(today, 6) ? `${w} ${dateObj(iso).getUTCDate()}` : w;
}
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[’'`\-/.]/g, " ").replace(/\s+/g, " ").trim();
function km(a, b) {
  const r = Math.PI / 180, dl = (b.lat - a.lat) * r, dn = (b.lon - a.lon) * r;
  const h = Math.sin(dl / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dn / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}
async function getJSON(u) {
  const r = await fetch(u, { cache: "no-cache" });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// ---------- icone ----------
const SUN = (x = 12, y = 12, r = 4.2) => {
  let rays = "";
  for (let k = 0; k < 8; k++) {
    const a = (k * Math.PI) / 4, c = Math.cos(a), s = Math.sin(a);
    rays += `M${(x + c * (r + 2)).toFixed(1)} ${(y + s * (r + 2)).toFixed(1)}L${(x + c * (r + 4)).toFixed(1)} ${(y + s * (r + 4)).toFixed(1)}`;
  }
  return `<circle cx="${x}" cy="${y}" r="${r}" class="i-sun"/><path d="${rays}" class="i-ray"/>`;
};
const MOON = (x = 12, y = 11) => `<path d="M${x + 3.5} ${y + 4.6}A6 6 0 1 1 ${x + 1.8} ${y - 5.7}a4.6 4.6 0 0 0 1.7 10.3z" class="i-moon"/>`;
const CLOUD = (dx = 0, dy = 0, s = 1, cls = "i-cloud") =>
  `<path transform="translate(${dx} ${dy}) scale(${s})" d="M7 19.5h10.2a3.8 3.8 0 0 0 .6-7.55A5.7 5.7 0 0 0 6.9 12.6 3.45 3.45 0 0 0 7 19.5z" class="${cls}"/>`;
const DROPS = (n, long) => {
  const xs = n === 2 ? [10, 15] : n === 3 ? [8.5, 12.5, 16.5] : [7.5, 10.8, 14.1, 17.4];
  return `<path d="${xs.map((x) => `M${x} 18.2l-1.1 ${long ? 4.2 : 2.8}`).join("")}" class="i-drop"/>`;
};
const FLAKES = (xs) => xs.map((x) => `<g class="i-flake" transform="translate(${x} 20.3)"><path d="M-1.6 0h3.2M-.8-1.4l1.6 2.8M.8-1.4l-1.6 2.8"/></g>`).join("");
function icon(code, size = 28, night = false) {
  const lift = -3.4;
  const body = {
    sereno: night ? MOON() : SUN(),
    "poco-nuvoloso": (night ? MOON(9, 8.5) : SUN(9, 8.6, 3.4)) + CLOUD(2.6, 1.2, 0.86),
    nuvoloso: CLOUD(-2.8, -3.2, 0.78, "i-cloud i-back") + CLOUD(1.2, 0.6, 0.9),
    coperto: CLOUD(-2.8, -3.2, 0.78, "i-cloud i-back") + CLOUD(1.2, 0.6, 0.9, "i-cloud i-dark"),
    rovesci: (night ? MOON(8.5, 6.5) : SUN(8.6, 6.8, 3.2)) + CLOUD(2, lift + 0.6, 0.86) + DROPS(2),
    pioggia: CLOUD(0, lift) + DROPS(3),
    "pioggia-forte": CLOUD(0, lift, 1, "i-cloud i-dark") + DROPS(4, true),
    temporale: CLOUD(0, lift, 1, "i-cloud i-dark") + `<path d="M12.6 16.2 10 20.4h2.6l-1.2 3.4 3.6-4.9h-2.6l1.4-2.7z" class="i-bolt"/>`,
    neve: CLOUD(0, lift) + FLAKES([8, 12.5, 17]),
    "pioggia-neve": CLOUD(0, lift) + `<path d="M9 18.2l-1.1 2.8M16.6 18.2l-1.1 2.8" class="i-drop"/>` + FLAKES([12.6]),
  }[code] || CLOUD();
  return `<svg class="wx" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">${body}</svg>`;
}
/** Ventaglio più o meno aperto: lo stato della previsione (anche il logo usa questa forma). */
function fan(state, size = 18) {
  const open = { deciso: 20, quasi: 40, aperto: 64 }[state] || 40;
  const ribs = state === "deciso" ? 3 : state === "quasi" ? 4 : 5;
  const cx = 12, cy = 20, L = 15;
  const pts = [];
  for (let k = 0; k < ribs; k++) {
    const a = ((-90 - open + (2 * open * k) / (ribs - 1)) * Math.PI) / 180;
    pts.push([cx + L * Math.cos(a), cy + L * Math.sin(a)]);
  }
  const f = (n) => n.toFixed(1);
  let pleats = "", ribsD = "";
  for (let k = 0; k < ribs - 1; k++) {
    const [a, b] = [pts[k], pts[k + 1]];
    pleats += `<path d="M${cx} ${cy}L${f(a[0])} ${f(a[1])}A${L} ${L} 0 0 1 ${f(b[0])} ${f(b[1])}z" class="fan-p${k % 2}"/>`;
  }
  for (const [x, y] of pts) ribsD += `M${cx} ${cy}L${f(x)} ${f(y)}`;
  const [a0, a1] = [pts[0], pts[pts.length - 1]];
  const arc = `M${f(a0[0])} ${f(a0[1])}A${L} ${L} 0 0 1 ${f(a1[0])} ${f(a1[1])}`;
  return `<svg class="fan fan-${state}" viewBox="-3 3 30 19" width="${size}" height="${f((size * 19) / 30)}" aria-hidden="true">${pleats}<path d="${arc}" class="fan-arc"/><path d="${ribsD}" class="fan-rib"/><circle cx="${cx}" cy="${cy}" r="1.8" class="fan-pin"/></svg>`;
}

// ---------- testi ----------
function windText(v) {
  if (!v || v.kmh == null) return "";
  const k = v.kmh;
  const force = k >= 62 ? "molto forte" : k >= 39 ? "forte" : k >= 20 ? "moderato" : "";
  const parts = [];
  if (force) parts.push(`vento di ${v.nome} ${force}`);
  if (v.raffiche != null && v.raffiche >= 55) parts.push(`raffiche fino a ${num(Math.round(v.raffiche / 5) * 5)} km/h`);
  return parts.join(", ");
}
function daySentence(d) {
  const parts = [LABEL[d.codice] || "–"];
  const w = windText(d.vento);
  if (w) parts.push(w);
  const n = d.neve, r = d.pioggia || {};
  if (n && r.p >= 30 && snowNear(n, C.data) && !["neve"].includes(d.codice)) parts.push(`neve oltre i ${num(n.quota)} m`);
  if (n && n.suolo >= 1) parts.push(`${num(n.suolo)} cm di neve al suolo`);
  return parts.join(", ") + ".";
}
/** La quota neve interessa solo se la neve arriva vicino al comune: non più di 700 m sopra la sua quota. */
const snowNear = (n, data) => !!(n && data && data.alt != null && n.quota > data.alt && n.quota - data.alt <= 700);
function checkWhen(iso, today) {
  if (iso <= today) return "stasera";
  if (iso === addDays(today, 1)) return "domani sera";
  return `${fWeek.format(dateObj(iso))} sera`;
}
/** Probabilità a parole (al femminile: pioggia, neve). */
function chance(p, many) {
  if (p == null) return "";
  const w = p >= 90 ? ["quasi certa", "quasi certe"] : p >= 70 ? ["molto probabile", "molto probabili"] : p >= 50 ? ["probabile", "probabili"]
    : p >= 25 ? ["possibile", "possibili"] : p >= 10 ? ["poco probabile", "poco probabili"] : ["improbabile", "improbabili"];
  return w[many ? 1 : 0];
}
const mmText = (v) => (v == null ? "" : v < 0.05 ? "0 mm" : v < 9.95 ? `${v.toFixed(1).replace(".", ",").replace(",0", "")} mm` : `${Math.round(v)} mm`);
const at = (h) => (h % 24 === 0 ? "mezzanotte" : h === 1 ? "l'1" : `le ${h}`);
/** Le ore di pioggia: "tra le 15 e le 18", "quasi tutto il giorno". */
function hoursText(wins) {
  if (!wins || !wins.length) return "";
  return wins.map(([a, b]) => (a <= 1 && b >= 23 ? "tutto il giorno" : b - a >= 16 ? "quasi tutto il giorno" : `tra ${at(a)} e ${at(b)}`)).join(" e ");
}
function rainNoun(d) {
  return d.codice === "neve" ? ["Neve", false] : d.codice === "pioggia-neve" ? ["Pioggia e neve", true] : ["Pioggia", false];
}
/** "Pioggia molto probabile, 6 mm, tra le 15 e le 18" */
function rainText(d, hours = true) {
  const r = d.pioggia || {};
  const p = r.p ?? (r.mm == null ? null : r.mm >= 1 ? 60 : 0);
  if (p == null) return "";
  const [noun, many] = rainNoun(d);
  const parts = [`${noun} ${chance(p, many)}`];
  if (p >= 25 && r.mm >= 0.1) parts.push(mmText(r.mm));
  let wins = d.pioggia_ore;
  if (wins && d.data === romeDate()) {  // oggi contano solo le ore che devono ancora venire
    const now = hourNow();
    wins = wins.filter((w) => w[1] > now).map((w) => [Math.max(w[0], now), w[1], w[2]]);
  }
  const h = hours && p >= 25 ? hoursText(wins) : "";
  if (h) parts.push(h);
  return parts.join(", ");
}
/** Cosa resta da chiarire e quando ricontrollare (vuoto se la previsione è sicura). */
function sureText(d, today) {
  const u = d.incertezza || {};
  if ((u.stato || "quasi") === "deciso") return "";
  let t = u.motivo === "pioggia" ? "Non è ancora chiaro se pioverà." : d.max_f ? `La massima può andare da ${deg(d.max_f[0])} a ${deg(d.max_f[1])}.` : "";
  if (u.fino_all_ultimo) t += ` Può restare incerta fino all'ultimo: ricontrolla ${checkWhen(u.ricontrolla, today)}.`;
  else if (u.ricontrolla) t += ` Ricontrolla ${checkWhen(u.ricontrolla, today)}.`;
  return t.trim();
}
function stateLine(d, today, size = 34) {
  const st = d.incertezza?.stato || "quasi";
  const more = sureText(d, today);
  return `<p class="state s-${st}">${fan(st, size)}<span><b>${STATE[st]}</b>: ${SURE[st]}.${more ? ` <span class="more-t">${esc(more)}</span>` : ""}</span></p>`;
}

// ---------- mare ----------
const fromDir = (deg) => (deg == null ? "" : `da ${CARD[Math.round(((deg % 360) + 360) % 360 / 45) % 8]}`);
const mText = (v) => `${v.toFixed(1).replace(".", ",")} m`;
/** "mosso, onde 0,6–1,2 m da sud-est" */
function seaText(m, short) {
  if (!m || m.stato == null) return "";
  const waves = m.max < 0.15 ? "" : m.max - m.min >= 0.3 ? `onde ${mText(m.min).replace(" m", "")}–${mText(m.max)}` : `onde fino a ${mText(m.max)}`;
  if (short) return `Mare ${DOUGLAS[m.stato]}${waves ? ", " + waves : ""}`;
  return [DOUGLAS[m.stato], waves, waves ? fromDir(m.dir) : ""].filter(Boolean).join(", ").replace(/, (da )/, " $1");
}
const WAVE = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" class="wave"><path d="M2 9c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2M2 15c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2"/></svg>`;

// ---------- montagna e sci ----------
async function loadSki() {
  if (C.ski === undefined || Date.now() - C.skiAt > 30 * 60e3) {
    try { C.ski = await getJSON(`data/sci.json?u=${encodeURIComponent((C.index && C.index.aggiornato) || Date.now())}`); }
    catch (e) { C.ski = C.ski || null; }
    C.skiAt = Date.now();
  }
  return C.ski;
}
const nearSki = (p, maxKm = 25) => (C.ski ? C.ski.comprensori.map((r) => ({ r, d: km(p, r) })).filter((x) => x.d <= maxKm).sort((a, b) => a.d - b.d) : []);
const isMountain = (data) => (data.alt != null && data.alt >= 700) || nearSki(data).length > 0;
const SKI_STATE = { open: "Aperto", closed: "Chiuso", no_report: "Senza bollettino" };
const cm = (v) => (v == null ? "–" : `${num(v)} cm`);
function skiRow(r, extra = "") {
  const parts = [];
  if (r.impianti && r.impianti[1]) parts.push(`impianti ${r.impianti[0] ?? "–"} su ${r.impianti[1]}`);
  if (r.km && r.km[1]) parts.push(`piste ${num(r.km[0] ?? 0)} km su ${num(r.km[1])}`);
  else if (r.piste && r.piste[1]) parts.push(`piste ${r.piste[0] ?? "–"} su ${r.piste[1]}`);
  const snow = r.neve || [];
  const snowTxt = snow[0] != null || snow[1] != null
    ? `neve ${snow[0] != null ? cm(snow[0]) + " a valle" : ""}${snow[0] != null && snow[1] != null ? ", " : ""}${snow[1] != null ? cm(snow[1]) + " in quota" : ""}${snow[2] ? `, ${cm(snow[2])} fresca` : ""}` : "";
  return `<li class="ski s-${r.stato}">
    <div class="sk-head"><b>${esc(r.nome)}</b><span class="sk-state">${SKI_STATE[r.stato] || r.stato}</span>${extra}</div>
    <p>${esc([parts.join(", "), snowTxt].filter(Boolean).join(". ")) || "Nessun dato pubblicato dal comprensorio."}${r.valanghe ? ` <span class="sk-av av-${r.valanghe}">Valanghe: ${r.valanghe} ${AVALANCHE[r.valanghe]}</span>` : ""}</p>
  </li>`;
}
/** Il riquadro "In montagna" del giorno scelto: neve prevista, zero termico, temperatura e vento in quota, piste vicine. */
function mountainBlock(d, data) {
  if (!isMountain(data)) return "";
  const n = d.neve, q = d.quota, r = d.pioggia || {}, mm = r.mm || 0, p = r.p ?? 0;
  const rows = [];
  if (n) {
    rows.push(["Zero termico", `${num(n.quota + 300)} m`]);
    if (p >= 25 && mm >= 1) rows.push(["Quota neve", `circa ${num(n.quota)} m`]);
  }
  const here = ["neve", "pioggia-neve"].includes(d.codice) ? mm * (d.codice === "neve" ? 1 : 0.5) : 0;
  if (here >= 1) rows.push([`Neve fresca a ${num(data.alt)} m`, `circa ${num(Math.round(here))} cm`]);
  if (n && p >= 25 && mm >= 1 && n.quota <= 2000) rows.push(["Neve fresca a 2.000 m", `circa ${num(Math.max(1, Math.round(mm)))} cm`]);
  if (q) {
    rows.push(["A 1.500 m", `${deg(q.t1500)}`]);
    if (q.vento != null) rows.push(["Vento in quota", `${num(q.vento)} km/h ${fromDir(q.dir)}`]);
  }
  const ski = nearSki(data);
  const list = "";
  return `<div class="mountain"><div class="h-head"><h3>In montagna</h3><a href="#neve">Neve e piste in Italia</a></div>
    <dl class="facts">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>${list}
    <p class="h-note">${ski.length ? "Piste e neve di oggi sono nel riquadro Neve e piste in alto. " : ""}La neve prevista è indicativa: circa 1 cm per ogni millimetro di pioggia.</p></div>`;
}
const IC_VALLE = `<svg viewBox="0 0 48 48" width="46" height="46" aria-hidden="true" class="sb-ic"><path d="M3 41.5h42" class="ic-l"/><path d="M11 40V25.5L24 15l13 10.5V40z" class="ic-f"/><path d="M20.5 40v-8h7v8" class="ic-l"/><path d="M7.5 27.5 24 14l16.5 13.5" class="ic-snow"/><path d="M5 41.5c3-2.6 6-2.6 9 0M33 41.5c3-2.6 7-2.6 10 0" class="ic-snow2"/></svg>`;
const IC_CIMA = `<svg viewBox="0 0 48 48" width="46" height="46" aria-hidden="true" class="sb-ic"><path d="M3 40 18.5 13l7.5 12.5 4.5-6.5L45 40z" class="ic-f"/><path d="m13.6 21.6 4.9-8.6 4.8 8-2.6-1.3-2.3 2.2-2.3-2.1z" class="ic-cap"/><path d="m28 22.5 2.5-3.5 3.2 4.6-1.9-.8-1.6 1.2z" class="ic-cap"/></svg>`;
const IC_PISTE = `<svg viewBox="0 0 48 48" width="46" height="46" aria-hidden="true" class="sb-ic"><path d="M4 38.5c10-1 22-8 40-24" class="ic-l"/><path d="M30 9v15" class="ic-l"/><path d="M30 9.5h9.5L36 13l3.5 3.5H30" class="ic-flag"/><circle cx="14.5" cy="22" r="2.4" class="ic-dot"/><path d="m9.5 33.5 4-7.5 4.5 2.5 2 5M12 28.5l-3 1.5" class="ic-l"/></svg>`;
const IC_IMPIANTI = `<svg viewBox="0 0 48 48" width="46" height="46" aria-hidden="true" class="sb-ic"><path d="M3 9.5 45 21" class="ic-l"/><path d="M24 15v6" class="ic-l"/><rect x="16" y="21" width="16" height="13" rx="3" class="ic-f"/><path d="M19 25.5h10" class="ic-l"/><path d="M5 42h38" class="ic-l"/></svg>`;
/** Il riquadro in cima alla pagina dei comuni di montagna: neve a valle e in cima, piste e impianti aperti e chiusi. */
function snowBox(data) {
  const near = nearSki(data);
  const today = data.giorni[0];
  const suolo = today && today.neve ? today.neve.suolo : null;
  if (!near.length && !(data.alt >= 700 && suolo >= 1)) return "";
  const item = (ic, lab, big, small, cls = "") => `<div class="sb-item ${cls}">${ic}<div><span class="sb-lab">${lab}</span><b>${big}</b>${small ? `<small>${small}</small>` : ""}</div></div>`;
  if (!near.length) {
    return `<section class="snowbox"><div class="sb-head"><h2>Neve</h2></div><div class="sb-grid">
      ${item(IC_VALLE, "Neve al suolo", cm(suolo), `a ${num(data.alt)} m, stima dei modelli`)}</div></section>`;
  }
  const { r, d } = near[0];
  const n = r.neve || [], m = r.modello || {};
  const here = d <= 5;
  const valle = n[0] != null ? [cm(n[0]), "dal comprensorio"]
    : here && suolo != null ? [cm(suolo), `a ${num(data.alt)} m, stima dei modelli`]
    : m.valle != null ? [cm(m.valle), "stima dei modelli"] : ["–", "non pubblicata"];
  const cima = n[1] != null ? [cm(n[1]), "dal comprensorio"]
    : m.cima != null ? [cm(m.cima), `a ${num(m.quota)} m, stima del modello ICON-EU${m.cima_3g != null && m.cima_3g !== m.cima ? `; tra 3 giorni circa ${cm(m.cima_3g)}` : ""}`]
    : ["–", "non pubblicata"];
  const fresh = n[2] ? `${cm(n[2])} di neve fresca. ` : "";
  // piste: aperte e chiuse
  let piste;
  if (r.piste && r.piste[0] != null && r.piste[1]) piste = [`${r.piste[0]} aperte`, `${r.piste[1] - r.piste[0]} chiuse${r.km && r.km[1] ? `, ${num(r.km[0] ?? 0)} km aperti su ${num(r.km[1])}` : ""}`];
  else if (r.km && r.km[0] != null && r.km[1]) piste = [`${num(r.km[0])} km aperti`, `su ${num(r.km[1])} km`];
  else if (r.piste && r.piste[1]) piste = [`${r.piste[1]} piste`, r.stato === "closed" ? "tutte chiuse" : "aperte e chiuse non ancora pubblicate"];
  else piste = ["–", "non pubblicate"];
  const imp = r.impianti && r.impianti[1] ? [`${r.impianti[0] ?? "–"} su ${r.impianti[1]}`, r.impianti[0] != null ? `aperti, ${r.impianti[1] - r.impianti[0]} chiusi` : "non pubblicati"] : ["–", ""];
  const others = near.slice(1, 4).map(({ r: o, d: dd }) => `${esc(o.nome)} (${SKI_STATE[o.stato].toLowerCase()}, ${num(dd)} km)`).join(", ");
  const when = r.controllato ? whenText(Date.parse(r.controllato)) : "";
  return `<section class="snowbox s-${r.stato}">
    <div class="sb-head"><h2>Neve e piste</h2><span class="sb-name">${esc(r.nome)}${here ? "" : `, a ${num(d)} km`}</span><span class="sk-state">${SKI_STATE[r.stato] || ""}</span>
      ${r.valanghe ? `<span class="sk-av av-${r.valanghe}">Valanghe: ${r.valanghe} ${AVALANCHE[r.valanghe]}</span>` : ""}</div>
    <div class="sb-grid">
      ${item(IC_VALLE, "Neve al suolo", valle[0], valle[1])}
      ${item(IC_CIMA, "Neve in cima", cima[0], cima[1])}
      ${item(IC_PISTE, "Piste", piste[0], piste[1])}
      ${item(IC_IMPIANTI, "Impianti", imp[0], imp[1])}
    </div>
    <p class="sb-note">${fresh}${when ? `Bollettino raccolto ${esc(when)} da <a href="https://liftradar.eu" target="_blank" rel="noopener">LiftRadar</a>. ` : ""}${others ? `Vicino: ${others}. ` : ""}<a href="#neve">Tutti i comprensori</a></p>
  </section>`;
}

function skiPage() {
  const S = C.ski;
  if (!S) return `<article class="info"><h1>Neve e piste</h1><p class="note">I dati dei comprensori non sono ancora disponibili: arrivano con il prossimo aggiornamento.</p></article>`;
  const t = S.totale || {};
  const byReg = new Map();
  for (const r of S.comprensori) { const k = r.regione || "Altro"; if (!byReg.has(k)) byReg.set(k, []); byReg.get(k).push(r); }
  const regs = [...byReg.keys()].sort((a, b) => a.localeCompare(b, "it"));
  const lists = regs.map((g) => `<section class="ski-reg"><h2>${esc(g)}</h2><ul class="ski-list">${byReg.get(g)
    .sort((a, b) => (a.stato === "open" ? 0 : 1) - (b.stato === "open" ? 0 : 1) || a.nome.localeCompare(b.nome, "it"))
    .map((r) => skiRow(r, `<a class="sk-fc" href="#citta/${esc(r.comune)}">Previsione per ${esc(r.comune_nome)}</a>`)).join("")}</ul></section>`).join("");
  const when = S.fonte_aggiornata ? whenText(Date.parse(S.fonte_aggiornata)) : "";
  return `<article class="info skipage">
    <h1>Neve e piste</h1>
    <p class="lede">Oggi in Italia sono aperti <b>${t.aperti} comprensori su ${t.comprensori}</b>${t.impianti ? `, con ${num(t.impianti[0])} impianti su ${num(t.impianti[1])}` : ""}${t.km && t.km[1] ? ` e ${num(t.km[0])} km di piste su ${num(t.km[1])}` : ""}.</p>
    <p class="muted">Dai bollettini dei comprensori e degli enti turistici, raccolti due volte al giorno da <a href="${esc(S.link)}" target="_blank" rel="noopener">LiftRadar</a>${when ? `; aggiornati ${esc(when)}` : ""}.
      Mancano per ora Piemonte, Appennini e Sicilia. Il pericolo valanghe è quello dei bollettini AINEVA ed Euregio (1 debole, 5 molto forte).</p>
    ${lists}
  </article>`;
}

// ---------- centralina MeteoNetwork più vicina ----------
async function loadStations() {
  if (C.st === undefined || Date.now() - C.stAt > 10 * 60e3) {
    try {
      const raw = await getJSON(`data/stazioni.json?t=${Math.floor(Date.now() / 6e5)}`);
      const F = Object.fromEntries(raw.campi.map((k, i) => [k, i]));
      C.st = raw.stazioni.map((r) => Object.fromEntries(Object.entries(F).map(([k, i]) => [k, r[i]])));
      C.stInfo = raw;
    } catch (e) { C.st = C.st || null; }
    C.stAt = Date.now();
  }
  return C.st;
}
function stationLine(data) {
  if (!C.st || data.lat == null) return "";
  let best = null;
  for (const s of C.st) {
    if (s.t == null) continue;
    const d = km(data, s);
    if (d > 12 || (data.alt != null && s.quota != null && Math.abs(data.alt - s.quota) > 250)) continue;
    if (!best || d < best.d) best = { s, d };
  }
  if (!best) return "";
  const s = best.s, t = Date.parse(s.ora.replace("Z", ":00Z"));
  const bits = [`<b>${String(s.t.toFixed(1)).replace(".", ",")}°</b>`];
  if (s.umidita != null) bits.push(`umidità ${num(s.umidita)}%`);
  if (s.pioggia_oggi != null) bits.push(`pioggia oggi ${mmText(s.pioggia_oggi)}`);
  if (s.vento != null) bits.push(`vento ${num(s.vento)} km/h`);
  return `<p class="station">${STATION}<span>Misurato alle ${esc(fClock.format(new Date(t)))} dalla centralina di ${esc(s.luogo || s.codice)}
    (${best.d < 1 ? "meno di 1 km" : num(best.d) + " km"}): ${bits.join(", ")}. <a href="https://www.meteonetwork.it/" target="_blank" rel="noopener">MeteoNetwork</a></span></p>`;
}
const STATION = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" class="st-i"><path d="M12 3v18M8 21h8M12 6h6M12 10h4"/><circle cx="12" cy="3.5" r="1.2"/></svg>`;

// ---------- webcam di Windy ----------
async function webcams(data) {
  if (!WINDY_KEY || data.lat == null) return null;
  const u = `https://api.windy.com/webcams/api/v3/webcams?nearby=${data.lat.toFixed(3)},${data.lon.toFixed(3)},30&include=images,location,urls&limit=4&lang=it`;
  const r = await fetch(u, { headers: { "x-windy-api-key": WINDY_KEY } });
  if (!r.ok) throw new Error(r.status);
  return (await r.json()).webcams || [];
}
function camsBlock(list) {
  if (!list || !list.length) return "";
  const items = list.map((w) => {
    const img = w.images?.current?.preview || w.images?.daylight?.preview;
    const link = w.urls?.detail || `https://www.windy.com/webcams/${w.webcamId}`;
    if (!img) return "";
    return `<li><a href="${esc(link)}" target="_blank" rel="noopener"><img src="${esc(img)}" alt="${esc(w.title || "Webcam")}" loading="lazy"><span>${esc(w.title || w.location?.city || "Webcam")}</span></a></li>`;
  }).join("");
  if (!items) return "";
  return `<section class="cams"><div class="h-head"><h3>Webcam vicine</h3><span class="sun">Webcam fornite da <a href="https://www.windy.com/webcams" target="_blank" rel="noopener">Windy.com</a>. <a href="https://www.windy.com/webcams/add" target="_blank" rel="noopener">Aggiungi una webcam</a></span></div><ul class="cam-grid">${items}</ul></section>`;
}

// ---------- allerte della Protezione Civile ----------
async function loadAlerts() {
  if (C.alerts === null || Date.now() - C.alertsAt > 10 * 60e3) {
    try { C.alerts = await getJSON(`data/allerte.json?u=${encodeURIComponent((C.index && C.index.aggiornato) || Date.now())}`); }
    catch (e) { C.alerts = C.alerts || false; }
    C.alertsAt = Date.now();
  }
  return C.alerts;
}
const listIt = (a) => (a.length < 2 ? a.join("") : `${a.slice(0, -1).join(", ")} e ${a[a.length - 1]}`);
/** Allerta del comune per un giorno: livello (1 gialla, 2 arancione, 3 rossa) e frase. */
function alertOf(id, iso) {
  const A = C.alerts;
  if (!A || !A.comuni || A.comuni[id] == null) return null;
  const z = A.zone[A.comuni[id]];
  const lv = !z ? null : iso === A.oggi ? z.oggi : iso === A.domani ? z.domani : null;
  if (!lv) return null;
  const max = Math.max(...lv);
  if (!max) return null;
  const parts = [];
  for (let k = max; k >= 1; k--) {
    const risks = A.rischi.filter((r, i) => lv[i] === k).map((r) => RISK[r] || r);
    if (risks.length) parts.push(`${parts.length ? LEVEL[k] : "allerta " + LEVEL[k]} per ${listIt(risks)}`);
  }
  return { level: max, text: parts.join(", "), zona: z.nome };
}
function alertBanner(data, today) {
  const rows = [today, addDays(today, 1)].map((iso) => [iso, alertOf(data.id, iso)]).filter(([, a]) => a);
  if (!rows.length) return "";
  const top = Math.max(...rows.map(([, a]) => a.level));
  const A = C.alerts;
  const items = rows.map(([iso, a]) => `<li><b>${cap(dayName(iso, today))}</b>: ${esc(a.text)}.</li>`).join("");
  return `<section class="alert al-${top}" aria-label="Allerte della Protezione Civile">
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="M12 2.8 22.5 21h-21z" class="al-tri"/><path d="M12 9v5.6M12 17.4v.4" class="al-mark"/></svg>
    <div><ul>${items}</ul><p>Zona ${esc(rows[0][1].zona)}. <a href="${esc(A.link)}" target="_blank" rel="noopener">Bollettino della Protezione Civile</a>, ${esc(A.nome.replace(/^Bollettino del /, ""))}.</p></div>
  </section>`;
}

// ---------- cosa è cambiato ----------
function changes(prev, cur, today, noSnow) {
  const out = [];
  const byDate = new Map(prev.map((d) => [d.data, d]));
  for (const d of cur) {
    if (d.data < today) continue;
    const o = byDate.get(d.data);
    if (!o) continue;
    const name = dayName(d.data, today);
    const r = d.pioggia?.p, ro = o.p;
    if (r != null && ro != null && Math.abs(r - ro) >= 25) {
      const txt = r >= 50 && ro < 50 ? "la pioggia ora è probabile" : r < 50 && ro >= 50 ? "la pioggia è diventata improbabile"
        : r > ro ? "la pioggia è più probabile" : "la pioggia è meno probabile";
      out.push({ w: Math.abs(r - ro) / 10 + 2, t: `<b>${cap(name)}</b>: ${txt} (${Math.round(r)}%, prima ${Math.round(ro)}%).` });
    }
    for (const [key, lab] of [["max", "massima"], ["min", "minima"]]) {
      if (d[key] == null || o[key] == null) continue;
      const dv = Math.round(d[key]) - Math.round(o[key]);
      if (Math.abs(dv) >= 2)
        out.push({ w: Math.abs(dv) / 1.5, t: `<b>${cap(name)}</b>: ${lab} di ${Math.abs(dv)}° ${dv > 0 ? "più alta" : "più bassa"} (${deg(d[key])}, prima ${deg(o[key])}).` });
    }
    const snowNow = ["neve", "pioggia-neve"].includes(d.codice), snowThen = ["neve", "pioggia-neve"].includes(o.codice);
    if (snowNow !== snowThen && !noSnow) out.push({ w: 4, t: `<b>${cap(name)}</b>: ${snowNow ? "ora è prevista neve" : "la neve non è più prevista"}.` });
  }
  return out.sort((a, b) => b.w - a.w).slice(0, 4).map((x) => x.t);
}
function snapshot(data) {
  return data.giorni.map((d) => ({ data: d.data, min: d.min, max: d.max, p: d.pioggia?.p, codice: d.codice }));
}
/** Confronto con l'ultima visita (salvata solo nel browser) o, alla prima visita, con ieri a quest'ora. */
function changeNote(data, today) {
  const key = `visita.${data.id}`;
  let base = session(`base.${data.id}`);
  const last = store(key);
  if (!base && last) { base = last; session(`base.${data.id}`, last); }
  if (!last || last.aggiornato !== data.aggiornato) store(key, { t: Date.now(), aggiornato: data.aggiornato, giorni: snapshot(data) });
  if (base && base.aggiornato === data.aggiornato)
    return { title: `Da quando sei passato, ${whenText(base.t)}`, items: [], same: true };
  if (base) return { title: `Da quando sei passato, ${whenText(base.t)}`, items: changes(base.giorni, data.giorni, today) };
  // prima visita: lo storico pubblicato dice com'era la previsione circa un giorno fa
  const target = Date.parse(data.aggiornato) - 24 * 36e5;
  const prev = [];
  let when = null;
  for (const [day, snaps] of Object.entries(data.storia || {})) {
    let best = null;
    for (const s of snaps) {
      const t = Date.parse(s[0].replace("Z", ":00Z"));
      if (t <= target + 3 * 36e5 && (!best || t > best.t)) best = { t, s };
    }
    if (best) { prev.push({ data: day, min: best.s[1], max: best.s[2], p: best.s[3], codice: best.s[5] }); when = when || best.t; }
  }
  if (!prev.length) return null;
  // per i comuni delle zone lo storico ha l'icona della quota della zona: la neve non si confronta
  return { title: "Rispetto a ieri", items: changes(prev, data.giorni, today, !!data.zona), first: true };
}

// ---------- disegno ----------
const hourNow = () => +fClock.format(new Date()).slice(0, 2);
/** Righe dell'ora per ora ancora da venire (per oggi si parte dall'ora in corso). */
function hoursLeft(d) {
  const rows = d.ore || [];
  if (d.data !== romeDate()) return rows;
  const h = hourNow();
  return rows.filter((r) => r[0] + r[8] > h);
}
function nowTemp(d) {
  const r = hoursLeft(d)[0];
  return r && r[1] != null && d.data === romeDate() && r[0] <= hourNow() ? r[1] : null;
}
function hero(data, today) {
  const g = data.giorni;
  const blocks = g.slice(0, 2).map((d, i) => {
    const now = i === 0 ? nowTemp(d) : null;
    const rain = rainText(d);
    return `<article class="now ${i ? "next" : ""}" data-i="${i}" tabindex="0">
      <h2>${cap(dayName(d.data, today))}${now != null ? `<span class="t-now">adesso ${deg(now)}</span>` : ""}</h2>
      <div class="now-main">${icon(d.codice, i ? 54 : 68)}<div class="temps"><span class="t-max" title="Massima">${deg(d.max)}</span><span class="t-min" title="Minima">${deg(d.min)}</span></div></div>
      <p class="sentence">${esc(daySentence(d))}</p>
      ${rain ? `<p class="rain-l${(d.pioggia?.p ?? 0) >= 50 ? " wet" : ""}">${DROP}<span>${esc(rain)}</span></p>` : ""}
      ${d.mare && data.mare_km != null ? `<p class="sea-l">${WAVE}<span>${esc(seaText(d.mare, true))}</span></p>` : ""}
      ${stateLine(d, today, i ? 30 : 38)}
    </article>`;
  }).join("");
  return `<div class="now-row">${blocks}</div>`;
}
const DROP = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" class="drop"><path d="M12 3.2c3.4 4.6 6 8 6 11.1a6 6 0 0 1-12 0c0-3.1 2.6-6.5 6-11.1z"/></svg>`;
const TRI = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" class="tri"><path d="M12 2.8 22.5 21h-21z" class="al-tri"/><path d="M12 9v5.6M12 17.4v.4" class="al-mark"/></svg>`;

function changesBlock(note) {
  if (!note) return "";
  if (note.same) return "";
  if (!note.items.length)
    return `<p class="changes-none">${esc(note.title)}: niente di importante è cambiato nella previsione.</p>`;
  return `<section class="changes" aria-live="polite"><h2>${esc(note.title)}</h2><ul>${note.items.map((t) => `<li>${t}</li>`).join("")}</ul></section>`;
}

function fanChart(data, today) {
  const g = data.giorni;
  const cols = g.map((d, i) => {
    const st = d.incertezza?.stato || "quasi";
    const p = d.pioggia?.p, mm = d.pioggia?.mm;
    const sel = i === C.day;
    const al = alertOf(data.id, d.data);
    const showMm = p != null && p >= 25 && mm >= 0.1;
    const label = `${cap(dayName(d.data, today))}: ${LABEL[d.codice] || ""}, massima ${deg(d.max)}, minima ${deg(d.min)}. ${rainText(d, false)}. ${STATE[st]}: ${SURE[st]}${al ? ". " + cap(al.text) : ""}`;
    return `<button class="col${sel ? " sel" : ""}${al ? " al-" + al.level : ""}" data-i="${i}" aria-pressed="${sel}" aria-label="${esc(label)}">
      <span class="c-day">${i === 0 ? "Oggi" : cap(fShort.format(dateObj(d.data)).replace(".", ""))}<small>${dateObj(d.data).getUTCDate()}</small></span>
      ${icon(d.codice, 32)}
      <span class="c-max">${deg(d.max)}</span>
      <span class="c-plot"></span>
      <span class="c-min">${deg(d.min)}</span>
      <span class="c-rain${p != null && p >= 50 ? " wet" : p != null && p >= 25 ? " maybe" : ""}"><i style="height:${p == null ? 0 : Math.max(2, (p / 100) * 24)}px"></i>${showMm ? `<b>${mmText(mm).replace(" mm", "")}</b><small>mm</small>` : ""}</span>
      <span class="c-state">${fan(st, 34)}</span>
    </button>`;
  }).join("");
  return `<section class="ventaglio" aria-labelledby="vTitle">
    <div class="sec-head"><h2 id="vTitle">I prossimi ${g.length} giorni</h2>
      <p class="v-legend"><span>${fan("deciso", 26)}sicura</span><span>${fan("quasi", 26)}abbastanza</span><span>${fan("aperto", 26)}incerta</span></p></div>
    <div class="v-scroll"><div class="v-grid" style="--n:${g.length}">${cols}<svg class="v-svg" aria-hidden="true"></svg></div></div>
    <p class="v-note">La fascia colorata è dove possono cadere massima e minima; la barra azzurra è la probabilità di pioggia, il numero i millimetri.</p>
  </section>`;
}

/** Disegna fasce e linee delle temperature dietro le colonne, alla larghezza effettiva. */
function drawBands(root, data) {
  const grid = root.querySelector(".v-grid"), svg = root.querySelector(".v-svg");
  const plots = [...root.querySelectorAll(".c-plot")];
  if (!grid || !plots.length) return;
  const gb = grid.getBoundingClientRect();
  const pb = plots[0].getBoundingClientRect();
  const top = pb.top - gb.top, h = pb.height;
  svg.setAttribute("viewBox", `0 0 ${gb.width} ${gb.height}`);
  svg.setAttribute("width", gb.width); svg.setAttribute("height", gb.height);
  const g = data.giorni;
  const vals = g.flatMap((d) => [d.max, d.min, ...(d.max_f || []), ...(d.min_f || [])]).filter((v) => v != null);
  if (!vals.length) { svg.innerHTML = ""; return; }
  const lo = Math.min(...vals) - 0.5, hi = Math.max(...vals) + 0.5;
  const y = (v) => top + 4 + (1 - (v - lo) / (hi - lo)) * (h - 8);
  const xs = plots.map((p) => { const b = p.getBoundingClientRect(); return b.left - gb.left + b.width / 2; });
  const band = (key) => {
    const pts = g.map((d, i) => (d[key + "_f"] ? [xs[i], d[key + "_f"]] : null)).filter(Boolean);
    if (pts.length < 2) return "";
    const up = pts.map(([x, f]) => `${x.toFixed(1)},${y(f[1]).toFixed(1)}`);
    const dn = pts.slice().reverse().map(([x, f]) => `${x.toFixed(1)},${y(f[0]).toFixed(1)}`);
    return `<polygon points="${up.concat(dn).join(" ")}" class="band band-${key}"/>`;
  };
  const line = (key) => {
    const pts = g.map((d, i) => (d[key] != null ? `${xs[i].toFixed(1)},${y(d[key]).toFixed(1)}` : null)).filter(Boolean);
    return pts.length > 1 ? `<polyline points="${pts.join(" ")}" class="line line-${key}"/>` : "";
  };
  const dots = (key) => g.map((d, i) => (d[key] != null ? `<circle cx="${xs[i].toFixed(1)}" cy="${y(d[key]).toFixed(1)}" r="2.6" class="dot dot-${key}"/>` : "")).join("");
  svg.innerHTML = band("max") + band("min") + line("max") + line("min") + dots("max") + dots("min");
}

function chartFor(id, iso) {
  const M = window.VENTAGLIO_MANIFEST;
  if (!M) return null;
  for (const mid of ["ecmwf", "gfs", "icon-eu", "aifs"]) {
    const m = M.models && M.models[mid];
    if (!m || !(m.regions || []).includes("italia")) continue;
    const st = (m.steps || []).find((x) => x.valid === iso && (x.charts || []).includes(id));
    if (!st) continue;
    const run = new Date(st.run).toISOString().slice(0, 13).replace(/[-T]/g, "");
    const lead = Math.round((Date.parse(iso) - Date.parse(m.run)) / 36e5);
    const label = ((M.charts || []).find((c) => c.id === id) || {}).label || id;
    return { url: `maps/${mid}/italia/${id}/${String(st.h).padStart(3, "0")}.${m.ext || "png"}?r=${run}`,
      hash: `#carte/${mid}/italia/${id}/${lead}`, label, model: m.short || mid };
  }
  return null;
}
function whyText(r, d, prevName) {
  const dir = r.dir == null ? null : Math.round(((r.dir % 360) + 360) % 360 / 45) % 8;
  const from = dir == null ? "" : ` da ${CARD[dir]}, ${ORIGIN[dir]}`;
  const w = d.vento || {};
  const fascia = { 6: "di notte", 12: "al mattino", 18: "nel pomeriggio", 0: "la sera" }[new Date(r.ora).getUTCHours()] || "";
  switch (r.tipo) {
    case "freddo": return `Arriva aria più fredda${from}: a 1.500 metri di quota la temperatura scende di ${r.delta} gradi rispetto a ${prevName}.`;
    case "caldo": return `Arriva aria più calda${from}: a 1.500 metri di quota la temperatura sale di ${r.delta} gradi rispetto a ${prevName}.`;
    case "neve": return `Lo zero termico scende intorno ai ${num(r.zero)} m: la neve può arrivare fino a circa ${num(Math.max(r.zero - 300, 0))} m.`;
    case "temporali": return `L'aria è instabile e carica di energia: possibili temporali${r.cape >= 1500 ? ", anche forti" : ""}.`;
    case "vento": {
      const art = ARTICLE[w.nome] || "il";
      return `Soffia ${art}${art.endsWith("'") ? "" : " "}${w.nome || "vento"}${w.raffiche ? `, con raffiche fino a ${num(Math.round(w.raffiche / 5) * 5)} km/h` : ""}.`;
    }
    case "bassa": return `Una zona di bassa pressione (${r.hpa} hPa) passa vicino e porta nuvole e piogge.`;
    case "alta": return `L'alta pressione (${r.hpa} hPa) tiene lontane le perturbazioni.`;
    case "pioggia": return `Passa una perturbazione: piove soprattutto ${fascia}.`;
    default: return "";
  }
}
function whyBlock(d, prevName) {
  const list = (d.perche || []).filter((r) => r.tipo !== "neve" || ["neve", "pioggia-neve"].includes(d.codice));
  if (!list.length) return "";
  const r = list[0];
  const text = whyText(r, d, prevName);
  if (!text) return "";
  const ch = chartFor(r.carta, r.ora);
  const at = `${dayName(romeDate(Date.parse(r.ora)))} alle ${fClock.format(new Date(r.ora))}`;
  const fig = ch ? `<figure class="why-map"><a href="${ch.hash}" aria-label="Apri la carta nella cartografia per appassionati">
      <img src="${ch.url}" loading="lazy" alt="Carta: ${esc(ch.label)}, ${esc(at)} (${esc(ch.model)})"></a>
      <figcaption>${esc(ch.label)}${r.carta === "prec6" ? " fino a" : ","} ${esc(at)}, modello ${esc(ch.model)}. <a href="${ch.hash}">Apri la carta</a></figcaption></figure>` : "";
  return `<h3>Perché</h3><p>${esc(text)}</p>${fig}`;
}

function scenarios(d) {
  const r = d.pioggia || {};
  if (!r.membri) return `<p class="muted">Per questo giorno non ci sono gli scenari dell'ensemble: la probabilità viene dal confronto tra i modelli.</p>`;
  const all = [];
  for (const [sid, list] of Object.entries(r.membri)) for (const mm of list) if (mm != null) all.push({ sid, mm });
  all.sort((a, b) => a.mm - b.mm);
  const cls = (mm) => (mm < 1 ? "f0" : mm < 5 ? "f1" : mm < 15 ? "f2" : "f3");
  const per = Object.entries(r.membri).map(([sid, list]) => {
    const k = list.filter((x) => x != null && x >= 1).length;
    return `${k} su ${list.length} del ${W[sid] || sid}`;
  });
  const dots = all.map((m) => `<i class="${cls(m.mm)}" title="${m.mm.toFixed(1).replace(".", ",")} mm (${W[m.sid] || m.sid})"></i>`).join("");
  const k = r.scenari ?? r.futuri;
  return `<p>Piove almeno 1 mm in <b>${k} scenari su ${r.su}</b>: ${per.join(" e ")}.</p>
    <div class="dots" role="img" aria-label="${k} scenari con pioggia su ${r.su}">${dots}</div>
    <p class="legend"><span><i class="f0"></i>asciutto</span><span><i class="f1"></i>1–5 mm</span><span><i class="f2"></i>5–15 mm</span><span><i class="f3"></i>oltre 15 mm</span></p>`;
}

function historyBlock(data, d) {
  const snaps = (data.storia || {})[d.data] || [];
  if (snaps.length < 2) return `<p class="muted">Lo storico di questo giorno si sta ancora raccogliendo: ogni aggiornamento aggiunge un punto.</p>`;
  const W0 = 320, H0 = 128, padL = 28, padR = 8, top = 8, mid = 76, bot = 110;
  const ts = snaps.map((s) => Date.parse(s[0].replace("Z", ":00Z")));
  const t0 = ts[0], t1 = Math.max(ts[ts.length - 1], t0 + 1);
  const x = (t) => padL + ((t - t0) / (t1 - t0)) * (W0 - padL - padR);
  const temps = snaps.flatMap((s) => [s[1], s[2]]).filter((v) => v != null);
  const lo = Math.min(...temps) - 1, hi = Math.max(...temps) + 1;
  const y = (v) => top + (1 - (v - lo) / (hi - lo)) * (mid - top);
  const poly = (k, cls) => {
    const p = snaps.map((s, i) => (s[k] != null ? `${x(ts[i]).toFixed(1)},${y(s[k]).toFixed(1)}` : null)).filter(Boolean);
    return p.length > 1 ? `<polyline points="${p.join(" ")}" class="${cls}"/>` : "";
  };
  const bars = snaps.map((s, i) => (s[3] == null ? "" : `<rect x="${(x(ts[i]) - 2).toFixed(1)}" y="${(bot - (s[3] / 100) * 26).toFixed(1)}" width="4" height="${((s[3] / 100) * 26).toFixed(1)}" class="h-rain"/>`)).join("");
  const first = snaps[0], last = snaps[snaps.length - 1];
  const ticks = [lo + 1, hi - 1].map((v) => `<text x="${padL - 6}" y="${(y(v) + 4).toFixed(1)}" class="h-tick" text-anchor="end">${Math.round(v)}°</text>`).join("");
  const svg = `<svg viewBox="0 0 ${W0} ${H0}" class="hist" role="img" aria-label="Come è cambiata la previsione">
    ${ticks}<line x1="${padL}" x2="${W0 - padR}" y1="${bot}" y2="${bot}" class="h-axis"/>${bars}${poly(2, "line line-max")}${poly(1, "line line-min")}
    <text x="${padL}" y="${H0}" class="h-tick">${esc(whenText(ts[0]))}</text>
    <text x="${W0 - padR}" y="${H0}" class="h-tick" text-anchor="end">ora</text></svg>`;
  const parts = [];
  if (first[2] != null && last[2] != null) parts.push(`massima ${deg(first[2])}, ora ${deg(last[2])}`);
  if (first[3] != null && last[3] != null) parts.push(`pioggia ${Math.round(first[3])}%, ora ${Math.round(last[3])}%`);
  return `<p>${esc(cap(whenText(ts[0])))} la previsione diceva: ${parts.join("; ")}.</p>${svg}
    <p class="legend"><span><i class="lg-max"></i>massima</span><span><i class="lg-min"></i>minima</span><span><i class="f2"></i>probabilità di pioggia</span></p>`;
}

function modelsBlock(d) {
  const rows = Object.entries(d.modelli || {}).map(([sid, m]) => `<tr${m.escluso ? ' class="out"' : ""}><th scope="row">${MODELS[sid] || sid}${m.escluso ? ' <small title="Molto diverso dagli altri modelli: non entra nella media">escluso dalla media</small>' : ""}</th>
    <td class="n t-min">${deg(m.min)}</td><td class="n t-max">${deg(m.max)}</td><td class="n">${m.mm == null ? "–" : m.mm.toFixed(1).replace(".", ",") + " mm"}</td></tr>`).join("");
  return `<table class="models-t"><thead><tr><th scope="col">Modello</th><th scope="col" class="n">Min</th><th scope="col" class="n">Max</th><th scope="col" class="n">Pioggia</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function chartsLink(d) {
  const M = window.VENTAGLIO_MANIFEST;
  const E = M && M.models && M.models.ecmwf;
  if (!E) return "";
  const noon = Date.parse(d.data + "T12:00:00Z");
  const lead = Math.round((noon - Date.parse(E.run)) / 36e5 / 6) * 6;
  if (lead < 0) return "";
  const chart = (d.pioggia?.p ?? 0) >= 30 ? "prec6" : "t850";
  return `<a class="to-charts" href="#carte/ecmwf/italia/${chart}/${lead}">Guarda la cartografia di ${esc(dayName(d.data))}</a>`;
}

const ARROW = (dir) => `<svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true" class="w-arr" style="transform:rotate(${Math.round(dir + 180)}deg)"><path d="M6 1.2 9.6 10 6 8 2.4 10z"/></svg>`;
/** Ora per ora (oppure ogni 3 ore): ora, icona, temperatura, pioggia, vento. */
function hoursBlock(d, today) {
  const rows = hoursLeft(d);
  if (!rows.length) return fasceBlock(d);
  const step = rows[0][8];
  const nowH = hourNow();
  const temps = rows.map((r) => r[1]).filter((v) => v != null);
  const lo = Math.min(...temps), hi = Math.max(...temps);
  const waves = C.data && C.data.mare_km != null && rows.some((r) => r[9] != null);
  const cells = rows.map((r) => {
    const [h, t, mm, , kmh, dir, code, night, st, swh] = r;
    const rate = (mm || 0) / st;
    const lift = t == null || hi === lo ? 0 : ((t - lo) / (hi - lo)) * 14;
    const isNow = d.data === today && h === nowH;
    const wind = kmh == null ? "" : `<span class="h-w${kmh >= 30 ? " strong" : ""}" title="Vento ${num(kmh)} km/h">${dir == null ? "" : ARROW(dir)}${num(kmh)}</span>`;
    return `<li class="${night ? "night" : ""}${rate >= 0.2 ? " wet" : ""}">
      <span class="h-h">${isNow ? "Ora" : step === 1 ? h : String(h).padStart(2, "0") + ":00"}</span>
      ${icon(code, 30, !!night)}
      <span class="h-t" style="transform:translateY(${(-lift).toFixed(1)}px)">${deg(t)}</span>
      <span class="h-r" title="${esc(mmText(mm))}"><i style="height:${Math.min(22, rate >= 0.1 ? 3 + (rate / 4) * 19 : 0).toFixed(1)}px"></i><small>${mm >= 0.1 ? mmText(mm).replace(" mm", "") : ""}</small></span>
      ${wind}${waves ? `<span class="h-s" title="Onde ${swh == null ? "–" : mText(swh)}">${swh == null ? "" : swh.toFixed(1).replace(".", ",")}</span>` : ""}
    </li>`;
  }).join("");
  const sun = d.alba ? `<span class="sun">Alba ${d.alba.replace(/^0/, "")}, tramonto ${d.tramonto.replace(/^0/, "")}</span>` : "";
  return `<div class="hours"><div class="h-head"><h3>${step === 1 ? "Ora per ora" : "Ogni 3 ore"}</h3>${sun}</div>
    <ol class="h-strip${waves ? " sea" : ""}" aria-label="${step === 1 ? "Previsione ora per ora" : "Previsione ogni 3 ore"}">${cells}</ol>
    <p class="h-note">Millimetri di pioggia ${step === 1 ? "nell'ora" : "nelle 3 ore"}, vento in km/h${waves ? ", onde in metri" : ""}.</p></div>`;
}
function fasceBlock(d) {
  const fasce = (d.fasce || []).map((f, k) => f ? `<li>${icon(f.codice, 30, k === 0 || k === 3)}
      <span class="f-name">${FASCE[k]}</span><span class="f-t">${deg(f.t)}</span>
      <span class="f-p${f.p != null && f.p >= 50 ? " wet" : ""}">${f.p == null ? "" : f.mm >= 0.1 && f.p >= 25 ? mmText(f.mm) : ""}</span></li>` : "").join("");
  if (!fasce) return "";
  return `<div class="hours"><div class="h-head"><h3>Durante il giorno</h3>${d.alba ? `<span class="sun">Alba ${d.alba.replace(/^0/, "")}, tramonto ${d.tramonto.replace(/^0/, "")}</span>` : ""}</div>
    <ul class="fasce" aria-label="Fasce della giornata">${fasce}</ul>
    <p class="h-note">${d.data <= addDays(romeDate(), 5) ? "Il dettaglio ora per ora arriva con il prossimo aggiornamento dei modelli." : "Così lontano i modelli non danno ancora il dettaglio ora per ora."}</p></div>`;
}
function facts(d, data) {
  const out = [];
  const r = rainText(d), [noun] = rainNoun(d);
  if (r) out.push([noun, r.slice(noun.length + 1)]);
  const v = d.vento;
  if (v && v.kmh != null) out.push(["Vento", `${v.nome}, ${num(v.kmh)} km/h${v.raffiche >= 40 ? `, raffiche fino a ${num(Math.round(v.raffiche / 5) * 5)}` : ""}`]);
  const n = d.neve, p = d.pioggia?.p ?? 0;
  if (n && p >= 25 && snowNear(n, data)) out.push(["Quota neve", `circa ${num(n.quota)} m`]);
  if (d.mare && data && data.mare_km != null) out.push([data.mare_km >= 3 ? `Mare (a ${num(data.mare_km)} km)` : "Mare", seaText(d.mare)]);
  return `<dl class="facts">${out.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>`;
}
function detail(data, today) {
  const d = data.giorni[C.day];
  if (!d) return "";
  const st = d.incertezza?.stato || "quasi";
  const al = alertOf(data.id, d.data);
  const more = sureText(d, today);
  const why = whyBlock(d, C.day > 0 ? dayName(data.giorni[C.day - 1].data, today) : "ieri") || chartsLinkBlock(d);
  return `<section class="detail" aria-live="polite">
    <div class="d-head">
      <h2>${esc(cap(dayName(d.data, today)))} <span>${esc(fDayMonth.format(dateObj(d.data)))}</span></h2>
      <p class="sentence">${esc(daySentence(d))}</p>
    </div>
    ${al ? `<p class="al-l al-${al.level}">${TRI}<span>${esc(cap(al.text))}. <a href="${esc(C.alerts.link)}" target="_blank" rel="noopener">Bollettino</a></span></p>` : ""}
    ${facts(d, data)}
    ${hoursBlock(d, today)}
    ${mountainBlock(d, data)}
    <div class="d-grid">
      ${why ? `<div class="d-col">${why}</div>` : ""}
      <div class="d-col"><h3>${fan(st, 28)} ${STATE[st]}</h3>
        <p><b>${cap(SURE[st])}.</b> ${st === "deciso" ? "Modelli e scenari dicono la stessa cosa." : esc(more)}</p></div>
    </div>
    <details class="more"${C.more ? " open" : ""}><summary>Scenari, modelli e storico</summary>
      <div class="d-grid">
        <div class="d-col"><h3>Gli ${d.pioggia?.su || 81} scenari</h3>${scenarios(d)}
          <h3>Come è cambiata la previsione</h3>${historyBlock(data, d)}</div>
        <div class="d-col"><h3>Cosa dicono i modelli</h3>${modelsBlock(d)}
          <div id="rankBox">${rankBox(data)}</div>${(d.perche || []).length ? chartsLink(d) : ""}</div>
      </div>
    </details>
  </section>`;
}
function chartsLinkBlock(d) {
  const l = chartsLink(d);
  return l ? `<h3>La cartografia</h3><p>${l}</p>` : "";
}

function search(placeholder = "Cerca il tuo comune", extra = "") {
  return `<div class="search" role="search">
    <div class="combo">
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>
      <input type="search" id="q" autocomplete="off" spellcheck="false" placeholder="${placeholder}" aria-label="${placeholder}"
        role="combobox" aria-expanded="false" aria-controls="qList" aria-autocomplete="list">
      <ul id="qList" role="listbox" hidden></ul>
    </div>
    <button type="button" class="near" id="near" aria-label="Vicino a me">${locIcon()}<span>Vicino a me</span></button>${extra}
  </div>
  <p class="loc-msg" id="locMsg" role="status"></p>`;
}
const locIcon = () => `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="7.5"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"/></svg>`;

function wireSearch(root) {
  const q = root.querySelector("#q"), list = root.querySelector("#qList");
  if (!q) return;
  let items = [], act = -1;
  const prep = (arr) => arr.map((p) => ({ p, n: norm(p.nome), a: norm(p.altro), pr: norm(p.provincia), s: norm(p.sigla) }));
  let places = prep(C.index.luoghi);
  const more = () => loadComuni().then((all) => { places = prep(all); if (q.value) render(); }).catch(() => {});
  q.addEventListener("focus", more, { once: true });
  const pick = (p) => { list.hidden = true; q.setAttribute("aria-expanded", "false"); C.go(p.id); };
  const render = () => {
    const v = norm(q.value);
    if (!v) { list.hidden = true; q.setAttribute("aria-expanded", "false"); return; }
    items = places.map((x) => {
      let r = x.n.startsWith(v) ? 0 : x.n.split(" ").some((w) => w.startsWith(v)) ? 1 : x.n.includes(v) ? 2
        : x.a && x.a.includes(v) ? 2 : x.pr.startsWith(v) || x.s === v ? 3 : 9;
      return { x, r };
    }).filter((o) => o.r < 9).sort((a, b) => a.r - b.r || a.x.n.localeCompare(b.x.n)).slice(0, 8).map((o) => o.x.p);
    act = items.length ? 0 : -1;
    list.innerHTML = items.length
      ? items.map((p, i) => `<li role="option" id="opt${i}" aria-selected="${i === act}" data-i="${i}">${esc(p.nome)} <span>${esc(p.sigla)}, ${esc(p.regione)}</span></li>`).join("")
      : `<li class="none">Nessun comune con questo nome. Controlla come l'hai scritto.</li>`;
    list.hidden = false;
    q.setAttribute("aria-expanded", "true");
    q.setAttribute("aria-activedescendant", act >= 0 ? "opt0" : "");
  };
  q.addEventListener("input", render);
  q.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!items.length) return;
      e.preventDefault();
      act = (act + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      [...list.children].forEach((li, i) => li.setAttribute("aria-selected", i === act));
      q.setAttribute("aria-activedescendant", "opt" + act);
    } else if (e.key === "Enter" && act >= 0 && items[act]) { e.preventDefault(); pick(items[act]); }
    else if (e.key === "Escape") { list.hidden = true; q.setAttribute("aria-expanded", "false"); }
  });
  list.addEventListener("mousedown", (e) => { const li = e.target.closest("li[data-i]"); if (li) { e.preventDefault(); pick(items[+li.dataset.i]); } });
  q.addEventListener("blur", () => setTimeout(() => { list.hidden = true; q.setAttribute("aria-expanded", "false"); }, 150));
  root.querySelector("#near").addEventListener("click", () => locate(root));
}

function locate(root) {
  const msg = root.querySelector("#locMsg");
  if (!navigator.geolocation) { msg.textContent = "Questo browser non permette di leggere la posizione: cerca la città per nome."; return; }
  msg.textContent = "Cerco la tua posizione…";
  navigator.geolocation.getCurrentPosition(async (pos) => {
    const me = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    let list = C.index.luoghi;
    try { list = await loadComuni(); } catch (e) { /* si ripiega sui capoluoghi */ }
    let best = null;
    for (const p of list) { const d = km(me, p); if (!best || d < best.d) best = { p, d }; }
    if (!best) return;
    if (best.d > 25) store("nota", `Sembri fuori dall'Italia: il comune più vicino che conosciamo è ${best.p.nome}, a ${Math.round(best.d)} km.`);
    C.go(best.p.id);
  }, (err) => {
    msg.textContent = err.code === 1
      ? "Non hai dato il permesso di leggere la posizione: cerca la città per nome."
      : "Non riesco a trovare la posizione adesso: cerca la città per nome.";
  }, { timeout: 12000, maximumAge: 600000 });
}

// ---------- preferiti ----------
const favs = () => (Array.isArray(store("preferiti")) ? store("preferiti") : []);
const isFav = (id) => favs().some((f) => f.id === id);
function toggleFav(data) {
  const name = data.nome.split("/")[0];
  const list = isFav(data.id) ? favs().filter((f) => f.id !== data.id) : [...favs(), { id: data.id, nome: name }];
  store("preferiti", list.slice(-12));
  return isFav(data.id);
}
const STAR = `<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="m12 3.2 2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 17l-5.4 2.9 1.1-6.1-4.5-4.2 6.1-.8z"/></svg>`;
function favChips(current) {
  const f = favs();
  if (!f.length || (f.length === 1 && f[0].id === current)) return "";
  return `<nav class="fav-chips" aria-label="I tuoi preferiti">${f.map((x) => `<a href="#citta/${esc(x.id)}"${x.id === current ? ' aria-current="page"' : ""}>${esc(x.nome)}</a>`).join("")}</nav>`;
}
/** Riassunto di oggi per una scheda dei preferiti (i comuni delle zone richiedono la previsione della zona). */
async function favDay(f) {
  const p = C.index.luoghi.find((x) => x.id === f.id);
  if (p) return { ...p.giorni[0], p: p.giorni[0].p };
  const all = await loadComuni();
  const c = C.comuniById.get(f.id);
  if (!c) return null;
  const z = await getJSON(`data/${c.file}.json?u=${encodeURIComponent(C.index.aggiornato)}`);
  const d = (c.file.startsWith("celle/") ? adapt(z, c) : z).giorni[0];
  return d && { data: d.data, min: d.min, max: d.max, p: d.pioggia?.p, codice: d.codice, stato: d.incertezza?.stato };
}
function favCard(f, d) {
  const al = d && alertOf(f.id, d.data);
  const body = !d ? `<span class="fc-wait">…</span>`
    : `${icon(d.codice, 40)}<span class="fc-t"><b class="t-max">${deg(d.max)}</b> <span class="t-min">${deg(d.min)}</span></span>
       <span class="fc-r">${d.p == null ? "" : `Pioggia ${chance(d.p)}`}</span>${al ? `<span class="fc-al al-${al.level}">${TRI}Allerta ${LEVEL[al.level]}</span>` : ""}`;
  return `<a class="fav-card" href="#citta/${esc(f.id)}" data-id="${esc(f.id)}"><span class="fc-name">${esc(f.nome)}</span>${body}</a>`;
}
function fansExplain(cls = "") {
  return `<div class="fans ${cls}">
    <figure>${fan("deciso", 64)}<figcaption><b>Chiuso</b>previsione sicura</figcaption></figure>
    <figure>${fan("quasi", 64)}<figcaption><b>Socchiuso</b>abbastanza sicura</figcaption></figure>
    <figure>${fan("aperto", 64)}<figcaption><b>Aperto</b>ancora incerta</figcaption></figure>
  </div>`;
}
function introCard() {
  if (store("spiegato")) return "";
  return `<aside class="intro" id="intro">
    ${fansExplain("small")}
    <div><p><b>${MOTTO}</b> Ogni giorno ha il suo ventaglio. Confrontiamo 81 scenari del tempo:
      se dicono tutti la stessa cosa il ventaglio è chiuso e la previsione è sicura. Più si apre, più il tempo può cambiare.</p>
      <button type="button" class="ok" id="introOk">Ho capito</button> <a href="#come-funziona">Come funziona</a></div>
  </aside>`;
}

// ---------- scheda da condividere ----------
const SHARE = `<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d="M12 15V3.5M7.5 8 12 3.5 16.5 8M5 12.5V19a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19v-6.5"/></svg>`;
/** Disegna su una tela 1080×1350 la previsione dei prossimi giorni, come immagine da mandare o pubblicare. */
async function drawCard(data) {
  if (document.fonts) { try { await document.fonts.ready; } catch (e) { /* va bene anche senza */ } }
  const W = 1080, H = 1350, cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  const g = cv.getContext("2d");
  if (!g.roundRect) g.roundRect = function (x, y, w, h) { this.rect(x, y, w, h); };
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const ink = "#13283D", paper = "#E9EEF1", max = "#C8102E", min = "#0B4EA2", muted = "#5A6A79", rain = "#1C7C93";
  const F = (w, size, wdth = 100) => `${w} ${size}px ${css("--font") || "Archivo, Arial Narrow, sans-serif"}`;
  g.fillStyle = paper; g.fillRect(0, 0, W, H);
  const img = (svg, x, y, size) => new Promise((ok) => {
    const im = new Image();
    const styled = svg.replace("<svg ", `<svg xmlns="http://www.w3.org/2000/svg" style="--panel:#fff;--ink:${ink};--muted:${muted};--sun:#E3A21A;--moon:#8E9DAC;--cloud-dark:#B3BEC8;--rain:${rain};--min:${min};--bassa:${max};--fan-a:#C9D7E2;--fan-b:#fff" `)
      .replace(/<svg([^>]*)>/, `<svg$1><style>.i-sun{fill:#E3A21A}.i-ray{stroke:#E3A21A;stroke-width:1.7;stroke-linecap:round}.i-moon{fill:#8E9DAC}.i-cloud{fill:#fff;stroke:${ink};stroke-width:1.5;stroke-linejoin:round}.i-back{stroke:${muted}}.i-dark{fill:#B3BEC8}.i-drop{stroke:${rain};stroke-width:1.8;stroke-linecap:round}.i-flake path{stroke:${min};stroke-width:1.3;stroke-linecap:round}.i-bolt{fill:#E3A21A;stroke:${ink};stroke-width:.6}.fan-rib,.fan-arc{fill:none;stroke:${ink};stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}.fan-p0{fill:#C9D7E2}.fan-p1{fill:#fff}.fan-pin{fill:${max}}</style>`);
    im.onload = () => { g.drawImage(im, x, y, size, size * (im.height / im.width || 1)); ok(); };
    im.onerror = () => ok();
    im.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(styled);
  });
  const today = romeDate();
  const days = data.giorni.filter((d) => d.data >= today);
  const d0 = days[0];
  // testata
  await img(fan("aperto", 60), 64, 70, 76);
  g.fillStyle = ink; g.font = F(700, 40); g.fillText("Ventaglio", 152, 112);
  g.font = F(600, 26); g.fillStyle = min; g.fillText(MOTTO, 64, 170);
  g.fillStyle = ink; g.font = F(700, 104);
  const name = data.nome.split("/")[0];
  let fs = 104; while (g.measureText(name).width > W - 128 && fs > 56) { fs -= 4; g.font = F(700, fs); }
  g.fillText(name, 64, 300);
  g.font = F(400, 28); g.fillStyle = muted;
  g.fillText(`${cap(fWeek.format(dateObj(d0.data)))} ${fDayMonth.format(dateObj(d0.data))}`, 64, 348);
  // oggi in grande
  g.fillStyle = "#fff"; g.beginPath(); g.roundRect(48, 390, W - 96, 380, 28); g.fill();
  await img(icon(d0.codice, 64), 88, 430, 210);
  g.font = F(700, 150); g.fillStyle = max; g.fillText(deg(d0.max), 330, 570);
  const wmax = g.measureText(deg(d0.max)).width;
  g.font = F(700, 80); g.fillStyle = min; g.fillText(deg(d0.min), 350 + wmax, 570);
  g.font = F(600, 34); g.fillStyle = ink; g.fillText(LABEL[d0.codice] || "", 330, 630);
  const rt = rainText(d0);
  g.font = F(500, 28); g.fillStyle = (d0.pioggia?.p ?? 0) >= 50 ? rain : muted;
  if (rt) g.fillText(rt.length > 52 ? rt.slice(0, 50) + "…" : rt, 330, 680);
  const st = d0.incertezza?.stato || "quasi";
  await img(fan(st, 40), 88, 686, 58);
  g.font = F(600, 28); g.fillStyle = ink; g.fillText(`${STATE[st]}: ${SURE[st]}`, 160, 726);
  // i giorni dopo
  const next = days.slice(1, 5), colW = (W - 96) / next.length;
  for (let i = 0; i < next.length; i++) {
    const d = next[i], x = 48 + i * colW, cx = x + colW / 2;
    g.fillStyle = "#fff"; g.beginPath(); g.roundRect(x + 6, 800, colW - 12, 400, 24); g.fill();
    g.textAlign = "center"; g.fillStyle = ink; g.font = F(700, 32);
    g.fillText(cap(dayName(d.data, today)).split(" ")[0], cx, 852);
    await img(icon(d.codice, 64), cx - 60, 872, 120);
    g.font = F(700, 52); g.fillStyle = max; g.fillText(deg(d.max), cx, 1050);
    g.font = F(700, 36); g.fillStyle = min; g.fillText(deg(d.min), cx, 1098);
    const p = d.pioggia?.p ?? 0;
    g.font = F(600, 24); g.fillStyle = p >= 50 ? rain : muted;
    g.fillText(p >= 25 && d.pioggia?.mm >= 0.1 ? mmText(d.pioggia.mm) : p >= 25 ? "pioggia possibile" : "asciutto", cx, 1140);
    await img(fan(d.incertezza?.stato || "quasi", 40), cx - 30, 1150, 60);
    g.textAlign = "left";
  }
  g.font = F(400, 24); g.fillStyle = muted;
  g.fillText("francescougenti.github.io/carte-meteo", 64, 1290);
  g.textAlign = "right"; g.fillText(`Aggiornato ${whenText(Date.parse(data.aggiornato))}`, W - 64, 1290); g.textAlign = "left";
  return new Promise((ok) => cv.toBlob(ok, "image/png"));
}
async function shareCard(data) {
  const blob = await drawCard(data);
  if (!blob) return;
  const name = data.nome.split("/")[0];
  const file = new File([blob], `ventaglio-${data.id}.png`, { type: "image/png" });
  const url = `${location.origin}${location.pathname}#citta/${data.id}`;
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], title: `Il meteo di ${name}`, text: `Il meteo di ${name} su Ventaglio: ${url}` }); return; }
    catch (e) { if (e && e.name === "AbortError") return; }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = file.name;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  window.dispatchEvent(new CustomEvent("ventaglio:toast", { detail: "Immagine scaricata: puoi mandarla o pubblicarla" }));
}

// ---------- pagine ----------
function homePage() {
  const byReg = new Map();
  for (const p of C.index.luoghi) {
    if (!byReg.has(p.regione)) byReg.set(p.regione, []);
    byReg.get(p.regione).push(p);
  }
  const regs = [...byReg.keys()].sort((a, b) => a.localeCompare(b, "it"));
  const lists = regs.map((r) => `<div class="reg"><h3>${esc(r.split("/")[0])}</h3><p>${byReg.get(r).sort((a, b) => a.nome.localeCompare(b.nome, "it"))
    .map((p) => `<a href="#citta/${p.id}">${esc(p.nome.split("/")[0])}</a>`).join(" ")}</p></div>`).join("");
  const f = favs();
  const favBlock = f.length ? `<section class="favs"><h2>I tuoi preferiti</h2><div class="fav-grid">${f.map((x) => favCard(x, null)).join("")}</div></section>` : "";
  return `<section class="home">
    <div class="home-top">
      <div><h1 class="brand-big">Ventaglio</h1>
        <p class="motto">${MOTTO}</p></div>
      ${fansExplain()}
    </div>
    <p class="lede">Il meteo del tuo comune e quanto è sicuro. Più il ventaglio di un giorno è chiuso, più puoi fidarti della previsione.</p>
    ${search("Cerca il tuo comune")}
    ${favBlock}
    <div class="cards2">
      <a class="radar-card" href="#radar">${RADAR_ICON}<span><b>Radar della pioggia</b>Dove piove adesso in Italia, dalla Protezione Civile</span></a>
      <a class="radar-card" href="#neve">${SNOW_ICON}<span><b>Neve e piste</b>Comprensori aperti, impianti e neve a valle e in quota</span></a>
    </div>
    <h2 class="regs-title">I capoluoghi</h2>
    <div class="regs">${lists}</div>
    <p class="explain">Per ogni giorno confrontiamo quattro modelli e 81 scenari dell'atmosfera, e ti diciamo quando conviene ricontrollare. <a href="#come-funziona">Come funziona</a></p>
  </section>`;
}
const SNOW_ICON = `<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true" class="radar-i"><path d="M2.5 19.5 9 9l3.5 5 2.5-3.5 6.5 9z"/><path d="m7.4 11.6 1.6.9 1.4-1.1M13.8 12.3l1.3.4 1.1-.9"/></svg>`;
const RADAR_ICON = `<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true" class="radar-i"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 18.4 5.6"/><circle cx="15.5" cy="8.6" r="1.4" class="blip"/></svg>`;

function cityPage(data) {
  const today = romeDate();
  const note = changeNote(data, today);
  const up = Date.parse(data.aggiornato);
  const first = (x) => String(x || "").split("/")[0];
  const prov = first(data.provincia), reg = first(data.regione);
  const where = [prov && prov !== first(data.nome) && prov !== reg ? `provincia di ${prov}` : null, reg,
    data.alt != null ? `${num(data.alt)} m` : null].filter(Boolean).join(", ");
  const nota = store("nota");
  if (nota) store("nota", null);
  const fav = isFav(data.id);
  const zone = data.zona ? ` Previsione della zona intorno, adattata alla quota del comune.` : "";
  return `<section class="city">
    <header class="c-head">
      <div class="c-title">
        <h1${data.nome.split("/")[0].length > 10 ? ' class="long"' : ""}>${esc(data.nome.split("/")[0])}<button type="button" class="share" id="share" aria-label="Condividi la previsione" title="Condividi la previsione">${SHARE}</button><button type="button" class="star" id="star" aria-pressed="${fav}" aria-label="${fav ? "Togli dai preferiti" : "Aggiungi ai preferiti"}" title="${fav ? "Togli dai preferiti" : "Aggiungi ai preferiti"}">${STAR}</button></h1>
        <p class="where">${esc(where)}. Aggiornato ${esc(whenText(up))}.${zone}</p>
      </div>
      <div class="c-tools">${search("Cerca un altro comune", `<a class="radar-btn" href="#radar/${esc(data.id)}">${RADAR_ICON}<span>Radar</span></a>`)}</div>
    </header>
    ${favChips(data.id)}
    ${nota ? `<p class="note">${esc(nota)}</p>` : ""}
    ${navigator.onLine === false ? `<p class="note">Sei offline: questa è l'ultima previsione scaricata, aggiornata ${esc(whenText(up))}.</p>` : ""}
    ${alertBanner(data, today)}
    ${introCard()}
    ${snowBox(data)}
    ${hero(data, today)}
    <div id="stationBox">${stationLine(data)}</div>
    ${changesBlock(note)}
    ${fanChart(data, today)}
    <div id="detail">${detail(data, today)}</div>
    <div id="cams"></div>
    <p class="motto-foot">${fan("deciso", 22)} ${MOTTO}</p>
  </section>`;
}

function infoPage() {
  return `<article class="info">
    <h1>Come funziona Ventaglio</h1>
    <p class="lede">${MOTTO} Una previsione del tempo non è mai una certezza: Ventaglio ti dice, giorno per giorno, quanto puoi fidarti.</p>
    <h2>Perché si chiama Ventaglio</h2>
    ${fansExplain()}
    <p>Per ogni giorno non c'è una sola previsione ma tante: 81 scenari, cioè simulazioni dell'atmosfera che partono da condizioni appena diverse.
      Se arrivano tutti allo stesso tempo, il ventaglio di quel giorno è <b>chiuso</b> e la previsione è sicura. Se si dividono, il ventaglio si apre:
      <b>socchiuso</b> quando la previsione è abbastanza sicura, <b>aperto</b> quando il tempo può ancora andare in modi diversi.
      Nel grafico dei prossimi giorni lo vedi anche nelle fasce colorate delle temperature: più si allargano, più il ventaglio è aperto.</p>
    <h2>Da dove vengono i dati</h2>
    <p>Ogni volta che i centri meteo pubblicano una nuova corsa, il sito scarica i dati e rifà i conti da solo. Usiamo quattro modelli:
      ECMWF IFS (il centro europeo), ECMWF AIFS (il suo modello a intelligenza artificiale), GFS (NOAA, Stati Uniti) e ICON-EU (servizio meteo tedesco, solo i primi 5 giorni).
      Massime, minime e quantità di pioggia sono una media pesata dei quattro, con la temperatura corretta per l'altitudine della città.</p>
    <h2>Gli scenari</h2>
    <p>Oltre ai modelli "singoli", ECMWF e NOAA fanno girare lo stesso modello molte volte partendo da condizioni leggermente diverse: 50 volte il modello europeo, 31 l'americano.
      Ognuna di queste simulazioni è uno scenario possibile. La probabilità di pioggia è semplicemente il numero di scenari in cui piove almeno 1 mm nella giornata, su 81.
      Le fasce colorate del grafico mostrano dove cadono massime e minime in 8 scenari su 10.</p>
    <h2>Quando il ventaglio è chiuso</h2>
    <p>Il ventaglio è <b>chiuso</b> quando gli scenari vanno d'accordo: piove in meno di 2 su 10 o in più di 8 su 10, e la massima sta in una forbice di 4 gradi.
      Altrimenti è <b>socchiuso</b> o <b>aperto</b>, secondo quanto si dividono.</p>
    <h2>Probabilità a parole</h2>
    <p>La pioggia è <i>quasi certa</i> quando piove almeno 1 mm in 9 scenari su 10 o più, <i>molto probabile</i> da 7 su 10, <i>probabile</i> da 5 su 10,
      <i>possibile</i> da 1 su 4, <i>poco probabile</i> da 1 su 10, altrimenti <i>improbabile</i>. I millimetri sono la media pesata dei modelli.
      Il conto degli scenari, giorno per giorno, è in "Scenari, modelli e storico", sotto il dettaglio di ogni giorno.</p>
    <h2>Ora per ora</h2>
    <p>Toccando un giorno si apre il dettaglio ora per ora: per oggi, domani e dopodomani ogni ora, poi ogni 3 ore fino al sesto giorno.
      Viene da ICON-EU (ogni ora fino a 3 giorni), ECMWF IFS e GFS (ogni 3 ore). Le ore di pioggia, come "tra le 15 e le 18", sono le ore consecutive
      in cui i modelli fanno cadere almeno 0,2 mm all'ora: sono indicative, soprattutto per i temporali.</p>
    <h2>Quando lo saprai</h2>
    <p>Misuriamo, sulle previsioni di oggi per tutte le città, quanto si restringono di solito gli scenari man mano che un giorno si avvicina.
      Da qui stimiamo il giorno in cui la previsione per la tua data dovrebbe diventare decisa e ti suggeriamo di ricontrollare quella sera, quando arrivano le corse del pomeriggio.
      È una stima: a volte una situazione resta incerta fino all'ultimo, e in quel caso te lo diciamo.</p>
    <h2>Cosa è cambiato</h2>
    <p>Il sito conserva ogni aggiornamento della previsione degli ultimi giorni. Per questo può mostrarti come è cambiata la previsione per un giorno e cosa è diverso da ieri.
      Ricorda anche cosa avevi visto all'ultima visita: questa informazione resta solo nel tuo browser, non viene inviata a nessuno, e lo stesso vale per la posizione se usi "Vicino a me".</p>
    <h2>I limiti</h2>
    <p>I modelli hanno maglie di 7–25 km: valli strette, coste e temporali locali possono andare diversamente. Le temperature del giorno sono stimate dai valori ogni 6 ore e dai massimi e minimi dei modelli quando ci sono.
      Per chi vuole vedere tutto c'è l'area <a href="#carte">Appassionati meteo</a>, con la cartografia dei modelli, i confronti, gli ensemble e i meteogrammi.</p>
    <h2>Tutti i comuni</h2>
    <p>I capoluoghi di provincia hanno una previsione calcolata esattamente nel loro punto. Gli altri comuni sono raggruppati in zone di circa 25 km, la maglia dei modelli globali:
      la previsione si calcola una volta per zona e il sito la adatta alla quota del tuo comune, con temperature più basse di circa 6,5 gradi ogni 1.000 metri
      e la neve al posto della pioggia quando il comune è sopra la quota neve.</p>
    <h2>Il perché, con la carta</h2>
    <p>Per ogni giorno Ventaglio cerca la causa principale del tempo che farà: aria più fredda o più calda in arrivo (e da dove), una bassa pressione, l'alta pressione,
      aria instabile, vento forte, lo zero termico basso. Te la spiega in una frase e ti mostra la carta dei modelli che la fa vedere, la stessa che guardano gli appassionati.</p>
    <h2>Radar e allerte</h2>
    <p>Il <a href="#radar">radar</a> mostra dove piove adesso, con l'ultima ora animata: sono i dati della rete radar nazionale del Dipartimento della Protezione Civile.
      Le allerte vengono dal bollettino nazionale di criticità idrogeologica e idraulica della Protezione Civile, che esce ogni giorno nel primo pomeriggio e vale per oggi e domani:
      se il tuo comune è in una zona con allerta gialla, arancione o rossa, lo vedi in cima alla pagina. Per le decisioni contano gli avvisi ufficiali della tua regione e del tuo comune.</p>
    <h2>Il mare</h2>
    <p>Per i comuni a meno di 12 km dalla costa Ventaglio mostra lo stato del mare, con le parole della scala Douglas (calmo, poco mosso, mosso, molto mosso, agitato...)
      e l'altezza delle onde, anche ora per ora. Viene dal modello d'onda di ECMWF, ogni 3 ore per 6 giorni, nel punto di mare più vicino al comune:
      è il mare al largo, sotto costa e nelle baie può essere più calmo.</p>
    <h2>Montagna, neve e piste</h2>
    <p>Per i comuni sopra i 700 metri o vicini a un comprensorio sciistico c'è il riquadro "In montagna": zero termico, quota neve, neve fresca prevista,
      temperatura e vento a 1.500 metri e i comprensori vicini. La pagina <a href="#neve">Neve e piste</a> dice quanti comprensori, impianti e chilometri di piste sono aperti
      e quanta neve c'è a valle e in quota, dai bollettini dei comprensori raccolti da LiftRadar due volte al giorno (per ora Alpi centrali e orientali e Valle d'Aosta).</p>
    <h2>Centraline e webcam</h2>
    <p>Quando c'è una centralina della rete MeteoNetwork entro 12 km e a una quota simile, sotto la previsione di oggi vedi cosa misura adesso.
      Le webcam vicine vengono da Windy.com. Con il pulsante di condivisione accanto al nome del comune ottieni un'immagine con la previsione da mandare o pubblicare.</p>
    <h2>Preferiti</h2>
    <p>Con la stella accanto al nome aggiungi un comune ai preferiti: li ritrovi nella pagina iniziale e in cima alla pagina di ogni comune. Restano solo in questo browser.</p>
    <h2>IA contro fisica</h2>
    <p>Ogni giorno confrontiamo le massime e le minime previste da ciascun modello con quelle misurate negli aeroporti italiani, per capire chi ci prende di più:
      il modello a intelligenza artificiale AIFS o i modelli fisici. <a href="#ia-contro-fisica">Guarda la classifica</a>.</p>
    <h2>Sul telefono, come un'app</h2>
    <p>Ventaglio si installa sulla schermata iniziale e si apre come un'app, anche con la connessione lenta: mostra l'ultima previsione scaricata.
      Su Android e sui computer usa il pulsante "Installa" in alto, oppure il menu del browser. Su iPhone e iPad, in Safari: tocca Condividi, poi "Aggiungi alla schermata Home".</p>
    <h2>Fonti e licenze</h2>
    <p>ECMWF Open Data (IFS, AIFS, ENS), licenza CC BY 4.0. NOAA/NCEP (GFS, GEFS), pubblico dominio. Deutscher Wetterdienst (ICON-EU). Elenco dei comuni: dati ISTAT tramite Garda Informatica (licenza MIT).
      Radar e bollettino di criticità: Dipartimento della Protezione Civile, licenza CC BY 4.0. Mappa di base del radar: © OpenStreetMap contributors, © CARTO.
      Onde: modello d'onda ECMWF (Open Data, CC BY 4.0). Comprensori sciistici: LiftRadar, dai bollettini dei comprensori; pericolo valanghe AINEVA ed Euregio.
      Centraline: MeteoNetwork (CC BY 4.0). Webcam: Windy.com.
      Quote dal modello digitale del terreno AWS Terrain Tiles. Previsioni e grafici sono un'elaborazione di questo sito, non prodotti ufficiali degli enti.</p>
  </article>`;
}

// ---------- IA contro fisica ----------
const SHORT = { ecmwf: "ECMWF IFS", aifs: "AIFS", gfs: "GFS", "icon-eu": "ICON-EU" };
const LEADS = { 1: "a 1 giorno", 3: "a 3 giorni", 5: "a 5 giorni" };
const MIN_DAYS = 7;
async function loadRanking() {
  if (!C.rank || Date.now() - C.rankAt > 30 * 60e3) {
    C.rank = await getJSON(`data/verifica/classifica.json?u=${encodeURIComponent((C.index && C.index.aggiornato) || Date.now())}`);
    C.rankAt = Date.now();
  }
  return C.rank;
}
const IT_NAMES = { Florence: "Firenze", Milan: "Milano", Naples: "Napoli", Rome: "Roma", Venice: "Venezia", Genoa: "Genova", Turin: "Torino", Forli: "Forlì" };
const stationName = (n) => String(n || "").split(",")[0].replace(/\s+(Arpt|Airport|Intl|Island)\b/g, "").replace("/", " ").trim()
  .replace(/^[A-Za-z]+/, (w) => IT_NAMES[w] || w);
const dec = (v, nd = 1) => (v == null ? "–" : v.toFixed(nd).replace(".", ","));
function nearestStation(cl, p, maxKm = 50) {
  let best = null;
  for (const [icao, st] of Object.entries(cl.stazioni || {})) {
    if (st.lat == null) continue;
    const d = km(p, st);
    if (d <= maxKm && (!best || d < best.d)) best = { icao, st, d };
  }
  return best;
}
function readyDate(cl) {
  const start = cl.dal || romeDate();
  return fDayMonth.format(dateObj(addDays(start, 30)));
}
function sortedModels(t) {
  return Object.entries(t || {}).sort((a, b) => a[1].errore - b[1].errore);
}
/** Riquadro nella pagina della città: chi ci prende di più alla stazione più vicina. */
function rankBox(data) {
  const cl = C.rank;
  if (!cl) return `<h3>Chi ci prende di più</h3><p class="muted">…</p>`;
  const near = nearestStation(cl, data);
  const link = `<a href="#ia-contro-fisica${near ? "/" + near.icao : ""}">IA contro fisica</a>`;
  if ((cl.giorni || 0) < MIN_DAYS) {
    return `<h3>Chi ci prende di più</h3><p>Stiamo confrontando ogni giorno le previsioni dei modelli con le temperature misurate negli aeroporti.
      La classifica sarà affidabile verso il ${esc(readyDate(cl))}. ${link}</p>`;
  }
  const where = near ? `alla stazione di ${esc(stationName(near.st.nome))} (${Math.round(near.d)} km)` : "in Italia";
  const t = near ? near.st.anticipo?.["1"] : cl.italia?.["1"];
  const rows = sortedModels(t);
  if (!rows.length) return "";
  const [bid, b] = rows[0];
  const ai = t.aifs;
  const aiTxt = bid === "aifs" ? "il modello a intelligenza artificiale batte i modelli fisici"
    : ai ? `AIFS, l'intelligenza artificiale, sbaglia in media di ${dec(ai.errore)}°` : "";
  return `<h3>Chi ci prende di più</h3><p>Negli ultimi ${near ? near.st.giorni : cl.giorni} giorni, ${where}, il più preciso con un giorno di anticipo è
    <b>${SHORT[bid]}</b>: sbaglia massime e minime in media di ${dec(b.errore)}°${aiTxt ? `; ${aiTxt}` : ""}. ${link}</p>`;
}
function rankingPage(focus) {
  const cl = C.rank;
  const lead = String(C.lead || 1);
  const n = Object.keys(cl.stazioni || {}).length;
  const few = (cl.giorni || 0) < MIN_DAYS;
  const status = few
    ? `<p class="note">Raccolta in corso: ${cl.giorni || 0} ${cl.giorni === 1 ? "giorno verificato" : "giorni verificati"}. La classifica comincia a dire qualcosa dopo una settimana
        e diventa affidabile dopo circa un mese, verso il ${esc(readyDate(cl))}. Fino ad allora i numeri qui sotto sono provvisori.</p>`
    : `<p class="muted">Ultimi ${cl.giorni} giorni, dal ${esc(fDayMonth.format(dateObj(cl.dal)))} al ${esc(fDayMonth.format(dateObj(cl.al)))}.</p>`;
  const tabs = Object.entries(LEADS).map(([k, v]) => `<button type="button" data-lead="${k}" aria-pressed="${k === lead}">${v}</button>`).join("");
  const table = (t, big) => {
    const rows = sortedModels(t);
    if (!rows.length) return `<p class="muted">Ancora nessun giorno da confrontare.</p>`;
    const worst = Math.max(...rows.map(([, m]) => m.errore), 0.1);
    return `<ol class="rank${big ? " big" : ""}">${rows.map(([sid, m]) => {
      const bias = Math.abs(m.scarto) >= 0.5 ? ` Tende a prevedere ${m.scarto > 0 ? "più caldo" : "più freddo"} del vero (in media ${dec(Math.abs(m.scarto))}°).` : "";
      const win = m.gare ? ` Il più vicino al vero nel ${Math.round((100 * m.vinti) / m.gare)}% dei casi.` : "";
      return `<li class="${m.tipo}"><span class="r-name">${SHORT[sid] || sid}<small>${m.tipo === "ia" ? "intelligenza artificiale" : "modello fisico"}</small></span>
        <span class="r-bar"><i style="width:${Math.max(4, (100 * m.errore) / worst)}%"></i></span>
        <span class="r-val">${dec(m.errore)}°</span>${big ? `<span class="r-note">${win}${bias}</span>` : ""}</li>`;
    }).join("")}</ol>`;
  };
  const stations = Object.entries(cl.stazioni || {}).sort((a, b) => stationName(a[1].nome).localeCompare(stationName(b[1].nome), "it"));
  const stRows = stations.map(([icao, st]) => {
    const rows = sortedModels(st.anticipo?.[lead]);
    if (!rows.length) return "";
    const [bid, b] = rows[0];
    const ai = st.anticipo[lead].aifs;
    return `<tr id="st-${icao}"${icao === focus ? ' class="focus"' : ""}><th scope="row">${esc(stationName(st.nome))}</th><td class="n">${st.giorni}</td>
      <td>${SHORT[bid]}${bid === "aifs" ? ' <span class="tag-ia">IA</span>' : ""}</td><td class="n">${dec(b.errore)}°</td><td class="n">${ai ? dec(ai.errore) + "°" : "–"}</td></tr>`;
  }).join("");
  return `<article class="info rankpage">
    <h1>IA contro fisica</h1>
    <p class="lede">AIFS, il modello a intelligenza artificiale del centro europeo ECMWF, contro tre modelli fisici tradizionali.
      Ogni giorno confrontiamo le temperature massime e minime previste con quelle misurate in ${n} aeroporti italiani.</p>
    ${status}
    <div class="lead-tabs" role="group" aria-label="Anticipo della previsione">${tabs}</div>
    <h2>Tutta Italia</h2>
    <p class="muted">Errore medio di massime e minime: più corta è la barra, più il modello ci prende.</p>
    ${table(cl.italia?.[lead], true)}
    <h2>Aeroporto per aeroporto</h2>
    <table class="models-t st-t"><thead><tr><th scope="col">Stazione</th><th scope="col" class="n">Giorni</th><th scope="col">Il più preciso</th>
      <th scope="col" class="n">Errore</th><th scope="col" class="n">AIFS</th></tr></thead><tbody>${stRows}</tbody></table>
    <h2>Come si calcola</h2>
    <p>Le osservazioni sono i bollettini METAR degli aeroporti (NOAA Aviation Weather Center): massima e minima del giorno, in ore UTC, con almeno 18 misure.
      Le previsioni sono quelle delle corse delle 00 UTC, lette nel punto esatto di ogni aeroporto e corrette per la sua quota, con 1, 3 o 5 giorni di anticipo
      (ICON-EU arriva a 5 giorni solo in parte). L'errore è la media delle differenze, in valore assoluto, tra previsto e misurato.
      Si contano solo gli ultimi ${cl.finestra} giorni, quindi la classifica cambia con le stagioni.</p>
  </article>`;
}

// ---------- tutti i comuni ----------
async function loadComuni() {
  if (C.comuni) return C.comuni;
  const raw = await getJSON(`data/citta/comuni.json?u=${encodeURIComponent((C.index && C.index.aggiornato) || "")}`);
  const F = Object.fromEntries(raw.campi.map((k, i) => [k, i]));
  C.comuni = raw.comuni.map((r) => {
    const [provincia, regione] = raw.province[r[F.sigla]] || ["", ""];
    return { id: r[F.id], nome: r[F.nome], altro: r[F.altro] || null, sigla: r[F.sigla], provincia, regione,
      lat: r[F.lat], lon: r[F.lon], alt: r[F.alt], file: r[F.file], mare: F.mare == null ? null : r[F.mare] };
  });
  C.comuniById = new Map(C.comuni.map((c) => [c.id, c]));
  return C.comuni;
}
/** Adatta la previsione di una zona alla quota del comune (temperature) e ricalcola pioggia o neve. */
function adapt(zone, c) {
  const d = JSON.parse(JSON.stringify(zone));
  const dz = zone.alt != null && c.alt != null ? 0.0065 * (zone.alt - c.alt) : 0;
  const sh = (v) => (v == null ? v : Math.round((v + dz) * 10) / 10);
  const snowCode = (code, tmax, n, mm) => {
    if (!RAINY.includes(code) || !n || c.alt == null) return code;
    const rain = (mm ?? 0) >= 15 ? "pioggia-forte" : "pioggia";
    if (tmax != null && tmax >= 6) return code === "neve" || code === "pioggia-neve" ? rain : code;
    if (n.quota <= c.alt + 50) return "neve";
    if (n.quota <= c.alt + 350) return "pioggia-neve";
    return code === "neve" || code === "pioggia-neve" ? rain : code;
  };
  for (const g of d.giorni) {
    g.min = sh(g.min); g.max = sh(g.max);
    if (g.min_f) g.min_f = g.min_f.map(sh);
    if (g.max_f) g.max_f = g.max_f.map(sh);
    for (const m of Object.values(g.modelli || {})) { m.min = sh(m.min); m.max = sh(m.max); }
    g.codice = snowCode(g.codice, g.max, g.neve, g.pioggia?.mm);
    (g.fasce || []).forEach((f) => { if (f) { f.t = f.t == null ? f.t : Math.round(f.t + dz); f.codice = snowCode(f.codice, f.t, g.neve, (f.mm ?? 0) * 4); } });
    if (g.neve && g.max != null && g.max > 6) g.neve.suolo = 0;
    for (const r of g.ore || []) {  // [ora, t, mm, nubi, km/h, dir, icona, notte, passo]
      if (r[1] != null) r[1] = Math.round(r[1] + dz);
      if (RAINY.includes(r[6]) || r[6] === "rovesci") {
        const heavy = (r[2] || 0) / (r[8] || 1) >= 4;
        const code = snowCode(r[6] === "rovesci" ? "pioggia" : r[6], r[1], g.neve, heavy ? 99 : 0);
        r[6] = code === "pioggia" && r[6] === "rovesci" ? "rovesci" : code;
      }
    }
  }
  for (const snaps of Object.values(d.storia || {})) for (const s of snaps) { s[1] = sh(s[1]); s[2] = sh(s[2]); }
  if (c.mare == null) for (const g of d.giorni) { delete g.mare; for (const r of g.ore || []) r.length = Math.min(r.length, 9); }
  Object.assign(d, { mare_km: c.mare, id: c.id, nome: c.nome, altro: c.altro, sigla: c.sigla, provincia: c.provincia, regione: c.regione,
    lat: c.lat, lon: c.lon, alt: c.alt, zona: { id: zone.id, comuni: zone.comuni, alt: zone.alt } });
  return d;
}

// ---------- interfaccia pubblica ----------
async function loadIndex(force) {
  if (!C.index || force) C.index = await getJSON(`data/citta/indice.json?t=${Date.now()}`);
  return C.index;
}
function selectDay(root, i, scroll) {
  C.day = i;
  root.querySelectorAll(".col").forEach((x) => { const on = +x.dataset.i === i; x.classList.toggle("sel", on); x.setAttribute("aria-pressed", on); });
  root.querySelector("#detail").innerHTML = detail(C.data, romeDate());
  wireDetail(root);
  drawBands(root, C.data);
  const det = root.querySelector(".detail");
  if (scroll && det && det.getBoundingClientRect().top > innerHeight * 0.6) det.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}
function wireDetail(root) {
  const more = root.querySelector("details.more");
  if (more) more.addEventListener("toggle", () => { C.more = more.open; });
  const strip = root.querySelector(".h-strip");
  if (strip && C.day === 0) strip.scrollLeft = 0;
}
function wireCity(root) {
  root.querySelectorAll(".col").forEach((b) => b.addEventListener("click", () => selectDay(root, +b.dataset.i, true)));
  root.querySelectorAll(".now").forEach((a) => {
    a.addEventListener("click", (e) => { if (!e.target.closest("a")) selectDay(root, +a.dataset.i, true); });
    a.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectDay(root, +a.dataset.i, true); } });
  });
  const star = root.querySelector("#star");
  if (star) star.addEventListener("click", () => {
    const on = toggleFav(C.data);
    star.setAttribute("aria-pressed", on);
    star.setAttribute("aria-label", on ? "Togli dai preferiti" : "Aggiungi ai preferiti");
    star.title = star.getAttribute("aria-label");
    window.dispatchEvent(new CustomEvent("ventaglio:toast", { detail: on ? `${C.data.nome.split("/")[0]} è tra i preferiti` : "Tolto dai preferiti" }));
  });
  const sh = root.querySelector("#share");
  if (sh) sh.addEventListener("click", () => shareCard(C.data).catch(() => {}));
  const ok = root.querySelector("#introOk");
  if (ok) ok.addEventListener("click", () => { store("spiegato", true); root.querySelector("#intro").remove(); });
  wireDetail(root);
  drawBands(root, C.data);
  wireSearch(root);
}
window.addEventListener("resize", () => { if (C.root && C.data && !C.root.hidden) drawBands(C.root, C.data); });

window.Citta = {
  /** go(id): cambia città aggiornando l'indirizzo (la fornisce la pagina principale). */
  init(root, go) { C.root = root; C.go = go; },
  async home() {
    try { await loadIndex(); } catch (e) { C.root.innerHTML = notReady(); return; }
    C.data = null;
    C.root.innerHTML = homePage();
    wireSearch(C.root);
    if (favs().length) {
      loadAlerts().then(() => Promise.all(favs().map(async (f) => {
        let d = null;
        try { d = await favDay(f); } catch (e) { /* resta il nome */ }
        const el = C.root.querySelector(`.fav-card[data-id="${CSS.escape(f.id)}"]`);
        if (el) el.outerHTML = favCard(f, d || { codice: null });
      })));
    }
    document.title = "Ventaglio: il meteo della tua città e quanto è sicuro";
  },
  async open(id, keepDay) {
    try { await loadIndex(); } catch (e) { C.root.innerHTML = notReady(); return false; }
    let p = C.index.luoghi.find((x) => x.id === id), comune = null;
    if (!p) {
      try { await loadComuni(); } catch (e) { C.root.innerHTML = notReady(); return true; }
      comune = C.comuniById.get(id);
      if (!comune) return false;
      p = comune;
    }
    const token = (C.loading = id + Date.now());
    let data;
    const file = comune ? comune.file : `citta/${id}`;
    try {
      [data] = await Promise.all([getJSON(`data/${file}.json?u=${encodeURIComponent(C.index.aggiornato)}`), loadAlerts(), loadSki(), loadStations()]);
      if (comune && file.startsWith("celle/")) data = adapt(data, comune);
    } catch (e) { C.root.innerHTML = `<section class="home"><p class="note">Non riesco a caricare la previsione di ${esc(p.nome)}. Controlla la connessione e ricarica la pagina.</p></section>`; return true; }
    if (C.loading !== token) return true;
    if (!keepDay || !C.data || C.data.id !== id) C.day = 0;
    C.data = data;
    C.day = Math.min(C.day, data.giorni.length - 1);
    C.root.innerHTML = cityPage(data);
    wireCity(C.root);
    loadRanking().then(() => { const box = C.root.querySelector("#rankBox"); if (box && C.data === data) box.innerHTML = rankBox(data); }).catch(() => {});
    webcams(data).then((list) => { const box = C.root.querySelector("#cams"); if (box && C.data === data) box.innerHTML = camsBlock(list); }).catch(() => {});
    store("citta", id);
    document.title = `${data.nome.split("/")[0]}: il meteo e quanto è sicuro – Ventaglio`;
    return true;
  },
  async ski() {
    try { await loadIndex(); } catch (e) { /* l'indice serve solo per la data */ }
    await loadSki();
    C.root.innerHTML = skiPage();
    document.title = "Neve e piste – Ventaglio";
  },
  info() {
    C.root.innerHTML = infoPage();
    document.title = "Come funziona – Ventaglio";
  },
  async ranking(focus) {
    try { await loadIndex(); } catch (e) { /* l'indice serve solo per la data */ }
    try { await loadRanking(); }
    catch (e) { C.root.innerHTML = `<article class="info"><h1>IA contro fisica</h1><p class="note">La classifica non è ancora disponibile: arriva con il prossimo aggiornamento.</p></article>`; return; }
    const draw = () => {
      C.root.innerHTML = rankingPage(focus);
      C.root.querySelectorAll("[data-lead]").forEach((b) => b.addEventListener("click", () => { C.lead = +b.dataset.lead; draw(); }));
      const row = focus && C.root.querySelector(`#st-${focus}`);
      if (row) row.scrollIntoView({ block: "center" });
    };
    draw();
    document.title = "IA contro fisica – Ventaglio";
  },
  /** Ricarica se c'è un aggiornamento; restituisce true se la città è cambiata. */
  async refresh() {
    if (!C.index) return false;
    const old = C.index.aggiornato;
    try { await loadIndex(true); } catch (e) { return false; }
    if (C.index.aggiornato === old) return false;
    if (C.data) await this.open(C.data.id, true);
    return true;
  },
  remembered: () => store("citta"),
  /** Luogo da mettere al centro del radar: quello aperto, quello chiesto o l'ultimo visto. */
  async place(id) {
    if (C.data && (!id || C.data.id === id)) return { id: C.data.id, nome: C.data.nome.split("/")[0], lat: C.data.lat, lon: C.data.lon };
    id = id || store("citta");
    if (!id) return null;
    try { await loadIndex(); } catch (e) { return null; }
    let p = C.index.luoghi.find((x) => x.id === id);
    if (!p) { try { await loadComuni(); p = C.comuniById.get(id); } catch (e) { return null; } }
    return p ? { id: p.id, nome: p.nome.split("/")[0], lat: p.lat, lon: p.lon } : null;
  },
  icon, fan, favs,
};
function notReady() {
  return `<section class="home"><h1 class="brand-big">Ventaglio</h1><p class="note">La previsione per città è in preparazione: arriva con il prossimo aggiornamento dei modelli. Intanto puoi guardare le <a href="#carte">carte</a>.</p></section>`;
}
})();
