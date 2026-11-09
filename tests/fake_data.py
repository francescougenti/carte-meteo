"""Crea dati GRIB2 sintetici con la stessa struttura dei server NOAA (GFS) ed ECMWF Open Data.

Serve solo a provare la catena completa (indice -> scaricamento a intervalli di byte -> decodifica ->
disegno) senza accesso ai server reali. I campi sono inventati ma fisicamente plausibili.

    python tests/fake_data.py /tmp/fake 2026110700
"""
import datetime as dt
import json
import os
import sys

import eccodes
import numpy as np

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fake"
BASE = dt.datetime.strptime(sys.argv[2] if len(sys.argv) > 2 else "2026110700", "%Y%m%d%H")

LAT = np.linspace(90, -90, 721)
LON_GFS = np.arange(1440) * 0.25  # 0 .. 359.75
LON_EC = -180 + np.arange(1440) * 0.25  # -180 .. 179.75


def blob(lon, lat, lon0, lat0, s):
    d = ((lon - lon0 + 180) % 360) - 180
    return np.exp(-(d ** 2 * np.cos(np.radians(lat0)) ** 2 + (lat - lat0) ** 2) / (2 * s ** 2))


def atmosphere(lon1d, valid_h, seed, lat1d=LAT):
    lon, lat = np.meshgrid(lon1d, lat1d)
    res = abs(float(lat1d[1] - lat1d[0]))
    t = valid_h / 24.0
    rng = np.random.default_rng(seed)
    clat = np.clip(lat, -80, 80)
    # geopotenziale 500 hPa: gradiente meridiano + onde di Rossby + goccia fredda in movimento
    z500 = 5880 - 330 * (1 + np.tanh((np.abs(clat) - 48) / 18)) - 2.2 * np.maximum(np.abs(clat) - 60, 0) ** 1.5
    wave = 140 * np.sin(np.radians(5 * lon - 25 * t)) * np.exp(-((clat - 52) / 14) ** 2)
    cut_lon, cut_lat = -5 + 6 * t, 44 - 0.6 * t
    z500 = z500 + wave - 230 * blob(lon, lat, cut_lon, cut_lat, 6) + 120 * blob(lon, lat, 25 + 3 * t, 55, 9)
    # pressione al suolo
    mslp = (101500 + 1700 * blob(lon, lat, -30 + 2 * t, 37, 10) - 2600 * blob(lon, lat, -25 + 8 * t, 61, 8)
            - 1500 * blob(lon, lat, cut_lon + 4, cut_lat - 2, 4.5) + 1600 * blob(lon, lat, 60, 55, 12)
            - 2100 * blob(lon, lat, -60 + 7 * t, 48, 6) + 1200 * blob(lon, lat, -100, 40, 9)
            + 800 * np.sin(np.radians(3 * lon + 10 * t)) * np.exp(-((clat - 30) / 10) ** 2))
    za = z500 - (5880 - 330 * (1 + np.tanh((np.abs(clat) - 48) / 18)))
    t850 = 273.15 + 24 - 0.62 * np.maximum(clat, 0) + 0.035 * za + 2 * np.sin(np.radians(2 * lon))
    t500 = t850 - 27 - 0.04 * np.maximum(clat - 30, 0)
    t2m = t850 + 7 + 3 * np.cos(np.radians(lon - 15 * t))
    rh = np.clip(55 + 35 * np.sin(np.radians(4 * lon + 2 * lat - 30 * t)) + 30 * blob(lon, lat, cut_lon + 4, cut_lat - 2, 6)
                 + 4 * rng.standard_normal(lon.shape), 3, 100)
    f = 2 * 7.292e-5 * np.sin(np.radians(np.where(np.abs(clat) < 8, 8 * np.sign(clat + 1e-9), clat)))
    dy = 111e3 * res
    dx = dy * np.cos(np.radians(clat))

    def geo(phi):  # vento geostrofico da un campo di geopotenziale (m)
        dpy = np.gradient(phi, axis=0) / (-dy)  # LAT decrescente
        dpx = np.gradient(phi, axis=1) / dx
        return -9.81 / f * dpy, 9.81 / f * dpx

    u10, v10 = geo(mslp / (1.2 * 9.81))
    u10, v10 = 0.55 * u10, 0.55 * v10
    z250 = 10500 + 1.9 * (z500 - 5600)
    u250, v250 = geo(z250)
    sp = np.hypot(u250, v250)
    lim = np.minimum(1, 95 / np.maximum(sp, 1))
    u250, v250 = u250 * lim, v250 * lim
    sp10 = np.hypot(u10, v10)
    lim = np.minimum(1, 30 / np.maximum(sp10, 1))
    u10, v10 = u10 * lim, v10 * lim
    rate = np.clip((101200 - mslp) / 100, 0, None) * 0.9 * (rh / 100) ** 2 + 0.6 * np.clip(rh - 80, 0, None) / 20
    return dict(
        mslp=mslp, z500=z500, z1000=(mslp - 101325) / 100 * 8.3 + 110, z250=z250, t850=t850, t500=t500,
        t2m=t2m, rh850=np.clip(rh + 8, 0, 100), rh700=rh, u10=u10, v10=v10, u250=u250, v250=v250,
        gust=np.hypot(u10, v10) * 1.6 + 2, cape=np.clip((t2m - 288) * 120, 0, None) * (rh / 100) ** 2,
        tcc=np.clip(rh * 1.1 - 20, 0, 100), pwat=np.clip(4 + 0.45 * rh * np.exp((t850 - 273) / 14), 1, 70),
        rate6=rate * 6,
    )


