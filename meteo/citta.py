"""Previsione "La tua città": unisce i modelli, misura l'incertezza e ricorda come cambia la previsione.

Legge i campioni sui luoghi salvati da ogni modello (data/campioni/*.npz) e scrive:

    data/citta/indice.json      elenco dei capoluoghi con oggi e domani in breve (ricerca e anteprime)
    data/citta/<id>.json        previsione completa di un capoluogo, con lo storico delle previsioni passate
    data/celle/<id>.json        la stessa previsione per una zona di comuni (il sito la adatta alla quota del comune)
    data/citta/comuni.json      tutti i comuni con la loro zona, per la ricerca e la posizione

Formato documentato in docs/formato-dati.md.
"""
import datetime as dt
import json
import math
import os
import warnings
from zoneinfo import ZoneInfo

import numpy as np

from . import luoghi
from .sources import now_utc

UTC = dt.timezone.utc
ROME = ZoneInfo("Europe/Rome")
FORMAT = 1
DAYS = 10
DET = ("ecmwf", "aifs", "gfs", "icon-eu")
WEIGHTS = {"ecmwf": 0.35, "aifs": 0.25, "gfs": 0.20, "icon-eu": 0.20}
ENS = ("ecmwf-ens", "gefs")
LAPSE = 0.0065       # °C per metro: correzione della temperatura tra quota del modello e quota reale
RAIN_DAY = 1.0       # mm: soglia di "giorno di pioggia"
RAIN_PERIOD = 0.5    # mm in 6 ore: soglia di pioggia in una fascia della giornata
T_RANGE_OK = 4.0     # °C: forbice della massima entro cui la temperatura è "decisa"
P_OK = 0.2           # probabilità di pioggia sotto il 20% o sopra l'80%: pioggia "decisa"
HISTORY_DAYS = 9
WIND_NAMES = ["Tramontana", "Grecale", "Levante", "Scirocco", "Ostro", "Libeccio", "Ponente", "Maestrale"]


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s):
    return dt.datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def rnd(v, nd=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), nd) if nd else int(round(float(v)))


# --------------------------------------------------------------------------------------
# Sorgenti
# --------------------------------------------------------------------------------------
class Source:
    """Campioni di un modello: valori per luogo e istante di validità."""

    def __init__(self, sid, path):
        with np.load(path) as z:
            self.id = sid
            self.run = parse(z["run"])
            self.ids = [str(x) for x in z["ids"]]
            self.valid = [parse(v) for v in z["valid"]]
            self.vars = {k[2:]: z[k].astype(np.float32) for k in z.files if k.startswith("v_")}
            self.orog = z["orog"] if "orog" in z.files else None
        self.row = {pid: i for i, pid in enumerate(self.ids)}
        self.col = {t: j for j, t in enumerate(self.valid)}
        self.ens = next(iter(self.vars.values())).ndim == 3 if self.vars else False

    @property
    def reach(self):
        return self.valid[-1] if self.valid else self.run

    def extend(self, older):
        """Aggiunge le scadenze della corsa precedente oltre l'ultima di questa (ECMWF 06/18 -> +240 h)."""
        extra = [j for j, t in enumerate(older.valid) if t > self.reach]
        if not extra:
            return
        rows = [older.row.get(pid) for pid in self.ids]
        for k, a in list(self.vars.items()):
            # le variabili che la corsa precedente non aveva restano vuote, ma della stessa lunghezza
            b = np.full(a.shape[:-1] + (len(extra),), np.nan, np.float32)
            if k in older.vars:
                for i, r in enumerate(rows):
                    if r is not None:
                        b[i] = older.vars[k][r][..., extra]
            self.vars[k] = np.concatenate([a, b], axis=-1)
        self.valid += [older.valid[j] for j in extra]
        self.col = {t: j for j, t in enumerate(self.valid)}
        self.extended_from = older.run

    def get(self, var, pid, t):
        """Valore (deterministico) o vettore dei membri (ensemble); None se manca."""
        a = self.vars.get(var)
        i, j = self.row.get(pid), self.col.get(t)
        if a is None or i is None or j is None or j >= a.shape[-1]:
            return None
        v = a[i][..., j]
        if self.ens:
            return v
        return None if np.isnan(v) else float(v)


