"""Prepara i contorni geografici (coste, terre, confini) ritagliati per ogni area.

Si lancia una sola volta: i file prodotti in assets/geo sono già nel repository.
Sorgente: Natural Earth (dominio pubblico), https://github.com/nvkelso/natural-earth-vector

    python tools/prepara_geo.py /percorso/cartella_shapefile_natural_earth
"""
import os
import sys

import shapefile
import shapely.wkb
from shapely.geometry import box, shape
from shapely.ops import unary_union

SRC = sys.argv[1] if len(sys.argv) > 1 else "ne_raw"
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "geo")
os.makedirs(OUT, exist_ok=True)

# riquadri di ritaglio (lon min, lat min, lon max, lat max), larghi rispetto all'area visibile
BOXES = {
    "italia": (-6, 27, 36, 56),
    "europa_ovest": (-45, 18, 60, 75),
    "europa": (-80, 8, 100, 89),
    "emisfero_nord": (-180, -25, 180, 90),
    "nord_america": (-180, -5, -15, 89),
}
RES = {"italia": "10m"}


def read(name, filt=None):
    r = shapefile.Reader(os.path.join(SRC, name))
    geoms = []
    for sr in r.iterShapeRecords():
        if filt and not filt(sr.record.as_dict()):
            continue
        if sr.shape.shapeType == 0 or not sr.shape.points:
            continue
        geoms.append(shape(sr.shape.__geo_interface__))
    return geoms


def clip(geoms, bbox, tol):
    b = box(*bbox)
    out = []
    for g in geoms:
        if not g.is_valid:
            g = g.buffer(0)
        if not g.intersects(b):
            continue
        c = g.intersection(b)
        if tol:
            c = c.simplify(tol, preserve_topology=True)
        if not c.is_empty:
            out.append(c)
    return unary_union(out) if out else None


def save(region, layer, geom):
    if geom is None or geom.is_empty:
        return
    path = os.path.join(OUT, f"{region}_{layer}.wkb")
    with open(path, "wb") as f:
        f.write(shapely.wkb.dumps(geom))
    print(f"{path}: {os.path.getsize(path) / 1024:.0f} KB")


cache = {}


def layer(res, name, filt=None, key=None):
    k = (res, name, key)
    if k not in cache:
        cache[k] = read(f"ne_{res}_{name}", filt)
    return cache[k]


for region, bbox in BOXES.items():
    res = RES.get(region, "50m")
    tol = 0.0 if res == "10m" else 0.02
    save(region, "land", clip(layer(res, "land"), bbox, tol))
    save(region, "coast", clip(layer(res, "coastline"), bbox, tol))
    save(region, "borders", clip(layer(res, "admin_0_boundary_lines_land"), bbox, tol))
    if region == "italia":
        regioni = layer(
            "10m",
            "admin_1_states_provinces_lines",
            lambda r: r["ADM0_NAME"] == "Italy" and r["FEATURECLA"] == "Admin-1 region boundary",
            key="it",
        )
        save(region, "admin1", clip(regioni, bbox, 0.0))
    if region == "nord_america":
        stati = layer(
            "50m",
            "admin_1_states_provinces_lines",
            lambda r: r["ADM0_NAME"] in ("United States of America", "Canada", "Mexico"),
            key="na",
        )
        save(region, "admin1", clip(stati, bbox, tol))
    if region in ("europa_ovest", "europa", "nord_america", "emisfero_nord"):
        save(region, "lakes", clip(layer("50m", "lakes"), bbox, tol))
