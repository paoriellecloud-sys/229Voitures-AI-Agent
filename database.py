import sqlite3

DB_NAME = "vehicles.db"


# ==============================
# CONNECTION
# ==============================

def get_connection():
    return sqlite3.connect(DB_NAME)


# ==============================
# CREATE TABLES
# ==============================

def create_vehicles_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand TEXT,
        model TEXT,
        year INTEGER,
        price REAL,
        fuel_type TEXT,
        transmission TEXT,
        mileage INTEGER,
        consumption REAL,
        location TEXT,
        description TEXT
    )
    """)
    conn.commit()
    conn.close()


def create_users_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        hashed_password TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()


def create_user_preferences_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER UNIQUE,
        preferred_max_price REAL,
        preferred_fuel_type TEXT,
        weight_price REAL DEFAULT 1.0,
        weight_mileage REAL DEFAULT 1.0,
        weight_year REAL DEFAULT 1.0,
        weight_consumption REAL DEFAULT 1.0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    conn.commit()
    conn.close()


def create_recommendation_history_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            vehicle_id INTEGER,
            liked INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, vehicle_id)
        )
    """)
    conn.commit()
    conn.close()


def create_inventory_cache_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            vehicle_id TEXT,
            title TEXT,
            price REAL,
            mileage INTEGER,
            year INTEGER,
            make TEXT,
            model TEXT,
            city TEXT,
            province TEXT,
            dealer_name TEXT,
            dealer_phone TEXT,
            vin TEXT,
            color TEXT,
            transmission TEXT,
            drivetrain TEXT,
            fuel_type TEXT,
            engine TEXT,
            trim TEXT,
            avg_market_price REAL,
            price_diff REAL,
            price_status TEXT,
            tps REAL,
            tvq REAL,
            total_taxes REAL,
            total_with_taxes REAL,
            options TEXT,
            description TEXT,
            highway_consumption TEXT,
            city_consumption TEXT,
            photos TEXT,
            url TEXT,
            json_url TEXT,
            raw_content TEXT,
            scraped_at TEXT,
            UNIQUE(source, vehicle_id)
        )
    """)
    conn.commit()
    conn.close()


def create_search_logs_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            intent TEXT,
            results_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# ==============================
# VEHICLES
# ==============================

def get_all_vehicles():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehicles")
    rows = cursor.fetchall()
    conn.close()
    vehicles = []
    for r in rows:
        vehicles.append({
            "id": r[0], "brand": r[1], "model": r[2], "year": r[3],
            "price": r[4], "fuel_type": r[5], "transmission": r[6],
            "mileage": r[7], "consumption": r[8], "location": r[9], "description": r[10],
        })
    return vehicles


# ==============================
# USERS
# ==============================

def get_user_by_username(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, hashed_password FROM users WHERE username = ?",
        (username,)
    )
    user = cursor.fetchone()
    conn.close()
    if user:
        return {"id": user[0], "username": user[1], "hashed_password": user[2]}
    return None


def create_user(username, hashed_password):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            (username, hashed_password)
        )
        conn.commit()
    except:
        conn.close()
        return None
    conn.close()
    return True


# ==============================
# ML TRAINING DATA
# ==============================

def get_training_data(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.price, v.mileage, v.year, v.consumption, r.liked
        FROM recommendation_history r
        JOIN vehicles v ON r.vehicle_id = v.id
        WHERE r.user_id = ? AND r.liked IS NOT NULL
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def save_recommendation_action(user_id, vehicle_id, liked):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, liked FROM recommendation_history
        WHERE user_id = ? AND vehicle_id = ?
    """, (user_id, vehicle_id))
    existing = cursor.fetchone()
    if existing is None:
        cursor.execute("""
            INSERT INTO recommendation_history (user_id, vehicle_id, liked)
            VALUES (?, ?, ?)
        """, (user_id, vehicle_id, liked))
    else:
        if liked is not None:
            cursor.execute("""
                UPDATE recommendation_history
                SET liked = ?, timestamp = CURRENT_TIMESTAMP
                WHERE user_id = ? AND vehicle_id = ?
            """, (liked, user_id, vehicle_id))
    conn.commit()
    conn.close()


# ==============================
# SEARCH LOGS
# ==============================

def log_search(query: str, intent: str, results_count: int = 0):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO search_logs (query, intent, results_count) VALUES (?, ?, ?)",
        (query, intent, results_count)
    )
    conn.commit()
    conn.close()


def get_popular_searches(limit: int = 10) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT query, COUNT(*) as count
        FROM search_logs
        WHERE intent = 'SEARCH'
        GROUP BY query
        ORDER BY count DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"query": r[0], "count": r[1]} for r in rows]


# ==============================
# LEARNING TABLES
# ==============================

