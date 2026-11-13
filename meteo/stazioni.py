"""Centraline della rete MeteoNetwork: l'ultima misura di ogni stazione italiana.

Serve un token BULK (segreto MNW_TOKEN del repository): senza, il passo viene saltato.
Una sola richiesta per giro (tutte le stazioni d'Italia), nei limiti dell'API (1 richiesta al secondo).
Dati con licenza CC BY 4.0 per le stazioni che l'hanno accettata: "Dati: MeteoNetwork".

Risultato: data/stazioni.json, solo le stazioni con una misura delle ultime 3 ore.
"""
import datetime as dt
import json
import os
import urllib.request

from . import citta

API = os.environ.get("METEO_MNW_URL") or "https://api.meteonetwork.it/v3/data-realtime?country=IT"
UA = "Ventaglio/1.0 (sito meteo personale; https://francescougenti.github.io/carte-meteo/)"
CAMPI = ["codice", "luogo", "lat", "lon", "quota", "t", "umidita", "pioggia_oggi", "intensita", "vento", "dir", "raffica", "ora"]
FRESH_H = 3


def num(v, nd=1):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if x == x else None


def when(row):
    for k in ("observation_time_utc", "observation_time"):
        v = row.get(k)
        if v:
            try:
                t = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00").replace(" ", "T"))
                return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                pass
    v = row.get("observation_time_local")
    if v:
        try:
            from zoneinfo import ZoneInfo
            t = dt.datetime.fromisoformat(str(v).replace(" ", "T"))
            return (t if t.tzinfo else t.replace(tzinfo=ZoneInfo("Europe/Rome"))).astimezone(dt.timezone.utc)
        except ValueError:
            pass
    return None


def update(public, log=print):
    token = os.environ.get("MNW_TOKEN", "").strip()
    if not token:
        return  # ancora senza token: le centraline restano spente
    req = urllib.request.Request(API, headers={"User-Agent": UA, "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        rows = json.loads(r.read())
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("stations") or []
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for s in rows:
        t = when(s)
        lat, lon = num(s.get("latitude"), 5), num(s.get("longitude"), 5)
        if t is None or lat is None or lon is None or (now - t).total_seconds() > FRESH_H * 3600:
            continue
        out.append([s.get("station_code"), s.get("place") or s.get("name"), lat, lon, num(s.get("altitude"), 0),
                    num(s.get("temperature")), num(s.get("rh"), 0), num(s.get("daily_rain")), num(s.get("rain_rate")),
                    num(s.get("wind_speed"), 0), num(s.get("wind_direction"), 0), num(s.get("wind_gust"), 0),
                    t.strftime("%Y-%m-%dT%H:%MZ")])
    citta.write_json(os.path.join(public, "data", "stazioni.json"), dict(
        formato=1, aggiornato=now.strftime("%Y-%m-%dT%H:%M:%SZ"), campi=CAMPI, stazioni=out,
        fonte="MeteoNetwork, rete di stazioni meteo amatoriali (dati CC BY 4.0)", link="https://www.meteonetwork.it/"))
    log(f"Centraline MeteoNetwork: {len(out)} stazioni con misure recenti su {len(rows)}")
