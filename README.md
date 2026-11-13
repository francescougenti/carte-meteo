# Ventaglio: il meteo della tua città e quanto è sicuro

*Ventaglio chiuso, con il tempo stai al sicuro.*

Sito meteo che si aggiorna da solo a ogni nuova corsa dei modelli, con due anime:

- **La tua città** (pagina iniziale), per tutti: la previsione di tutti i 7.894 comuni italiani per 10 giorni, ora per ora
  nei primi giorni, con quanto è sicura, quando conviene ricontrollarla e cosa è cambiato dall'ultima visita;
  in più il radar della pioggia e le allerte della Protezione Civile.
- **Per appassionati**: carte in stile Meteociel, confronto tra modelli, ensemble e meteogrammi.

## La tua città

Per ogni comune e per ogni giorno (i capoluoghi e Ostuni sono calcolati nel loro punto, gli altri comuni in zone di circa
25 km e poi adattati alla loro quota):

- minima, massima, pioggia, nuvole, vento con il nome italiano (Scirocco, Maestrale…), quota neve e quattro fasce della giornata.
  Sono una media pesata di ECMWF IFS, AIFS, GFS e ICON-EU, con la temperatura corretta per l'altitudine della città;
- **gli 81 scenari**: la probabilità di pioggia è il numero di membri degli ensemble (50 ECMWF + 31 GEFS) in cui piove almeno 1 mm;
  le fasce colorate del grafico "I prossimi 10 giorni" mostrano dove cadono massime e minime in 8 scenari su 10;
- **ventaglio chiuso, socchiuso o aperto**: previsione sicura, abbastanza sicura o ancora incerta, e **quando lo saprai**: il giorno in cui
  conviene ricontrollare, stimato da come si restringono gli scenari con l'avvicinarsi della data. Le probabilità sono dette a parole
  (pioggia quasi certa, molto probabile, probabile, possibile, poco probabile, improbabile), con i millimetri sempre in vista;
- **ora per ora**: toccando un giorno, temperatura, pioggia, nuvole e vento ogni ora per tre giorni (ICON-EU) e poi ogni 3 ore
  fino al sesto (ECMWF IFS e GFS), con le ore in cui piove ("tra le 15 e le 18"), alba e tramonto;
- **cosa è cambiato**: dall'ultima visita (ricordata solo nel browser) o rispetto a ieri, e come è cambiata la previsione
  per ogni giorno negli ultimi giorni (lo storico è conservato nei dati del sito);
- **il perché, con la carta**: la causa principale del tempo del giorno (aria fredda o calda in arrivo e da dove,
  bassa o alta pressione, instabilità, vento, zero termico) in una frase, con la carta dei modelli che la mostra;
- quattro modelli a confronto e **IA contro fisica**: quale modello ha indovinato di più all'aeroporto più vicino
  (con gli scenari e lo storico, a scomparsa sotto il dettaglio del giorno);
- **preferiti**: la stella accanto al nome; i preferiti compaiono nella pagina iniziale e in cima a ogni comune (solo nel browser);
- **allerte**: dal bollettino nazionale di criticità idrogeologica e idraulica della Protezione Civile, comune per comune, per oggi e domani;
- **radar** (`#radar`): la pioggia in atto dalla rete radar nazionale della Protezione Civile, con l'ultima ora animata.

La pagina **IA contro fisica** confronta ogni giorno le massime e le minime previste da AIFS (intelligenza artificiale), ECMWF IFS,
GFS e ICON-EU con quelle misurate in circa 40 aeroporti italiani (METAR), con 1, 3 e 5 giorni di anticipo.
Il sito si installa sul telefono come un'app (manifest e service worker) e mostra l'ultima previsione anche offline.

I file dei dati sono descritti in [docs/formato-dati.md](docs/formato-dati.md). Il sito raccoglie da subito anche le
previsioni dei modelli e le temperature osservate negli aeroporti (METAR), per confrontare nei prossimi mesi
i modelli fisici con quello a intelligenza artificiale, città per città.

## Per appassionati

| Modello | Fonte | Fino a | Aree |
|---|---|---|---|
| GFS 0.25° | NOAA/NCEP | +192 h | tutte |
| ECMWF IFS 0.25° | ECMWF Open Data | +240 h (06/18: +144 h) | tutte |
| ECMWF AIFS 0.25° (intelligenza artificiale) | ECMWF Open Data | +240 h | Italia, Europa |
| ICON-EU 0.0625° | DWD | +120 h | Italia, Europa occidentale |
| GEFS 0.5°, 31 membri | NOAA/NCEP | +240 h | Europa, Emisfero Nord |
| ECMWF ENS 0.25°, 50 membri | ECMWF Open Data | +240 h (corse 00 e 12) | Europa, Emisfero Nord |

- **Aree:** Italia, Europa occidentale, Europa, Emisfero Nord, Nord America
- **Carte (17):** geopotenziale 500 hPa e pressione, pressione e spessore 500/1000, temperatura a 850 hPa, 500 hPa e 2 m, theta-e 850 hPa, precipitazioni in 6 ore e cumulate, acqua precipitabile, nuvolosità, umidità a 700 hPa, quota dello zero termico e neve al suolo (solo Italia ed Europa), vento a 10 m, raffiche, corrente a getto a 250 hPa, CAPE. Lo zero termico di ECMWF e AIFS è calcolato dalle temperature sui livelli di pressione; GFS e ICON-EU lo forniscono già pronto. Se un modello non fornisce un campo (per esempio AIFS non dà raffiche e CAPE), quella carta manca solo per lui.
- **Ensemble:** spaghetti delle isoipse 552 e 576 dam a 500 hPa, media e dispersione del geopotenziale.
- **Località:** meteogrammi con tutti i modelli a confronto (temperatura a 2 m e 850 hPa, pioggia, vento e raffiche, pressione, nuvolosità, zero termico, neve) e pennacchi dell'ensemble (temperatura a 2 m e a 850 hPa, pioggia, pressione, geopotenziale) per 12 città.
- **Sito:** sezioni Carte, Confronto (due modelli qualsiasi affiancati), Ensemble e Località; scadenze a passi di 6 ore, animazione, link condivisibili, aggiornamento automatico della pagina, tema chiaro e scuro.

