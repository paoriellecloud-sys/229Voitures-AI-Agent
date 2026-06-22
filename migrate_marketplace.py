"""Migration: ajoute les colonnes marketplace à inventory_cache."""
import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "/home/ubuntu/data/229voitures.db")

COLUMNS = [
    ("marketplace_price",    "ALTER TABLE inventory_cache ADD COLUMN marketplace_price REAL"),
    ("marketplace_posted_at","ALTER TABLE inventory_cache ADD COLUMN marketplace_posted_at TEXT"),
    ("price_alert",          "ALTER TABLE inventory_cache ADD COLUMN price_alert INTEGER DEFAULT 0"),
    ("stock_number",         "ALTER TABLE inventory_cache ADD COLUMN stock_number TEXT"),
]


def run():
    conn = sqlite3.connect(DB_PATH)
    try:
        for col_name, sql in COLUMNS:
            try:
                conn.execute(sql)
                conn.commit()
                print(f"[migrate] Colonne '{col_name}' ajoutée.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"[migrate] Colonne '{col_name}' existe déjà — ignorée.")
                else:
                    raise
        print("[migrate] Migration terminée.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
