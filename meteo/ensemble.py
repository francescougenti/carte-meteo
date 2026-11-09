"""Generazione dei prodotti ensemble: carte (spaghetti, media e dispersione) e pennacchi per località."""
import datetime as dt
import multiprocessing
import os
import shutil
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait

import numpy as np

from . import config as C
from . import grib, points
from .sources import fetch, log

COARSE = 1.0  # risoluzione delle carte dell'ensemble (gradi): basta per le isoipse
VARS = ("z500", "t850", "mslp", "tp6")


def _download(plan, threads=16):
    def one(item):
        key, (url, rng, sub) = item
        try:
            return key, (fetch(url, rng), sub)
        except Exception as e:
            return key, e
    with ThreadPoolExecutor(threads) as ex:
        return dict(ex.map(one, plan.items()))


def generate(model, run, public, work, workers, only_steps=None):
    from . import render

    steps = model.steps(run)
    if only_steps:
        steps = [s for s in steps if s in only_steps]
    nm = len(model.members)
    stage = os.path.join(public, "maps", model.id + ".new")
    shutil.rmtree(stage, ignore_errors=True)
    wdir = os.path.join(work, model.id)
    shutil.rmtree(wdir, ignore_errors=True)
    os.makedirs(wdir)
    info = dict(id=model.id, short=model.chart_label, credit=model.credit)
    series = {v: np.full((len(C.CITIES), nm, len(steps)), np.nan, np.float32) for v in VARS}
    prev_tot = [None] * nm
    results, t0 = {}, time.time()
    sampler = None

    def collect(done):
        for f in done:
            try:
                h, ok = f.result()
                results[h] = ok
                os.remove(os.path.join(wdir, f"{h:03d}.npz"))
            except Exception:
                traceback.print_exc()

    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx, max_tasks_per_child=8) as pool:
        pending = set()
        for si, h in enumerate(steps):
            try:
                raw = _download(model.plan(run, h))
            except Exception as e:
                log(f"    ! +{h}h non scaricata: {e}")
                continue
            stack, bad = [None] * nm, 0
            for (mi, key), val in raw.items():
                if isinstance(val, Exception):
                    bad += 1
                    continue
                try:
                    la, lo, a = grib.decode(*val)
                except Exception:
                    bad += 1
                    continue
                a = model.convert(key, a)
                if sampler is None:
                    sampler = points.sampler(la, lo)
                if key == "tp_total":  # cumulata dall'inizio -> 6 ore
                    if prev_tot[mi] is not None:
                        series["tp6"][:, mi, si] = np.maximum(sampler(a) - prev_tot[mi], 0)
                    prev_tot[mi] = sampler(a)
                    continue
                series[key][:, mi, si] = sampler(a)
                if key == "z500":
                    s = max(1, int(round(COARSE / float(lo[1] - lo[0]))))
                    stack[mi] = a[::s, ::s]
                    clats, clons = la[::s], lo[::s]
            have = [m for m in stack if m is not None]
            log(f"    +{h:3d}h: {len(have)}/{nm} membri" + (f", {bad} campi mancanti" if bad else "")
                + f"  ({time.time() - t0:.0f} s)")
            if len(have) < nm * 0.6:
                continue
            path = os.path.join(wdir, f"{h:03d}.npz")
            np.savez(path, _lats=clats, _lons=clons, z500=np.array(have, np.float32))
            job = dict(npz=path, model=info, run=run.iso, h=h, out=stage, regions=C.ENS_REGIONS,
                       products=[p["id"] for p in C.ENS_PRODUCTS])
            pending.add(pool.submit(render.render_ens_step, job))
            while len(pending) >= workers + 1:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                collect(done)
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            collect(done)
    shutil.rmtree(wdir, ignore_errors=True)
    valids = [(run.time + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ") for h in steps]
    points.write_ens(public, model, run.iso, steps, valids, series)
    return results, stage


def finalize(model, run, public, stage, results, manifest):
    final = os.path.join(public, "maps", model.id)
    steps = [dict(h=h, valid=(run.time + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  charts=results[h]) for h in sorted(results) if results[h]]
    if not steps:
        shutil.rmtree(stage, ignore_errors=True)
        raise RuntimeError("nessuna carta ensemble prodotta")
    if os.path.isdir(final):
        os.rename(final, final + ".old")
    os.rename(stage, final)
    shutil.rmtree(final + ".old", ignore_errors=True)
    manifest.setdefault("ensembles", {})[model.id] = dict(
        label=model.long_label, short=model.label, credit=model.credit, run=run.iso,
        members=len(model.members), updated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        steps=steps, products=[p["id"] for p in C.ENS_PRODUCTS], regions=C.ENS_REGIONS)
