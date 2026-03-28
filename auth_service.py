import os
import secrets
import logging
import uuid
from datetime import datetime, timedelta
from database import get_connection
from email_service import send_magic_link_email

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("BASE_URL", "https://229voitures-ai-agent-production.up.railway.app")


def request_magic_link(email: str) -> bool:
    conn = get_connection()
    try:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(minutes=15)).isoformat()
        existing = conn.execute(
            "SELECT user_id FROM registered_users WHERE email=?", (email,)
        ).fetchone()
        user_id = existing[0] if existing else str(uuid.uuid4())
        if not existing:
            conn.execute(
                "INSERT INTO registered_users (user_id, email) VALUES (?,?)",
                (user_id, email)
            )
        conn.execute(
            "INSERT INTO magic_links (email, token, user_id, expires_at) VALUES (?,?,?,?)",
            (email, token, user_id, expires)
        )
        conn.commit()
        send_magic_link_email(email, token, BASE_URL)
        logger.info(f"[auth] Magic link envoyé à {email}")
        return True
    except Exception as e:
        logger.error(f"[auth] Erreur request_magic_link: {e}")
        return False
    finally:
        conn.close()


def verify_magic_link(token: str) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT email, user_id, expires_at, used FROM magic_links WHERE token=?",
            (token,)
        ).fetchone()
        if not row:
            return {"success": False, "error": "Lien invalide"}
        email, user_id, expires_at, used = row
        if used:
            return {"success": False, "error": "Lien déjà utilisé"}
        if datetime.now() > datetime.fromisoformat(expires_at):
            return {"success": False, "error": "Lien expiré"}
        conn.execute("UPDATE magic_links SET used=1 WHERE token=?", (token,))
        conn.execute(
            "UPDATE registered_users SET last_login=? WHERE user_id=?",
            (datetime.now().isoformat(), user_id)
        )
        conn.commit()
        return {"success": True, "user_id": user_id, "email": email}
    except Exception as e:
        logger.error(f"[auth] Erreur verify_magic_link: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()
