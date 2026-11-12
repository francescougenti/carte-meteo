"""Sorgenti degli ensemble: GEFS (NOAA, 31 membri) ed ECMWF ENS (50 membri).

Solo libreria standard, come sources.py: il controllo orario le usa senza installare nulla.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

from .sources import GFS, Run, cycles_back, first_working, http_exists, http_get

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class GEFSEns:
    id = "gefs"
    kind = "ens"
    label = "GEFS"
    long_label = "GEFS 0.5° (NOAA, 31 membri)"
    chart_label = "GEFS 0.5°"
    credit = "Dati: NOAA/NCEP – GEFS 0.5° (controllo + 30 membri perturbati)"
    max_step = 240
    members = ["gec00"] + [f"gep{i:02d}" for i in range(1, 31)]
    roots = [os.environ.get("METEO_GEFS_ROOT") or "https://noaa-gefs-pds.s3.amazonaws.com"]
    FIELDS = {"z500": ("HGT", "500 mb"), "t850": ("TMP", "850 mb"), "mslp": ("PRMSL", "mean sea level"),
              "t2m": ("TMP", "2 m above ground")}
    accum = "bucket"  # la pioggia arriva già in intervalli di 6 ore

    def steps(self, run):
        return list(range(0, self.max_step + 1, 6))

    def url(self, root, t, mem, fh):
        d, h = t.strftime("%Y%m%d"), t.strftime("%H")
        return f"{root}/gefs.{d}/{h}/atmos/pgrb2ap5/{mem}.t{h}z.pgrb2a.0p50.f{fh:03d}"

    def latest(self):
        for t in cycles_back():
            if http_exists(self.url(self.roots[0], t, self.members[-1], self.max_step) + ".idx"):
                return Run(self, t, self.roots[0])
        return None

    def plan(self, run, fh):
        """{(indice membro, campo): (url, (inizio, fine), sotto-messaggio)}"""
        when = "anl" if fh == 0 else f"{fh} hour fcst"

        def one(item):
            mi, mem = item
            url = self.url(run.root, run.time, mem, fh)
            try:
                recs = GFS.parse_idx(http_get(url + ".idx").decode())
            except Exception:
                return {}
            out = {}
            for key, (var, lev) in self.FIELDS.items():
                cand = [r for r in recs if r["var"] == var and r["level"] == lev]
                best = next((r for r in cand if r["time"] == when), cand[0] if cand else None)
                if best:
                    out[(mi, key)] = (url, (best["offset"], best["end"]), best["sub"])
            if fh > 0:
                for r in recs:
                    if r["var"] == "APCP" and r["level"] == "surface" and r["time"] == f"{fh - 6}-{fh} hour acc fcst":
                        out[(mi, "tp6")] = (url, (r["offset"], r["end"]), r["sub"])
            return out

        plan = {}
        with ThreadPoolExecutor(16) as ex:
            for part in ex.map(one, enumerate(self.members)):
                plan.update(part)
        return plan

    def convert(self, key, a):
        if key == "mslp":
            return a / 100.0
        if key == "z500":
            return a / 10.0
        if key in ("t850", "t2m"):
            return a - 273.15
        return a


class ECMWFEns:
    id = "ecmwf-ens"
    kind = "ens"
    label = "ECMWF ENS"
    long_label = "ECMWF ENS 0.25° (50 membri)"
    chart_label = "ECMWF ENS 0.25°"
    credit = "Dati: ECMWF Open Data – ENS 0.25°, 50 membri (licenza CC BY 4.0)"
    max_step = 240
    members = list(range(1, 51))
    roots = [
        os.environ.get("METEO_ENS_ROOT") or "https://data.ecmwf.int/forecasts",
        "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com",
    ]
    FIELDS = {"z500": ("gh", "pl", "500"), "t850": ("t", "pl", "850"), "mslp": ("msl", "sfc", None),
              "tp_total": ("tp", "sfc", None), "t2m": ("2t", "sfc", None)}
    accum = "total"  # pioggia cumulata dall'inizio: le 6 ore si ottengono per differenza

    def steps(self, run):
        return list(range(0, self.max_step + 1, 6))

    def url(self, root, t, step):
        d, h = t.strftime("%Y%m%d"), t.strftime("%H")
        return f"{root}/{d}/{h}z/ifs/0p25/enfo/{d}{h}0000-{step}h-enfo-ef.grib2"

    def latest(self):
        if os.environ.get("METEO_ENS_ROOT"):
            self.roots = self.roots[:1]
        for t in cycles_back(8):
            if t.hour not in (0, 12):  # solo le corse che arrivano a +240 h
                continue
            for root in self.roots:
                if http_exists(self.url(root, t, self.max_step)[: -len(".grib2")] + ".index"):
                    return Run(self, t, root)
        return None

    def plan(self, run, step):
        roots = [run.root] + [r for r in self.roots if r != run.root]
        url, text = first_working([self.url(r, run.time, step) for r in roots],
                                  lambda u: http_get(u[: -len(".grib2")] + ".index"))
        out = {}
        for line in text.decode().splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("type") != "pf":
                continue
            try:
                mi = int(e.get("number")) - 1
            except (TypeError, ValueError):
                continue
            for key, (param, levtype, level) in self.FIELDS.items():
                if e.get("param") == param and e.get("levtype") == levtype and (
                        level is None or str(e.get("levelist")) == level):
                    off, ln = int(e["_offset"]), int(e["_length"])
                    out[(mi, key)] = (url, (off, off + ln - 1), 0)
        return out

    def convert(self, key, a):
        if key == "mslp":
            return a / 100.0
        if key == "z500":
            return a / 10.0
        if key in ("t850", "t2m"):
            return a - 273.15
        if key == "tp_total":
            return a * 1000.0
        return a
