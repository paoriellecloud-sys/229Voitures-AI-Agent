import uuid
import requests
import inspect

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_coherence"
TEST_PASS = "testpass_229"

SCENARIOS = [
    {
        "nom": "Cohérence info → achat → RDV",
        "conversation": [
            {
                "msg": "C'est quoi la différence entre un Kia Sorento et un Hyundai Santa Fe?",
                "checks": {
                    "pas_de_fiches": lambda r, h: not h,
                    "compare_les_deux": lambda r, h: all(w in r.lower() for w in ["sorento", "santa fe"]),
                    "reponse_substantielle": lambda r, h: len(r) > 100,
                }
            },
            {
                "msg": "Le Sorento m'intéresse plus. As-tu des Sorento en inventaire?",
                "checks": {
                    "retourne_fiches": lambda r, h: h,
                    "fiches_sorento": lambda r, h: "sorento" in r.lower(),
                }
            },
            {
                "msg": "C'est quoi le prix total avec taxes pour le premier?",
                "checks": {
                    "mentionne_taxes": lambda r, h: any(w in r.lower() for w in ["tps", "tvq", "total", "taxes"]),
                    "pas_nouvelles_fiches": lambda r, h: not h,
                    "prix_coherent": lambda r, h: any(w in r for w in ["$", "000"]),
                }
            },
            {
                "msg": "Le vendeur veut m'ajouter 599$ de frais de dossier. C'est normal?",
                "checks": {
                    "denonce_frais": lambda r, h: any(w in r.lower() for w in ["illégal", "opc", "lpc", "interdit"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Ok je veux un RDV pour le premier Sorento",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                    "bon_vehicule": lambda r, h: any(w in r.lower() for w in ["sorento", "formulaire", "concessionnaire"]),
                }
            },
        ]
    },
    {
        "nom": "Cohérence budget → alternatives → info",
        "conversation": [
            {
                "msg": "J'ai un budget de 300$/mois tout inclus. Qu'est-ce que tu as?",
                "checks": {
                    "calcule_budget": lambda r, h: any(w in r.lower() for w in ["mois", "budget", "17", "16", "15"]),
                    "retourne_fiches_ou_explique": lambda r, h: h or any(w in r.lower() for w in ["inventaire", "alerte", "budget"]),
                }
            },
            {
                "msg": "C'est quoi les modèles les plus fiables dans ce budget?",
                "checks": {
                    "suggestions_pertinentes": lambda r, h: any(w in r.lower() for w in ["honda", "toyota", "kia", "hyundai", "civic", "corolla", "elantra", "rio"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Le Honda Civic, c'est fiable en hiver au Québec?",
                "checks": {
                    "repond_hiver": lambda r, h: any(w in r.lower() for w in ["hiver", "neige", "québec", "traction", "pneus"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 80,
                }
            },
            {
                "msg": "As-tu des Civic dans mon budget?",
                "checks": {
                    "repond_inventaire": lambda r, h: h or any(w in r.lower() for w in ["inventaire", "alerte", "pas de civic", "budget"]),
                }
            },
        ]
    },
    {
        "nom": "Cohérence protection acheteur",
        "conversation": [
            {
                "msg": "Je magasine une voiture usagée. Quels sont les pièges à éviter en concession?",
                "checks": {
                    "mentionne_pieges": lambda r, h: any(w in r.lower() for w in ["frais", "garantie", "financement", "opc", "lpc", "inspection"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 150,
                }
            },
            {
                "msg": "Le concessionnaire m'offre un taux de 4.99% si je prends leur assurance vie à 129$/mois. C'est légal?",
                "checks": {
                    "denonce_vente_liee": lambda r, h: any(w in r.lower() for w in ["illégal", "lpc", "vente liée", "conditionnel", "interdit"]),
                    "calcule_cout": lambda r, h: any(w in r for w in ["129", "$"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Si j'achète et que le char brise après 3 semaines, j'ai quels recours?",
                "checks": {
                    "mentionne_recours": lambda r, h: any(w in r.lower() for w in ["garantie légale", "vice caché", "lpc", "tribunal", "recours", "protection"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 100,
                }
            },
            {
                "msg": "Montre-moi des Toyota RAV4 sous 28 000$",
                "checks": {
                    "retourne_fiches": lambda r, h: h,
                    "prix_dans_budget": lambda r, h: "rav4" in r.lower(),
                }
            },
            {
                "msg": "Je veux voir le deuxième. RDV samedi matin.",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                    "bon_vehicule": lambda r, h: any(w in r.lower() for w in ["rav4", "toyota", "formulaire"]),
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
        headers={"Authorization":
                 f"Bearer {token}"},
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
    except:
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
        print(f"{'='*60}")

        for i, turn in enumerate(
                scenario["conversation"], 1):
            print(f"\n--- Tour {i} ---")
            print(f"[CLIENT] {turn['msg']}\n")

            response, has_cards = chat(
                token, session_id, turn["msg"])

            print(f"[AGENT]  {response[:300]}"
                  f"{'...' if len(response)>300 else ''}")
            if has_cards:
                print("[FICHES] Présentes")

            print("\n[CHECKS]")
            for name, fn in turn["checks"].items():
                result = run_check(
                    fn, response, has_cards)
                total += 1
                grand_total += 1
                if result:
                    passed += 1
                    grand_passed += 1
                    print(f"  [OK]   {name}")
                else:
                    print(f"  [FAIL] {name}")

        score = round(passed/total*10, 1)
        print(f"\nSCORE : {passed}/{total} — {score}/10")

    print(f"\n{'='*60}")
    score_final = round(grand_passed/grand_total*10, 1)
    print(f"SCORE GLOBAL : {grand_passed}/{grand_total}"
          f" — {score_final}/10")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