SAMPLE = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")


def encode(values, lon_first, lat1d=LAT, lon1d=None):
    h = eccodes.codes_clone(SAMPLE)
    nj, ni = values.shape
    res = abs(float(lat1d[1] - lat1d[0]))
    lon_last = lon_first + (ni - 1) * res
    for k, v in (("Ni", ni), ("Nj", nj), ("latitudeOfFirstGridPointInDegrees", float(lat1d[0])),
                 ("longitudeOfFirstGridPointInDegrees", lon_first % 360),
                 ("latitudeOfLastGridPointInDegrees", float(lat1d[-1])),
                 ("longitudeOfLastGridPointInDegrees", lon_last % 360),
                 ("iDirectionIncrementInDegrees", res), ("jDirectionIncrementInDegrees", res),
                 ("jScansPositively", 1 if lat1d[0] < lat1d[-1] else 0), ("bitsPerValue", 16)):
        eccodes.codes_set(h, k, v)
    eccodes.codes_set_values(h, values.astype(np.float64).ravel())
    msg = eccodes.codes_get_message(h)
    eccodes.codes_release(h)
    return msg


def write_gfs(run, steps):
    d, hh = run.strftime("%Y%m%d"), run.strftime("%H")
    folder = os.path.join(OUT, "gfs", f"gfs.{d}", hh, "atmos")
    os.makedirs(folder, exist_ok=True)
    cum = 0
    prev = 0
    for fh in sorted(steps):
        a = atmosphere(LON_GFS, run.hour + fh, fh)
        if fh > 0:
            for k in range(prev, fh, 6):  # accumula anche le scadenze non scritte
                cum = cum + atmosphere(LON_GFS, run.hour + k + 6, k)["rate6"]
        prev = fh
        when = "anl" if fh == 0 else f"{fh} hour fcst"
        recs = [("CLMR", "1 hybrid level", when, a["t850"] * 0),
                ("PRMSL", "mean sea level", when, a["mslp"]),
                ("HGT", "1000 mb", when, a["z1000"]), ("HGT", "500 mb", when, a["z500"]),
                ("HGT", "250 mb", when, a["z250"]), ("TMP", "850 mb", when, a["t850"]),
                ("TMP", "500 mb", when, a["t500"]), ("RH", "850 mb", when, a["rh850"]),
                ("RH", "700 mb", when, a["rh700"]), ("UGRD", "250 mb", when, a["u250"]),
                ("VGRD", "250 mb", when, a["v250"]), ("TMP", "2 m above ground", when, a["t2m"]),
                ("UGRD", "10 m above ground", when, a["u10"]), ("VGRD", "10 m above ground", when, a["v10"]),
                ("GUST", "surface", when, a["gust"]), ("CAPE", "surface", when, a["cape"]),
                ("CAPE", "180-0 mb above ground", when, a["cape"] * 0.5),
                ("PWAT", "entire atmosphere (considered as a single layer)", when, a["pwat"]),
                ("SNOD", "surface", when, np.clip((2 - (a["t2m"] - 273.15)) * 0.05, 0, None)),
                ("HGT", "0C isotherm", when, np.clip((a["t850"] - 273.15) * 150 + 1500, 0, None))]
        if fh > 0:
            recs += [("TCDC", "entire atmosphere", f"{max(fh - 6, 0)}-{fh} hour ave fcst", a["tcc"] * 0.8),
                     ("TCDC", "entire atmosphere", when, a["tcc"]),
                     ("APCP", "surface", f"{fh - 6}-{fh} hour acc fcst", a["rate6"]),
                     ("APCP", "surface", f"0-{fh} hour acc fcst", cum)]
        path = os.path.join(folder, f"gfs.t{hh}z.pgrb2.0p25.f{fh:03d}")
        lines, off = [], 0
        with open(path, "wb") as f:
            for n, (var, lev, tm, val) in enumerate(recs, 1):
                msg = encode(val, 0.0)
                f.write(msg)
                lines.append(f"{n}:{off}:d={run:%Y%m%d%H}:{var}:{lev}:{tm}:")
                off += len(msg)
        with open(path + ".idx", "w") as f:
            f.write("\n".join(lines) + "\n")
    print("GFS", run, sorted(steps))


