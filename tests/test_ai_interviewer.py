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
Tu es un acheteur québécois de 35 ans vivant à Québec.
Budget : environ 400$/mois tout inclus.
Tu cherches un VUS fiable pour l'hiver.
Tu es méfiant des concessionnaires.
Tu ne connais rien en mécanique.

RÔLE : Tester l'agent 229Voitures.
INSTRUCTIONS :
- Pose UNE question courte et naturelle par tour
- Progression : Budget → Véhicule → Fiabilité →
  Prix/Taxes → Financement/Pièges → Négociation → RDV
- Si l'agent est vague, insiste
- Si quelque chose te semble suspect, relève-le
- Réponds UNIQUEMENT avec ta question, rien d'autre
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

def ask_gemini(prompt, history):
    history.append({"role": "user",
                    "parts": [{"text": prompt}]})
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=history,
        config=types.GenerateContentConfig(
            system_instruction=PERSONA,
            max_output_tokens=300
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
    evaluation = ask_gemini(
        """Sur la base de cette conversation complète,
        donne une note sur 10 à l'agent 229Voitures.
        Évalue :
        - Honnêteté et transparence
        - Protection acheteur (frais illégaux, pièges)
        - Connaissance du marché québécois
        - Comportement compagnon vs vendeur
        - Qualité des conseils
        Sois précis et critique.""",
        chat_history
    )
    print(f"[NOTE FINALE]\n{evaluation}")
    print("\n=== FIN DU TEST ===")

if __name__ == "__main__":
    main()
