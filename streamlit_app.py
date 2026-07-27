"""
HPC su globo — AWS vs OCI con dati reali
----------------------------------------
Streamlit + componente bidirezionale (globe_component/index.html, Globe.gl).

Dati: data/hpc.csv (prezzi reali, inclusi quelli a 0: contano come tutti gli
altri) e data/combinations.csv (shape ammesse).
- provider: 'aws' | 'oci' — pin arancione chiaro (AWS) / rosso scuro (OCI)
- region:   codici AWS (us-east-1, ...) | 'global' per OCI (stesso prezzo
            in tutte le città OCI)
- architecture: ARM | x86(AMD) | x86(Intel)
- prezzi: price($/h), daily_price, weekly_price, monthly_price

Musica di sottofondo: metti un .mp3 nella cartella audio/ e attiva il
pulsante "Musica" nella sidebar (se ci sono più file, si usa il primo in
ordine alfabetico).
"""

import base64
import csv
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image 

PROVIDER_COLOR = {"oci": "#a4161a", "aws": "#ffa94d"}   # rosso scuro / arancione chiaro
PROVIDER_LABEL = {"oci": "OCI", "aws": "AWS"}
NA_COLOR = "#6b7280"                                     # grigio: non disponibile
Z_PRIORITY = {"aws": 30, "oci": 20, "nd": 10}            # sovrapposizione pin
EPS = 1e-9

GROUP_ORDER = ["Europa", "Nord America", "Asia", "Medio-Oriente",
               "Sud America", "Africa", "Oceania"]

ARCH_OPTIONS = [("ARM", "ARM"), ("x86 AMD", "x86(AMD)"), ("x86 Intel", "x86(Intel)")]

GRANULARITY = {  # etichetta -> (colonna csv, suffisso, formato numerico)
    "Hourly":         ("price($/h)",    "/h",         "$ %.3f"),
    "Daily":          ("daily_price",   "/day",    "$ %.2f"),
    "Weekly":         ("weekly_price",  "/week", "$ %.1f"),
    "Monthly (730h)": ("monthly_price", "/month",      "$ %.0f"),
}

