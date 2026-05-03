"""
Scenario premier acheteur — 8 tours
Usage : python tests/test_scenario_premier_acheteur.py
"""

import uuid
import re
import requests

BASE_URL  = "http://148.116.73.158:8000"
CHAT_URL  = f"{BASE_URL}/agent/chat"
TEST_USER = "test_agent_auto"
TEST_PASS = "testpass_229"


def get_token() -> str:
    requests.post(f"{BASE_URL}/register", params={"username": TEST_USER, "password": TEST_PASS})
    r = requests.post(
        f"{BASE_URL}/login",
        data={"username": TEST_USER, "password": TEST_PASS},
    )
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Impossible d'obtenir un token : {data}")
    return token


def chat(token: str, message: str, session_id: str) -> dict:
    r = requests.post(
        CHAT_URL,
        json={"message": message, "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


results = []

def run_test(name: str, passed: bool, response: str, detail: str = ""):
    status = "[PASS]" if passed else "[FAIL]"
    results.append(passed)
    print(f"\n{'-'*60}")
    print(f"{status}  {name}")
    rep = response[:300] + ("..." if len(response) > 300 else "")
    print(f"Reponse : {rep}")
    if not passed:
        print(f"Probleme : {detail}")


def main():
    print("[*] Connexion...")
    token = get_token()
    print("[OK] Token obtenu\n")

    sid = str(uuid.uuid4())
    print(f"{'='*60}")
    print("SCENARIO : Premier acheteur — 8 tours")
    print(f"{'='*60}")

    # ── T1 : budget mensuel hybride ──────────────────────────────
    r1 = chat(token,
        "Salut! Je cherche un premier char. Je veux quelque chose "
        "d'economique, idealement hybride. Budget 350$/mois taxes "
        "incluses. C'est quoi mes options?",
        sid)
    resp1 = r1.get("response", "")
    html1 = r1.get("html_cards", "") or r1.get("_html_cards", "")

    vT1_1 = bool(html1 and len(html1.strip()) > 50)
    hybrid_signals = ["hybride", "hybrid", "toyota", "corolla", "rav4", "eco"]
    vT1_2 = any(s in html1.lower() or s in resp1.lower() for s in hybrid_signals)

    checks = []
    checks.append(("T1 — Vehicules hybrides retournes (html_cards)", vT1_1,
        f"html_cards vide ({len(html1)} chars)"))
    checks.append(("T1 — Signal hybride dans les resultats", vT1_2,
        "Aucun vehicule hybride detecte dans la reponse"))

    # ── T2 : fiabilite du 2e vehicule ───────────────────────────
    r2 = chat(token, "Le deuxieme m'interesse. C'est-tu fiable comme modele?", sid)
    resp2 = r2.get("response", "")
    html2 = r2.get("html_cards", "") or r2.get("_html_cards", "")
    lower2 = resp2.lower()

    reliability_signals = ["fiab", "moteur", "transmission", "probleme", "rappel",
                           "historique", "km", "kilometr", "toyota", "honda", "hyundai"]
    vT2_1 = any(s in lower2 for s in reliability_signals)
    vT2_2 = not bool(html2 and len(html2.strip()) > 50)  # CHAT = pas de nouvelles fiches

    checks.append(("T2 — Parle de fiabilite du modele", vT2_1,
        f"Aucun terme fiabilite/mecanique: {resp2[:100]}"))
    checks.append(("T2 — Pas de nouvelles fiches (question CHAT)", vT2_2,
        f"html_cards inattendu ({len(html2)} chars)"))

    # ── T3 : km du vehicule ──────────────────────────────────────
    r3 = chat(token, "Il a combien de km?", sid)
    resp3 = r3.get("response", "")
    lower3 = resp3.lower()

    has_number = bool(re.search(r'\d[\d\s]*', resp3))
    vT3_1 = ("km" in lower3 or "kilomet" in lower3) and has_number

    checks.append(("T3 — Repond avec les km du vehicule", vT3_1,
        f"Pas de km numerique dans la reponse: {resp3[:100]}"))

    # ── T4 : mythe des 80 000 km ─────────────────────────────────
    r4 = chat(token,
        "C'est beaucoup ca. Mon chum dit que passe 80 000 km un char "
        "vaut plus rien. Il a raison?",
        sid)
    resp4 = r4.get("response", "")
    lower4 = resp4.lower()

    nuance_signals = ["entretien", "historique", "carfax", "condition", "inspection",
                      "depend", "pas necessairement", "tout depend", "pas toujours",
                      "bien entretenu", "mythe"]
    vT4_1 = any(s in lower4 for s in nuance_signals)
    vT4_2 = len(resp4) > 80

    checks.append(("T4 — Nuance le mythe des 80k km", vT4_1,
        f"Aucun signal nuance/entretien: {resp4[:100]}"))
    checks.append(("T4 — Reponse substantielle (>80 chars)", vT4_2,
        f"Reponse trop courte ({len(resp4)} chars)"))

    # ── T5 : bundling protection forcee avec financement ─────────
    r5 = chat(token,
        "Le vendeur m'a dit qu'avec le financement a 5.99% je dois "
        "prendre le forfait protection complete a 2 800$. C'est normal?",
        sid)
    resp5 = r5.get("response", "")
    lower5 = resp5.lower()

    illegal_signals = ["illegal", "illegaux", "interdit", "lpc", "opc",
                       "protection du consommateur", "abusif", "pas oblige",
                       "facultatif", "optionnel", "pas le droit", "contraire"]
    validate_signals = ["c'est normal", "c'est standard", "c'est courant",
                        "vous devez", "obligatoire"]
    vT5_1 = any(s in lower5 for s in illegal_signals)
    vT5_2 = not any(s in lower5 for s in validate_signals)

    checks.append(("T5 — Denonce le bundling force (LPC)", vT5_1,
        f"Aucun signal illegal/LPC/OPC: {resp5[:120]}"))
    checks.append(("T5 — Ne valide pas la pratique abusive", vT5_2,
        f"Agent a valide le bundling force: {[s for s in validate_signals if s in lower5]}"))

    # ── T6 : particulier vs concessionnaire ──────────────────────
    r6 = chat(token,
        "Pis si j'achete le meme char d'un particulier sur Marketplace "
        "a 2 000$ moins cher?",
        sid)
    resp6 = r6.get("response", "")
    lower6 = resp6.lower()

    dealer_signals = ["garantie", "opc", "carfax", "inspection", "certifie",
                      "protection", "vice cache", "concessionnaire", "229"]
    vT6_1 = any(s in lower6 for s in dealer_signals)
    vT6_2 = len(resp6) > 80

    checks.append(("T6 — Mentionne avantages concessionnaire", vT6_1,
        f"Aucun signal garantie/OPC/Carfax: {resp6[:100]}"))
    checks.append(("T6 — Reponse substantielle (>80 chars)", vT6_2,
        f"Reponse trop courte ({len(resp6)} chars)"))

    # ── T7 : RDV samedi matin pour le 2e ─────────────────────────
    r7 = chat(token,
        "Ok t'as me convaincu. Je veux voir le deuxieme ce samedi matin.",
        sid)
    resp7 = r7.get("response", "")
    html7 = r7.get("html_cards", "") or r7.get("_html_cards", "")

    vT7_1 = bool(html7 and len(html7.strip()) > 50)

    checks.append(("T7 — Formulaire RDV affiche", vT7_1,
        f"html_cards vide apres demande RDV ({len(html7)} chars)"))

    # ── T8 : questions a poser chez le conco ─────────────────────
    r8 = chat(token,
        "C'est quoi les questions que je devrais poser quand je vais "
        "chez le concessionnaire?",
        sid)
    resp8 = r8.get("response", "")
    lower8 = resp8.lower()

    advice_signals = ["carfax", "inspection", "garantie", "historique",
                      "essai", "financement", "kilomet", "accident"]
    vT8_1 = len(resp8) > 100
    vT8_2 = sum(1 for s in advice_signals if s in lower8) >= 3

    checks.append(("T8 — Reponse substantielle (>100 chars)", vT8_1,
        f"Reponse trop courte ({len(resp8)} chars)"))
    checks.append(("T8 — Couvre au moins 3 sujets cles (carfax/inspection/garantie...)", vT8_2,
        f"Sujets detectes: {[s for s in advice_signals if s in lower8]}"))

    # ── Affichage detail ─────────────────────────────────────────
    all_ok = all(c[1] for c in checks)
    run_test("SCENARIO Premier acheteur", all_ok, resp8,
             " | ".join(c[2] for c in checks if not c[1]))
    print("\n  Detail :")
    for name, ok, detail in checks:
        tag = "[PASS]" if ok else "[FAIL]"
        line = f"    {tag} {name}"
        if not ok:
            line += f" -> {detail}"
        print(line)

    total  = len(results)
    passed = sum(results)
    print(f"\n{'='*60}")
    print(f"RESULTAT FINAL : {passed}/{total} tests passes")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
