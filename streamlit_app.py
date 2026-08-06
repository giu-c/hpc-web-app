import base64
import csv
from bisect import bisect_left
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

PROVIDER_COLOR = {"oci": "#a4161a", "aws": "#ffa94d"}   # rosso scuro / arancione chiaro
PROVIDER_LABEL = {"oci": "OCI", "aws": "AWS"}
NA_COLOR = "#6b7280"                                     # grigio: non disponibile
Z_PRIORITY = {"aws": 30, "oci": 20, "nd": 10}            # sovrapposizione pin
EPS = 1e-9

GROUP_ORDER = ("Europe", "North America", "Asia", "Middle East",
               "South America", "Africa", "Oceania")

ARCH_OPTIONS = (("ARM", "ARM"), ("x86 AMD", "x86(AMD)"), ("x86 Intel", "x86(Intel)"))

# Ordine unico dei tagli temporali: vale per hpc.csv, per i normalizzati e
# (con l'ultimo nome diverso) per i listini dei volumi. L'indice 0..3 è la
# chiave che gira in tutta l'app al posto del nome della colonna.
REAL_COLS = ("price($/h)", "daily_price", "weekly_price", "monthly_price")
NORM_COLS = tuple("N-" + c for c in REAL_COLS)
VOL_COLS = ("price($/h)", "daily_price", "weekly_price", "monthly_price(730h)")

GRANULARITY = {  # etichetta -> (indice prezzo, suffisso, formato numerico)
    "Hourly":         (0, "/h",     "$ %.3f"),
    "Daily":          (1, "/day",   "$ %.2f"),
    "Weekly":         (2, "/week",  "$ %.1f"),
    "Monthly (730h)": (3, "/month", "$ %.0f"),
}

# --- Volume di avvio ---------------------------------------------------------
VOLUME_SIZES = {"30 GB": 30, "200 GB": 200, "1 TB": 1000}
VOLUME_SPEED = {"🐢 Lower": 0, "🐈​ Balanced": 10, "​🐎​ High": 20, "⚡ Ultra": 120}
VOL_SIZE_DEFAULT = "30 GB"
VOL_SPEED_DEFAULT = "🐈​ Balanced"

# In ebs_gp3_prices.csv 12 regioni su 34 sono scritte per esteso invece che
# con il codice: qui si riportano tutte alla stessa forma dell'hpc.csv.
EBS_REGION_ALIAS = {
    "EU (Frankfurt)":              "eu-central-1",
    "EU (Ireland)":                "eu-west-1",
    "EU (London)":                 "eu-west-2",
    "EU (Milan)":                  "eu-south-1",
    "EU (Paris)":                  "eu-west-3",
    "EU (Stockholm)":              "eu-north-1",
    "Mexico (Central)":            "mx-central-1",
    "South America (Sao Paulo)":   "sa-east-1",
    "Asia Pacific (Taipei)":       "ap-east-2",
    "Asia Pacific (Malaysia)":     "ap-southeast-5",
    "Asia Pacific (New Zealand)":  "ap-southeast-6",
    "Asia Pacific (Thailand)":     "ap-southeast-7",
}

# ----------------------------------------------------------------------------
# Città. AWS: da aws_cities.txt (raggruppamento incluso). OCI: da
# oci_cities.txt; coordinate approssimate della località indicata (per
# "Kenya" si usa Nairobi, per "Marocco 2" un punto presso Settat; le coppie
# di sedi omonime hanno un piccolo scostamento per restare distinguibili).
# ----------------------------------------------------------------------------
AWS_CITIES = [
    # Nord America
    {"id": "aws|us-east-1",      "region": "us-east-1",      "name": "US East (N. Virginia)",      "lat": 38.95,  "lng": -77.45,  "group": "North America"},
    {"id": "aws|us-east-2",      "region": "us-east-2",      "name": "US East (Ohio)",             "lat": 39.96,  "lng": -83.00,  "group": "North America"},
    {"id": "aws|us-west-1",      "region": "us-west-1",      "name": "US West (N. California)",    "lat": 37.35,  "lng": -121.96, "group": "North America"},
    {"id": "aws|us-west-2",      "region": "us-west-2",      "name": "US West (Oregon)",           "lat": 45.85,  "lng": -119.70, "group": "North America"},
    {"id": "aws|ca-central-1",   "region": "ca-central-1",   "name": "Canada (Central)",           "lat": 45.50,  "lng": -73.57,  "group": "North America"},
    {"id": "aws|ca-west-1",      "region": "ca-west-1",      "name": "Canada West (Calgary)",      "lat": 51.05,  "lng": -114.07, "group": "North America"},
    {"id": "aws|mx-central-1",   "region": "mx-central-1",   "name": "Mexico (Central)",           "lat": 20.59,  "lng": -100.39, "group": "North America"},
    # Sud America
    {"id": "aws|sa-east-1",      "region": "sa-east-1",      "name": "South America (São Paulo)",  "lat": -23.55, "lng": -46.63,  "group": "South America"},
    # Europa
    {"id": "aws|eu-central-1",   "region": "eu-central-1",   "name": "Europe (Frankfurt)",         "lat": 50.11,  "lng": 8.68,    "group": "Europe"},
    {"id": "aws|eu-central-2",   "region": "eu-central-2",   "name": "Europe (Zurich)",            "lat": 47.37,  "lng": 8.54,    "group": "Europe"},
    {"id": "aws|eu-west-1",      "region": "eu-west-1",      "name": "Europe (Ireland)",           "lat": 53.35,  "lng": -6.26,   "group": "Europe"},
    {"id": "aws|eu-west-2",      "region": "eu-west-2",      "name": "Europe (London)",            "lat": 51.51,  "lng": -0.13,   "group": "Europe"},
    {"id": "aws|eu-west-3",      "region": "eu-west-3",      "name": "Europe (Paris)",             "lat": 48.86,  "lng": 2.35,    "group": "Europe"},
    {"id": "aws|eu-south-1",     "region": "eu-south-1",     "name": "Europe (Milan)",             "lat": 45.46,  "lng": 9.19,    "group": "Europe"},
    {"id": "aws|eu-south-2",     "region": "eu-south-2",     "name": "Europe (Spain)",             "lat": 41.65,  "lng": -0.88,   "group": "Europe"},
    {"id": "aws|eu-north-1",     "region": "eu-north-1",     "name": "Europe (Stockholm)",         "lat": 59.33,  "lng": 18.06,   "group": "Europe"},
    # Africa
    {"id": "aws|af-south-1",     "region": "af-south-1",     "name": "Africa (Cape Town)",         "lat": -33.92, "lng": 18.42,   "group": "Africa"},
    # Medio-Oriente
    {"id": "aws|il-central-1",   "region": "il-central-1",   "name": "Israel (Tel Aviv)",          "lat": 32.08,  "lng": 34.78,   "group": "Middle East"},
    {"id": "aws|me-south-1",     "region": "me-south-1",     "name": "Middle East (Bahrain)",      "lat": 26.23,  "lng": 50.59,   "group": "Middle East"},
    {"id": "aws|me-central-1",   "region": "me-central-1",   "name": "Middle East (UAE)",          "lat": 25.20,  "lng": 55.27,   "group": "Middle East"},
    # Asia
    {"id": "aws|ap-east-1",      "region": "ap-east-1",      "name": "Asia Pacific (Hong Kong)",   "lat": 22.32,  "lng": 114.17,  "group": "Asia"},
    {"id": "aws|ap-east-2",      "region": "ap-east-2",      "name": "Asia Pacific (Taipei)",      "lat": 25.03,  "lng": 121.56,  "group": "Asia"},
    {"id": "aws|ap-south-1",     "region": "ap-south-1",     "name": "Asia Pacific (Mumbai)",      "lat": 19.08,  "lng": 72.88,   "group": "Asia"},
    {"id": "aws|ap-south-2",     "region": "ap-south-2",     "name": "Asia Pacific (Hyderabad)",   "lat": 17.38,  "lng": 78.49,   "group": "Asia"},
    {"id": "aws|ap-southeast-1", "region": "ap-southeast-1", "name": "Asia Pacific (Singapore)",   "lat": 1.35,   "lng": 103.82,  "group": "Asia"},
    {"id": "aws|ap-southeast-3", "region": "ap-southeast-3", "name": "Asia Pacific (Jakarta)",     "lat": -6.21,  "lng": 106.85,  "group": "Asia"},
    {"id": "aws|ap-southeast-5", "region": "ap-southeast-5", "name": "Asia Pacific (Malaysia)",    "lat": 3.14,   "lng": 101.69,  "group": "Asia"},
    {"id": "aws|ap-southeast-7", "region": "ap-southeast-7", "name": "Asia Pacific (Thailand)",    "lat": 13.76,  "lng": 100.50,  "group": "Asia"},
    {"id": "aws|ap-northeast-1", "region": "ap-northeast-1", "name": "Asia Pacific (Tokyo)",       "lat": 35.68,  "lng": 139.69,  "group": "Asia"},
    {"id": "aws|ap-northeast-2", "region": "ap-northeast-2", "name": "Asia Pacific (Seoul)",       "lat": 37.57,  "lng": 126.98,  "group": "Asia"},
    {"id": "aws|ap-northeast-3", "region": "ap-northeast-3", "name": "Asia Pacific (Osaka)",       "lat": 34.69,  "lng": 135.50,  "group": "Asia"},
    # Oceania
    {"id": "aws|ap-southeast-2", "region": "ap-southeast-2", "name": "Asia Pacific (Sydney)",      "lat": -33.87, "lng": 151.21,  "group": "Oceania"},
    {"id": "aws|ap-southeast-4", "region": "ap-southeast-4", "name": "Asia Pacific (Melbourne)",   "lat": -37.81, "lng": 144.96,  "group": "Oceania"},
    {"id": "aws|ap-southeast-6", "region": "ap-southeast-6", "name": "Asia Pacific (New Zealand)", "lat": -36.85, "lng": 174.76,  "group": "Oceania"},
]

