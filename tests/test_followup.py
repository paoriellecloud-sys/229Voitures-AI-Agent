import uuid
import requests

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_followup"
TEST_PASS = "testpass_229"

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

    print("=== TEST FOLLOWUP CONVERSATION ===\n")

    CONVERSATION = [
        {
            "msg": "As-tu des Volkswagen Jetta?",
            "check": "fiches",
            "desc": "T1 — Recherche Jetta → fiches attendues"
        },
        {
            "msg": "Comment se fait-il que la première a autant de km?",
            "check": "no_fiches",
            "desc": "T2 — FOLLOWUP km → réponse textuelle, pas de nouvelles fiches"
        },
        {
            "msg": "C'est quoi la différence entre la première et la deuxième?",
            "check": "no_fiches",
            "desc": "T3 — FOLLOWUP comparaison → réponse textuelle"
        },
        {
            "msg": "La deuxième m'intéresse. C'est fiable comme modèle?",
            "check": "no_fiches",
            "desc": "T4 — FOLLOWUP opinion → réponse textuelle"
        },
        {
            "msg": "Ok je veux un RDV pour la deuxième samedi matin",
            "check": "fiches",
            "desc": "T5 — RDV sur proposition 2 → formulaire attendu"
        },
    ]

    passed = 0
    total = len(CONVERSATION)

    for i, turn in enumerate(CONVERSATION, 1):
        print(f"--- {turn['desc']} ---")
        print(f"[CLIENT] {turn['msg']}\n")

        response, has_cards = chat(
            token, session_id, turn["msg"])

        print(f"[AGENT]  {response[:400]}"
              f"{'...' if len(response) > 400 else ''}")

        if has_cards:
            print("[FICHES] Présentes")

        # Vérification
        if turn["check"] == "fiches":
            ok = has_cards
        else:
            ok = not has_cards

        if ok:
            passed += 1
            print(f"[OK] ✅")
        else:
            print(f"[FAIL] ❌ — "
                  f"{'Fiches attendues' if turn['check'] == 'fiches' else 'Fiches non attendues'}")

        print()

    print(f"{'='*50}")
    print(f"RÉSULTAT : {passed}/{total}")

if __name__ == "__main__":
    main()
