"""Dati ora per ora per la previsione "La tua città".

Le carte si disegnano ogni 6 ore; per sapere a che ora piove servono scadenze più fitte. Qui si scaricano
solo pochi campi (temperatura, pioggia cumulata, nuvole, vento) e solo per leggerli sui comuni,
senza disegnare carte:

    ICON-EU   ogni ora fino a +78 h
    ECMWF     ogni 3 ore fino a +144 h
    GFS       ogni 3 ore fino a +120 h

Risultato: data/campioni/<modello>-orario.npz, con lo stesso formato degli altri campioni.
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import grib, points
from .sources import download

KEYS = ("t2m", "tp_total", "tcc", "u10", "v10")
PLAN = {"icon-eu": (1, 78), "ecmwf": (3, 144), "gfs": (3, 120)}  # passo e ultima scadenza (ore)


def steps_for(model, run):
    if model.id not in PLAN:
        return []
    every, last = PLAN[model.id]
    reach = max(model.steps(run))
    return list(range(0, min(last, reach) + 1, every))


def one_step(model, run, h):
    """Campi richiesti di una scadenza, decodificati: (lats, lons, {chiave: griglia})."""
    try:
        plan = {k: v for k, v in model.plan(run, h).items() if k in KEYS}
        raw = download(plan, threads=4)
    except Exception as e:  # scadenza non pubblicata (indice mancante): si salta
        return h, None, None, {"_errore": str(e)}
    out, lats, lons = {}, None, None
    for key, (msg, sub) in raw.items():
        try:
            la, lo, v = grib.decode(msg, sub)
        except Exception:
            continue
        if lats is None:
            lats, lons = la, lo
        elif v.shape != (len(lats), len(lons)):
            continue
        out[key] = model.convert(key, v).astype(np.float32)
    return h, lats, lons, out


def write(public, model, run, places, log=print):
    steps = steps_for(model, run)
    if not steps:
        return
    t0 = dt.datetime.now()
    ids = [p["id"] for p in places]
    series = {k: np.full((len(places), len(steps)), np.nan, np.float32) for k in KEYS}
    sampler, done, failed = None, 0, 0
    col = {h: j for j, h in enumerate(steps)}
    with ThreadPoolExecutor(6) as ex:
        for i in range(0, len(steps), 12):  # a gruppi, per non tenere in memoria troppe griglie
            for h, lats, lons, arrays in ex.map(lambda s: one_step(model, run, s), steps[i:i + 12]):
                if lats is None:
                    failed += 1
                    continue
                if sampler is None:
                    sampler = points.sampler(lats, lons, places)
                for k, a in arrays.items():
                    if k in series:
                        series[k][:, col[h]] = sampler(a)
                done += 1
    if sampler is None:
        log(f"    ! ora per ora {model.id}: nessuna scadenza scaricata")
        return
    if "tp_total" in series:
        series["tp_total"][:, 0] = np.where(np.isnan(series["tp_total"][:, 0]), 0.0, series["tp_total"][:, 0])
    valids = [(run.time + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ") for h in steps]
    points.write_samples(public, f"{model.id}-orario", run.iso, ids, steps, valids, series)
    log(f"    ora per ora {model.id}: {done} scadenze ({failed} mancanti) in {(dt.datetime.now() - t0).seconds} s")
