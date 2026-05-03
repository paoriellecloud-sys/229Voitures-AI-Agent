import uuid
import requests

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_conv_rdv"
TEST_PASS = "testpass_229"

MESSAGES = [
    "Salut, j'ai vu un RAV4 2019 à 18 000$ "
    "sur Kijiji. C'est un bon prix?",

    "Comment je peux vérifier "
    "s'il a eu un accident?",

    "Si j'achète d'un particulier, "
    "j'ai quels droits si le char "
    "est un citron?",

    "As-tu des RAV4 2019 "
    "dans ton inventaire?",

    "Combien ça va me coûter par mois "
    "si je finance la 3ème sur 60 mois?",

    "Le vendeur me propose une garantie "
    "prolongée à 2 500$. "
    "Ça vaut la peine?",

    "Ok je veux voir la 3ème proposition. "
    "Je veux un RDV pour samedi matin."
]

def get_token():
    requests.post(f"{BASE_URL}/register",
        params={"username": TEST_USER,
                "password": TEST_PASS})
    r = requests.post(f"{BASE_URL}/login",
        data={"username": TEST_USER,
              "password": TEST_PASS})
    return r.json().get("access_token")

def chat(token, session_id, message):
    r = requests.post(f"{BASE_URL}/agent/chat",
        json={"message": message,
              "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60)
    data = r.json()
    return data.get("response", ""), \
           bool(data.get("html_cards", ""))

def main():
    token = get_token()
    session_id = str(uuid.uuid4())

    print("=== TEST CONVERSATION → RDV ===\n")

    for i, message in enumerate(MESSAGES, 1):
        print(f"--- Message {i}/{len(MESSAGES)} ---")
        print(f"[TOI]   {message}\n")

        response, has_cards = chat(
            token, session_id, message)

        print(f"[AGENT] {response[:500]}"
              f"{'...' if len(response) > 500 else ''}")

        if has_cards:
            print("[FICHES] Fiches affichees")

        # Vérification RDV au dernier message
        if i == len(MESSAGES):
            if has_cards and any(
                w in response.lower()
                for w in ["formulaire", "rendez-vous",
                          "rdv", "concessionnaire",
                          "prenom", "courriel"]):
                print("\n[OK] RDV DECLENCHE — SUCCES")
            else:
                print("\n[FAIL] RDV NON DECLENCHE — ECHEC")

        print()

    print("=== FIN DU TEST ===")

if __name__ == "__main__":
    main()
