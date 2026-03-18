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
    """
    Decodes a VIN number via the free NHTSA API.
    Returns basic vehicle information.
    """
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
            "DriveType", "Doors", "PlantCountry"
        ]

        for item in results:
            variable = item.get("Variable", "")
            value = item.get("Value", "")
            if variable in important_fields and value and value != "Not Applicable":
                info[variable] = value

        return {
            "vin": vin,
            "decoded": info,
            "source": "NHTSA"
        }

    except Exception as e:
        return {"error": f"Impossible de décoder le VIN : {str(e)}"}


# =============================
# SAFETY RECALLS (NHTSA - Free)
# =============================

def get_recalls(make: str, model: str, year: str) -> dict:
    """
    Retrieves safety recalls via NHTSA API.
    """
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
# FULL VEHICLE REPORT
# =============================

def get_vehicle_report(vin: str) -> dict:
    """
    Generates a complete free report for a given VIN.
    Combines NHTSA data + Gemini analysis.
    """

    # Step 1 — Decode VIN
    vin_info = decode_vin(vin)
    if "error" in vin_info:
        return vin_info

    decoded = vin_info.get("decoded", {})
    make = decoded.get("Make", "")
    model = decoded.get("Model", "")
    year = decoded.get("ModelYear", "")

    # Step 2 — Safety recalls
    recalls_info = {}
    if make and model and year:
        recalls_info = get_recalls(make, model, year)

    # Step 3 — Gemini analysis
    prompt = f"""
    Tu es AutoAgent 229Voitures, expert automobile au Canada.
    Génère un rapport VIN court et structuré en français.

    VIN : {vin}
    DONNÉES NHTSA : {decoded}
    RAPPELS : {recalls_info}

    Utilise EXACTEMENT ce format — sois concis, max 2-3 lignes par section :

    🔍 RAPPORT VIN — {vin}

    🚗 VÉHICULE
    • Marque/Modèle/Année : [valeur]
    • Carrosserie : [valeur] · [portes] portes
    • Moteur : [cylindrée] · [carburant]
    • Transmission : [valeur]

    ⚠️ RAPPELS DE SÉCURITÉ
    [Si aucun rappel] ✅ Aucun rappel confirmé pour ce VIN
    [Si rappels] ⚠️ [nombre] rappel(s) — [composant principal concerné]
    • Vérifier auprès d'un concessionnaire avec le VIN

    🔧 POINTS À SURVEILLER
    • [problème 1 connu pour ce modèle/année — 1 ligne]
    • [problème 2 — 1 ligne]
    • [problème 3 — 1 ligne]

    💰 VALEUR MARCHÉ CANADA
    • Fourchette estimée : [min] $ — [max] $
    • Prix moyen : ~ [valeur] $

    🎯 RECOMMANDATION
    [Acheter ✅ / Inspecter ⚠️ / Éviter ❌] — 1 phrase d'explication

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
        "recalls": recalls_info,
        "full_report": response.text,
        "sources": [
            "NHTSA (vpic.nhtsa.dot.gov)",
            "NHTSA Recalls (api.nhtsa.gov)",
            "Google Search via Gemini"
        ]
    }