"""Prepara assets/luoghi/comuni.json: tutti i comuni italiani con provincia, coordinate e altitudine.

Fonte dei comuni: database dei comuni italiani di Garda Informatica (dati ISTAT, licenza MIT),
distribuito nel pacchetto npm "italian-cap-comuni-province":

    npm pack italian-cap-comuni-province && tar xzf italian-cap-comuni-province-*.tgz
    python tools/prepara_luoghi.py package/dist/gi_comuni_cap-*.json

L'altitudine si aggiunge dopo, dal modello digitale del terreno (tools/altitudini.py), e resta
nel file: lo script la conserva se il file esiste già.
"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "luoghi", "comuni.json")
FIELDS = ["istat", "nome", "altro", "sigla", "capoluogo", "lat", "lon", "alt"]


def main(src):
    rows = json.load(open(src, encoding="utf-8"))
    old = {}
    if os.path.exists(OUT):
        prev = json.load(open(OUT, encoding="utf-8"))
        i_alt = prev["campi"].index("alt")
        old = {r[0]: r[i_alt] for r in prev["comuni"]}
    comuni, province = {}, {}
    for r in rows:
        code = r["codice_istat"]
        if code in comuni:
            continue
        altro = r["denominazione_ita_altra"]
        altro = "" if altro == r["denominazione_ita"] else altro
        comuni[code] = [code, r["denominazione_ita"], altro, r["sigla_provincia"],
                        1 if r["flag_capoluogo"] == "SI" else 0,
                        round(float(r["lat"]), 5), round(float(r["lon"]), 5), old.get(code)]
        province.setdefault(r["sigla_provincia"], [r["denominazione_provincia"], r["denominazione_regione"]])
    data = {
        "fonte": "Comuni italiani: Garda Informatica, database dei comuni italiani da dati ISTAT (licenza MIT). "
                 "Altitudine: modello digitale del terreno AWS Terrain Tiles (SRTM e altre fonti).",
        "campi": FIELDS,
        "province": dict(sorted(province.items())),
        "comuni": sorted(comuni.values(), key=lambda c: c[0]),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    caps = sum(c[4] for c in comuni.values())
    print(f"{len(comuni)} comuni, {caps} capoluoghi, {len(province)} province -> {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main(sys.argv[1])
