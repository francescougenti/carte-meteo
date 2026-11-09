# Carte meteo GFS, ECMWF, AIFS, ICON-EU ed ensemble

Sito di carte meteo in stile Meteociel che si aggiorna da solo a ogni nuova corsa (00, 06, 12, 18 UTC).

| Modello | Fonte | Fino a | Aree |
|---|---|---|---|
| GFS 0.25° | NOAA/NCEP | +192 h | tutte |
| ECMWF IFS 0.25° | ECMWF Open Data | +240 h (06/18: +144 h) | tutte |
| ECMWF AIFS 0.25° (intelligenza artificiale) | ECMWF Open Data | +240 h | Italia, Europa |
| ICON-EU 0.0625° | DWD | +120 h | Italia, Europa occidentale |
| GEFS 0.5°, 31 membri | NOAA/NCEP | +240 h | Europa, Emisfero Nord |
| ECMWF ENS 0.25°, 50 membri | ECMWF Open Data | +240 h (corse 00 e 12) | Europa, Emisfero Nord |

- **Aree:** Italia, Europa occidentale, Europa, Emisfero Nord, Nord America
- **Carte (15):** geopotenziale 500 hPa e pressione, pressione e spessore 500/1000, temperatura a 850 hPa, 500 hPa e 2 m, theta-e 850 hPa, precipitazioni in 6 ore e cumulate, acqua precipitabile, nuvolosità, umidità a 700 hPa, vento a 10 m, raffiche, corrente a getto a 250 hPa, CAPE. Se un modello non fornisce un campo (per esempio AIFS non dà raffiche e CAPE), quella carta manca solo per lui.
- **Ensemble:** spaghetti delle isoipse 552 e 576 dam a 500 hPa, media e dispersione del geopotenziale.
- **Località:** meteogrammi con tutti i modelli a confronto (temperatura a 2 m e 850 hPa, pioggia, vento e raffiche, pressione, nuvolosità) e pennacchi dell'ensemble (temperatura a 850 hPa, pioggia, pressione, geopotenziale) per 12 città.
- **Sito:** sezioni Carte, Confronto (due modelli qualsiasi affiancati), Ensemble e Località; scadenze a passi di 6 ore, animazione, link condivisibili, aggiornamento automatico della pagina.

## Come funziona

Tutto gira gratis su GitHub, senza server.

1. Ogni mezz'ora GitHub Actions controlla se NOAA o ECMWF hanno pubblicato una corsa completa più nuova di quella sul sito. Il controllo dura pochi secondi.
2. Se c'è una corsa nuova, lo script scarica solo i campi che servono dai file GRIB2 ufficiali, usando gli indici per prendere i singoli pezzi:
   - GFS: bucket NOAA su AWS (`noaa-gfs-bdp-pds`), con NOMADS come riserva
   - ECMWF: `data.ecmwf.int`, con il mirror AWS come riserva
3. Disegna le carte (circa 2.500 per GFS e 3.000 per ECMWF) e pubblica il sito su GitHub Pages. Su GitHub ci vogliono circa 10–15 minuti per modello.

Le corse ECMWF delle 06 e 18 UTC arrivano solo a +144 h. In quel caso le scadenze da +150 a +240 h restano quelle della corsa precedente (00 o 12 UTC), segnate nella linea del tempo con una sottolineatura a puntini.

## Attivazione (una volta sola)

1. Crea un repository **pubblico** su GitHub. Pubblico perché così GitHub Actions non ha limiti di minuti.
2. Carica tutti i file di questa cartella, compresa `.github/workflows/aggiorna-carte.yml`.
3. Nel repository vai in **Settings → Pages**. In **Build and deployment → Source** scegli **GitHub Actions**.
4. Vai in **Actions → Aggiorna carte meteo → Run workflow** per far partire subito il primo aggiornamento. Poi riparte da solo.
5. Il sito è su `https://TUO-UTENTE.github.io/NOME-REPOSITORY/`.

Se un aggiornamento non riesce, GitHub te lo segnala per email e alla corsa successiva riprova da solo.

## Personalizzare

Tutto è in `meteo/config.py`:

- `REGIONS`: aree, proiezione, riquadro, distanza tra le isobare (`isobar`, in hPa)
- `CHARTS`: carte, titoli, scale di colore e soglie (`levels`)
- `CITIES`: le località dei meteogrammi (nome, latitudine, longitudine)
- `ENS_PRODUCTS`, `SPAGHETTI_LEVELS`: i prodotti dell'ensemble e le isoipse degli spaghetti
- In `meteo/sources.py` e `meteo/ensemble_sources.py`: `max_step` stabilisce fin dove arriva ogni modello, `regions` su quali aree si disegna

Dopo una modifica al codice il sito si ripubblica da solo. Per ridisegnare subito tutte le carte usa **Run workflow** e spunta "Rigenera tutte le carte".

## Prova in locale

```bash
pip install -r requirements.txt
python -m meteo.build --public public --models gfs --steps 0,6,12 --regions italia
cp -r site/. public/ && python -m http.server -d public 8000
```

Per provare senza internet, `tests/fake_data.py` crea dati GRIB2 sintetici con la stessa struttura dei server reali e `tests/range_server.py` li serve in locale. Si usano con le variabili `METEO_GFS_ROOT`, `METEO_ECMWF_ROOT` e `METEO_NOW`.

## Limiti

- GitHub Pages ammette siti fino a 1 GB. Con tutti i modelli il sito occupa circa 750–850 MB: per questo AIFS e ICON-EU hanno solo due aree. Il registro di ogni aggiornamento riporta lo spazio occupato e avvisa sopra i 950 MB.
- ARPEGE (Météo-France) non è incluso: l'archivio aperto di Météo-France al momento delle prove non conteneva i file delle corse.
- GitHub può ritardare di qualche minuto i controlli programmati nelle ore di punta.
- I controlli programmati si sospendono dopo 60 giorni senza commit. Il workflow lo evita facendo un commit vuoto ogni 40 giorni.

## Fonti e licenze

- GFS: NOAA/NCEP, dati di pubblico dominio.
- GEFS: NOAA/NCEP, dati di pubblico dominio.
- ECMWF IFS, AIFS ed ENS: [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data), licenza [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Le carte sono un'elaborazione grafica di questo sito, non prodotti ufficiali ECMWF.
- ICON-EU: [Deutscher Wetterdienst](https://opendata.dwd.de/), open data.
- Grafici dei meteogrammi: [Chart.js](https://www.chartjs.org/) (licenza MIT), incluso in `site/vendor`.
- Coste e confini: [Natural Earth](https://www.naturalearthdata.com/), pubblico dominio. I file in `assets/geo` si rigenerano con `tools/prepara_geo.py`.
