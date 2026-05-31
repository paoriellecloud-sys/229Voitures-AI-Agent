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
    "PM3": {"model": "Sportage", "engine": "2.4L",       "drivetrain": "AWD"},
    "PM2": {"model": "Sportage", "engine": "2.4L",       "drivetrain": "FWD"},
    "PC3": {"model": "Sportage", "engine": "1.6T",       "drivetrain": "AWD"},
    "E2C": {"model": "Seltos",   "engine": "2.0L",       "drivetrain": "AWD"},
    "E2B": {"model": "Seltos",   "engine": "2.0L",       "drivetrain": "FWD"},
    "E3C": {"model": "Seltos",   "engine": "1.6T",       "drivetrain": "AWD"},
    "EPC": {"model": "Seltos",   "engine": "2.0L CVT",   "drivetrain": "FWD"},
    "EPD": {"model": "Seltos",   "engine": "2.0L CVT",   "drivetrain": "AWD"},
    "C2C": {"model": "Sorento",  "engine": "2.4L",       "drivetrain": "AWD"},
    "C3C": {"model": "Sorento",  "engine": "2.0T",       "drivetrain": "AWD"},
    "U4C": {"model": "Telluride","engine": "3.8L",       "drivetrain": "AWD"},
}

_HYUNDAI_VDS = {
    "EL4": {"model": "Tucson",  "engine": "2.0L", "drivetrain": "AWD"},
    "EL2": {"model": "Tucson",  "engine": "2.0L", "drivetrain": "FWD"},
    "BH3": {"model": "Elantra", "engine": "2.0L", "drivetrain": "FWD"},
    "ZA8": {"model": "Kona",    "engine": "2.0L", "drivetrain": "AWD"},
}

_TOYOTA_VDS = {
    "RFR":  {"model": "RAV4",        "engine": "2.5L",        "drivetrain": "AWD"},
    "BJR":  {"model": "RAV4 Hybrid", "engine": "2.5L Hybrid", "drivetrain": "AWD"},
    "BJ3":  {"model": "RAV4 Prime",  "engine": "2.5L PHEV",   "drivetrain": "AWD"},
    "DFW":  {"model": "Corolla",     "engine": "1.8L",        "drivetrain": "FWD"},
    "BFJR": {"model": "Highlander",  "engine": "3.5L",        "drivetrain": "AWD"},
}


# ── Fonctions de décodage ────────────────────────────────────────────────────

def decode_year(vin: str) -> int:
    if not vin or len(vin) < 10:
        return 0
    return _YEAR_MAP.get(vin[9].upper(), 0)


def decode_manufacturer(vin: str) -> dict:
    if not vin or len(vin) < 3:
        return {}
    return _WMI_MAP.get(vin[:3].upper(), {})


def _lookup_vds(vin: str, table: dict) -> dict:
    vds = vin[3:8].upper()
    return table.get(vds[:4]) or table.get(vds[:3]) or {}


def decode_kia_vds(vin: str) -> dict:
    return _lookup_vds(vin, _KIA_VDS)


def decode_hyundai_vds(vin: str) -> dict:
    return _lookup_vds(vin, _HYUNDAI_VDS)


def decode_toyota_vds(vin: str) -> dict:
    return _lookup_vds(vin, _TOYOTA_VDS)


