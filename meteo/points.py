"""Valori dei modelli sulle località, per i meteogrammi e i pennacchi dell'ensemble."""
import json
import math
import os

import numpy as np
from scipy.ndimage import map_coordinates

from . import config as C


def sampler(lats, lons, places=None):
    """Funzione che legge un campo (griglia lats×lons) sulle località con interpolazione bilineare."""
    places = C.CITIES if places is None else places
    dlat, dlon = float(lats[1] - lats[0]), float(lons[1] - lons[0])
    glob = len(lons) * dlon >= 359.9
    la = np.array([c["lat"] for c in places])
    lo = np.array([c["lon"] for c in places])
    cj = (la - float(lats[0])) / dlat
    ci = (lo - float(lons[0])) / dlon
    if glob:
        ci = np.mod(ci, len(lons))
    coords = np.array([cj, ci])

    def f(a):
        src = np.concatenate([a, a[:, :1]], axis=1) if glob else a
        return map_coordinates(src, coords, order=1, mode="constant", cval=np.nan)
    return f


def clean(v, nd=1):
    v = float(v)
    return None if math.isnan(v) else round(v, nd)


def det_values(arrays, f):
    """Valori per località di una scadenza di un modello deterministico."""
    out = {}

    def put(name, a, nd=1):
        if a is not None:
            vals = f(a)
            for i, c in enumerate(C.CITIES):
                out.setdefault(c["id"], {})[name] = clean(vals[i], nd)
    g = arrays.get
    put("t2m", g("t2m"))
    put("t850", g("t850"))
    put("z500", g("z500"))
    put("mslp", g("mslp"))
    put("tp6", g("tp6"))
    put("tcc", g("tcc"), 0)
    put("fzl", g("fzl"), 0)
    put("snow", g("snow"), 0)
    if g("u10") is not None and g("v10") is not None:
        put("wind10", np.hypot(g("u10"), g("v10")) * 3.6, 0)
    if g("gust") is not None:
        put("gust", g("gust") * 3.6, 0)
    return out


def write_det(public, model, run_iso, rows):
    """rows: lista di (h, valid_iso, {città: {variabile: valore}}) in ordine di scadenza."""
    rows = sorted(rows, key=lambda r: r[0])
    data = {"model": model.id, "run": run_iso, "h": [r[0] for r in rows], "valid": [r[1] for r in rows],
            "cities": {}}
    names = ("t2m", "t850", "z500", "mslp", "tp6", "tcc", "wind10", "gust", "fzl", "snow")
    for c in C.CITIES:
        data["cities"][c["id"]] = {n: [r[2].get(c["id"], {}).get(n) for r in rows] for n in names}
    for c in data["cities"].values():
        for n in list(c):
            if all(v is None for v in c[n]):
                del c[n]
    _write(os.path.join(public, "data", "punti", f"{model.id}.json"), data)


# --------------------------------------------------------------------------------------
# Campioni per la previsione "La tua città": tutti i luoghi attivi, file compatti .npz
# --------------------------------------------------------------------------------------
PLACE_VARS = ("t2m", "tmax6", "tmin6", "tp6", "tcc", "u10", "v10", "gust", "fzl", "snow", "t850", "cape", "mslp")


def place_values(arrays, f):
    """{variabile: valori sui luoghi} di una scadenza di un modello deterministico."""
    return {n: f(arrays[n]).astype(np.float32) for n in PLACE_VARS if arrays.get(n) is not None}


def write_samples(public, model_id, run_iso, ids, hs, valids, series, orog=None):
    """series: {variabile: array (n_luoghi, n_scadenze)} oppure (n_luoghi, n_membri, n_scadenze)."""
    path = os.path.join(public, "data", "campioni", f"{model_id}.npz")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    extra = {} if orog is None else {"orog": np.asarray(orog, np.float32)}
    with open(path + ".tmp", "wb") as fh:
        np.savez_compressed(fh, run=np.array(run_iso), ids=np.array(ids), h=np.array(hs, np.int32),
                            valid=np.array(valids), **{f"v_{k}": np.asarray(v, np.float32) for k, v in series.items()},
                            **extra)
    os.replace(path + ".tmp", path)


def det_series(rows, ids):
    """rows: lista di (h, valid_iso, {variabile: valori}) -> {variabile: (n_luoghi, n_scadenze)}."""
    names = sorted({k for r in rows for k in r[2]})
    out = {}
    for n in names:
        a = np.full((len(ids), len(rows)), np.nan, np.float32)
        for j, r in enumerate(rows):
            if n in r[2]:
                a[:, j] = r[2][n]
        out[n] = a
    return out


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(path + ".tmp", path)


def write_ens(public, model, run_iso, hs, valids, series):
    """series: {variabile: array (n_località, n_membri, n_scadenze)}."""
    data = {"model": model.id, "run": run_iso, "h": hs, "valid": valids, "members": len(model.members),
            "cities": {}}
    for i, c in enumerate(C.CITIES):
        data["cities"][c["id"]] = {
            n: [[clean(v) for v in member] for member in arr[i]] for n, arr in series.items()}
    _write(os.path.join(public, "data", "ensemble", f"{model.id}.json"), data)
