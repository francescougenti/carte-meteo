"""Sorgenti dati: individua l'ultima corsa disponibile e scarica solo i campi necessari.

Usa solo la libreria standard di Python, così il controllo orario non richiede installazioni.

GFS   -> NOAA/NCEP, file GRIB2 0.25° su AWS (Open Data) con ripiego su NOMADS
ECMWF -> ECMWF Open Data (IFS 0.25°, licenza CC BY 4.0) con ripiego sul mirror AWS
"""
import bz2
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "carte-meteo/1.0 (generatore di carte meteo)"
UTC = dt.timezone.utc


def log(*a):
    print(*a, flush=True)


def now_utc():
    fake = os.environ.get("METEO_NOW")  # solo per i test
    if fake:
        return dt.datetime.strptime(fake, "%Y%m%d%H%M").replace(tzinfo=UTC)
    return dt.datetime.now(UTC)


def http_get(url, rng=None, timeout=90, tries=4):
    """GET con eventuale intervallo di byte (rng = (inizio, fine) oppure (inizio, None))."""
    err = None
    for k in range(tries):
        headers = {"User-Agent": UA}
        if rng:
            headers["Range"] = f"bytes={rng[0]}-{'' if rng[1] is None else rng[1]}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if rng and r.status == 200:  # il server ha ignorato l'intervallo
                    data = data[rng[0]: None if rng[1] is None else rng[1] + 1]
                return data
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                raise
            err = e
        except Exception as e:  # rete instabile: riprova
            err = e
        time.sleep(3 * (k + 1) ** 2)
    raise err


def http_exists(url, timeout=30):
    """True se il file esiste. Prova HEAD e, se il server non lo accetta, una GET di un solo byte."""
    for method in ("HEAD", "GET"):
        try:
            headers = {"User-Agent": UA}
            if method == "GET":
                headers["Range"] = "bytes=0-0"
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status in (200, 206)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
        except Exception:
            pass
    return False


def first_working(urls, fetch):
    """Prova le sorgenti in ordine e restituisce (url, dati) della prima che risponde."""
    err = None
    for u in urls:
        try:
            return u, fetch(u)
        except Exception as e:
            err = e
    raise err


