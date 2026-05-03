import uuid
import requests
import inspect

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_conv_auto"
TEST_PASS = "testpass_229"

CONVERSATION = [
    {
        "msg": "Salut! J'ai vu un RAV4 2019 a 18 000$ sur Kijiji. C'est un bon prix?",
        "checks": {
            "alerte_prix_bas": lambda r: any(w in r.lower() for w in ["bas", "attention", "suspect", "verifi", "cache", "pepins", "inspecti"]),
            "mentionne_carfax": lambda r: any(w in r.lower() for w in ["carfax", "historique", "equifax"]),
            "calcule_taxes": lambda r: any(w in r.lower() for w in ["tps", "tvq", "taxes", "total"]),
        }
    },
    {
        "msg": "Comment je peux verifier s'il a eu un accident?",
        "checks": {
            "mentionne_carfax": lambda r: any(w in r.lower() for w in ["carfax", "equifax", "rapport"]),
            "mentionne_inspection": lambda r: "inspection" in r.lower(),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    {
        "msg": "Si j'achete d'un particulier, j'ai quels droits si le char est un citron?",
        "checks": {
            "mentionne_droits": lambda r: any(w in r.lower() for w in ["garantie legale", "vice cache", "lpc", "protection", "recours", "2 ans", "particulier"]),
            "compare_concessionnaire": lambda r: any(w in r.lower() for w in ["concessionnaire", "concession", "avantage", "difference"]),
        }
    },
    {
        "msg": "As-tu des RAV4 2019 dans ton inventaire?",
        "checks": {
            "retourne_fiches": lambda r, h: h,
            "prix_coherent": lambda r: any(w in r for w in ["$", "000"]),
            "alerte_kilometrage": lambda r: any(w in r.lower() for w in ["inspection", "km", "kilomet"]),
        }
    },
    {
        "msg": "Combien ca coute par mois si je finance la 3eme sur 60 mois a 7.99%?",
        "checks": {
            "calcule_mensualites": lambda r: any(w in r.lower() for w in ["/mois", "par mois", "mensualit", "mensuel"]),
            "mentionne_taux": lambda r: any(w in r.lower() for w in ["7.99", "taux", "%"]),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    {
        "msg": "Le vendeur me propose une garantie prolongee a 2 500$. Ca vaut la peine?",
        "checks": {
            "conseil_nuance": lambda r: any(w in r.lower() for w in ["depend", "utile", "negoci", "verifi", "couverture", "kilometrage"]),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    {
        "msg": "Ok je suis convaincu. Je veux voir la 3eme proposition ce samedi matin.",
        "checks": {
            "rdv_declenche": lambda r, h: h,
            "bon_vehicule": lambda r: any(w in r.lower() for w in ["rav4", "formulaire", "rdv", "rendez-vous", "concessionnaire"]),
        }
    },
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
    return (data.get("response", ""),
            bool(data.get("html_cards", "")))


def run_check(fn, response, has_cards):
    try:
        sig = inspect.signature(fn)
        if len(sig.parameters) == 2:
            return fn(response, has_cards)
        return fn(response)
    except Exception:
        return False


def main():
    token = get_token()
    session_id = str(uuid.uuid4())

    total_checks = 0
    passed_checks = 0

    print("=== TEST CONVERSATION AUTOMATISE ===\n")

    for i, turn in enumerate(CONVERSATION, 1):
        print(f"{'='*60}")
        print(f"TOUR {i}/{len(CONVERSATION)}")
        print(f"[CLIENT] {turn['msg']}\n")

        response, has_cards = chat(token, session_id, turn["msg"])

        print(f"[AGENT]  {response[:400]}"
              f"{'...' if len(response) > 400 else ''}")
        if has_cards:
            print("[FICHES] Presentes")
        print()

        print("[CHECKS]")
        for name, fn in turn["checks"].items():
            result = run_check(fn, response, has_cards)
            total_checks += 1
            if result:
                passed_checks += 1
                print(f"  [OK]   {name}")
            else:
                print(f"  [FAIL] {name}")
        print()

    print(f"{'='*60}")
    print(f"RESULTAT : {passed_checks}/{total_checks} checks passes")
    score = round(passed_checks / total_checks * 10, 1)
    print(f"SCORE    : {score}/10")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
