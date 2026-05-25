import uuid
import requests
import inspect

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_stress"
TEST_PASS = "testpass_229"

SCENARIOS = [
    {
        "nom": "Client indécis — change d'avis 5 fois",
        "conversation": [
            {
                "msg": "Je cherche quelque chose de fiable pour ma famille",
                "checks": {
                    "demande_precision": lambda r, h: any(w in r.lower() for w in ["budget", "modèle", "combien", "précis"]),
                }
            },
            {
                "msg": "Autour de 400 par mois",
                "checks": {
                    "comprend_budget": lambda r, h: any(w in r.lower() for w in ["400", "mois", "budget", "22", "23"]),
                }
            },
            {
                "msg": "Un VUS genre",
                "checks": {
                    "retourne_fiches": lambda r, h: h,
                }
            },
            {
                "msg": "Non finalement je veux quelque chose de plus économique",
                "checks": {
                    "cherche_alternatives": lambda r, h: h or any(w in r.lower() for w in ["économique", "berline", "compact", "civic", "corolla"]),
                }
            },
            {
                "msg": "Ok montre moi le premier que tu m'avais montré tantôt",
                "checks": {
                    "souvient_premier": lambda r, h: any(w in r.lower() for w in ["proposition", "premier", "$", "km"]),
                }
            },
            {
                "msg": "C'est combien avec les taxes et le financement sur 60 mois",
                "checks": {
                    "calcule_tout": lambda r, h: any(w in r.lower() for w in ["tps", "tvq", "total", "mois", "/"]),
                    "pas_nouvelles_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Finalement je veux voir ça. Peux-tu m'arranger quelque chose pour cette semaine?",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                }
            },
        ]
    },
    {
        "nom": "Questions répétées sous différentes formes",
        "conversation": [
            {
                "msg": "C'est quoi les frais que je dois payer quand j'achète une auto en concession?",
                "checks": {
                    "mentionne_taxes": lambda r, h: any(w in r.lower() for w in ["tps", "tvq", "taxes"]),
                    "mentionne_frais_illegaux": lambda r, h: any(w in r.lower() for w in ["illégal", "opc", "lpc", "interdit"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Donc si je comprends bien, à part les taxes, je devrais rien payer d'autre?",
                "checks": {
                    "confirme_oui": lambda r, h: any(w in r.lower() for w in ["oui", "exact", "correctement", "c'est ça", "effectivement"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Pis les frais de livraison, c'est légal ça?",
                "checks": {
                    "repond_livraison": lambda r, h: any(w in r.lower() for w in ["illégal", "inclus", "prix affiché", "opc"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Et les frais de mise en route?",
                "checks": {
                    "coherent_avec_avant": lambda r, h: any(w in r.lower() for w in ["illégal", "inclus", "même chose", "pareil", "opc"]),
                    "pas_de_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Ok, as-tu des RAV4 ou des CR-V dans tes véhicules?",
                "checks": {
                    "retourne_fiches": lambda r, h: h,
                    "rav4_ou_crv": lambda r, h: any(w in r.lower() for w in ["rav4", "cr-v", "toyota", "honda"]),
                }
            },
            {
                "msg": "Le premier, c'est un RAV4 ou un CR-V?",
                "checks": {
                    "identifie_modele": lambda r, h: any(w in r.lower() for w in ["rav4", "cr-v", "toyota", "honda", "proposition 1"]),
                    "pas_nouvelles_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Il est chez quel concessionnaire?",
                "checks": {
                    "mentionne_concessionnaire": lambda r, h: any(w in r.lower() for w in ["kia", "honda", "ford", "québec", "ste-foy", "donnacona", "val-bélair"]),
                    "pas_nouvelles_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Je veux y aller le voir",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                }
            },
        ]
    },
    {
        "nom": "Mélange info + achat dans même message",
        "conversation": [
            {
                "msg": "C'est quoi un Kia Seltos et as-tu ça en inventaire?",
                "checks": {
                    "explique_et_montre": lambda r, h: h and any(w in r.lower() for w in ["seltos", "kia", "compact"]),
                }
            },
            {
                "msg": "C'est fiable? Pis c'est quoi le prix avec taxes pour le deuxième?",
                "checks": {
                    "repond_fiabilite": lambda r, h: any(w in r.lower() for w in ["fiable", "fiabilité", "reliable", "bon"]),
                    "calcule_taxes": lambda r, h: any(w in r.lower() for w in ["tps", "tvq", "total", "$"]),
                    "pas_nouvelles_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Le vendeur dit que c'est 500$ de frais de préparation en plus. Normal? Pis le troisième Seltos, il a combien de km?",
                "checks": {
                    "denonce_frais": lambda r, h: any(w in r.lower() for w in ["illégal", "opc", "lpc", "interdit"]),
                    "mentionne_km": lambda r, h: any(w in r.lower() for w in ["km", "kilomètre", "kilométrage"]),
                    "pas_nouvelles_fiches": lambda r, h: not h,
                }
            },
            {
                "msg": "Ok je prends le premier. Booking samedi?",
                "checks": {
                    "rdv_declenche": lambda r, h: h,
                    "bon_vehicule": lambda r, h: any(w in r.lower() for w in ["seltos", "kia", "formulaire"]),
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
    for attempt in range(3):
        try:
            r = requests.post(
                f"{BASE_URL}/agent/chat",
                json={"message": message,
                      "session_id": session_id},
                headers={"Authorization":
                         f"Bearer {token}"},
                timeout=90)
            if r.status_code == 200 and r.text:
                data = r.json()
                return (
                    data.get("response", ""),
                    bool(data.get("html_cards","")))
            import time
            time.sleep(3)
        except Exception:
            import time
            time.sleep(3)
    return ("ERREUR", False)

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
