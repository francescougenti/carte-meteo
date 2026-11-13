# Formato dei dati di Ventaglio

Tutti i file stanno sotto `data/` nel sito pubblicato e sono rigenerati a ogni nuova corsa.
Il campo `formato` vale `1`: aumenta solo se un cambiamento rompe la compatibilità, così un'app
futura può leggere gli stessi file in sicurezza.

Orari: istanti in UTC nel formato `2026-11-12T06:00:00Z`; giorni come date `2026-11-12`.
I giorni sono quelli del calendario italiano; le quantità giornaliere coprono le 24 ore UTC di quella data
(circa un'ora prima dell'ora italiana). Temperature in °C, pioggia in mm, vento in km/h, quote in metri.

## Capoluoghi, zone e comuni

- I capoluoghi di provincia e le località dei meteogrammi hanno una previsione calcolata nel loro punto: `data/citta/<id>.json`.
- Gli altri comuni sono raggruppati in 641 zone di 0,25° (circa 25 km). La previsione di una zona, `data/celle/<id>.json`,
  ha lo stesso formato di quella di una città, calcolata nel baricentro dei comuni della zona e alla loro quota mediana (`alt`).
  Il sito la adatta al comune: temperature + 0,0065 × (quota della zona − quota del comune), e neve al posto della pioggia
  se la quota neve del giorno è vicina o sotto la quota del comune.

## `data/citta/comuni.json`

L'ultimo campo, `mare`, è la distanza dalla costa in km per i comuni entro 12 km dal mare (vuoto per gli altri).

Tutti i 7.894 comuni, per la ricerca e "Vicino a me":
`{"campi": ["id", "nome", "altro", "sigla", "lat", "lon", "alt", "file"], "province": {sigla: [provincia, regione]}, "comuni": [[...], ...]}`.
`file` è `citta/<id>` o `celle/<id>`.

## `data/citta/indice.json`

Elenco dei capoluoghi, per la ricerca rapida e le anteprime.

```json
{
  "formato": 1,
  "aggiornato": "2026-11-12T11:00:00Z",
  "corse": {"ecmwf": "2026-11-12T00:00:00Z", "gfs": "...", "aifs": "...", "icon-eu": "...", "gefs": "...", "ecmwf-ens": "..."},
  "crescita": [0.5, 0.9, 1.2, ...],
  "luoghi": [
    {"id": "lecce", "nome": "Lecce", "altro": null, "sigla": "LE", "provincia": "Lecce", "regione": "Puglia",
     "lat": 40.35350, "lon": 18.17192, "alt": 49,
     "giorni": [{"data": "2026-11-12", "min": 9.1, "max": 17.4, "p": 23, "codice": "poco-nuvoloso", "stato": "deciso"}, ...]}
  ]
}
```

- `crescita[k]`: indice di incertezza tipico (mediana su tutti i luoghi) a `k` giorni di anticipo, misurato sulla corsa attuale. Serve a stimare "quando lo saprai".
- `giorni`: oggi, domani e dopodomani in breve.

## `data/citta/<id>.json`

Previsione completa di un luogo.

