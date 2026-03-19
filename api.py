from fastapi import FastAPI, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from database import *
from auth import *
from modules.agent_router import smart_chat

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

    # Create demo user if it doesn't exist
    if not get_user_by_username("demo229"):
        hashed_password = get_password_hash("demo229voitures")
        create_user("demo229", hashed_password)


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
# SMART AGENT — SINGLE ENTRY POINT
# =============================

class ChatRequest(BaseModel):
    message: str


@app.post("/agent/chat")
def chat_agent(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Single entry point for all user messages.
    Automatically detects intent and routes to the right function.
    Handles: general chat, vehicle search, URL analysis, URL comparison, VIN check.
    Example: {"message": "Trouve moi 2 Kia Seltos LX 2021 chez Force Occasion"}
    """
    result = smart_chat(request.message, user_id=current_user["username"])
    return result


# =============================
# IMAGE / CONTRACT ANALYSIS
# =============================

class ImageRequest(BaseModel):
    image_base64: str
    media_type: str = "image/jpeg"
    context: str = ""

@app.post("/agent/analyze_image")
def analyze_image(request: ImageRequest, current_user: dict = Depends(get_current_user)):
    """
    Analyzes a car contract or listing photo using Gemini Vision.
    Supports CCAQ contracts, dealer listings, and vehicle photos.
    """
    from google import genai
    from google.genai import types
    import os
    import base64

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    prompt = f"""
    Tu es AutoAgent 229Voitures, expert automobile et conseiller financier au Canada.
    Analyse cette image et identifie ce qu'elle contient.

    Contexte fourni par l'utilisateur : {request.context if request.context else "Aucun contexte fourni"}

    Si c'est un CONTRAT CCAQ ou contrat de vente automobile :
    Analyse systématiquement ces éléments :

    📋 RÉSUMÉ DU CONTRAT
    • Véhicule : [marque, modèle, année, VIN si visible]
    • Prix du véhicule (ligne A) : [valeur]
    • Prix après réduction (ligne E) : [valeur]
    • Véhicule d'échange (ligne F) : [valeur si applicable]
    • Sous-total taxes (ligne H) : [valeur]
    • TPS + TVQ calculées : [valeurs]
    • Accessoires additionnels (ligne P) : [valeur et détail]
    • Total à payer (ligne S) : [valeur]
    • Solde à la livraison (ligne W) : [valeur]
    • Taux de financement : [% si visible]
    • Paiements mensuels : [montant si visible]

    ✅ POINTS POSITIFS
    • [éléments favorables pour l'acheteur]

    ⚠️ POINTS À SURVEILLER
    • [anomalies, frais élevés, clauses à vérifier]

    🔴 RED FLAGS
    • [produits F&I surévalués, taux excessif, frais cachés]
    Produits F&I typiquement surévalués : garantie prolongée >2000$, renonciation de dette >2500$, protection peinture >800$

    💰 VÉRIFICATION DES CALCULS
    • TPS (5%) correcte ? [oui/non + calcul]
    • TVQ (9.975%) correcte ? [oui/non + calcul]
    • Total cohérent ? [oui/non]

    🎯 RECOMMANDATION
    [Signer ✅ / Négocier ⚠️ / Refuser ❌] — explication courte

    Si c'est une FICHE CLIENT ou formulaire de vente :
    Identifie les champs importants et explique à quoi sert chaque section pour aider l'utilisateur à comprendre le processus de vente.

    Si c'est une PHOTO DE VÉHICULE :
    Analyse l'état visible du véhicule et identifie les points à inspecter.

    ⚠️ Analyse à titre informatif. Consultez un professionnel avant de signer. 229Voitures n'est pas un conseiller juridique ou financier.
    """

    try:
        image_data = base64.b64decode(request.image_base64)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": request.media_type,
                                "data": request.image_base64
                            }
                        },
                        {"text": prompt}
                    ]
                }
            ]
        )

        return {
            "intent": "ANALYZE_IMAGE",
            "response": response.text,
            "context": request.context
        }

    except Exception as e:
        return {"error": f"Impossible d'analyser l'image : {str(e)}"}


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


@app.get("/debug_search")
def debug_search(current_user: dict = Depends(get_current_user)):
    from modules.scraper import serpapi_search
    results = serpapi_search("Kia Seltos LX 2021 occasion Quebec", 2)
    return {
        "serpapi_key_set": bool(os.getenv("SERPAPI_KEY")),
        "results": results
    }