"""Genera le carte delle corse nuove e aggiorna il manifest del sito.

    python -m meteo.build --public public              # GFS ed ECMWF, solo se c'è una corsa nuova
    python -m meteo.build --public public --force      # rigenera comunque
    python -m meteo.build --models gfs --steps 0,6,12  # prove veloci
"""
import argparse
import datetime as dt
import json
import multiprocessing
import os
import shutil
import sys
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

import numpy as np

from . import config as C
from . import citta, ensemble, grib, luoghi, points, verifica
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
        m.setdefault("ensembles", {})
        return m
    except Exception:
        return {"models": {}, "ensembles": {}}


def save_manifest(public, m):
    m["generated"] = iso(dt.datetime.now(UTC))
    m["regions"] = [dict(id=r["id"], label=r["label"]) for r in C.REGIONS]
    m["groups"] = C.GROUPS
    m["charts"] = [dict(id=c["id"], label=c["label"], group=c["group"], title=c["title"], regions=c.get("regions"))
                   for c in C.CHARTS]
    m["ens_products"] = [dict(id=p["id"], label=p["label"], title=p["title"]) for p in C.ENS_PRODUCTS]
    m["cities"] = [dict(id=c["id"], name=c["name"]) for c in C.CITIES]
    m["order"] = [k for k in MODELS]
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
    arrays = model.derive(arrays)
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
    rows, sampler = [], None
    places = luoghi.sample_points()
    prows, psampler, orog = [], None, None

    def collect(done):
        for f in done:
            try:
                h, ok = f.result()
                results[h] = ok
                os.remove(os.path.join(wdir, f"{h:03d}.npz"))
                log(f"    +{h:3d}h: {len(ok)} carte  ({time.time() - t0:.0f} s)")
            except Exception:
                traceback.print_exc()

    # i processi si rinnovano ogni poche scadenze: la memoria resta sotto controllo per tutta la corsa
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx, max_tasks_per_child=6) as pool:
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
            if sampler is None:
                sampler = points.sampler(lats, lons)
                psampler = points.sampler(lats, lons, places)
            rows.append((h, iso(run.time + dt.timedelta(hours=h)), points.det_values(arrays, sampler)))
            if "orog" in arrays:
                orog = psampler(arrays.pop("orog"))
            prows.append((h, iso(run.time + dt.timedelta(hours=h)), points.place_values(arrays, psampler)))
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
    if rows:
        points.write_det(public, model, run.iso, rows)
    if prows:
        keep_long_samples(public, model, run)
        points.write_samples(public, model.id, run.iso, [p["id"] for p in places], [r[0] for r in prows],
                             [r[1] for r in prows], points.det_series(prows, [p["id"] for p in places]), orog)
    return results, stage


def keep_long_samples(public, model, run):
    """ECMWF 06/18 arriva a +144 h: si tiene da parte la corsa precedente, che arriva a +240 h."""
    path = os.path.join(public, "data", "campioni", f"{model.id}.npz")
    if not os.path.exists(path):
        return
    try:
        with np.load(path) as z:
            old_reach = int(z["h"][-1]) if len(z["h"]) else 0
    except Exception:
        return
    if max(model.steps(run)) < old_reach:
        os.replace(path, path.replace(".npz", "-lungo.npz"))


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
            if v0 > last_valid and run.time - dt.timedelta(hours=12) <= r0 < run.time \
                    and old.get("ext", "png") == C.IMG_EXT:
                for rid in regions:
                    for cid in e["charts"]:
                        src = os.path.join(final, rid, cid, f"{e['h']:03d}.{old.get('ext', 'png')}")
                        if os.path.exists(src):
                            dst = os.path.join(stage, rid, cid, os.path.basename(src))
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
        updated=iso(dt.datetime.now(UTC)), steps=steps, charts=used, regions=regions, ext=C.IMG_EXT,
        schema=C.SCHEMA)
    if kept:
        log(f"  tenute {kept} scadenze lunghe della corsa precedente")


