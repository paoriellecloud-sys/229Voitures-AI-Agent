from google import genai
from google.genai import types
from modules.scraper import analyze_listing, compare_listings, search_and_analyze
from modules.vin_checker import get_vehicle_report
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# =============================
# IN-MEMORY SESSION STORE
# =============================

# Stores conversation history per user
# Format: { user_id: { "history": [...], "context": {...} } }
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
                "last_listings": [],  # last vehicles found
                "viewed_urls": [],    # URLs the user has looked at
                "last_intent": None,
            }
        }
    return sessions[user_id]


def update_context(user_id: str, intent_data: dict, response: str):
    """Updates session context based on conversation."""
    session = get_session(user_id)
    ctx = session["context"]

    # Extract budget if mentioned
    budget_match = re.search(r'\b(\d{4,6})\s*\$', response + " " + intent_data.get("query", ""))
    if budget_match:
        ctx["budget"] = int(budget_match.group(1))

    # Track last intent
    ctx["last_intent"] = intent_data.get("intent")

    # Track viewed URLs
    urls = intent_data.get("urls", [])
    if urls:
        ctx["viewed_urls"].extend(urls)
        ctx["viewed_urls"] = list(set(ctx["viewed_urls"]))[-10:]  # keep last 10


def build_context_summary(user_id: str) -> str:
    """Builds a context summary to inject into prompts."""
    session = get_session(user_id)
    ctx = session["context"]
    history = session["history"]

    parts = []

    if ctx["budget"]:
        parts.append(f"Budget mentionné: {ctx['budget']}$")
    if ctx["preferred_make"]:
        parts.append(f"Marque préférée: {ctx['preferred_make']}")
    if ctx["preferred_model"]:
        parts.append(f"Modèle préféré: {ctx['preferred_model']}")
    if ctx["last_listings"]:
        listings_summary = ", ".join([f"#{i+1} {l}" for i, l in enumerate(ctx["last_listings"][:3])])
        parts.append(f"Derniers véhicules trouvés: {listings_summary}")
    if ctx["viewed_urls"]:
        parts.append(f"Annonces consultées: {len(ctx['viewed_urls'])}")

    context_str = "\n".join(parts) if parts else ""

    # Build conversation history (last 6 exchanges)
    history_str = ""
    for msg in history[-6:]:
        role = "Utilisateur" if msg["role"] == "user" else "Agent"
        history_str += f"{role}: {msg['content'][:200]}\n"

    return context_str, history_str


# =============================
# SYSTEM PROMPTS
# =============================

SYSTEM_PROMPT = """
Tu es AutoAgent 229Voitures, compagnon automobile expert au Canada.

Ton rôle est d'ACCOMPAGNER l'utilisateur dans son choix de véhicule comme un ami expert.

Règles STRICTES :
- Réponds en maximum 4-5 phrases courtes et directes
- Toujours en français, toujours en dollars canadiens (CAD)
- Sois honnête : si tu n'as pas de données vérifiées, dis-le
- Rappelle toujours les préférences et le budget de l'utilisateur si tu les connais
- Termine TOUJOURS par une question ou suggestion pour guider l'utilisateur
- Si l'utilisateur hésite, aide-le à comparer ou à prendre une décision
- Si tu as trouvé des véhicules, propose toujours la prochaine étape :
  * Vérifier le VIN
  * Comparer deux options
  * Contacter le concessionnaire
  * Voir d'autres options similaires
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
- CHAT: general question, advice
- SEARCH: user wants to find listings (keywords: trouve, cherche, montre, propose, liste, donne moi)
- ANALYZE_URL: message contains exactly 1 URL
- COMPARE_URLS: message contains 2+ URLs
- CHECK_VIN: message contains a VIN (17 alphanumeric characters)
- FOLLOWUP: user is responding to a previous suggestion (ex: "le 2", "oui", "compare-les", "vérifie le vin", "montre-moi plus")

For FOLLOWUP, set followup_action to one of:
- "select_listing" (user picks a number like "le 2", "le premier")
- "check_vin" (user wants VIN check)
- "compare" (user wants comparison)
- "more_results" (user wants more options)
- "contact_dealer" (user wants dealer info)
- "yes" or "no" (simple confirmation)

For SEARCH, extract:
- query: the vehicle search terms
- site: dealer domain if mentioned, null otherwise
- count: number of results requested (default 2)

Return ONLY the JSON, no explanation.
"""


# =============================
# INTENT DETECTION
# =============================

def detect_intent(message: str, context_summary: str) -> dict:
    """Detects user intent with conversation context."""
    prompt = INTENT_PROMPT.format(message=message, context=context_summary)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    try:
        raw = response.text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    return {
        "intent": "CHAT",
        "urls": [],
        "vin": None,
        "query": message,
        "site": None,
        "count": 2,
        "followup_action": None
    }


# =============================
# HANDLE FOLLOWUP
# =============================

