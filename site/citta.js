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
const STATE = { deciso: "Deciso", quasi: "Quasi deciso", aperto: "Ancora aperto" };
const FASCE = ["Notte", "Mattina", "Pomeriggio", "Sera"];

const C = { index: null, data: null, day: 0, root: null, go: null, loading: null };

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
  const r = d.pioggia || {};
  if (r.futuri != null && r.p > 15 && r.p < 85 && ["rovesci", "pioggia", "pioggia-forte", "temporale", "neve", "pioggia-neve"].includes(d.codice))
    parts[0] += ` (piove in ${r.futuri} futuri su ${r.su})`;
  const w = windText(d.vento);
  if (w) parts.push(w);
  const n = d.neve;
  if (n && r.p >= 30 && n.quota <= 1500 && !["neve"].includes(d.codice) && C.data && (C.data.alt == null || n.quota > C.data.alt))
    parts.push(`neve oltre i ${num(n.quota)} m`);
  if (n && n.suolo >= 1) parts.push(`${num(n.suolo)} cm di neve al suolo`);
  return parts.join(", ") + ".";
}
function checkWhen(iso, today) {
  if (iso <= today) return "stasera";
  if (iso === addDays(today, 1)) return "domani sera";
  return `${fWeek.format(dateObj(iso))} sera`;
}
function rainFact(r) {
  const k = r.futuri, n = r.su;
  if (k == null) return "";
  if (k === n) return `piove in tutti gli ${n} futuri`;
  if (k === 0) return `asciutto in tutti gli ${n} futuri`;
  return r.p >= 50 ? `piove in ${k} futuri su ${n}` : `asciutto in ${n - k} futuri su ${n}`;
}
function certaintyText(d, today) {
  const u = d.incertezza || {}, r = d.pioggia || {};
  const range = d.max_f ? `${deg(d.max_f[0])} e ${deg(d.max_f[1])}` : "";
  if (u.stato === "deciso") {
    const facts = [rainFact(r), range ? `massima tra ${range}` : ""].filter(Boolean);
    return `I futuri sono d'accordo: ${facts.join(", ")}.`;
  }
  let t = u.motivo === "pioggia" && r.futuri != null
    ? `I futuri si dividono sulla pioggia: piove in ${r.futuri} su ${r.su}.`
    : d.max_f ? `La massima può andare da ${deg(d.max_f[0])} a ${deg(d.max_f[1])}.` : "";
  if (u.fino_all_ultimo) t += ` Potrebbe restare incerto fino all'ultimo: ricontrolla ${checkWhen(u.ricontrolla, today)} e la mattina stessa.`;
  else if (u.ricontrolla) {
    const a = u.anticipo === 1 ? "il giorno prima" : `${u.anticipo} giorni prima`;
    t += ` Di solito un giorno così si decide ${a}: ricontrolla ${checkWhen(u.ricontrolla, today)}.`;
  }
  return t.trim();
}

// ---------- cosa è cambiato ----------
function changes(prev, cur, today) {
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
    if (snowNow !== snowThen) out.push({ w: 4, t: `<b>${cap(name)}</b>: ${snowNow ? "ora è prevista neve" : "la neve non è più prevista"}.` });
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
  return { title: "Rispetto a ieri", items: changes(prev, data.giorni, today), first: true };
}

