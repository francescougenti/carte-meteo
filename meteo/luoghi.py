"""Luoghi della previsione "La tua città".

- I capoluoghi di provincia e le località dei meteogrammi (per esempio Ostuni) hanno una previsione calcolata
  esattamente nel loro punto (data/citta/<id>.json).
- Tutti gli altri comuni sono raggruppati in zone di 0,25° (circa 25 km, la maglia dei modelli globali):
  la previsione si calcola una volta per zona, nel baricentro dei suoi comuni e alla loro quota mediana
  (data/celle/<id>.json); il sito la adatta poi all'altitudine di ogni comune.

L'elenco completo dei comuni è in assets/luoghi/comuni.json (vedi tools/prepara_luoghi.py).
"""
import functools
import json
import os
import re
import statistics
import unicodedata

from . import config as C

PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "luoghi", "comuni.json")


def slug(s):
    s = unicodedata.normalize("NFKD", s.split("/")[0]).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


@functools.lru_cache(maxsize=1)
def all_places():
    """Tutti i comuni, con un identificativo leggibile e unico (nome, più la sigla se il nome si ripete)."""
    with open(PATH, encoding="utf-8") as f:
        data = json.load(f)
    F = {k: i for i, k in enumerate(data["campi"])}
    rows = data["comuni"]
    seen = {}
    for r in rows:
        seen[slug(r[F["nome"]])] = seen.get(slug(r[F["nome"]]), 0) + 1
    out = []
    for r in rows:
        s = slug(r[F["nome"]])
        prov, reg = data["province"].get(r[F["sigla"]], ["", ""])
        out.append(dict(
            id=s if seen[s] == 1 else f"{s}-{r[F['sigla']].lower()}", istat=r[F["istat"]], name=r[F["nome"]],
            alt_name=r[F["altro"]] or None, sigla=r[F["sigla"]], provincia=prov, regione=reg,
            capoluogo=bool(r[F["capoluogo"]]), lat=r[F["lat"]], lon=r[F["lon"]], alt=r[F["alt"]]))
    return out


@functools.lru_cache(maxsize=1)
def active():
    """Luoghi con la previsione per città, in ordine stabile (codice ISTAT)."""
    places = all_places()
    by_id = {p["id"]: p for p in places}
    keep = {p["id"] for p in places if p["capoluogo"]}
    keep |= {c["id"] for c in C.CITIES if c["id"] in by_id}
    return [p for p in places if p["id"] in keep]


CELL = 0.25  # gradi


@functools.lru_cache(maxsize=1)
def cells():
    """Zone che raggruppano i comuni non calcolati punto per punto."""
    act = {p["id"] for p in active()}
    groups = {}
    for p in all_places():
        if p["id"] not in act:
            groups.setdefault((round(p["lat"] / CELL), round(p["lon"] / CELL)), []).append(p)
    out = []
    for (i, j), ps in sorted(groups.items()):
        alts = [p["alt"] for p in ps if p["alt"] is not None]
        out.append(dict(id=f"z{round(i * CELL * 100):04d}-{round(j * CELL * 100):04d}",
                        lat=round(sum(p["lat"] for p in ps) / len(ps), 4),
                        lon=round(sum(p["lon"] for p in ps) / len(ps), 4),
                        alt=int(statistics.median(alts)) if alts else None,
                        comuni=[p["id"] for p in ps]))
    return out


def sample_points():
    """Tutti i punti in cui si leggono i modelli: luoghi attivi e zone."""
    return active() + cells()


def file_of():
    """Comune -> file della sua previsione ("citta/<id>" oppure "celle/<id>")."""
    out = {p["id"]: f"citta/{p['id']}" for p in active()}
    for c in cells():
        for cid in c["comuni"]:
            out[cid] = f"celle/{c['id']}"
    return out
