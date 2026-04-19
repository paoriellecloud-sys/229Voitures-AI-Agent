"""
Response Builder - 229Voitures
Responsabilite UNIQUE : construire la reponse finale via Gemini.
Gemini fait SEULEMENT la redaction - pas la logique.
"""

import os
import google.generativeai as genai
from modules.formatters import format_vehicles_html_block
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/229voitures/.env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = "gemini-2.5-flash"

SYSTEM_PROMPT_CORE = """Tu es 229Voitures AI Agent, expert automobile au Quebec.
Tu proteges les acheteurs ET tu facilites la prise de RDV avec les concessionnaires partenaires.
Tu es direct, honnete et proactif comme un ami expert.

REGLES ABSOLUES :
- Tu PEUX et DOIS proposer le formulaire de contact quand l'utilisateur est interesse
- Si des PROPOSITIONS ACTIVES sont listees, parle UNIQUEMENT de ces vehicules
- Ne jamais inventer de vehicule ou de prix
- Repondre en francais sauf si l'utilisateur ecrit en anglais
- Maximum 3-4 phrases de conseil
- Ne jamais lister Prix, km, VIN en texte si les fiches HTML sont affichees
- Terminer par UNE seule question ou action concrete
- Quand un utilisateur dit oui, je suis interesse, je veux le voir → proposer le RDV immediatement

PROTECTION ACHETEUR :
- Taxes QC : TPS 5% + TVQ 9.975% = 14.975% total
- Pas de droit de remord pour les autos au Quebec
- Frais de dossier, protection peinture, Vinlock = OPTIONNELS
- Recommander inspection independante pour tout vehicule d'occasion
"""


def _get_model():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_PROMPT_CORE,
    )


def build_search_response(
    message: str,
    vehicles: list,
    session: dict,
    history_str: str = "",
) -> dict:
    """
    Construit la reponse pour un intent SEARCH.
    Gemini commente les vehicules trouves.
    """
    vehicle_shown = {}
    html_cards = ""

    if vehicles:
        for i, v in enumerate(vehicles, 1):
            vehicle_shown[i] = v
        html_cards = format_vehicles_html_block(vehicles[:3])

    active_props = _format_propositions(vehicle_shown)

    prompt = f"""{active_props}

Message utilisateur: {message}

{"Rédige UNE seule phrase d'accroche (max 20 mots) sans mentionner aucun véhicule spécifique par nom/année/couleur. Ensuite pose UNE question de suivi courte. Les fiches HTML affichent déjà tous les détails — ne les répète pas. Exemple correct: \"Voici ce que j'ai trouvé pour vous. Laquelle vous intéresse ?\" Exemple incorrect: \"J'ai un Kona 2021 noir à 18 589$...\"" if vehicles else "Aucun vehicule trouve. Propose des alternatives ou une alerte email. Sois proactif."}
"""

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        text = response.text
    except Exception as e:
        text = f"Desolé, une erreur est survenue. Veuillez reessayer."
        print(f"[response_builder] Erreur Gemini SEARCH: {e}")

    return {
        "response": text,
        "html_cards": html_cards,
        "vehicle_shown": vehicle_shown,
        "intent": "SEARCH",
    }


def build_chat_response(
    message: str,
    session: dict,
    history_str: str = "",
    vehicle_shown: dict = None,
    selected_vehicle: dict = None,
) -> dict:
    """
    Construit la reponse pour un intent CHAT ou FOLLOWUP.
    Gemini repond avec le contexte des propositions actives.
    """
    vehicle_shown = vehicle_shown or {}
    active_props = _format_propositions(vehicle_shown)

    selected_context = ""
    if selected_vehicle:
        y = selected_vehicle.get("year", "")
        mk = selected_vehicle.get("make", "")
        mo = selected_vehicle.get("model", "")
        pr = selected_vehicle.get("price", "")
        dl = selected_vehicle.get("dealer_name", "")
        km = selected_vehicle.get("mileage", "")
        selected_context = f"\nVehicule selectionne par l'utilisateur: {y} {mk} {mo} — {pr}$ — {dl} — {km} km\n"

    user_data = session.get("user_data", {})
    budget = user_data.get("budget")
    budget_context = f"\nBudget utilisateur: {budget}$\n" if budget else ""

    prompt = f"""
{active_props}
{selected_context}
{budget_context}

Historique recent:
{history_str[-3000:] if history_str else ""}

Message utilisateur: {message}

Reponds directement et utilise les propositions actives si l'utilisateur y fait reference.
"""

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        text = response.text
    except Exception as e:
        text = "Desolé, une erreur est survenue. Veuillez reessayer."
        print(f"[response_builder] Erreur Gemini CHAT: {e}")

    return {
        "response": text,
        "html_cards": "",
        "vehicle_shown": vehicle_shown,
        "intent": "CHAT",
    }


def build_no_results_response(
    message: str,
    query: str,
    session: dict,
    history_str: str = "",
) -> dict:
    """
    Reponse quand aucun vehicule n'est trouve.
    Gemini propose des alternatives.
    """
    prompt = f"""
Historique recent:
{history_str[-2000:] if history_str else ""}

Message utilisateur: {message}
Recherche effectuee: {query}

Aucun vehicule trouve dans l'inventaire pour cette recherche.
Sois proactif :
1. Propose des modeles alternatifs similaires disponibles
2. Si vraiment rien de similaire, propose une alerte email
3. Ne dis jamais "je n'ai rien" sans proposer une alternative concrete
4. Reste positif et orienté solution
"""

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        text = response.text
    except Exception as e:
        text = "Je n'ai pas trouve ce vehicule. Voulez-vous que je cherche des modeles similaires ?"
        print(f"[response_builder] Erreur Gemini NO_RESULTS: {e}")

    return {
        "response": text,
        "html_cards": "",
        "vehicle_shown": {},
        "intent": "SEARCH",
    }


def _format_propositions(vehicle_shown: dict) -> str:
    """Formate les propositions actives pour le prompt Gemini."""
    if not vehicle_shown:
        return ""

    lines = ["\n=== PROPOSITIONS ACTIVES DANS CETTE SESSION ==="]
    for k, v in sorted(vehicle_shown.items()):
        lines.append(
            f"Proposition {k} : {v.get('year','')} {v.get('make','')} {v.get('model','')} "
            f"— {v.get('price','')}$ — {v.get('dealer_name','')} ({v.get('city','')}) "
            f"— Couleur: {v.get('color','')} — Carburant: {v.get('fuel_type','')} "
            f"— Traction: {v.get('drivetrain','')} — Km: {v.get('mileage','')}"
        )
    lines.append("===============================================")
    lines.append(
        "REGLE ABSOLUE STRICTE :\n"
        "1. Tu ne peux parler QUE des vehicules listés ci-dessus\n"
        "2. Si les fiches HTML sont affichées, tu ne répètes PAS les données techniques\n"
        "3. Tu ne mentionnes JAMAIS un vehicule qui n'est pas dans cette liste\n"
        "4. Ton rôle = commenter et conseiller en 2-3 phrases MAX\n"
        "5. Format: UNE phrase d'intro + observation pertinente + UNE question"
    )
    return "\n".join(lines) + "\n"
