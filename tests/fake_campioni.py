"""Campioni sintetici per provare "La tua città" senza scaricare i modelli.

Simula diversi giorni di corse (una ogni 6 ore) di tutti i modelli su tutti i luoghi, con una
perturbazione che attraversa l'Italia, una seconda molto incerta a fine settimana, ciclo diurno,
dispersione dell'ensemble che cresce con l'anticipo e piccoli cambi tra una corsa e l'altra.
Dopo ogni corsa chiama citta.build(), così si accumula anche lo storico delle previsioni.

    python tests/fake_campioni.py /tmp/pub 2026111206     # ultima corsa simulata
"""
import datetime as dt
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from meteo import citta, luoghi, points  # noqa: E402

UTC = dt.timezone.utc
PUB = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pub"
LAST = dt.datetime.strptime(sys.argv[2] if len(sys.argv) > 2 else "2026111206", "%Y%m%d%H").replace(tzinfo=UTC)
RUNS = int(sys.argv[3]) if len(sys.argv) > 3 else 12  # quante corse simulare (3 giorni)
DET = {"gfs": 0.25, "ecmwf": 0.0, "aifs": -0.2, "icon-eu": 0.15}
T0 = LAST - dt.timedelta(hours=6 * (RUNS - 1))


def fake_alt(p):
    """Altitudini plausibili: le città di montagna note, il resto in pianura o collina."""
    known = {"potenza": 819, "l-aquila": 714, "enna": 931, "campobasso": 701, "aosta": 583, "cuneo": 534,
             "nuoro": 549, "isernia": 423, "rieti": 405, "belluno": 389, "avellino": 348, "sondrio": 307,
             "bolzano": 262, "trento": 194, "ostuni": 218, "perugia": 493, "siena": 322, "urbino": 485,
             "lanusei": 595, "tempio-pausania": 566, "caltanissetta": 568, "frosinone": 291, "teramo": 265}
    return known.get(p["id"], int(abs(math.sin(p["lat"] * 7 + p["lon"] * 3)) * 120))


def front(t_h, lon, lat, center_h, speed=1.2, width=10.0):
    """Intensità (0..1) di una perturbazione che entra da ovest: passa sul luogo verso center_h."""
    arrive = center_h + (lon - 12.0) / speed * 3.0 + (lat - 42.0) * 0.8
    return math.exp(-((t_h - arrive) / width) ** 2)


def truth(p, t, shift=0.0, amp=1.0, second=0.5, tbias=0.0):
    """Tempo "vero" (o di un membro) in un luogo e istante: temperatura, pioggia 6 h, nubi, vento..."""
    h = (t - T0).total_seconds() / 3600.0
    hod = t.hour
    lat, lon, alt = p["lat"], p["lon"], p["alt"]
    f1 = front(h, lon, lat, 60 + shift)
    f2 = front(h, lon, lat, 165 + 3 * shift, width=14) * second
    wet = amp * (f1 + f2)
    base = 17.5 - 0.65 * (lat - 38) - 0.0065 * alt - 5.0 * front(h, lon, lat, 75 + shift, width=30) + tbias
    diurnal = 4.2 * math.sin((hod - 9) / 24 * 2 * math.pi) * (1 - 0.6 * min(wet, 1))
    t2m = base + diurnal
    tp6 = max(0.0, 9.0 * wet - 0.6) * (1.3 if lon > 14 else 1.0)
    tcc = min(100.0, 15 + 85 * min(1.0, 1.4 * wet + 0.25 * front(h, lon, lat, 50 + shift, width=25)))
    pre = front(h, lon, lat, 48 + shift, width=14)
    post = front(h, lon, lat, 80 + shift, width=16)
    u = -2.0 * pre + 6.0 * post   # da sud-est prima, da nord-ovest dopo
    v = 6.0 * pre - 5.0 * post
    fzl = max(0.0, 2400 - 1500 * front(h, lon, lat, 78 + shift, width=26) + 30 * tbias * 10)
    return dict(t2m=t2m, tp6=tp6, tcc=tcc, u10=u, v10=v, gust=math.hypot(u, v) * 1.7 + 3,
                cape=400 * wet if lat < 41.5 else 80 * wet, fzl=fzl, t850=t2m - 8, mslp=1015 - 12 * wet,
                snow=max(0.0, (alt - fzl + 300) / 40) * min(1, wet * 3) if alt > fzl - 300 else 0.0)


