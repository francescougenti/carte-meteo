"""Raccolta dei dati per la verifica dei modelli ("IA contro fisica, nella tua città", fase 3).

Da subito si conservano:
  - le massime e minime previste da ogni modello deterministico per i luoghi abbinati a una stazione,
    corsa per corsa (solo le corse delle 00 e delle 12 UTC, da 1 a 5 giorni di anticipo);
  - le temperature osservate nelle stazioni aeroportuali italiane (bollettini METAR di NOAA),
    riassunte in massima e minima del giorno (UTC).

    data/verifica/previsioni.json
    data/verifica/osservazioni.json
"""
import datetime as dt
import json
import math
import os
import urllib.request

from . import citta
from .sources import now_utc

UTC = dt.timezone.utc
KEEP_DAYS = 60
LEADS = range(1, 6)
METAR_URL = os.environ.get("METEO_METAR_URL") or "https://aviationweather.gov/api/data/metar"
BBOX = "35.4,6.4,47.2,18.8"  # Italia
MAX_KM, MAX_DZ = 25.0, 150.0
RAIN_WX = ("RA", "DZ", "SH", "TS", "SN", "GR", "GS", "PL")


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
    for icao, obs in recent.items():
        by_day = {}
        for t, (temp, rain) in obs.items():
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
    ids = [p["id"] for p in places]
    for sid in citta.DET:
        s = sources.get(sid)
        if s is None or s.run.hour not in (0, 12):
            continue
        key = f"{sid}|{s.run.strftime('%Y%m%d%H')}"
        if key in runs:
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


def update(public, info, now=None, log=print):
    """Da chiamare dopo citta.build(): aggiorna previsioni e osservazioni per la verifica."""
    now = now or now_utc()
    base = os.path.join(public, "data", "verifica")
    if info:
        p = os.path.join(base, "previsioni.json")
        citta.write_json(p, record_forecasts(p, info["sources"], info["places"], now))
    p = os.path.join(base, "osservazioni.json")
    try:
        reports = fetch_metars()
    except Exception as e:
        log(f"Verifica: osservazioni METAR non scaricate ({e})")
        return
    data = update_observations(p, reports, now)
    if info:
        data["abbinamenti"] = match_stations(info["places"], data["stazioni"])
    citta.write_json(p, data)
    log(f"Verifica: {len(data['stazioni'])} stazioni, {len(data.get('abbinamenti', {}))} luoghi abbinati")
