"""Gestion des annonces Marketplace Facebook — isolé du système chat."""
import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "/home/ubuntu/data/229voitures.db")

_BASE_URL = "https://229voitures.ca"


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def get_vehicle_by_vin(vin: str) -> dict | None:
    """Retourne le véhicule depuis inventory_cache par VIN, ou None si introuvable/vendu."""
    if not vin:
        return None
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM inventory_cache WHERE vin = ? LIMIT 1", (vin,)
        ).fetchone()
        if not row:
            return None
        v = dict(row)
        if v.get("price") is None:
            return None
        return v
    finally:
        conn.close()


def find_similar_vehicles(vehicle: dict, limit: int = 3) -> list:
    """Retourne des alternatives si le véhicule est introuvable.

    Cherche d'abord même make, puis même catégorie de prix (+/- 20%).
    Réutilise search_inventory_cache depuis agent_router pour ne pas dupliquer.
    """
    from modules.handlers.search_handler import get_alternatives

    make = (vehicle or {}).get("make", "")
    model = (vehicle or {}).get("model", "")
    price = (vehicle or {}).get("price") or 0

    query = f"{make} {model}".strip() or "vus"
    price_max = int(price * 1.20) if price else None

    alts = get_alternatives(query=query, price_max=price_max, limit=limit)
    return alts[:limit]


def mark_marketplace_listing(vin: str, price: float) -> str:
    """Enregistre une annonce Marketplace et retourne le lien UTM."""
    conn = _conn()
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "UPDATE inventory_cache SET marketplace_price = ?, marketplace_posted_at = ? WHERE vin = ?",
            (price, now, vin),
        )
        conn.commit()
    finally:
        conn.close()
    return f"{_BASE_URL}/auto/{vin}?utm_source=facebook&utm_medium=marketplace"


def check_price_drift(vin: str) -> dict:
    """Compare le prix courant au prix affiché sur Marketplace.

    Retourne display_price et has_alert.
    Si prix actuel > marketplace_price → alerte (prix a monté après la publication).
    """
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT price, marketplace_price, price_alert FROM inventory_cache WHERE vin = ? LIMIT 1",
            (vin,),
        ).fetchone()
        if not row:
            return {"display_price": None, "has_alert": False}

        current_price = row["price"]
        mp_price = row["marketplace_price"]

        if mp_price is None:
            return {"display_price": current_price, "has_alert": False}

        has_alert = bool(current_price and current_price > mp_price)

        if has_alert:
            conn.execute(
                "UPDATE inventory_cache SET price_alert = 1 WHERE vin = ?", (vin,)
            )
            conn.commit()
        else:
            conn.execute(
                "UPDATE inventory_cache SET price_alert = 0 WHERE vin = ?", (vin,)
            )
            conn.commit()

        display_price = mp_price if has_alert else current_price
        return {"display_price": display_price, "has_alert": has_alert}
    finally:
        conn.close()