def restore_state(public):
    """Se la cache è andata persa, recupera dal sito pubblicato lo storico delle previsioni per città
    e i dati raccolti per la verifica (altrimenti si ripartirebbe da zero)."""
    site = os.environ.get("METEO_SITE_URL", "").rstrip("/")
    if not site.startswith("https://"):
        return
    import urllib.request

    def get(rel):
        dst = os.path.join(public, rel)
        if os.path.exists(dst):
            return None
        try:
            with urllib.request.urlopen(f"{site}/{rel}", timeout=60) as r:
                body = r.read()
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(body)
            return body
        except Exception:
            return None
    got = 0
    idx = get("data/citta/indice.json")
    if idx:
        got += 1
        for p in json.loads(idx).get("luoghi", []):
            got += get(f"data/citta/{p['id']}.json") is not None
    for rel in ("data/verifica/previsioni.json", "data/verifica/osservazioni.json"):
        got += get(rel) is not None
    if got:
        log(f"Recuperati dal sito pubblicato {got} file di storico e verifica")


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
    ap.add_argument("--models", default="", help="modelli separati da virgola (predefinito: tutti)")
    ap.add_argument("--force", action="store_true", help="rigenera anche se la corsa è già pubblicata")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--steps", help="solo queste scadenze (prove), es. 0,6,12")
    ap.add_argument("--regions", help="solo queste aree (prove)")
    ap.add_argument("--charts", help="solo queste carte (prove)")
    a = ap.parse_args(argv)

    all_regions = a.regions.split(",") if a.regions else [r["id"] for r in C.REGIONS]
    charts = a.charts.split(",") if a.charts else [c["id"] for c in C.CHARTS]
    only = [int(s) for s in a.steps.split(",")] if a.steps else None
    manifest = load_manifest(a.public)
    updated, errors = [], []
    for mid in (a.models.split(",") if a.models else list(MODELS)):
        model = MODELS[mid]
        group = "ensembles" if model.kind == "ens" else "models"
        try:
            run = model.latest()
            if run is None:
                log(f"{model.label}: nessuna corsa completa trovata")
                continue
            entry = manifest[group].get(mid, {})
            same = entry.get("run") == run.iso and entry.get("schema", 1) >= C.SCHEMA
            if same and os.path.isdir(os.path.join(a.public, "maps", mid)) and not a.force:
                log(f"{model.label}: la corsa {run.time:%d/%m %H}Z è già pubblicata")
                continue
            log(f"{model.label}: genero la corsa {run.time:%d/%m/%Y %H}Z da {run.root}")
            t0 = time.time()
            if model.kind == "ens":
                results, stage = ensemble.generate(model, run, a.public, a.work, a.workers, only)
                ensemble.finalize(model, run, a.public, stage, results, manifest)
                n = sum(len(v) for v in results.values()) * len(C.ENS_REGIONS)
            else:
                regions = [r for r in all_regions if not model.regions or r in model.regions]
                results, stage = generate(model, run, a.public, a.work, a.workers, regions, charts, only)
                finalize(model, run, a.public, stage, results, manifest, regions, charts)
                n = sum(len(v) for v in results.values()) * len(regions)
            save_manifest(a.public, manifest)
            updated.append(mid)
            log(f"{model.label}: {n} carte in {time.time() - t0:.0f} s")
        except Exception as e:
            errors.append(mid)
            log(f"::error::{model.label}: generazione non riuscita: {e}")
            traceback.print_exc()
    if updated:
        save_manifest(a.public, manifest)
    # pochi secondi: si ricalcola a ogni giro, così anche le correzioni al calcolo arrivano subito
    restore_state(a.public)
    try:
        t0 = time.time()
        info = citta.build(a.public, log=log)
        verifica.update(a.public, info, log=log)
        log(f"Previsione per città e verifica: {time.time() - t0:.0f} s")
    except Exception as e:
        log(f"::warning::Previsione per città non aggiornata: {e}")
        traceback.print_exc()
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(a.public) for f in fs) / 1e6
    log(f"Spazio occupato dal sito: {size:.0f} MB")
    if size > 950:
        log("::warning::Il sito supera 950 MB: GitHub Pages accetta al massimo 1 GB")
    gh_output(updated="true" if updated else "false", models=",".join(updated), errors=",".join(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