def load_sources(public):
    base = os.path.join(public, "data", "campioni")
    out = {}
    for sid in DET + ENS:
        p = os.path.join(base, f"{sid}.npz")
        if not os.path.exists(p):
            continue
        try:
            out[sid] = Source(sid, p)
        except Exception as e:  # file rovinato: si va avanti con gli altri modelli
            print(f"  ! campioni di {sid} illeggibili: {e}")
            continue
        long = os.path.join(base, f"{sid}-lungo.npz")
        if os.path.exists(long):
            try:
                old = Source(sid, long)
                if out[sid].run - dt.timedelta(hours=12) <= old.run < out[sid].run:
                    out[sid].extend(old)
            except Exception:
                pass
    # la quota del terreno di GFS fa da ripiego per i modelli globali a 0.25° che non la pubblicano
    if "gfs" in out and out["gfs"].orog is not None:
        for sid in ("ecmwf", "aifs"):
            s = out.get(sid)
            if s is not None and s.orog is None:
                g = out["gfs"]
                s.orog = np.array([g.orog[g.row[pid]] if pid in g.row else np.nan for pid in s.ids], np.float32)
    return out


# --------------------------------------------------------------------------------------
# Un giorno di un luogo
# --------------------------------------------------------------------------------------
def at(day, hour):
    return dt.datetime(day.year, day.month, day.day, tzinfo=UTC) + dt.timedelta(hours=hour)


def corr(src, pid, place):
    """Correzione della temperatura per la differenza tra quota del modello e quota del luogo."""
    if src.orog is None or place.get("alt") is None or pid not in src.row:
        return 0.0
    z = float(src.orog[src.row[pid]])
    if math.isnan(z):
        return 0.0
    return float(np.clip(LAPSE * (z - place["alt"]), -10, 10))


def det_day(src, place, day, now):
    """Riassunto di un giorno per un modello deterministico (None se il modello non copre il giorno)."""
    pid = place["id"]
    c = corr(src, pid, place)
    g = lambda v, h: src.get(v, pid, at(day, h))  # noqa: E731
    temp = lambda v, h: plausible(g(v, h))  # noqa: E731
    t = {h: temp("t2m", h) for h in (0, 6, 12, 18, 24)}
    mx12, mx18, mn6 = temp("tmax6", 12), temp("tmax6", 18), temp("tmin6", 6)
    # massime e minime "del periodo" coerenti con le temperature agli estremi del periodo, altrimenti si scartano
    mx12 = mx12 if consistent_max(mx12, t[6], t[12]) else None
    mx18 = mx18 if consistent_max(mx18, t[12], t[18]) else None
    mn6 = mn6 if consistent_min(mn6, t[0], t[6]) else None
    t = {h: (v + c if v is not None else None) for h, v in t.items()}
    hi = [t[12], t[18], *(v + c for v in (mx12, mx18) if v is not None)]
    lo = [t[0], t[6], *(v + c for v in [mn6] if v is not None)]
    # massima e minima solo se il modello copre le ore in cui di solito cadono (corse partite a giornata in corso)
    hi = [v for v in hi if v is not None] if (t[12] is not None or mx18 is not None) else []
    lo = [v for v in lo if v is not None] if (t[6] is not None or mn6 is not None) else []
    periods = [g("tp6", h) for h in (6, 12, 18, 24)]
    need = [k for k, h in enumerate((6, 12, 18, 24)) if at(day, h) > now]
    if not hi and not lo and all(periods[k] is None for k in need):
        return None
    mm = None
    if need and all(periods[k] is not None for k in need):
        mm = sum(max(periods[k], 0.0) for k in need)
    u = [g("u10", h) for h in (0, 6, 12, 18)]
    v = [g("v10", h) for h in (0, 6, 12, 18)]
    winds = [(math.hypot(a, b) * 3.6, a, b, h) for a, b, h in zip(u, v, (0, 6, 12, 18)) if a is not None and b is not None]
    gusts = [x * 3.6 for x in (g("gust", h) for h in (6, 12, 18, 24)) if x is not None]
    day_h = (6, 12, 18) if day.month in (4, 5, 6, 7, 8, 9) else (6, 12)
    clouds = [x for x in (g("tcc", h) for h in day_h) if x is not None]
    capes = [x for x in (g("cape", h) for h in (12, 18)) if x is not None]
    fzl = [x for x in (g("fzl", h) for h in (0, 6, 12, 18, 24)) if x is not None]
    snow = g("snow", 12)
    t850 = [x for x in (g("t850", h) for h in (0, 6, 12, 18)) if x is not None and -60 < x < 45]
    u8 = [x for x in (g("u850", h) for h in (6, 12, 18)) if x is not None]
    v8 = [x for x in (g("v850", h) for h in (6, 12, 18)) if x is not None]
    pres = [(x, h) for h, x in ((h, g("mslp", h)) for h in (0, 6, 12, 18)) if x is not None and 900 < x < 1080]
    out = dict(max=max(hi) if hi else None, min=min(lo) if lo else None, mm=mm,
               t850=float(np.mean(t850)) if len(t850) >= 3 else None,
               u850=float(np.mean(u8)) if u8 and len(u8) == len(v8) else None,
               v850=float(np.mean(v8)) if v8 and len(u8) == len(v8) else None,
               p_min=min(pres)[0] if pres else None, p_mean=float(np.mean([x for x, _ in pres])) if pres else None,
               h_pmin=min(pres)[1] if pres else None,
               nubi=float(np.mean(clouds)) if clouds else None, cape=max(capes) if capes else None,
               fzl=min(fzl) if fzl else None, suolo=snow,
               raffiche=max(gusts) if gusts else None, periodi=periods, t=t)
    if winds:
        w = max(winds)
        out.update(vento=w[0], u=w[1], v=w[2], h_vento=w[3])
    # fasce della giornata (ore UTC, circa un'ora prima dell'ora italiana)
    fasce = []
    for k, (h0, h1) in enumerate(((0, 6), (6, 12), (12, 18), (18, 24))):
        tt = [x for x in (t[h0], t[h1]) if x is not None]
        cl = [x for x in (g("tcc", h0), g("tcc", h1)) if x is not None]
        fasce.append(dict(t=float(np.mean(tt)) if tt else None, mm=periods[k],
                          nubi=float(np.mean(cl)) if cl else None))
    out["fasce"] = fasce
    return out


