import uuid
import requests
import inspect

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_conv_scenarios"
TEST_PASS = "testpass_229"

SCENARIOS = [
    {
        "nom": "Marie — Maman méfiante",
        "description": "Famille de 4, budget serré, craint les arnaques",
        "conversation": [
            {
                "msg": "Bonjour, je cherche un VUS 7 places pour ma famille. On est 4 enfants et mon mari. Budget 500$/mois tout inclus.",
                "checks": {
                    "vehicule_7_places": lambda r, h: any(w in r.lower() for w in ["7 places", "7places", "sorento", "telluride", "palisade", "traverse", "pilot", "sienna", "carnival", "familial", "pas de 7 places", "depasse", "alerte"]),
                    "budget_compris": lambda r, h: any(w in r.lower() for w in ["500", "mois", "budget", "mensuel", "28 000", "27 000", "29 000", "pouvoir d'achat", "taxes incluses"]),
                }
            },
            {
                "msg": "Le vendeur m'a dit que je dois payer 899$ de frais de preparation en plus. C'est normal?",
                "checks": {
                    "denonce_frais": lambda r, h: any(w in r.lower() for w in ["illegal", "illegaux", "opc", "lpc", "interdit", "refuser", "abusif"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Si je fais financer a 8.99% sur 84 mois, c'est une bonne idee?",
                "checks": {
                    "deconseille_84_mois": lambda r, h: any(
                        w in r.lower() for w in [
                            "long", "interet", "intérêt",
                            "couter", "coûter", "attention",
                            "risque", "depasse", "dépasse",
                            "valeur", "cher", "payer plus",
                            "durée", "duree", "84", "total"
                        ]
                    ),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Ok, montre-moi ce que t'as pour ma famille",
                "checks": {
                    "retourne_vehicules": lambda r, h: h,
                    "vehicule_famille": lambda r, h: any(w in r.lower() for w in ["sorento", "telluride", "palisade", "sienna", "traverse", "pilot", "carnival", "7 places", "familial"]),
                }
            },
            {
                "msg": "Je veux prendre rendez-vous pour voir le premier samedi apres-midi",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                    "formulaire_present": lambda r, h: any(w in r.lower() for w in ["formulaire", "concessionnaire", "rdv", "rendez-vous", "prenom", "courriel"]),
                }
            },
        ]
    },
    {
        "nom": "Kevin — Jeune acheteur",
        "description": "Premier achat, pas de crédit, veut une citadine",
        "conversation": [
            {
                "msg": "Salut! C'est mon premier char. J'ai pas vraiment de credit. Budget 200$/mois max. Je veux quelque chose de pas trop vieux.",
                "checks": {
                    "aborde_credit": lambda r, h: any(w in r.lower() for w in ["credit", "dossier", "taux", "financement"]),
                    "budget_realiste": lambda r, h: any(w in r.lower() for w in ["200", "budget", "11 000", "12 000", "10 000"]),
                }
            },
            {
                "msg": "Le concessionnaire me propose un taux de 19.99% parce que j'ai pas de credit. C'est normal?",
                "checks": {
                    "alerte_taux_eleve": lambda r, h: any(w in r.lower() for w in ["eleve", "cher", "attention", "normal", "sous-marin", "negocie", "compare"]),
                    "conseil_concret": lambda r, h: len(r) > 100,
                }
            },
            {
                "msg": "C'est quoi les voitures les plus fiables pour mon budget?",
                "checks": {
                    "suggestions_pertinentes": lambda r, h: any(w in r.lower() for w in ["honda", "toyota", "hyundai", "kia", "civic", "corolla", "accent", "elantra", "rio"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Montre-moi des Civic ou Corolla dans mon budget",
                "checks": {
                    "retourne_fiches": lambda r, h: h,
                    "prix_dans_budget": lambda r, h: any(w in r for w in ["$", "000"]),
                }
            },
            {
                "msg": "Ok la deuxieme me plait. Je veux aller la voir demain matin.",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                    "bon_vehicule": lambda r, h: any(w in r.lower() for w in ["formulaire", "rdv", "concessionnaire", "rendez-vous"]),
                }
            },
        ]
    },
    {
        "nom": "Robert — Client difficile",
        "description": "Sceptique, teste les limites, veut un Ferrari",
        "conversation": [
            {
                "msg": "J'ai lu que vous etes des arnaqueurs. Pourquoi je devrais vous faire confiance?",
                "checks": {
                    "repond_professionnellement": lambda r, h: len(r) > 80,
                    "pas_defensif": lambda r, h: not any(w in r.lower() for w in ["insulte", "grossier", "impoli"]),
                }
            },
            {
                "msg": "Ok. Trouvez-moi une Ferrari 488 2020 pour 15 000$.",
                "checks": {
                    "refuse_poliment": lambda r, h: any(w in r.lower() for w in ["pas", "n'avons", "inventaire", "impossible", "n'a pas"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "C'est quoi votre meilleure voiture de sport en inventaire?",
                "checks": {
                    "repond_honnêtement": lambda r, h: len(r) > 50,
                }
            },
            {
                "msg": "Le concessionnaire m'a dit que si je prends leur assurance vie a 150$/mois, j'ai un taux de 2.99%. Sinon c'est 9.99%. C'est legal?",
                "checks": {
                    "denonce_vente_liee": lambda r, h: any(w in r.lower() for w in ["illegal", "illegaux", "lpc", "opc", "interdit", "vente liee", "conditionnel", "abusif"]),
                    "conseil_clair": lambda r, h: len(r) > 100,
                }
            },
            {
                "msg": "Ok finalement t'as convaincu. Montre-moi tes meilleures options sous 30 000$.",
                "checks": {
                    "retourne_fiches": lambda r, h: h or any(w in r.lower() for w in ["pas en inventaire", "n'ai rien", "depasse", "minimum", "moins cher", "alerte", "disponible"]),
                    "prix_dans_budget": lambda r, h: any(w in r for w in ["$", "000"]),
                }
            },
            {
                "msg": "Je prends la premiere. RDV vendredi soir.",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                }
            },
        ]
    }
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

    grand_total = 0
    grand_passed = 0

    for scenario in SCENARIOS:
        session_id = str(uuid.uuid4())
        total = 0
        passed = 0

        print(f"\n{'='*60}")
        print(f"SCENARIO : {scenario['nom']}")
        print(f"          {scenario['description']}")
        print(f"{'='*60}")

        for i, turn in enumerate(scenario["conversation"], 1):
            print(f"\n--- Tour {i} ---")
            print(f"[CLIENT] {turn['msg']}\n")

            response, has_cards = chat(token, session_id, turn["msg"])

            print(f"[AGENT]  {response[:350]}"
                  f"{'...' if len(response) > 350 else ''}")
            if has_cards:
                print("[FICHES] Presentes")

            print("\n[CHECKS]")
            for name, fn in turn["checks"].items():
                result = run_check(fn, response, has_cards)
                total += 1
                grand_total += 1
                if result:
                    passed += 1
                    grand_passed += 1
                    print(f"  [OK]   {name}")
                else:
                    print(f"  [FAIL] {name}")

        score = round(passed / total * 10, 1)
        print(f"\nSCORE {scenario['nom']} : {passed}/{total} — {score}/10")

    print(f"\n{'='*60}")
    score_final = round(grand_passed / grand_total * 10, 1)
    print(f"SCORE GLOBAL : {grand_passed}/{grand_total} — {score_final}/10")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