OCI_CITIES = [
    # Nord America
    {"id": "oci|ashburn",      "name": "US East (Ashburn)",                   "lat": 39.04,  "lng": -77.49,  "group": "North America"},
    {"id": "oci|chicago",      "name": "US Midwest (Chicago)",                "lat": 41.88,  "lng": -87.63,  "group": "North America"},
    {"id": "oci|phoenix",      "name": "US West (Phoenix)",                   "lat": 33.45,  "lng": -112.07, "group": "North America"},
    {"id": "oci|sanjose",      "name": "US West (San Jose)",                  "lat": 37.34,  "lng": -121.89, "group": "North America"},
    {"id": "oci|montreal",     "name": "Canada Southeast (Montreal)",         "lat": 45.50,  "lng": -73.57,  "group": "North America"},
    {"id": "oci|toronto",      "name": "Canada Southeast (Toronto)",          "lat": 43.65,  "lng": -79.38,  "group": "North America"},
    {"id": "oci|queretaro",    "name": "Mexico Central (Querétaro)",          "lat": 20.59,  "lng": -100.39, "group": "North America"},
    {"id": "oci|monterrey",    "name": "Mexico Northeast (Monterrey)",        "lat": 25.67,  "lng": -100.31, "group": "North America"},
    # Sud America
    {"id": "oci|sanpaolo",     "name": "Brazil East (São Paulo)",             "lat": -23.55, "lng": -46.63,  "group": "South America"},
    {"id": "oci|vinhedo",      "name": "Brazil Southeast (Vinhedo)",          "lat": -23.03, "lng": -46.98,  "group": "South America"},
    {"id": "oci|santiago",     "name": "Chile Central (Santiago)",            "lat": -33.45, "lng": -70.67,  "group": "South America"},
    {"id": "oci|valparaiso",   "name": "Chile West (Valparaiso)",             "lat": -33.05, "lng": -71.62,  "group": "South America"},
    {"id": "oci|bogota",       "name": "Colombia Central (Bogotá)",           "lat": 4.71,   "lng": -74.07,  "group": "South America"},
    # Europa
    {"id": "oci|parigi",       "name": "France Central (Paris)",              "lat": 48.86,  "lng": 2.35,    "group": "Europe"},
    {"id": "oci|marsiglia",    "name": "France South (Marseille)",            "lat": 43.30,  "lng": 5.37,    "group": "Europe"},
    {"id": "oci|francoforte",  "name": "Germany Central (Frankfurt)",         "lat": 50.11,  "lng": 8.68,    "group": "Europe"},
    {"id": "oci|milano",       "name": "Italy Northwest (Milan)",             "lat": 45.46,  "lng": 9.19,    "group": "Europe"},
    {"id": "oci|torino",       "name": "Italy North (Turin)",                 "lat": 45.07,  "lng": 7.69,    "group": "Europe"},
    {"id": "oci|amsterdam",    "name": "Netherlands Northwest (Amsterdam)",   "lat": 52.37,  "lng": 4.90,    "group": "Europe"},
    {"id": "oci|jovanovac",    "name": "Serbia Central (Jovanovac)",          "lat": 44.02,  "lng": 20.99,   "group": "Europe"},
    {"id": "oci|madrid",       "name": "Spain Central (Madrid)",              "lat": 40.42,  "lng": -3.70,   "group": "Europe"},
    {"id": "oci|madrid2",      "name": "Spain Central 2 (Madrid)",            "lat": 40.30,  "lng": -3.55,   "group": "Europe"},
    {"id": "oci|stoccolma",    "name": "Sweden Central (Stockholm)",          "lat": 59.33,  "lng": 18.06,   "group": "Europe"},
    {"id": "oci|zurigo",       "name": "Switzerland North (Zurich)",          "lat": 47.37,  "lng": 8.54,    "group": "Europe"},
    {"id": "oci|londra",       "name": "UK South (London)",                   "lat": 51.51,  "lng": -0.13,   "group": "Europe"},
    {"id": "oci|newport",      "name": "UK West (Newport)",                   "lat": 51.58,  "lng": -3.00,   "group": "Europe"},
    # Africa
    {"id": "oci|kenya",        "name": "Kenya",                               "lat": -1.29,  "lng": 36.82,   "group": "Africa"},
    {"id": "oci|casablanca",   "name": "Morocco West (Casablanca)",           "lat": 33.57,  "lng": -7.59,   "group": "Africa"},
    {"id": "oci|marocco2",     "name": "Morocco 2",                           "lat": 33.00,  "lng": -7.62,   "group": "Africa"},
    {"id": "oci|johannesburg", "name": "South Africa Central (Johannesburg)", "lat": -26.20, "lng": 28.05,   "group": "Africa"},
    # Medio-Oriente
    {"id": "oci|gerusalemme",  "name": "Israel Central (Jerusalem)",          "lat": 31.77,  "lng": 35.21,   "group": "Middle East"},
    {"id": "oci|gedda",        "name": "Saudi Arabia West (Jeddah)",          "lat": 21.49,  "lng": 39.19,   "group": "Middle East"},
    {"id": "oci|riyad",        "name": "Saudi Arabia Central (Riyadh)",       "lat": 24.71,  "lng": 46.68,   "group": "Middle East"},
    {"id": "oci|dubai",        "name": "UAE East (Dubai)",                    "lat": 25.20,  "lng": 55.27,   "group": "Middle East"},
    {"id": "oci|abudhabi",     "name": "UAE Central (Abu Dhabi)",             "lat": 24.45,  "lng": 54.38,   "group": "Middle East"},
    # Asia
    {"id": "oci|mumbai",       "name": "India West (Mumbai)",                 "lat": 19.08,  "lng": 72.88,   "group": "Asia"},
    {"id": "oci|hyderabad",    "name": "India South (Hyderabad)",             "lat": 17.38,  "lng": 78.49,   "group": "Asia"},
    {"id": "oci|batam",        "name": "Indonesia North (Batam)",             "lat": 1.13,   "lng": 104.05,  "group": "Asia"},
    {"id": "oci|tokyo",        "name": "Japan East (Tokyo)",                  "lat": 35.68,  "lng": 139.69,  "group": "Asia"},
    {"id": "oci|osaka",        "name": "Japan Central (Osaka)",               "lat": 34.69,  "lng": 135.50,  "group": "Asia"},
    {"id": "oci|kulai",        "name": "Malaysia West (Kulai)",               "lat": 1.66,   "lng": 103.60,  "group": "Asia"},
    {"id": "oci|singapore",    "name": "Singapore (Singapore)",               "lat": 1.35,   "lng": 103.82,  "group": "Asia"},
    {"id": "oci|singaporew",   "name": "Singapore West (Singapore)",          "lat": 1.33,   "lng": 103.69,  "group": "Asia"},
    {"id": "oci|seul",         "name": "South Korea Central (Seoul)",         "lat": 37.57,  "lng": 126.98,  "group": "Asia"},
    {"id": "oci|chuncheon",    "name": "South Korea North (Chuncheon)",       "lat": 37.88,  "lng": 127.73,  "group": "Asia"},
    # Oceania
    {"id": "oci|sydney",       "name": "Australia East (Sydney)",             "lat": -33.87, "lng": 151.21,  "group": "Oceania"},
    {"id": "oci|melbourne",    "name": "Australia Southeast (Melbourne)",     "lat": -37.81, "lng": 144.96,  "group": "Oceania"},
]


