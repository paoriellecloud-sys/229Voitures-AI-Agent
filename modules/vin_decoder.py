"""
VIN Decoder — décode les informations véhicule via l'API NHTSA gratuite,
avec fallback sur les tables manuelles si l'API est indisponible.

Structure VIN (17 caractères, indices Python 0-based) :
  [0:3]  WMI  — fabricant / pays
  [3:8]  VDS  — description véhicule (modèle, moteur, traction)
  [8]    chiffre de contrôle
  [9]    année modèle
  [10]   usine d'assemblage
  [11:]  numéro séquentiel
"""
import requests as _requests

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
    "E2C": {"model": "Seltos",   "engine": "2.0L",        "drivetrain": "AWD"},
    "E2B": {"model": "Seltos",   "engine": "2.0L",        "drivetrain": "FWD"},
    "E3C": {"model": "Seltos",   "engine": "1.6T",        "drivetrain": "AWD"},
    "EPC": {"model": "Seltos",   "engine": "2.0L CVT",    "drivetrain": "FWD"},
    "EPD": {"model": "Seltos",   "engine": "2.0L CVT",    "drivetrain": "AWD"},
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


def _decode_nhtsa(vin: str) -> dict | None:
    """
    Appelle l'API NHTSA vPIC gratuite et retourne un dict normalisé,
    ou None si l'API est indisponible ou retourne des données vides.
    """
    try:
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"
        resp = _requests.get(url, timeout=5)
        resp.raise_for_status()
        results = resp.json().get("Results", [])
        fields = {
            r["Variable"]: r["Value"]
            for r in results
            if r.get("Value") and r["Value"] not in ("Not Applicable", "null", "")
        }
        if not fields.get("Make"):
            return None

        # Moteur : cylindrée + configuration
        disp = fields.get("Displacement (L)", "")
        cfg  = fields.get("Engine Configuration", "")
        engine_parts = []
        if disp:
            try:
                engine_parts.append(f"{round(float(disp), 1)}L")
            except ValueError:
                engine_parts.append(disp + "L")
        if cfg:
            engine_parts.append(cfg)
        engine = " ".join(engine_parts) or "N/D"

        # Traction — normaliser les valeurs NHTSA
        # NHTSA utilise "4X2" (FWD/RWD) et "4X4" (AWD/4WD)
        _dt_raw = (fields.get("Drive Type") or "").upper()
        if "AWD" in _dt_raw or "ALL-WHEEL" in _dt_raw or "4X4" in _dt_raw:
            drivetrain = "AWD"
        elif "4WD" in _dt_raw or "4-WHEEL" in _dt_raw:
            drivetrain = "4WD"
        elif "FWD" in _dt_raw or "FRONT" in _dt_raw or "4X2" in _dt_raw:
            drivetrain = "FWD"
        elif "RWD" in _dt_raw or "REAR" in _dt_raw:
            drivetrain = "RWD"
        else:
            drivetrain = _dt_raw or "N/D"

        transmission = fields.get("Transmission Style", "N/D")
        year_raw = fields.get("Model Year", "")
        try:
            year = int(year_raw)
        except (ValueError, TypeError):
            year = 0

        return {
            "year":         year,
            "manufacturer": fields.get("Make", "Inconnu").title(),
            "country":      fields.get("Plant Country", "Inconnu").title(),
            "model_info":   fields.get("Model", "N/D").title(),
            "engine":       engine,
            "drivetrain":   drivetrain,
            "transmission": transmission,
            "body_type":    fields.get("Body Class", "N/D"),
            "plant":        "",
            "decoded":      True,
            "source":       "NHTSA",
        }
    except Exception as _e:
        print(f"[vin_decoder] NHTSA timeout ou erreur - fallback manuel ({_e})")
        return None


def _decode_manual(vin: str) -> dict:
    """Décodage local depuis les tables WMI/VDS (fallback hors-ligne)."""
    year = decode_year(vin)
    mfr = decode_manufacturer(vin)
    manufacturer = mfr.get("manufacturer", "Inconnu")
    country = mfr.get("country", "Inconnu")
    plant = vin[10]

    _VDS_DECODERS = {
        "Kia":     decode_kia_vds,
        "Hyundai": decode_hyundai_vds,
        "Toyota":  decode_toyota_vds,
    }
    vds_info = _VDS_DECODERS.get(manufacturer, lambda v: {})(vin)

    return {
        "year":         year,
        "manufacturer": manufacturer,
        "country":      country,
        "model_info":   vds_info.get("model", "N/D"),
        "engine":       vds_info.get("engine", "N/D"),
        "drivetrain":   vds_info.get("drivetrain", "N/D"),
        "transmission": "N/D",
        "body_type":    "N/D",
        "plant":        plant,
        "decoded":      bool(vds_info),
        "source":       "manuel",
    }


def decode_full(vin: str) -> dict:
    """
    Décode toutes les informations depuis le VIN.
    Essaie d'abord l'API NHTSA gratuite, puis fallback sur les tables locales.
    """
    if not vin or len(vin) != 17:
        return {"decoded": False, "error": "VIN invalide (doit faire 17 caractères)"}

    vin = vin.upper()
    result = _decode_nhtsa(vin)
    if result is None:
        result = _decode_manual(vin)
    if not result.get("plant"):
        result["plant"] = vin[10]
    return result


def enrich_vin_report(vin_data: dict, vin: str) -> dict:
    """
    Remplace les champs N/D d'un rapport VIN existant par les données décodées.
    La transmission est maintenant remplie quand l'API NHTSA la fournit.
    vin_data est modifié en place et retourné.
    """
    decoded = decode_full(vin)
    if not decoded.get("decoded"):
        return vin_data

    if vin_data.get("moteur") in (None, "N/D", ""):
        vin_data["moteur"] = decoded["engine"]

    if vin_data.get("traction") in (None, "N/D", ""):
        vin_data["traction"] = decoded["drivetrain"]

    if vin_data.get("transmission") in (None, "N/D", "") and decoded.get("transmission") not in (None, "N/D", ""):
        vin_data["transmission"] = decoded["transmission"]

    return vin_data