def write_ecmwf(run, steps, top="ecmwf", path="ifs", aifs=False):
    d, hh = run.strftime("%Y%m%d"), run.strftime("%H")
    folder = os.path.join(OUT, top, d, f"{hh}z", path, "0p25", "oper")
    os.makedirs(folder, exist_ok=True)
    for st in sorted(steps):
        a = atmosphere(LON_EC, run.hour + st, 1000 + st)
        cum = sum(atmosphere(LON_EC, run.hour + k + 6, 1000 + k)["rate6"] for k in range(0, st, 6)) if st else a["mslp"] * 0
        recs = [("msl", "sfc", None, a["mslp"]), ("2t", "sfc", None, a["t2m"]), ("10u", "sfc", None, a["u10"]),
                ("10v", "sfc", None, a["v10"]), ("tcc", "sfc", None, a["tcc"] / (100.0 if aifs else 1.0)),
                ("tp", "sfc", None, cum / 1000.0)]
        if aifs:
            recs.append(("tcw", "sfc", None, a["pwat"]))
        else:
            recs += [("tcwv", "sfc", None, a["pwat"]), ("mucape", "sfc", None, a["cape"])]
        if st and not aifs:
            recs.append(("10fg", "sfc", None, a["gust"] * 1.05))
        zl = {"1000": a["z1000"], "925": a["z1000"] + 680, "850": a["z1000"] + 1350, "700": a["z500"] - 2600,
              "600": a["z500"] - 1300, "500": a["z500"], "250": a["z250"]}
        for lev in ("1000", "925", "850", "700", "600", "500", "250"):
            tl = a["t500"] if lev in ("500", "250") else a["t850"] + 0.0065 * (zl["850"] - zl[lev])
            rl = a["rh850"] if lev == "850" else a["rh700"]
            recs += [("gh", "pl", lev, zl[lev]), ("t", "pl", lev, tl),
                     (("q", "pl", lev, qfrom(rl, tl - 273.15, float(lev))) if aifs else ("r", "pl", lev, rl)),
                     ("u", "pl", lev, a["u250"]), ("v", "pl", lev, a["v250"])]
        if not aifs:
            recs += [("sd", "sfc", None, np.clip((2 - (a["t2m"] - 273.15)) * 0.012, 0, None)),
                     ("rsn", "sfc", None, a["t2m"] * 0 + 240.0)]
        name = f"{d}{hh}0000-{st}h-oper-fc"
        lines, off = [], 0
        with open(os.path.join(folder, name + ".grib2"), "wb") as f:
            for p, lt, lev, val in recs:
                msg = encode(val, -180.0)
                f.write(msg)
                e = {"domain": "g", "date": d, "time": hh + "00", "expver": "0001", "class": "od",
                     "type": "fc", "stream": "oper", "step": str(st), "levtype": lt, "param": p,
                     "_offset": off, "_length": len(msg)}
                if lev:
                    e["levelist"] = lev
                lines.append(json.dumps(e))
                off += len(msg)
        with open(os.path.join(folder, name + ".index"), "w") as f:
            f.write("\n".join(lines) + "\n")
    print(top, run, sorted(steps))


