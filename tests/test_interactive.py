import uuid
import requests

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_interactive"
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
    return r.json().get("response", "")

def main():
    token = get_token()
    session_id = str(uuid.uuid4())

    print("=== TEST INTERACTIF 229Voitures ===")
    print("Tape 'quit' pour terminer\n")

    while True:
        message = input("[TOI] → ").strip()
        if message.lower() == "quit":
            break
        if not message:
            continue

        response = chat(token, session_id, message)
        print(f"\n[AGENT] → {response}\n")
        print("-" * 60 + "\n")

if __name__ == "__main__":
    main()
