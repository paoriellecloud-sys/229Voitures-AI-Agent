"""
VIN Decoder — décode les informations véhicule depuis le VIN sans API externe.

Structure VIN (17 caractères, indices Python 0-based) :
  [0:3]  WMI  — fabricant / pays
  [3:8]  VDS  — description véhicule (modèle, moteur, traction)
  [8]    chiffre de contrôle
  [9]    année modèle
  [10]   usine d'assemblage
  [11:]  numéro séquentiel
"""

# ── Tables de décodage ──────────────────────────────────────────────────────

_YEAR_MAP = {
    "A": 2010, "B": 2011, "C": 2012, "D": 2013, "E": 2014,
    "F": 2015, "G": 2016, "H": 2017, "J": 2018, "K": 2019,
    "L": 2020, "M": 2021, "N": 2022, "P": 2023, "R": 2024,
    "S": 2025, "T": 2026,
}

_WMI_MAP = {
    "1HG": {"manufacturer": "Honda",      "country": "Canada"},
    "2HG": {"manufacturer": "Honda",      "country": "Canada"},
    "KND": {"manufacturer": "Kia",        "country": "Corée du Sud"},
    "5NP": {"manufacturer": "Hyundai",    "country": "États-Unis"},
    "KMH": {"manufacturer": "Hyundai",    "country": "Corée du Sud"},
    "1FM": {"manufacturer": "Ford",       "country": "États-Unis"},
    "2FM": {"manufacturer": "Ford",       "country": "Canada"},
    "1G1": {"manufacturer": "Chevrolet",  "country": "États-Unis"},
    "JTD": {"manufacturer": "Toyota",     "country": "Japon"},
    "JTM": {"manufacturer": "Toyota",     "country": "Japon"},
    "2T3": {"manufacturer": "Toyota",     "country": "Canada"},
    "WBA": {"manufacturer": "BMW",        "country": "Allemagne"},
    "WVW": {"manufacturer": "Volkswagen", "country": "Allemagne"},
    "3VW": {"manufacturer": "Volkswagen", "country": "Mexique"},
    "1C4": {"manufacturer": "Chrysler",   "country": "États-Unis"},
    "2C4": {"manufacturer": "Chrysler",   "country": "Canada"},
    "WAU": {"manufacturer": "Audi",       "country": "Allemagne"},
}

_KIA_VDS = {
    "PM3": {"model": "Sportage", "engine": "2.4L",  "drivetrain": "AWD"},
    "PM2": {"model": "Sportage", "engine": "2.4L",  "drivetrain": "FWD"},
    "PC3": {"model": "Sportage", "engine": "1.6T",  "drivetrain": "AWD"},
    "E2C": {"model": "Seltos",   "engine": "2.0L",  "drivetrain": "AWD"},
    "E2B": {"model": "Seltos",   "engine": "2.0L",  "drivetrain": "FWD"},
    "E3C": {"model": "Seltos",   "engine": "1.6T",  "drivetrain": "AWD"},
    "C2C": {"model": "Sorento",  "engine": "2.4L",  "drivetrain": "AWD"},
    "C3C": {"model": "Sorento",  "engine": "2.0T",  "drivetrain": "AWD"},
    "U4C": {"model": "Telluride","engine": "3.8L",  "drivetrain": "AWD"},
}

_HYUNDAI_VDS = {
    "EL4": {"model": "Tucson",  "engine": "2.0L", "drivetrain": "AWD"},
    "EL2": {"model": "Tucson",  "engine": "2.0L", "drivetrain": "FWD"},
    "BH3": {"model": "Elantra", "engine": "2.0L", "drivetrain": "FWD"},
    "ZA8": {"model": "Kona",    "engine": "2.0L", "drivetrain": "AWD"},
}