// ---------- disegno ----------
function hero(data, today) {
  const g = data.giorni;
  const blocks = g.slice(0, 2).map((d, i) => {
    const st = d.incertezza?.stato || "quasi";
    const lowTxt = d.min == null ? "" : `<span class="t-min" title="Minima">${deg(d.min)}</span>`;
    return `<article class="now ${i ? "next" : ""}">
      <h2>${cap(dayName(d.data, today))}</h2>
      <div class="now-main">${icon(d.codice, 56)}<div class="temps"><span class="t-max" title="Massima">${deg(d.max)}</span>${lowTxt}</div></div>
      <p class="sentence">${esc(daySentence(d))}</p>
      <p class="state">${fan(st, 20)}<span><b>${STATE[st]}.</b> ${esc(certaintyText(d, today))}</span></p>
    </article>`;
  }).join("");
  return `<div class="now-row">${blocks}</div>`;
}

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
    const p = d.pioggia?.p;
    const sel = i === C.day;
    const label = `${cap(dayName(d.data, today))}: ${LABEL[d.codice] || ""}, massima ${deg(d.max)}, minima ${deg(d.min)}, pioggia ${p == null ? "non disponibile" : Math.round(p) + "%"}, ${STATE[st].toLowerCase()}`;
    return `<button class="col${sel ? " sel" : ""}" data-i="${i}" aria-pressed="${sel}" aria-label="${esc(label)}">
      <span class="c-day">${i === 0 ? "Oggi" : cap(fShort.format(dateObj(d.data)).replace(".", ""))}<small>${dateObj(d.data).getUTCDate()}</small></span>
      ${icon(d.codice, 30)}
      <span class="c-max">${deg(d.max)}</span>
      <span class="c-plot"></span>
      <span class="c-min">${deg(d.min)}</span>
      <span class="c-rain${p != null && p >= 30 ? " wet" : ""}"><i style="height:${p == null ? 0 : Math.max(2, (p / 100) * 26)}px"></i>${p == null ? "–" : Math.round(p) + "%"}</span>
      <span class="c-state" title="${STATE[st]}">${fan(st, 34)}</span>
    </button>`;
  }).join("");
  return `<section class="ventaglio" aria-labelledby="vTitle">
    <div class="sec-head"><h2 id="vTitle">I prossimi ${g.length} giorni</h2>
      <p>Le fasce colorate mostrano dove cadono massime e minime in 8 futuri su 10: più si allargano, meno è sicuro.</p></div>
    <div class="v-scroll"><div class="v-grid" style="--n:${g.length}">${cols}<svg class="v-svg" aria-hidden="true"></svg></div></div>
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

function futures(d) {
  const r = d.pioggia || {};
  if (!r.membri) return `<p class="muted">Per questo giorno non ci sono i futuri dell'ensemble: la probabilità viene dal confronto tra i modelli.</p>`;
  const all = [];
  for (const [sid, list] of Object.entries(r.membri)) for (const mm of list) if (mm != null) all.push({ sid, mm });
  all.sort((a, b) => a.mm - b.mm);
  const cls = (mm) => (mm < 1 ? "f0" : mm < 5 ? "f1" : mm < 15 ? "f2" : "f3");
  const per = Object.entries(r.membri).map(([sid, list]) => {
    const k = list.filter((x) => x != null && x >= 1).length;
    return `${k} su ${list.length} del ${W[sid] || sid}`;
  });
  const dots = all.map((m) => `<i class="${cls(m.mm)}" title="${m.mm.toFixed(1).replace(".", ",")} mm (${W[m.sid] || m.sid})"></i>`).join("");
  return `<p>Piove almeno 1 mm in <b>${r.futuri} futuri su ${r.su}</b>: ${per.join(" e ")}.</p>
    <div class="dots" role="img" aria-label="${r.futuri} futuri con pioggia su ${r.su}">${dots}</div>
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
  const rows = Object.entries(d.modelli || {}).map(([sid, m]) => `<tr><th scope="row">${MODELS[sid] || sid}</th>
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
  return `<a class="to-charts" href="#carte/ecmwf/italia/${chart}/${lead}">Guarda le carte di ${esc(dayName(d.data))} per appassionati</a>`;
}

function detail(data, today) {
  const d = data.giorni[C.day];
  if (!d) return "";
  const st = d.incertezza?.stato || "quasi";
  const fasce = (d.fasce || []).map((f, k) => f ? `<li>${icon(f.codice, 30, k === 0 || k === 3)}
      <span class="f-name">${FASCE[k]}</span><span class="f-t">${deg(f.t)}</span>
      <span class="f-p${f.p != null && f.p >= 30 ? " wet" : ""}">${f.p == null ? "" : Math.round(f.p) + "%"}</span></li>` : "").join("");
  return `<section class="detail" aria-live="polite">
    <div class="d-head">
      <h2>${esc(cap(dayName(d.data, today)))} <span>${esc(fDayMonth.format(dateObj(d.data)))}</span></h2>
      <p class="sentence">${esc(daySentence(d))}</p>
    </div>
    <div class="d-grid">
      <div class="d-col">
        ${fasce ? `<ul class="fasce" aria-label="Fasce della giornata">${fasce}</ul>` : ""}
        <h3>${fan(st, 22)} Quando lo saprai</h3>
        <p><b>${STATE[st]}.</b> ${esc(certaintyText(d, today))}</p>
        <h3>Gli ${d.pioggia?.su || 81} futuri</h3>
        ${futures(d)}
      </div>
      <div class="d-col">
        <h3>Come è cambiata la previsione</h3>
        ${historyBlock(data, d)}
        <h3>Cosa dicono i modelli</h3>
        ${modelsBlock(d)}
        ${chartsLink(d)}
      </div>
    </div>
  </section>`;
}

function search(placeholder = "Cerca la tua città") {
  return `<div class="search" role="search">
    <div class="combo">
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>
      <input type="search" id="q" autocomplete="off" spellcheck="false" placeholder="${placeholder}" aria-label="${placeholder}"
        role="combobox" aria-expanded="false" aria-controls="qList" aria-autocomplete="list">
      <ul id="qList" role="listbox" hidden></ul>
    </div>
    <button type="button" class="near" id="near">${locIcon()}<span>Vicino a me</span></button>
  </div>
  <p class="loc-msg" id="locMsg" role="status"></p>`;
}
const locIcon = () => `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="7.5"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"/></svg>`;