## Come funziona

Tutto gira gratis su GitHub, senza server.

1. Ogni mezz'ora GitHub Actions controlla se NOAA o ECMWF hanno pubblicato una corsa completa più nuova di quella sul sito. Il controllo dura pochi secondi.
2. Se c'è una corsa nuova, lo script scarica solo i campi che servono dai file GRIB2 ufficiali, usando gli indici per prendere i singoli pezzi:
   - GFS: bucket NOAA su AWS (`noaa-gfs-bdp-pds`), con NOMADS come riserva
   - ECMWF: `data.ecmwf.int`, con il mirror AWS come riserva
3. Disegna le carte (circa 2.500 per GFS e 3.000 per ECMWF), legge i valori dei modelli su tutte le città, ricalcola la previsione "La tua città" e pubblica il sito su GitHub Pages. Su GitHub ci vogliono circa 10–15 minuti per modello.

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
- `CITIES`: le località dei meteogrammi (nome, latitudine, longitudine); hanno anche la previsione "La tua città"
- In `meteo/citta.py`: pesi dei modelli (`WEIGHTS`), soglie di pioggia e di "deciso" (`RAIN_DAY`, `T_RANGE_OK`, `P_OK`)
- L'elenco dei comuni è in `assets/luoghi/comuni.json` (si rigenera con `tools/prepara_luoghi.py` e `tools/altitudini.py`)
- `ENS_PRODUCTS`, `SPAGHETTI_LEVELS`: i prodotti dell'ensemble e le isoipse degli spaghetti
- In `meteo/sources.py` e `meteo/ensemble_sources.py`: `max_step` stabilisce fin dove arriva ogni modello, `regions` su quali aree si disegna

Dopo una modifica al codice il sito si ripubblica da solo; se cambi carte o formato, aumenta `SCHEMA` in `config.py` per far ridisegnare tutto subito.

**Importante:** la riga `cron` del workflow va modificata solo dal tuo account. GitHub esegue i controlli programmati a nome di chi l'ha cambiata per ultimo e non li esegue per conto di app esterne. Per ridisegnare subito tutte le carte usa **Run workflow** e spunta "Rigenera tutte le carte".

## Prova in locale

```bash
pip install -r requirements.txt
python -m meteo.build --public public --models gfs --steps 0,6,12 --regions italia
cp -r site/. public/ && python -m http.server -d public 8000
```

Per provare senza internet, `tests/fake_data.py` crea dati GRIB2 sintetici con la stessa struttura dei server reali e `tests/range_server.py` li serve in locale. Si usano con le variabili `METEO_GFS_ROOT`, `METEO_ECMWF_ROOT`, `METEO_AIFS_ROOT`, `METEO_ICON_ROOT`, `METEO_GEFS_ROOT`, `METEO_ENS_ROOT`, `METEO_METAR_URL` e `METEO_NOW`.

Per provare solo "La tua città", `tests/fake_campioni.py /tmp/pub` simula tre giorni di corse di tutti i modelli su tutte le città (con lo storico); poi `cp -r site/. /tmp/pub/ && python -m http.server -d /tmp/pub 8000`.

## Limiti

- GitHub Pages ammette siti fino a 1 GB. Con tutti i modelli il sito occupa circa 750–850 MB (immagini WebP senza perdita a 96 colori): per questo AIFS e ICON-EU hanno solo due aree. Il registro di ogni aggiornamento riporta lo spazio occupato e avvisa sopra i 950 MB.
- ARPEGE (Météo-France) non è incluso: l'archivio aperto di Météo-France al momento delle prove non conteneva i file delle corse.
- GitHub può ritardare di qualche minuto i controlli programmati nelle ore di punta.
- I controlli programmati si sospendono dopo 60 giorni senza commit. Il workflow lo evita facendo un commit vuoto ogni 40 giorni.

## Fonti e licenze

- Elenco dei comuni: database dei comuni italiani di Garda Informatica, dati ISTAT, licenza MIT. Altitudini: AWS Terrain Tiles.
- Osservazioni (verifica): bollettini METAR, NOAA Aviation Weather Center.

- GFS: NOAA/NCEP, dati di pubblico dominio.
- GEFS: NOAA/NCEP, dati di pubblico dominio.
- ECMWF IFS, AIFS ed ENS: [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data), licenza [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Le carte sono un'elaborazione grafica di questo sito, non prodotti ufficiali ECMWF.
- ICON-EU: [Deutscher Wetterdienst](https://opendata.dwd.de/), open data.
- Grafici dei meteogrammi: [Chart.js](https://www.chartjs.org/) (licenza MIT), incluso in `site/vendor`.
- Radar della pioggia (prodotto SRI) e bollettino di criticità: [Dipartimento della Protezione Civile](https://github.com/pcm-dpc), licenza CC BY 4.0.
- Mappa del radar: [Leaflet](https://leafletjs.com/) (licenza BSD-2, in `site/vendor/leaflet`), mappa di base © OpenStreetMap contributors e © CARTO.
- Coste e confini: [Natural Earth](https://www.naturalearthdata.com/), pubblico dominio. I file in `assets/geo` si rigenerano con `tools/prepara_geo.py`.
