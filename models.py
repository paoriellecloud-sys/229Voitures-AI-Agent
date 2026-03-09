from database import get_connection

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
# RECOMMENDATION HISTORY
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