_TOYOTA_VDS = {
    "RFR":  {"model": "RAV4",       "engine": "2.5L",         "drivetrain": "AWD"},
    "BJR":  {"model": "RAV4 Hybrid","engine": "2.5L Hybrid",  "drivetrain": "AWD"},
    "BJ3":  {"model": "RAV4 Prime", "engine": "2.5L PHEV",    "drivetrain": "AWD"},
    "DFW":  {"model": "Corolla",    "engine": "1.8L",         "drivetrain": "FWD"},
    "BFJR": {"model": "Highlander", "engine": "3.5L",         "drivetrain": "AWD"},
}


# ── Fonctions de décodage ────────────────────────────────────────────────────

def decode_year(vin: str) -> int:
    """Retourne l'année modèle depuis la position 10 du VIN (index 9)."""
    if not vin or len(vin) < 10:
        return 0
    return _YEAR_MAP.get(vin[9].upper(), 0)


def decode_manufacturer(vin: str) -> dict:
    """Retourne marque et pays depuis les 3 premiers caractères du VIN (WMI)."""
    if not vin or len(vin) < 3:
        return {}
    return _WMI_MAP.get(vin[:3].upper(), {})


def _lookup_vds(vin: str, table: dict) -> dict:
    """Cherche une clé VDS (3 ou 4 chars) dans la table fournie."""
    vds = vin[3:8].upper()
    # Essayer 4 caractères d'abord, puis 3
    return table.get(vds[:4]) or table.get(vds[:3]) or {}


def decode_kia_vds(vin: str) -> dict:
    """Décode le VDS d'un VIN Kia (KND ou KMH)."""
    return _lookup_vds(vin, _KIA_VDS)


def decode_hyundai_vds(vin: str) -> dict:
    """Décode le VDS d'un VIN Hyundai (5NP ou KMH)."""
    return _lookup_vds(vin, _HYUNDAI_VDS)


def decode_toyota_vds(vin: str) -> dict:
    """Décode le VDS d'un VIN Toyota (JTM, JTD, 2T3)."""
    return _lookup_vds(vin, _TOYOTA_VDS)


def decode_full(vin: str) -> dict:
    """
    Décode toutes les informations disponibles depuis le VIN.
    Retourne un dict complet avec year, manufacturer, model_info, engine, drivetrain.
    """
    if not vin or len(vin) != 17:
        return {"decoded": False, "error": "VIN invalide (doit faire 17 caractères)"}

    vin = vin.upper()
    year = decode_year(vin)
    mfr = decode_manufacturer(vin)
    manufacturer = mfr.get("manufacturer", "Inconnu")
    country = mfr.get("country", "Inconnu")
    plant = vin[10]

    _VDS_DECODERS = {
        "Kia":        decode_kia_vds,
        "Hyundai":    decode_hyundai_vds,
        "Toyota":     decode_toyota_vds,
    }
    vds_info = _VDS_DECODERS.get(manufacturer, lambda v: {})(vin)

    return {
        "year":         year,
        "manufacturer": manufacturer,
        "country":      country,
        "model_info":   vds_info.get("model", "N/D"),
        "engine":       vds_info.get("engine", "N/D"),
        "drivetrain":   vds_info.get("drivetrain", "N/D"),
        "plant":        plant,
        "decoded":      bool(vds_info),
    }


def enrich_vin_report(vin_data: dict, vin: str) -> dict:
    """
    Remplace les champs N/D d'un rapport VIN existant par les données décodées.
    vin_data est modifié en place et retourné.
    """
    decoded = decode_full(vin)
    if not decoded.get("decoded"):
        return vin_data

    if vin_data.get("moteur") in (None, "N/D", ""):
        vin_data["moteur"] = decoded["engine"]

    if vin_data.get("traction") in (None, "N/D", ""):
        vin_data["traction"] = decoded["drivetrain"]

    # La transmission (automatique/manuelle) n'est pas encodée dans le VIN standard
    # → on ne touche pas au champ "transmission"

    return vin_data
