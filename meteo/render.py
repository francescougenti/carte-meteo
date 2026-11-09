"""Disegno delle carte (matplotlib + cartopy).

Ogni processo tiene in memoria una figura per area con coste e confini già disegnati;
per ogni carta aggiunge i campi, salva il PNG e li rimuove. Così il fondo si disegna una volta sola.
"""
import datetime as dt
import io
import os
import traceback

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402
import cartopy.crs as ccrs  # noqa: E402
import shapely.wkb  # noqa: E402
from PIL import Image  # noqa: E402
from scipy.ndimage import map_coordinates, maximum_filter, minimum_filter, uniform_filter  # noqa: E402

from . import config as C  # noqa: E402

PC = ccrs.PlateCarree()
GEO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "geo")
GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.linewidth": 0.6})
HALO_W = [pe.withStroke(linewidth=2.4, foreground="white")]
HALO_D = [pe.withStroke(linewidth=1.6, foreground="#222222")]


def fmt_time(t):
    return f"{GIORNI[t.weekday()]} {t:%d/%m/%Y} {t:%H}Z"


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def make_proj(reg):
    p = reg["proj"]
    if p[0] == "lcc":
        return ccrs.LambertConformal(central_longitude=p[1], central_latitude=p[2], standard_parallels=p[3])
    return ccrs.NorthPolarStereo(central_longitude=p[1])


def load_geom(region, layer):
    path = os.path.join(GEO_DIR, f"{region}_{layer}.wkb")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        g = shapely.wkb.loads(f.read())
    return list(getattr(g, "geoms", [g]))


_COLORS = {}


def cmap_norm(chart):
    """Oggetti nuovi a ogni carta: se condivisi, le barre dei colori precedenti reagirebbero ai cambi."""
    levels, ext = chart["levels"], chart["extend"]
    n = len(levels) - 1 + (ext in ("both", "min")) + (ext in ("both", "max"))
    if chart["id"] not in _COLORS:
        _COLORS[chart["id"]] = C.colors_for(chart["pal"], n)
    return ListedColormap(_COLORS[chart["id"]]), BoundaryNorm(levels, ncolors=n, extend=ext)


def safe_remove(a):
    try:
        a.remove()
    except Exception:
        pass


