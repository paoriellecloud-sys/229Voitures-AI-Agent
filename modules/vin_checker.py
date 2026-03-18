import requests
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# =============================
# DECODE VIN (NHTSA - Free)
# =============================

def decode_vin(vin: str) -> dict:
    """Decodes a VIN number via the free NHTSA API."""
    try:
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"
        response = requests.get(url, timeout=10)
        data = response.json()
        results = data.get("Results", [])

        info = {}
        important_fields = [
            "Make", "Model", "ModelYear", "VehicleType",
            "BodyClass", "EngineCylinders", "DisplacementL",
            "FuelTypePrimary", "TransmissionStyle",
            "DriveType", "Doors", "PlantCountry",
            "ManufacturerName", "PlantCity", "PlantState",
            "Series", "Trim", "GVWR"
        ]

        for item in results:
            variable = item.get("Variable", "")
            value = item.get("Value", "")
            if variable in important_fields and value and value != "Not Applicable":
                info[variable] = value

        return {"vin": vin, "decoded": info, "source": "NHTSA"}

    except Exception as e:
        return {"error": f"Impossible de décoder le VIN : {str(e)}"}


# =============================
# DECODE VIN CHARACTERS
# =============================

def decode_vin_chars(vin: str) -> dict:
    """
    Decodes VIN characters to extract country, manufacturer,
    vehicle type, model year, assembly plant and usage type.
    """
    if len(vin) != 17:
        return {"error": "VIN invalide — doit contenir 17 caractères"}

    # Position 1 — Country of manufacture
    country_map = {
        '1': 'États-Unis', '2': 'Canada', '3': 'Mexique',
        '4': 'États-Unis', '5': 'États-Unis', '6': 'Australie',
        '7': 'Nouvelle-Zélande', '8': 'Argentine', '9': 'Brésil',
        'J': 'Japon', 'K': 'Corée du Sud', 'L': 'Chine',
        'S': 'Royaume-Uni', 'V': 'France', 'W': 'Allemagne',
        'X': 'Russie', 'Y': 'Suède', 'Z': 'Italie'
    }

    # Position 10 — Model year
    year_map = {
        'A': 2010, 'B': 2011, 'C': 2012, 'D': 2013, 'E': 2014,
        'F': 2015, 'G': 2016, 'H': 2017, 'J': 2018, 'K': 2019,
        'L': 2020, 'M': 2021, 'N': 2022, 'P': 2023, 'R': 2024,
        'S': 2025, 'T': 2026,
        '1': 2001, '2': 2002, '3': 2003, '4': 2004, '5': 2005,
        '6': 2006, '7': 2007, '8': 2008, '9': 2009
    }

    country = country_map.get(vin[0], 'Inconnu')
    model_year = year_map.get(vin[9], 'Inconnu')
    assembly_plant = vin[10]
    serial = vin[11:]

    # Position 7 — Vehicle type/usage hint
    usage_hint = "Personnel"
    if vin[6] in ['T', 'U', 'V']:
        usage_hint = "Possiblement commercial/fleet"

    return {
        "country_of_manufacture": country,
        "model_year_from_vin": model_year,
        "assembly_plant_code": assembly_plant,
        "serial_number": serial,
        "usage_hint": usage_hint,
        "vin_valid_format": len(vin) == 17 and vin.isalnum()
    }


# =============================
# SAFETY RECALLS (NHTSA - Free)
# =============================

def get_recalls(make: str, model: str, year: str) -> dict:
    """Retrieves safety recalls via NHTSA API."""
    try:
        url = f"https://api.nhtsa.gov/recalls/recallsByVehicle?make={make}&model={model}&modelYear={year}"
        response = requests.get(url, timeout=10)
        data = response.json()
        recalls = data.get("results", [])

        if not recalls:
            return {"count": 0, "message": "Aucun rappel trouvé.", "recalls": []}

        recall_list = []
        for r in recalls[:5]:
            recall_list.append({
                "component": r.get("Component", "N/A"),
                "summary": r.get("Summary", "N/A")[:200],
                "remedy": r.get("Remedy", "N/A")[:200]
            })

        return {
            "count": len(recalls),
            "message": f"{len(recalls)} rappel(s) trouvé(s).",
            "recalls": recall_list
        }

    except Exception as e:
        return {"error": f"Impossible de récupérer les rappels : {str(e)}"}


# =============================
# NHTSA COMPLAINTS (Free)
# =============================

def get_complaints(make: str, model: str, year: str) -> dict:
    """Retrieves owner complaints via NHTSA API."""
    try:
        url = f"https://api.nhtsa.gov/complaints/complaintsByVehicle?make={make}&model={model}&modelYear={year}"
        response = requests.get(url, timeout=10)
        data = response.json()
        complaints = data.get("results", [])

        if not complaints:
            return {"count": 0, "top_issues": []}

        # Group by component
        components = {}
        for c in complaints:
            comp = c.get("components", "Autre")
            components[comp] = components.get(comp, 0) + 1

        # Sort by frequency
        top = sorted(components.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "count": len(complaints),
            "top_issues": [{"component": k, "complaints": v} for k, v in top]
        }

    except Exception as e:
        return {"count": 0, "top_issues": [], "error": str(e)}