# ----------------------------------------------------------------------------
# Città. AWS: da aws_cities.txt (raggruppamento incluso). OCI: da
# oci_cities.txt; coordinate approssimate della località indicata (per
# "Kenya" si usa Nairobi, per "Marocco 2" un punto presso Settat; le coppie
# di sedi omonime hanno un piccolo scostamento per restare distinguibili).
# ----------------------------------------------------------------------------
AWS_CITIES = [
    # Nord America
    {"id": "aws|us-east-1",      "region": "us-east-1",      "name": "US East (N. Virginia)",      "lat": 38.95,  "lng": -77.45,  "group": "Nord America"},
    {"id": "aws|us-east-2",      "region": "us-east-2",      "name": "US East (Ohio)",             "lat": 39.96,  "lng": -83.00,  "group": "Nord America"},
    {"id": "aws|us-west-1",      "region": "us-west-1",      "name": "US West (N. California)",    "lat": 37.35,  "lng": -121.96, "group": "Nord America"},
    {"id": "aws|us-west-2",      "region": "us-west-2",      "name": "US West (Oregon)",           "lat": 45.85,  "lng": -119.70, "group": "Nord America"},
    {"id": "aws|ca-central-1",   "region": "ca-central-1",   "name": "Canada (Central)",           "lat": 45.50,  "lng": -73.57,  "group": "Nord America"},
    {"id": "aws|ca-west-1",      "region": "ca-west-1",      "name": "Canada West (Calgary)",      "lat": 51.05,  "lng": -114.07, "group": "Nord America"},
    {"id": "aws|mx-central-1",   "region": "mx-central-1",   "name": "Mexico (Central)",           "lat": 20.59,  "lng": -100.39, "group": "Nord America"},
    # Sud America
    {"id": "aws|sa-east-1",      "region": "sa-east-1",      "name": "South America (São Paulo)",  "lat": -23.55, "lng": -46.63,  "group": "Sud America"},
    # Europa
    {"id": "aws|eu-central-1",   "region": "eu-central-1",   "name": "Europe (Frankfurt)",         "lat": 50.11,  "lng": 8.68,    "group": "Europa"},
    {"id": "aws|eu-central-2",   "region": "eu-central-2",   "name": "Europe (Zurich)",            "lat": 47.37,  "lng": 8.54,    "group": "Europa"},
    {"id": "aws|eu-west-1",      "region": "eu-west-1",      "name": "Europe (Ireland)",           "lat": 53.35,  "lng": -6.26,   "group": "Europa"},
    {"id": "aws|eu-west-2",      "region": "eu-west-2",      "name": "Europe (London)",            "lat": 51.51,  "lng": -0.13,   "group": "Europa"},
    {"id": "aws|eu-west-3",      "region": "eu-west-3",      "name": "Europe (Paris)",             "lat": 48.86,  "lng": 2.35,    "group": "Europa"},
    {"id": "aws|eu-south-1",     "region": "eu-south-1",     "name": "Europe (Milan)",             "lat": 45.46,  "lng": 9.19,    "group": "Europa"},
    {"id": "aws|eu-south-2",     "region": "eu-south-2",     "name": "Europe (Spain)",             "lat": 41.65,  "lng": -0.88,   "group": "Europa"},
    {"id": "aws|eu-north-1",     "region": "eu-north-1",     "name": "Europe (Stockholm)",         "lat": 59.33,  "lng": 18.06,   "group": "Europa"},
    # Africa
    {"id": "aws|af-south-1",     "region": "af-south-1",     "name": "Africa (Cape Town)",         "lat": -33.92, "lng": 18.42,   "group": "Africa"},
    # Medio-Oriente
    {"id": "aws|il-central-1",   "region": "il-central-1",   "name": "Israel (Tel Aviv)",          "lat": 32.08,  "lng": 34.78,   "group": "Medio-Oriente"},
    {"id": "aws|me-south-1",     "region": "me-south-1",     "name": "Middle East (Bahrain)",      "lat": 26.23,  "lng": 50.59,   "group": "Medio-Oriente"},
    {"id": "aws|me-central-1",   "region": "me-central-1",   "name": "Middle East (UAE)",          "lat": 25.20,  "lng": 55.27,   "group": "Medio-Oriente"},
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
    {"id": "oci|ashburn",    "name": "Stati Uniti orientali (Ashburn)",         "lat": 39.04,  "lng": -77.49,  "group": "Nord America"},
    {"id": "oci|chicago",    "name": "Midwest degli Stati Uniti (Chicago)",     "lat": 41.88,  "lng": -87.63,  "group": "Nord America"},
    {"id": "oci|phoenix",    "name": "Stati Uniti occidentali (Phoenix)",       "lat": 33.45,  "lng": -112.07, "group": "Nord America"},
    {"id": "oci|sanjose",    "name": "Stati Uniti occidentali (San Jose)",      "lat": 37.34,  "lng": -121.89, "group": "Nord America"},
    {"id": "oci|montreal",   "name": "Canada sud-orientale (Montreal)",         "lat": 45.50,  "lng": -73.57,  "group": "Nord America"},
    {"id": "oci|toronto",    "name": "Canada sud-orientale (Toronto)",          "lat": 43.65,  "lng": -79.38,  "group": "Nord America"},
    {"id": "oci|queretaro",  "name": "Messico centrale (Querétaro)",            "lat": 20.59,  "lng": -100.39, "group": "Nord America"},
    {"id": "oci|monterrey",  "name": "Messico nord-orientale (Monterrey)",      "lat": 25.67,  "lng": -100.31, "group": "Nord America"},
    # Sud America
    {"id": "oci|sanpaolo",   "name": "Brasile orientale (San Paolo)",           "lat": -23.55, "lng": -46.63,  "group": "Sud America"},
    {"id": "oci|vinhedo",    "name": "Brasile sud-orientale (Vinhedo)",         "lat": -23.03, "lng": -46.98,  "group": "Sud America"},
    {"id": "oci|santiago",   "name": "Cile centrale (Santiago)",                "lat": -33.45, "lng": -70.67,  "group": "Sud America"},
    {"id": "oci|valparaiso", "name": "Cile occidentale (Valparaiso)",           "lat": -33.05, "lng": -71.62,  "group": "Sud America"},
    {"id": "oci|bogota",     "name": "Colombia centrale (Bogotà)",              "lat": 4.71,   "lng": -74.07,  "group": "Sud America"},
    # Europa
    {"id": "oci|parigi",     "name": "Francia centrale (Parigi)",               "lat": 48.86,  "lng": 2.35,    "group": "Europa"},
    {"id": "oci|marsiglia",  "name": "Francia meridionale (Marsiglia)",         "lat": 43.30,  "lng": 5.37,    "group": "Europa"},
    {"id": "oci|francoforte","name": "Germania centrale (Francoforte)",         "lat": 50.11,  "lng": 8.68,    "group": "Europa"},
    {"id": "oci|milano",     "name": "Italia nord-occidentale (Milano)",        "lat": 45.46,  "lng": 9.19,    "group": "Europa"},
    {"id": "oci|torino",     "name": "Italia settentrionale (Torino)",          "lat": 45.07,  "lng": 7.69,    "group": "Europa"},
    {"id": "oci|amsterdam",  "name": "Paesi Bassi nord-occidentali (Amsterdam)","lat": 52.37,  "lng": 4.90,    "group": "Europa"},
    {"id": "oci|jovanovac",  "name": "Serbia Centrale (Jovanovac)",             "lat": 44.02,  "lng": 20.99,   "group": "Europa"},
    {"id": "oci|madrid",     "name": "Spagna centrale (Madrid)",                "lat": 40.42,  "lng": -3.70,   "group": "Europa"},
    {"id": "oci|madrid2",    "name": "Spagna centrale 2 (Madrid)",              "lat": 40.30,  "lng": -3.55,   "group": "Europa"},
    {"id": "oci|stoccolma",  "name": "Svezia centrale (Stoccolma)",             "lat": 59.33,  "lng": 18.06,   "group": "Europa"},
    {"id": "oci|zurigo",     "name": "Svizzera nord (Zurigo)",                  "lat": 47.37,  "lng": 8.54,    "group": "Europa"},
    {"id": "oci|londra",     "name": "Regno Unito sud (Londra)",                "lat": 51.51,  "lng": -0.13,   "group": "Europa"},
    {"id": "oci|newport",    "name": "Regno Unito occidentale (Newport)",       "lat": 51.58,  "lng": -3.00,   "group": "Europa"},
    # Africa
    {"id": "oci|kenya",      "name": "Kenya",                                   "lat": -1.29,  "lng": 36.82,   "group": "Africa"},
    {"id": "oci|casablanca", "name": "Marocco occidentale (Casablanca)",        "lat": 33.57,  "lng": -7.59,   "group": "Africa"},
    {"id": "oci|marocco2",   "name": "Marocco 2",                               "lat": 33.00,  "lng": -7.62,   "group": "Africa"},
    {"id": "oci|johannesburg","name": "Sud Africa centrale (Johannesburg)",     "lat": -26.20, "lng": 28.05,   "group": "Africa"},
    # Medio-Oriente
    {"id": "oci|gerusalemme","name": "Israele centrale (Gerusalemme)",          "lat": 31.77,  "lng": 35.21,   "group": "Medio-Oriente"},
    {"id": "oci|gedda",      "name": "Arabia Saudita occidentale (Gedda)",      "lat": 21.49,  "lng": 39.19,   "group": "Medio-Oriente"},
    {"id": "oci|riyad",      "name": "Arabia Saudita centrale (Riyad)",         "lat": 24.71,  "lng": 46.68,   "group": "Medio-Oriente"},
    {"id": "oci|dubai",      "name": "Emirati Arabi Uniti orientali (Dubai)",   "lat": 25.20,  "lng": 55.27,   "group": "Medio-Oriente"},
    {"id": "oci|abudhabi",   "name": "Emirati Arabi Uniti centrali (Abu Dhabi)","lat": 24.45,  "lng": 54.38,   "group": "Medio-Oriente"},
    # Asia
    {"id": "oci|mumbai",     "name": "India occidentale (Mumbai)",              "lat": 19.08,  "lng": 72.88,   "group": "Asia"},
    {"id": "oci|hyderabad",  "name": "India del sud (Hyderabad)",               "lat": 17.38,  "lng": 78.49,   "group": "Asia"},
    {"id": "oci|batam",      "name": "Indonesia settentrionale (Batam)",        "lat": 1.13,   "lng": 104.05,  "group": "Asia"},
    {"id": "oci|tokyo",      "name": "Giappone orientale (Tokyo)",              "lat": 35.68,  "lng": 139.69,  "group": "Asia"},
    {"id": "oci|osaka",      "name": "Giappone centrale (Osaka)",               "lat": 34.69,  "lng": 135.50,  "group": "Asia"},
    {"id": "oci|kulai",      "name": "Malesia occidentale (Kulai)",             "lat": 1.66,   "lng": 103.60,  "group": "Asia"},
    {"id": "oci|singapore",  "name": "Singapore (Singapore)",                   "lat": 1.35,   "lng": 103.82,  "group": "Asia"},
    {"id": "oci|singaporew", "name": "Regione occidentale di Singapore",        "lat": 1.33,   "lng": 103.69,  "group": "Asia"},
    {"id": "oci|seul",       "name": "Corea del Sud centrale (Seul)",           "lat": 37.57,  "lng": 126.98,  "group": "Asia"},
    {"id": "oci|chuncheon",  "name": "Corea del Sud settentrionale (Chuncheon)","lat": 37.88,  "lng": 127.73,  "group": "Asia"},
    # Oceania
    {"id": "oci|sydney",     "name": "Australia orientale (Sydney)",            "lat": -33.87, "lng": 151.21,  "group": "Oceania"},
    {"id": "oci|melbourne",  "name": "Australia sud-orientale (Melbourne)",     "lat": -37.81, "lng": 144.96,  "group": "Oceania"},
]

