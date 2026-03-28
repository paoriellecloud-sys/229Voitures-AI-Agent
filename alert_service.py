import logging
from database import get_connection
from email_service import send_alert_email

logger = logging.getLogger(__name__)


def save_alert(user_id: str, email: str, criteria: dict) -> bool:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO user_alerts
            (user_id, email, brand, model, year_min, year_max, price_max, km_max, city)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, email,
            criteria.get("brand", "").lower(),
            criteria.get("model", "").lower(),
            criteria.get("year_min"),
            criteria.get("year_max"),
            criteria.get("price_max"),
            criteria.get("km_max"),
            criteria.get("city", "").lower(),
        ))
        conn.commit()
        logger.info(f"[alert] Alerte sauvegardée pour {email}")
        return True
    except Exception as e:
        logger.error(f"[alert] Erreur save_alert: {e}")
        return False
    finally:
        conn.close()


def check_alerts_for_vehicle(vehicle: dict):
    conn = get_connection()
    try:
        alerts = conn.execute("SELECT * FROM user_alerts WHERE active=1").fetchall()
        for alert in alerts:
            try:
                alert_id, _, email, brand, model, year_min, year_max, price_max, km_max, city, _, _ = alert
                v_title = vehicle.get("title", "").lower()
                v_price = vehicle.get("price", 999999)
                v_km = vehicle.get("mileage", 999999)
                v_city = vehicle.get("city", "").lower()
                v_id = str(vehicle.get("vehicle_id", ""))
                if brand and brand not in v_title:
                    continue
                if model and model not in v_title:
                    continue
                if price_max and v_price > price_max:
                    continue
                if km_max and v_km > km_max:
                    continue
                if city and city not in v_city:
                    continue
                already = conn.execute(
                    "SELECT 1 FROM sent_alerts WHERE alert_id=? AND vehicle_id=?",
                    (alert_id, v_id)
                ).fetchone()
                if already:
                    continue
                if send_alert_email(email, vehicle):
                    conn.execute(
                        "INSERT OR IGNORE INTO sent_alerts (alert_id, vehicle_id) VALUES (?,?)",
                        (alert_id, v_id)
                    )
                    conn.commit()
                    logger.info(f"[alert] Match envoyé à {email} — {vehicle.get('title','')}")
            except Exception as e:
                logger.error(f"[alert] Erreur alerte id={alert[0]}: {e}")
    finally:
        conn.close()


def get_user_alerts(user_id: str) -> list:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, brand, model, price_max, km_max, city FROM user_alerts WHERE user_id=? AND active=1",
            (user_id,)
        ).fetchall()
        return [{"id": r[0], "brand": r[1], "model": r[2],
                 "price_max": r[3], "km_max": r[4], "city": r[5]} for r in rows]
    except Exception as e:
        logger.error(f"[alert] get_user_alerts error: {e}")
        return []
    finally:
        conn.close()
