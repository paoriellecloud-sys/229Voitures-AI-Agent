import os
import uuid
import requests
from google import genai
from google.genai import types

BASE_URL = "http://148.116.73.158:8000"
AGENT_URL = f"{BASE_URL}/agent/chat"
MAX_TURNS = 12
TEST_USER = "test_interviewer"
TEST_PASS = "testpass_229"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

PERSONA = """
Tu es un acheteur québécois de 35 ans, Québec.
Budget : 400$/mois tout inclus.
Tu cherches un VUS fiable pour l'hiver.
Tu es méfiant des concessionnaires.

PROGRESSION OBLIGATOIRE — respecte cet ordre :
Tours 1-2 : Budget et recherche de véhicule
Tours 3-4 : Demande des fiches précises
Tours 5-6 : Prix, taxes, frais cachés
Tours 7-8 : Financement et pièges (assurance forcée, frais dossier)
Tours 9-10 : Négociation du prix
Tours 11 : Prise de rendez-vous
Tour 12 : Question sur recours si problème après achat

RÈGLES :
- Pose UNE question courte par tour
- Ne réponds JAMAIS toi-même — attends la réponse de l'agent
- Si l'agent est vague, insiste avec "Peux-tu être plus précis?"
- Réagis aux réponses de l'agent naturellement
- Reste dans le sujet automobile québécois
"""

def get_token():
    requests.post(f"{BASE_URL}/register",
        params={"username": TEST_USER,
                "password": TEST_PASS})
    r = requests.post(f"{BASE_URL}/login",
        data={"username": TEST_USER,
              "password": TEST_PASS})
    token = r.json().get("access_token")
    if not token:
        raise Exception(f"Token non trouvé: {r.json()}")
    return token

def ask_agent(token, session_id, message):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(AGENT_URL,
        json={"message": message,
              "session_id": session_id},
        headers=headers,
        timeout=60)
    r.raise_for_status()
    return r.json().get("response", "")

def ask_gemini(prompt, history, max_tokens=300):
    history.append({"role": "user",
                    "parts": [{"text": prompt}]})
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=history,
        config=types.GenerateContentConfig(
            system_instruction=PERSONA,
            max_output_tokens=max_tokens
        )
    )
    answer = response.text.strip()
    history.append({"role": "model",
                    "parts": [{"text": answer}]})
    return answer

def main():
    print("=== TEST INTERVIEWER IA — 229Voitures ===\n")

    token = get_token()
    session_id = str(uuid.uuid4())
    chat_history = []
    conversation = []

    # Message initial pour lancer la conversation
    question = ask_gemini(
        "Commence par te présenter brièvement "
        "et pose ta première question sur le budget.",
        chat_history
    )

    for turn in range(1, MAX_TURNS + 1):
        print(f"--- Tour {turn}/{MAX_TURNS} ---")
        print(f"[CLIENT] {question}\n")

        # Agent répond
        answer = ask_agent(token, session_id, question)
        print(f"[AGENT]  {answer[:400]}{'...' if len(answer) > 400 else ''}\n")

        conversation.append({"question": question, "agent": answer})

        # Gemini génère la prochaine question (sauf après le dernier tour)
        if turn < MAX_TURNS:
            question = ask_gemini(
                f"L'agent a répondu : {answer[:400]}\n\nPose ta prochaine question.",
                chat_history
            )

    # Évaluation finale
    print("\n=== ÉVALUATION FINALE ===\n")
    eval_prompt = """Sur la base de cette conversation complète,
donne une note sur 10 à l'agent 229Voitures.
Évalue :
- Honnêteté et transparence
- Protection acheteur (frais illégaux, pièges)
- Connaissance du marché québécois
- Comportement compagnon vs vendeur
- Qualité des conseils
Sois précis et critique."""

    eval_response = gemini_client.models.generate_content(
        model="gemini-2.5-pro",
        contents=chat_history + [{
            "role": "user",
            "parts": [{"text": eval_prompt}]
        }],
        config=types.GenerateContentConfig(
            max_output_tokens=4000,
            temperature=0.3
        )
    )
    print(f"[NOTE FINALE]\n{eval_response.text}")

if __name__ == "__main__":
    main()