# ----------------------------------------------------------------------------
# Anagrafica delle città, preparata UNA volta all'avvio del processo.
#
# Compreso lo scostamento anti-sovrapposizione: le coppie AWS/OCI quasi
# coincidenti (Milano, Zurigo, Tokyo, ...) dipendono solo dalle coordinate,
# che non cambiano mai, quindi calcolarle a ogni rerun era lavoro sprecato
# (34 x 48 confronti a vuoto). In più ora i pin non si spostano più quando
# si deseleziona la città gemella: restano fermi dove li si è visti.
# ----------------------------------------------------------------------------
def _build_cities():
    cities = ([dict(c, provider="aws") for c in AWS_CITIES] +
              [dict(c, provider="oci") for c in OCI_CITIES])

    shift = {}
    for a in cities:
        if a["provider"] != "aws":
            continue
        for o in cities:
            if o["provider"] != "oci":
                continue
            if abs(a["lat"] - o["lat"]) < 1.0 and abs(a["lng"] - o["lng"]) < 1.0:
                shift[a["id"]] = 0.7
                shift[o["id"]] = -0.7

    for c in cities:
        c["lng"] += shift.get(c["id"], 0.0)
        c["region"] = c.get("region", "global")
        c["prov_label"] = PROVIDER_LABEL[c["provider"]]
        c["z"] = Z_PRIORITY[c["provider"]]
        c["sub"] = (f"AWS · {c['region']}" if c["provider"] == "aws"
                    else "OCI · global single price")
        c["label"] = f"{c['prov_label']} — {c['name']}"

    cities.sort(key=lambda c: (GROUP_ORDER.index(c["group"]),
                               c["provider"], c["name"]))
    return cities


ALL_CITIES = _build_cities()
CITY_BY_ID = {c["id"]: c for c in ALL_CITIES}
AWS_REGION_NAME = {c["region"]: c["name"] for c in ALL_CITIES
                   if c["provider"] == "aws"}


# ----------------------------------------------------------------------------
# Logica pura (nessuna dipendenza da Streamlit: testabile e riusabile)
# ----------------------------------------------------------------------------
class Row(NamedTuple):
    """Una riga di hpc.csv già ripulita. `prices` sono 8 float: nelle prime
    quattro posizioni i prezzi reali (orario, giornaliero, settimanale,
    mensile), nelle altre quattro i normalizzati, nello stesso ordine."""
    family: str
    processor: str
    prices: tuple


class Offer(NamedTuple):
    """Un'offerta per una città, volume di avvio già incluso nei prezzi."""
    price: float
    n_price: float
    family: str
    processor: str
    arch: str


def fmt_usd(value):
    """$ con decimali adattivi e separatori in stile italiano."""
    if value == 0:
        return "$ 0"
    dec = 0 if value >= 100 else (2 if value >= 1 else (3 if value >= 0.01 else 4))
    s = f"{value:,.{dec}f}"
    return "$ " + s.replace(",", "§").replace(".", ",").replace("§", ".")


def md_usd(value):
    """fmt_usd per il markdown. Due `$` nello stesso paragrafo vengono letti
    come delimitatori di formula LaTeX: il testo in mezzo finirebbe in
    monospace. Con la barra rovesciata il dollaro resta un dollaro."""
    return fmt_usd(value).replace("$", r"\$")


def nearest(options, target):
    """Il valore di `options` più vicino a `target` (a parità, il più basso)."""
    return min(options, key=lambda x: (abs(x - target), x))


def _to_float(value, default=0.0):
    """float tollerante: celle vuote o non numeriche non fanno saltare il run."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_volumes(path, region_alias=None):
    """Un CSV di prezzi dei volumi -> ({(region, size, VPU): (4 prezzi)},
    {(size, VPU): (max IOPS, max MB/s)}). IOPS e throughput non dipendono dalla
    regione (cambia solo il prezzo), quindi la seconda mappa è globale."""
    alias = region_alias or {}
    prices, specs = {}, {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            region = r["region"].strip()
            region = alias.get(region, region)
            size, vpu = int(r["size(GB)"]), int(r["VPU"])
            prices[(region, size, vpu)] = tuple(_to_float(r[c]) for c in VOL_COLS)
            specs[(size, vpu)] = (int(r["max_iops"]),
                                  int(r["max_throughput(MBps)"]))
    return prices, specs


def _load_all(data_dir):
    """Legge hpc.csv, combinations.csv e i due listini dei volumi; costruisce
    indice, mappe delle shape e listino dei dischi. Gira una volta sola per
    processo (vedi load_all): qui si può spendere, a runtime no."""
    data_dir = Path(data_dir)

    with open(data_dir / "combinations.csv", newline="", encoding="utf-8-sig") as f:
        combos = frozenset((int(r["vCPU"]), int(r["ram(GB)"]))
                           for r in csv.DictReader(f))
    vcpus = sorted({v for v, _ in combos})
    rams = sorted({r for _, r in combos})
    rams_for = {v: sorted(r for vv, r in combos if vv == v) for v in vcpus}
    vcpus_for = {r: sorted(v for v, rr in combos if rr == r) for r in rams}

    index = {}
    # In hpc.csv le offerte OCI compaiono una volta per `country` (la region è
    # sempre 'global' e i prezzi sono identici): senza questa deduplica la
    # stessa configurazione si ripeteva 22 volte nelle liste e falsava medie e
    # conteggi. La firma comprende TUTTI i prezzi: due righe uguali di nome ma
    # con importi diversi restano due offerte distinte.
    seen = set()
    with open(data_dir / "hpc.csv", newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key = (r["provider"].strip().lower(),
                   r["region"].strip(),
                   r["architecture"].strip(),
                   int(r["vCPU"]),
                   int(float(r["ram(GB)"])))
            real = tuple(_to_float(r.get(c)) for c in REAL_COLS)
            # Se manca il normalizzato si ripiega sul prezzo reale: una cella
            # vuota letta come 0 metterebbe la riga in testa alla classifica.
            norm = tuple(_to_float(r.get(c), real[i])
                         for i, c in enumerate(NORM_COLS))
            row = Row(r["family"].strip(), r["processor"].strip(), real + norm)
            sig = (key, row)
            if sig in seen:
                continue
            seen.add(sig)
            index.setdefault(key, []).append(row)

    # Le liste diventano tuple: l'indice è di sola lettura e le tuple pesano
    # meno (niente spazio di crescita preallocato).
    index = {k: tuple(v) for k, v in index.items()}

    # Listini dei volumi: AWS per regione (con i nomi estesi riportati a
    # codice), OCI sotto la chiave 'global'. Le chiavi non si sovrappongono.
    volumes, vol_specs = _load_volumes(data_dir / "ebs_gp3_prices.csv",
                                       EBS_REGION_ALIAS)
    oci_volumes, oci_specs = _load_volumes(data_dir / "oci_volume_prices.csv")
    volumes.update(oci_volumes)
    vol_specs.update(oci_specs)

    return {"index": index, "combos": combos, "vcpus": vcpus, "rams": rams,
            "rams_for": rams_for, "vcpus_for": vcpus_for,
            "volumes": volumes, "vol_specs": vol_specs}


def volume_cost(volumes, provider, region, size, vpu, i_price):
    """Costo del volume di avvio per una città: AWS per regione, OCI 'global'
    (stesso prezzo ovunque). Chiave assente -> 0, così un buco nel listino
    non nasconde l'offerta: la mostra solo senza il sovrapprezzo del disco."""
    row = volumes.get((region if provider == "aws" else "global", size, vpu))
    return row[i_price] if row else 0.0


