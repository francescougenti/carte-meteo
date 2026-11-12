"""Verifica dei modelli: "IA contro fisica".

Si conservano:
  - le temperature osservate nelle stazioni aeroportuali italiane (bollettini METAR di NOAA),
    riassunte in massima e minima del giorno (UTC);
  - le massime e minime previste da ogni modello deterministico nel punto esatto di ogni stazione e alla sua quota,
    corsa per corsa (corse delle 00 e delle 12 UTC, da 1 a 5 giorni di anticipo).
Dal confronto nasce la classifica: errore medio di ogni modello e giorni in cui è stato il più vicino al vero.

    data/verifica/osservazioni.json
    data/verifica/previsioni.json
    data/verifica/classifica.json
"""
import datetime as dt
import json
import math
import os
import urllib.request

import numpy as np

from . import citta, luoghi
from .sources import now_utc

UTC = dt.timezone.utc
KEEP_DAYS = 60
LEADS = range(1, 6)
METAR_URL = os.environ.get("METEO_METAR_URL") or "https://aviationweather.gov/api/data/metar"
BBOX = "35.4,6.4,47.2,18.8"  # Italia
MAX_KM, MAX_DZ = 25.0, 150.0
RAIN_WX = ("RA", "DZ", "SH", "TS", "SN", "GR", "GS", "PL")
MIN_OBS = 18          # osservazioni minime perché massima e minima del giorno siano affidabili
WINDOW = 30           # giorni della classifica
SCORE_LEADS = (1, 3, 5)
KIND = {"ecmwf": "fisico", "gfs": "fisico", "icon-eu": "fisico", "aifs": "ia"}


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