def plausible(v, lo=-60.0, hi=55.0):
    """Temperatura (°C) fisicamente possibile, altrimenti None (dati rovinati, campi a 0 K...)."""
    return v if v is not None and lo < v < hi else None


def consistent_max(m, a, b):
    ends = [x for x in (a, b) if x is not None]
    return m is not None and (not ends or max(ends) - 1.5 <= m <= max(ends) + 12)


def consistent_min(m, a, b):
    ends = [x for x in (a, b) if x is not None]
    return m is not None and (not ends or min(ends) - 12 <= m <= min(ends) + 1.5)


def ens_day(src, place, day, now):
    """Massime, minime e pioggia del giorno per ogni membro di un ensemble."""
    pid = place["id"]
    g = lambda v, h: src.get(v, pid, at(day, h))  # noqa: E731
    ok = lambda x: None if x is None else np.where((x > -60) & (x < 55), x, np.nan)  # noqa: E731
    hi = [x for x in (ok(g("t2m", 12)), ok(g("t2m", 18))) if x is not None]
    lo = [x for x in (ok(g("t2m", 0)), ok(g("t2m", 6))) if x is not None]
    need = [h for h in (6, 12, 18, 24) if at(day, h) > now]
    per = [g("tp6", h) for h in need]
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # membri senza dati: restano NaN
        if hi:
            out["max"] = np.nanmax(np.stack(hi), axis=0)
        if lo:
            out["min"] = np.nanmin(np.stack(lo), axis=0)
    if need and all(p is not None for p in per):
        mm = np.sum(np.maximum(np.stack(per), 0), axis=0)
        ok = ~np.isnan(mm)
        if ok.sum() >= 10:
            out["mm"] = mm[ok]
        fasce = []
        for h in (6, 12, 18, 24):
            p = g("tp6", h)
            fasce.append(None if p is None or np.isnan(p).all() else float(np.mean(p[~np.isnan(p)] >= RAIN_PERIOD)))
        out["fasce_p"] = fasce
    return out


def blend(per_model, key, tol=None):
    """Media pesata dei modelli. Con tol: con almeno 3 modelli si scarta chi si allontana più di tol dalla mediana."""
    vals = {sid: d.get(key) for sid, d in per_model.items()}
    vals = {sid: v for sid, v in vals.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}
    if tol is not None and len(vals) >= 3:
        med = float(np.median(list(vals.values())))
        vals = {sid: v for sid, v in vals.items() if abs(v - med) <= tol}
    den = sum(WEIGHTS[sid] for sid in vals)
    return sum(WEIGHTS[sid] * v for sid, v in vals.items()) / den if den else None


