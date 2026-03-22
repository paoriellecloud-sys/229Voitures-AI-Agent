from google import genai
from google.genai import types
from modules.scraper import analyze_listing, compare_listings, search_and_analyze
from modules.vin_checker import get_vehicle_report
from database import log_search
import os
import json
import re
import sqlite3
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
DB_PATH = os.environ.get("DB_PATH", "229voitures.db")

sessions = {}


# =============================
# NETTOYAGE HTML
# =============================

def strip_html(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'"\s*target="_blank"[^>]*>', '', text)
    text = re.sub(r'\s*class="[^"]*">', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


# =============================
# SESSION MANAGEMENT
# =============================

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


# =============================
# INVENTORY CACHE SEARCH
# =============================

def search_inventory_cache(query: str, limit: int = 5) -> list[dict]:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT, vehicle_id TEXT, title TEXT, price REAL, mileage INTEGER,
                year INTEGER, make TEXT, model TEXT, city TEXT, province TEXT,
                dealer_name TEXT, dealer_phone TEXT, vin TEXT, color TEXT,
                transmission TEXT, drivetrain TEXT, fuel_type TEXT, engine TEXT, trim TEXT,
                avg_market_price REAL, price_diff REAL, price_status TEXT,
                tps REAL, tvq REAL, total_taxes REAL, total_with_taxes REAL,
                options TEXT, description TEXT, highway_consumption TEXT, city_consumption TEXT,
                photos TEXT, url TEXT, json_url TEXT, raw_content TEXT, scraped_at TEXT,
                UNIQUE(source, vehicle_id)
            )
        """)
        conn.commit()

        keywords = [k.strip() for k in query.lower().split() if len(k.strip()) > 2]

        conditions = []
        params = []
        for kw in keywords[:5]:
            conditions.append("(LOWER(title) LIKE ? OR LOWER(raw_content) LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%"])

        if not conditions:
            conn.close()
            return []

        sql = f"""
            SELECT url, source, title, price, mileage, raw_content, scraped_at
            FROM inventory_cache
            WHERE {" AND ".join(conditions)}
            ORDER BY scraped_at DESC
            LIMIT ?
        """
        params.append(limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            try:
                raw = json.loads(row["raw_content"]) if row["raw_content"] else {}
            except Exception:
                raw = {}

            results.append({
                "url": row["url"],
                "source": row["source"],
                "title": row["title"],
                "price": row["price"],
                "mileage": row["mileage"],
                "details": raw,
                "scraped_at": row["scraped_at"],
            })

        return results

    except Exception as e:
        print(f"[search_inventory_cache] Erreur: {e}")
        return []


def format_cache_results_for_prompt(results: list[dict]) -> str:
    if not results:
        return ""

    lines = ["=== VÉHICULES DISPONIBLES (données réelles Force Occasion) ===\n"]
    for i, r in enumerate(results, 1):
        d = r.get("details", {})
        annee = d.get("annee", "")
        marque = d.get("marque", "")
        modele = d.get("modele", "")
        prix = d.get("prix", r.get("price", ""))
        prix_marche = d.get("prix_marche", "")
        km = d.get("kilometrage", r.get("mileage", ""))
        ville = d.get("ville", "")
        province = d.get("province", "")
        concessionnaire = d.get("concessionnaire", "")
        telephone = d.get("telephone", "")
        transmission = d.get("transmission", "")
        moteur = d.get("moteur", "")
        carburant = d.get("carburant", "")
        traction = d.get("traction", "")
        couleur = d.get("couleur", "")
        niv = d.get("vin", "") or d.get("niv", "")
        stock = d.get("stock", "") or d.get("id", "") or r.get("vehicle_id", "")
        tps = d.get("tps", "")
        tvq = d.get("tvq", "")
        options = (d.get("options", "") or "")[:200]
        source = r.get("source", "")

        if prix and not tps:
            try:
                prix_num = float(str(prix).replace(",", "").replace("$", "").strip())
                tps = round(prix_num * 0.05, 2)
                tvq = round(prix_num * 0.09975, 2)
                total_taxes = round(prix_num + tps + tvq, 2)
            except Exception:
                total_taxes = ""
        else:
            try:
                prix_num = float(str(prix).replace(",", "").replace("$", "").strip())
                total_taxes = round(prix_num + float(str(tps).replace(",","")) + float(str(tvq).replace(",","")), 2)
            except Exception:
                total_taxes = ""

        line = f"""