def handle_followup(user_id: str, intent_data: dict, history_str: str, context_summary: str) -> dict:
    """Handles followup messages based on conversation context."""
    session = get_session(user_id)
    ctx = session["context"]
    action = intent_data.get("followup_action")

    # User selected a listing by number
    if action == "select_listing" and ctx["last_listings"]:
        listings_text = "\n".join([f"#{i+1}: {l}" for i, l in enumerate(ctx["last_listings"])])
        prompt = f"""
        {SYSTEM_PROMPT}

        Conversation history:
        {history_str}

        Context: {context_summary}
        Available listings:
        {listings_text}

        The user selected one of these listings. Identify which one and provide:
        - Brief summary of the selected vehicle
        - Your recommendation
        - Ask if they want to: check VIN, compare with another, or contact the dealer

        Respond in French, max 4 sentences.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return {"intent": "FOLLOWUP", "response": response.text}

    # User wants VIN check
    elif action == "check_vin":
        prompt = f"""
        {SYSTEM_PROMPT}

        Conversation history:
        {history_str}

        The user wants to check the VIN of a vehicle we discussed.
        Ask them to provide the VIN number, or if we already have it, confirm which vehicle they mean.
        Respond in French, max 2 sentences.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return {"intent": "FOLLOWUP", "response": response.text}

    # User wants comparison
    elif action == "compare" and len(ctx["last_listings"]) >= 2:
        listings_text = "\n".join([f"#{i+1}: {l}" for i, l in enumerate(ctx["last_listings"][:3])])
        prompt = f"""
        {SYSTEM_PROMPT}

        The user wants to compare vehicles from our conversation.
        Available listings:
        {listings_text}

        Context: {context_summary}

        Compare these vehicles concisely and recommend the best one.
        Consider the user's budget if known.
        Respond in French, max 5 sentences.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return {"intent": "FOLLOWUP", "response": response.text}

    # User wants more results
    elif action == "more_results":
        last_query = ctx.get("last_query", "véhicule occasion Canada")
        result = search_and_analyze(query=last_query, count=3)
        return {
            "intent": "SEARCH",
            "response": result.get("analysis", ""),
            "urls_found": result.get("urls_found", []),
            "scraped_count": result.get("scraped_count", 0)
        }

    # General followup
    else:
        prompt = f"""
        {SYSTEM_PROMPT}

        Conversation history:
        {history_str}

        Context: {context_summary}

        Continue helping the user naturally based on the conversation.
        Respond in French, max 4 sentences.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        return {"intent": "FOLLOWUP", "response": response.text}


# =============================
# SMART ROUTER — SINGLE ENTRY POINT
# =============================

def smart_chat(message: str, user_id: str = "default") -> dict:
    """
    Single entry point for all user messages.
    Maintains conversation memory and guides the user proactively.
    """

    session = get_session(user_id)
    context_summary, history_str = build_context_summary(user_id)

    # Add user message to history
    session["history"].append({"role": "user", "content": message})

    # Detect intent with context
    intent_data = detect_intent(message, context_summary)
    intent = intent_data.get("intent", "CHAT")

    result = {}

    # Route to the right function
    if intent == "FOLLOWUP":
        result = handle_followup(user_id, intent_data, history_str, context_summary)

    elif intent == "CHECK_VIN" and intent_data.get("vin"):
        vin_result = get_vehicle_report(intent_data["vin"])
        result = {"intent": "CHECK_VIN", "response": vin_result}

    elif intent == "COMPARE_URLS" and len(intent_data.get("urls", [])) >= 2:
        compare_result = compare_listings(intent_data["urls"][0], intent_data["urls"][1])
        result = {
            "intent": "COMPARE_URLS",
            "response": compare_result.get("comparison", ""),
            "urls": intent_data["urls"]
        }

    elif intent == "ANALYZE_URL" and len(intent_data.get("urls", [])) >= 1:
        analyze_result = analyze_listing(intent_data["urls"][0])
        result = {
            "intent": "ANALYZE_URL",
            "response": analyze_result.get("analysis", ""),
            "url": intent_data["urls"][0],
            "scraped": analyze_result.get("scraped", False)
        }

    elif intent == "SEARCH" and intent_data.get("query"):
        search_result = search_and_analyze(
            query=intent_data["query"],
            site=intent_data.get("site"),
            count=intent_data.get("count", 2)
        )
        # Save listings to context for followup
        session["context"]["last_listings"] = search_result.get("urls_found", [])
        session["context"]["last_query"] = intent_data.get("query", "")

        # Add follow-up suggestion to response
        base_response = search_result.get("analysis", "")
        followup = "\n\nSouhaitez-vous que je vérifie le VIN d'un de ces véhicules, ou voulez-vous les comparer entre eux ?"

        result = {
            "intent": "SEARCH",
            "response": base_response + followup,
            "urls_found": search_result.get("urls_found", []),
            "scraped_count": search_result.get("scraped_count", 0)
        }

    else:
        # CHAT with full context
        full_prompt = f"""
        {SYSTEM_PROMPT}

        Conversation history:
        {history_str}

        Context about this user: {context_summary}

        User message: {message}
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        result = {"intent": "CHAT", "response": response.text}

    # Save response to history
    response_text = result.get("response", "")
    if isinstance(response_text, str):
        session["history"].append({"role": "assistant", "content": response_text})

    # Update context
    update_context(user_id, intent_data, response_text if isinstance(response_text, str) else "")

    # Keep history manageable (last 20 messages)
    session["history"] = session["history"][-20:]

    return result