def cycles_back(n=6):
    """Le ultime n corse sinottiche (00/06/12/18 UTC), dalla più recente."""
    t = now_utc()
    t = t.replace(minute=0, second=0, microsecond=0, hour=(t.hour // 6) * 6)
    return [t - dt.timedelta(hours=6 * k) for k in range(n)]


class Run:
    def __init__(self, model, time, root, stream=None):
        self.model, self.time, self.root, self.stream = model, time, root, stream

    @property
    def id(self):
        return self.time.strftime("%Y%m%d%H")

    @property
    def iso(self):
        return self.time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def __repr__(self):
        return f"{self.model.id} {self.time:%Y-%m-%d %HZ} ({self.root})"


# --------------------------------------------------------------------------------------
# GFS
# --------------------------------------------------------------------------------------
class GFS:
    id = "gfs"
    kind = "det"
    regions = None  # tutte le aree
    label = "GFS"
    long_label = "GFS 0.25° (NOAA/NCEP)"
    chart_label = "GFS 0.25°"
    credit = "Dati: NOAA/NCEP – GFS 0.25°"
    max_step = 192
    roots = [
        os.environ.get("METEO_GFS_ROOT") or "https://noaa-gfs-bdp-pds.s3.amazonaws.com",
        "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod",
    ]
    # campo -> (variabile, livello) nell'indice .idx
    FIELDS = {
        "mslp": ("PRMSL", "mean sea level"),
        "z500": ("HGT", "500 mb"),
        "z1000": ("HGT", "1000 mb"),
        "z250": ("HGT", "250 mb"),
        "t850": ("TMP", "850 mb"),
        "t500": ("TMP", "500 mb"),
        "t2m": ("TMP", "2 m above ground"),
        "rh850": ("RH", "850 mb"),
        "rh700": ("RH", "700 mb"),
        "u10": ("UGRD", "10 m above ground"),
        "v10": ("VGRD", "10 m above ground"),
        "u250": ("UGRD", "250 mb"),
        "v250": ("VGRD", "250 mb"),
        "gust": ("GUST", "surface"),
        "cape": ("CAPE", "surface"),
        "tcc": ("TCDC", "entire atmosphere*"),  # "*": il livello inizia così (la dicitura è cambiata nelle versioni)
        "pwat": ("PWAT", "entire atmosphere*"),
        "snow": ("SNOD", "surface"),
        "fzl": ("HGT", "0C isotherm"),
    }

    def steps(self, run):
        return list(range(0, self.max_step + 1, 6))

    def url(self, root, t, fh):
        d, h = t.strftime("%Y%m%d"), t.strftime("%H")
        return f"{root}/gfs.{d}/{h}/atmos/gfs.t{h}z.pgrb2.0p25.f{fh:03d}"

    def latest(self):
        if os.environ.get("METEO_GFS_ROOT"):
            self.roots = self.roots[:1]
        for t in cycles_back():
            for root in self.roots:
                if http_exists(self.url(root, t, self.max_step) + ".idx"):
                    return Run(self, t, root)
        return None

    @staticmethod
    def parse_idx(text):
        recs = []
        for line in text.splitlines():
            p = line.strip().split(":")
            if len(p) < 6:
                continue
            recs.append(dict(n=p[0], offset=int(p[1]), var=p[3], level=p[4], time=p[5]))
        offsets = sorted({r["offset"] for r in recs})
        nxt = {o: (offsets[i + 1] - 1 if i + 1 < len(offsets) else None) for i, o in enumerate(offsets)}
        for r in recs:
            r["end"] = nxt[r["offset"]]
            r["sub"] = int(r["n"].split(".")[1]) - 1 if "." in r["n"] else 0
        return recs

    def plan(self, run, fh):
        """Restituisce {campo: (url, (inizio, fine), sotto-messaggio)}."""
        roots = [run.root] + [r for r in self.roots if r != run.root]
        url, idx = first_working([self.url(r, run.time, fh) for r in roots], lambda u: http_get(u + ".idx"))
        recs = self.parse_idx(idx.decode())
        when = "anl" if fh == 0 else f"{fh} hour fcst"
        out = {}
        for key, (var, level) in self.FIELDS.items():
            cand = [r for r in recs if r["var"] == var and (
                r["level"] == level or (level.endswith("*") and r["level"].startswith(level[:-1])))]
            if not cand:
                continue
            best = next((r for r in cand if r["time"] == when), None) or next(
                (r for r in cand if "ave" not in r["time"] and "acc" not in r["time"]), cand[0])
            out[key] = (url, (best["offset"], best["end"]), best["sub"])
        if fh > 0:
            apcp = [r for r in recs if r["var"] == "APCP" and r["level"] == "surface"]
            for r in apcp:
                if r["time"] == f"{fh - 6}-{fh} hour acc fcst":
                    out["tp_bucket6"] = (url, (r["offset"], r["end"]), r["sub"])
                if r["time"] == f"0-{fh} hour acc fcst":
                    out["tp_total"] = (url, (r["offset"], r["end"]), r["sub"])
        return out

    def convert(self, key, a):
        if key == "mslp":
            return a / 100.0
        if key.startswith("z"):
            return a / 10.0
        if key in ("t850", "t500", "t2m"):
            return a - 273.15
        if key == "snow":
            return a * 100.0  # m -> cm
        return a  # RH %, vento m/s, pioggia kg/m² = mm, CAPE J/kg, nubi %, PWAT mm, zero termico m

    def derive(self, arrays):
        return arrays


# --------------------------------------------------------------------------------------
# ECMWF IFS (open data)
# --------------------------------------------------------------------------------------
class ECMWF:
    id = "ecmwf"
    kind = "det"
    regions = None
    path = "ifs"
    env_root = "METEO_ECMWF_ROOT"
    label = "ECMWF"
    long_label = "ECMWF IFS 0.25° (Open Data)"
    chart_label = "ECMWF IFS 0.25°"
    credit = "Dati: ECMWF Open Data – IFS 0.25° (licenza CC BY 4.0)"
    max_step = 240
    short_step = 144  # le corse delle 06 e 18 UTC arrivano a +144 h
    roots = [
        os.environ.get("METEO_ECMWF_ROOT") or "https://data.ecmwf.int/forecasts",
        "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com",
    ]
    # campo -> (nomi possibili del parametro, tipo di livello, livello)
    FIELDS = {
        "mslp": (["msl"], "sfc", None),
        "z500": (["gh"], "pl", "500"),
        "z1000": (["gh"], "pl", "1000"),
        "z250": (["gh"], "pl", "250"),
        "t850": (["t"], "pl", "850"),
        "t500": (["t"], "pl", "500"),
        "t2m": (["2t"], "sfc", None),
        "rh850": (["r"], "pl", "850"),
        "rh700": (["r"], "pl", "700"),
        "u10": (["10u"], "sfc", None),
        "v10": (["10v"], "sfc", None),
        "u250": (["u"], "pl", "250"),
        "v250": (["v"], "pl", "250"),
        "gust": (["10fg", "10fg6", "10fg3", "i10fg"], "sfc", None),
        "cape": (["mucape", "cape"], "sfc", None),
        "tcc": (["tcc"], "sfc", None),
        "pwat": (["tcwv"], "sfc", None),
        "tp_total": (["tp"], "sfc", None),
        # neve: equivalente in acqua (m) e densità (kg/m³) -> altezza in cm
        "sd": (["sd"], "sfc", None),
        "rsn": (["rsn"], "sfc", None),
        # livelli per calcolare la quota dello zero termico
        "t1000": (["t"], "pl", "1000"), "t925": (["t"], "pl", "925"), "t700": (["t"], "pl", "700"),
        "t600": (["t"], "pl", "600"),
        "z925": (["gh"], "pl", "925"), "z850": (["gh"], "pl", "850"), "z700": (["gh"], "pl", "700"),
        "z600": (["gh"], "pl", "600"),
    }

    def last_step(self, t):
        return self.max_step if t.hour in (0, 12) else self.short_step

    def steps(self, run):
        return list(range(0, self.last_step(run.time) + 1, 6))

    def url(self, root, t, step, stream):
        d, h = t.strftime("%Y%m%d"), t.strftime("%H")
        return f"{root}/{d}/{h}z/{self.path}/0p25/{stream}/{d}{h}0000-{step}h-{stream}-fc.grib2"

    def latest(self):
        if os.environ.get(self.env_root):
            self.roots = self.roots[:1]
        for t in cycles_back():
            streams = ["oper"] if t.hour in (0, 12) or self.path != "ifs" else ["oper", "scda"]
            for root in self.roots:
                for stream in streams:
                    u = self.url(root, t, self.last_step(t), stream)
                    if http_exists(u[: -len(".grib2")] + ".index"):
                        return Run(self, t, root, stream)
        return None

    def plan(self, run, step):
        roots = [run.root] + [r for r in self.roots if r != run.root]
        url, text = first_working([self.url(r, run.time, step, run.stream) for r in roots],
                                  lambda u: http_get(u[: -len(".grib2")] + ".index"))
        text = text.decode()
        entries = [json.loads(line) for line in text.splitlines() if line.strip()]
        out = {}
        for key, (names, levtype, level) in self.FIELDS.items():
            for name in names:
                e = next((e for e in entries if e.get("param") == name and e.get("levtype") == levtype
                          and (level is None or str(e.get("levelist")) == level)), None)
                if e:
                    off, ln = int(e["_offset"]), int(e["_length"])
                    out[key] = (url, (off, off + ln - 1), 0)
                    break
        return out

    def convert(self, key, a):
        if key == "mslp":
            return a / 100.0
        if key.startswith("z"):
            return a / 10.0
        if key == "t2m" or (key.startswith("t") and key[1:].isdigit()):
            return a - 273.15
        if key == "tp_total":
            return a * 1000.0  # m -> mm
        if key == "tcc" and np.nanmax(a) <= 1.01:
            return a * 100.0
        return a

    def derive(self, arrays):
        return derive_snow_fzl(arrays)


LEVELS_FZL = (1000, 925, 850, 700, 600, 500)


def freezing_level(arrays):
    """Quota dello zero termico (m) dalle temperature e dalle quote dei livelli di pressione.

    Si sale dal livello più basso e si interpola dove la temperatura passa da sopra a sotto 0 °C.
    Se fa già sotto zero a 1000 hPa la quota è 0 (zero termico al livello del mare).
    """
    ts = [arrays.get(f"t{p}") for p in LEVELS_FZL]
    zs = [arrays.get(f"z{p}") for p in LEVELS_FZL]
    if any(x is None for x in ts + zs):
        return None
    T = np.stack(ts)
    Z = np.stack(zs) * 10.0  # dam -> m
    out = np.full(T.shape[1:], np.nan, np.float32)
    done = T[0] <= 0
    out[done] = 0.0
    for k in range(len(LEVELS_FZL) - 1):
        t0, t1 = T[k], T[k + 1]
        cross = (~done) & (t0 > 0) & (t1 <= 0)
        frac = t0 / np.where(cross, t0 - t1, 1.0)
        out = np.where(cross, Z[k] + frac * (Z[k + 1] - Z[k]), out)
        done |= cross
    out = np.where(done, out, Z[-1])  # ancora sopra zero a 500 hPa: oltre i 5500 m circa
    return np.maximum(out, 0.0).astype(np.float32)


def derive_snow_fzl(arrays):
    sd, rsn = arrays.pop("sd", None), arrays.pop("rsn", None)
    if sd is not None and rsn is not None and "snow" not in arrays:
        arrays["snow"] = (sd * 1000.0 / np.maximum(rsn, 50.0) * 100.0).astype(np.float32)
    if "fzl" not in arrays:
        f = freezing_level(arrays)
        if f is not None:
            arrays["fzl"] = f
    for k in ("t1000", "t925", "t700", "t600", "z925", "z850", "z700", "z600"):
        arrays.pop(k, None)
    return arrays


def rh_from_q(q, t_c, p):
    """Umidità relativa (%) da umidità specifica (kg/kg) e temperatura (°C) a p hPa."""
    e = q * p / (0.622 + 0.378 * q)
    es = 6.112 * np.exp(17.67 * t_c / (t_c + 243.5))
    return np.clip(100.0 * e / es, 0.0, 100.0)


class AIFS(ECMWF):
    """Modello a intelligenza artificiale di ECMWF (AIFS Single), stesso portale Open Data."""
    id = "aifs"
    label = "AIFS"
    long_label = "ECMWF AIFS 0.25° (intelligenza artificiale)"
    chart_label = "ECMWF AIFS 0.25°"
    credit = "Dati: ECMWF Open Data – AIFS Single 0.25° (licenza CC BY 4.0)"
    path = "aifs-single"
    env_root = "METEO_AIFS_ROOT"
    regions = ["italia", "europa"]
    max_step = 240
    roots = [
        os.environ.get("METEO_AIFS_ROOT") or "https://data.ecmwf.int/forecasts",
        "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com",
    ]
    FIELDS = dict(ECMWF.FIELDS)
    FIELDS.update({
        "rh850": (["r"], "pl", "850"),  # AIFS non dà l'umidità relativa: si ricava da q e T
        "rh700": (["r"], "pl", "700"),
        "q850": (["q"], "pl", "850"),
        "q700": (["q"], "pl", "700"),
        "pwat": (["tcwv", "tcw"], "sfc", None),
    })

    def last_step(self, t):
        return self.max_step

    def convert(self, key, a):
        if key == "tp_total":
            return a  # AIFS dà la pioggia già in kg/m² (= mm), l'IFS invece in metri
        return super().convert(key, a)

    def derive(self, arrays):
        for lev in (850, 700):
            q, t = arrays.get(f"q{lev}"), arrays.get(f"t{lev}")
            if f"rh{lev}" not in arrays and q is not None and t is not None:
                arrays[f"rh{lev}"] = rh_from_q(q, t, float(lev)).astype(np.float32)
        for k in ("q850", "q700"):
            arrays.pop(k, None)
        return derive_snow_fzl(arrays)


class ICONEU:
    """Modello tedesco ICON-EU (DWD), griglia regolare di 0.0625° (circa 7 km) sull'Europa."""
    id = "icon-eu"
    kind = "det"
    label = "ICON-EU"
    long_label = "ICON-EU 0.0625° (DWD)"
    chart_label = "ICON-EU 0.0625°"
    credit = "Dati: Deutscher Wetterdienst (DWD) – ICON-EU"
    regions = ["italia", "europa_ovest"]
    max_step = 120
    roots = [os.environ.get("METEO_ICON_ROOT") or "https://opendata.dwd.de/weather/nwp/icon-eu/grib"]
    # campo -> (parametro DWD, livello in hPa o None)
    FIELDS = {
        "mslp": ("pmsl", None), "z500": ("fi", "500"), "z1000": ("fi", "1000"), "z250": ("fi", "250"),
        "t850": ("t", "850"), "t500": ("t", "500"), "t2m": ("t_2m", None),
        "rh850": ("relhum", "850"), "rh700": ("relhum", "700"),
        "u10": ("u_10m", None), "v10": ("v_10m", None), "u250": ("u", "250"), "v250": ("v", "250"),
        "gust": ("vmax_10m", None), "cape": ("cape_ml", None), "tcc": ("clct", None), "pwat": ("tqv", None),
        "tp_total": ("tot_prec", None), "snow": ("h_snow", None), "fzl": ("hzerocl", None),
    }

    def steps(self, run):
        return list(range(0, self.max_step + 1, 6))

    def url(self, root, t, step, param, level):
        stamp, h = t.strftime("%Y%m%d%H"), t.strftime("%H")
        kind = "pressure-level" if level else "single-level"
        lev = f"{level}_" if level else ""
        return (f"{root}/{h}/{param}/icon-eu_europe_regular-lat-lon_{kind}_{stamp}_{step:03d}_"
                f"{lev}{param.upper()}.grib2.bz2")

    def latest(self):
        for t in cycles_back():
            if http_exists(self.url(self.roots[0], t, self.max_step, "tot_prec", None)):
                return Run(self, t, self.roots[0])
        return None

    def plan(self, run, step):
        return {k: (self.url(run.root, run.time, step, p, lev), None, 0) for k, (p, lev) in self.FIELDS.items()}

    def convert(self, key, a):
        if key == "mslp":
            return a / 100.0
        if key.startswith("z"):
            return a / 9.80665 / 10.0  # geopotenziale (m²/s²) -> dam
        if key in ("t850", "t500", "t2m"):
            return a - 273.15
        if key == "snow":
            return a * 100.0
        if key == "fzl":
            return np.where(a < 0, 0.0, a)  # valore mancante quando fa sotto zero già al suolo
        return a

    def derive(self, arrays):
        return arrays


try:  # numpy serve solo per convert() durante la generazione, non al controllo orario
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

def fetch(url, rng):
    data = http_get(url, rng)
    if url.endswith(".bz2"):
        data = bz2.decompress(data)
    return data


def download(plan, threads=8):
    """Scarica in parallelo i pezzi di GRIB indicati dal piano. Restituisce {campo: (byte, sub)}.

    Un campo che manca sul server (404) viene saltato: la carta che lo usa non sarà disegnata.
    """
    def one(item):
        key, (url, rng, sub) = item
        try:
            return key, (fetch(url, rng), sub)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return key, None
            raise
    with ThreadPoolExecutor(threads) as ex:
        return {k: v for k, v in ex.map(one, plan.items()) if v is not None}


from .ensemble_sources import ECMWFEns, GEFSEns  # noqa: E402

# ordine di elaborazione: prima i deterministici, poi gli ensemble (più pesanti)
MODELS = {"gfs": GFS(), "ecmwf": ECMWF(), "aifs": AIFS(), "icon-eu": ICONEU(),
          "gefs": GEFSEns(), "ecmwf-ens": ECMWFEns()}