Véhicule #{i} — {source}
  Titre      : {annee} {marque} {modele}
  Prix       : {prix}$ (marché moyen: {prix_marche}$)
  Taxes QC   : TPS {tps}$ + TVQ {tvq}$ = Total estimé {total_taxes}$
  Kilométrage: {km} km
  Localisation: {ville}, {province}
  Concessionnaire: {concessionnaire} | Tél: {telephone}
  Moteur     : {moteur} | Transmission: {transmission}
  Carburant  : {carburant} | Traction: {traction}
  Couleur    : {couleur}
  VIN        : {niv}
  N° Stock   : {stock}
  Options    : {options}
  URL fiche  : {r.get('url', '')}
"""
        lines.append(line)

    lines.append("\n=== FIN DES DONNÉES FORCE OCCASION ===")
    return "\n".join(lines)


# =============================
# SYSTEM PROMPT
# =============================

SYSTEM_PROMPT = """
Tu es AutoAgent 229Voitures, compagnon automobile expert au Canada.
Tu combines l'expertise d'un conseiller financier automobile, d'un mécanicien et d'un négociateur professionnel.

RÈGLES DE COMMUNICATION :
- Réponds en maximum 4-5 phrases courtes et directes
- Toujours en français, toujours en dollars canadiens (CAD)
- Sois honnête : si tu n'as pas de données vérifiées, dis-le clairement
- Termine TOUJOURS par une question ou suggestion concrète pour guider l'utilisateur
- La date actuelle est mars 2026 — distingue clairement événements passés vs à venir
- Ne jamais présenter un événement passé comme "à venir"
- NE JAMAIS inclure de HTML brut dans ta réponse (pas de class=, target=, href= en texte)
- Les liens doivent être en format markdown uniquement : [texte](url)

RÈGLES SUR LES DONNÉES D'INVENTAIRE :
- Quand des données FORCE OCCASION sont fournies, utilise TOUJOURS ces données réelles — ne pas inventer
- Affiche le prix EXACT de la fiche, jamais "estimation"
- Affiche le kilométrage EXACT, jamais "environ"
- Affiche le nom du concessionnaire et la ville EXACTS
- Calcule les taxes avec les chiffres exacts TPS/TVQ fournis
- Si un prix_marche est disponible : compare le prix demandé au prix du marché
- Si prix < prix_marche → signale que c'est sous le marché (bonne affaire potentielle)
- Si prix > prix_marche → signale que c'est au-dessus du marché (négocier)
- Le VIN est toujours disponible dans les données Force Occasion — ne jamais dire que tu ne l'as pas si les données du cache sont présentes
- Toujours afficher le N° Stock dans la présentation des véhicules Force Occasion pour faciliter la recherche chez le concessionnaire

RÈGLES DE RELANCE INTELLIGENTE :
- Si l'utilisateur mentionne un budget → rappelle-le dans chaque réponse suivante
- Si le prix dépasse le budget mentionné → signale-le immédiatement et propose une alternative
- Si l'utilisateur a vu 2+ véhicules → propose une comparaison directe spontanément
- Si le kilométrage dépasse 100 000 km → propose automatiquement de vérifier le VIN
- Si l'utilisateur dit "c'est cher" → cherche des alternatives similaires moins chères
- Si l'utilisateur hésite → pose UNE seule question précise pour l'aider à décider
- Si un prix semble anormalement bas → avertis l'utilisateur d'un red flag potentiel

FLOW DE QUALIFICATION CLIENT (inspiré de la fiche invité CCAQ) :
Quand un utilisateur commence une recherche sans préciser ses besoins, guide-le avec ces questions dans l'ordre :
1. Quel type de véhicule ? (VUS, berline, camionnette, cabriolet...)
2. Quelle utilisation principale ? (famille, travail, plaisir, ville, longues distances)
3. Quel budget mensuel ou total ?
4. Comptant initial disponible ?
5. Location ou achat ?
6. Véhicule d'échange ? (si oui, obtenir modèle, année, km)
7. Critères prioritaires ? (espace, sécurité, économie, performance, option)
8. Préférence AWD/4x4 pour l'hiver québécois ?
Ne pose qu'UNE question à la fois.

