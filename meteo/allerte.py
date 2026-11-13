"""Allerte meteo-idro della Protezione Civile per ogni comune.

Fonte: bollettino di criticità nazionale, pubblicato ogni giorno di norma entro le 16 nel repository
github.com/pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica (licenza CC BY 4.0).
Per ognuna delle zone di allerta dà il livello (verde, giallo, arancione, rosso) per oggi e domani,
per rischio idraulico, temporali e idrogeologico. Ogni comune viene assegnato alla sua zona dalla posizione.

    data/allerte.json   solo le zone con almeno un'allerta e i comuni che ci cadono
"""
import io
import json
import os
import re
import urllib.request
import zipfile

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from . import citta, luoghi
from .sources import now_utc

RAW = os.environ.get("METEO_ALLERTE_ROOT") or \
    "https://raw.githubusercontent.com/pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica/master/files"
LINK = "https://mappe.protezionecivile.gov.it/it/mappe-rischi/bollettino-di-criticita"
RISKS = (("idraulico", "Per rischio idraulico"), ("temporali", "Per rischio temporali"),
         ("idrogeologico", "Per rischio idrogeologico"))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "carte-meteo/1.0 (allerte)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def level(text):
    t = str(text or "").upper()
    return 3 if "ROSSA" in t else 2 if "ARANCIONE" in t else 1 if "GIALLA" in t else 0


def latest_base():
    """Nome dell'ultimo bollettino (es. 20261113_1434), dall'archivio "latest_all.zip"."""
    names = zipfile.ZipFile(io.BytesIO(get(f"{RAW}/all/latest_all.zip"))).namelist()
    for n in names:
        m = re.match(r"(\d{8}_\d{4})_today\.", os.path.basename(n))
        if m:
            return m.group(1)
    raise RuntimeError("nome del bollettino non trovato")


def levels(props):
    return [level(props.get(label)) for _, label in RISKS]


def update(public, log=print):
    path = os.path.join(public, "data", "allerte.json")
    old = citta.read_json(path)
    base = latest_base()
    if old and old.get("bollettino") == base:
        return old
    today = json.loads(get(f"{RAW}/geojson/{base}_today.json"))
    tomorrow = json.loads(get(f"{RAW}/geojson/{base}_tomorrow.json"))
    try:
        meta = json.loads(get(f"{RAW}/{base}.json"))
    except Exception:
        meta = {}
    tom = {}
    for f in tomorrow.get("features", []):
        tom.setdefault(f["properties"].get("Nome zona"), levels(f["properties"]))
    feats = [f for f in today.get("features", []) if f.get("geometry")]
    geoms = [shape(f["geometry"]) for f in feats]
    tree = STRtree(geoms)
    zones = []
    for f in feats:
        p = f["properties"]
        zones.append(dict(nome=p.get("Nome zona", ""), oggi=levels(p), domani=tom.get(p.get("Nome zona"), [0, 0, 0])))
    comuni = {}
    for c in luoghi.all_places():
        pt = Point(c["lon"], c["lat"])
        hit = [int(i) for i in tree.query(pt, predicate="intersects")]
        if not hit:  # sul bordo o sulla costa: la zona più vicina, se è a meno di ~5 km
            i = int(tree.nearest(pt))
            if geoms[i].distance(pt) < 0.05:
                hit = [i]
        if not hit:
            continue
        i = max(hit, key=lambda k: max(zones[k]["oggi"] + zones[k]["domani"]))
        if max(zones[i]["oggi"] + zones[i]["domani"]) > 0:
            comuni[c["id"]] = i
    used = sorted(set(comuni.values()))
    remap = {old_i: new_i for new_i, old_i in enumerate(used)}
    day = f"{base[:4]}-{base[4:6]}-{base[6:8]}"
    nxt = citta.dt.date.fromisoformat(day) + citta.dt.timedelta(days=1)
    data = dict(formato=1, bollettino=base, nome=meta.get("name") or f"Bollettino del {day}", emesso=meta.get("date"),
                oggi=day, domani=nxt.isoformat(), link=LINK, rischi=[r for r, _ in RISKS],
                fonte="Dipartimento della Protezione Civile, bollettino di criticità nazionale (CC BY 4.0)",
                aggiornato=now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
                zone=[zones[i] for i in used], comuni={cid: remap[i] for cid, i in sorted(comuni.items())})
    citta.write_json(path, data)
    log(f"Allerte: {data['nome']}, {len(used)} zone con allerta, {len(comuni)} comuni")
    return data
