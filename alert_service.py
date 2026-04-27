import sqlite3
import logging
from database import get_connection
from email_service import send_alert_email

logger = logging.getLogger(__name__)


def save_alert(user_id: str, email: str, criteria: dict) -> bool:
    conn = get_connection()
    try:
        for col in ("fuel_type TEXT", "drivetrain TEXT"):
            try:
                conn.execute(f"ALTER TABLE user_alerts ADD COLUMN {col}")
                conn.commit()
            except Exception:
                pass
        conn.execute("""
            INSERT INTO user_alerts
            (user_id, email, brand, model, year_min, year_max, price_max, km_max, city, fuel_type, drivetrain)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, email,
            criteria.get("brand", "").lower(),
            criteria.get("model", "").lower(),
            criteria.get("year_min"),
            criteria.get("year_max"),
            criteria.get("price_max"),
            criteria.get("km_max"),
            criteria.get("city", "").lower(),
            criteria.get("fuel_type", "").lower(),
            criteria.get("drivetrain", "").lower(),
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
    conn.row_factory = sqlite3.Row
    try:
        alerts = conn.execute("SELECT * FROM user_alerts WHERE active=1").fetchall()
        for alert in alerts:
            try:
                alert_dict = dict(alert)
                alert_id  = alert_dict["id"]
                email     = alert_dict["email"]
                brand     = alert_dict.get("brand") or ""
                model     = alert_dict.get("model") or ""
                year_min  = alert_dict.get("year_min")
                year_max  = alert_dict.get("year_max")
                price_max = alert_dict.get("price_max")
                km_max    = alert_dict.get("km_max")
                city      = alert_dict.get("city") or ""
                v_title   = vehicle.get("title", "").lower()
                v_price   = vehicle.get("price", 999999)
                v_km      = vehicle.get("mileage", 999999)
                v_city    = vehicle.get("city", "").lower()
                v_id      = str(vehicle.get("vehicle_id", ""))
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
                # Filtre année
                v_year = vehicle.get("year", 0)
                if year_min and v_year and int(v_year) < int(year_min):
                    continue
                if year_max and v_year and int(v_year) > int(year_max):
                    continue
                # Filtre carburant
                fuel_filter = (alert_dict.get("fuel_type") or "").lower()
                v_fuel = str(vehicle.get("fuel_type", "")).lower()
                if fuel_filter:
                    if fuel_filter == "phev" and "phev" not in v_fuel:
                        continue
                    elif fuel_filter == "hybride" and not any(
                        w in v_fuel for w in ["hybride", "hybrid", "phev"]
                    ):
                        continue
                    elif fuel_filter == "électrique" and not any(
                        w in v_fuel for w in ["électrique", "electrique", "ev"]
                    ):
                        continue
                # Filtre traction
                drivetrain_filter = (alert_dict.get("drivetrain") or "").lower()
                v_drivetrain = str(vehicle.get("drivetrain", "")).lower()
                if drivetrain_filter == "awd" and not any(
                    w in v_drivetrain for w in ["intégrale", "integrale", "awd", "4x4", "4rm"]
                ):
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
