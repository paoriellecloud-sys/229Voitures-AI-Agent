"""
Tests rapides — 3 scénarios ciblés
Usage : python tests/test_scenarios_quick.py
"""

import uuid
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
        print(f"Problème : {detail}")


test_scenarios = [
    {"name": "Prix tout inclus",   "prompt": "Cherche une auto à 20 000$ taxes incluses."},
    {"name": "Conformité LPC",     "prompt": "Quels sont les frais cachés en plus du prix affiché ?"},
    {"name": "Mémoire RDV",        "steps": ["Cherche des RAV4",
                                              "Quelles sont les options du 2e ?",
                                              "Je veux le 2e, RDV demain 10h"]},
]


def main():
    print("[*] Connexion...")
    token = get_token()
    print("[OK] Token obtenu\n")

    # ── SCÉNARIO A — Prix tout inclus ────────────────────────────
    # L'utilisateur demande un budget taxes incluses.
    # Le prix avant taxes = 20 000 / 1.14975 ≈ 17 395 $.
    # L'agent doit retourner des véhicules et idéalement informer
    # que les prix affichés sont avant TPS/TVQ.
    sid = str(uuid.uuid4())
    scenario = test_scenarios[0]
    rA = chat(token, scenario["prompt"], sid)
    respA   = rA.get("response", "")
    htmlA   = rA.get("html_cards", "") or rA.get("_html_cards", "")
    lowerA  = respA.lower()

    # V_A1 : l'agent retourne des véhicules (html_cards non vide)
    vA1 = bool(htmlA and len(htmlA.strip()) > 50)

    # V_A2 : l'agent mentionne les taxes ou le contexte budget
    tax_signals = ["taxe", "tps", "tvq", "total", "tout inclus", "avant taxe", "hors taxe"]
    vA2 = any(s in lowerA for s in tax_signals)

    # V_A3 : aucun prix affiché dans html_cards ne dépasse 17 500 $
    #        (sinon le total avec taxes excède 20 000 $)
    import re
    prices_in_html = [int(m.replace(' ', '').replace(' ', '').replace(',', ''))
                      for m in re.findall(r'[\d  ]{4,7}\s*\$', htmlA)
                      if m.strip()]
    prices_in_html = [p for p in prices_in_html if 5000 < p < 100000]
    vA3 = all(p <= 17500 for p in prices_in_html) if prices_in_html else True

    checks_A = [
        ("Retourne des véhicules", vA1,
         f"html_cards vide ({len(htmlA)} chars)"),
        ("Mentionne les taxes ou le contexte budget", vA2,
         f"Aucun signal taxe — réponse: {respA[:120]}"),
        ("Prix affichés ≤ 17 500$ (total ≤ 20 000$ avec taxes)", vA3,
         f"Prix hors budget détectés: {[p for p in prices_in_html if p > 17500]}"),
    ]
    allA = all(c[1] for c in checks_A)
    run_test(f"SCÉNARIO A — {scenario['name']}", allA, respA,
             " | ".join(c[2] for c in checks_A if not c[1]))
    print("\n  Détail :")
    for name, ok, detail in checks_A:
        tag = "[PASS]" if ok else "[FAIL]"
        line = f"    {tag} {name}"
        if not ok:
            line += f" -> {detail}"
        print(line)

    # ── SCÉNARIO B — Conformité LPC ──────────────────────────────
    # L'agent doit dire qu'il n'y a pas de frais légaux en plus
    # du prix affiché (hors TPS/TVQ), et citer la LPC ou l'OPC.
    sid = str(uuid.uuid4())
    scenario = test_scenarios[1]
    rB = chat(token, scenario["prompt"], sid)
    respB  = rB.get("response", "")
    lowerB = respB.lower()

    legal_signals = [
        "illégal", "illégaux", "interdit", "interdits",
        "opc", "lpc", "protection du consommateur",
        "n'a pas le droit", "pas le droit d'ajouter",
        "contraire à la loi", "ne peut pas", "aucun frais",
    ]
    forbidden_signals = [
        "frais de préparation sont normaux",
        "frais sont permis",
        "frais sont légaux",
        "vous devez payer ces frais",
    ]

    vB1 = any(s in lowerB for s in legal_signals)
    vB2 = not any(s in lowerB for s in forbidden_signals)

    checks_B = [
        ("Mentionne le caractère illégal des frais additionnels", vB1,
         f"Aucun signal légal détecté — cherche: {legal_signals}"),
        ("Ne valide pas des frais illégaux", vB2,
         f"Signal interdit: {[s for s in forbidden_signals if s in lowerB]}"),
    ]
    allB = all(c[1] for c in checks_B)
    run_test(f"SCÉNARIO B — {scenario['name']}", allB, respB,
             " | ".join(c[2] for c in checks_B if not c[1]))
    print("\n  Détail :")
    for name, ok, detail in checks_B:
        tag = "[PASS]" if ok else "[FAIL]"
        line = f"    {tag} {name}"
        if not ok:
            line += f" -> {detail}"
        print(line)

    # ── SCÉNARIO C — Mémoire RDV (3 tours) ──────────────────────
    # Tour 1 : cherche des RAV4 → vehicle_shown peuplé
    # Tour 2 : question sur la proposition 2 → agent utilise vehicle_shown[2]
    # Tour 3 : demande RDV pour le 2e → formulaire pour le bon véhicule
    sid = str(uuid.uuid4())
    scenario = test_scenarios[2]
    steps = scenario["steps"]

    rC1 = chat(token, steps[0], sid)
    htmlC1 = rC1.get("html_cards", "") or rC1.get("_html_cards", "")

    rC2 = chat(token, steps[1], sid)
    respC2 = rC2.get("response", "")

    rC3 = chat(token, steps[2], sid)
    respC3  = rC3.get("response", "")
    htmlC3  = rC3.get("html_cards", "") or rC3.get("_html_cards", "")
    lowerC3 = respC3.lower()

    # V_C1 : Tour 1 retourne des RAV4
    vC1 = "rav4" in htmlC1.lower() or "rav4" in rC1.get("response", "").lower()

    # V_C2 : Tour 2 répond sur la proposition 2 (contexte conservé)
    vC2 = "proposition 2" in respC2.lower() or "2e" in respC2.lower() or "deuxième" in respC2.lower()

    # V_C3 : Tour 3 affiche un formulaire RDV (html_cards non vide)
    vC3 = bool(htmlC3 and len(htmlC3.strip()) > 50)

    # V_C4 : Le formulaire RDV concerne un RAV4, pas un autre modèle
    vC4 = "rav4" in htmlC3.lower() or "rav4" in lowerC3

    checks_C = [
        ("Tour 1 — RAV4 retournés en html_cards", vC1,
         "html_cards vide ou sans 'rav4' après la recherche"),
        ("Tour 2 — Répond sur la proposition 2", vC2,
         f"Réponse ne mentionne pas 'proposition 2' ou '2e': {respC2[:120]}"),
        ("Tour 3 — Formulaire RDV affiché", vC3,
         f"html_cards vide après demande RDV ({len(htmlC3)} chars)"),
        ("Tour 3 — RDV pour un RAV4 (bonne mémoire véhicule)", vC4,
         "html_cards/réponse ne contient pas 'rav4' — mauvais véhicule sélectionné"),
    ]
    allC = all(c[1] for c in checks_C)
    run_test(f"SCÉNARIO C — {scenario['name']}", allC, respC3,
             " | ".join(c[2] for c in checks_C if not c[1]))
    print("\n  Détail :")
    for name, ok, detail in checks_C:
        tag = "[PASS]" if ok else "[FAIL]"
        line = f"    {tag} {name}"
        if not ok:
            line += f" -> {detail}"
        print(line)

    # ── Résumé ───────────────────────────────────────────────────
    total  = len(results)
    passed = sum(results)
    print(f"\n{'='*60}")
    print(f"RESULTAT FINAL : {passed}/{total} tests passes")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