EXPERTISE CONTRAT CCAQ :
A - Prix du véhicule | B - Accessoires | C - Prix de vente (A+B)
D - Réduction | E - Prix après réduction (C-D) | F - Véhicule d'échange
H - Sous-total (E-F-G) | K - TPS 5%×H | L - TVQ 9.975%×H
M - Total véhicule | P - Accessoires F&I | S - Total à payer | W - Solde dû livraison

PRODUITS F&I À SURVEILLER :
- Garantie prolongée, renonciation de dette (2000-3500$), protection peinture/tissu, assurance crédit
- Ces produits peuvent ajouter 3000-8000$ au total — toujours négociables

CAPACITÉS DISPONIBLES :
1. RECHERCHE dans inventaire local Force Occasion (données réelles et vérifiées)
2. RECHERCHE web si pas de résultats locaux
3. ANALYSE D'ANNONCE via URL
4. ANALYSE DE CONTRAT CCAQ par photo
5. COMPARAISON de véhicules avec score
6. VÉRIFICATION VIN complète
7. CALCUL TAXES QC : TPS 5% + TVQ 9.975%
8. FIABILITÉ et rappels par modèle
9. NÉGOCIATION basée sur contrat CCAQ
10. RED FLAGS : prix suspects, frais cachés

FORMAT DE PRÉSENTATION DES VÉHICULES :
🚗 [Année] [Marque] [Modèle] — [Concessionnaire], [Ville]
• Prix : [prix exact]$ | Marché moyen : [prix_marche]$
• Kilométrage : [km exact] km
• Moteur : [moteur] | Transmission : [transmission]
• VIN : [niv]
💰 Taxes QC : [prix]$ + TPS [tps]$ + TVQ [tvq]$ = **[total]$**
🔗 [url fiche]
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
  "followup_action": null,
  "vehicle_filter": null
}}

Intent rules:

- CHAT: Use for ALL evaluation and advice questions:
  * "bonne affaire?", "c'est bien?", "fiable?", "vaut la peine?", "recommandes-tu?"
  * "problemes connus", "rappels", "historique de fiabilite"
  * "X$ c'est raisonnable?", "trop cher?", "bon prix?"
  * Negotiation advice, cost of ownership questions
  IMPORTANT: For evaluation questions, answer the question FIRST directly,
  then offer to search for listings as a follow-up suggestion.

- SEARCH: ONLY when user EXPLICITLY wants to find/list vehicles.
  Requires keywords: trouve, cherche, montre, propose, liste, donne moi
  Also trigger SEARCH for: "je recherche", "je cherche", "je veux trouver"
  Examples → SEARCH:
  - "Trouve moi un Toyota RAV4 2021" → SEARCH
  - "Cherche des Honda CRV sous 25000" → SEARCH
  - "je recherche une Seltos 2022 au quebec" → SEARCH
  - "Montre moi des Kia Seltos au Quebec" → SEARCH

- ANALYZE_URL: message contains exactly 1 URL
- COMPARE_URLS: message contains 2+ URLs
- CHECK_VIN: message contains a VIN (17 alphanumeric characters)
- FOLLOWUP: user responds to a previous suggestion (ex: "le 2", "oui", "compare-les", "verifie le vin")

For SEARCH extract:
- query: exact vehicle search terms (make, model, year, trim, budget, location)
- vehicle_filter: specific make+model being searched (ex: "Kia Seltos 2022")
- site: dealer domain if mentioned, null otherwise
- count: number of results requested (default 3)