def outliers(per_model, key, tol):
    vals = {sid: d.get(key) for sid, d in per_model.items() if d.get(key) is not None}
    if len(vals) < 3:
        return set()
    med = float(np.median(list(vals.values())))
    return {sid for sid, v in vals.items() if abs(v - med) > tol}


def wind_name(u, v):
    """Nome del vento dalla direzione di provenienza (componenti u, v verso cui soffia)."""
    deg = (math.degrees(math.atan2(-u, -v)) + 360) % 360
    return deg, WIND_NAMES[int(((deg + 22.5) % 360) // 45)]


def sky_code(nubi, mm, p, cape, snow_kind):
    """Codice dell'icona: sereno, poco-nuvoloso, nuvoloso, coperto, rovesci, pioggia, pioggia-forte,
    temporale, neve, pioggia-neve."""
    wet = p is not None and p >= 0.5 and (mm or 0) >= RAIN_DAY
    if wet:
        if snow_kind == "neve":
            return "neve"
        if snow_kind == "mista":
            return "pioggia-neve"
        if cape is not None and cape >= 400:
            return "temporale"
        return "pioggia-forte" if (mm or 0) >= 15 else "pioggia"
    if p is not None and p >= 0.3:
        return "rovesci"
    n = 50 if nubi is None else nubi
    return "sereno" if n < 20 else "poco-nuvoloso" if n < 50 else "nuvoloso" if n < 80 else "coperto"


def snow_kind(fzl, alt, tmax):
    """Neve, pioggia mista a neve oppure nulla, dalla quota dello zero termico (m) e dalla massima."""
    if fzl is None or alt is None or (tmax is not None and tmax >= 6):
        return None
    snow_level = fzl - 300  # la neve arriva di solito qualche centinaio di metri sotto lo zero termico
    if snow_level <= alt + 50:
        return "neve"
    if snow_level <= alt + 350:
        return "mista"
    return None


def pct(a, q):
    return float(np.percentile(a, q))


def place_day(place, day, sources, now):
    det = {}
    for sid in DET:
        s = sources.get(sid)
        if s is not None:
            d = det_day(s, place, day, now)
            if d is not None:
                det[sid] = d
    ens = {}
    for sid in ENS:
        s = sources.get(sid)
        if s is not None:
            e = ens_day(s, place, day, now)
            if e:
                ens[sid] = e
    if not det:
        return None
    tmax, tmin, mm = blend(det, "max", tol=8), blend(det, "min", tol=8), blend(det, "mm")
    out = dict(data=day.isoformat(), max=rnd(tmax), min=rnd(tmin))
    # forbice della temperatura dall'ensemble, centrata sulla previsione dei modelli
    for key, val in (("max", tmax), ("min", tmin)):
        mem = np.concatenate([e[key] for e in ens.values() if key in e]) if any(key in e for e in ens.values()) else None
        if val is None:
            continue
        if mem is not None and np.isfinite(mem).sum() >= 10:
            mem = mem[np.isfinite(mem)]
            med = pct(mem, 50)
            out[key + "_f"] = [rnd(val + pct(mem, 10) - med), rnd(val + pct(mem, 90) - med)]
        else:
            vals = [d[key] for d in det.values() if d.get(key) is not None]
            out[key + "_f"] = [rnd(min(vals) - 1), rnd(max(vals) + 1)]
    # pioggia: probabilità dagli scenari dell'ensemble, quantità dai modelli
    members = {sid: e["mm"] for sid, e in ens.items() if "mm" in e}
    if members:
        allm = np.concatenate(list(members.values()))
        k, n = int((allm >= RAIN_DAY).sum()), int(len(allm))
        rain = dict(p=rnd(100.0 * k / n, 0), scenari=k, su=n, forte=int((allm >= 10).sum()),
                    membri={sid: [rnd(x) for x in m] for sid, m in members.items()})
        p = k / n
    else:
        vals = [d["mm"] for d in det.values() if d.get("mm") is not None]
        p = (sum(v >= RAIN_DAY for v in vals) / len(vals)) if vals else None
        rain = dict(p=rnd(100 * p, 0) if p is not None else None, scenari=None, su=None)
    rain["mm"] = rnd(mm)
    out["pioggia"] = rain
    nubi, cape, fzl = blend(det, "nubi"), blend(det, "cape"), blend(det, "fzl")
    suolo = blend(det, "suolo")
    if suolo and tmax is not None and tmax > 6:
        suolo = 0.0  # la neve al suolo del modello viene dalle quote più alte della cella, non dalla città
    kind = snow_kind(fzl, place.get("alt"), tmax) if (mm or 0) >= RAIN_DAY else None
    out["nubi"] = rnd(nubi, 0)
    out["codice"] = sky_code(nubi, mm, p, cape, kind)
    if fzl is not None:
        out["neve"] = dict(quota=int(round(max(fzl - 300, 0) / 100.0) * 100), suolo=rnd(suolo or 0, 0))
    wv = [(d["vento"], d["u"], d["v"], d.get("raffiche")) for d in det.values() if "vento" in d]
    if wv:
        speed = blend({sid: d for sid, d in det.items() if "vento" in d}, "vento")
        uu, vv = sum(w[1] for w in wv), sum(w[2] for w in wv)
        deg, name = wind_name(uu, vv)
        gust = blend(det, "raffiche")
        out["vento"] = dict(kmh=rnd(speed, 0), raffiche=rnd(gust, 0), dir=rnd(deg, 0), nome=name)
    # fasce: notte, mattina, pomeriggio, sera
    fp = [None] * 4
    for e in ens.values():
        for k, x in enumerate(e.get("fasce_p") or []):
            if x is not None:
                fp[k] = x if fp[k] is None else (fp[k] + x) / 2
    fasce = []
    for k in range(4):
        parts = {sid: d["fasce"][k] for sid, d in det.items()}
        t, m, nb = blend(parts, "t", tol=8), blend(parts, "mm"), blend(parts, "nubi")
        if t is None and m is None:
            fasce.append(None)
            continue
        pk = fp[k] if fp[k] is not None else (None if m is None else float(m >= RAIN_PERIOD))
        kk = snow_kind(fzl, place.get("alt"), t) if (m or 0) >= RAIN_PERIOD else None
        code = sky_code(nb, (m or 0) * 4, pk, cape if k in (2, 3) else None, kk)
        fasce.append(dict(t=rnd(t, 0), mm=rnd(m), p=rnd(100 * pk, 0) if pk is not None else None, codice=code))
    out["fasce"] = fasce
    u8, v8 = blend(det, "u850"), blend(det, "v850")
    hours = (6, 12, 18, 24)
    wet = [(f["mm"] or 0, h) for f, h in zip(fasce, hours) if f is not None]
    gust_h = max((d["vento"], d["h_vento"]) for d in det.values() if "vento" in d)[1] if wv else 12
    pm = [(d["p_min"], d["h_pmin"]) for d in det.values() if d.get("p_min") is not None]
    out["_aria"] = dict(t850=blend(det, "t850", tol=6), dir850=wind_name(u8, v8)[0] if u8 is not None and v8 is not None
                        else None, v850=math.hypot(u8, v8) * 3.6 if u8 is not None and v8 is not None else None,
                        p_min=blend(det, "p_min", tol=8), p_mean=blend(det, "p_mean", tol=8),
                        h_pmin=min(pm)[1] if pm else 12, h_rain=max(wet)[1] if wet else 12, h_vento=gust_h,
                        cape=cape, fzl=fzl, p=p, mm=mm)
    out["modelli"] = {sid: dict(max=rnd(d["max"]), min=rnd(d["min"]), mm=rnd(d["mm"])) for sid, d in det.items()}
    for sid in outliers(det, "max", 8) | outliers(det, "min", 8):
        out["modelli"][sid]["escluso"] = True  # molto diverso dagli altri: non entra nella media
    # incertezza: la forbice della massima e quanto si dividono gli scenari sulla pioggia
    u_t = (out["max_f"][1] - out["max_f"][0]) / T_RANGE_OK if out.get("max_f") else 0.0
    u_r = (min(p, 1 - p) / P_OK) if p is not None else 0.0
    out["_u"] = max(u_t, u_r)
    out["_motivo"] = "pioggia" if u_r >= u_t else "temperatura"
    return out


# --------------------------------------------------------------------------------------
# Il perché: la causa principale del tempo di ogni giorno, con la carta che la mostra
# --------------------------------------------------------------------------------------
def at_iso(day, hour):
    return iso(at(dt.date.fromisoformat(day), hour))


def reasons(days, today):
    """Aggiunge a ogni giorno "perche": fino a tre cause in ordine di importanza, ognuna con la carta da guardare."""
    prev = None
    for d in days:
        if d is None:
            prev = None
            continue
        a = d.pop("_aria")
        out = []
        p, mm = a["p"] or 0, a["mm"] or 0
        if prev is not None and a["t850"] is not None and prev["t850"] is not None:
            delta = a["t850"] - prev["t850"]
            if abs(delta) >= 4:
                out.append((abs(delta), dict(tipo="freddo" if delta < 0 else "caldo", delta=rnd(abs(delta), 0),
                                              dir=rnd(a["dir850"], 0), carta="t850", ora=at_iso(d["data"], 12))))
        if d["codice"] in ("neve", "pioggia-neve") and a["fzl"] is not None:
            out.append((9, dict(tipo="neve", zero=int(round(a["fzl"] / 100.0)) * 100, carta="zero",
                                ora=at_iso(d["data"], a["h_rain"]))))
        if a["cape"] is not None and a["cape"] >= 800 and p >= 0.4:
            out.append((6, dict(tipo="temporali", cape=rnd(a["cape"], 0), carta="cape", ora=at_iso(d["data"], 12))))
        w = d.get("vento") or {}
        if (w.get("kmh") or 0) >= 39 or (w.get("raffiche") or 0) >= 65:
            out.append((5 + (w.get("raffiche") or 0) / 40, dict(tipo="vento", carta="gust" if w.get("raffiche") else "wind10",
                                                                 ora=at_iso(d["data"], a["h_vento"]))))
        if a["p_min"] is not None and a["p_min"] <= 1008 and p >= 0.5:
            out.append((4 + (1008 - a["p_min"]) / 4, dict(tipo="bassa", hpa=rnd(a["p_min"], 0), carta="mslp",
                                                          ora=at_iso(d["data"], a["h_pmin"]))))
        elif a["p_mean"] is not None and a["p_mean"] >= 1022 and p <= 0.2:
            out.append((3.5, dict(tipo="alta", hpa=rnd(a["p_mean"], 0), carta="mslp", ora=at_iso(d["data"], 12))))
        if p >= 0.6 and mm >= 2 and not any(r[1]["tipo"] in ("bassa", "neve", "temporali") for r in out):
            out.append((3, dict(tipo="pioggia", carta="prec6", ora=at_iso(d["data"], a["h_rain"]))))
        d["perche"] = [r for _, r in sorted(out, key=lambda x: -x[0])[:3]]
        prev = a


# --------------------------------------------------------------------------------------
# Quando lo saprai
# --------------------------------------------------------------------------------------
def state_of(u):
    return "deciso" if u <= 1.0 else "quasi" if u <= 1.75 else "aperto"


def growth(all_days):
    """Come cresce di solito l'incertezza con l'anticipo, misurata oggi su tutti i luoghi."""
    by_lead = {}
    for days in all_days:
        for k, d in enumerate(days):
            if d is not None:
                by_lead.setdefault(k, []).append(d["_u"])
    g = [float(np.median(by_lead[k])) if k in by_lead else None for k in range(DAYS)]
    out, last = [], 0.15
    for v in g:  # non decrescente: più lontano non può essere più facile da prevedere
        last = max(last, v if v is not None else last)
        out.append(last)
    return out


def when(d, lead, G, today):
    """Stato del giorno e da quando conviene ricontrollare."""
    u = d.pop("_u")
    motivo = d.pop("_motivo")
    st = state_of(u)
    info = dict(stato=st, motivo=motivo, indice=rnd(u, 2))
    if st == "deciso" or lead == 0:
        return info
    best = None
    for l in range(lead - 1, 0, -1):  # dal più lontano al più vicino: il primo giorno utile
        if u * G[l] / max(G[lead], 0.15) <= 1.0:
            best = l
            break
    if best is None:
        info["fino_all_ultimo"] = True
        info["ricontrolla"] = (today + dt.timedelta(days=lead - 1)).isoformat()
    else:
        info["ricontrolla"] = (today + dt.timedelta(days=lead - best)).isoformat()
        info["anticipo"] = best
    return info


# --------------------------------------------------------------------------------------
# Storico: come era la previsione per ogni giorno ai passaggi precedenti
# --------------------------------------------------------------------------------------
def merge_history(old, days, now, today):
    hist = {k: v for k, v in (old or {}).items() if dt.date.fromisoformat(k) >= today - dt.timedelta(days=1)}
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    oldest = now - dt.timedelta(days=HISTORY_DAYS)
    for d in days:
        if d is None:
            continue
        snap = [stamp, d.get("min"), d.get("max"), d["pioggia"].get("p"), d["pioggia"].get("mm"), d["codice"]]
        lst = [s for s in hist.get(d["data"], []) if dt.datetime.strptime(s[0], "%Y-%m-%dT%H:%MZ").replace(
            tzinfo=UTC) >= oldest]
        if lst and now - dt.datetime.strptime(lst[-1][0], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC) < dt.timedelta(
                hours=2, minutes=30):
            lst[-1] = snap  # più passaggi ravvicinati: si tiene l'ultimo
        else:
            lst.append(snap)
        hist[d["data"]] = lst[-48:]
    return dict(sorted(hist.items()))


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(path + ".tmp", path)


# --------------------------------------------------------------------------------------
def build(public, now=None, log=print):
    now = now or now_utc()
    sources = load_sources(public)
    if not any(s in sources for s in DET):
        log("La tua città: nessun campione dei modelli, salto")
        return None
    today = now.astimezone(ROME).date()
    places, cells = luoghi.active(), luoghi.cells()
    points = places + cells
    all_days = []
    for p in points:
        all_days.append([place_day(p, today + dt.timedelta(days=k), sources, now) for k in range(DAYS)])
    G = growth(all_days)
    runs = {sid: iso(s.run) for sid, s in sources.items()}
    members = sum(next(iter(s.vars.values())).shape[1] for s in sources.values() if s.ens and s.vars)
    index = []
    active_ids = {p["id"] for p in places}
    for p, days in zip(points, all_days):
        reasons(days, today)
        for k, d in enumerate(days):
            if d is not None:
                d["incertezza"] = when(d, k, G, today)
        days = [d for d in days if d is not None]
        is_city = p["id"] in active_ids
        path = os.path.join(public, "data", "citta" if is_city else "celle", f"{p['id']}.json")
        old = read_json(path)
        head = (dict(id=p["id"], nome=p["name"], altro=p["alt_name"], provincia=p["provincia"], sigla=p["sigla"],
                     regione=p["regione"]) if is_city else dict(id=p["id"], comuni=len(p["comuni"])))
        data = dict(formato=FORMAT, **head, lat=p["lat"], lon=p["lon"], alt=p["alt"], aggiornato=iso(now), corse=runs,
                    membri=members, giorni=days,
                    storia=merge_history(old.get("storia") if old else None, days, now, today))
        write_json(path, data)
        if is_city:
            brief = [dict(data=d["data"], min=d["min"], max=d["max"], p=d["pioggia"].get("p"), codice=d["codice"],
                          stato=d["incertezza"]["stato"]) for d in days[:3]]
            index.append(dict(id=p["id"], nome=p["name"], altro=p["alt_name"], sigla=p["sigla"],
                              provincia=p["provincia"], regione=p["regione"], lat=p["lat"], lon=p["lon"],
                              alt=p["alt"], giorni=brief))
    write_json(os.path.join(public, "data", "citta", "indice.json"),
               dict(formato=FORMAT, aggiornato=iso(now), corse=runs, crescita=[rnd(x, 2) for x in G], luoghi=index))
    write_comuni(public)
    log(f"La tua città: {len(index)} capoluoghi e {len(cells)} zone per {len(luoghi.all_places())} comuni")
    return dict(sources=sources, places=places, today=today)


def write_comuni(public):
    """Elenco di tutti i comuni per la ricerca: nome, provincia, posizione, quota e file della previsione."""
    files = luoghi.file_of()
    prov = {}
    rows = []
    for p in luoghi.all_places():
        prov.setdefault(p["sigla"], [p["provincia"], p["regione"]])
        rows.append([p["id"], p["name"], p["alt_name"] or "", p["sigla"], p["lat"], p["lon"], p["alt"], files[p["id"]]])
    write_json(os.path.join(public, "data", "citta", "comuni.json"),
               dict(formato=FORMAT, campi=["id", "nome", "altro", "sigla", "lat", "lon", "alt", "file"],
                    province=dict(sorted(prov.items())), comuni=rows))