function wireSearch(root) {
  const q = root.querySelector("#q"), list = root.querySelector("#qList");
  if (!q) return;
  let items = [], act = -1;
  const places = C.index.luoghi.map((p) => ({ p, n: norm(p.nome), a: norm(p.altro), pr: norm(p.provincia), s: norm(p.sigla) }));
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
      : `<li class="none">Nessun capoluogo con questo nome. Per ora ci sono i capoluoghi di provincia: prova con il tuo.</li>`;
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
  navigator.geolocation.getCurrentPosition((pos) => {
    const me = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    let best = null;
    for (const p of C.index.luoghi) { const d = km(me, p); if (!best || d < best.d) best = { p, d }; }
    if (!best) return;
    if (best.d > 30) store("nota", `Il capoluogo più vicino a te è ${best.p.nome}, a ${Math.round(best.d)} km. Presto arriveranno tutti i comuni.`);
    C.go(best.p.id);
  }, (err) => {
    msg.textContent = err.code === 1
      ? "Non hai dato il permesso di leggere la posizione: cerca la città per nome."
      : "Non riesco a trovare la posizione adesso: cerca la città per nome.";
  }, { timeout: 12000, maximumAge: 600000 });
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
  return `<section class="home">
    <h1 class="brand-big">Ventaglio</h1>
    <p class="lede">Il meteo della tua città, con una cosa in più: quanto è sicura la previsione e quando conviene ricontrollarla.</p>
    ${search()}
    <p class="explain">Per ogni giorno mettiamo a confronto quattro modelli e 81 simulazioni diverse dell'atmosfera, i <i>futuri</i>.
      Se vanno d'accordo la previsione è decisa; se si dividono te lo diciamo, insieme al momento in cui di solito si chiarisce.
      Ventaglio ricorda anche cosa diceva l'ultima volta che sei passato. <a href="#come-funziona">Come funziona</a></p>
    <h2 class="regs-title">Le città disponibili</h2>
    <div class="regs">${lists}</div>
  </section>`;
}

function cityPage(data) {
  const today = romeDate();
  const note = changeNote(data, today);
  const runs = data.corse || {};
  const up = Date.parse(data.aggiornato);
  const first = (x) => String(x || "").split("/")[0];
  const prov = first(data.provincia), reg = first(data.regione);
  const where = [prov && prov !== first(data.nome) && prov !== reg ? `provincia di ${prov}` : null, reg,
    data.alt != null ? `${num(data.alt)} m` : null].filter(Boolean).join(", ");
  const nota = store("nota");
  if (nota) store("nota", null);
  return `<section class="city">
    <header class="c-head">
      <div><h1>${esc(data.nome.split("/")[0])}</h1>
        <p class="where">${esc(where)}. Aggiornato ${esc(whenText(up))}
          con ${Object.keys(runs).filter((k) => MODELS[k]).length} modelli e ${data.membri} futuri. <a href="#come-funziona">Come funziona</a></p></div>
      ${search("Cerca un'altra città")}
    </header>
    ${nota ? `<p class="note">${esc(nota)}</p>` : ""}
    ${hero(data, today)}
    ${changesBlock(note)}
    ${fanChart(data, today)}
    <div id="detail">${detail(data, today)}</div>
  </section>`;
}