def city_offers(index, provider, region, vcpu, ram, arch_values, i_price,
                vol_cost=0.0):
    """Tutte le offerte per una città/shape, dalla più economica in su.
    `vol_cost` (il volume di avvio scelto) si somma sia al prezzo reale sia a
    quello normalizzato: il disco costa quello che costa, non si normalizza."""
    offers = []
    for arch in arch_values:
        for row in index.get((provider, region, arch, vcpu, ram), ()):
            p = row.prices
            offers.append(Offer(p[i_price] + vol_cost, p[i_price + 4] + vol_cost,
                                row.family, row.processor, arch))
    offers.sort(key=lambda o: (o.price, o.family))
    return offers


def price_stats(offers):
    """(min, media, max) dei prezzi di una lista di offerte."""
    prices = [o.price for o in offers]
    return min(prices), sum(prices) / len(prices), max(prices)


def options_rows(index, volumes, aws_regions, include_oci, arch_values,
                 vcpu, ram, i_price, vol_size, vol_vpu):
    """Righe per la lista 'Opzioni Disponibili': tutte le offerte OCI (globali,
    senza ripetizioni per città) + per AWS l'offerta più economica di OGNI
    family cercata tra tutte le città selezionate (la Region indica dove).
    Entrambi i prezzi comprendono il volume di avvio; la classifica — sia
    l'ordinamento sia lo spareggio per family — segue il prezzo normalizzato,
    che è poi il criterio con cui si confrontano davvero le offerte."""
    rows = []
    if include_oci:
        cost = volume_cost(volumes, "oci", "global", vol_size, vol_vpu, i_price)
        for o in city_offers(index, "oci", "global", vcpu, ram, arch_values,
                             i_price, cost):
            rows.append({"Provider": "OCI", "Region": "global",
                         "Family": o.family, "Architecture": o.arch,
                         "Processor": o.processor,
                         "Price": o.price, "N-Price": o.n_price})

    best_by_family = {}
    for region in aws_regions:
        # L'EBS costa diversamente da regione a regione: il confronto tra
        # città si fa quindi sul totale istanza + disco di quella regione.
        cost = volume_cost(volumes, "aws", region, vol_size, vol_vpu, i_price)
        for o in city_offers(index, "aws", region, vcpu, ram, arch_values,
                             i_price, cost):
            cur = best_by_family.get(o.family)
            if cur is None or (o.n_price, region) < (cur["N-Price"], cur["Region"]):
                best_by_family[o.family] = {
                    "Provider": "AWS", "Region": region, "Family": o.family,
                    "Architecture": o.arch, "Processor": o.processor,
                    "Price": o.price, "N-Price": o.n_price}
    rows += best_by_family.values()

    # Codici AWS -> nomi estesi ("ap-south-1" -> "Asia Pacific (Mumbai)");
    # va fatto DOPO la scelta per family, che spareggia sui codici.
    for r in rows:
        r["Region"] = AWS_REGION_NAME.get(r["Region"], r["Region"])
    rows.sort(key=lambda r: (r["N-Price"], r["Price"], r["Provider"], r["Family"]))
    return rows


