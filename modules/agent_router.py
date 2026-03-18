from google import genai
from google.genai import types
from modules.scraper import analyze_listing, compare_listings, search_and_analyze
from modules.vin_checker import get_vehicle_report
from database import log_search
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

sessions = {}


def get_session(user_id: str) -> dict:
    if user_id not in sessions:
        sessions[user_id] = {
            "history": [],
            "context": {
                "budget": None,
                "preferred_make": None,
                "preferred_model": None,
                "preferred_year": None,
                "preferred_trim": None,
                "preferred_transmission": None,
                "last_listings": [],
                "viewed_urls": [],
                "last_intent": None,
            }
        }
    return sessions[user_id]


def update_context(user_id: str, intent_data: dict, response: str):
    session = get_session(user_id)
    ctx = session["context"]
    budget_match = re.search(r'\b(\d{4,6})\s*\$', response + " " + (intent_data.get("query") or ""))
    if budget_match:
        ctx["budget"] = int(budget_match.group(1))
    ctx["last_intent"] = intent_data.get("intent")
    urls = intent_data.get("urls", [])
    if urls:
        ctx["viewed_urls"].extend(urls)
        ctx["viewed_urls"] = list(set(ctx["viewed_urls"]))[-10:]


def build_context_summary(user_id: str):
    session = get_session(user_id)
    ctx = session["context"]
    history = session["history"]
    parts = []
    if ctx["budget"]:
        parts.append(f"Budget mentionné: {ctx['budget']}$")
    if ctx["preferred_make"]:
        parts.append(f"Marque préférée: {ctx['preferred_make']}")
    if ctx["last_listings"]:
        listings_summary = ", ".join([f"#{i+1} {l}" for i, l in enumerate(ctx["last_listings"][:3])])
        parts.append(f"Derniers véhicules trouvés: {listings_summary}")
    context_str = "\n".join(parts) if parts else ""
    history_str = ""
    for msg in history[-6:]:
        role = "Utilisateur" if msg["role"] == "user" else "Agent"
        history_str += f"{role}: {msg['content'][:200]}\n"
    return context_str, history_str


SYSTEM_PROMPT = """
Tu es AutoAgent 229Voitures, compagnon automobile expert au Canada.

RÈGLES DE COMMUNICATION :
- Réponds en maximum 4-5 phrases courtes et directes
- Toujours en français, toujours en dollars canadiens (CAD)
- Sois honnête : si tu n'as pas de données vérifiées, dis-le clairement
- Termine TOUJOURS par une question ou suggestion concrète pour guider l'utilisateur

RÈGLES DE RELANCE INTELLIGENTE :
- Si l'utilisateur mentionne un budget → rappelle-le dans chaque réponse suivante
- Si le prix dépasse le budget mentionné → signale-le immédiatement et propose une alternative
- Si l'utilisateur a vu 2+ véhicules → propose une comparaison directe spontanément
- Si le kilométrage dépasse 100 000 km → propose automatiquement de vérifier le VIN
- Si l'utilisateur dit "c'est cher" ou "trop cher" → cherche des alternatives similaires moins chères
- Si l'utilisateur hésite entre 2 options → pose UNE seule question précise pour l'aider à décider
- Si un prix semble anormalement bas → avertis l'utilisateur d'un risque potentiel (red flag)
- Utilise toujours les informations des échanges précédents pour personnaliser ta réponse

CAPACITÉS DISPONIBLES :
1. RECHERCHE : Trouver des véhicules d'occasion au Canada avec prix et kilométrage réels
2. ANALYSE D'ANNONCE : Analyser une fiche véhicule via son URL
3. COMPARAISON : Comparer 2+ véhicules selon les critères de l'utilisateur avec score
4. VÉRIFICATION VIN : Vérifier l'historique complet d'un véhicule via son numéro VIN
5. TAXES QUÉBEC : Calculer automatiquement TPS (5%) + TVQ (9.975%) = 14.975%
6. COÛT TOTAL DE POSSESSION : Estimer sur 5 ans — assurance, entretien, carburant, dépréciation
7. FIABILITÉ : Donner l'historique de fiabilité, problèmes connus et rappels pour chaque modèle
8. NÉGOCIATION : Donner des arguments précis pour négocier le prix avec le concessionnaire
9. RED FLAGS : Détecter les prix suspects, kilométrages trop bas pour l'année, incohérences
10. RECOMMANDATION PERSONNALISÉE : Après 2-3 échanges, proposer le véhicule idéal selon le profil

CALCUL TAXES QUÉBEC (obligatoire pour toute annonce analysée) :
- TPS fédérale : 5% du prix affiché
- TVQ provinciale : 9.975% du prix affiché
- Total taxes : 14.975%
- Toujours afficher : prix affiché + TPS + TVQ + total estimé

MENTION LÉGALE OBLIGATOIRE (à inclure dans tout calcul financier) :
"⚠️ Estimations à titre informatif. Consultez votre concessionnaire pour un prix final. 229Voitures n'est pas un conseiller financier."
"""

