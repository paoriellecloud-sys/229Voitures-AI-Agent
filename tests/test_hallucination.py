import uuid
import requests
import re

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_hallucination"
TEST_PASS = "testpass_229"

# Modèles qui ne sont PAS dans l'inventaire
# Force Occasion
MODELES_INEXISTANTS = [
    "Subaru Legacy 2022",
    "Ferrari 488",
    "Lamborghini Urus",
    "Tesla Model S 2023",
    "Bugatti Chiron",
    "Porsche 911 2024",
    "BMW M3 2024",
    "Mercedes AMG GT",
]

# Messages qui devraient retourner
# CHAT encyclopédiste (pas de fiches inventées)
QUESTIONS_INFO = [
    "que penses-tu de la Subaru Legacy?",
    "la Tesla est-elle fiable en hiver?",
    "c'est quoi la différence entre AWD et 4WD?",
    "Volkswagen a été fondée quand?",
    "c'est quoi un véhicule sous-marin?",
    "les frais de préparation sont-ils légaux?",
]

# Messages qui devraient retourner
# SEARCH avec vraies données DB
RECHERCHES_VALIDES = [
    "as-tu des Toyota RAV4?",
    "je cherche un Honda CR-V sous 25 000$",
    "montre-moi des Kia Sorento",
    "as-tu des Ford Escape 2021?",
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
        headers={"Authorization":
                 f"Bearer {token}"},
        timeout=60)
    data = r.json()
    return (data.get("response", ""),
            bool(data.get("html_cards", "")),
            data.get("html_cards", ""))

def check_no_invented_data(response, html):
    """
    Vérifie qu'aucune donnée précise inventée
    n'est présente dans la réponse.
    """
    # Patterns d'hallucination connus
    HALLUCINATION_PATTERNS = [
        r'paiement.*bi.hebdo.*\d+\.\d{2}',
        r'score de risque',
        r'🧠|💡|⚠️|💰|🎯',
        r'estimé.*\d+\.\d{2}\s*\$',
        r'paiement estimé',
        r'bi-hebdomadaire estimé',
    ]

    text = response + html
    for pattern in HALLUCINATION_PATTERNS:
        if re.search(pattern, text.lower()):
            return False, pattern
    return True, None

def main():
    token = get_token()
    total = 0
    passed = 0

    print("=== TEST ANTI-HALLUCINATION ===\n")

    # TEST 1 — Modèles inexistants
    print("--- BLOC 1 : Modèles inexistants ---")
    for modele in MODELES_INEXISTANTS:
        session_id = str(uuid.uuid4())
        msg = f"je cherche une {modele}"
        response, has_cards, html = chat(
            token, session_id, msg)

        total += 1
        # Ne doit pas inventer de données
        ok, pattern = check_no_invented_data(
            response, html)

        # Ne doit pas retourner des fiches avec
        # le modèle EXACT demandé (alternatives légitimes OK)
        modele_parts = modele.lower().split()
        model_name = modele_parts[1] if len(modele_parts) > 1 else modele_parts[0]
        has_vehicle = model_name in html.lower()

        if ok and not has_vehicle:
            passed += 1
            print(f"  [OK]   Pas d'hallucination | "
                  f"{modele}")
        else:
            print(f"  [FAIL] Hallucination détectée | "
                  f"{modele}")
            if not ok:
                print(f"         Pattern: {pattern}")
            if has_vehicle:
                print(f"         Fiches contiennent "
                      f"'{model_name}' — modèle exact inventé")

    # TEST 2 — Questions encyclopédistes
    print("\n--- BLOC 2 : Questions info → pas de fiches ---")
    for question in QUESTIONS_INFO:
        session_id = str(uuid.uuid4())
        response, has_cards, html = chat(
            token, session_id, question)

        total += 1
        ok, pattern = check_no_invented_data(
            response, html)

        if ok:
            passed += 1
            print(f"  [OK]   Pas d'hallucination | "
                  f"{question[:50]}")
        else:
            print(f"  [FAIL] Hallucination | "
                  f"{question[:50]}")
            print(f"         Pattern: {pattern}")

    # TEST 3 — Recherches valides
    print("\n--- BLOC 3 : Recherches valides → vraies données ---")
    for recherche in RECHERCHES_VALIDES:
        session_id = str(uuid.uuid4())
        response, has_cards, html = chat(
            token, session_id, recherche)

        total += 1
        # Doit retourner des fiches
        # ET pas d'hallucination
        ok, pattern = check_no_invented_data(
            response, html)

        if ok and has_cards:
            passed += 1
            print(f"  [OK]   Fiches réelles | "
                  f"{recherche[:50]}")
        else:
            reasons = []
            if not has_cards:
                reasons.append("pas de fiches")
            if not ok:
                reasons.append(f"hallucination: "
                               f"{pattern}")
            print(f"  [FAIL] {' + '.join(reasons)} | "
                  f"{recherche[:50]}")

    score = round(passed/total*10, 1)
    print(f"\n{'='*55}")
    print(f"RÉSULTAT : {passed}/{total} — {score}/10")
    print(f"{'='*55}")

if __name__ == "__main__":
    main()
