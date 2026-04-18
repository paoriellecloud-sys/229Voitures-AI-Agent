"""
Smart Chat - 229Voitures
Orchestrateur principal - remplace agent_router.py
Flux clair et previsible :
1. Classifier l'intention (intent_classifier)
2. Identifier le vehicule si besoin (vehicle_selector)
3. Chercher l'inventaire si besoin (inventory_service)
4. Construire la reponse (response_builder)
5. Gerer le RDV si besoin (rdv_handler)
"""

import json
import sqlite3
import os
from datetime import datetime

from modules.intent_classifier import classify
from modules.vehicle_selector import select_vehicle
from modules.inventory_service import search
from modules.response_builder import (
    build_search_response,
    build_chat_response,
    build_no_results_response,
)
from modules.rdv_handler import generate_form, create_lead, generate_confirmation
from modules.formatters import generate_vin_report

DB_PATH = os.getenv("DB_PATH", "/home/ubuntu/data/229voitures.db")


# ─── Session ────────────────────────────────────────────────────────────────

def _get_session_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            user_id TEXT PRIMARY KEY,
            history TEXT DEFAULT '[]',
            user_data TEXT DEFAULT '{}',
            context TEXT DEFAULT '{}',
            vehicle_shown TEXT DEFAULT '{}',
            updated_at TEXT
        )
    """)
    conn.commit()
    return conn


def load_session(user_id: str) -> dict:
    try:
        conn = _get_session_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            vs_raw = row["vehicle_shown"] or "{}"
            vs = json.loads(vs_raw)
            vs = {int(k): v for k, v in vs.items()}
            return {
                "history": json.loads(row["history"] or "[]"),
                "user_data": json.loads(row["user_data"] or "{}"),
                "context": json.loads(row["context"] or "{}"),
                "vehicle_shown": vs,
            }
    except Exception as e:
        print(f"[smart_chat] load_session error: {e}")
    return {"history": [], "user_data": {}, "context": {}, "vehicle_shown": {}}


def save_session(user_id: str, session: dict):
    try:
        conn = _get_session_conn()
        cursor = conn.cursor()
        vs = {str(k): v for k, v in session.get("vehicle_shown", {}).items()}
        cursor.execute("""
            INSERT OR REPLACE INTO sessions (user_id, history, user_data, context, vehicle_shown, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            json.dumps(session.get("history", [])[-20:]),
            json.dumps(session.get("user_data", {})),
            json.dumps(session.get("context", {})),
            json.dumps(vs),
            datetime.utcnow().isoformat(),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[smart_chat] save_session error: {e}")


def _history_to_str(history: list) -> str:
    lines = []
    for msg in history[-10:]:
        role = "Utilisateur" if msg.get("role") == "user" else "Agent"
        content = msg.get("content", "")[:500]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


# ─── Budget extraction ───────────────────────────────────────────────────────

import re

BUDGET_PATTERNS = [
    r'(?:mon budget est|budget de|je veux d[eé]penser|maximum|max)\s*(\d[\d\s,]*)\s*\$',
    r'(\d[\d\s,]*)\s*\$\s*(?:de budget|max|maximum)',
    r'autour de\s*(\d[\d\s,]*)\s*\$',
    r'(\d[\d\s,]*)\s*\$?\s*(?:par mois|/mois|mensuel|aux deux semaines)',
    r'budget\s*(?:de|est)?\s*(\d[\d\s,]*)',
]


def _extract_budget(message: str, user_data: dict) -> dict:
    if user_data.get("budget_clarified"):
        return user_data
    for pattern in BUDGET_PATTERNS:
        match = re.search(pattern, message.lower())
        if match:
            amount_str = match.group(1).replace(" ", "").replace(",", "")
            try:
                amount = float(amount_str)
                if amount >= 100:
                    user_data["budget"] = amount
                    user_data["budget_clarified"] = True
            except ValueError:
                pass
    return user_data


# ─── Point d'entree principal ────────────────────────────────────────────────

def smart_chat(message: str, user_id: str = "default") -> dict:
    """
    Orchestrateur principal.
    Flux : classify → select → search/chat → respond
    """
    # 1. Charger la session
    session = load_session(user_id)
    history = session["history"]
    user_data = session["user_data"]
    vehicle_shown = session.get("vehicle_shown", {})

    # 2. Extraire le budget si mentionne
    user_data = _extract_budget(message, user_data)
    session["user_data"] = user_data

    history_str = _history_to_str(history)

    # ── Interception DEMANDE_RDV (soumission formulaire) ──────────────────
    if message.startswith("DEMANDE_RDV |"):
        return _handle_rdv_submission(message, session, vehicle_shown, user_id)

    # 3. Classifier l'intention
    classification = classify(message, vehicle_shown)
    intent = classification["intent"]
    vehicle_ref = classification.get("vehicle_ref")

    print(f"[smart_chat] intent={intent} ref={vehicle_ref} msg={message[:60]}")

    # ── RDV ───────────────────────────────────────────────────────────────
    if intent == "RDV":
        return _handle_rdv_intent(message, session, vehicle_shown, user_id, history_str)

    # ── VIN ───────────────────────────────────────────────────────────────
    if intent == "VIN":
        return _handle_vin(message, session, user_id)

    # ── FOLLOWUP ──────────────────────────────────────────────────────────
    if intent == "FOLLOWUP" and vehicle_shown:
        selected = select_vehicle(message, vehicle_shown)
        result = build_chat_response(
            message=message,
            session=session,
            history_str=history_str,
            vehicle_shown=vehicle_shown,
            selected_vehicle=selected,
        )
        _update_history(session, message, result["response"])
        save_session(user_id, session)
        return result

    # ── SEARCH ────────────────────────────────────────────────────────────
    if intent == "SEARCH":
        vehicles = search(query=message, vehicle_filter=vehicle_ref, limit=6)

        if vehicles:
            result = build_search_response(
                message=message,
                vehicles=vehicles,
                session=session,
                history_str=history_str,
            )
            session["vehicle_shown"] = result["vehicle_shown"]
        else:
            result = build_no_results_response(
                message=message,
                query=vehicle_ref or message,
                session=session,
                history_str=history_str,
            )

        _update_history(session, message, result["response"])
        save_session(user_id, session)
        return result

    # ── CHAT ──────────────────────────────────────────────────────────────
    result = build_chat_response(
        message=message,
        session=session,
        history_str=history_str,
        vehicle_shown=vehicle_shown,
    )
    _update_history(session, message, result["response"])
    save_session(user_id, session)
    return result


# ─── Handlers specifiques ────────────────────────────────────────────────────

def _handle_rdv_intent(message, session, vehicle_shown, user_id, history_str):
    """Affiche le formulaire RDV pour le bon vehicule."""
    selected = select_vehicle(message, vehicle_shown)
    print(f"[RDV DEBUG] message={message} vehicle_shown_keys={list(vehicle_shown.keys())} selected_year={selected.get('year') if selected else None}")

    if not selected and vehicle_shown:
        # Si un seul vehicule ou impossible de determiner → demander confirmation
        if len(vehicle_shown) == 1:
            selected = list(vehicle_shown.values())[0]
        else:
            # Demander confirmation
            result = build_chat_response(
                message=message,
                session=session,
                history_str=history_str,
                vehicle_shown=vehicle_shown,
            )
            _update_history(session, message, result["response"])
            save_session(user_id, session)
            return result

    if not selected:
        return {
            "response": "Pour quel vehicule souhaitez-vous prendre rendez-vous ? Faites une recherche d'abord.",
            "html_cards": "",
            "vehicle_shown": vehicle_shown,
            "intent": "RDV",
        }

    html_form = generate_form(selected)
    response_text = f"Voici le formulaire pour contacter {selected.get('dealer_name', 'le concessionnaire')} pour le {selected.get('year','')} {selected.get('make','')} {selected.get('model','')}."

    session["context"]["rdv_vehicle"] = selected
    _update_history(session, message, response_text)
    save_session(user_id, session)

    return {
        "response": response_text,
        "html_cards": html_form,
        "vehicle_shown": vehicle_shown,
        "intent": "RDV",
    }


def _handle_rdv_submission(message, session, vehicle_shown, user_id):
    """Traite la soumission du formulaire RDV."""
    try:
        parts = message.split("|")
        data = {}
        for part in parts[1:]:
            if ":" in part:
                key, val = part.strip().split(":", 1)
                data[key.strip()] = val.strip()

        rdv_vehicle = session.get("context", {}).get("rdv_vehicle", {})
        if not rdv_vehicle and vehicle_shown:
            rdv_vehicle = list(vehicle_shown.values())[0]

        price_raw = rdv_vehicle.get("price", "")
        try:
            price_str = f"{float(price_raw):,.0f} $".replace(",", " ")
        except Exception:
            price_str = str(price_raw)

        lead_data = {
            "name": data.get("nom", ""),
            "email": data.get("email", ""),
            "phone": data.get("tel", ""),
            "vehicle": f"{rdv_vehicle.get('year','')} {rdv_vehicle.get('make','')} {rdv_vehicle.get('model','')}".strip(),
            "price": price_str,
            "stock_number": rdv_vehicle.get("stock_number", ""),
            "vin": rdv_vehicle.get("vin", ""),
            "dealer": rdv_vehicle.get("dealer_name", ""),
            "message": data.get("message", ""),
        }

        create_lead(lead_data)

        confirmation = generate_confirmation(
            vehicle=rdv_vehicle,
            name=lead_data["name"],
            phone=lead_data["phone"],
            email=lead_data["email"],
        )

        _update_history(session, message, confirmation)
        save_session(user_id, session)

        return {
            "response": confirmation,
            "html_cards": "",
            "vehicle_shown": vehicle_shown,
            "intent": "LEAD_SENT",
        }

    except Exception as e:
        print(f"[smart_chat] RDV submission error: {e}")
        return {
            "response": "Votre demande a été reçue. Le concessionnaire vous contactera bientôt.",
            "html_cards": "",
            "vehicle_shown": vehicle_shown,
            "intent": "LEAD_SENT",
        }


def _handle_vin(message, session, user_id):
    """Analyse un VIN."""
    import re
    vin_match = re.search(r'\b[A-HJ-NPR-Z0-9]{17}\b', message.upper())
    if not vin_match:
        return {"response": "VIN invalide.", "html_cards": "", "vehicle_shown": {}, "intent": "VIN"}

    vin = vin_match.group(0)

    try:
        from modules.vin_checker import get_vehicle_report
        report_data = get_vehicle_report(vin)
        html = generate_vin_report(report_data)
        response_text = f"Voici le rapport VIN pour le {report_data.get('year', '')} {report_data.get('make', '')} {report_data.get('model', '')}."
    except Exception as e:
        print(f"[smart_chat] VIN error: {e}")
        response_text = f"Impossible d'analyser le VIN {vin} pour le moment."
        html = ""

    _update_history(session, message, response_text)
    save_session(user_id, session)

    return {
        "response": response_text,
        "html_cards": html,
        "vehicle_shown": session.get("vehicle_shown", {}),
        "intent": "VIN",
    }


def _update_history(session: dict, user_msg: str, agent_msg: str):
    session["history"].append({"role": "user", "content": user_msg})
    session["history"].append({"role": "assistant", "content": agent_msg})
    if len(session["history"]) > 40:
        session["history"] = session["history"][-40:]