class Canvas:
    """Figura di un'area con fondo (terre, mari, coste, confini) già disegnato."""

    def __init__(self, reg, lats, lons):
        self.reg = reg
        w, h = reg["figsize"]
        self.fig = plt.figure(figsize=(w, h), dpi=C.DPI, facecolor="white")
        self.proj = make_proj(reg)
        ax = self.ax = self.fig.add_axes(C.MAP_RECT, projection=self.proj)
        if reg["extent"]:
            ax.set_extent(reg["extent"], crs=PC)
            x0, x1 = ax.get_xlim()
            y0, y1 = ax.get_ylim()
        else:  # stereografica polare: quadrato centrato sul polo
            _, y = self.proj.transform_point(reg["proj"][1], reg["proj"][2], PC)
            rr = abs(y)
            x0, x1, y0, y1 = -rr, rr, -rr, rr
        # allarga la vista per riempire esattamente il riquadro della mappa
        target = (w * C.MAP_RECT[2]) / (h * C.MAP_RECT[3])
        cx, cy, dx, dy = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
        if dx / dy < target:
            dx = dy * target
        else:
            dy = dx / target
        self.lim = (cx - dx / 2, cx + dx / 2, cy - dy / 2, cy + dy / 2)
        ax.set_xlim(*self.lim[:2])
        ax.set_ylim(*self.lim[2:])
        ax.set_facecolor(C.SEA)
        ax.spines["geo"].set_linewidth(0.8)

        rid = reg["id"]
        land = load_geom(rid, "land")
        if land:
            ax.add_geometries(land, PC, facecolor=C.LAND, edgecolor="none", zorder=0)
        lakes = load_geom(rid, "lakes")
        if lakes:
            ax.add_geometries(lakes, PC, facecolor=C.LAKE, edgecolor="none", zorder=0.5)
            ax.add_geometries(lakes, PC, facecolor="none", edgecolor="#1a1a1a", linewidth=0.3, zorder=5)
        admin1 = load_geom(rid, "admin1")
        if admin1:
            ax.add_geometries(admin1, PC, facecolor="none", edgecolor="#3a3a3a", linewidth=0.3,
                              alpha=0.8, zorder=5)
        borders = load_geom(rid, "borders")
        if borders:
            ax.add_geometries(borders, PC, facecolor="none", edgecolor="#1a1a1a", linewidth=0.5, zorder=5)
        coast = load_geom(rid, "coast")
        if coast:
            ax.add_geometries(coast, PC, facecolor="none", edgecolor="#111111", linewidth=0.65, zorder=5)
        g = reg["grid"]
        ax.gridlines(crs=PC, draw_labels=False, linewidth=0.35, color="#000000", alpha=0.28,
                     linestyle=(0, (2, 3)), xlocs=np.arange(-180, 181, g), ylocs=np.arange(-80, 81, g),
                     zorder=4)

        self.cax = self.fig.add_axes(C.CBAR_RECT)
        top = C.MAP_RECT[1] + C.MAP_RECT[3]
        f = self.fig
        self.t_title = f.text(0.012, top + 0.040, "", fontsize=11.5, fontweight="bold", va="bottom")
        self.t_sub = f.text(0.012, top + 0.010, "", fontsize=9, va="bottom", color="#333333")
        self.t_valid = f.text(0.988, top + 0.040, "", fontsize=11, fontweight="bold", va="bottom", ha="right")
        self.t_run = f.text(0.988, top + 0.010, "", fontsize=9, va="bottom", ha="right", color="#333333")
        self.t_credit = f.text(0.012, 0.012, "", fontsize=7.5, color="#555555")
        self.t_unit = f.text(0.988, 0.012, "", fontsize=7.5, color="#555555", ha="right")
        self._window(lats, lons)

    def _window(self, lats, lons):
        """Griglia regolare nelle coordinate della proiezione, interpolata dalla griglia lat/lon del modello.

        Disegnare su una griglia regolare già proiettata è più veloce e funziona anche sul polo.
        """
        x0, x1, y0, y1 = self.lim
        nx = C.GRID_NX
        ny = int(round(nx * (y1 - y0) / (x1 - x0)))
        self.xs, self.ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
        XX, YY = np.meshgrid(self.xs, self.ys)
        pts = PC.transform_points(self.proj, XX, YY)
        lon, lat = pts[..., 0], pts[..., 1]
        dlat, dlon = float(lats[1] - lats[0]), float(lons[1] - lons[0])
        ci = np.mod((lon - float(lons[0])) / dlon, len(lons))
        cj = (lat - float(lats[0])) / dlat
        self.coords = np.array([cj, ci])
        self.lon, self.lat = lon, lat
        self.km = (x1 - x0) / nx / 1000.0  # passo della griglia in km
        self.shape = (len(lats), len(lons))
        # punti per le frecce del vento
        k = max(1, nx // self.reg["arrows"])
        sl = (slice(k // 2, None, k), slice(k // 2, None, k))
        self.arrow_sl = sl
        self.arrow_xy = (XX[sl], YY[sl])

    def cut(self, a):
        src = np.concatenate([a, a[:, :1]], axis=1)  # colonna ciclica per i 180°
        return map_coordinates(src, self.coords, order=1, mode="nearest").astype(np.float32)

    def header(self, model, chart, run, valid, lead, step_run):
        self.t_title.set_text(f"{model['short']} – {chart['label']}")
        self.t_sub.set_text(chart["title"])
        self.t_valid.set_text(f"+{lead} h    {fmt_time(valid)}")
        self.t_run.set_text(f"Corsa del {fmt_time(step_run)}")
        self.t_credit.set_text(model["credit"])
        self.t_unit.set_text(self.reg["label"])

    def colorbar(self, chart):
        """Barra dei colori disegnata a mano: quella di matplotlib trattiene in memoria le carte precedenti."""
        cax = self.cax
        cax.cla()
        lv, ext = chart["levels"], chart["extend"]
        cmap, _ = cmap_norm(chart)
        cols = list(cmap.colors)
        nb = len(lv) - 1
        lo = ext in ("both", "min")
        hi = ext in ("both", "max")
        tri = 0.55
        for k in range(nb):
            cax.add_patch(Rectangle((k, 0), 1, 1, facecolor=cols[k + lo], edgecolor="none"))
        outline = [(0, 0)]
        if lo:
            cax.add_patch(Polygon([(0, 0), (-tri, 0.5), (0, 1)], facecolor=cols[0], edgecolor="none"))
            outline = [(0, 0), (-tri, 0.5), (0, 1)]
        else:
            outline = [(0, 0), (0, 1)]
        outline += [(nb, 1)] + ([(nb + tri, 0.5)] if hi else []) + [(nb, 0)]
        if hi:
            cax.add_patch(Polygon([(nb, 0), (nb + tri, 0.5), (nb, 1)], facecolor=cols[-1], edgecolor="none"))
        cax.add_patch(Polygon(outline, closed=True, facecolor="none", edgecolor="#333333", linewidth=0.5))
        cax.set_xlim(-tri - 0.05, nb + tri + 0.05)
        cax.set_ylim(-0.02, 1.02)
        step = -(-len(lv) // 17)
        pos = list(range(0, len(lv), step))
        integer = all(float(lv[i]).is_integer() for i in pos)
        cax.set_xticks(pos)
        cax.set_xticklabels([f"{lv[i]:.0f}" if integer else f"{lv[i]:g}" for i in pos])
        cax.set_yticks([])
        cax.tick_params(axis="x", labelsize=7.5, length=2, pad=1.5)
        for sp in cax.spines.values():
            sp.set_visible(False)
        cax.patch.set_visible(False)
        cax.set_title(chart["unit"], fontsize=7.5, loc="left", pad=1.5, color="#333333")


class Fields(dict):
    """Campi ritagliati sull'area, calcolati al primo uso."""

    def __init__(self, cv, raw):
        super().__init__()
        self.cv, self.raw = cv, raw

    def __missing__(self, k):
        v = self.cv.cut(self.raw[k])
        self[k] = v
        return v


class Ctx:
    def __init__(self, cv, fields):
        self.cv, self.ax, self.d = cv, cv.ax, fields
        self.artists, self.mappable = [], None

    def fill(self, Z, chart):
        cmap, norm = cmap_norm(chart)
        cs = self.ax.contourf(self.cv.xs, self.cv.ys, Z, levels=chart["levels"], cmap=cmap, norm=norm,
                              extend=chart["extend"], transform=self.cv.proj, zorder=1)
        self.artists.append(cs)
        self.mappable = cs

    def lines(self, Z, levels, color="#1b1b1b", lw=0.6, label=True, fmt="%d", fs=6.5, ls="solid",
              z=6, halo=None):
        cs = self.ax.contour(self.cv.xs, self.cv.ys, Z, levels=levels, colors=color, linewidths=lw,
                             linestyles=ls, transform=self.cv.proj, zorder=z)
        self.artists.append(cs)
        if label:
            try:
                txt = self.ax.clabel(cs, inline=True, fontsize=fs, fmt=fmt, inline_spacing=1)
            except Exception:
                txt = []
            for t in txt:
                t.set_zorder(z + 1)
                if halo:
                    t.set_path_effects(halo)
            self.artists.extend(txt)

    def isobars(self, color="#1b1b1b", lw=0.6, centers=False, halo=None, label=True):
        step = self.cv.reg["isobar"]
        self.lines(self.d["mslp"], np.arange(920, 1080, step), color=color, lw=lw, halo=halo, label=label)
        if centers:
            self.centers(self.d["mslp"])

    def centers(self, P):
        """Lettere A (alta pressione) e B (bassa pressione) sui massimi e minimi locali."""
        n = max(5, int(self.cv.reg["centers"] / self.cv.km))
        good = np.isfinite(P)
        if not good.any():
            return
        Pf = np.where(good, P, np.nanmean(P))
        mn, mx = minimum_filter(Pf, size=n, mode="nearest"), maximum_filter(Pf, size=n, mode="nearest")
        avg = uniform_filter(Pf, size=n, mode="nearest")
        x0, x1, y0, y1 = self.cv.lim
        ix, iy = (x1 - x0) * 0.025, (y1 - y0) * 0.03
        placed = []
        for mask, col, letter in (((Pf == mn) & (Pf < 1013) & (avg - Pf > 1.0), "#c8102e", "B"),
                                  ((Pf == mx) & (Pf > 1017) & (Pf - avg > 1.0), "#0b4ea2", "A")):
            jj, ii = np.nonzero(mask)
            order = np.argsort(Pf[jj, ii]) if letter == "B" else np.argsort(-Pf[jj, ii])
            for k in order[:40]:
                x, y = self.cv.xs[ii[k]], self.cv.ys[jj[k]]
                if not (x0 + ix < x < x1 - ix and y0 + iy < y < y1 - iy):
                    continue
                if any(abs(x - px) < 3 * ix and abs(y - py) < 3 * iy for px, py in placed):
                    continue
                placed.append((x, y))
                self.artists.append(self.ax.text(x, y, letter, color=col, fontsize=15, fontweight="bold",
                                                 ha="center", va="center", zorder=9, path_effects=HALO_W))
                self.artists.append(self.ax.text(x, y - iy * 0.75, f"{Pf[jj[k], ii[k]]:.0f}", color=col,
                                                 fontsize=7.5, fontweight="bold", ha="center", va="top",
                                                 zorder=9, path_effects=HALO_W))

    def arrows(self, U, V, color="#111111", min_kmh=0.0):
        """Frecce di direzione (lunghezza fissa: l'intensità la danno i colori)."""
        sl = self.cv.arrow_sl
        u, v = U[sl].astype(np.float64), V[sl].astype(np.float64)
        if min_kmh:
            weak = np.hypot(u, v) * 3.6 < min_kmh
            u, v = np.where(weak, np.nan, u), np.where(weak, np.nan, v)
        lon, lat = self.cv.lon[sl], self.cv.lat[sl]
        up, vp = self.cv.proj.transform_vectors(PC, lon, lat, u, v)
        sp = np.hypot(up, vp)
        sp = np.where(sp < 0.5, np.nan, sp)
        x, y = self.cv.arrow_xy
        q = self.ax.quiver(x, y, up / sp, vp / sp, transform=self.cv.proj, color=color, scale_units="inches",
                           scale=5.2, width=0.0016, headwidth=3.6, headlength=4.0, headaxislength=3.6,
                           pivot="middle", zorder=7)
        self.artists.append(q)

    def clear(self):
        for a in self.artists:
            safe_remove(a)
        self.artists = []


# --------------------------------------------------------------------------------------
# Le carte
# --------------------------------------------------------------------------------------
def theta_e(t_c, rh, p=850.0):
    """Temperatura potenziale equivalente (Bolton 1980), in °C."""
    T = t_c + 273.15
    rh = np.clip(rh, 1.0, 100.0)
    es = 6.112 * np.exp(17.67 * t_c / (t_c + 243.5))
    e = rh / 100.0 * es
    r = 622.0 * e / (p - e)  # g/kg
    td = 243.5 * np.log(e / 6.112) / (17.67 - np.log(e / 6.112)) + 273.15
    tl = 1.0 / (1.0 / (td - 56.0) + np.log(T / td) / 800.0) + 56.0
    th = T * (1000.0 / p) ** (0.2854 * (1 - 0.00028 * r)) * np.exp((3.376 / tl - 0.00254) * r * (1 + 0.00081 * r))
    return th - 273.15


def cv_big(x):
    return x.cv.reg["id"] in ("emisfero_nord",)


def draw(cid, x, ch):
    d = x.d
    if cid == "z500":
        x.fill(d["z500"], ch)
        x.isobars(color="white", lw=0.8, centers=True, halo=HALO_D)
    elif cid == "mslp":
        x.fill(d["z500"] - d["z1000"], ch)
        x.isobars(color="#111111", lw=0.85, centers=True, halo=HALO_W)
    elif cid == "thetae850":
        x.fill(theta_e(d["t850"], d["rh850"]), ch)
        x.isobars(color="#1b1b1b", lw=0.5)
    elif cid == "rh700":
        x.fill(d["rh700"], ch)
        x.lines(d["z500"], np.arange(460, 610, 4), color="#1b1b1b", lw=0.6, halo=HALO_W)
    elif cid == "t850":
        x.fill(d["t850"], ch)
        x.isobars(color="#1b1b1b", lw=0.55, halo=HALO_W)
    elif cid == "t500":
        x.fill(d["t500"], ch)
        x.lines(d["z500"], np.arange(460, 610, 4), color="#1b1b1b", lw=0.6, halo=HALO_W)
    elif cid == "t2m":
        x.fill(d["t2m"], ch)
        x.lines(d["t2m"], [0], color="#1b1b1b", lw=0.8, ls="dashed", label=False)
    elif cid == "prec6":
        x.fill(d["tp6"], ch)
        x.isobars(color="#2b2b2b", lw=0.55, centers=True, halo=HALO_W)
    elif cid == "preccum":
        x.fill(d["tpcum"], ch)
    elif cid == "pwat":
        x.fill(d["pwat"], ch)
        x.isobars(color="#1b1b1b", lw=0.5, halo=HALO_W)
    elif cid == "tcc":
        x.fill(d["tcc"], ch)
        x.isobars(color="#0b3d91", lw=0.55, centers=True, halo=HALO_W)
    elif cid == "wind10":
        x.fill(np.hypot(d["u10"], d["v10"]) * 3.6, ch)
        x.isobars(color="#2b2b2b", lw=0.45, halo=HALO_W)
        x.arrows(d["u10"], d["v10"])
    elif cid == "gust":
        x.fill(d["gust"] * 3.6, ch)
        x.isobars(color="#2b2b2b", lw=0.45, halo=HALO_W)
    elif cid == "jet250":
        x.fill(np.hypot(d["u250"], d["v250"]) * 3.6, ch)
        x.lines(d["z250"], np.arange(880, 1140, 12 if cv_big(x) else 8), color="#1b1b1b", lw=0.55, halo=HALO_W)
        x.arrows(d["u250"], d["v250"], min_kmh=90)
    elif cid == "cape":
        x.fill(d["cape"], ch)
        x.isobars(color="#2b2b2b", lw=0.45, halo=HALO_W)
    else:
        raise KeyError(cid)


def save_png(fig, path):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=C.DPI, facecolor="white")
    buf.seek(0)
    im = Image.open(buf).convert("RGB").quantize(colors=256, method=Image.Quantize.FASTOCTREE,
                                                 dither=Image.Dither.NONE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, optimize=True)


_CANVAS = {}


def render_step(job):
    """Disegna tutte le carte di una scadenza. Restituisce (h, carte prodotte in tutte le aree)."""
    data = np.load(job["npz"])
    lats, lons = data["_lats"], data["_lons"]
    raw = {k: data[k] for k in data.files if not k.startswith("_")}
    run = parse_iso(job["run"])
    h = job["h"]
    valid = run + dt.timedelta(hours=h)
    produced = {}
    for rid in job["regions"]:
        reg = C.REGION_BY_ID[rid]
        key = (rid, lats.shape[0], lons.shape[0])
        cv = _CANVAS.get(key)
        if cv is None:
            cv = _CANVAS[key] = Canvas(reg, lats, lons)
        fields = Fields(cv, raw)
        for cid in job["charts"]:
            ch = C.CHART_BY_ID[cid]
            if h == 0 and not ch.get("step0", True):
                continue
            if any(n not in raw or not np.isfinite(raw[n]).any() for n in ch["needs"]):
                continue
            x = Ctx(cv, fields)
            try:
                draw(cid, x, ch)
                cv.header(job["model"], ch, run, valid, h, run)
                cv.colorbar(ch)
                save_png(cv.fig, os.path.join(job["out"], rid, cid, f"{h:03d}.png"))
                produced.setdefault(cid, set()).add(rid)
            except Exception:
                print(f"  ! errore nel disegno {job['model']['id']} {rid} {cid} +{h}h", flush=True)
                traceback.print_exc()
            finally:
                x.clear()
    full = sorted(c for c, rs in produced.items() if len(rs) == len(job["regions"]))
    return h, full
