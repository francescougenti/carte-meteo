"""Configurazione: aree, carte, scale di colore."""
import numpy as np

DPI = 100
MAP_RECT = [0.008, 0.115, 0.984, 0.80]  # x, y, larghezza, altezza (frazione della figura)
CBAR_RECT = [0.10, 0.058, 0.80, 0.022]
GRID_NX = 460  # punti della griglia di disegno in orizzontale

LAND = "#ece6d8"
SEA = "#d6e2ea"
LAKE = "#d6e2ea"

# --------------------------------------------------------------------------------------
# Aree geografiche
# proj: ("lcc", lon0, lat0, (par1, par2)) oppure ("nps", lon0, lat_bordo)
# centers: raggio di ricerca dei centri di alta/bassa pressione (km); arrows: frecce in orizzontale
# --------------------------------------------------------------------------------------
REGIONS = [
    dict(id="italia", label="Italia", proj=("lcc", 12.5, 42.0, (38.0, 46.0)),
         extent=(6.0, 19.5, 35.8, 47.4), figsize=(8.8, 8.7),
         isobar=2, centers=450, grid=5, arrows=22),
    dict(id="europa_ovest", label="Europa occidentale", proj=("lcc", 5.0, 47.0, (40.0, 55.0)),
         extent=(-16.0, 24.0, 34.0, 60.0), figsize=(9.6, 7.9),
         isobar=4, centers=800, grid=10, arrows=26),
    dict(id="europa", label="Europa", proj=("lcc", 10.0, 50.0, (40.0, 60.0)),
         extent=(-30.0, 48.0, 29.0, 72.0), figsize=(9.6, 7.9),
         isobar=4, centers=1000, grid=10, arrows=28),
    dict(id="emisfero_nord", label="Emisfero Nord", proj=("nps", 10.0, 22.0),
         extent=None, figsize=(8.8, 9.0),
         isobar=4, centers=1500, grid=20, arrows=34),
    dict(id="nord_america", label="Nord America", proj=("lcc", -98.0, 45.0, (33.0, 45.0)),
         extent=(-130.0, -62.0, 17.0, 60.0), figsize=(9.6, 7.9),
         isobar=4, centers=1000, grid=10, arrows=28),
]
REGION_BY_ID = {r["id"]: r for r in REGIONS}

# --------------------------------------------------------------------------------------
# Scale di colore (ancore interpolate sul numero di classi necessario)
# --------------------------------------------------------------------------------------
PAL = {
    "temp": ["#2a0845", "#5a1f8a", "#8b55c7", "#3c3fbd", "#2b6fd6", "#3aa0e8", "#8fd6f5",
             "#d4f1ee", "#a9df86", "#56bb4f", "#2f9443", "#e2e45a", "#f6c344", "#f39433",
             "#e85d2a", "#c9282b", "#93152e", "#b23a83", "#e590c4"],
    "geo": ["#3a0b5c", "#5d1f8f", "#3a3fa8", "#2463c9", "#2f95e0", "#46c3e6", "#63d6b3",
            "#9ad37a", "#d8e45e", "#ffe34d", "#ffbe45", "#fb8a3a", "#ec5530", "#c92a2a",
            "#901818", "#5e0d14"],
    "prec": ["#cfe9ff", "#9fd2ff", "#5daef5", "#2f7be0", "#1d9a52", "#62c540", "#c4e23a",
             "#f6e03a", "#f6a92a", "#ee6a24", "#d6262b", "#b0177a", "#7e1fa6", "#4b1585"],
    "wind": ["#eaf6ff", "#c6e6ff", "#97d2fa", "#62bdd8", "#5ec29a", "#93d36b", "#d1e35a",
             "#ffe15a", "#ffb547", "#ff7f3f", "#ec4335", "#c41f5a", "#8f1f8f", "#5a1c8c"],
    "jet": ["#dff1ff", "#a9d8ff", "#6fb6f2", "#4f8fe0", "#5ab87d", "#a8d65a", "#ffe45a",
            "#ffb347", "#ff7043", "#e53935", "#b0176c", "#6a1b9a"],
    "rh": ["#e9f6e2", "#c3e6b4", "#8fcf8a", "#53b16f", "#2b8d6a", "#1f6d86", "#23498f"],
    "cape": ["#fff3b0", "#ffd65e", "#ffad40", "#ff7a2c", "#ef4b2c", "#cc1f2f", "#a3145e",
             "#7b1c8c", "#4b1c8c", "#2b2373"],
    "pwat": ["#f6e7c4", "#e3d6a0", "#bfe0a3", "#7ccaa6", "#46b1c6", "#2f86d1", "#3557b8",
             "#5c3fa6", "#8e2c97", "#c32a7a", "#e8558a"],
    "cloud": ["#f4f6f8", "#dfe4ea", "#c6cdd6", "#aab4c0", "#8f9aa8", "#747f8e", "#5b6574",
              "#444d5a"],
}


