import sqlite3

DB_NAME = "vehicles.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


# ==============================
# TABLES
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
            "id": r[0],
            "brand": r[1],
            "model": r[2],
            "year": r[3],
            "price": r[4],
            "fuel_type": r[5],
            "transmission": r[6],
            "mileage": r[7],
            "consumption": r[8],
            "location": r[9],
            "description": r[10],
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
        SELECT 
            v.price,
            v.mileage,
            v.year,
            v.consumption,
            r.liked
        FROM recommendation_history r
        JOIN vehicles v ON r.vehicle_id = v.id
        WHERE r.user_id = ?
          AND r.liked IS NOT NULL
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


def create_all_tables():
    """Crée toutes les tables en une seule fonction"""
    create_vehicles_table()
    create_users_table()
    create_user_preferences_table()
    create_recommendation_history_table()