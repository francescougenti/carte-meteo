"""Neve al suolo nei comprensori sciistici secondo il modello ICON-EU (circa 7 km), a valle e in quota.

Serve quando il comprensorio non pubblica le altezze della neve: "a valle" è il valore del modello nel
punto del comprensorio, "in quota" quello della cella più alta del modello entro RAGGIO_KM, con la sua quota.

Risultato: data/campioni/icon-eu-neve.npz (letto da sci.update).
"""
import datetime as dt
import json
import os

import numpy as np

from . import points

RAGGIO_KM = 8.0


class Peaks:
    def __init__(self, public):
        self.public = public
        self.resorts, self.cells, self.alts, self.sampler = [], None, None, None
        self.rows = []
        try:
            with open(os.path.join(public, "data", "sci.json"), encoding="utf-8") as f:
                self.resorts = [dict(id=r["id"], lat=r["lat"], lon=r["lon"]) for r in json.load(f)["comprensori"]]
        except Exception:
            self.resorts = []

    @property
    def ready(self):
        return self.cells is not None

    def start(self, lats, lons, orog):
        """Sceglie per ogni comprensorio la cella del modello più alta nel raggio."""
        if not self.resorts:
            return
        self.sampler = points.sampler(lats, lons, self.resorts)
        self.cells, self.alts = [], []
        dlat = RAGGIO_KM / 111.0
        for r in self.resorts:
            dlon = dlat / max(np.cos(np.radians(r["lat"])), 0.2)
            jj = np.where(np.abs(lats - r["lat"]) <= dlat)[0]
            ii = np.where(np.abs(lons - r["lon"]) <= dlon)[0]
            if not len(jj) or not len(ii):
                self.cells.append(None), self.alts.append(np.nan)
                continue
            sub = orog[np.ix_(jj, ii)]
            if not np.isfinite(sub).any():
                self.cells.append(None), self.alts.append(np.nan)
                continue
            j, i = np.unravel_index(np.nanargmax(sub), sub.shape)
            self.cells.append((int(jj[j]), int(ii[i])))
            self.alts.append(float(sub[j, i]))

    def add(self, h, valid, arrays):
        if not self.ready or "snow" not in arrays:
            return
        snow = arrays["snow"]
        top = [float(snow[c]) if c else np.nan for c in self.cells]
        self.rows.append((h, valid, np.array(top, np.float32), self.sampler(snow).astype(np.float32)))

    def write(self, run):
        if not self.rows:
            return
        ids = [r["id"] for r in self.resorts]
        series = {"cima": np.stack([r[2] for r in self.rows], axis=1), "valle": np.stack([r[3] for r in self.rows], axis=1)}
        points.write_samples(self.public, "icon-eu-neve", run.iso, ids, [r[0] for r in self.rows], [r[1] for r in self.rows],
                             series, orog=np.array(self.alts, np.float32))


def write_standalone(public, model, run, log=print):
    """Come durante la generazione delle carte, ma scaricando solo neve al suolo e quota del terreno (ICON-EU)."""
    from . import grib
    from .sources import download
    peaks = Peaks(public)
    if not peaks.resorts:
        return
    for h in model.steps(run):
        plan = {k: v for k, v in model.plan(run, h).items() if k in ("snow", "orog")}
        try:
            raw = download(plan, threads=2)
        except Exception as e:
            log(f"    ! neve nei comprensori +{h}h: {e}")
            continue
        arrays, lats, lons = {}, None, None
        for key, (msg, sub) in raw.items():
            la, lo, v = grib.decode(msg, sub)
            lats, lons, arrays[key] = la, lo, model.convert(key, v).astype(np.float32)
        if lats is None:
            continue
        if not peaks.ready and "orog" in arrays:
            peaks.start(lats, lons, arrays["orog"])
        peaks.add(h, (run.time + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ"), arrays)
    peaks.write(run)
    log(f"    neve nei comprensori: {len(peaks.rows)} scadenze di {model.id}")