def qfrom(rh, t_c, p):
    es = 6.112 * np.exp(17.67 * t_c / (t_c + 243.5))
    e = rh / 100.0 * es
    return 0.622 * e / (p - 0.378 * e)


def write_icon(run, steps):
    """ICON-EU: un file .bz2 per campo, griglia regionale 0.0625°."""
    import bz2
    lat = np.round(np.arange(29.5, 70.5 + 1e-6, 0.0625), 4)
    lon = np.round(np.arange(-23.5, 62.5 + 1e-6, 0.0625), 4)
    stamp, hh = run.strftime("%Y%m%d%H"), run.strftime("%H")
    for st in sorted(steps):
        a = atmosphere(lon, run.hour + st, 2000 + st, lat1d=lat)
        cum = sum(atmosphere(lon, run.hour + k + 6, 2000 + k, lat1d=lat)["rate6"] for k in range(0, st, 6)) \
            if st else a["mslp"] * 0
        single = {"pmsl": a["mslp"], "t_2m": a["t2m"], "u_10m": a["u10"], "v_10m": a["v10"],
                  "vmax_10m": a["gust"], "cape_ml": a["cape"], "clct": a["tcc"], "tqv": a["pwat"],
                  "tot_prec": cum, "h_snow": np.clip((2 - (a["t2m"] - 273.15)) * 0.05, 0, None),
                  "hzerocl": np.clip((a["t850"] - 273.15) * 150 + 1500, 0, None)}
        press = {("fi", "500"): a["z500"] * 9.80665, ("fi", "1000"): a["z1000"] * 9.80665,
                 ("fi", "250"): a["z250"] * 9.80665, ("t", "850"): a["t850"], ("t", "500"): a["t500"],
                 ("relhum", "850"): a["rh850"], ("relhum", "700"): a["rh700"],
                 ("u", "250"): a["u250"], ("v", "250"): a["v250"]}
        items = [(p, None, v) for p, v in single.items()] + [(p, lv, v) for (p, lv), v in press.items()]
        for p, lv, v in items:
            folder = os.path.join(OUT, "icon", hh, p)
            os.makedirs(folder, exist_ok=True)
            kind = "pressure-level" if lv else "single-level"
            name = f"icon-eu_europe_regular-lat-lon_{kind}_{stamp}_{st:03d}_{lv + '_' if lv else ''}{p.upper()}.grib2.bz2"
            with open(os.path.join(folder, name), "wb") as f:
                f.write(bz2.compress(encode(v, -23.5, lat1d=lat), 1))
    print("ICON-EU", run, sorted(steps))