INTENT_PROMPT = """
Analyze this user message and return ONLY a JSON object with the intent and extracted data.

Message: "{message}"
Conversation context: {context}

Return exactly this JSON format:
{{
  "intent": "CHAT" | "SEARCH" | "ANALYZE_URL" | "COMPARE_URLS" | "CHECK_VIN" | "FOLLOWUP",
  "urls": [],
  "vin": null,
  "query": null,
  "site": null,
  "count": 2,
  "followup_action": null
}}

Intent rules:
- CHAT: general question, advice without specific vehicle lookup needed
- SEARCH: use this when ANY of these conditions are met:
  1. User explicitly searches (keywords: trouve, cherche, montre, propose, liste, donne moi)
  2. User mentions a specific vehicle make/model (Toyota, Honda, Kia, Ford, Mazda, Hyundai, etc.)
  3. User mentions a year + vehicle type (ex: "SUV 2021", "berline 2020")
  4. User mentions a budget + vehicle type (ex: "voiture sous 20000$")
  5. User asks about availability, price, or options for a specific model
  Examples that should be SEARCH not CHAT:
  - "Kia Niro PHEV, c'est bien?" → SEARCH (specific model mentioned)
  - "Toyota Corolla 2020 fiable?" → SEARCH (specific model + year)
  - "VUS hybride sous 25000$?" → SEARCH (budget + type)
  - "Honda CRV disponible au Quebec?" → SEARCH (specific model + location)
- ANALYZE_URL: message contains exactly 1 URL
- COMPARE_URLS: message contains 2+ URLs
- CHECK_VIN: message contains a VIN (17 alphanumeric characters)
- FOLLOWUP: user is responding to a previous suggestion (ex: "le 2", "oui", "compare-les", "vérifie le vin", "montre-moi plus")

For FOLLOWUP, set followup_action to one of:
- "select_listing", "check_vin", "compare", "more_results", "contact_dealer", "yes", "no"

For SEARCH extract:
- query: full search terms including make, model, year, trim, budget, location
- site: dealer domain if mentioned, null otherwise
- count: number of results requested (default 2)

Return ONLY the JSON, no explanation.
"""


def detect_intent(message: str, context_summary: str) -> dict:
    prompt = INTENT_PROMPT.format(message=message, context=context_summary)
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    try:
        raw = response.text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {"intent": "CHAT", "urls": [], "vin": None, "query": message, "site": None, "count": 2, "followup_action": None}


