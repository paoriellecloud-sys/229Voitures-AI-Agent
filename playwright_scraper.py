import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "/home/ubuntu/data/229voitures.db")


# =============================
# CACHE STATS
# =============================

def get_cache_stats():
    """Retourne les statistiques du cache inventory_cache."""
    try:
        conn = sqlite3.connect(DB_PATH)
        total = conn.execute("SELECT COUNT(*) FROM inventory_cache").fetchone()[0]
        try:
            fresh = conn.execute(
                "SELECT COUNT(*) FROM inventory_cache WHERE scraped_at >= datetime('now', '-7 days')"
            ).fetchone()[0]
        except Exception:
            fresh = total
        try:
            sources = conn.execute(
                "SELECT COUNT(DISTINCT source) FROM inventory_cache"
            ).fetchone()[0]
        except Exception:
            sources = 1
        conn.close()
        return {"total": total, "fresh": fresh, "sources": sources}
    except Exception as e:
        print(f"[get_cache_stats] Erreur: {e}")
        return {"total": 0, "fresh": 0, "sources": 0}


# =============================
# SEARCH CACHE
# =============================

def search_cache(query: str):
    """Recherche dans inventory_cache."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute("PRAGMA table_info(inventory_cache)")
        columns = [col[1] for col in cursor.fetchall()]
        rows = conn.execute(
            "SELECT * FROM inventory_cache WHERE LOWER(title) LIKE ? OR LOWER(raw_content) LIKE ? LIMIT 20",
            (f"%{query.lower()}%", f"%{query.lower()}%")
        ).fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"[search_cache] Erreur: {e}")
        return []


# =============================
# STUBS
# =============================

def init_inventory_cache():
    pass

def save_to_cache(data):
    pass

async def scrape_with_playwright(url):
    return {"success": False, "error": "Playwright non configuré"}