ALL_CITIES = ([dict(c, provider="aws") for c in AWS_CITIES] +
              [dict(c, provider="oci") for c in OCI_CITIES])
ALL_CITIES.sort(key=lambda c: (GROUP_ORDER.index(c["group"]), c["provider"], c["name"]))
CITY_BY_ID = {c["id"]: c for c in ALL_CITIES}
AWS_REGION_NAME = {c["region"]: c["name"] for c in AWS_CITIES}


# ----------------------------------------------------------------------------
# Logica pura (nessuna dipendenza da Streamlit: testabile e riusabile)
# ----------------------------------------------------------------------------
def fmt_usd(value):
    """$ con decimali adattivi e separatori in stile italiano."""
    if value == 0:
        return "$ 0"
    dec = 0 if value >= 100 else (2 if value >= 1 else (3 if value >= 0.01 else 4))
    s = f"{value:,.{dec}f}"
    return "$ " + s.replace(",", "§").replace(".", ",").replace("§", ".")


def nearest(options, target):
    """Il valore di `options` più vicino a `target` (a parità, il più basso)."""
    return min(options, key=lambda x: (abs(x - target), x))


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


INTRO_TEMPLATE = """<style>
  html, body { margin: 0; height: 100%; background: #000; overflow: hidden; }
  video { width: 100%; height: 100%; object-fit: cover; background: #000; }
  .skip { position: fixed; bottom: 18px; right: 22px;
          color: rgba(255, 255, 255, .75);
          font: 14px -apple-system, "Segoe UI", Roboto, sans-serif; }
</style>
<video id="v" autoplay muted playsinline
       src="data:video/mp4;base64,__B64__"></video>
<div class="skip">clicca per saltare &#9656;</div>
<script>
  // L'iframe del componente si trasforma da solo in un layer fisso a tutto
  // schermo sopra la pagina (stessa origine: possiamo ridimensionarci).
  const f = window.frameElement;
  if (f) {
    Object.assign(f.style, {
      position: 'fixed', inset: '0', width: '100vw', height: '100vh',
      zIndex: '999999', background: '#000', border: '0'
    });
  }
  const v = document.getElementById('v');
  let gone = false;
  function hide() {
    if (gone || !f) return;
    gone = true;
    try { v.pause(); } catch (e) {}
    f.style.transition = 'opacity .45s ease';
    f.style.opacity = '0';
    setTimeout(function () { f.style.display = 'none'; }, 500);
  }
  v.addEventListener('ended', hide);
  v.addEventListener('error', hide);
  document.addEventListener('click', hide);   // click = salta l'intro
  setTimeout(hide, 12000);                    // rete di sicurezza
  v.play().catch(hide);   // se anche l'autoplay muto fallisse, via l'overlay
</script>"""


def intro_overlay_html(video_b64):
    """Overlay di intro a tutto schermo. L'autoplay senza interazione è
    consentito dai browser solo con audio muto: il video parte muto."""
    return INTRO_TEMPLATE.replace("__B64__", video_b64)


