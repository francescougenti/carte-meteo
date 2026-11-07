"""Genera le carte delle corse nuove e aggiorna il manifest del sito.

    python -m meteo.build --public public              # GFS ed ECMWF, solo se c'è una corsa nuova
    python -m meteo.build --public public --force      # rigenera comunque
    python -m meteo.build --models gfs --steps 0,6,12  # prove veloci
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

import numpy as np

from . import config as C
from . import grib
from .sources import MODELS, UTC, download, log


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def manifest_path(public):
    return os.path.join(public, "data", "manifest.json")


def load_manifest(public):
    try:
        with open(manifest_path(public)) as f:
            m = json.load(f)
        m.setdefault("models", {})
        return m
    except Exception:
        return {"models": {}}


def save_manifest(public, m):
    m["generated"] = iso(dt.datetime.now(UTC))
    m["regions"] = [dict(id=r["id"], label=r["label"]) for r in C.REGIONS]
    m["groups"] = C.GROUPS
    m["charts"] = [dict(id=c["id"], label=c["label"], group=c["group"], title=c["title"]) for c in C.CHARTS]
    p = manifest_path(public)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w") as f:
        json.dump(m, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(p + ".tmp", p)


def prepare_step(model, run, h, prev_cum):
    """Scarica e decodifica una scadenza. Restituisce (lats, lons, campi, precipitazione cumulata)."""
    raw = download(model.plan(run, h))
    arrays, lats, lons = {}, None, None
    for key, (msg, sub) in raw.items():
        try:
            la, lo, v = grib.decode(msg, sub)
        except Exception as e:
            log(f"    ! {key} +{h}h: decodifica non riuscita ({e})")
            continue
        if lats is None:
            lats, lons = la, lo
        elif v.shape != (len(lats), len(lons)):
            log(f"    ! {key} +{h}h: griglia diversa, scartato")
            continue
        arrays[key] = model.convert(key, v).astype(np.float32)
    tot, b6 = arrays.pop("tp_total", None), arrays.pop("tp_bucket6", None)
    if h == 0:
        cum = tot if tot is not None else (np.zeros_like(arrays["mslp"]) if "mslp" in arrays else None)
    else:
        cum = tot
        if cum is None and prev_cum is not None and b6 is not None:
            cum = prev_cum + b6
        tp6 = b6
        if tp6 is None and cum is not None and prev_cum is not None:
            tp6 = cum - prev_cum
        if tp6 is not None:
            arrays["tp6"] = np.maximum(tp6, 0.0)
        if cum is not None:
            arrays["tpcum"] = np.maximum(cum, 0.0)
    return lats, lons, arrays, cum


def generate(model, run, public, work, workers, regions, charts, only_steps=None):
    from . import render

    steps = model.steps(run)
    if only_steps:
        steps = [s for s in steps if s in only_steps]
    stage = os.path.join(public, "maps", model.id + ".new")
    shutil.rmtree(stage, ignore_errors=True)
    wdir = os.path.join(work, model.id)
    shutil.rmtree(wdir, ignore_errors=True)
    os.makedirs(wdir)
    info = dict(id=model.id, short=model.chart_label, credit=model.credit)
    results, prev_cum = {}, None
    t0 = time.time()

    def collect(done):
        for f in done:
            try:
                h, ok = f.result()
                results[h] = ok
                os.remove(os.path.join(wdir, f"{h:03d}.npz"))
                log(f"    +{h:3d}h: {len(ok)} carte  ({time.time() - t0:.0f} s)")
            except Exception:
                traceback.print_exc()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = set()
        for h in steps:
            try:
                lats, lons, arrays, prev_cum = prepare_step(model, run, h, prev_cum)
            except Exception as e:
                log(f"    ! +{h}h non scaricata: {e}")
                prev_cum = None
                continue
            if "mslp" not in arrays or lats is None:
                log(f"    ! +{h}h incompleta, saltata")
                continue
            path = os.path.join(wdir, f"{h:03d}.npz")
            np.savez(path, _lats=lats, _lons=lons, **arrays)
            job = dict(npz=path, model=info, run=run.iso, h=h, out=stage, regions=regions, charts=charts)
            pending.add(pool.submit(render.render_step, job))
            while len(pending) >= workers + 1:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                collect(done)
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            collect(done)
    shutil.rmtree(wdir, ignore_errors=True)
    return results, stage


def finalize(model, run, public, stage, results, manifest, regions, charts):
    """Sostituisce le carte vecchie con le nuove; per ECMWF 06/18 tiene le scadenze lunghe della corsa precedente."""
    final = os.path.join(public, "maps", model.id)
    steps = [dict(h=h, run=run.iso, valid=iso(run.time + dt.timedelta(hours=h)), charts=results[h])
             for h in sorted(results) if results[h]]
    if not steps:
        shutil.rmtree(stage, ignore_errors=True)
        raise RuntimeError("nessuna carta prodotta")
    last_valid = parse_iso(steps[-1]["valid"])
    old = manifest["models"].get(model.id)
    kept = 0
    if old and os.path.isdir(final):
        for e in old.get("steps", []):
            r0, v0 = parse_iso(e["run"]), parse_iso(e["valid"])
            if v0 > last_valid and run.time - dt.timedelta(hours=12) <= r0 < run.time:
                for rid in regions:
                    for cid in e["charts"]:
                        src = os.path.join(final, rid, cid, f"{e['h']:03d}.png")
                        if os.path.exists(src):
                            dst = os.path.join(stage, rid, cid, f"{e['h']:03d}.png")
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.move(src, dst)
                steps.append(e)
                kept += 1
    if os.path.isdir(final):
        os.rename(final, final + ".old")
    os.rename(stage, final)
    shutil.rmtree(final + ".old", ignore_errors=True)
    steps.sort(key=lambda e: e["valid"])
    used = [c for c in charts if any(c in e["charts"] for e in steps)]
    manifest["models"][model.id] = dict(
        label=model.long_label, short=model.label, credit=model.credit, run=run.iso,
        updated=iso(dt.datetime.now(UTC)), steps=steps, charts=used)
    if kept:
        log(f"  tenute {kept} scadenze lunghe della corsa precedente")


def gh_output(**kw):
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a") as f:
            for k, v in kw.items():
                f.write(f"{k}={v}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public", default="public", help="cartella del sito pubblicato")
    ap.add_argument("--work", default="work", help="cartella temporanea")
    ap.add_argument("--models", default="gfs,ecmwf")
    ap.add_argument("--force", action="store_true", help="rigenera anche se la corsa è già pubblicata")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--steps", help="solo queste scadenze (prove), es. 0,6,12")
    ap.add_argument("--regions", help="solo queste aree (prove)")
    ap.add_argument("--charts", help="solo queste carte (prove)")
    a = ap.parse_args(argv)

    regions = a.regions.split(",") if a.regions else [r["id"] for r in C.REGIONS]
    charts = a.charts.split(",") if a.charts else [c["id"] for c in C.CHARTS]
    only = [int(s) for s in a.steps.split(",")] if a.steps else None
    manifest = load_manifest(a.public)
    updated, errors = [], []
    for mid in a.models.split(","):
        model = MODELS[mid]
        try:
            run = model.latest()
            if run is None:
                log(f"{model.label}: nessuna corsa completa trovata")
                continue
            cur = manifest["models"].get(mid, {}).get("run")
            if cur == run.iso and os.path.isdir(os.path.join(a.public, "maps", mid)) and not a.force:
                log(f"{model.label}: la corsa {run.time:%d/%m %H}Z è già pubblicata")
                continue
            log(f"{model.label}: genero la corsa {run.time:%d/%m/%Y %H}Z da {run.root}")
            t0 = time.time()
            results, stage = generate(model, run, a.public, a.work, a.workers, regions, charts, only)
            finalize(model, run, a.public, stage, results, manifest, regions, charts)
            save_manifest(a.public, manifest)
            updated.append(mid)
            n = sum(len(v) for v in results.values()) * len(regions)
            log(f"{model.label}: {n} carte in {time.time() - t0:.0f} s")
        except Exception as e:
            errors.append(mid)
            log(f"::error::{model.label}: generazione non riuscita: {e}")
            traceback.print_exc()
    if updated:
        save_manifest(a.public, manifest)
    gh_output(updated="true" if updated else "false", models=",".join(updated), errors=",".join(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
