import uuid
import requests
import inspect

BASE_URL = "http://148.116.73.158:8000"
TEST_USER = "test_extreme"
TEST_PASS = "testpass_229"

CONVERSATION = [
    # BLOC 1 — Questions encyclopédistes pures
    {
        "msg": "C'est quoi la différence entre un hybride et un électrique?",
        "checks": {
            "chat_pur": lambda r, h: not h,
            "contenu": lambda r, h: any(w in r.lower() for w in ["batterie", "essence", "électrique", "hybride", "moteur"]),
        }
    },
    {
        "msg": "Volkswagen a été fondée quand et par qui?",
        "checks": {
            "chat_pur": lambda r, h: not h,
            "contenu": lambda r, h: any(w in r.lower() for w in ["1937", "allemagne", "fondée", "créée", "volkswagen"]),
        }
    },
    {
        "msg": "C'est quoi un véhicule sous-marin?",
        "checks": {
            "chat_pur": lambda r, h: not h,
            "contenu": lambda r, h: any(w in r.lower() for w in ["valeur", "prêt", "dette", "inondé", "eau", "dommage"]),
        }
    },
    # BLOC 2 — Recherche avec budget
    {
        "msg": "Ok asteure montre-moi des RAV4 sous 30 000$",
        "checks": {
            "retourne_fiches": lambda r, h: h,
            "prix_ok": lambda r, h: any(w in r for w in ["$", "000"]),
        }
    },
    # BLOC 3 — FOLLOWUP sur les fiches
    {
        "msg": "C'est quoi la différence entre le premier et le deuxième?",
        "checks": {
            "pas_nouvelles_fiches": lambda r, h: not h,
            "compare_vehicules": lambda r, h: any(w in r.lower() for w in ["proposition", "premier", "deuxième", "rav4", "km", "prix"]),
        }
    },
    {
        "msg": "Le premier a-t-il encore sa garantie?",
        "checks": {
            "pas_nouvelles_fiches": lambda r, h: not h,
            "parle_garantie": lambda r, h: any(w in r.lower() for w in ["garantie", "manufacturier", "km", "ans", "kilométrage"]),
        }
    },
    # BLOC 4 — Changement de sujet brutal
    {
        "msg": "Parle-moi des Acura en général",
        "checks": {
            "chat_pur": lambda r, h: not h,
            "parle_acura": lambda r, h: any(w in r.lower() for w in ["acura", "honda", "luxe", "fiable", "mdx", "rdx"]),
        }
    },
    {
        "msg": "Les Tesla sont-elles bonnes pour l'hiver au Québec?",
        "checks": {
            "chat_pur": lambda r, h: not h,
            "contexte_qc": lambda r, h: any(w in r.lower() for w in ["hiver", "québec", "autonomie", "froid", "batterie", "recharge"]),
        }
    },
    # BLOC 5 — Retour aux fiches précédentes
    {
        "msg": "Ok je reviens au RAV4. Le deuxième m'intéresse encore",
        "checks": {
            "pas_nouvelles_fiches": lambda r, h: not h,
            "parle_rav4": lambda r, h: any(w in r.lower() for w in ["rav4", "proposition", "deuxième", "prix", "km"]),
        }
    },
    # BLOC 6 — Pièges et questions légales
    {
        "msg": "Le vendeur dit que je dois payer 799$ de frais de préparation. Normal?",
        "checks": {
            "denonce_frais": lambda r, h: any(w in r.lower() for w in ["illégal", "opc", "lpc", "interdit", "refuser"]),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    {
        "msg": "Il veut aussi me vendre une assurance vie à 89$/mois avec le financement",
        "checks": {
            "alerte_fi": lambda r, h: any(w in r.lower() for w in ["assurance", "nécessaire", "coûte", "négoci", "personnel", "attention"]),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    # BLOC 7 — Questions techniques précises
    {
        "msg": "C'est quoi la différence entre AWD et 4WD pour l'hiver?",
        "checks": {
            "chat_pur": lambda r, h: not h,
            "explique": lambda r, h: any(w in r.lower() for w in ["awd", "4wd", "intégrale", "hiver", "neige", "permanent"]),
        }
    },
    {
        "msg": "Le RAV4 Prime usagé est-il admissible aux rabais Roulez Vert?",
        "checks": {
            "reponse_correcte": lambda r, h: any(w in r.lower() for w in ["non", "neuf", "usagé", "pas admissible", "occasion"]),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    # BLOC 8 — Mémoire longue distance
    {
        "msg": "Finalement je veux voir le premier RAV4 que tu m'as montré",
        "checks": {
            "souvient_rav4": lambda r, h: any(w in r.lower() for w in ["rav4", "proposition", "premier", "formulaire", "rdv", "concessionnaire"]),
        }
    },
    # BLOC 9 — Nouveau sujet + financement + légal
    {
        "msg": "Non attends, montre-moi plutôt des Kia Sorento",
        "checks": {
            "retourne_fiches": lambda r, h: h,
            "sorento": lambda r, h: any(w in r.lower() for w in ["sorento", "kia"]),
        }
    },
    {
        "msg": "C'est combien par mois si je finance le premier sur 72 mois?",
        "checks": {
            "calcule_mensualites": lambda r, h: any(w in r.lower() for w in ["/mois", "par mois", "mensualit", "72"]),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    {
        "msg": "Le vendeur me dit que le taux de 3.99% est conditionnel à leur forfait protection à 2000$. C'est légal?",
        "checks": {
            "denonce_vente_liee": lambda r, h: any(w in r.lower() for w in ["illégal", "lpc", "vente liée", "conditionnel", "interdit"]),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    # BLOC 10 — Nouveau modèle + alerte mécanique + RDV final
    {
        "msg": "Ok laisse faire le Sorento. As-tu des Honda CR-V 2020 ou 2021?",
        "checks": {
            "retourne_fiches": lambda r, h: h,
            "crv": lambda r, h: any(w in r.lower() for w in ["cr-v", "crv", "honda"]),
        }
    },
    {
        "msg": "Le CR-V 1.5T a pas un problème de dilution d'huile?",
        "checks": {
            "alerte_mecanique": lambda r, h: any(w in r.lower() for w in ["dilution", "huile", "1.5", "turbo", "2017", "2018", "2019"]),
            "pas_de_fiches": lambda r, h: not h,
        }
    },
    {
        "msg": "Ok je veux contacter le concessionnaire pour le premier CR-V",
        "checks": {
            "formulaire_rdv": lambda r, h: h,
            "mention_dealer": lambda r, h: any(w in r.lower() for w in ["concessionnaire", "formulaire", "rdv", "rendez-vous", "contact"]),
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
                return (data.get("response", ""),
                        bool(data.get("html_cards","")))
            else:
                import time
                time.sleep(3)
        except Exception as e:
            import time
            time.sleep(3)
    return ("ERREUR", False)


def main():
    token = get_token()
    session_id = str(uuid.uuid4())

    print("=== TEST EXTREME — 20 TOURS ===\n")

    total_checks = 0
    passed_checks = 0
    failed_turns = []

    for i, turn in enumerate(CONVERSATION, 1):
        print(f"[T{i:02d}] {turn['msg']}")
        response, has_cards = chat(token, session_id, turn["msg"])

        preview = response[:300] + ("..." if len(response) > 300 else "")
        print(f"       → {preview}")
        if has_cards:
            print("       [FICHES présentes]")

        turn_ok = True
        for check_name, check_fn in turn["checks"].items():
            total_checks += 1
            try:
                ok = check_fn(response, has_cards)
            except Exception as e:
                ok = False
                print(f"       [ERREUR check '{check_name}': {e}]")

            if ok:
                passed_checks += 1
                print(f"       ✅ {check_name}")
            else:
                turn_ok = False
                print(f"       ❌ {check_name}")

        if not turn_ok:
            failed_turns.append(i)

        print()

    print("=" * 55)
    print(f"CHECKS  : {passed_checks}/{total_checks}")
    print(f"TOURS OK: {len(CONVERSATION) - len(failed_turns)}/{len(CONVERSATION)}")
    if failed_turns:
        print(f"ÉCHECS  : tours {failed_turns}")
    else:
        print("PARFAIT : aucun échec")


if __name__ == "__main__":
    main()