# =============================
# MILEAGE VALIDATION
# =============================

def validate_mileage(year: str, mileage: int = None) -> dict:
    """
    Checks if mileage is reasonable for the vehicle year.
    Average Canadian driver: ~20,000 km/year.
    """
    if not mileage or not year:
        return {"status": "unknown", "message": "Kilométrage non fourni"}

    try:
        current_year = 2026
        vehicle_age = current_year - int(year)
        expected_avg = vehicle_age * 20000
        expected_low = vehicle_age * 10000
        expected_high = vehicle_age * 30000

        if mileage < expected_low:
            status = "suspect_low"
            msg = f"Kilométrage très bas ({mileage:,} km) pour un véhicule de {vehicle_age} ans — vérifier l'odomètre"
        elif mileage > expected_high:
            status = "high"
            msg = f"Kilométrage élevé ({mileage:,} km) — prévoir entretien majeur"
        else:
            status = "normal"
            msg = f"Kilométrage normal ({mileage:,} km) pour un véhicule de {vehicle_age} ans"

        return {
            "status": status,
            "message": msg,
            "expected_average": expected_avg,
            "vehicle_age_years": vehicle_age
        }
    except Exception:
        return {"status": "unknown", "message": "Impossible de valider le kilométrage"}


# =============================
# FULL VEHICLE REPORT
# =============================

def get_vehicle_report(vin: str, mileage: int = None) -> dict:
    """
    Generates a complete free report for a given VIN.
    Combines NHTSA + VIN decoding + complaints + mileage validation + Gemini analysis.
    """

    # Step 1 — Decode VIN
    vin_info = decode_vin(vin)
    if "error" in vin_info:
        return vin_info

    decoded = vin_info.get("decoded", {})
    make = decoded.get("Make", "")
    model = decoded.get("Model", "")
    year = decoded.get("ModelYear", "")

    # Step 2 — VIN character analysis
    vin_chars = decode_vin_chars(vin)

    # Step 3 — Safety recalls
    recalls_info = {}
    if make and model and year:
        recalls_info = get_recalls(make, model, year)

    # Step 4 — Owner complaints
    complaints_info = {}
    if make and model and year:
        complaints_info = get_complaints(make, model, year)

    # Step 5 — Mileage validation
    mileage_info = validate_mileage(year, mileage)

    # Step 6 — Gemini analysis
    prompt = f"""
    Tu es AutoAgent 229Voitures, expert automobile au Canada.
    Génère un rapport VIN concis et structuré en français.

    VIN : {vin}
    DONNÉES NHTSA : {decoded}
    DÉCODAGE VIN : {vin_chars}
    RAPPELS : {recalls_info}
    PLAINTES PROPRIÉTAIRES : {complaints_info}
    VALIDATION KILOMÉTRAGE : {mileage_info}

    Utilise EXACTEMENT ce format — sois concis, max 2-3 lignes par section :

    🔍 RAPPORT VIN — {vin}

    🚗 VÉHICULE
    • [Marque] [Modèle] [Année] · [Carrosserie] · [Portes] portes
    • Moteur : [cylindrée] · [carburant]
    • Transmission : [valeur] · Traction : [valeur]
    • Assemblé : [pays] · Usage : [Personnel/Commercial]

    ⚠️ RAPPELS DE SÉCURITÉ
    [Si aucun] ✅ Aucun rappel actif pour ce VIN
    [Si rappels] ⚠️ [nombre] rappel(s) — [composant principal]
    • Action : vérifier auprès d'un concessionnaire certifié

    📊 PLAINTES PROPRIÉTAIRES
    [Si aucune] ✅ Peu de plaintes enregistrées
    [Si plaintes] Top problèmes signalés :
    • [composant 1] — [nombre] plaintes
    • [composant 2] — [nombre] plaintes

    🛣️ KILOMÉTRAGE
    • [statut kilométrage et commentaire]

    🔧 POINTS À SURVEILLER
    • [problème connu 1 pour ce modèle/année]
    • [problème connu 2]
    • [problème connu 3]

    💰 VALEUR MARCHÉ CANADA
    • Fourchette : [min] $ — [max] $
    • Prix moyen : ~ [valeur] $

    🎯 RECOMMANDATION
    [Acheter ✅ / Inspecter ⚠️ / Éviter ❌] — 1 phrase claire

    ⚠️ Données à titre informatif. Vérifiez auprès d'un concessionnaire certifié. 229Voitures n'est pas un conseiller financier.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    return {
        "vin": vin,
        "vehicle_info": decoded,
        "vin_decoded": vin_chars,
        "recalls": recalls_info,
        "complaints": complaints_info,
        "mileage_validation": mileage_info,
        "full_report": response.text,
        "sources": [
            "NHTSA (vpic.nhtsa.dot.gov)",
            "NHTSA Recalls (api.nhtsa.gov)",
            "NHTSA Complaints (api.nhtsa.gov)",
            "Google Search via Gemini"
        ]
    }