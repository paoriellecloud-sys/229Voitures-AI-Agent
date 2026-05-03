import os
import uuid
import requests
import anthropic

BASE_URL = "http://148.116.73.158:8000"
AGENT_URL = f"{BASE_URL}/agent/chat"
MAX_TURNS = 12
TEST_USER = "test_interviewer"
TEST_PASS = "testpass_229"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

persona_prompt = """
Tu es un acheteur québécois de 35 ans vivant à Québec.
Budget : environ 400$/mois tout inclus (taxes, etc.).
Tu cherches un VUS fiable pour l'hiver.
Tu es méfiant des concessionnaires (peur des arnaques, frais cachés).
Tu ne connais rien en mécanique.

TON RÔLE : Tester l'agent "229Voitures" pour voir s'il est compétent et honnête.

INSTRUCTIONS :
1. Pose UNE question à la fois, courte et naturelle.
2. Sois naturel, curieux et sceptique.
3. Progression : Budget -> Véhicule précis -> Fiabilité ->
   Prix/Taxes -> Financement/Pièges -> Négociation -> RDV.
4. Si l'agent est vague, insiste.
5. Si l'agent dit quelque chose de suspect, relève-le.
6. Réponds uniquement avec la question pour ce tour.
"""

def get_token():
    requests.post(f"{BASE_URL}/register",
        params={"username": TEST_USER, "password": TEST_PASS})
    r = requests.post(f"{BASE_URL}/login",
        params={"username": TEST_USER, "password": TEST_PASS})
    return r.json().get("access_token")

def ask_agent(token, session_id, message):
    r = requests.post(AGENT_URL,
        json={"message": message, "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "")

def ask_claude(conversation_history):
    msg = client.messages.create(
        model="claude-sonnet-4-5-20251022",
        max_tokens=300,
        system=persona_prompt,
        messages=conversation_history
    )
    return msg.content[0].text.strip()

def main():
    print("=== TEST INTERVIEWER IA — 229Voitures ===\n")

    token = get_token()
    session_id = str(uuid.uuid4())
    conversation_history = []

    for turn in range(1, MAX_TURNS + 1):
        print(f"--- Tour {turn}/{MAX_TURNS} ---")

        # Claude génère la question
        question = ask_claude(conversation_history)
        print(f"[CLIENT] {question}\n")

        # Agent répond
        answer = ask_agent(token, session_id, question)
        # Garder seulement le texte, pas le HTML
        print(f"[AGENT]  {answer[:300]}...\n"
              if len(answer) > 300 else f"[AGENT]  {answer}\n")

        # Mettre à jour l'historique
        conversation_history.append(
            {"role": "assistant", "content": question})
        conversation_history.append(
            {"role": "user",
             "content": f"L'agent a répondu : {answer[:500]}"})

    # Évaluation finale
    print("\n=== ÉVALUATION FINALE ===\n")
    conversation_history.append({
        "role": "user",
        "content": """Sur la base de cette conversation complète,
        donne une note sur 10 à l'agent 229Voitures.
        Évalue : honnêteté, protection acheteur,
        connaissance du marché québécois,
        qualité des conseils, comportement compagnon vs vendeur.
        Sois précis et critique."""
    })

    evaluation = ask_claude(conversation_history)
    print(f"[NOTE FINALE]\n{evaluation}")

    print("\n=== FIN DU TEST ===")

if __name__ == "__main__":
    main()