| Campo | Contenuto |
|---|---|
| `id`, `nome`, `altro`, `provincia`, `sigla`, `regione`, `lat`, `lon`, `alt` | il luogo (`altro`: nome nell'altra lingua, per esempio Bozen) |
| `mare_km` | distanza del centro dalla costa in km, solo se entro 12 km (comuni "sul mare") |
| `aggiornato` | quando è stata calcolata questa previsione |
| `corse` | corsa usata per ogni modello |
| `membri` | numero di scenari (membri degli ensemble) disponibili |
| `giorni` | fino a 10 giorni, vedi sotto |
| `storia` | le previsioni passate per ogni giorno, vedi sotto |

Ogni elemento di `giorni`:

| Campo | Contenuto |
|---|---|
| `data` | il giorno |
| `min`, `max` | minima e massima: media pesata dei modelli, corretta per l'altitudine del luogo |
| `min_f`, `max_f` | forbice `[basso, alto]` in cui cadono minima e massima in 8 scenari su 10 (10° e 90° percentile dell'ensemble, centrati sui modelli) |
| `pioggia.p` | probabilità (%) di almeno 1 mm nella giornata: scenari con pioggia / scenari totali |
| `pioggia.scenari`, `pioggia.su` | scenari (membri degli ensemble) con pioggia e scenari totali; `forte`: scenari con almeno 10 mm |
| `pioggia.mm` | pioggia prevista dai modelli (media pesata) |
| `pioggia.membri` | pioggia di ogni scenario, per ensemble (`ecmwf-ens`: 50, `gefs`: 31) |
| `nubi` | copertura nuvolosa nelle ore di luce (%) |
| `codice` | icona del giorno: `sereno`, `poco-nuvoloso`, `nuvoloso`, `coperto`, `rovesci`, `pioggia`, `pioggia-forte`, `temporale`, `neve`, `pioggia-neve` |
| `neve.quota` | quota indicativa della neve (zero termico meno 300 m); `neve.suolo`: neve al suolo in cm |
| `vento` | `kmh` vento medio massimo, `raffiche`, `dir` direzione di provenienza in gradi, `nome` (Tramontana, Grecale, Levante, Scirocco, Ostro, Libeccio, Ponente, Maestrale) |
| `fasce` | quattro fasce di 6 ore (notte, mattina, pomeriggio, sera, in ore UTC 0–6, 6–12, 12–18, 18–24), ognuna con `t`, `mm`, `p`, `codice`; `null` se la fascia è già passata |
| `modelli` | `min`, `max`, `mm` di ogni modello deterministico; `escluso: true` se è troppo lontano dagli altri ed è stato lasciato fuori dalla media |
| `perche` | fino a tre cause del tempo del giorno, la più importante per prima (vedi sotto) |
| `incertezza` | vedi sotto |
| `alba`, `tramonto` | ore locali (`"06:34"`), calcolate per la posizione del luogo |
| `ore` | ora per ora, solo per i primi 6 giorni (vedi sotto) |
| `quota` | in quota: `t1500` temperatura a 850 hPa (circa 1.500 m), `vento` km/h e `dir` direzione di provenienza a 850 hPa |
| `mare` | solo per i luoghi sul mare, nelle ore di luce (6–21): onde `min` e `max` (altezza significativa, m), `stato` (scala Douglas 0–9: calmo, quasi calmo, poco mosso, mosso, molto mosso, agitato, molto agitato, grosso, molto grosso, tempestoso), `dir` (da dove arrivano, gradi) e `periodo` (s) all'ora delle onde più alte; primi 6 giorni |
| `pioggia_ore` | fino a due intervalli di pioggia `[dalle, alle, mm]` in ore locali (24 = mezzanotte), ricavati da `ore`; mancano se il giorno nel complesso è asciutto (probabilità sotto il 30% e meno di 1 mm) |

`ore`: righe `[ora, temperatura, mm, nubi %, vento km/h, direzione di provenienza in gradi, icona, notte (0/1), passo in ore]`
(più l'altezza delle onde in metri come decimo valore, per i luoghi sul mare),
in ora locale. Per oggi, domani e dopodomani una riga ogni ora (da quella in corso), poi una ogni 3 ore fino al sesto giorno.
I `mm` sono quelli caduti nel `passo` che termina a quell'ora. È una media pesata di ICON-EU (ogni ora fino a +78 h),
ECMWF IFS e GFS (ogni 3 ore, interpolati nelle ore intermedie), con la temperatura corretta per l'altitudine come per i giorni.
L'icona è quella della tabella sopra, calcolata ora per ora (neve e pioggia mista dallo zero termico).

`incertezza`:

- `stato`: `deciso`, `quasi` o `aperto`.
- `motivo`: `pioggia` o `temperatura`, cioè cosa rende incerta la previsione.
- `indice`: il valore numerico (1 o meno = deciso). È il maggiore tra la forbice della massima divisa per 4 °C e la distanza della probabilità di pioggia dalla certezza (min(p, 1−p) / 0,2).
- `ricontrolla`: il giorno in cui conviene ricontrollare (la sera); `anticipo`: quanti giorni prima del giorno previsto.
- `fino_all_ultimo`: `true` se non si prevede che diventi decisa prima del giorno stesso.

`perche`: ogni causa ha `tipo` e la carta che la mostra (`carta`: id della carta, `ora`: istante di validità).

| `tipo` | Quando | Altri campi |
|---|---|---|
| `freddo`, `caldo` | la temperatura a 850 hPa cambia di almeno 4° rispetto al giorno prima | `delta` (gradi), `dir` (direzione di provenienza dell'aria a 850 hPa) |
| `neve` | è prevista neve o pioggia mista | `zero` (zero termico, m) |
| `temporali` | CAPE di almeno 800 J/kg e pioggia probabile | `cape` |
| `vento` | vento medio da 39 km/h o raffiche da 65 km/h | |
| `bassa` | pressione minima fino a 1008 hPa e pioggia probabile | `hpa` |
| `alta` | pressione media da 1022 hPa e pioggia improbabile | `hpa` |
| `pioggia` | pioggia probabile senza una delle cause sopra | |

`storia` è un oggetto `{giorno: [istantanee]}`; ogni istantanea è
`[quando, min, max, probabilità pioggia %, mm, codice]` (`quando` nel formato `2026-11-12T11:00Z`).
Si conserva al massimo un'istantanea ogni due ore e mezza, per 9 giorni.

## `data/verifica/previsioni.json`

Massime e minime previste da ogni modello deterministico nel punto esatto delle stazioni aeroportuali e alla loro quota,
per la verifica. Chiave `modello|AAAAMMGGHH` (corse delle 00 e 12 UTC):
`{"luoghi": ["st-LIRF", ...], "giorni": [date da 1 a 5 giorni dopo], "min": [[valore per stazione] per giorno], "max": [...]}`.
Le corse del primo giorno (12 novembre 2026) hanno come luoghi i capoluoghi invece delle stazioni e non entrano nella classifica.
Si conservano 60 giorni.

## `data/verifica/classifica.json`

"IA contro fisica": confronto tra previsto e misurato negli ultimi `finestra` (30) giorni, solo corse delle 00 UTC.

- `giorni`, `dal`, `al`: giorni verificati.
- `italia` e `stazioni.<ICAO>.anticipo`: `{"1"|"3"|"5": {modello: {...}}}`, con anticipo in giorni. Per ogni modello:
  `tipo` (`ia` o `fisico`), `n` (casi), `errore` (errore medio assoluto di massime e minime, °C), `errore_max`, `errore_min`,
  `scarto` (errore medio con segno: positivo = previsto più caldo del vero), `vinti` e `gare` (casi in cui è stato il più vicino al vero, su quelli con almeno 3 modelli).
- `stazioni.<ICAO>`: anche `nome`, `lat`, `lon`, `giorni`.

## `data/verifica/osservazioni.json`

Temperature osservate nelle stazioni aeroportuali italiane (bollettini METAR, NOAA Aviation Weather Center).

- `stazioni`: `{ICAO: [nome, lat, lon, quota]}`
- `giorni`: `{giorno UTC: {ICAO: [minima, massima, numero di osservazioni, pioggia osservata 0/1]}}`
- `abbinamenti`: `{luogo: [ICAO, distanza km]}`: stazione entro 25 km e 150 m di dislivello
- `recenti`: osservazioni grezze delle ultime 72 ore, per ricalcolare minime e massime

## `data/sci.json`

Comprensori sciistici italiani da [LiftRadar](https://liftradar.eu) (bollettini dei comprensori e degli enti turistici, due volte al giorno).

- `totale`: `comprensori`, `aperti`, `impianti` `[aperti, totali]`, `km` di piste `[aperti, totali]`.
- `comprensori`: `id`, `nome`, `regione`, `lat`, `lon`, `stato` (`open`, `closed`, `no_report`), `controllato`, `impianti` e `piste` `[aperti, totali]`,
  `km` `[aperti, totali]`, `neve` `[a valle, in quota, fresca]` in cm (null se non pubblicata), `valanghe` (grado di pericolo 1–5),
  `comune`, `comune_nome`, `comune_km`: il comune più vicino, per la previsione;
  `modello`: neve al suolo stimata da ICON-EU, adesso, `valle` nel punto del comprensorio e `cima` nella cella più alta del modello
  entro 8 km, con la sua `quota` (m) e `cima_3g` (tra 3 giorni). Il sito la usa quando il comprensorio non pubblica le altezze della neve.
- `fonte_aggiornata`: quando LiftRadar ha raccolto i dati.

## `data/stazioni.json`

Ultima misura delle centraline MeteoNetwork italiane (solo quelle delle ultime 3 ore). Esiste solo se il repository ha il segreto `MNW_TOKEN` (token BULK).
`campi`: `codice`, `luogo`, `lat`, `lon`, `quota`, `t` (°C), `umidita` (%), `pioggia_oggi` (mm), `intensita` (mm/h), `vento` (km/h), `dir`, `raffica`, `ora` (UTC);
`stazioni`: una riga per centralina in quell'ordine.

## `data/allerte.json`

Allerte del bollettino di criticità idrogeologica e idraulica nazionale del Dipartimento della Protezione Civile
(repository `pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica`, licenza CC BY 4.0), aggiornato quando esce un bollettino nuovo.

- `bollettino`: nome dei file di origine (`AAAAMMGG_HHMM`); `nome`, `emesso`; `oggi` e `domani`: i giorni a cui si riferisce.
- `rischi`: `["idraulico", "temporali", "idrogeologico"]`, l'ordine dei livelli qui sotto.
- `zone`: zone di allerta con almeno un'allerta, `{nome, oggi: [livello per rischio], domani: [...]}`; livello 0 nessuna, 1 gialla, 2 arancione, 3 rossa.
- `comuni`: `{id del comune: indice in zone}`, solo i comuni in zone con allerta. Il comune è assegnato alla zona che contiene il suo punto (o alla più vicina entro 5 km).
- `link`, `fonte`, `aggiornato`.

## `data/campioni/<modello>.npz`

File interni (NumPy) con i valori di ogni modello sui luoghi: `ids`, `h`, `valid`, `run`, `orog` (quota del terreno nel modello)
e un array `v_<variabile>` per variabile, di forma (luoghi, scadenze) o (luoghi, membri, scadenze) per gli ensemble.
`ecmwf-lungo.npz` conserva la corsa delle 00/12 quando quella delle 06/18 arriva solo a +144 h.
`<modello>-orario.npz` (ICON-EU, ECMWF IFS, GFS) contiene `t2m`, `tp_total` (pioggia cumulata dall'inizio della corsa), `tcc`, `u10` e `v10`
sui capoluoghi e sulle zone, ogni ora (ICON-EU) o ogni 3 ore, per la previsione ora per ora.
`icon-eu-neve.npz` contiene la neve al suolo di ICON-EU (cm) nei comprensori: `valle` e `cima`, con `orog` = quota della cella in cima.
`ecmwf-mare.npz` contiene `swh` (altezza significativa delle onde, m), `mwd` (direzione media, gradi) e `pp1d` (periodo di picco, s) ogni 3 ore fino a +144 h,
nella cella di mare più vicina ai capoluoghi costieri e ai comuni costieri di ogni zona.
