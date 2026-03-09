import requests
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# =============================
# DECODER LE VIN (NHTSA - Gratuit)
# =============================

def decode_vin(vin: str) -> dict:
    """
    Décode un numéro VIN via l'API gratuite NHTSA (USA).
    Retourne les infos de base du véhicule.
    """
    try:
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"
        response = requests.get(url, timeout=10)
        data = response.json()

        results = data.get("Results", [])

        # Extraire les infos importantes
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
            "source": "NHTSA (National Highway Traffic Safety Administration)"
        }

    except Exception as e:
        return {"error": f"Impossible de décoder le VIN : {str(e)}"}


# =============================
# RAPPELS DE SÉCURITÉ (NHTSA - Gratuit)
# =============================

def get_recalls(make: str, model: str, year: str) -> dict:
    """
    Récupère les rappels de sécurité via NHTSA.
    """
    try:
        url = f"https://api.nhtsa.gov/recalls/recallsByVehicle?make={make}&model={model}&modelYear={year}"
        response = requests.get(url, timeout=10)
        data = response.json()

        recalls = data.get("results", [])

        if not recalls:
            return {
                "count": 0,
                "message": "✅ Aucun rappel de sécurité trouvé pour ce véhicule.",
                "recalls": []
            }

        recall_list = []
        for r in recalls[:5]:  # Limiter à 5 rappels
            recall_list.append({
                "component": r.get("Component", "N/A"),
                "summary": r.get("Summary", "N/A")[:200],
                "consequence": r.get("Conséquence", r.get("Consequence", "N/A"))[:200],
                "remedy": r.get("Remedy", "N/A")[:200]
            })

        return {
            "count": len(recalls),
            "message": f"⚠️ {len(recalls)} rappel(s) de sécurité trouvé(s).",
            "recalls": recall_list
        }

    except Exception as e:
        return {"error": f"Impossible de récupérer les rappels : {str(e)}"}


# =============================
# RAPPORT COMPLET (CarFax Gratuit)
# =============================

def get_vehicle_report(vin: str) -> dict:
    """
    Génère un rapport complet gratuit pour un VIN donné.
    Combine NHTSA + analyse Gemini.
    """

    # Étape 1 — Décoder le VIN
    vin_info = decode_vin(vin)

    if "error" in vin_info:
        return vin_info

    decoded = vin_info.get("decoded", {})
    make = decoded.get("Make", "")
    model = decoded.get("Model", "")
    year = decoded.get("ModelYear", "")

    # Étape 2 — Rappels de sécurité
    recalls_info = {}
    if make and model and year:
        recalls_info = get_recalls(make, model, year)

    # Étape 3 — Analyse Gemini
    prompt = f"""
    Tu es un expert automobile. Génère un rapport de vérification de véhicule basé sur ces informations.

    VIN : {vin}

    INFORMATIONS DU VÉHICULE (source NHTSA) :
    {decoded}

    RAPPELS DE SÉCURITÉ :
    {recalls_info}

    Génère un rapport structuré avec :

    ## 🚗 INFORMATIONS DU VÉHICULE
    (marque, modèle, année, moteur, transmission, carburant)

    ## ⚠️ RAPPELS DE SÉCURITÉ
    (liste des rappels avec recommandations)

    ## 🔍 POINTS À VÉRIFIER
    (basé sur les problèmes connus de ce modèle/année)

    ## 💰 VALEUR MARCHANDE ESTIMÉE
    (prix moyen au Canada pour ce véhicule)

    ## 🎯 RECOMMANDATION FINALE
    (acheter / inspecter / éviter)

    Réponds en français de façon claire et professionnelle.
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