def handle_followup(user_id: str, intent_data: dict, history_str: str, context_summary: str) -> dict:
    session = get_session(user_id)
    ctx = session["context"]
    action = intent_data.get("followup_action")

    if action == "select_listing" and ctx["last_listings"]:
        listings_text = "\n".join([f"#{i+1}: {l}" for i, l in enumerate(ctx["last_listings"])])
        prompt = f"{SYSTEM_PROMPT}\nHistorique:\n{history_str}\nContexte: {context_summary}\nAnnonces:\n{listings_text}\nL'utilisateur a sélectionné une annonce. Identifie laquelle et résume-la. Propose: vérifier VIN, comparer, ou contacter le concessionnaire. Max 4 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "check_vin":
        prompt = f"{SYSTEM_PROMPT}\nHistorique:\n{history_str}\nL'utilisateur veut vérifier le VIN. Demande-lui le numéro VIN. Max 2 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "compare" and len(ctx["last_listings"]) >= 2:
        listings_text = "\n".join([f"#{i+1}: {l}" for i, l in enumerate(ctx["last_listings"][:3])])
        prompt = f"{SYSTEM_PROMPT}\nCompare ces véhicules et recommande le meilleur. Budget: {ctx.get('budget', 'non précisé')}$\n{listings_text}\nMax 5 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "more_results":
        last_query = ctx.get("last_query", "véhicule occasion Canada")
        result = search_and_analyze(query=last_query, count=3)
        return {"intent": "SEARCH", "response": result.get("analysis", ""), "urls_found": result.get("urls_found", []), "scraped_count": result.get("scraped_count", 0)}

    else:
        prompt = f"{SYSTEM_PROMPT}\nHistorique:\n{history_str}\nContexte: {context_summary}\nContinue à aider l'utilisateur naturellement. Max 4 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        return {"intent": "FOLLOWUP", "response": response.text}


def smart_chat(message: str, user_id: str = "default") -> dict:
    session = get_session(user_id)
    context_summary, history_str = build_context_summary(user_id)
    session["history"].append({"role": "user", "content": message})
    intent_data = detect_intent(message, context_summary)
    intent = intent_data.get("intent", "CHAT")
    result = {}

    if intent == "FOLLOWUP":
        result = handle_followup(user_id, intent_data, history_str, context_summary)

    elif intent == "CHECK_VIN" and intent_data.get("vin"):
        result = {"intent": "CHECK_VIN", "response": get_vehicle_report(intent_data["vin"])}

    elif intent == "COMPARE_URLS" and len(intent_data.get("urls", [])) >= 2:
        compare_result = compare_listings(intent_data["urls"][0], intent_data["urls"][1])
        result = {"intent": "COMPARE_URLS", "response": compare_result.get("comparison", ""), "urls": intent_data["urls"]}

    elif intent == "ANALYZE_URL" and len(intent_data.get("urls", [])) >= 1:
        analyze_result = analyze_listing(intent_data["urls"][0])
        result = {"intent": "ANALYZE_URL", "response": analyze_result.get("analysis", ""), "url": intent_data["urls"][0], "scraped": analyze_result.get("scraped", False)}

    elif intent == "SEARCH" and intent_data.get("query"):
        search_result = search_and_analyze(query=intent_data["query"], site=intent_data.get("site"), count=intent_data.get("count", 2))
        session["context"]["last_listings"] = search_result.get("urls_found", [])
        session["context"]["last_query"] = intent_data.get("query", "")

        # Log the search for analytics
        try:
            log_search(
                query=intent_data["query"],
                intent="SEARCH",
                results_count=search_result.get("scraped_count", 0)
            )
        except Exception:
            pass

        base_response = search_result.get("analysis", "")
        followup = "\n\nSouhaitez-vous que je vérifie le VIN d'un de ces véhicules, ou voulez-vous les comparer entre eux ?"
        result = {"intent": "SEARCH", "response": base_response + followup, "urls_found": search_result.get("urls_found", []), "scraped_count": search_result.get("scraped_count", 0)}

    else:
        full_prompt = f"{SYSTEM_PROMPT}\nHistorique:\n{history_str}\nContexte: {context_summary}\nMessage: {message}"
        response = client.models.generate_content(model="gemini-2.5-flash", contents=full_prompt, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        result = {"intent": "CHAT", "response": response.text}

    response_text = result.get("response", "")
    if isinstance(response_text, str):
        session["history"].append({"role": "assistant", "content": response_text})
    update_context(user_id, intent_data, response_text if isinstance(response_text, str) else "")
    session["history"] = session["history"][-20:]
    return result