def _load_all(data_dir):
    """Legge hpc.csv e combinations.csv; costruisce indice e mappe delle shape."""
    data_dir = Path(data_dir)

    with open(data_dir / "combinations.csv", newline="", encoding="utf-8-sig") as f:
        combos = {(int(r["vCPU"]), int(r["ram(GB)"])) for r in csv.DictReader(f)}
    vcpus = sorted({v for v, _ in combos})
    rams = sorted({r for _, r in combos})
    rams_for = {v: sorted(r for vv, r in combos if vv == v) for v in vcpus}
    vcpus_for = {r: sorted(v for v, rr in combos if rr == r) for r in rams}

    index = {}
    n_rows = 0
    with open(data_dir / "hpc.csv", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            n_rows += 1
            key = (row["provider"].strip().lower(),
                   row["region"].strip(),
                   row["architecture"].strip(),
                   int(row["vCPU"]),
                   int(float(row["ram(GB)"])))
            index.setdefault(key, []).append({
                "family": row["family"].strip(),
                "processor": row["processor"].strip(),
                "prices": {col: float(row[col]) for col in
                           ("price($/h)", "daily_price", "weekly_price", "monthly_price")},
            })

    return {"index": index, "combos": combos, "vcpus": vcpus, "rams": rams,
            "rams_for": rams_for, "vcpus_for": vcpus_for, "n_rows": n_rows}


def city_offers(index, provider, region, vcpu, ram, arch_values, price_col):
    """Tutte le offerte per una città/shape, dalla più economica in su."""
    offers = []
    for arch in arch_values:
        for off in index.get((provider, region, arch, vcpu, ram), []):
            offers.append({"arch": arch, "family": off["family"],
                           "processor": off["processor"],
                           "price": off["prices"][price_col]})
    offers.sort(key=lambda o: (o["price"], o["family"]))
    return offers


def price_stats(offers):
    """(min, media, max) dei prezzi di una lista di offerte."""
    prices = [o["price"] for o in offers]
    return min(prices), sum(prices) / len(prices), max(prices)


def options_rows(index, aws_regions, include_oci, arch_values, vcpu, ram, price_col):
    """Righe per la lista 'Opzioni Disponibili': tutte le offerte OCI (globali,
    senza ripetizioni per città) + per AWS l'offerta più economica di OGNI
    family cercata tra tutte le città selezionate (la Region indica dove).
    Ordinate dalla più economica alla meno economica."""
    rows = []
    if include_oci:
        for o in city_offers(index, "oci", "global", vcpu, ram, arch_values, price_col):
            rows.append({"Provider": "OCI", "Region": "global", "Family": o["family"],
                         "Architecture": o["arch"], "Processor": o["processor"],
                         "Price": o["price"]})
    best_by_family = {}
    for region in aws_regions:
        for o in city_offers(index, "aws", region, vcpu, ram, arch_values, price_col):
            cur = best_by_family.get(o["family"])
            if cur is None or (o["price"], region) < (cur["Price"], cur["Region"]):
                best_by_family[o["family"]] = {
                    "Provider": "AWS", "Region": region, "Family": o["family"],
                    "Architecture": o["arch"], "Processor": o["processor"],
                    "Price": o["price"]}
    rows += best_by_family.values()
    # Codici AWS -> nomi estesi ("ap-south-1" -> "Asia Pacific (Mumbai)");
    # va fatto DOPO la scelta per family, che spareggia sui codici.
    for r in rows:
        r["Region"] = AWS_REGION_NAME.get(r["Region"], r["Region"])
    rows.sort(key=lambda r: (r["Price"], r["Provider"], r["Family"]))
    return rows


def build_payload(data, groups, city_ids, arch_values, vcpu, ram,
                  price_col, suffix, selected_id):
    """Pin per il globo + statistiche per il pannello."""
    index = data["index"]
    pins = []

    for c in ALL_CITIES:
        if c["group"] not in groups or c["id"] not in city_ids:
            continue
        region = c.get("region", "global")
        offers = city_offers(index, c["provider"], region, vcpu, ram,
                             arch_values, price_col)
        pin = {**c, "region": region, "offers": offers,
               "sub": ("AWS · " + region) if c["provider"] == "aws"
                      else "OCI · prezzo globale"}
        if offers:
            mn, avg, mx = price_stats(offers)
            pin.update(available=True, cost=mn,
                       color=PROVIDER_COLOR[c["provider"]],
                       z=Z_PRIORITY[c["provider"]],
                       price_label=fmt_usd(mn) + suffix, best=offers[0],
                       t1=f"min {fmt_usd(mn)}{suffix}",
                       t2=f"media {fmt_usd(avg)}{suffix}",
                       t3=f"max {fmt_usd(mx)}{suffix}")
        else:
            pin.update(available=False, cost=None, color=NA_COLOR,
                       z=Z_PRIORITY["nd"], price_label="N/D", best=None,
                       t1="", t2="N/D per questa configurazione", t3="")
        pin["selected"] = pin["id"] == selected_id
        pin["prov_label"] = PROVIDER_LABEL[c["provider"]]
        pin["highlight"] = False
        pins.append(pin)

    # Anti-sovrapposizione: coppie AWS/OCI quasi coincidenti scostate di
    # ±0,7° di longitudine (coppie calcolate sulle coordinate originali,
    # ogni pin spostato al massimo una volta).
    aws_pins = [p for p in pins if p["provider"] == "aws"]
    oci_pins = [p for p in pins if p["provider"] == "oci"]
    to_shift = {"aws": set(), "oci": set()}
    for a in aws_pins:
        for o in oci_pins:
            if abs(a["lat"] - o["lat"]) < 1.0 and abs(a["lng"] - o["lng"]) < 1.0:
                to_shift["aws"].add(a["id"])
                to_shift["oci"].add(o["id"])
    for p in pins:
        if p["id"] in to_shift["aws"]:
            p["lng"] = p["lng"] + 0.7
        elif p["id"] in to_shift["oci"]:
            p["lng"] = p["lng"] - 0.7

    avail = sorted([p for p in pins if p["available"]],
                   key=lambda p: (p["cost"], p["name"]))
    for i, p in enumerate(avail, start=1):
        p["rank"] = i
    pins = avail + sorted([p for p in pins if not p["available"]],
                          key=lambda p: p["name"])

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
        # ... e l'OCI più vicina al pin AWS più economico pulsa con lui
        f = best_aws_ties[0]
        near_pool = oci_avail or [p for p in pins if p["provider"] == "oci"]
        if near_pool:
            nearest_oci = min(near_pool, key=lambda p: (p["lat"] - f["lat"]) ** 2
                              + (p["lng"] - f["lng"]) ** 2)
            nearest_oci["highlight"] = True

    # Prezzo medio su TUTTE le configurazioni disponibili con i filtri attivi
    # (le offerte OCI, globali, contano una volta sola)
    oci_prices, aws_prices = [], []
    if oci_pins:
        oci_prices += [o["price"] for o in
                       city_offers(index, "oci", "global", vcpu, ram,
                                   arch_values, price_col)]
    for p in aws_pins:
        aws_prices += [o["price"] for o in p["offers"]]
    all_prices = oci_prices + aws_prices
    avg_oci = (sum(oci_prices) / len(oci_prices)) if oci_prices else None
    avg_aws = (sum(aws_prices) / len(aws_prices)) if aws_prices else None

    stats = {
        "n": len(pins), "n_avail": len(avail),
        "min": avail[0]["cost"] if avail else 0.0,
        "max": avail[-1]["cost"] if avail else 0.0,
        "avg_all": (sum(all_prices) / len(all_prices)) if all_prices else None,
        "n_configs": len(all_prices),
        "avg_oci": avg_oci, "n_oci": len(oci_prices),
        "avg_aws": avg_aws, "n_aws": len(aws_prices),
        "best_oci": oci_avail[0] if oci_avail else None,
        "best_aws": best_aws_ties[0] if best_aws_ties else None,
        "best_aws_ties": best_aws_ties,
        "focus": focus,
    }
    return pins, stats


# ---------------------------- UI (Streamlit) ---------------------------------

st.set_page_config(
    page_title="   🟠AWS  ⚔️ ​ OCI🔴   ",
    page_icon=Image.open(Path(__file__).parent / "favicon.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS: City List essenziale (niente chip: il conteggio appare nella barra,
# vedi lo stile dinamico più sotto), bottone "Opzioni Disponibili" sempre
# verde a prescindere dal tema, KPI più grandi.
st.markdown("""<style>
section[data-testid='stSidebar'] div[data-testid='stMultiSelect'] span[data-baseweb='tag']
  { display: none; }
section[data-testid='stSidebar'] div[data-testid='stMultiSelect'] div[data-baseweb='select']
  { position: relative; }
section[data-testid='stSidebar'] div[data-testid='stMultiSelect'] div[data-baseweb='select']:focus-within::before
  { content: "" !important; }
section[data-testid='stSidebar'] [data-testid='stAudio']
  { display: none; }
.st-key-btn_options button {
  background-color: #22c55e !important; border-color: #22c55e !important;
  color: #06130b !important; font-weight: 700;
}
.st-key-btn_options button:hover, .st-key-btn_options button:focus {
  background-color: #16a34a !important; border-color: #16a34a !important;
  color: #06130b !important;
}
.st-key-kpi_panel [data-testid='stMetricLabel'] p
  { font-size: 1.06rem; font-weight: 600; }
.st-key-kpi_panel [data-testid='stMetricValue']
  { font-size: 2.15rem; }
.st-key-kpi_panel [data-testid='stMetricDelta']
  { font-size: 1rem; }
/* Riepilogo scorrevole delle città selezionate. Il menu di BaseWeb elenca
   solo le opzioni NON ancora scelte, quindi va nascosto quando è vuoto
   ("No results") e sostituito da questo riquadro, che appare solo mentre la
   barra della City List è attiva (:focus-within = si è cliccato dentro). */
div[data-baseweb='popover']:has(div[data-baseweb='menu']):not(:has(li[role='option']))
  { display: none !important; }
div[data-baseweb='popover']:has([data-testid='stSelectboxVirtualDropdownEmpty'])
  { display: none !important; }
.st-key-city_box .st-key-city_recap,
.st-key-city_box div:has(.st-key-city_recap):not(:has(div[data-testid='stMultiSelect']))
  { display: none; }
.st-key-city_box:focus-within .st-key-city_recap,
.st-key-city_box:focus-within div:has(.st-key-city_recap):not(:has(div[data-testid='stMultiSelect']))
  { display: block; }
/* Niente height= lato Streamlit: l'altezza sta qui, così a riquadro chiuso
   nessun involucro resta a occupare spazio. */
.st-key-city_recap {
  max-height: 190px; overflow-y: auto;
  margin-top: .35rem; padding: .3rem .35rem;
  border: 1px solid rgba(255, 255, 255, .15); border-radius: .5rem;
  background: rgba(255, 255, 255, .02);
}
.st-key-city_recap [data-testid='stVerticalBlock'] { gap: .1rem; }
.st-key-city_recap [data-testid='stHorizontalBlock'] { gap: .2rem; }
.st-key-city_recap .city-row {
  font-size: .84rem; color: #cfd8ea; line-height: 1.7;
  display: block; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap;
}
.st-key-city_recap div[data-testid='stButton'] button {
  background: transparent !important; border: none !important;
  color: #64748b !important; padding: 0 .35rem !important;
  min-height: 1.5rem !important; height: 1.5rem;
}
.st-key-city_recap div[data-testid='stButton'] button:hover
  { color: #f87171 !important; }
/* Prima riga "Close Window": resta agganciata in cima anche scorrendo. */
.st-key-city_recap .st-key-close_recap {
  position: sticky; top: -.3rem; z-index: 2; background: #0f1727;
}
.st-key-city_recap .st-key-close_recap button {
  color: #94a3b8 !important; font-size: .78rem;
  border-bottom: 1px solid rgba(255, 255, 255, .12) !important;
  border-radius: 0 !important;
}
.st-key-city_recap .st-key-close_recap button:hover
  { color: #e6edf3 !important; }
</style>""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = BASE_DIR / "audio"
VIDEO_DIR = BASE_DIR / "video"


@st.cache_data(show_spinner=False)
def load_all(data_dir: str):
    return _load_all(data_dir)


@st.cache_data(show_spinner=False)
def load_intro_html(signature):
    """HTML dell'overlay con il video incorporato in base64; la firma
    (nome, size, mtime) lo rigenera solo quando il file cambia."""
    name = signature[0]
    b64 = base64.b64encode((VIDEO_DIR / name).read_bytes()).decode("ascii")
    return intro_overlay_html(b64)


@st.cache_data(show_spinner=False)
def load_playlist(signature):
    """Playlist unica in memoria; la firma (nome, size, mtime) la invalida
    solo quando i file cambiano, così l'audio resta identico tra i rerun
    e la riproduzione non si interrompe usando i filtri."""
    return concat_mp3([AUDIO_DIR / name for name, _, _ in signature])


DATA = load_all(str(DATA_DIR))
COMBOS = DATA["combos"]

ss = st.session_state
ss.setdefault("selected", None)     # id del pin selezionato (o None)
ss.setdefault("last_n", 0)          # nonce dell'ultimo click già gestito
ss.setdefault("show_options", False)
ss.setdefault("city_open", False)   # riquadro City List forzato aperto
ss.setdefault("city_blur", 0)       # ... e forzato chiuso (togliendo il focus)
ss.setdefault("scroll_opts", False)
ss.setdefault("regions_sel", list(GROUP_ORDER))
ss.setdefault("prev_groups", set(GROUP_ORDER))
ss.setdefault("vcpu_sel", 4 if (4, 16) in COMBOS else DATA["vcpus"][0])
ss.setdefault("ram_sel", 16 if (4, 16) in COMBOS else DATA["rams_for"][DATA["vcpus"][0]][0])


def _apply_click(payload):
    if payload and payload.get("n", 0) > ss.last_n:
        ss.last_n = payload["n"]
        ss.selected = payload.get("id")
        return True
    return False


# Il valore del componente (ultimo click) è già in session_state a inizio run
_apply_click(ss.get("globe"))


def _sync_from_vcpu():
    if (ss.vcpu_sel, ss.ram_sel) not in COMBOS:
        ss.ram_sel = nearest(DATA["rams_for"][ss.vcpu_sel], ss.ram_sel)


def _sync_from_ram():
    if (ss.vcpu_sel, ss.ram_sel) not in COMBOS:
        ss.vcpu_sel = nearest(DATA["vcpus_for"][ss.ram_sel], ss.vcpu_sel)


def _clear_cities():
    ss.city_sel = []
    ss.regions_sel = []    # coerenza: si spengono anche i bottoni Regions
    ss.clear_all = False   # la spunta torna subito libera (azione istantanea)


def _remove_city(cid):
    ss.city_sel = [i for i in ss.city_sel if i != cid]
    # Il rerun fa perdere il focus (e quindi chiuderebbe il riquadro): lo
    # teniamo aperto per questo giro, così si possono togliere più città.
    ss.city_open = True


def _close_recap():
    # Il contatore rende unico l'HTML dello script di blur: senza, al secondo
    # click Streamlit riuserebbe l'iframe identico e non lo rieseguirebbe.
    ss.city_blur += 1


def _toggle_options():
    ss.show_options = not ss.show_options
    ss.scroll_opts = ss.show_options   # all'apertura, scorri fino alla tabella


def city_label(cid):
    c = CITY_BY_ID[cid]
    return f"{PROVIDER_LABEL[c['provider']]} — {c['name']}"


# --- Intro video a tutto schermo (una volta per sessione) --------------------
# La pagina si carica normalmente sotto l'overlay, che sparisce a fine video
# (o al click). Al refresh del browser l'intro riparte.
ss.setdefault("intro_done", False)
if not ss.intro_done:
    ss.intro_done = True
    intro_files = sorted(VIDEO_DIR.glob("*.mp4"))
    if intro_files:
        p = intro_files[0]
        components.html(
            load_intro_html((p.name, p.stat().st_size, int(p.stat().st_mtime))),
            height=0,
        )

# --- Pannello laterale (dall'alto verso il basso, come da specifica) ---------
with st.sidebar:
    st.markdown("#### Regions")
    groups = st.pills("Regions", GROUP_ORDER, selection_mode="multi",
                      key="regions_sel", label_visibility="collapsed") or []
    groups_set = set(groups)

    # City List sincronizzata con Regions: le opzioni sono le città delle
    # zone selezionate; una zona appena riattivata riporta dentro le sue
    # città; una zona rimossa le toglie da opzioni e selezione.
    city_options = [c["id"] for c in ALL_CITIES if c["group"] in groups_set]
    if "city_sel" not in ss:
        ss.city_sel = city_options[:]                      # default: tutte
    else:
        added = groups_set - ss.prev_groups
        keep = {i for i in ss.city_sel if i in set(city_options)}
        keep |= {i for i in city_options if CITY_BY_ID[i]["group"] in added}
        ss.city_sel = [i for i in city_options if i in keep]
    ss.prev_groups = groups_set

    st.markdown("#### City List")
    # Barra + riquadro nello stesso contenitore: basta il :focus-within del
    # contenitore per far comparire l'elenco quando si clicca nella barra.
    with st.container(key="city_box"):
        st.multiselect("City List", options=city_options, key="city_sel",
                       format_func=city_label, label_visibility="collapsed",
                       placeholder="Cerca o seleziona una città…")

        # La tendina elenca solo le città ancora da aggiungere; quelle già
        # scelte vivono qui, in un riquadro con scroll, ognuna con la sua ✕.
        if ss.city_sel:
            with st.container(border=False, key="city_recap"):
                st.button("✕  Close Window", key="close_recap",
                          use_container_width=True, on_click=_close_recap)
                for cid in ss.city_sel:
                    col_name, col_x = st.columns([0.85, 0.15],
                                                 vertical_alignment="center")
                    col_name.markdown(
                        f"<span class='city-row' title='{city_label(cid)}'>"
                        f"{city_label(cid)}</span>", unsafe_allow_html=True)
                    col_x.button("✕", key=f"rm_{cid}",
                                 on_click=_remove_city, args=(cid,))

    if ss.city_open:      # rerun dopo una ✕: il riquadro resta aperto
        st.markdown(
            "<style>.st-key-city_box .st-key-city_recap, .st-key-city_box "
            "div:has(.st-key-city_recap):not(:has(div[data-testid="
            "'stMultiSelect'])) { display: block !important; }</style>",
            unsafe_allow_html=True,
        )
    ss.city_open = False

    # Il riquadro vive su :focus-within, quindi per chiuderlo basta togliere
    # il focus: dopo il click su "Close Window" resterebbe sul bottone.
    if ss.city_blur:
        components.html(
            f"""<script>
            /* {ss.city_blur} */
            try {{
              var d = window.parent.document;
              var box = d.querySelector('.st-key-city_box');
              var a = d.activeElement;
              if (box && a && box.contains(a)) a.blur();
            }} catch (e) {{}}
            </script>""",
            height=0,
        )

    st.checkbox("Deseleziona tutte ☄️​", key="clear_all",
                on_change=_clear_cities, disabled=not ss.city_sel)

    st.markdown("#### Architecture")
    a1, a2, a3 = st.columns(3)
    arch_checked = [
        a1.checkbox("ARM", value=True),
        a2.checkbox("x86 AMD", value=True),
        a3.checkbox("x86 Intel", value=True),
    ]
    arch_values = [csv_val for (_, csv_val), on in zip(ARCH_OPTIONS, arch_checked) if on]

    st.markdown("#### Shape")
    st.select_slider("Numero di vCPU", options=DATA["vcpus"],
                     key="vcpu_sel", on_change=_sync_from_vcpu)
    st.select_slider("GB di RAM", options=DATA["rams"],
                     key="ram_sel", on_change=_sync_from_ram)
    if (ss.vcpu_sel, ss.ram_sel) not in COMBOS:   # rete di sicurezza
        ss.ram_sel = nearest(DATA["rams_for"][ss.vcpu_sel], ss.ram_sel)

    st.markdown("#### Time-Based Pricing")
    gran = st.selectbox("Time-Based Pricing", list(GRANULARITY),
                        index=list(GRANULARITY).index("Weekly"),
                        label_visibility="collapsed")

    st.divider()
    rotate = st.toggle("Rotazione automatica", value=True)
    music = st.toggle("Musica", value=False)
    if music:
        tracks = sorted(AUDIO_DIR.glob("*.mp3"))
        if tracks:
            signature = tuple((p.name, p.stat().st_size, int(p.stat().st_mtime))
                              for p in tracks)
            # Player nascosto via CSS: comanda tutto la spunta qui sopra
            st.audio(load_playlist(signature), format="audio/mpeg",
                     loop=True, autoplay=True)
        else:
            st.caption("Nessun .mp3 trovato: caricane uno nella cartella "
                       "`audio/` del progetto.")

price_col, suffix, num_fmt = GRANULARITY[gran]
vcpu, ram = ss.vcpu_sel, ss.ram_sel

# "N città selezionate su M" DENTRO la barra della City List (sparisce
# mentre si digita nella ricerca; con 0 selezioni resta il placeholder).
count_txt = (f"{len(ss.city_sel)} / {len(city_options)} città"
             if ss.city_sel else "")
st.markdown(
    "<style>section[data-testid='stSidebar'] div[data-testid='stMultiSelect'] "
    "div[data-baseweb='select']::before { "
    f'content: "{count_txt}"; '
    "position: absolute; left: 12px; top: 50%; transform: translateY(-50%); "
    "color: #e6edf3; font-size: .88rem; pointer-events: none; z-index: 1; "
    "white-space: nowrap; max-width: 76%; overflow: hidden; "
    "text-overflow: ellipsis; }</style>",
    unsafe_allow_html=True,
)

pins, stats = build_payload(DATA, groups_set, set(ss.city_sel), arch_values,
                            vcpu, ram, price_col, suffix, ss.selected)

# Se il pin selezionato è stato filtrato via, deselezioniamo
if ss.selected and ss.selected not in {p["id"] for p in pins}:
    ss.selected = None
    pins, stats = build_payload(DATA, groups_set, set(ss.city_sel), arch_values,
                                vcpu, ram, price_col, suffix, None)

# --- Layout ------------------------------------------------------------------
st.title("Virtual Machines, Around the World")
st.caption(
    f"   · In totale: {DATA['n_rows']} prezzi, aggiornati al 20 Luglio 2026. "
)

col_globe, col_stats = st.columns([2.5, 1], gap="large")

with col_globe:
    if not groups:
        st.warning("Seleziona almeno una zona geografica nella sezione **Regions**.")
    elif not ss.city_sel:
        st.warning("Seleziona almeno una città nella sezione **City List**.")
    if not arch_values:
        st.warning("Seleziona almeno un'architettura nella sezione **Architecture**.")

    globe_dir = BASE_DIR / "globe_component"
    hpc_globe = components.declare_component("hpc_pricing_globe", path=str(globe_dir))

    # Al componente servono solo i campi "leggeri"; l'ordine (N/D, poi OCI,
    # poi AWS) rafforza la priorità di sovrapposizione insieme allo z-index.
    pin_args = sorted(
        [{k: p[k] for k in ("id", "name", "sub", "lat", "lng", "color",
                            "selected", "highlight", "z", "t1", "t2", "t3")}
         for p in pins],
        key=lambda p: p["z"],
    )
    clicked = hpc_globe(pins=pin_args, selected=ss.selected or "",
                        rotate=rotate, focus=stats["focus"],
                        key="globe", default=None)
    if _apply_click(clicked):   # rete di sicurezza: click arrivato solo ora
        st.rerun()

    # --- Bottone verde, al centro sotto il globo -----------------------------
    b1, b2, b3 = st.columns([1, 1.2, 1])
    b2.button("Opzioni Disponibili", key="btn_options", type="primary",
              use_container_width=True, on_click=_toggle_options)

    # --- Analitiche della città selezionata ----------------------------------
    sel = next((p for p in pins if p["id"] == ss.selected), None)
    if sel:
        chip = (f"<span style='display:inline-block;width:12px;height:12px;"
                f"border-radius:50%;background:{PROVIDER_COLOR[sel['provider']]};"
                f"margin-right:6px'></span>")
        st.markdown(f"#### {chip}{sel['prov_label']} — {sel['name']}",
                    unsafe_allow_html=True)

        if not sel["available"]:
            st.info("Nessuna offerta per questa combinazione di architettura e "
                    "shape in questa città: prova ad allargare i filtri.")
        else:
            b, diff = sel["best"], sel["cost"] - stats["min"]
            pct = (f"{diff / stats['min'] * 100:+.0f}%"
                   if stats["min"] > 0 and diff > 0 else None)

            c1, c2, c3 = st.columns(3)
            c1.metric(f"Miglior prezzo ({gran})", sel["price_label"])
            c1.caption(f"{b['family']} · {b['processor']} · {b['arch']}")
            if diff > 0:
                c2.metric("Delta vs più economica", fmt_usd(diff) + suffix,
                          delta=pct, delta_color="inverse")
            else:
                c2.metric("Delta vs più economica", "È la più economica ✓")
            c3.metric("Posizione in classifica",
                      f"{sel['rank']}ª su {stats['n_avail']}")
            if sel["provider"] == "oci":
                st.caption("Prezzo OCI valido per tutte le città (region `global`).")

            st.markdown(f"**Offerte disponibili** — {vcpu} vCPU · {ram} GB")
            df_off = pd.DataFrame([{
                "Famiglia": o["family"], "Processore": o["processor"],
                "Architettura": o["arch"],
                "Prezzo": fmt_usd(o["price"]) + suffix,
            } for o in sel["offers"]])
            st.dataframe(df_off, hide_index=True, use_container_width=True)

        st.button("Deseleziona", on_click=lambda: ss.update(selected=None))

with col_stats, st.container(key="kpi_panel"):
    if stats["avg_oci"] is not None and stats["avg_aws"] is not None:
        d = stats["avg_oci"] - stats["avg_aws"]
        if abs(d) < EPS:
            st.metric("​📈​ Average Price Gap", fmt_usd(0) + suffix,
                      delta="Parità", delta_color="off")
        else:
            winner = "OCI" if d < 0 else "AWS"
            st.metric("​📈​ Average Price Gap", fmt_usd(abs(d)) + suffix,
                      delta=f"a favore di {winner}", delta_color="green")
        st.caption(f"   · Media OCI {fmt_usd(stats['avg_oci'])}{suffix} "
                   f"su {stats['n_oci']} opzioni")
        st.caption(f"   · Media AWS {fmt_usd(stats['avg_aws'])}{suffix} "
                   f"su {stats['n_aws']} opzioni")
        st.caption("")

    if stats["best_oci"]:
        st.metric("​​🔴​ Cheapest OCI option", stats["best_oci"]["price_label"])
        st.caption("   · Prezzo unico globale")
        st.caption("")

    if stats["best_aws"]:
        st.metric("​🟠​ Cheapest AWS option", stats["best_aws"]["price_label"])
        for p in stats["best_aws_ties"]:
            st.caption(f"   · {p['name']}")
        st.caption("")

# --- Opzioni Disponibili (rivelate dal bottone verde) ------------------------
if ss.show_options:
    st.divider()
    st.markdown("<div id='opzioni-anchor'></div>", unsafe_allow_html=True)
    st.subheader("Opzioni Disponibili")
    rows = options_rows(
        DATA["index"],
        aws_regions=[p["region"] for p in pins if p["provider"] == "aws"],
        include_oci=any(p["provider"] == "oci" for p in pins),
        arch_values=arch_values, vcpu=vcpu, ram=ram, price_col=price_col,
    )
    if rows:
        
        df = pd.DataFrame(rows)
        st.dataframe(
            df, hide_index=True, use_container_width=True,
            column_config={
                "Price": st.column_config.ProgressColumn(
                    f"Price ({suffix.lstrip('/')})", format=num_fmt,
                    min_value=0.0,
                    max_value=float(max(r["Price"] for r in rows) or 1.0),
                ),
            },
        )
        
        st.caption(
            "   · OCI: offerte uguali e disponibili in tutte le città")
        st.caption(
            "   · AWS: per ogni family, l'offerta più economica disponibile tra le città selezionate")
                
    else:
        st.caption("Nessuna opzione disponibile con i filtri attuali.")

    # All'apertura, scorri dolcemente fino alla tabella (una volta sola)
    if ss.scroll_opts:
        ss.scroll_opts = False
        components.html(
            """<script>
            setTimeout(function () {
              try {
                var el = window.parent.document.getElementById('opzioni-anchor');
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
              } catch (e) {}
            }, 250);
            </script>""",
            height=0,
        )