def build_payload(data, groups, city_ids, arch_values, vcpu, ram,
                  i_price, suffix, vol_size, vol_vpu):
    """Pin per il globo + statistiche per il pannello. Ogni prezzo comprende
    il volume di avvio scelto (per AWS quello della regione della città).

    Il pin selezionato NON entra qui: dipende dal click, non dai filtri, e
    tenerlo fuori rende il risultato memoizzabile (vedi payload()) e valido
    anche mentre si passa da una città all'altra."""
    index, volumes = data["index"], data["volumes"]
    pins = []

    for c in ALL_CITIES:
        if c["group"] not in groups or c["id"] not in city_ids:
            continue
        vol = volume_cost(volumes, c["provider"], c["region"],
                          vol_size, vol_vpu, i_price)
        offers = city_offers(index, c["provider"], c["region"], vcpu, ram,
                             arch_values, i_price, vol)
        pin = {**c, "offers": offers, "highlight": False}
        if offers:
            mn, avg, mx = price_stats(offers)
            pin.update(available=True, cost=mn,
                       color=PROVIDER_COLOR[c["provider"]],
                       price_label=fmt_usd(mn) + suffix, best=offers[0],
                       t1=f"min {fmt_usd(mn)}{suffix}",
                       t2=f"avg {fmt_usd(avg)}{suffix}",
                       t3=f"max {fmt_usd(mx)}{suffix}")
        else:
            pin.update(available=False, cost=None, color=NA_COLOR,
                       price_label="N/A", best=None,
                       t1="", t2="N/A for this setup", t3="")
        pins.append(pin)

    avail = sorted((p for p in pins if p["available"]),
                   key=lambda p: (p["cost"], p["name"]))
    pins = avail + sorted((p for p in pins if not p["available"]),
                          key=lambda p: p["name"])

    # ---- Classifiche per famiglia di istanza -------------------------------
    # Contenuto della scheda che si apre cliccando il pin. Si prepara qui,
    # dentro la parte memoizzata: il click sul globo è poi tutto lato
    # browser, non fa ripartire lo script e non costa niente al server.
    #
    # Ogni statistica è riferita alla SINGOLA istanza, non alla città: due
    # città si confrontano su m6g contro m6g, non sul rispettivo minimo (che
    # potrebbe essere di due famiglie diverse e quindi incomparabile).
    #
    # Le città OCI valgono UNA voce sola: i prezzi sono globali, identici in
    # tutte e 47, e contarle una per una spingeva ogni città AWS in fondo e
    # faceva risultare #14 una città che è economica esattamente quanto la
    # prima. La voce OCI, se presente, entra in classifica una volta e basta.
    fam = {}   # family -> [(prezzo, dove), ...]
    oci_pin = next((p for p in pins
                    if p["provider"] == "oci" and p["available"]), None)
    if oci_pin:
        for o in oci_pin["offers"]:
            fam.setdefault(o.family, []).append((o.price, "OCI · every city"))
    for p in pins:
        if p["provider"] == "aws" and p["available"]:
            for o in p["offers"]:
                fam.setdefault(o.family, []).append((o.price, p["name"]))

    fam_stats = {}
    for f, lst in fam.items():
        lst.sort()
        # I prezzi ordinati servono per la posizione in classifica: con
        # bisect_left il conto è di quanti sono STRETTAMENTE più economici,
        # quindi a pari prezzo si condivide lo stesso posto invece di
        # dipendere dall'ordine alfabetico.
        fam_stats[f] = ([t[0] for t in lst], lst[0][0], lst[0][1], len(lst))

    for p in avail:
        rows = []
        for o in p["offers"]:
            stat = fam_stats.get(o.family)
            if stat is None:                      # non può accadere: guardia
                rows.append([o.family, o.processor, o.arch,
                             fmt_usd(o.price) + suffix,
                             fmt_usd(o.n_price) + suffix, "", "", "", ""])
                continue
            prices, best, where, n = stat
            rank = bisect_left(prices, o.price) + 1
            # Sovrapprezzo rispetto a dove la STESSA istanza costa meno:
            # prima quanto si paga in più, poi di quanto in percentuale.
            # Senza suffisso: la casella è stretta e il taglio temporale si
            # legge già nel prezzo dell'istanza. La percentuale si omette se
            # il riferimento è gratis, altrimenti sarebbe una divisione per
            # zero (e "+∞%" non direbbe niente di utile).
            over = ""
            if rank > 1:
                diff = o.price - best
                pct = f"+{diff / best * 100:.0f}%" if best > EPS else ""
                over = f"📉+{fmt_usd(diff)} ({pct})"
            rows.append([
                o.family, o.processor, o.arch,
                fmt_usd(o.price) + suffix, fmt_usd(o.n_price) + suffix,
                # Vuoto = questa città è la più economica per questa istanza
                "" if rank == 1 else fmt_usd(best) + suffix,
                "" if rank == 1 else where,
                f"#{rank} of {n}", over,
            ])
        p["rows"] = rows

    # Migliori offerte per provider; per AWS anche gli eventuali pari merito
    aws_avail = [p for p in avail if p["provider"] == "aws"]
    oci_avail = [p for p in avail if p["provider"] == "oci"]
    best_aws_ties, focus = [], ""
    if aws_avail:
        m = aws_avail[0]["cost"]
        best_aws_ties = [p for p in aws_avail if abs(p["cost"] - m) < EPS]
        focus = best_aws_ties[0]["id"]
        for p in best_aws_ties:
            p["highlight"] = True
        # ... e l'OCI più vicina al pin AWS più economico pulsa con lui.
        # Solo fra le OCI DISPONIBILI: una città N/D per la configurazione
        # attiva non va evidenziata (non è una vera alternativa).
        if oci_avail:
            f = best_aws_ties[0]
            nearest_oci = min(oci_avail, key=lambda p: (p["lat"] - f["lat"]) ** 2
                              + (p["lng"] - f["lng"]) ** 2)
            nearest_oci["highlight"] = True

    # Prezzo medio su TUTTE le configurazioni disponibili con i filtri attivi
    # (le offerte OCI, globali, contano una volta sola)
    oci_prices, aws_prices = [], []
    if any(p["provider"] == "oci" for p in pins):
        oci_vol = volume_cost(volumes, "oci", "global", vol_size, vol_vpu, i_price)
        oci_prices = [o.price for o in
                      city_offers(index, "oci", "global", vcpu, ram,
                                  arch_values, i_price, oci_vol)]
    for p in pins:
        if p["provider"] == "aws":
            aws_prices += [o.price for o in p["offers"]]
    all_prices = oci_prices + aws_prices

    stats = {
        "n": len(pins), "n_avail": len(avail),
        "min": avail[0]["cost"] if avail else 0.0,
        "max": avail[-1]["cost"] if avail else 0.0,
        "avg_all": (sum(all_prices) / len(all_prices)) if all_prices else None,
        "n_configs": len(all_prices),
        "avg_oci": (sum(oci_prices) / len(oci_prices)) if oci_prices else None,
        "n_oci": len(oci_prices),
        "avg_aws": (sum(aws_prices) / len(aws_prices)) if aws_prices else None,
        "n_aws": len(aws_prices),
        "best_oci": oci_avail[0] if oci_avail else None,
        "best_aws": best_aws_ties[0] if best_aws_ties else None,
        "best_aws_ties": best_aws_ties,
        "focus": focus,
        "aws_regions": tuple(dict.fromkeys(p["region"] for p in pins
                                           if p["provider"] == "aws")),
        "has_oci": any(p["provider"] == "oci" for p in pins),
    }
    return pins, stats


# ----------------------------------------------------------------------------
# Intro a tutto schermo
# ----------------------------------------------------------------------------
INTRO_HTML = """<style>
  html, body { margin: 0; height: 100%; background: #000; overflow: hidden; }
  video { width: 100%; height: 100%; object-fit: cover; background: #000; }
  .skip {
    position: fixed; bottom: 18px; right: 22px;
    color: rgba(255, 255, 255, .75);
    font: 14px -apple-system, "Segoe UI", Roboto, sans-serif;
  }
</style>

<video id="intro" autoplay muted playsinline src="data:video/mp4;base64,__B64__"></video>
<div class="skip">click to skip &#9656;</div>

<script>
  // L'iframe del componente si promuove da solo a livello fisso sopra la
  // pagina (stessa origine: possiamo ridimensionarci).
  const frame = window.frameElement;
  const video = document.getElementById('intro');
  let closed = false;

  if (frame) {
    Object.assign(frame.style, {
      position: 'fixed', inset: '0', width: '100vw', height: '100vh',
      zIndex: '999999', background: '#000', border: '0'
    });
  }

  function close() {
    if (closed || !frame) return;
    closed = true;
    video.pause();
    // Il tag <video> va svuotato: senza, i byte del filmato restano
    // agganciati all'iframe nascosto per tutta la sessione.
    video.removeAttribute('src');
    video.load();
    frame.style.transition = 'opacity .45s ease';
    frame.style.opacity = '0';
    setTimeout(function () {
      // L'iframe si NASCONDE, non si rimuove. È un nodo creato da React
      // (Streamlit): toglierlo dal DOM alle sue spalle fa fallire il
      // successivo smontaggio con "NotFoundError: Failed to execute
      // 'removeChild' on 'Node'". Svuotato il video, un nodo nascosto di
      // 0x0 non costa niente.
      Object.assign(frame.style, {
        display: 'none', position: 'static', width: '0', height: '0',
        pointerEvents: 'none'
      });
    }, 500);
  }

  video.addEventListener('ended', close);
  video.addEventListener('error', close);
  document.addEventListener('click', close);   // click = salta l'intro
  setTimeout(close, 12000);                    // rete di sicurezza
  video.play().catch(close);   // se anche l'autoplay muto fallisse, via tutto
</script>"""


def strip_id3(data):
    """Rimuove il tag ID3v2 in testa e l'ID3v1 in coda a un file MP3: i
    frame audio nudi si possono concatenare e i player li leggono in fila."""
    if data[:3] == b"ID3" and len(data) > 10:
        flags = data[5]
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) \
             | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        off = 10 + size + (10 if flags & 0x10 else 0)
        data = data[off:] if off < len(data) else b""
    if len(data) >= 128 and data[-128:-125] == b"TAG":
        data = data[:-128]
    return data


def concat_mp3(paths):
    """Unisce più MP3 in un'unica traccia: riprodotta con loop, suona i
    brani in sequenza e poi ripete la playlist."""
    return b"".join(strip_id3(Path(p).read_bytes()) for p in paths)


