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

Massime e minime previste, per la verifica dei modelli (fase 3). Chiave `modello|AAAAMMGGHH` (solo corse delle 00 e 12 UTC):
`{"luoghi": [id...], "giorni": [date da 1 a 5 giorni dopo], "min": [[valore per luogo] per giorno], "max": [...]}`.
Si conservano 60 giorni.

## `data/verifica/osservazioni.json`

Temperature osservate nelle stazioni aeroportuali italiane (bollettini METAR, NOAA Aviation Weather Center).

- `stazioni`: `{ICAO: [nome, lat, lon, quota]}`
- `giorni`: `{giorno UTC: {ICAO: [minima, massima, numero di osservazioni, pioggia osservata 0/1]}}`
- `abbinamenti`: `{luogo: [ICAO, distanza km]}`: stazione entro 25 km e 150 m di dislivello
- `recenti`: osservazioni grezze delle ultime 72 ore, per ricalcolare minime e massime

## `data/campioni/<modello>.npz`

File interni (NumPy) con i valori di ogni modello sui luoghi: `ids`, `h`, `valid`, `run`, `orog` (quota del terreno nel modello)
e un array `v_<variabile>` per variabile, di forma (luoghi, scadenze) o (luoghi, membri, scadenze) per gli ensemble.
`ecmwf-lungo.npz` conserva la corsa delle 00/12 quando quella delle 06/18 arriva solo a +144 h.
