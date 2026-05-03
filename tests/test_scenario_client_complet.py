"""
Scenario client complet — Marc, 42 ans, famille, 15 tours
Usage : python tests/test_scenario_client_complet.py
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


def parse_prices(html: str) -> list:
    prices = []
    for m in re.findall(r'\b(\d[\d\s,]*)\$', html):
        try:
            val = int(m.strip().replace(' ', '').replace(',', '').replace('\xa0', ''))
            if 5000 < val < 100000:
                prices.append(val)
        except ValueError:
            pass
    return prices


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
    print("SCENARIO : Marc — client complet 15 tours")
    print(f"{'='*60}")

    checks = []

    # ── T1 : VUS famille budget 500$/mois tout inclus ────────────
    # 500$/mois -> total ~24 800$ avant taxes (72 mois, 7.99%)
    r1 = chat(token,
        "Salut, je magasine un VUS pour remplacer mon Elantra 2019. "
        "Budget max 500$/mois tout inclus. J'aimerais quelque chose "
        "de fiable pour ma famille, idealement hybride mais pas "
        "obligatoire.",
        sid)
    resp1 = r1.get("response", "")
    html1 = r1.get("html_cards", "") or r1.get("_html_cards", "")
    lower1 = resp1.lower()

    vT1_1 = bool(html1 and len(html1.strip()) > 50)
    prices1 = parse_prices(html1)
    vT1_2 = all(p <= 31000 for p in prices1) if prices1 else True

    checks.append(("T1 — VUS retournes dans le budget (html_cards)", vT1_1,
        f"html_cards vide ({len(html1)} chars)"))
    checks.append(("T1 — Prix affiches <= 31 000$ avant taxes (tolerance 1k)", vT1_2,
        f"Prix hors budget: {[p for p in prices1 if p > 31000]}"))

    # ── T2 : hybride vs hybride rechargeable ─────────────────────
    r2 = chat(token,
        "Le premier m'interesse. C'est quoi la difference entre "
        "hybride et hybride rechargeable?",
        sid)
    resp2 = r2.get("response", "")
    html2 = r2.get("html_cards", "") or r2.get("_html_cards", "")
    lower2 = resp2.lower()

    phev_signals = ["rechargeable", "phev", "branchable", "prise", "batterie",
                    "electrique", "autonomie", "hybride"]
    vT2_1 = sum(1 for s in phev_signals if s in lower2) >= 2
    vT2_2 = not bool(html2 and len(html2.strip()) > 50)

    checks.append(("T2 — Explique hybride vs PHEV", vT2_1,
        f"Explication insuffisante — signaux: {[s for s in phev_signals if s in lower2]}"))
    checks.append(("T2 — Pas de nouvelles fiches (question CHAT)", vT2_2,
        f"html_cards inattendu ({len(html2)} chars)"))

    # ── T3 : reprise Elantra 2019 ────────────────────────────────
    r3 = chat(token,
        "Ok. Pis pour mon Elantra 2019 que je veux echanger, est-ce que "
        "le concessionnaire peut me faire une reprise et appliquer ca "
        "sur le prix?",
        sid)
    resp3 = r3.get("response", "")
    lower3 = resp3.lower()

    reprise_signals = ["reprise", "echange", "trade", "valeur", "revente",
                       "mise de fonds", "concessionnaire"]
    vT3_1 = any(s in lower3 for s in reprise_signals)

    checks.append(("T3 — Mentionne reprise/echange possible", vT3_1,
        f"Aucun signal reprise/echange: {resp3[:100]}"))

    # ── T4 : valeur Elantra 87 000 km ───────────────────────────
    r4 = chat(token,
        "Il a 87 000 km et il est en bon etat. Vaut-il quelque chose?",
        sid)
    resp4 = r4.get("response", "")
    lower4 = resp4.lower()

    valeur_signals = ["valeur", "prix", "estimation", "dollar", "marche",
                      "carfax", "condition", "kilometrage", "km", "elantra",
                      "entre", "environ"]
    vT4_1 = any(s in lower4 for s in valeur_signals)
    vT4_2 = len(resp4) > 80

    checks.append(("T4 — Donne estimation ou conseille comment evaluer", vT4_1,
        f"Aucun signal valeur/estimation: {resp4[:100]}"))
    checks.append(("T4 — Reponse substantielle (>80 chars)", vT4_2,
        f"Reponse trop courte ({len(resp4)} chars)"))

    # ── T5 : impact mise de fonds 8 000$ ────────────────────────
    r5 = chat(token,
        "Si je mets 8 000$ de mise de fonds, ca change quoi pour "
        "mes mensualites?",
        sid)
    resp5 = r5.get("response", "")
    lower5 = resp5.lower()

    finance_signals = ["mensualite", "mois", "paiement", "reduit", "moins",
                       "8 000", "8000", "mise de fonds", "financement",
                       "montant", "diminue", "calcul"]
    vT5_1 = sum(1 for s in finance_signals if s in lower5) >= 2

    checks.append(("T5 — Explique impact mise de fonds sur mensualites", vT5_1,
        f"Explication insuffisante — signaux: {[s for s in finance_signals if s in lower5]}"))

    # ── T6 : assurance vie forcee avec financement ───────────────
    r6 = chat(token,
        "Le vendeur m'a dit que si je finance chez eux a 6.99%, je "
        "dois prendre leur assurance vie a 89$/mois. "
        "C'est-tu obligatoire?",
        sid)
    resp6 = r6.get("response", "")
    lower6 = resp6.lower()

    lpc_signals6 = ["illegal", "illegaux", "interdit", "lpc", "opc",
                    "protection du consommateur", "abusif", "abusive",
                    "pas oblige", "facultatif", "optionnel", "pas le droit",
                    "contraire", "conditionnel", "tactique", "pas normal",
                    "non", "n'est pas obligatoire"]
    vT6_1 = any(s in lower6 for s in lpc_signals6)

    checks.append(("T6 — Denonce assurance forcee = illegal LPC", vT6_1,
        f"Aucun signal illegal/LPC: {resp6[:120]}"))

    # ── T7 : frais de dossier 1 200$ ────────────────────────────
    r7 = chat(token,
        "Pis les frais de dossier de 1 200$ qu'ils veulent me charger, "
        "c'est normal ca?",
        sid)
    resp7 = r7.get("response", "")
    lower7 = resp7.lower()

    lpc_signals7 = ["illegal", "illegaux", "interdit", "lpc", "opc",
                    "protection du consommateur", "pas le droit", "contraire",
                    "abusif", "pas normal", "non", "frais de dossier",
                    "frais cachés", "frais caches", "interdit d'ajouter"]
    vT7_1 = any(s in lower7 for s in lpc_signals7)

    checks.append(("T7 — Denonce frais dossier = illegal OPC", vT7_1,
        f"Aucun signal illegal/OPC: {resp7[:120]}"))

    # ── T8 : Kia vs Toyota fiabilite ────────────────────────────
    r8 = chat(token,
        "Mon voisin dit que les Kia sont moins fiables que les Toyota. "
        "Qu'est-ce que tu en penses?",
        sid)
    resp8 = r8.get("response", "")
    lower8 = resp8.lower()

    nuance_signals8 = ["kia", "toyota", "fiab", "modele", "depend",
                       "historique", "entretien", "garantie", "carfax",
                       "ameliore", "progres", "stereotype", "generalisation"]
    vT8_1 = "kia" in lower8 and "toyota" in lower8
    vT8_2 = any(s in lower8 for s in ["depend", "entretien", "historique",
                                        "modele", "ameliore", "progres",
                                        "garantie", "stereotype"])

    checks.append(("T8 — Mentionne Kia et Toyota", vT8_1,
        f"Un des deux absents: {resp8[:100]}"))
    checks.append(("T8 — Reponse nuancee (pas de denigrement)", vT8_2,
        f"Aucune nuance detectee: {resp8[:100]}"))

    # ── T9 : identifie le modele Prop 1 (memoire session) ────────
    r9 = chat(token,
        "Ok mais le premier vehicule que tu m'as montre, "
        "c'est un Kia ou un Toyota?",
        sid)
    resp9 = r9.get("response", "")
    lower9 = resp9.lower()

    brand_signals9 = ["kia", "toyota", "hyundai", "ford", "honda",
                      "nissan", "mazda", "chevrolet", "jeep", "subaru"]
    vT9_1 = any(s in lower9 for s in brand_signals9)

    checks.append(("T9 — Identifie la marque du 1er vehicule (memoire)", vT9_1,
        f"Aucune marque identifiee: {resp9[:100]}"))

    # ── T10 : garantie manufacturier ────────────────────────────
    r10 = chat(token, "Il a encore sa garantie du manufacturier?", sid)
    resp10 = r10.get("response", "")
    lower10 = resp10.lower()

    garantie_signals = ["garantie", "manufacturier", "ans", "km",
                        "kilometr", "couverture", "expir", "valide",
                        "groupe motopropulseur", "powertrain"]
    vT10_1 = any(s in lower10 for s in garantie_signals)

    checks.append(("T10 — Repond sur la garantie du modele", vT10_1,
        f"Aucun signal garantie: {resp10[:100]}"))

    # ── T11 : problemes mecaniques connus ───────────────────────
    r11 = chat(token,
        "C'est quoi les problemes mecaniques connus sur ce modele?",
        sid)
    resp11 = r11.get("response", "")
    lower11 = resp11.lower()

    mecanique_signals = ["moteur", "transmission", "inspection", "kilometrage",
                         "batterie", "hybride", "recent", "nouveau modele",
                         "peu de donnees", "pas encore", "historique", "entretien"]
    vT11_1 = any(s in lower11 for s in mecanique_signals)
    vT11_2 = len(resp11) > 80

    checks.append(("T11 — Mentionne points de vigilance mecaniques", vT11_1,
        f"Aucun terme mecanique: {resp11[:100]}"))
    checks.append(("T11 — Reponse substantielle (>80 chars)", vT11_2,
        f"Reponse trop courte ({len(resp11)} chars)"))

    # ── T12 : recours si bris dans 6 mois ───────────────────────
    r12 = chat(token,
        "Si je l'achete pis qu'il brise dans 6 mois, j'ai quels recours?",
        sid)
    resp12 = r12.get("response", "")
    lower12 = resp12.lower()

    recours_signals = ["lpc", "opc", "garantie", "legale", "legal",
                       "protection du consommateur", "recours", "vice cache",
                       "remboursement", "reparation", "concessionnaire",
                       "tribunal", "plainte"]
    vT12_1 = any(s in lower12 for s in recours_signals)

    checks.append(("T12 — Mentionne recours LPC/garantie legale", vT12_1,
        f"Aucun signal recours/LPC: {resp12[:100]}"))

    # ── T13 : conseils negociation ───────────────────────────────
    r13 = chat(token,
        "Ok je pense que je vais y aller. C'est quoi la meilleure "
        "facon de negocier le prix?",
        sid)
    resp13 = r13.get("response", "")
    lower13 = resp13.lower()

    nego_signals = ["prix", "negoci", "offre", "marche", "comparable",
                    "carfax", "inspection", "comptant", "financement",
                    "preparer", "recherche", "valeur", "concession"]
    vT13_1 = sum(1 for s in nego_signals if s in lower13) >= 3
    vT13_2 = len(resp13) > 100

    checks.append(("T13 — Conseils negociation concrets (>= 3 signaux)", vT13_1,
        f"Conseils insuffisants — signaux: {[s for s in nego_signals if s in lower13]}"))
    checks.append(("T13 — Reponse substantielle (>100 chars)", vT13_2,
        f"Reponse trop courte ({len(resp13)} chars)"))

    # ── T14 : RDV samedi apres-midi ──────────────────────────────
    r14 = chat(token,
        "Parfait. Je veux prendre rendez-vous pour le voir samedi "
        "apres-midi.",
        sid)
    resp14 = r14.get("response", "")
    html14  = r14.get("html_cards", "") or r14.get("_html_cards", "")

    vT14_1 = bool(html14 and len(html14.strip()) > 50)

    checks.append(("T14 — Formulaire RDV affiche", vT14_1,
        f"html_cards vide apres demande RDV ({len(html14)} chars)"))

    # ── T15 : 5 choses a verifier sur place ─────────────────────
    r15 = chat(token,
        "Avant d'y aller, c'est quoi les 5 choses les plus importantes "
        "a verifier sur place?",
        sid)
    resp15 = r15.get("response", "")
    lower15 = resp15.lower()

    verif_signals = ["carfax", "inspection", "essai", "test drive",
                     "kilometrage", "km", "accident", "rouille", "garantie",
                     "documents", "titre", "historique", "financement",
                     "freins", "pneus", "huile", "bruit", "moteur"]
    found_signals = [s for s in verif_signals if s in lower15]
    vT15_1 = len(found_signals) >= 5
    vT15_2 = len(resp15) > 150

    checks.append(("T15 — Liste >= 5 points de verification", vT15_1,
        f"Seulement {len(found_signals)} signaux detectes: {found_signals}"))
    checks.append(("T15 — Reponse detaillee (>150 chars)", vT15_2,
        f"Reponse trop courte ({len(resp15)} chars)"))

    # ── Affichage detail ─────────────────────────────────────────
    all_ok = all(c[1] for c in checks)
    run_test("SCENARIO Marc — client complet 15 tours", all_ok, resp15,
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
