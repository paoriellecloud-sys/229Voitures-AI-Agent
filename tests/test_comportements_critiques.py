import uuid
import requests
import inspect
import re

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_critiques"
TEST_PASS = "testpass_229"

SCENARIOS = [
    {
        "nom": "B1 — Pas de fiches sans budget",
        "description": "L'agent doit clarifier avant de montrer des fiches",
        "conversation": [
            {
                "msg": "Je cherche un VUS pour ma famille",
                "checks": {
                    "demande_budget_STRICT":
                        lambda r, h: not h and any(
                            w in r.lower() for w in
                            ["budget", "combien",
                             "mensuel", "comptant"]),
                }
            },
            {
                "msg": "400$/mois",
                "checks": {
                    "comprend_budget_STRICT":
                        lambda r, h: any(
                            w in r.lower() for w in
                            ["22", "400", "mois",
                             "budget"]),
                }
            },
            {
                "msg": "Montre moi des VUS",
                "checks": {
                    "retourne_vus_STRICT":
                        lambda r, h: h and any(
                            w in r.lower() for w in
                            ["rogue", "kona", "escape",
                             "tucson", "rav4", "cr-v",
                             "seltos", "sportage"]),
                    "pas_de_mustang":
                        lambda r, h: "mustang" not in
                            h.lower(),
                }
            },
        ]
    },
    {
        "nom": "B2 — Alternatives pertinentes",
        "description": "Si pas de Sportage → alternatives VUS, pas Mustang",
        "conversation": [
            {
                "msg": "As-tu des Kia Sportage sous 20 000$?",
                "checks": {
                    "alternatives_vus_STRICT":
                        lambda r, h:
                            "mustang" not in h.lower() and
                            "ferrari" not in h.lower() and
                            (not h or any(w in h.lower()
                             for w in ["rogue", "kona",
                             "escape", "tucson", "cr-v",
                             "rav4", "seltos"])),
                }
            },
        ]
    },
    {
        "nom": "B3 — Budget persistant",
        "description": "Le budget doit rester en mémoire toute la conversation",
        "conversation": [
            {
                "msg": "Mon budget c'est 350$/mois tout inclus",
                "checks": {
                    "confirme_budget":
                        lambda r, h: any(
                            w in r.lower() for w in
                            ["350", "19", "20", "budget"]),
                }
            },
            {
                "msg": "Montre moi des Honda CR-V",
                "checks": {
                    "respecte_budget_STRICT":
                        lambda r, h: not any(
                            p > 20000
                            for p in [
                                int(m.replace(',','').replace(' ',''))
                                for m in re.findall(
                                    r'\b(\d{2})\s*(\d{3})\b',
                                    h)
                                if m
                            ]
                        ) if h else True,
                }
            },
            {
                "msg": "As-tu autre chose?",
                "checks": {
                    "budget_toujours_respecte":
                        lambda r, h: any(
                            w in r.lower() for w in
                            ["350", "budget", "19",
                             "20", "alerte"]),
                }
            },
        ]
    },
    {
        "nom": "B4 — RDV bon véhicule",
        "description": "RDV proposition 2 → bon concessionnaire",
        "conversation": [
            {
                "msg": "Montre moi des Kia Sorento",
                "checks": {
                    "retourne_sorento":
                        lambda r, h: h and
                            "sorento" in r.lower(),
                }
            },
            {
                "msg": "Je veux un RDV pour le deuxième",
                "checks": {
                    "rdv_proposition_2_STRICT":
                        lambda r, h: h and
                            "sorento" in h.lower() and
                            "proposition 1" not in
                            h.lower(),
                }
            },
        ]
    },
    {
        "nom": "B5 — Zéro hallucination",
        "description": "Pas de données inventées sur modèles inexistants",
        "conversation": [
            {
                "msg": "Je cherche une Subaru Legacy 2022",
                "checks": {
                    "pas_de_legacy_invente_STRICT":
                        lambda r, h:
                            "legacy" not in h.lower(),
                }
            },
            {
                "msg": "Je cherche une Ferrari 488",
                "checks": {
                    "pas_de_ferrari_STRICT":
                        lambda r, h: not h or
                            "ferrari" not in h.lower(),
                }
            },
        ]
    },
    {
        "nom": "B6 — Frais illégaux systématique",
        "description": "OPC/LPC mentionné pour tout type de frais",
        "conversation": [
            {
                "msg": "Le vendeur veut 799$ de frais de préparation",
                "checks": {
                    "denonce_STRICT":
                        lambda r, h: all(
                            w in r.lower() for w in
                            ["illégal"]) and not h,
                }
            },
            {
                "msg": "Et 499$ de frais de livraison?",
                "checks": {
                    "coherent_STRICT":
                        lambda r, h:
                            "illégal" in r.lower()
                            and not h,
                }
            },
            {
                "msg": "Pis 299$ de frais de dossier?",
                "checks": {
                    "toujours_coherent_STRICT":
                        lambda r, h:
                            "illégal" in r.lower()
                            and not h,
                }
            },
        ]
    },
    {
        "nom": "B7 — Mémoire et cohérence longue",
        "description": "Se souvenir du sujet après changements de sujet",
        "conversation": [
            {
                "msg": "Montre moi des Toyota RAV4",
                "checks": {
                    "retourne_rav4":
                        lambda r, h: h and
                            "rav4" in r.lower(),
                }
            },
            {
                "msg": "C'est quoi la différence entre AWD et 4WD?",
                "checks": {
                    "repond_info_STRICT":
                        lambda r, h: not h and any(
                            w in r.lower() for w in
                            ["awd", "4wd", "intégrale"]),
                }
            },
            {
                "msg": "Les Tesla sont bonnes en hiver?",
                "checks": {
                    "repond_tesla_STRICT":
                        lambda r, h: not h and any(
                            w in r.lower() for w in
                            ["tesla", "hiver", "batterie"]),
                }
            },
            {
                "msg": "Je reviens au RAV4. Le premier m'intéresse",
                "checks": {
                    "souvient_rav4_STRICT":
                        lambda r, h: any(
                            w in r.lower() for w in
                            ["rav4", "toyota", "premier",
                             "27", "23", "proposition"]),
                }
            },
            {
                "msg": "RDV samedi pour ce RAV4",
                "checks": {
                    "rdv_rav4_STRICT":
                        lambda r, h: h and
                            "rav4" in h.lower(),
                }
            },
        ]
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
                    bool(data.get("html_cards","")),
                    data.get("html_cards",""))
            import time
            time.sleep(3)
        except Exception:
            import time
            time.sleep(3)
    return ("ERREUR", False, "")

def run_check(fn, response, has_cards, html):
    try:
        sig = inspect.signature(fn)
        params = len(sig.parameters)
        if params == 3:
            return fn(response, has_cards, html)
        elif params == 2:
            return fn(response, html)
        return fn(response)
    except:
        return False

def main():
    token = get_token()
    grand_total = 0
    grand_passed = 0
    grand_failed_behaviors = []

    print("=== TEST COMPORTEMENTS CRITIQUES ===")
    print("RÈGLE : Si FAIL → corriger l'agent, jamais le test\n")

    for scenario in SCENARIOS:
        session_id = str(uuid.uuid4())
        total = 0
        passed = 0
        scenario_failed = False

        print(f"\n{'='*60}")
        print(f"COMPORTEMENT : {scenario['nom']}")
        print(f"              {scenario['description']}")
        print(f"{'='*60}")

        for i, turn in enumerate(
                scenario["conversation"], 1):
            print(f"\n--- Tour {i} ---")
            print(f"[CLIENT] {turn['msg']}\n")

            response, has_cards, html = chat(
                token, session_id, turn["msg"])

            print(f"[AGENT]  {response[:250]}"
                  f"{'...' if len(response)>250 else ''}")
            if has_cards:
                print("[FICHES] Présentes")

            print("\n[CHECKS]")
            for name, fn in turn["checks"].items():
                result = run_check(
                    fn, response, has_cards, html)
                total += 1
                grand_total += 1
                if result:
                    passed += 1
                    grand_passed += 1
                    print(f"  [OK]   {name}")
                else:
                    scenario_failed = True
                    print(f"  [FAIL] {name}")
                    print(f"         → BUG À CORRIGER "
                          f"DANS L'AGENT")

        score = round(passed/total*10, 1)
        status = "✅" if passed == total else "❌"
        print(f"\n{status} SCORE : {passed}/{total} "
              f"— {score}/10")

        if scenario_failed:
            grand_failed_behaviors.append(
                scenario['nom'])

    print(f"\n{'='*60}")
    score_final = round(grand_passed/grand_total*10, 1)
    print(f"SCORE GLOBAL : {grand_passed}/{grand_total}"
          f" — {score_final}/10")

    if grand_failed_behaviors:
        print(f"\nCOMPORTEMENTS À CORRIGER :")
        for b in grand_failed_behaviors:
            print(f"  ❌ {b}")
    else:
        print("\n✅ Tous les comportements critiques "
              "sont garantis")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
