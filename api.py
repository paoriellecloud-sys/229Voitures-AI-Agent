from fastapi import FastAPI, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from database import *
from auth import *
from modules.agent_chat import auto_chat, auto_chat_web, analyze_vehicle_url
from modules.scraper import analyze_listing, compare_listings

import numpy as np
import joblib
import os

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, confusion_matrix
from dotenv import load_dotenv

from modules.vin_checker import get_vehicle_report

load_dotenv()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)


# =============================
# STARTUP
# =============================

@app.on_event("startup")
def startup():
    create_vehicles_table()
    create_users_table()
    create_user_preferences_table()
    create_recommendation_history_table()


# =============================
# AUTH
# =============================

@app.post("/register")
def register(username: str, password: str):
    hashed_password = get_password_hash(password)
    if not create_user(username, hashed_password):
        return {"error": "User already exists"}
    return {"message": "User created successfully"}


@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_username(form_data.username)
    if not user:
        return {"error": "Invalid credentials"}
    if not verify_password(form_data.password, user["hashed_password"]):
        return {"error": "Invalid credentials"}
    access_token = create_access_token({"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}


# =============================
# ML - TRAIN
# =============================

@app.post("/train_model")
def train_model(current_user: dict = Depends(get_current_user)):
    data = get_training_data(current_user["id"])
    if len(data) < 10:
        return {"error": "Not enough data to train model (min 10 samples required)"}
    X = np.array([[d[0], d[1], d[2], d[3]] for d in data])
    y = np.array([d[4] for d in data])
    if len(set(y)) < 2:
        return {"error": "Need both liked and non-liked data to train model"}
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(X_train_scaled, y_train)
    y_pred = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    cm = confusion_matrix(y_test, y_pred).tolist()
    model_path = f"{MODEL_DIR}/model_user_{current_user['id']}.pkl"
    joblib.dump({"model": model, "scaler": scaler}, model_path)
    return {
        "message": "Model trained successfully",
        "accuracy": round(float(accuracy), 3),
        "precision": round(float(precision), 3),
        "recall": round(float(recall), 3),
        "confusion_matrix": cm
    }


# =============================
# ML RECOMMENDATION
# =============================

@app.post("/recommend_ml")
def recommend_ml(current_user: dict = Depends(get_current_user)):
    model_path = f"{MODEL_DIR}/model_user_{current_user['id']}.pkl"
    if not os.path.exists(model_path):
        return {"error": "Model not trained yet"}
    saved = joblib.load(model_path)
    model = saved["model"]
    scaler = saved["scaler"]
    vehicles = get_all_vehicles()
    scored = []
    for v in vehicles:
        X = np.array([[v["price"], v["mileage"], v["year"], v["consumption"]]])
        X_scaled = scaler.transform(X)
        probability = model.predict_proba(X_scaled)[0][1]
        scored.append({"vehicle": v, "like_probability": round(float(probability), 4)})
    scored = sorted(scored, key=lambda x: x["like_probability"], reverse=True)
    top5 = scored[:5]
    for item in top5:
        save_recommendation_action(current_user["id"], item["vehicle"]["id"], None)
    return top5


# =============================
# LIKE VEHICLE
# =============================

class LikeRequest(BaseModel):
    vehicle_id: int
    liked: int


@app.post("/like_vehicle")
def like_vehicle(request: LikeRequest, current_user: dict = Depends(get_current_user)):
    save_recommendation_action(current_user["id"], request.vehicle_id, request.liked)
    return {"message": "Action saved"}


# =============================
# AI VEHICLE EXPERT
# =============================

@app.post("/ai_vehicle_expert")
def ai_vehicle_expert(data: dict, current_user: dict = Depends(get_current_user)):
    vehicle_id = data.get("vehicle_id")
    question = data.get("question", "")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, price, mileage, year, consumption FROM vehicles WHERE id = ?", (vehicle_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"error": "Vehicle not found"}
    vehicle = {"id": row[0], "price": row[1], "mileage": row[2], "year": row[3], "consumption": row[4]}
    score = 0
    if vehicle["mileage"] < 100000: score += 2
    if vehicle["year"] >= 2018: score += 2
    if vehicle["price"] < 20000: score += 1
    if vehicle["consumption"] < 8: score += 1
    if score >= 4:
        advice = "Très bon achat potentiel."
    elif score >= 2:
        advice = "A analyser, mais peut être intéressant."
    else:
        advice = "Risque élevé, à vérifier attentivement."
    return {"vehicle": vehicle, "score": score, "advice": advice, "question": question}


# =============================
# 🤖 AGENT CHAT SIMPLE
# =============================

class ChatRequest(BaseModel):
    message: str


@app.post("/agent/chat")
def chat_agent(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Chat simple avec Gemini.
    Exemple: {"message": "Quelle est la meilleure Toyota Corolla 2022?"}
    """
    response = auto_chat(request.message)
    return {"response": response}


# =============================
# 🌐 AGENT CHAT + RECHERCHE WEB
# =============================

@app.post("/agent/chat_web")
def chat_agent_web(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Chat avec Gemini + Google Search en temps réel.
    Exemple: {"message": "Trouve-moi une Toyota Corolla 2023 moins de 25000$ au Québec"}
    """
    response = auto_chat_web(request.message)
    return {"response": response}


# =============================
# 🔗 ANALYSER UN LIEN
# =============================

class UrlRequest(BaseModel):
    url: str


@app.post("/agent/analyze_url")
def analyze_url(request: UrlRequest, current_user: dict = Depends(get_current_user)):
    """
    Analyse une annonce AutoTrader ou Kijiji via son URL.
    Exemple: {"url": "https://www.autotrader.ca/a/toyota/corolla/..."}
    """
    result = analyze_listing(request.url)
    return result


# =============================
# ⚖️ COMPARER 2 ANNONCES
# =============================

class CompareRequest(BaseModel):
    url1: str
    url2: str


@app.post("/agent/compare_urls")
def compare_urls(request: CompareRequest, current_user: dict = Depends(get_current_user)):
    """
    Compare 2 annonces automobiles et recommande la meilleure.
    Exemple: {"url1": "https://autotrader.ca/...", "url2": "https://kijiji.ca/..."}
    """
    result = compare_listings(request.url1, request.url2)
    return result


class VinRequest(BaseModel):
    vin: str

@app.post("/agent/check_vin")
def check_vin(
    request: VinRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    CarFax gratuit — rapport complet via VIN.
    Exemple: {"vin": "2T1BURHE0JC043821"}
    """
    result = get_vehicle_report(request.vin)
    return result

# =============================
# DEBUG ROUTES
# =============================

@app.get("/debug_history")
def debug_history(current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recommendation_history WHERE user_id = ?", (current_user["id"],))
    rows = cursor.fetchall()
    conn.close()
    return {"rows": rows}


@app.get("/debug_vehicles")
def debug_vehicles():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM vehicles")
    rows = cursor.fetchall()
    conn.close()
    return {"vehicles": rows}


@app.get("/debug_users")
def debug_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    return {"rows": rows}