def write_run(run, places):
    ids = [p["id"] for p in places]
    rng = np.random.default_rng(int(run.timestamp()) // 3600)
    drift = np.random.default_rng(7)  # errore che cambia piano piano da una corsa all'altra
    k = int((run - T0).total_seconds() // 21600)
    walk = np.cumsum(drift.normal(0, 1.0, 200))[k]
    for sid, bias in DET.items():
        last = 120 if sid == "icon-eu" else 144 if (sid == "ecmwf" and run.hour in (6, 18)) else 192 if sid == "gfs" else 240
        hs = list(range(0, last + 1, 6))
        valids = [run + dt.timedelta(hours=x) for x in hs]
        series = {n: np.full((len(places), len(hs)), np.nan, np.float32) for n in points.PLACE_VARS}
        for i, p in enumerate(places):
            for j, (hh, t) in enumerate(zip(hs, valids)):
                lead = hh / 24.0
                sh = (walk * 2.5 + bias * 8) * lead / 4
                x = truth(p, t, shift=sh, tbias=bias + 0.15 * walk * lead / 3)
                if hh == 0:
                    x["tp6"] = np.nan
                for n, val in x.items():
                    series[n][i, j] = val
                series["tmax6"][i, j] = x["t2m"] + 1.0 if hh else np.nan
                series["tmin6"][i, j] = x["t2m"] - 1.0 if hh else np.nan
        orog = np.array([p["alt"] * 0.6 + 90 for p in places], np.float32)
        for i, p in enumerate(places):  # i modelli vedono il luogo più in basso: correggi di conseguenza
            series["t2m"][i] -= 0.0065 * (orog[i] - p["alt"])
            series["tmax6"][i] -= 0.0065 * (orog[i] - p["alt"])
            series["tmin6"][i] -= 0.0065 * (orog[i] - p["alt"])
        if sid == "aifs":
            for n in ("gust", "cape", "snow", "tmax6", "tmin6"):
                series.pop(n)
        points.write_samples(PUB, sid, run.strftime("%Y-%m-%dT%H:%M:%SZ"), ids, hs,
                             [v.strftime("%Y-%m-%dT%H:%M:%SZ") for v in valids], series, orog)
    for sid, nm, every in (("gefs", 31, 6), ("ecmwf-ens", 50, 12)):
        er = run.replace(hour=(run.hour // every) * every)
        hs = list(range(0, 241, 6))
        valids = [er + dt.timedelta(hours=x) for x in hs]
        series = {n: np.full((len(places), nm, len(hs)), np.nan, np.float32) for n in ("t2m", "tp6")}
        shifts = rng.normal(0, 1, nm)
        amps = np.clip(rng.normal(1, 0.35, nm), 0, 2)
        seconds = rng.uniform(0, 1.2, nm)
        tb = rng.normal(0, 1, nm)
        for i, p in enumerate(places):
            for j, (hh, t) in enumerate(zip(hs, valids)):
                lead = hh / 24.0
                for m in range(nm):
                    x = truth(p, t, shift=shifts[m] * (2 + 4 * lead), amp=amps[m] if lead > 1 else 1.0,
                              second=seconds[m], tbias=tb[m] * (0.3 + 0.45 * lead) - 0.0065 * 200)
                    series["t2m"][i, m, j] = x["t2m"]
                    series["tp6"][i, m, j] = np.nan if hh == 0 else x["tp6"]
        points.write_samples(PUB, sid, er.strftime("%Y-%m-%dT%H:%M:%SZ"), ids, hs,
                             [v.strftime("%Y-%m-%dT%H:%M:%SZ") for v in valids], series)


def main():
    places = luoghi.active()
    for p in places:
        p["alt"] = fake_alt(p)
    run = T0
    while run <= LAST:
        print("corsa simulata", run.strftime("%d/%m %HZ"))
        write_run(run, places)
        citta.build(PUB, now=run + dt.timedelta(hours=5))
        run += dt.timedelta(hours=6)


if __name__ == "__main__":
    main()