function infoPage() {
  return `<article class="info">
    <h1>Come funziona Ventaglio</h1>
    <p class="lede">Una previsione del tempo non è mai una certezza. Ventaglio te lo dice in modo chiaro, giorno per giorno, e ti aiuta a capire quando fidarti.</p>
    <h2>Da dove vengono i dati</h2>
    <p>Ogni volta che i centri meteo pubblicano una nuova corsa, il sito scarica i dati e rifà i conti da solo. Usiamo quattro modelli:
      ECMWF IFS (il centro europeo), ECMWF AIFS (il suo modello a intelligenza artificiale), GFS (NOAA, Stati Uniti) e ICON-EU (servizio meteo tedesco, solo i primi 5 giorni).
      Massime, minime e quantità di pioggia sono una media pesata dei quattro, con la temperatura corretta per l'altitudine della città.</p>
    <h2>I futuri</h2>
    <p>Oltre ai modelli "singoli", ECMWF e NOAA fanno girare lo stesso modello molte volte partendo da condizioni leggermente diverse: 50 volte il modello europeo, 31 l'americano.
      Ognuna di queste simulazioni è un futuro possibile. La probabilità di pioggia è semplicemente il numero di futuri in cui piove almeno 1 mm nella giornata, su 81.
      Le fasce colorate del grafico mostrano dove cadono massime e minime in 8 futuri su 10.</p>
    <h2>Deciso, quasi deciso, ancora aperto</h2>
    <p>Un giorno è <b>deciso</b> quando i futuri vanno d'accordo: piove in meno di 2 su 10 o in più di 8 su 10, e la massima sta in una forbice di 4 gradi.
      Quando si dividono, il giorno è <b>quasi deciso</b> o <b>ancora aperto</b>. Il ventaglio accanto a ogni giorno è più chiuso o più aperto di conseguenza.</p>
    <h2>Quando lo saprai</h2>
    <p>Misuriamo, sulle previsioni di oggi per tutte le città, quanto si restringono di solito i futuri man mano che un giorno si avvicina.
      Da qui stimiamo il giorno in cui la previsione per la tua data dovrebbe diventare decisa e ti suggeriamo di ricontrollare quella sera, quando arrivano le corse del pomeriggio.
      È una stima: a volte una situazione resta incerta fino all'ultimo, e in quel caso te lo diciamo.</p>
    <h2>Cosa è cambiato</h2>
    <p>Il sito conserva ogni aggiornamento della previsione degli ultimi giorni. Per questo può mostrarti come è cambiata la previsione per un giorno e cosa è diverso da ieri.
      Ricorda anche cosa avevi visto all'ultima visita: questa informazione resta solo nel tuo browser, non viene inviata a nessuno, e lo stesso vale per la posizione se usi "Vicino a me".</p>
    <h2>I limiti</h2>
    <p>I modelli hanno maglie di 7–25 km e dati ogni 6 ore: valli strette, coste e temporali locali possono andare diversamente. Le temperature del giorno sono stimate dai valori ogni 6 ore e dai massimi e minimi dei modelli quando ci sono.
      Per ora ci sono i capoluoghi di provincia; i comuni arriveranno in seguito. Per chi vuole vedere tutto c'è la parte <a href="#carte">per appassionati</a> con le carte, i confronti e gli ensemble.</p>
    <h2>Fonti e licenze</h2>
    <p>ECMWF Open Data (IFS, AIFS, ENS), licenza CC BY 4.0. NOAA/NCEP (GFS, GEFS), pubblico dominio. Deutscher Wetterdienst (ICON-EU). Elenco dei comuni: dati ISTAT tramite Garda Informatica (licenza MIT).
      Quote dal modello digitale del terreno AWS Terrain Tiles. Previsioni e grafici sono un'elaborazione di questo sito, non prodotti ufficiali degli enti.</p>
  </article>`;
}

// ---------- interfaccia pubblica ----------
async function loadIndex(force) {
  if (!C.index || force) C.index = await getJSON(`data/citta/indice.json?t=${Date.now()}`);
  return C.index;
}
function wireCity(root) {
  root.querySelectorAll(".col").forEach((b) => b.addEventListener("click", () => {
    C.day = +b.dataset.i;
    root.querySelectorAll(".col").forEach((x) => { x.classList.toggle("sel", x === b); x.setAttribute("aria-pressed", x === b); });
    root.querySelector("#detail").innerHTML = detail(C.data, romeDate());
    drawBands(root, C.data);
  }));
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
    document.title = "Ventaglio: il meteo della tua città e quanto è sicuro";
  },
  async open(id, keepDay) {
    try { await loadIndex(); } catch (e) { C.root.innerHTML = notReady(); return false; }
    const p = C.index.luoghi.find((x) => x.id === id);
    if (!p) return false;
    const token = (C.loading = id + Date.now());
    let data;
    try { data = await getJSON(`data/citta/${id}.json?u=${encodeURIComponent(C.index.aggiornato)}`); }
    catch (e) { C.root.innerHTML = `<section class="home"><p class="note">Non riesco a caricare la previsione di ${esc(p.nome)}. Controlla la connessione e ricarica la pagina.</p></section>`; return true; }
    if (C.loading !== token) return true;
    if (!keepDay || !C.data || C.data.id !== id) C.day = 0;
    C.data = data;
    C.day = Math.min(C.day, data.giorni.length - 1);
    C.root.innerHTML = cityPage(data);
    wireCity(C.root);
    store("citta", id);
    document.title = `${data.nome.split("/")[0]}: il meteo e quanto è sicuro – Ventaglio`;
    return true;
  },
  info() {
    C.root.innerHTML = infoPage();
    document.title = "Come funziona – Ventaglio";
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
  icon, fan,
};
function notReady() {
  return `<section class="home"><h1 class="brand-big">Ventaglio</h1><p class="note">La previsione per città è in preparazione: arriva con il prossimo aggiornamento dei modelli. Intanto puoi guardare le <a href="#carte">carte</a>.</p></section>`;
}
})();
