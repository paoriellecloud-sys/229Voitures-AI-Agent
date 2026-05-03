import os
import uuid
import requests
import google.generativeai as genai

BASE_URL = "http://148.116.73.158:8000"
AGENT_URL = f"{BASE_URL}/agent/chat"
MAX_TURNS = 12
TEST_USER = "test_interviewer"
TEST_PASS = "testpass_229"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")

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
        params={"username": TEST_USER,
                "password": TEST_PASS})
    return r.json().get("access_token")

def ask_agent(token, session_id, message):
    r = requests.post(AGENT_URL,
        json={"message": message,
              "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60)
    r.raise_for_status()
    return r.json().get("response", "")

def main():
    print("=== TEST INTERVIEWER IA — 229Voitures ===\n")

    token = get_token()
    session_id = str(uuid.uuid4())

    chat = gemini.start_chat(history=[])

    # Message initial pour lancer la conversation
    chat.send_message(PERSONA +
        "\n\nCommence par te présenter brièvement "
        "et pose ta première question sur le budget.")

    conversation = []

    for turn in range(1, MAX_TURNS + 1):
        print(f"--- Tour {turn}/{MAX_TURNS} ---")

        # Gemini génère la question
        if turn == 1:
            question = chat.last.text.strip()
        else:
            response = chat.send_message(
                f"L'agent a répondu : {conversation[-1]['agent'][:400]}"
                "\n\nPose ta prochaine question.")
            question = response.text.strip()

        print(f"[CLIENT] {question}\n")

        # Agent répond
        answer = ask_agent(token, session_id, question)
        print(f"[AGENT]  {answer[:400]}{'...' if len(answer) > 400 else ''}\n")

        conversation.append({
            "question": question,
            "agent": answer
        })

    # Évaluation finale
    print("\n=== ÉVALUATION FINALE ===\n")
    eval_response = chat.send_message(
        """Sur la base de cette conversation complète,
        donne une note sur 10 à l'agent 229Voitures.
        Évalue :
        - Honnêteté et transparence
        - Protection acheteur (frais illégaux, pièges)
        - Connaissance du marché québécois
        - Comportement compagnon vs vendeur
        - Qualité des conseils
        Sois précis et critique."""
    )
    print(f"[NOTE FINALE]\n{eval_response.text}")
    print("\n=== FIN DU TEST ===")

if __name__ == "__main__":
    main()
