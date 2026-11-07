# Carte meteo GFS ed ECMWF

Sito con le carte dei modelli **GFS** (NOAA/NCEP, fino a +192 h) ed **ECMWF IFS** (Open Data, fino a +240 h), in stile Meteociel. Si aggiorna da solo a ogni nuova corsa (00, 06, 12, 18 UTC).

- **Aree:** Italia, Europa occidentale, Europa, Emisfero Nord, Nord America
- **Carte (15):** geopotenziale 500 hPa e pressione, pressione e spessore 500/1000, temperatura a 850 hPa, 500 hPa e 2 m, theta-e 850 hPa, precipitazioni in 6 ore e cumulate, acqua precipitabile, nuvolosità, umidità a 700 hPa, vento a 10 m, raffiche, corrente a getto a 250 hPa, CAPE
- **Sito:** scelta di modello, area e carta, scadenze a passi di 6 ore, animazione, confronto GFS/ECMWF affiancati, link condivisibili, aggiornamento automatico della pagina

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
- In `meteo/sources.py`, `max_step` stabilisce fin dove arriva ogni modello

Dopo una modifica al codice il sito si ripubblica da solo. Per ridisegnare subito tutte le carte usa **Run workflow** e spunta "Rigenera tutte le carte".

## Prova in locale

```bash
pip install -r requirements.txt
python -m meteo.build --public public --models gfs --steps 0,6,12 --regions italia
cp -r site/. public/ && python -m http.server -d public 8000
```

Per provare senza internet, `tests/fake_data.py` crea dati GRIB2 sintetici con la stessa struttura dei server reali e `tests/range_server.py` li serve in locale. Si usano con le variabili `METEO_GFS_ROOT`, `METEO_ECMWF_ROOT` e `METEO_NOW`.

## Limiti

- GitHub Pages ammette siti fino a 1 GB. Con tutte le carte il sito occupa circa 600–750 MB.
- GitHub può ritardare di qualche minuto i controlli programmati nelle ore di punta.
- I controlli programmati si sospendono dopo 60 giorni senza commit. Il workflow lo evita facendo un commit vuoto ogni 40 giorni.

## Fonti e licenze

- GFS: NOAA/NCEP, dati di pubblico dominio.
- ECMWF: [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data), licenza [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Le carte sono un'elaborazione grafica di questo sito, non prodotti ufficiali ECMWF.
- Coste e confini: [Natural Earth](https://www.naturalearthdata.com/), pubblico dominio. I file in `assets/geo` si rigenerano con `tools/prepara_geo.py`.