def _decode_nhtsa(vin: str) -> dict | None:
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
    Ajoute aussi les known_issues (recours collectifs, rappels).
    """
    decoded = decode_full(vin)

    if not decoded.get("decoded"):
        vin_data["known_issues"] = check_known_issues(vin, 0, "", "")
        return vin_data

    if vin_data.get("moteur") in (None, "N/D", ""):
        vin_data["moteur"] = decoded.get("engine", "N/D")

    if vin_data.get("traction") in (None, "N/D", ""):
        vin_data["traction"] = decoded.get("drivetrain", "N/D")

    if vin_data.get("transmission") in (None, "N/D", "") and decoded.get("transmission") not in (None, "N/D", ""):
        vin_data["transmission"] = decoded["transmission"]

    year = int(decoded.get("year") or 0)
    make = decoded.get("manufacturer", "")
    model = decoded.get("model_info", "")
    vin_data["known_issues"] = check_known_issues(vin, year, make, model)

    return vin_data


# ── Recours collectifs et rappels connus au Canada ──────────────────────────

_KNOWN_ISSUES = [
    {
        "make":   "Kia",
        "years":  set(range(2011, 2020)),
        "models": {"sportage", "sorento", "optima", "soul", "stinger"},
        "niveau": "warning",
        "titre":  "Moteur Theta II — Recours collectif Canada",
        "description": (
            "Ce véhicule Kia est potentiellement visé par le recours collectif "
            "relatif au moteur Theta II (calage, panne moteur). "
            "Remplacement gratuit possible."
        ),
        "action": "Vérifiez votre NIV sur le site du règlement",
        "url":    "https://www.kia.ca/kia-recall",
    },
    {
        "make":   "Hyundai",
        "years":  set(range(2011, 2020)),
        "models": {"tucson", "santa fe", "santa fe sport", "sonata", "elantra"},
        "niveau": "warning",
        "titre":  "Moteur Theta II — Recours collectif Canada",
        "description": (
            "Ce véhicule Hyundai est potentiellement visé par le recours collectif "
            "relatif au moteur Theta II. Vérifiez votre admissibilité."
        ),
        "action": "Vérifiez votre admissibilité",
        "url":    "https://www.hyundaicanada.com/fr/owners-section/recalls",
    },
    {
        "make":   "Toyota",
        "years":  {2022, 2023},
        "models": {"tundra", "lx 600", "lx"},
        "niveau": "warning",
        "titre":  "Rappel moteur biturbo 3.4L — Transports Canada",
        "description": (
            "Débris métalliques possibles dans le moteur. "
            "Remplacement du moteur requis selon Transports Canada (Rappel 2024304)."
        ),
        "action": "Contacter un concessionnaire Toyota autorisé",
        "url": (
            "https://recalls-rappels.canada.ca/fr/avis-rappel/"
            "numero-rappel-transports-canada-2024304-toyota"
        ),
    },
    {
        "make":   "Lexus",
        "years":  {2022, 2023},
        "models": {"lx 600", "lx"},
        "niveau": "warning",
        "titre":  "Rappel moteur biturbo 3.4L — Transports Canada",
        "description": (
            "Débris métalliques possibles dans le moteur. "
            "Remplacement du moteur requis selon Transports Canada (Rappel 2024304)."
        ),
        "action": "Contacter un concessionnaire Lexus autorisé",
        "url": (
            "https://recalls-rappels.canada.ca/fr/avis-rappel/"
            "numero-rappel-transports-canada-2024304-toyota"
        ),
    },
]


def check_known_issues(vin: str, year: int, make: str, model: str) -> list:
    issues = []
    make_l  = (make  or "").strip().lower()
    model_l = (model or "").strip().lower()

    try:
        yr = int(year)
    except (ValueError, TypeError):
        yr = 0

    for rule in _KNOWN_ISSUES:
        if rule["make"].lower() != make_l:
            continue
        if yr not in rule["years"]:
            continue
        if not any(m in model_l or model_l in m for m in rule["models"]):
            continue
        issues.append({
            "niveau":      rule["niveau"],
            "titre":       rule["titre"],
            "description": rule["description"],
            "action":      rule["action"],
            "url":         rule["url"],
        })

    tc_url = (
        f"https://wwwapps.tc.gc.ca/Saf-Sec-Sur/7/VRDB-BDRV/"
        f"search-recherche/s.aspx?vins={vin.upper()}&lang=fr"
        if vin and len(vin) == 17
        else "https://tc.canada.ca/fr/securite-automobile/rappels-securite-vehicules"
    )
    issues.append({
        "niveau":      "info",
        "titre":       "Vérifier les rappels Transports Canada",
        "description": "Consultez la base officielle pour tout rappel actif sur ce véhicule.",
        "action":      "Rechercher par NIV sur le site de Transports Canada",
        "url":         tc_url,
    })

    return issues
