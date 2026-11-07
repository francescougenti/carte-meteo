"""Controllo veloce (solo libreria standard): c'è una corsa GFS o ECMWF più nuova di quella pubblicata?

    python3 -m meteo.check --manifest-url https://utente.github.io/carte-meteo/data/manifest.json
"""
import argparse
import json
import os
import sys
import time

from .sources import MODELS, http_get, log


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest-url", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    published = {}
    if a.manifest_url:
        try:
            sep = "&" if "?" in a.manifest_url else "?"
            published = json.loads(http_get(f"{a.manifest_url}{sep}t={int(time.time())}", tries=2)).get("models", {})
        except Exception as e:
            log(f"Manifest pubblicato non leggibile ({e}): genero tutto")
    need = []
    for mid, model in MODELS.items():
        run = model.latest()
        cur = published.get(mid, {}).get("run")
        if run is None:
            log(f"{model.label}: nessuna corsa completa trovata")
            continue
        log(f"{model.label}: ultima corsa {run.time:%d/%m %H}Z, pubblicata {cur or 'nessuna'}")
        if a.force or run.iso != cur:
            need.append(mid)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"update={'true' if need else 'false'}\nmodels={','.join(need)}\n")
    log("Da aggiornare: " + (", ".join(need) if need else "niente"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
