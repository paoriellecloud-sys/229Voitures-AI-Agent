import uuid
import requests
import inspect

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_conv_scenarios2"
TEST_PASS = "testpass_229"

SCENARIOS = [
    {
        "nom": "Luc — Curieux encyclopédiste",
        "description": "Pose des questions générales sur l'auto au Québec",
        "conversation": [
            {
                "msg": "C'est quoi exactement un véhicule sous-marin?",
                "checks": {
                    "explique_sous_marin": lambda r, h: any(w in r.lower() for w in ["accident", "inondé", "eau", "dommage", "caché", "historique", "carfax"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 80,
                }
            },
            {
                "msg": "Pourquoi les prix des voitures usagées ont autant monté depuis 2020?",
                "checks": {
                    "mentionne_causes": lambda r, h: any(w in r.lower() for w in ["covid", "puce", "pénurie", "demande", "offre", "production", "semi-conducteur", "pandémie"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 100,
                }
            },
            {
                "msg": "C'est quoi la différence entre un concessionnaire certifié et un vendeur indépendant?",
                "checks": {
                    "mentionne_differences": lambda r, h: any(w in r.lower() for w in ["garantie", "inspection", "opc", "lpc", "certifié", "indépendant", "recours", "protection"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Pis c'est quoi les frais F&I dont tout le monde parle?",
                "checks": {
                    "explique_fi": lambda r, h: any(w in r.lower() for w in ["finance", "insurance", "assurance", "garantie", "produit", "marge", "profit", "concessionnaire"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 100,
                }
            },
            {
                "msg": "Ok, asteure montre-moi des Kia Sorento dans mon budget de 500$/mois",
                "checks": {
                    "retourne_fiches": lambda r, h: h,
                    "calcule_budget": lambda r, h: any(w in r.lower() for w in ["mois", "budget", "28", "29", "30", "taxes"]),
                }
            },
        ]
    },
    {
        "nom": "Diane — Acheteuse prudente",
        "description": "Vérifie chaque information avant d'agir",
        "conversation": [
            {
                "msg": "J'ai entendu dire que les Kia et Hyundai peuvent se faire voler facilement. C'est vrai?",
                "checks": {
                    "repond_honnêtement": lambda r, h: any(w in r.lower() for w in ["vol", "tiktok", "défi", "vrai", "modèles", "sonata", "elantra", "immobiliseur", "antivol"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Si j'achète un véhicule usagé en concession et qu'il brise après 2 semaines, j'ai quels recours?",
                "checks": {
                    "mentionne_recours": lambda r, h: any(w in r.lower() for w in ["garantie légale", "vice caché", "lpc", "opc", "tribunal", "recours", "30 jours", "protection"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 100,
                }
            },
            {
                "msg": "Est-ce que je peux négocier le prix d'un véhicule usagé en concession au Québec?",
                "checks": {
                    "encourage_negociation": lambda r, h: any(w in r.lower() for w in ["oui", "négoci", "marché", "prix", "levier", "argument", "offre"]),
                    "conseils_concrets": lambda r, h: len(r) > 80,
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "C'est quoi un bon kilométrage pour un véhicule usagé de 5 ans?",
                "checks": {
                    "donne_repere": lambda r, h: any(w in r.lower() for w in ["20 000", "25 000", "15 000", "km", "année", "entretien", "moyen", "normale"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Ok je cherche une Toyota Corolla 2020 ou 2021 en bon état",
                "checks": {
                    "retourne_fiches": lambda r, h: h,
                    "mentionne_inspection": lambda r, h: any(w in r.lower() for w in ["inspection", "carfax", "mécanique", "vérifi"]),
                }
            },
            {
                "msg": "La deuxième m'intéresse. Je veux prendre rendez-vous.",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                    "formulaire_present": lambda r, h: any(w in r.lower() for w in ["formulaire", "rdv", "rendez-vous", "concessionnaire", "prénom"]),
                }
            },
        ]
    },
    {
        "nom": "Alex — Tech savvy",
        "description": "Pose des questions techniques précises",
        "conversation": [
            {
                "msg": "Quelle est la différence entre un hybride, un hybride rechargeable et un électrique pur?",
                "checks": {
                    "explique_3_types": lambda r, h: any(w in r.lower() for w in ["hybride", "phev", "bev", "batterie", "moteur", "essence", "électrique", "rechargeable"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 150,
                }
            },
            {
                "msg": "Pour un hybride rechargeable, c'est vrai que la batterie se dégrade avec le temps?",
                "checks": {
                    "repond_precis": lambda r, h: any(w in r.lower() for w in ["batterie", "dégrada", "capacité", "année", "cycle", "garanti", "kilométrage"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "C'est quoi la différence entre AWD et 4WD? Pour le Québec c'est lequel le mieux?",
                "checks": {
                    "explique_difference": lambda r, h: any(w in r.lower() for w in ["awd", "4wd", "intégrale", "permanent", "hiver", "neige", "traction", "québec"]),
                    "pas_de_fiches": lambda r, h: not h,
                    "reponse_substantielle": lambda r, h: len(r) > 100,
                }
            },
            {
                "msg": "As-tu des RAV4 hybrides ou Prime en inventaire?",
                "checks": {
                    "retourne_fiches": lambda r, h: h or any(w in r.lower() for w in ["rav4", "inventaire", "alerte", "pas de"]),
                    "mentionne_rabais": lambda r, h: any(w in r.lower() for w in ["rabais", "roulez vert", "usagé", "neuf", "gouvernement", "subvention"]),
                }
            },
            {
                "msg": "Le Premier est-il admissible aux rabais gouvernementaux?",
                "checks": {
                    "reponse_correcte_rabais": lambda r, h: any(w in r.lower() for w in ["non", "usagé", "neuf", "pas admissible", "roulez vert", "occasion"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Ok je veux voir le premier samedi matin.",
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
        print(f"          {scenario['description']}")
        print(f"{'='*60}")

        for i, turn in enumerate(scenario["conversation"], 1):
            print(f"\n--- Tour {i} ---")
            print(f"[CLIENT] {turn['msg']}\n")

            response, has_cards = chat(
                token, session_id, turn["msg"])

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

        score = round(passed/total*10, 1)
        print(f"\nSCORE {scenario['nom']} : {passed}/{total} — {score}/10")

    print(f"\n{'='*60}")
    score_final = round(grand_passed/grand_total*10, 1)
    print(f"SCORE GLOBAL : {grand_passed}/{grand_total} — {score_final}/10")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