def create_learning_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # Good responses — saved when user clicks 👍
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS good_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            response TEXT NOT NULL,
            intent TEXT,
            user_id TEXT,
            score INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Bad responses — saved when user clicks 👎
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bad_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            response TEXT NOT NULL,
            intent TEXT,
            user_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # User memory — persistent preferences per user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            budget REAL,
            preferred_make TEXT,
            preferred_model TEXT,
            preferred_type TEXT,
            preferred_fuel TEXT,
            needs_awd INTEGER DEFAULT 0,
            family_size INTEGER,
            city TEXT,
            last_search TEXT,
            searches_count INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id)
        )
    """)

    # User memory v2 — JSON blob (supports arbitrary fields like financing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_memory_v2 (
            user_id TEXT PRIMARY KEY,
            memory  TEXT,
            updated_at TEXT
        )
    """)

    # Pattern learning — frequent questions and best answers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            best_response TEXT NOT NULL,
            frequency INTEGER DEFAULT 1,
            avg_score REAL DEFAULT 1.0,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pattern)
        )
    """)

    conn.commit()
    conn.close()


def save_good_response(question: str, response: str, intent: str, user_id: str):
    """Saves a liked response for future learning."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Check if similar question exists — increment score
        cursor.execute(
            "SELECT id, score FROM good_responses WHERE question = ? AND intent = ?",
            (question[:200], intent)
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                "UPDATE good_responses SET score = score + 1 WHERE id = ?",
                (existing[0],)
            )
        else:
            cursor.execute(
                "INSERT INTO good_responses (question, response, intent, user_id) VALUES (?, ?, ?, ?)",
                (question[:200], response[:2000], intent, user_id)
            )
        conn.commit()
    except Exception as e:
        print(f"save_good_response error: {e}")
    finally:
        conn.close()


def save_bad_response(question: str, response: str, intent: str, user_id: str):
    """Saves a disliked response to avoid repeating it."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO bad_responses (question, response, intent, user_id) VALUES (?, ?, ?, ?)",
            (question[:200], response[:2000], intent, user_id)
        )
        conn.commit()
    except Exception as e:
        print(f"save_bad_response error: {e}")
    finally:
        conn.close()


def get_similar_good_responses(question: str, limit: int = 3) -> list:
    """Finds similar good responses to inject as examples."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        keywords = question.lower().split()[:5]
        conditions = ' OR '.join(['LOWER(question) LIKE ?' for _ in keywords])
        params = [f'%{kw}%' for kw in keywords]
        params.append(limit)
        cursor.execute(f"""
            SELECT question, response, score FROM good_responses
            WHERE {conditions}
            ORDER BY score DESC LIMIT ?
        """, params)
        rows = cursor.fetchall()
        return [{"question": r[0], "response": r[1], "score": r[2]} for r in rows]
    except Exception as e:
        print(f"get_similar_good_responses error: {e}")
        return []
    finally:
        conn.close()


def update_user_memory(user_id: str, data: dict):
    """Updates persistent user memory (JSON blob — supports any field)."""
    import json
    from datetime import datetime
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT memory FROM user_memory_v2 WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            current = json.loads(row[0]) if row[0] else {}
            current.update(data)
            conn.execute(
                "UPDATE user_memory_v2 SET memory = ?, updated_at = ? WHERE user_id = ?",
                (json.dumps(current), datetime.now().isoformat(), user_id)
            )
        else:
            conn.execute(
                "INSERT INTO user_memory_v2 (user_id, memory, updated_at) VALUES (?, ?, ?)",
                (user_id, json.dumps(data), datetime.now().isoformat())
            )
        conn.commit()
    except Exception as e:
        print(f"[update_user_memory] error: {e}")
    finally:
        conn.close()


def get_user_memory(user_id: str) -> dict:
    """Gets persistent user memory (JSON blob)."""
    import json
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT memory FROM user_memory_v2 WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return {}
    except Exception as e:
        print(f"[get_user_memory] error: {e}")
        return {}
    finally:
        conn.close()


def reset_old_sessions():
    """Purge sessions SQLite > 24h (nettoyage préventif)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE created_at < datetime('now', '-1 day')")
        conn.commit()
        print("[database] Sessions > 24h supprimées")
    except Exception as e:
        print(f"[database] reset sessions error: {e}")
    finally:
        conn.close()


def get_popular_patterns() -> list:
    """Gets the most frequent/successful question patterns."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT question, response, score FROM good_responses
            ORDER BY score DESC LIMIT 5
        """)
        rows = cursor.fetchall()
        return [{"question": r[0], "response": r[1], "score": r[2]} for r in rows]
    except Exception as e:
        print(f"get_popular_patterns error: {e}")
        return []
    finally:
        conn.close()