def write_gefs(run, steps, members=31):
    lat = np.linspace(90, -90, 361)
    lon = np.arange(720) * 0.5
    d, hh = run.strftime("%Y%m%d"), run.strftime("%H")
    folder = os.path.join(OUT, "gefs", f"gefs.{d}", hh, "atmos", "pgrb2ap5")
    os.makedirs(folder, exist_ok=True)
    names = ["gec00"] + [f"gep{i:02d}" for i in range(1, members)]
    for mi, mem in enumerate(names):
        for fh in sorted(steps):
            a = atmosphere(lon + 4 * mi, run.hour + fh + mi, 3000 + mi * 7 + fh, lat1d=lat)
            when = "anl" if fh == 0 else f"{fh} hour fcst"
            recs = [("HGT", "500 mb", when, a["z500"] + 3 * mi), ("TMP", "850 mb", when, a["t850"] - 0.1 * mi),
                    ("PRMSL", "mean sea level", when, a["mslp"])]
            if fh:
                recs.append(("APCP", "surface", f"{fh - 6}-{fh} hour acc fcst", a["rate6"]))
            path = os.path.join(folder, f"{mem}.t{hh}z.pgrb2a.0p50.f{fh:03d}")
            lines, off = [], 0
            with open(path, "wb") as f:
                for n, (var, lev, tm, val) in enumerate(recs, 1):
                    msg = encode(val, 0.0, lat1d=lat)
                    f.write(msg)
                    lines.append(f"{n}:{off}:d={run:%Y%m%d%H}:{var}:{lev}:{tm}:ENS=+{mi}")
                    off += len(msg)
            with open(path + ".idx", "w") as f:
                f.write("\n".join(lines) + "\n")
    print("GEFS", run, sorted(steps))


def write_ens(run, steps, members=50):
    lat = np.linspace(90, -90, 181)  # griglia di prova a 1° per contenere lo spazio
    lon = -180 + np.arange(360) * 1.0
    d, hh = run.strftime("%Y%m%d"), run.strftime("%H")
    folder = os.path.join(OUT, "ens", d, f"{hh}z", "ifs", "0p25", "enfo")
    os.makedirs(folder, exist_ok=True)
    for st in sorted(steps):
        name = f"{d}{hh}0000-{st}h-enfo-ef"
        lines, off = [], 0
        with open(os.path.join(folder, name + ".grib2"), "wb") as f:
            for m in range(1, members + 1):
                a = atmosphere(lon + 3 * m, run.hour + st + m, 4000 + m * 11 + st, lat1d=lat)
                cum = sum(atmosphere(lon + 3 * m, run.hour + k + 6 + m, 4000 + m * 11 + k, lat1d=lat)["rate6"]
                          for k in range(0, st, 6)) if st else a["mslp"] * 0
                for p, lt, lev, val in (("gh", "pl", "500", a["z500"] - 2 * m), ("t", "pl", "850", a["t850"]),
                                        ("msl", "sfc", None, a["mslp"]), ("tp", "sfc", None, cum / 1000.0),
                                        ("2t", "sfc", None, a["t2m"])):
                    msg = encode(val, -180.0, lat1d=lat)
                    f.write(msg)
                    e = {"type": "pf", "stream": "enfo", "step": str(st), "levtype": lt, "param": p,
                         "number": str(m), "_offset": off, "_length": len(msg)}
                    if lev:
                        e["levelist"] = lev
                    lines.append(json.dumps(e))
                    off += len(msg)
        with open(os.path.join(folder, name + ".index"), "w") as f:
            f.write("\n".join(lines) + "\n")
    print("ENS", run, sorted(steps))


if __name__ == "__main__":
    which = sys.argv[3].split(",") if len(sys.argv) > 3 else ["gfs", "ecmwf", "aifs", "icon", "gefs", "ens"]
    if "gfs" in which:
        write_gfs(BASE, [0, 6, 12, 48, 192])
    if "ecmwf" in which:
        write_ecmwf(BASE, [0, 6, 12, 150, 156, 240])
        write_ecmwf(BASE + dt.timedelta(hours=6), [0, 6, 12, 144])
    if "aifs" in which:
        write_ecmwf(BASE, [0, 6, 12, 240], top="aifs", path="aifs-single", aifs=True)
    if "icon" in which:
        write_icon(BASE, [0, 6, 12, 120])
    if "gefs" in which:
        write_gefs(BASE, [0, 6, 12, 240])
    if "ens" in which:
        write_ens(BASE, [0, 6, 12, 240])
