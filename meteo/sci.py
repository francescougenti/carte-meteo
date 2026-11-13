"""Comprensori sciistici italiani: aperti o chiusi, impianti e piste aperte, neve a valle e in quota.

Fonte: LiftRadar (liftradar.eu), che raccoglie due volte al giorno i bollettini dei comprensori e degli enti
turistici (Dolomiti Superski tramite l'Open Data Hub dell'Alto Adige, Valle d'Aosta, Trentino, Bormio,
Livigno, Friuli Venezia Giulia...) e il pericolo valanghe AINEVA / Euregio.

Risultato: data/sci.json, con il comune più vicino a ogni comprensorio (per la previsione).
"""
import datetime as dt
import json
import os
import urllib.request

import numpy as np

from . import citta, luoghi

URLS = [os.environ.get("METEO_SCI_URL") or "https://raw.githubusercontent.com/mironiasty/liftradar/data/json/index.json",
        "https://liftradar.eu/json/index.json"]
UA = "Ventaglio/1.0 (sito meteo personale; https://francescougenti.github.io/carte-meteo/)"
STATUS = {"open": "aperto", "closed": "chiuso", "no_report": "senza bollettino"}


def fetch():
    err = None
    for u in URLS:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:  # si prova la copia successiva
            err = e
    raise err


def nearest_comune(lat, lon, places, xyz):
    la, lo = np.radians(lat), np.radians(lon)
    p = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    k = int(np.argmax(xyz @ p))
    d = 6371.0 * float(np.arccos(np.clip(xyz[k] @ p, -1, 1)))
    return places[k], d


def update(public, log=print):
    data = fetch()
    resorts = [r for r in data.get("resorts", []) if r.get("country") == "it" and r.get("location")]
    if not resorts:
        log("Piste da sci: nessun comprensorio italiano nella fonte")
        return
    places = luoghi.all_places()
    la, lo = np.radians([p["lat"] for p in places]), np.radians([p["lon"] for p in places])
    xyz = np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    out = []
    for r in resorts:
        loc = r["location"]
        c, d = nearest_comune(loc["lat"], loc["lon"], places, xyz)
        lifts, slopes, snow, av = r.get("lifts") or {}, r.get("slopes") or {}, r.get("snow") or {}, r.get("avalanche") or {}
        out.append(dict(
            id=r["id"], nome=r["name"], regione=r.get("region"), lat=round(loc["lat"], 4), lon=round(loc["lon"], 4),
            stato=r.get("status"), controllato=r.get("checked_at"),
            impianti=[lifts.get("open"), lifts.get("total")] if lifts else None,
            piste=[slopes.get("open"), slopes.get("total")] if slopes.get("total") is not None else None,
            km=[slopes.get("open_km"), slopes.get("total_km")] if slopes.get("total_km") is not None else None,
            neve=[snow.get("valley_cm"), snow.get("mountain_cm"), snow.get("fresh_cm")],
            valanghe=av.get("danger_level"),
            comune=c["id"], comune_nome=c["name"], comune_km=round(d, 1)))
    out.sort(key=lambda x: (x["regione"] or "", x["nome"]))
    n_open = sum(x["stato"] == "open" for x in out)
    lifts = [x["impianti"] for x in out if x["impianti"] and x["impianti"][0] is not None]
    kms = [x["km"] for x in out if x["km"] and x["km"][0] is not None and x["km"][1] is not None]
    summary = dict(comprensori=len(out), aperti=n_open, impianti=[sum(a for a, _ in lifts), sum(b for _, b in lifts)],
                   km=[round(sum(a for a, _ in kms)), round(sum(b for _, b in kms))])
    citta.write_json(os.path.join(public, "data", "sci.json"), dict(
        formato=1, aggiornato=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        fonte_aggiornata=data.get("generated_at"), totale=summary, comprensori=out,
        fonte="LiftRadar (liftradar.eu), dai bollettini dei comprensori e degli enti turistici; pericolo valanghe AINEVA ed Euregio",
        link="https://liftradar.eu"))
    log(f"Piste da sci: {len(out)} comprensori italiani, {n_open} aperti")
