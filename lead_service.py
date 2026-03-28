import logging
from database import get_connection
from email_service import send_lead_email

logger = logging.getLogger(__name__)

ADMIN_EMAIL = "paorielle229@gmail.com"

DEALER_EMAILS = {
    "force occasion": ADMIN_EMAIL,
    "kia val-bélair": ADMIN_EMAIL,
    "default": ADMIN_EMAIL,
}


def create_lead(lead_data: dict) -> bool:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO leads
            (user_id, name, email, phone, vehicle_title, vehicle_price,
             vehicle_url, dealer_name, dealer_email, message)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            lead_data.get("user_id", "anonymous"),
            lead_data.get("name", ""),
            lead_data.get("email", ""),
            lead_data.get("phone", ""),
            lead_data.get("vehicle_title", ""),
            lead_data.get("vehicle_price", 0),
            lead_data.get("vehicle_url", ""),
            lead_data.get("dealer_name", ""),
            lead_data.get("dealer_email", ADMIN_EMAIL),
            lead_data.get("message", ""),
        ))
        conn.commit()
        dealer_email = lead_data.get("dealer_email") or DEALER_EMAILS.get(
            lead_data.get("dealer_name", "").lower(), ADMIN_EMAIL
        )
        send_lead_email(dealer_email, lead_data)
        logger.info(f"[lead] Lead créé: {lead_data.get('vehicle_title')}")
        return True
    except Exception as e:
        logger.error(f"[lead] Erreur create_lead: {e}")
        return False
    finally:
        conn.close()


def get_leads_stats() -> dict:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        this_month = conn.execute("""
            SELECT COUNT(*) FROM leads
            WHERE created_at >= date('now','start of month')
        """).fetchone()[0]
        this_week = conn.execute("""
            SELECT COUNT(*) FROM leads
            WHERE created_at >= date('now','-7 days')
        """).fetchone()[0]
        by_dealer = conn.execute("""
            SELECT dealer_name, COUNT(*) as total
            FROM leads
            GROUP BY dealer_name
            ORDER BY total DESC
        """).fetchall()
        recent = conn.execute("""
            SELECT id, name, email, phone, vehicle_title, vehicle_price,
                   dealer_name, status, created_at
            FROM leads
            ORDER BY created_at DESC
            LIMIT 50
        """).fetchall()
        return {
            "total": total,
            "this_month": this_month,
            "this_week": this_week,
            "by_dealer": [{"dealer": r[0] or "Non spécifié", "count": r[1]} for r in by_dealer],
            "recent": [{
                "id": r[0], "name": r[1], "email": r[2], "phone": r[3],
                "vehicle": r[4], "price": r[5], "dealer": r[6],
                "status": r[7], "date": r[8],
            } for r in recent],
        }
    except Exception as e:
        logger.error(f"[lead] get_leads_stats error: {e}")
        return {}
    finally:
        conn.close()
