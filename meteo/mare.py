"""Il mare: altezza, direzione e periodo delle onde davanti ai comuni costieri.

Dati: modello d'onda di ECMWF (open data, stream "wave", griglia 0.25°), ogni 3 ore fino a +144 h.
I comuni "sul mare" sono quelli con il centro a meno di COAST_KM dalla costa (Natural Earth): per
ognuno si prende la cella di mare più vicina della griglia del modello.

Risultato: data/campioni/ecmwf-mare.npz (swh, mwd, pp1d su capoluoghi e zone costiere).
"""
import datetime as dt
import functools
import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import shapely.wkb
from scipy.spatial import cKDTree

from . import luoghi, points
from .sources import download, first_working, http_get

COAST_KM = 12.0
KEYS = {"swh": "swh", "mwd": "mwd", "pp1d": "pp1d"}
STEPS = list(range(0, 145, 3))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R_EARTH = 6371.0

# Scala Douglas (codice WMO 3700): altezza significativa delle onde in metri, limite superiore
DOUGLAS = [(0.0, "calmo"), (0.1, "quasi calmo"), (0.5, "poco mosso"), (1.25, "mosso"), (2.5, "molto mosso"),
           (4.0, "agitato"), (6.0, "molto agitato"), (9.0, "grosso"), (14.0, "molto grosso"), (99.0, "tempestoso")]


def douglas(h):
    """Grado della scala Douglas (0–9) dall'altezza significativa delle onde."""
    if h is None or not np.isfinite(h):
        return None
    for k, (top, _) in enumerate(DOUGLAS):
        if h <= top:
            return k
    return 9


def _xyz(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


@functools.lru_cache(maxsize=1)
def coast_tree():
    geom = shapely.wkb.loads(open(os.path.join(ROOT, "assets", "geo", "italia_coast.wkb"), "rb").read())
    pts = []
    for line in getattr(geom, "geoms", [geom]):
        n = max(2, int(line.length / 0.01))  # un punto ogni ~1 km
        for k in range(n + 1):
            p = line.interpolate(k / n, normalized=True)
            pts.append((p.y, p.x))
    pts = np.array(pts)
    return cKDTree(_xyz(pts[:, 0], pts[:, 1]))


@functools.lru_cache(maxsize=1)
def coast_km():
    """{id del comune: distanza dalla costa in km} per i comuni entro COAST_KM dal mare."""
    places = luoghi.all_places()
    d, _ = coast_tree().query(_xyz(np.array([p["lat"] for p in places]), np.array([p["lon"] for p in places])))
    km = 2 * R_EARTH * np.arcsin(np.minimum(d / 2, 1.0))
    return {p["id"]: round(float(k), 1) for p, k in zip(places, km) if k <= COAST_KM}


def targets():
    """Punti in cui leggere il mare: i capoluoghi costieri e, per le zone, la media dei loro comuni costieri."""
    near = coast_km()
    out = [dict(id=p["id"], lat=p["lat"], lon=p["lon"]) for p in luoghi.active() if p["id"] in near]
    by_id = {p["id"]: p for p in luoghi.all_places()}
    for c in luoghi.cells():
        cs = [by_id[i] for i in c["comuni"] if i in near]
        if cs:
            out.append(dict(id=c["id"], lat=float(np.mean([p["lat"] for p in cs])),
                            lon=float(np.mean([p["lon"] for p in cs]))))
    return out


def url(root, t, step):
    d, h = t.strftime("%Y%m%d"), t.strftime("%H")
    return f"{root}/{d}/{h}z/ifs/0p25/wave/{d}{h}0000-{step}h-wave-fc.grib2"


def plan(model, run, step):
    roots = [run.root] + [r for r in model.roots if r != run.root]
    u, text = first_working([url(r, run.time, step) for r in roots],
                            lambda x: http_get(x[: -len(".grib2")] + ".index"))
    entries = [json.loads(line) for line in text.decode().splitlines() if line.strip()]
    out = {}
    for key, name in KEYS.items():
        e = next((e for e in entries if e.get("param") == name), None)
        if e:
            off, ln = int(e["_offset"]), int(e["_length"])
            out[key] = (u, (off, off + ln - 1), 0)
    return out


def one_step(model, run, step):
    from . import grib  # eccodes serve solo qui
    try:
        raw = download(plan(model, run, step), threads=3)
    except Exception as e:
        return step, None, None, {"_errore": str(e)}
    out, lats, lons = {}, None, None
    for key, (msg, sub) in raw.items():
        try:
            la, lo, v = grib.decode(msg, sub)
        except Exception:
            continue
        lats, lons = la, lo
        out[key] = v
    return step, lats, lons, out


def nearest_sea(lats, lons, field, pts, max_km=45.0):
    """Indice (riga, colonna) della cella di mare valida più vicina a ogni punto (None se troppo lontana)."""
    jj = np.where((lats >= 34) & (lats <= 48.5))[0]
    ii = np.where((lons >= 5) & (lons <= 21))[0]
    sub = field[np.ix_(jj, ii)]
    J, I = np.nonzero(np.isfinite(sub))
    if not len(J):
        return [None] * len(pts)
    tree = cKDTree(_xyz(lats[jj][J], lons[ii][I]))
    d, k = tree.query(_xyz(np.array([p["lat"] for p in pts]), np.array([p["lon"] for p in pts])))
    km = 2 * R_EARTH * np.arcsin(np.minimum(d / 2, 1.0))
    return [(int(jj[J[x]]), int(ii[I[x]])) if dk <= max_km else None for x, dk in zip(k, km)]


def write(public, model, run, log=print):
    pts = targets()
    if not pts:
        return
    t0 = dt.datetime.now()
    series = {k: np.full((len(pts), len(STEPS)), np.nan, np.float32) for k in KEYS}
    cells, done = None, 0
    with ThreadPoolExecutor(6) as ex:
        for step, lats, lons, arrays in ex.map(lambda s: one_step(model, run, s), STEPS):
            if lats is None or "swh" not in arrays:
                continue
            if cells is None:
                cells = nearest_sea(lats, lons, arrays["swh"], pts)
            j = STEPS.index(step)
            for k, a in arrays.items():
                if k in series and a.shape == arrays["swh"].shape:
                    series[k][:, j] = [a[c] if c else np.nan for c in cells]
            done += 1
    if cells is None:
        log(f"    ! mare: nessuna scadenza del modello d'onda per la corsa {run.time:%d/%m %H}Z")
        return
    valids = [(run.time + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ") for h in STEPS]
    points.write_samples(public, "ecmwf-mare", run.iso, [p["id"] for p in pts], STEPS, valids, series)
    lost = sum(c is None for c in cells)
    log(f"    mare: {done} scadenze per {len(pts)} punti costieri ({lost} senza mare vicino) "
        f"in {(dt.datetime.now() - t0).seconds} s")
