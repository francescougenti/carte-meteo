"""Aggiunge l'altitudine (m s.l.m.) ai comuni di assets/luoghi/comuni.json che non ce l'hanno.

Usa le AWS Terrain Tiles (registry.opendata.aws/terrain-tiles), formato Terrarium:
quota = R*256 + G + B/256 - 32768. Livello di zoom 11: un pixel misura circa 55 m in Italia.

    python tools/altitudini.py            # tutti i comuni senza altitudine
    python tools/altitudini.py --capoluoghi
"""
import argparse
import io
import json
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "luoghi", "comuni.json")
TILE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
Z = 11


def tile_xy(lat, lon, z=Z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    la = math.radians(lat)
    y = (1.0 - math.log(math.tan(la) + 1.0 / math.cos(la)) / math.pi) / 2.0 * n
    return x, y


def get_tile(key):
    x, y = key
    for k in range(4):
        try:
            with urllib.request.urlopen(TILE.format(z=Z, x=x, y=y), timeout=60) as r:
                rgb = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB"), dtype=np.float64)
            return key, rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
        except Exception as e:
            err = e
            time.sleep(2 * (k + 1))
    print(f"  ! tessera {key} non scaricata: {err}", file=sys.stderr)
    return key, None


def sample(h, fx, fy):
    """Interpolazione bilineare tra i centri dei pixel di una tessera 256x256."""
    px, py = fx * 256 - 0.5, fy * 256 - 0.5
    x0, y0 = int(np.clip(math.floor(px), 0, 254)), int(np.clip(math.floor(py), 0, 254))
    ax, ay = float(np.clip(px - x0, 0, 1)), float(np.clip(py - y0, 0, 1))
    v = (h[y0, x0] * (1 - ax) * (1 - ay) + h[y0, x0 + 1] * ax * (1 - ay)
         + h[y0 + 1, x0] * (1 - ax) * ay + h[y0 + 1, x0 + 1] * ax * ay)
    return max(0, int(round(v)))  # sul mare (comuni costieri) il modello dà valori negativi


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--capoluoghi", action="store_true", help="solo i capoluoghi")
    ap.add_argument("--tutti", action="store_true", help="ricalcola anche quelli che hanno già l'altitudine")
    a = ap.parse_args(argv)
    data = json.load(open(PATH, encoding="utf-8"))
    F = {k: i for i, k in enumerate(data["campi"])}
    todo = [c for c in data["comuni"] if (a.tutti or c[F["alt"]] is None) and (not a.capoluoghi or c[F["capoluogo"]])]
    where = {}
    for c in todo:
        x, y = tile_xy(c[F["lat"]], c[F["lon"]])
        where.setdefault((int(x), int(y)), []).append((c, x % 1, y % 1))
    print(f"{len(todo)} comuni da completare, {len(where)} tessere da scaricare")
    done = 0
    with ThreadPoolExecutor(16) as ex:
        for key, h in ex.map(get_tile, where):
            if h is None:
                continue
            for c, fx, fy in where[key]:
                c[F["alt"]] = sample(h, fx, fy)
                done += 1
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"altitudine aggiunta a {done} comuni")
    return 0 if done == len(todo) else 1


if __name__ == "__main__":
    sys.exit(main())
