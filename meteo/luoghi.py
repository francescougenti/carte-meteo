"""Luoghi della previsione "La tua città".

Fase 1: i capoluoghi di provincia più le località dei meteogrammi (per esempio Ostuni).
L'elenco completo dei comuni è in assets/luoghi/comuni.json (vedi tools/prepara_luoghi.py).
"""
import functools
import json
import os
import re
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