def colors_for(pal, n):
    from matplotlib.colors import LinearSegmentedColormap, to_hex
    cm = LinearSegmentedColormap.from_list(pal, PAL[pal])
    return [to_hex(cm(x)) for x in np.linspace(0, 1, n)]


def r(a, b, s):
    return [round(float(v), 3) for v in np.arange(a, b + s / 2, s)]


# --------------------------------------------------------------------------------------
# Carte
# needs: campi richiesti; step0: disponibile anche a +0 h
# --------------------------------------------------------------------------------------
CHARTS = [
    dict(id="z500", group="Pressione", label="Geopotenziale 500 hPa e pressione",
         title="Geopotenziale 500 hPa (dam) e pressione al suolo (hPa)",
         needs=["z500", "mslp"], unit="dam", pal="geo", levels=r(472, 600, 4), extend="both"),
    dict(id="mslp", group="Pressione", label="Pressione al suolo",
         title="Pressione al livello del mare (hPa) e spessore 500/1000 hPa (dam)",
         needs=["mslp", "z500", "z1000"], unit="dam", pal="geo", levels=r(492, 588, 4), extend="both"),
    dict(id="thetae850", group="Temperature", label="Theta-e 850 hPa",
         title="Temperatura potenziale equivalente a 850 hPa (°C) e pressione al suolo (hPa)",
         needs=["t850", "rh850", "mslp"], unit="°C", pal="temp", levels=r(-16, 72, 4), extend="both"),
    dict(id="rh700", group="Precipitazioni e nubi", label="Umidità 700 hPa",
         title="Umidità relativa a 700 hPa (%) e geopotenziale 500 hPa (dam)",
         needs=["rh700", "z500"], unit="%", pal="rh", levels=[50, 60, 70, 80, 90, 95, 100], extend="neither"),
    dict(id="t850", group="Temperature", label="Temperatura 850 hPa",
         title="Temperatura a 850 hPa (°C) e pressione al suolo (hPa)",
         needs=["t850", "mslp"], unit="°C", pal="temp", levels=r(-32, 32, 2), extend="both"),
    dict(id="t500", group="Temperature", label="Temperatura 500 hPa",
         title="Temperatura a 500 hPa (°C) e geopotenziale 500 hPa (dam)",
         needs=["t500", "z500"], unit="°C", pal="temp", levels=r(-48, -4, 2), extend="both"),
    dict(id="t2m", group="Temperature", label="Temperatura a 2 m",
         title="Temperatura a 2 metri dal suolo (°C)",
         needs=["t2m"], unit="°C", pal="temp", levels=r(-30, 44, 2), extend="both"),
    dict(id="prec6", group="Precipitazioni e nubi", label="Precipitazioni 6 ore",
         title="Precipitazioni nelle 6 ore precedenti (mm) e pressione al suolo (hPa)",
         needs=["tp6", "mslp"], unit="mm", pal="prec", step0=False,
         levels=[0.2, 0.5, 1, 2, 4, 6, 10, 15, 20, 30, 40, 60, 80, 100], extend="max"),
    dict(id="preccum", group="Precipitazioni e nubi", label="Precipitazioni cumulate",
         title="Precipitazioni cumulate dall'inizio della corsa (mm)",
         needs=["tpcum"], unit="mm", pal="prec", step0=False,
         levels=[1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 300], extend="max"),
    dict(id="pwat", group="Precipitazioni e nubi", label="Acqua precipitabile",
         title="Acqua precipitabile (mm) e pressione al suolo (hPa)",
         needs=["pwat", "mslp"], unit="mm", pal="pwat", levels=r(5, 60, 5), extend="max"),
    dict(id="tcc", group="Precipitazioni e nubi", label="Nuvolosità totale",
         title="Copertura nuvolosa totale (%) e pressione al suolo (hPa)",
         needs=["tcc", "mslp"], unit="%", pal="cloud", levels=r(20, 100, 10), extend="neither"),
    dict(id="wind10", group="Vento e instabilità", label="Vento a 10 m",
         title="Vento medio a 10 metri (km/h) e pressione al suolo (hPa)",
         needs=["u10", "v10", "mslp"], unit="km/h", pal="wind",
         levels=[10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 100, 120], extend="max"),
    dict(id="gust", group="Vento e instabilità", label="Raffiche",
         title="Raffiche di vento (km/h) e pressione al suolo (hPa)",
         needs=["gust", "mslp"], unit="km/h", pal="wind",
         levels=[30, 40, 50, 60, 70, 80, 90, 100, 120, 140, 160], extend="max"),
    dict(id="jet250", group="Vento e instabilità", label="Corrente a getto 250 hPa",
         title="Vento a 250 hPa – corrente a getto (km/h) e geopotenziale 250 hPa (dam)",
         needs=["u250", "v250", "z250"], unit="km/h", pal="jet",
         levels=[100, 125, 150, 175, 200, 225, 250, 275, 300, 350], extend="max"),
    dict(id="cape", group="Vento e instabilità", label="Instabilità (CAPE)",
         title="Energia potenziale convettiva – CAPE (J/kg) e pressione al suolo (hPa)",
         needs=["cape", "mslp"], unit="J/kg", pal="cape",
         levels=[100, 250, 500, 750, 1000, 1500, 2000, 2500, 3000, 4000], extend="max"),
]
CHART_BY_ID = {c["id"]: c for c in CHARTS}
GROUPS = ["Pressione", "Temperature", "Precipitazioni e nubi", "Vento e instabilità"]

