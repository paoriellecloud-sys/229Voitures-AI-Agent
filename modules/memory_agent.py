"""
Memory Agent — retient les propositions et persiste les sessions SQLite.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "database" / "vehicles.db"

def init_sessions_table():
    """Crée la table sessions si elle n'existe pas."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                data TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()

def save_session(session_id: str, user_id: str, session_data: dict):
    """Sauvegarde la session en SQLite."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_sessions
                (session_id, user_id, data, updated_at)
                VALUES (?, ?, ?, ?)
            """, (session_id, user_id, json.dumps(session_data, ensure_ascii=False), datetime.now().isoformat()))
            conn.commit()
    except Exception as e:
        print(f"[memory_agent] Erreur save_session: {e}")

def load_session(session_id: str) -> dict:
    """Charge une session depuis SQLite."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT data FROM user_sessions WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            if row:
                return json.loads(row[0])
    except Exception as e:
        print(f"[memory_agent] Erreur load_session: {e}")
    return {}

def inject_proposals_in_prompt(session: dict, prompt: str) -> str:
    """
    Injecte les dernières propositions dans le prompt Gemini.
    Corrige le bug : agent oublie les véhicules qu'il vient de montrer.
    """
    last_results = session.get("context", {}).get("last_results", [])
    if not last_results:
        return prompt

    lines = []
    for i, v in enumerate(last_results):
        year = v.get("year", "")
        make = v.get("make", "")
        model = v.get("model", "")
        price = v.get("price", "")
        dealer = v.get("dealer_name", "")
        city = v.get("city", "")
        lines.append(
            f"  Proposition {i+1}: {year} {make} {model} "
            f"— {price}$ — {dealer}, {city}"
        )

    proposals_text = "\n".join(lines)

    injection = f"""
VÉHICULES DÉJÀ PROPOSÉS À L'UTILISATEUR (mémoire obligatoire):
{proposals_text}
Tu DOIS te souvenir de ces propositions si l'utilisateur y fait référence
("le deuxième", "celui-là", "as-tu autre chose", etc.)

"""
    return injection + prompt

def get_proposal_by_number(session: dict, number: int) -> dict:
    """
    Retourne la proposition N depuis la session.
    Utilisé pour les RDV et références directes.
    """
    last_results = session.get("context", {}).get("last_results", [])
    if 1 <= number <= len(last_results):
        return last_results[number - 1]
    return {}
