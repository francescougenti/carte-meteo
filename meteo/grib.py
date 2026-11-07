"""Decodifica dei messaggi GRIB2 in griglie latitudine/longitudine regolari."""
import os
import tempfile

import eccodes
import numpy as np

LAT_MIN = -15.0  # tutte le aree sono nell'emisfero nord: si scarta il resto per risparmiare memoria


def decode(msg, sub=0):
    """Restituisce (lats crescenti, lons crescenti in [-180,180), valori[nlat, nlon])."""
    if sub:
        eccodes.codes_grib_multi_support_on()
        fd, path = tempfile.mkstemp(suffix=".grib2")
        try:
            os.write(fd, msg)
            os.close(fd)
            with open(path, "rb") as f:
                for _ in range(sub):
                    h = eccodes.codes_grib_new_from_file(f)
                    eccodes.codes_release(h)
                h = eccodes.codes_grib_new_from_file(f)
                return _grid(h)
        finally:
            os.unlink(path)
    h = eccodes.codes_new_from_message(msg)
    return _grid(h)


def _grid(h):
    try:
        g = lambda k: eccodes.codes_get(h, k)  # noqa: E731
        ni, nj = g("Ni"), g("Nj")
        lat1, lat2 = g("latitudeOfFirstGridPointInDegrees"), g("latitudeOfLastGridPointInDegrees")
        lon1 = g("longitudeOfFirstGridPointInDegrees")
        dlon = g("iDirectionIncrementInDegrees")
        ineg = g("iScansNegatively")
        vals = eccodes.codes_get_values(h).astype(np.float32)
        if g("bitmapPresent"):
            vals[vals == g("missingValue")] = np.nan
    finally:
        eccodes.codes_release(h)
    vals = vals.reshape(nj, ni)
    lats = np.linspace(lat1, lat2, nj)
    lons = lon1 + (-1 if ineg else 1) * dlon * np.arange(ni)
    lons = ((lons + 180.0) % 360.0) - 180.0
    oi = np.argsort(lons)
    lons, vals = lons[oi], vals[:, oi]
    if lats[0] > lats[-1]:
        lats, vals = lats[::-1], vals[::-1]
    keep = lats >= LAT_MIN
    return lats[keep].astype(np.float32), lons.astype(np.float32), np.ascontiguousarray(vals[keep])