# --------------------------------------------------------------------------------------
# Osservazioni
# --------------------------------------------------------------------------------------
def fetch_metars(hours=8):
    url = f"{METAR_URL}?bbox={BBOX}&format=json&hours={hours}"
    req = urllib.request.Request(url, headers={"User-Agent": "carte-meteo/1.0 (verifica previsioni)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def update_observations(path, reports, now):
    data = citta.read_json(path) or {}
    st = data.setdefault("stazioni", {})
    recent = data.setdefault("recenti", {})
    for m in reports:
        icao = str(m.get("icaoId") or "")
        if not icao.startswith("LI") or m.get("temp") is None or m.get("obsTime") is None:
            continue
        if m.get("lat") is not None and m.get("lon") is not None:
            st[icao] = [m.get("name") or icao, round(float(m["lat"]), 4), round(float(m["lon"]), 4),
                        None if m.get("elev") is None else int(m["elev"])]
        t = dt.datetime.fromtimestamp(int(m["obsTime"]), UTC).strftime("%Y-%m-%dT%H:%MZ")
        wx = str(m.get("wxString") or "")
        recent.setdefault(icao, {})[t] = [float(m["temp"]), int(any(w in wx for w in RAIN_WX))]
    # riassunto giornaliero (UTC) e pulizia degli orari vecchi
    days = data.setdefault("giorni", {})
    cut = (now - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%MZ")
    fresh = (now - dt.timedelta(days=2)).date().isoformat()  # i giorni più vecchi non hanno più tutte le osservazioni
    for icao, obs in recent.items():
        by_day = {}
        for t, (temp, rain) in obs.items():
            if t[:10] >= fresh:
                by_day.setdefault(t[:10], []).append((temp, rain))
        for day, vals in by_day.items():
            temps = [v[0] for v in vals]
            days.setdefault(day, {})[icao] = [min(temps), max(temps), len(vals), int(any(v[1] for v in vals))]
        recent[icao] = {t: v for t, v in obs.items() if t >= cut}
    oldest = (now - dt.timedelta(days=KEEP_DAYS)).date().isoformat()
    data["giorni"] = {d: v for d, v in sorted(days.items()) if d >= oldest}
    data["aggiornato"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    data["fonte"] = "NOAA Aviation Weather Center, bollettini METAR"
    return data


def match_stations(places, stations):
    """Luogo -> stazione più vicina entro 25 km e 150 m di dislivello."""
    out = {}
    for p in places:
        best = None
        for icao, (name, lat, lon, elev) in stations.items():
            d = km((p["lat"], p["lon"]), (lat, lon))
            if d > MAX_KM:
                continue
            if p.get("alt") is not None and elev is not None and abs(p["alt"] - elev) > MAX_DZ:
                continue
            if best is None or d < best[1]:
                best = (icao, d)
        if best:
            out[p["id"]] = [best[0], round(best[1], 1)]
    return out


# --------------------------------------------------------------------------------------
# Previsioni
# --------------------------------------------------------------------------------------
def record_forecasts(path, sources, places, now):
    data = citta.read_json(path) or {}
    runs = data.setdefault("corse", {})
    if not places:
        return data
    ids = [p["id"] for p in places]
    for sid in citta.DET:
        s = sources.get(sid)
        if s is None or s.run.hour not in (0, 12):
            continue
        key = f"{sid}|{s.run.strftime('%Y%m%d%H')}"
        if key in runs and runs[key]["luoghi"][:1] == ids[:1]:
            continue
        base = s.run.date()
        days, tmin, tmax = [], [], []
        for k in LEADS:
            day = base + dt.timedelta(days=k)
            lo, hi = [], []
            for p in places:
                d = citta.det_day(s, p, day, s.run)
                lo.append(citta.rnd(d["min"]) if d else None)
                hi.append(citta.rnd(d["max"]) if d else None)
            if any(v is not None for v in hi):
                days.append(day.isoformat())
                tmin.append(lo)
                tmax.append(hi)
        if days:
            runs[key] = dict(luoghi=ids, giorni=days, min=tmin, max=tmax)
    oldest = (now - dt.timedelta(days=KEEP_DAYS)).strftime("%Y%m%d%H")
    data["corse"] = {k: v for k, v in sorted(runs.items()) if k.split("|")[1] >= oldest}
    data["aggiornato"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return data


# --------------------------------------------------------------------------------------
# Classifica
# --------------------------------------------------------------------------------------
def scores(fc, ob, now):
    """Errore medio di massime e minime per modello, anticipo e stazione, sugli ultimi WINDOW giorni."""
    days_ok = {}
    for day, st in ob.get("giorni", {}).items():
        for icao, (tmin, tmax, n, _) in st.items():
            if n >= MIN_OBS and day < now.date().isoformat():
                days_ok[(day, icao)] = (tmin, tmax)
    first = (now.date() - dt.timedelta(days=WINDOW)).isoformat()
    err = {}  # (stazione, giorno, anticipo) -> {modello: (errore massima, errore minima)}
    for key, run in fc.get("corse", {}).items():
        sid, stamp = key.split("|")
        if sid not in KIND or not stamp.endswith("00") or not run["luoghi"] or not run["luoghi"][0].startswith("st-"):
            continue
        base = dt.datetime.strptime(stamp, "%Y%m%d%H").date()
        icaos = [x[3:] for x in run["luoghi"]]
        for day, mins, maxs in zip(run["giorni"], run["min"], run["max"]):
            lead = (dt.date.fromisoformat(day) - base).days
            if lead not in SCORE_LEADS or day < first:
                continue
            for icao, fmin, fmax in zip(icaos, mins, maxs):
                o = days_ok.get((day, icao))
                if o is None or fmin is None or fmax is None:
                    continue
                err.setdefault((icao, day, lead), {})[sid] = (fmax - o[1], fmin - o[0])

    def summary(items):
        out = {}
        for lead in SCORE_LEADS:
            cases = [m for (_, _, ld), m in items if ld == lead]
            per = {}
            for m in cases:
                best = min(m, key=lambda s: abs(m[s][0]) + abs(m[s][1])) if len(m) >= 3 else None
                for sid, (emax, emin) in m.items():
                    p = per.setdefault(sid, dict(emax=[], emin=[], vinti=0, gare=0))
                    p["emax"].append(emax)
                    p["emin"].append(emin)
                    if best is not None:
                        p["gare"] += 1
                        p["vinti"] += sid == best
            if per:
                out[str(lead)] = {sid: dict(tipo=KIND[sid], n=len(p["emax"]),
                                            errore=citta.rnd(np.mean(np.abs(p["emax"] + p["emin"])), 2),
                                            errore_max=citta.rnd(np.mean(np.abs(p["emax"])), 2),
                                            errore_min=citta.rnd(np.mean(np.abs(p["emin"])), 2),
                                            scarto=citta.rnd(np.mean(p["emax"] + p["emin"]), 2),
                                            vinti=p["vinti"], gare=p["gare"])
                                  for sid, p in per.items()}
        return out

    items = list(err.items())
    by_station = {}
    for (icao, day, lead), m in items:
        by_station.setdefault(icao, []).append(((icao, day, lead), m))
    stations = ob.get("stazioni", {})
    giorni = sorted({day for (_, day, _) in err})
    return dict(
        formato=1, aggiornato=now.strftime("%Y-%m-%dT%H:%M:%SZ"), finestra=WINDOW, giorni=len(giorni),
        dal=giorni[0] if giorni else None, al=giorni[-1] if giorni else None,
        italia=summary(items),
        stazioni={icao: dict(nome=stations.get(icao, [icao])[0], lat=stations.get(icao, [None, None])[1],
                             lon=stations.get(icao, [None, None, None])[2], giorni=len({d for (_, d, _), _ in lst}),
                             anticipo=summary(lst))
                  for icao, lst in sorted(by_station.items())})


def update(public, info, now=None, log=print):
    """Da chiamare dopo citta.build(): osservazioni, previsioni alle stazioni e classifica."""
    now = now or now_utc()
    base = os.path.join(public, "data", "verifica")
    pf, po = os.path.join(base, "previsioni.json"), os.path.join(base, "osservazioni.json")
    if info:
        citta.write_json(pf, record_forecasts(pf, info["sources"], luoghi.stations(), now))
    try:
        reports = fetch_metars()
        data = update_observations(po, reports, now)
        if info:
            data["abbinamenti"] = match_stations(info["places"], data["stazioni"])
        citta.write_json(po, data)
        log(f"Verifica: {len(data['stazioni'])} stazioni, {len(data.get('abbinamenti', {}))} luoghi abbinati")
    except Exception as e:
        log(f"Verifica: osservazioni METAR non scaricate ({e})")
    fc, ob = citta.read_json(pf) or {}, citta.read_json(po) or {}
    cl = scores(fc, ob, now)
    citta.write_json(os.path.join(base, "classifica.json"), cl)
    log(f"Classifica: {cl['giorni']} giorni verificati")