# ============================================================================
# UI (Streamlit)
# ============================================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = BASE_DIR / "audio"
VIDEO_DIR = BASE_DIR / "video"
GLOBE_DIR = BASE_DIR / "globe_component"

st.set_page_config(
    page_title=" · 🟠 AWS ⚔️ OCI 🔴 ",
    page_icon=Image.open(BASE_DIR / "favicon.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

# Un solo blocco di stile, iniettato una volta per rerun. Regole raggruppate
# per zona della pagina; niente più selettori :has()/:focus-within per
# pilotare finestre (ci pensano st.expander e st.dialog).
st.markdown("""<style>
/* --- Sidebar: City List ------------------------------------------------- */
/* Le "pillole" delle città selezionate sono nascoste (con 80 città la barra
   diventerebbe altissima): il conteggio lo mette lo stile dinamico più
   sotto, l'elenco completo sta nell'expander. */
section[data-testid='stSidebar'] div[data-testid='stMultiSelect'] span[data-baseweb='tag'] { display: none; }
section[data-testid='stSidebar'] div[data-testid='stMultiSelect'] div[data-baseweb='select'] { position: relative; }
section[data-testid='stSidebar'] div[data-testid='stMultiSelect'] div[data-baseweb='select']:focus-within::before { content: "" !important; }
/* Quando sono già state scelte tutte le città il menu resta vuoto
   ("No results"): meglio non aprirlo affatto. */
div[data-baseweb='popover']:has([data-testid='stSelectboxVirtualDropdownEmpty']) { display: none !important; }
.st-key-city_list [data-testid='stVerticalBlock'] { gap: .1rem; }
.st-key-city_list [data-testid='stHorizontalBlock'] { gap: .2rem; }
.st-key-city_list .city-row {
  font-size: .84rem; color: #cfd8ea; line-height: 1.7;
  display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.st-key-city_list div[data-testid='stButton'] button {
  background: transparent !important; border: none !important;
  color: #64748b !important; padding: 0 .35rem !important;
  min-height: 1.5rem !important; height: 1.5rem;
}
.st-key-city_list div[data-testid='stButton'] button:hover { color: #f87171 !important; }
section[data-testid='stSidebar'] [data-testid='stAudio'] { display: none; }

/* --- Sidebar: velocità del disco ---------------------------------------- */
/* Quattro pulsanti su una riga sola anche nella sidebar stretta. */
.st-key-vol_speed [data-baseweb='button-group'] { width: 100%; }
.st-key-vol_speed [data-baseweb='button-group'] > div { flex: 1 1 0; }
.st-key-vol_speed button { padding-left: .35rem !important; padding-right: .35rem !important; width: 100%; }
.st-key-vol_speed button p {
  font-size: .74rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* --- Bottone "Available Options": verde in ogni tema --------------------- */
.st-key-btn_options button {
  background-color: #0f9163 !important; border-color: #12a06e !important;
  color: #eafff5 !important; font-weight: 600;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .14);
  transition: background-color .18s ease, border-color .18s ease;
}
.st-key-btn_options button:hover, .st-key-btn_options button:focus {
  background-color: #14a373 !important; border-color: #1cb782 !important;
  color: #ffffff !important;
}

/* --- Colonna KPI --------------------------------------------------------- */
.st-key-kpi_panel [data-testid='stMetricLabel'] p { font-size: 1.06rem; font-weight: 600; }
.st-key-kpi_panel [data-testid='stMetricValue'] { font-size: 2.15rem; }
.st-key-kpi_panel [data-testid='stMetricDelta'] { font-size: 1rem; }
.st-key-kpi_panel [data-testid='stCaptionContainer'] p {
  line-height: 1.5; font-size: .8rem;
  /* La colonna è stretta: senza questo le medie andrebbero a capo. */
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
/* Schede KPI: superficie appena più chiara del fondo, riflesso interno sul
   bordo alto (inset) e ombra portata sotto. */
.st-key-kpi_gap, .st-key-kpi_oci, .st-key-kpi_aws {
  background: linear-gradient(158deg, rgba(255, 255, 255, .055), rgba(255, 255, 255, .012) 62%);
  border: 1px solid rgba(255, 255, 255, .10);
  border-radius: 14px;
  padding: 1rem 1.15rem 1.05rem;
  flex: 1 1 auto;        /* si spartiscono l'avanzo fino a chiudere in fondo */
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .13), 0 10px 22px rgba(0, 0, 0, .45);
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.st-key-kpi_gap:hover, .st-key-kpi_oci:hover, .st-key-kpi_aws:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, .18);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .16), 0 16px 30px rgba(0, 0, 0, .55);
}
/* `min-height` e non `height`: con molte città a pari merito il contenuto
   può crescere, e deve poterlo fare senza essere tagliato. */
[data-testid='stVerticalBlock']:has(> .st-key-kpi_gap, > .st-key-kpi_oci, > .st-key-kpi_aws) {
  min-height: 600px; gap: .6rem;
}
.st-key-kpi_gap [data-testid='stVerticalBlock'],
.st-key-kpi_oci [data-testid='stVerticalBlock'],
.st-key-kpi_aws [data-testid='stVerticalBlock'] { gap: .35rem; }

/* --- Testata ------------------------------------------------------------- */
/* Di serie il contenuto parte a 6rem dal bordo e il globo finiva sotto la
   piega. La barra di Streamlit resta al suo posto, solo trasparente. */
div[data-testid='stMainBlockContainer'], section[data-testid='stMain'] .block-container {
  padding-top: 2.6rem !important;
}
header[data-testid='stHeader'] { background: transparent; }
section[data-testid='stMain'] h1 {
  padding-top: 0 !important; padding-bottom: .35rem !important; margin-top: 0 !important;
}
section[data-testid='stMain'] [data-testid='stCaptionContainer'] { margin-bottom: .1rem; }
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Cache. Regola pratica:
#   @st.cache_resource -> oggetti grossi e di sola lettura (l'indice dei
#       prezzi, la playlist): restituisce SEMPRE lo stesso oggetto.
#   @st.cache_data     -> risultati piccoli e derivati: restituisce una copia,
#       quindi va bene solo dove la copia costa meno del ricalcolo.
# L'indice con cache_data veniva ri-deserializzato a ogni rerun: era la voce
# di costo più pesante dell'intera app.
# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def load_all(data_dir: str):
    return _load_all(data_dir)


@st.cache_resource(show_spinner=False)
def load_intro_html(signature):
    """HTML dell'overlay con il video incorporato in base64; la firma
    (nome, size, mtime) lo rigenera solo quando il file cambia."""
    b64 = base64.b64encode((VIDEO_DIR / signature[0]).read_bytes()).decode("ascii")
    return INTRO_HTML.replace("__B64__", b64)


@st.cache_resource(show_spinner=False)
def load_playlist(signature):
    """Playlist unica in memoria; la firma (nome, size, mtime) la invalida
    solo quando i file cambiano, così l'audio resta identico tra i rerun
    e la riproduzione non si interrompe usando i filtri."""
    return concat_mp3([AUDIO_DIR / name for name, _, _ in signature])


@st.cache_data(show_spinner=False, max_entries=48)
def payload(groups, city_ids, arch_values, vcpu, ram, i_price, suffix,
            vol_size, vol_vpu):
    """build_payload memoizzato sui filtri attivi. Gli argomenti sono tuple di
    valori immutabili (le chiavi di cache più economiche da calcolare), quindi
    i rerun che non toccano i filtri — rotazione, musica, apertura di una
    finestra, click su un pin — non ricalcolano niente."""
    return build_payload(load_all(str(DATA_DIR)), frozenset(groups),
                         frozenset(city_ids), arch_values,
                         vcpu, ram, i_price, suffix, vol_size, vol_vpu)


@st.cache_data(show_spinner=False, max_entries=16)
def options_table(aws_regions, include_oci, arch_values, vcpu, ram, i_price,
                  vol_size, vol_vpu):
    """Righe della tabella 'Available Options', già in DataFrame: si ricostruisce
    solo quando cambiano i filtri, non a ogni apertura del pannello."""
    data = load_all(str(DATA_DIR))
    rows = options_rows(data["index"], data["volumes"], aws_regions, include_oci,
                        arch_values, vcpu, ram, i_price, vol_size, vol_vpu)
    return (pd.DataFrame(rows), max((r["N-Price"] for r in rows), default=0.0)) \
        if rows else (None, 0.0)


DATA = load_all(str(DATA_DIR))
COMBOS = DATA["combos"]

ss = st.session_state
ss.setdefault("show_options", False)
ss.setdefault("scroll_opts", False)
ss.setdefault("regions_sel", list(GROUP_ORDER))
ss.setdefault("prev_groups", frozenset(GROUP_ORDER))
ss.setdefault("vcpu_sel", 4 if (4, 16) in COMBOS else DATA["vcpus"][0])
ss.setdefault("ram_sel", 16 if (4, 16) in COMBOS else DATA["rams_for"][DATA["vcpus"][0]][0])
ss.setdefault("vol_size", VOL_SIZE_DEFAULT)        # volume di avvio: 30 GB...
ss.setdefault("vol_speed", VOL_SPEED_DEFAULT)      # ... Balanced 🐱
ss.setdefault("vol_speed_prev", VOL_SPEED_DEFAULT)


def _sync_from_vcpu():
    if (ss.vcpu_sel, ss.ram_sel) not in COMBOS:
        ss.ram_sel = nearest(DATA["rams_for"][ss.vcpu_sel], ss.ram_sel)


def _sync_from_ram():
    if (ss.vcpu_sel, ss.ram_sel) not in COMBOS:
        ss.vcpu_sel = nearest(DATA["vcpus_for"][ss.ram_sel], ss.vcpu_sel)


def _lock_speed():
    """I 'pulsanti' della velocità sono a scelta singola obbligatoria: un
    secondo click sulla voce attiva la deselezionerebbe (comportamento di
    serie di st.segmented_control), qui invece la si tiene ferma."""
    if ss.vol_speed is None:
        ss.vol_speed = ss.vol_speed_prev
    ss.vol_speed_prev = ss.vol_speed


def _clear_cities():
    """Svuota solo la City List: le Regions restano accese, così la tendina
    continua a proporre le città di quelle zone e se ne possono riscegliere
    alcune senza dover riattivare i bottoni delle regioni."""
    ss.city_sel = []


def _remove_city(cid):
    ss.city_sel = [i for i in ss.city_sel if i != cid]


def _toggle_options():
    ss.show_options = not ss.show_options
    ss.scroll_opts = ss.show_options   # all'apertura, scorri fino alla tabella


# --- Intro video a tutto schermo (una volta per sessione) --------------------
# La pagina si carica normalmente sotto l'overlay, che sparisce a fine video
# (o al click). Al refresh del browser l'intro riparte.
ss.setdefault("intro_done", False)
if not ss.intro_done:
    ss.intro_done = True
    intro_files = sorted(VIDEO_DIR.glob("*.mp4")) if VIDEO_DIR.is_dir() else []
    if intro_files:
        p = intro_files[0]
        stat = p.stat()
        components.html(
            load_intro_html((p.name, stat.st_size, int(stat.st_mtime))), height=0)


# --- Pannello laterale (dall'alto verso il basso, come da specifica) ---------
with st.sidebar:
    st.markdown("#### Regions")
    groups = st.pills("Regions", GROUP_ORDER, selection_mode="multi",
                      key="regions_sel", label_visibility="collapsed") or []
    groups_set = frozenset(groups)

    # City List sincronizzata con Regions: le opzioni sono le città delle
    # zone selezionate; una zona appena riattivata riporta dentro le sue
    # città; una zona rimossa le toglie da opzioni e selezione.
    city_options = [c["id"] for c in ALL_CITIES if c["group"] in groups_set]
    if "city_sel" not in ss:
        ss.city_sel = city_options[:]                      # default: tutte
    else:
        added = groups_set - ss.prev_groups
        keep = set(ss.city_sel)
        keep.update(i for i in city_options if CITY_BY_ID[i]["group"] in added)
        ss.city_sel = [i for i in city_options if i in keep]
    ss.prev_groups = groups_set

    st.markdown("#### City List")
    st.multiselect("City List", options=city_options, key="city_sel",
                   format_func=lambda cid: CITY_BY_ID[cid]["label"],
                   label_visibility="collapsed",
                   placeholder="Search or select a city…")

    # La tendina elenca solo le città ancora da aggiungere; quelle già scelte
    # vivono qui. L'expander è nativo: tiene da solo lo stato aperto/chiuso
    # tra un rerun e l'altro, quindi si possono togliere più città di fila
    # senza che la finestra si richiuda.
    if ss.city_sel:
        with st.expander(f"✅ Selected — {len(ss.city_sel)} / {len(city_options)}"):
            with st.container(key="city_list", height=210, border=False):
                for cid in ss.city_sel:
                    label = CITY_BY_ID[cid]["label"]
                    col_name, col_x = st.columns([0.85, 0.15],
                                                 vertical_alignment="center")
                    col_name.markdown(
                        f"<span class='city-row' title='{label}'>{label}</span>",
                        unsafe_allow_html=True)
                    col_x.button("✕", key=f"rm_{cid}",
                                 on_click=_remove_city, args=(cid,))
            st.button("Clear all ☄️", key="clear_all", on_click=_clear_cities,
                      use_container_width=True)

    st.markdown("#### Architecture")
    a1, a2, a3 = st.columns(3)
    arch_checked = (a1.checkbox("ARM", value=True),
                    a2.checkbox("x86 AMD", value=True),
                    a3.checkbox("x86 Intel", value=True))
    arch_values = tuple(val for (_, val), on in zip(ARCH_OPTIONS, arch_checked) if on)

    st.markdown("#### Shape")
    st.select_slider("Number of vCPU", options=DATA["vcpus"],
                     key="vcpu_sel", on_change=_sync_from_vcpu)
    st.select_slider("GB of RAM", options=DATA["rams"],
                     key="ram_sel", on_change=_sync_from_ram)
    if (ss.vcpu_sel, ss.ram_sel) not in COMBOS:   # rete di sicurezza
        ss.ram_sel = nearest(DATA["rams_for"][ss.vcpu_sel], ss.ram_sel)

    st.markdown("#### Volume")
    st.selectbox("Boot volume size", list(VOLUME_SIZES), key="vol_size")
    st.segmented_control("Disk speed", list(VOLUME_SPEED), key="vol_speed",
                         on_change=_lock_speed, label_visibility="collapsed")
    vol_size = VOLUME_SIZES[ss.vol_size]
    vol_vpu = VOLUME_SPEED[ss.vol_speed or VOL_SPEED_DEFAULT]
    v_iops, v_mbps = DATA["vol_specs"].get((vol_size, vol_vpu), (0, 0))
    st.caption(f"   · up to {v_iops:,} IOPS · {v_mbps} MB/s".replace(",", "."))

    st.markdown("#### Time-Based Pricing")
    gran = st.selectbox("Time-Based Pricing", list(GRANULARITY),
                        index=list(GRANULARITY).index("Weekly"),
                        label_visibility="collapsed")

    st.divider()
    rotate = st.toggle("Globe rotation", value=True)
    music = st.toggle("Music", value=False)
    if music:
        tracks = sorted(AUDIO_DIR.glob("*.mp3")) if AUDIO_DIR.is_dir() else []
        if tracks:
            signature = tuple((p.name, p.stat().st_size, int(p.stat().st_mtime))
                              for p in tracks)
            # Player nascosto via CSS: comanda tutto la spunta qui sopra
            st.audio(load_playlist(signature), format="audio/mpeg",
                     loop=True, autoplay=True)
        else:
            st.caption("No .mp3 found: drop one into the project's "
                       "`audio/` folder.")

i_price, suffix, num_fmt = GRANULARITY[gran]
vcpu, ram = ss.vcpu_sel, ss.ram_sel
vol_note = f"{ss.vol_size} · {ss.vol_speed or VOL_SPEED_DEFAULT}"
arch_note = " + ".join(lbl for lbl, val in ARCH_OPTIONS if val in arch_values) or "none"

# "N città selezionate su M" DENTRO la barra della City List (sparisce mentre
# si digita nella ricerca; con 0 selezioni resta il placeholder). È l'unica
# regola CSS che dipende dallo stato, quindi vive qui e non nel blocco fisso.
if ss.city_sel:
    st.markdown(
        "<style>section[data-testid='stSidebar'] div[data-testid='stMultiSelect'] "
        "div[data-baseweb='select']::before {"
        f' content: "{len(ss.city_sel)} / {len(city_options)} cities";'
        " position: absolute; left: 12px; top: 50%; transform: translateY(-50%);"
        " color: #e6edf3; font-size: .88rem; pointer-events: none; z-index: 1;"
        " white-space: nowrap; max-width: 76%; overflow: hidden;"
        " text-overflow: ellipsis; }</style>",
        unsafe_allow_html=True,
    )

pins, stats = payload(tuple(sorted(groups_set)), tuple(ss.city_sel), arch_values,
                      vcpu, ram, i_price, suffix, vol_size, vol_vpu)

# --- Layout ------------------------------------------------------------------
st.title("Virtual Machines, Around the World 🔭")
st.caption(
    f" · {vcpu} vCPU · {ram} GB RAM · [ {arch_note} ] · "
    f"{len(ss.city_sel)}/{len(city_options)} cities "
    f"in {len(groups)} of {len(GROUP_ORDER)} regions. · {gran} pricing (updated July 2026)"
)

col_globe, col_stats = st.columns([2.5, 1], gap="large")

with col_globe:
    if not groups:
        st.warning("Select at least one geographic area in the **Regions** section.")
    elif not ss.city_sel:
        st.warning("Select at least one city in the **City List** section.")
    if not arch_values:
        st.warning("Select at least one architecture in the **Architecture** section.")

    # Il nome del componente finisce nell'URL da cui il browser scarica
    # index.html. Cambiandolo si cambia l'URL, quindi una copia vecchia
    # rimasta in cache non può più essere riutilizzata: è il modo più
    # sicuro per essere certi di eseguire davvero il file aggiornato.
    hpc_globe = components.declare_component("hpc_globe_v12", path=str(GLOBE_DIR))

    # Payload del globo. Contiene anche il contenuto della scheda che si apre
    # al click (`head` e `rows`), così il popup è tutto lato browser: cliccare
    # un pin non manda niente al server e non fa ripartire lo script.
    # L'ordine (N/D, poi OCI, poi AWS) rafforza la priorità di sovrapposizione
    # insieme allo z-index.
    #
    # Le offerte OCI sono le stesse in tutte e 47 le città (region 'global'):
    # si spediscono una volta sola in `shared` e i pin ci puntano con `ref`.
    # Sulla tabella, che è la parte grossa del payload, è più della metà in meno.
    oci_rows = next((p["rows"] for p in pins
                     if p["provider"] == "oci" and p["available"]), [])
    pin_args = sorted(
        ({"id": p["id"], "name": p["name"], "sub": p["sub"],
          "lat": p["lat"], "lng": p["lng"], "color": p["color"],
          "highlight": p["highlight"], "provider": p["provider"], "z": p["z"],
          "t1": p["t1"], "t2": p["t2"], "t3": p["t3"],
          "avail": p["available"],
          "ref": "oci" if p["provider"] == "oci" else "",
          "rows": () if p["provider"] == "oci" else p.get("rows", ())}
         for p in pins),
        key=lambda p: p["z"],
    )
    hpc_globe(pins=pin_args, shared={"oci": oci_rows}, rotate=rotate,
              focus=stats["focus"], key="globe")

    # --- Bottone verde, al centro sotto il globo -----------------------------
    b1, b2, b3 = st.columns([1, 1.2, 1])
    b2.button("Available Options", key="btn_options", type="primary",
              use_container_width=True, on_click=_toggle_options)

with col_stats, st.container(key="kpi_panel"):
    if stats["avg_oci"] is not None and stats["avg_aws"] is not None:
        d = stats["avg_oci"] - stats["avg_aws"]
        with st.container(key="kpi_gap"):
            if abs(d) < EPS:
                st.metric("​📈​ Average Price Gap", fmt_usd(0) + suffix,
                          delta="Even", delta_color="off")
            else:
                winner = "OCI" if d < 0 else "AWS"
                st.metric("​📈​ Average Price Gap", fmt_usd(abs(d)) + suffix,
                          delta=f"in favor of {winner}", delta_color="green")
            # Righe della stessa sezione in un unico caption (a capo con "  \n"):
            # elementi separati prenderebbero il gap pieno del blocco verticale.
            st.caption(f"   · OCI Avg: {md_usd(stats['avg_oci'])}{suffix} "
                       f"({stats['n_oci']} opts)  \n"
                       f"   · AWS Avg: {md_usd(stats['avg_aws'])}{suffix} "
                       f"({stats['n_aws']} opts)")

    if stats["best_oci"]:
        with st.container(key="kpi_oci"):
            st.metric("​​🔴​ Cheapest OCI option", stats["best_oci"]["price_label"])
            st.caption("   · Global single price")

    if stats["best_aws"]:
        with st.container(key="kpi_aws"):
            st.metric("​🟠​ Cheapest AWS option", stats["best_aws"]["price_label"])
            st.caption("  \n".join(f"   · {p['name']}"
                                   for p in stats["best_aws_ties"]))

# --- Opzioni Disponibili (rivelate dal bottone verde) ------------------------
if ss.show_options:
    st.divider()
    st.markdown("<div id='opzioni-anchor'></div>", unsafe_allow_html=True)
    st.subheader("Available Options")
    st.caption(
        f"   · Setup: {vcpu} vCPU · {ram} GB RAM · ( {arch_note} )"
        f"   · Prices include the boot volume ({vol_note});"
    )

    df, n_max = options_table(stats["aws_regions"], stats["has_oci"], arch_values,
                              vcpu, ram, i_price, vol_size, vol_vpu)
    if df is not None:
        st.dataframe(
            df, hide_index=True, use_container_width=True,
            column_config={
                # Prezzo reale: numero secco. La barra sta sul normalizzato,
                # che è la colonna su cui la tabella è ordinata.
                "Price": st.column_config.NumberColumn(
                    f"Price ({suffix.lstrip('/')})", format=num_fmt),
                "N-Price": st.column_config.ProgressColumn(
                    f"N-Price ({suffix.lstrip('/')})", format=num_fmt,
                    min_value=0.0, max_value=float(n_max or 1.0)),
            },
        )
        st.caption(
            "\n   · OCI: same offers available across all cities\n"
            "\n   · AWS: cheapest offer per family among selected cities\n"
            "\n   · Sorted by normalized price (N-Price)"
        )
    else:
        st.caption("No options available with the current filters.")

    # All'apertura, scorri dolcemente fino alla tabella (una volta sola)
    if ss.scroll_opts:
        ss.scroll_opts = False
        components.html(
            """<script>
              setTimeout(() => {
                const el = window.parent.document.getElementById('opzioni-anchor');
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }, 250);
            </script>""",
            height=0,
        )