# --------------------------------------------------------------------------------------
# Località dei meteogrammi e dei pennacchi dell'ensemble
# --------------------------------------------------------------------------------------
CITIES = [
    dict(id="ostuni", name="Ostuni", lat=40.729, lon=17.578),
    dict(id="bari", name="Bari", lat=41.117, lon=16.872),
    dict(id="lecce", name="Lecce", lat=40.352, lon=18.172),
    dict(id="napoli", name="Napoli", lat=40.852, lon=14.268),
    dict(id="roma", name="Roma", lat=41.893, lon=12.483),
    dict(id="firenze", name="Firenze", lat=43.770, lon=11.256),
    dict(id="bologna", name="Bologna", lat=44.494, lon=11.343),
    dict(id="milano", name="Milano", lat=45.464, lon=9.190),
    dict(id="torino", name="Torino", lat=45.070, lon=7.687),
    dict(id="venezia", name="Venezia", lat=45.441, lon=12.316),
    dict(id="palermo", name="Palermo", lat=38.116, lon=13.361),
    dict(id="cagliari", name="Cagliari", lat=39.223, lon=9.121),
]

# --------------------------------------------------------------------------------------
# Prodotti dell'ensemble
# --------------------------------------------------------------------------------------
PAL["spread"] = ["#fff7c2", "#fde38a", "#fdc35c", "#fb9a3d", "#f06a2e", "#d83a2c", "#b01f45", "#7d1b6a",
                 "#4f1c7c"]
ENS_REGIONS = ["europa", "emisfero_nord"]
SPAGHETTI_LEVELS = [(552, "#1f5fbf"), (576, "#c8102e")]
ENS_PRODUCTS = [
    dict(id="spaghetti", label="Spaghetti 500 hPa",
         title="Isoipse 552 dam (blu) e 576 dam (rosso) di ogni membro; linee spesse: media dell'ensemble",
         unit="", levels=[], pal=None, extend="neither"),
    dict(id="media", label="Media e dispersione 500 hPa",
         title="Geopotenziale medio a 500 hPa (dam, linee) e dispersione tra i membri (dam, colori)",
         unit="dam", pal="spread", levels=[1, 2, 3, 4, 5, 6, 8, 10, 12, 15], extend="max"),
]
ENS_PRODUCT_BY_ID = {p["id"]: p for p in ENS_PRODUCTS}