Return ONLY the JSON, no explanation.
"""


# =============================
# INTENT DETECTION
# =============================

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
    return {"intent": "CHAT", "urls": [], "vin": None, "query": message, "site": None, "count": 3, "followup_action": None}


# =============================
# FOLLOWUP HANDLER
# =============================

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


# =============================
# SMART CHAT — MAIN ENTRY POINT
# =============================

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
        query = intent_data["query"]
        session["context"]["last_query"] = query

        # ─── ÉTAPE 1 : Chercher dans l'inventaire local (Force Occasion) ───
        cache_results = search_inventory_cache(query, limit=5)

        if cache_results:
            cache_text = format_cache_results_for_prompt(cache_results)
            session["context"]["last_listings"] = [r["url"] for r in cache_results]

            prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

{cache_text}

RECHERCHE DE L'UTILISATEUR : "{query}"

INSTRUCTIONS :
- Présente les véhicules trouvés en utilisant UNIQUEMENT les données réelles ci-dessus
- Utilise le FORMAT DE PRÉSENTATION défini dans tes instructions
- Compare le prix au prix du marché si disponible
- Si le kilométrage > 100 000 km, suggère de vérifier le VIN
- Termine avec une question concrète (vérifier VIN, voir plus de détails, comparer ?)
- NE PAS inventer de données — utilise seulement ce qui est fourni
- NE PAS inclure de HTML brut dans ta réponse
"""
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            result = {
                "intent": "SEARCH",
                "response": response.text + "\n\nSouhaitez-vous vérifier le VIN d'un de ces véhicules ou les comparer entre eux ?",
                "urls_found": [r["url"] for r in cache_results],
                "scraped_count": len(cache_results),
                "source": "inventory_cache"
            }

        else:
            # ─── ÉTAPE 2 : Fallback — recherche web via SerpAPI ───
            print(f"[smart_chat] Aucun résultat local pour '{query}' → fallback SerpAPI")
            search_result = search_and_analyze(
                query=query,
                site=intent_data.get("site"),
                count=intent_data.get("count", 3)
            )
            session["context"]["last_listings"] = search_result.get("urls_found", [])

            try:
                log_search(query=query, intent="SEARCH", results_count=search_result.get("scraped_count", 0))
            except Exception:
                pass

            # Nettoyer le HTML parasite dans la réponse SerpAPI
            base_response = strip_html(search_result.get("analysis", ""))

            result = {
                "intent": "SEARCH",
                "response": base_response + "\n\nSouhaitez-vous que je vérifie le VIN d'un de ces véhicules, ou voulez-vous les comparer entre eux ?",
                "urls_found": search_result.get("urls_found", []),
                "scraped_count": search_result.get("scraped_count", 0),
                "source": "serpapi"
            }

    else:
        # ─── CHAT — conseils, fiabilité, prix, etc. ───
        learning_context = ""
        try:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from database import get_similar_good_responses, get_user_memory

            user_mem = get_user_memory(user_id) if user_id else {}
            if user_mem:
                mem_parts = []
                if user_mem.get('budget'): mem_parts.append(f"Budget connu: {user_mem['budget']}$")
                if user_mem.get('preferred_make'): mem_parts.append(f"Marque préférée: {user_mem['preferred_make']}")
                if user_mem.get('preferred_type'): mem_parts.append(f"Type préféré: {user_mem['preferred_type']}")
                if user_mem.get('city'): mem_parts.append(f"Ville: {user_mem['city']}")
                if user_mem.get('needs_awd'): mem_parts.append("Préfère AWD/4x4")
                if mem_parts:
                    learning_context += f"\n\nMÉMOIRE UTILISATEUR:\n" + "\n".join(mem_parts)

            good = get_similar_good_responses(message, limit=2)
            if good:
                learning_context += "\n\nEXEMPLES DE BONNES RÉPONSES PASSÉES:\n"
                for g in good:
                    learning_context += f"Q: {g['question']}\nA: {g['response'][:300]}...\n\n"
        except Exception:
            learning_context = ""

        full_prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}
{learning_context}

Message de l'utilisateur: {message}

INSTRUCTIONS :
- Réponds directement sans préambule
- Si l'utilisateur mentionne un modèle → utilise Google Search pour les prix actuels au Canada
- Si budget mentionné → vérifie si le prix est réaliste sur le marché canadien
- Calcule toujours TPS 5% + TVQ 9.975% si un prix est mentionné
- Si la mémoire utilisateur contient un budget → l'utiliser comme référence
- NE PAS inclure de HTML brut dans ta réponse
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
        )
        result = {"intent": "CHAT", "response": response.text}

    response_text = result.get("response", "")
    # Nettoyage final HTML sur toutes les réponses
    if isinstance(response_text, str):
        result["response"] = strip_html(response_text)
        session["history"].append({"role": "assistant", "content": result["response"]})
    update_context(user_id, intent_data, result["response"] if isinstance(result.get("response"), str) else "")
    session["history"] = session["history"][-20:]
    return result