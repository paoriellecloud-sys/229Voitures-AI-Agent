"""
Tests personas — 3 profils d'acheteurs sur 3 tours chacun
Usage : python tests/test_personas.py
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


scenarios = [
    {"persona": "Pragmatique", "steps": [
        "Cherche un véhicule 30k$ tout inclus",
        "Quels sont les frais cachés?",
        "RDV mardi 16h",
    ]},
    {"persona": "Technique", "steps": [
        "RAV4 vs Escape, fiabilité?",
        "Consommation ville?",
        "RDV samedi 10h",
    ]},
    {"persona": "Sceptique", "steps": [
        "Vous vendez des autos accidentées?",
        "Pourquoi je devrais te faire confiance?",
        "RDV, note inspection",
    ]},
]


def main():
    print("[*] Connexion...")
    token = get_token()
    print("[OK] Token obtenu\n")

    # ═══════════════════════════════════════════════════════════
    # PERSONA 1 — PRAGMATIQUE
    # ═══════════════════════════════════════════════════════════
    persona = scenarios[0]
    sid = str(uuid.uuid4())
    print(f"\n{'='*60}")
    print(f"PERSONA : {persona['persona']}")
    print(f"{'='*60}")

    # Tour 1 : recherche budget 30 000$ tout inclus
    # prix avant taxes = 30 000 / 1.14975 ≈ 26 092$
    r1 = chat(token, persona["steps"][0], sid)
    resp1  = r1.get("response", "")
    html1  = r1.get("html_cards", "") or r1.get("_html_cards", "")

    vP1_1 = bool(html1 and len(html1.strip()) > 50)

    import re as _re
    raw_prices = _re.findall(r'(\d[\d\s]{3,6})\s*\$', html1)
    prices1 = []
    for p in raw_prices:
        try:
            v = int(p.replace(' ', '').replace(' ', '').replace(',', ''))
            if 5000 < v < 100000:
                prices1.append(v)
        except ValueError:
            pass
    vP1_2 = all(p <= 26200 for p in prices1) if prices1 else True

    # Tour 2 : frais cachés → agent doit dire qu'il n'y en a pas de légaux
    r2 = chat(token, persona["steps"][1], sid)
    resp2  = r2.get("response", "")
    lower2 = resp2.lower()

    legal_signals = [
        "illégal", "illégaux", "interdit", "interdits",
        "opc", "lpc", "protection du consommateur",
        "pas le droit", "aucun frais", "seules taxes",
        "seulement les taxes", "tps", "tvq",
    ]
    vP1_3 = any(s in lower2 for s in legal_signals)
    vP1_4 = "frais de préparation" not in lower2 or "illégal" in lower2 or "interdit" in lower2

    # Tour 3 : RDV → formulaire affiché
    r3 = chat(token, persona["steps"][2], sid)
    resp3 = r3.get("response", "")
    html3 = r3.get("html_cards", "") or r3.get("_html_cards", "")

    vP1_5 = bool(html3 and len(html3.strip()) > 50)

    checks_P1 = [
        ("T1 — Véhicules retournés dans budget", vP1_1,
         f"html_cards vide ({len(html1)} chars)"),
        ("T1 — Prix ≤ 26 200$ (total ≤ 30 000$ avec taxes)", vP1_2,
         f"Prix hors budget: {[p for p in prices1 if p > 26200]}"),
        ("T2 — Signal légal sur frais additionnels", vP1_3,
         f"Aucun signal OPC/LPC/illégal — réponse: {resp2[:100]}"),
        ("T2 — Frais de préparation non validés", vP1_4,
         "Agent mentionne 'frais de préparation' sans les qualifier d'illégaux"),
        ("T3 — Formulaire RDV affiché", vP1_5,
         f"html_cards vide après 'RDV mardi 16h' ({len(html3)} chars)"),
    ]
    all_P1 = all(c[1] for c in checks_P1)
    run_test(f"PERSONA 1 — {persona['persona']}", all_P1, resp3,
             " | ".join(c[2] for c in checks_P1 if not c[1]))
    print("\n  Détail :")
    for name, ok, detail in checks_P1:
        tag = "[PASS]" if ok else "[FAIL]"
        line = f"    {tag} {name}"
        if not ok:
            line += f" -> {detail}"
        print(line)

    # ═══════════════════════════════════════════════════════════
    # PERSONA 2 — TECHNIQUE
    # ═══════════════════════════════════════════════════════════
    persona = scenarios[1]
    sid = str(uuid.uuid4())
    print(f"\n{'='*60}")
    print(f"PERSONA : {persona['persona']}")
    print(f"{'='*60}")

    # Tour 1 : comparaison fiabilité RAV4 vs Escape → CHAT attendu
    r1 = chat(token, persona["steps"][0], sid)
    resp1  = r1.get("response", "")
    lower1 = resp1.lower()

    vT_1 = "rav4" in lower1 and ("escape" in lower1 or "ford" in lower1)
    vT_2 = any(s in lower1 for s in ["fiab", "moteur", "km", "kilomét", "transmission", "problème", "rappel"])

    # Tour 2 : consommation ville → réponse technique, pas de fiches
    r2 = chat(token, persona["steps"][1], sid)
    resp2  = r2.get("response", "")
    html2  = r2.get("html_cards", "") or r2.get("_html_cards", "")
    lower2 = resp2.lower()

    vT_3 = any(s in lower2 for s in ["l/100", "consommation", "litres", "hybride", "mpg", "carburant"])
    vT_4 = not bool(html2 and len(html2.strip()) > 50)

    # Tour 3 : RDV samedi 10h
    r3 = chat(token, persona["steps"][2], sid)
    html3 = r3.get("html_cards", "") or r3.get("_html_cards", "")

    vT_5 = bool(html3 and len(html3.strip()) > 50)

    checks_T = [
        ("T1 — Mentionne RAV4 et Escape", vT_1,
         f"Un des deux modèles absent de la réponse: {resp1[:100]}"),
        ("T1 — Parle de fiabilité/mécanique", vT_2,
         f"Aucun terme technique fiabilité: {resp1[:100]}"),
        ("T2 — Parle de consommation", vT_3,
         f"Aucune donnée conso ville: {resp2[:100]}"),
        ("T2 — Pas de fiches HTML (question technique)", vT_4,
         f"html_cards non vide inattendu ({len(html2)} chars)"),
        ("T3 — Formulaire RDV affiché", vT_5,
         f"html_cards vide après 'RDV samedi 10h' ({len(html3)} chars)"),
    ]
    all_T = all(c[1] for c in checks_T)
    run_test(f"PERSONA 2 — {persona['persona']}", all_T, r3.get("response", ""),
             " | ".join(c[2] for c in checks_T if not c[1]))
    print("\n  Détail :")
    for name, ok, detail in checks_T:
        tag = "[PASS]" if ok else "[FAIL]"
        line = f"    {tag} {name}"
        if not ok:
            line += f" -> {detail}"
        print(line)

    # ═══════════════════════════════════════════════════════════
    # PERSONA 3 — SCEPTIQUE
    # ═══════════════════════════════════════════════════════════
    persona = scenarios[2]
    sid = str(uuid.uuid4())
    print(f"\n{'='*60}")
    print(f"PERSONA : {persona['persona']}")
    print(f"{'='*60}")

    # Tour 1 : "Vous vendez des autos accidentées?"
    r1 = chat(token, persona["steps"][0], sid)
    resp1  = r1.get("response", "")
    lower1 = resp1.lower()

    transparency_signals = [
        "carfax", "rapport vin", "inspection", "accident",
        "historique", "concessionnaire", "certifié", "certifie",
        "transparent", "rapports", "vérif",
    ]
    vS_1 = any(s in lower1 for s in transparency_signals)
    vS_2 = "oui on vend" not in lower1 and "on vend des" not in lower1

    # Tour 2 : "Pourquoi je devrais te faire confiance?"
    r2 = chat(token, persona["steps"][1], sid)
    resp2  = r2.get("response", "")
    lower2 = resp2.lower()

    trust_signals = [
        "concessionnaire", "partenaire", "certifié", "certifie",
        "opc", "protection", "inspection", "carfax",
        "transparent", "données", "inventaire", "229",
    ]
    vS_3 = any(s in lower2 for s in trust_signals)
    vS_4 = len(resp2) > 80

    # Tour 3 : "RDV, note inspection" → formulaire + mentionne inspection
    r3 = chat(token, persona["steps"][2], sid)
    resp3  = r3.get("response", "")
    html3  = r3.get("html_cards", "") or r3.get("_html_cards", "")
    lower3 = resp3.lower()

    vS_5 = bool(html3 and len(html3.strip()) > 50)
    vS_6 = "inspection" in lower3 or "inspection" in html3.lower()

    checks_S = [
        ("T1 — Parle de transparence/Carfax/historique", vS_1,
         f"Aucun signal transparence: {resp1[:100]}"),
        ("T1 — Ne confirme pas vendre des autos accidentées", vS_2,
         "Agent a dit qu'il vend des autos accidentées"),
        ("T2 — Argumente la confiance", vS_3,
         f"Aucun signal de crédibilité: {resp2[:100]}"),
        ("T2 — Réponse substantielle (>80 chars)", vS_4,
         f"Réponse trop courte ({len(resp2)} chars)"),
        ("T3 — Formulaire RDV affiché", vS_5,
         f"html_cards vide après 'RDV, note inspection' ({len(html3)} chars)"),
        ("T3 — Inspection mentionnée dans le RDV", vS_6,
         "Le mot 'inspection' absent de la réponse/formulaire"),
    ]
    all_S = all(c[1] for c in checks_S)
    run_test(f"PERSONA 3 — {persona['persona']}", all_S, resp3,
             " | ".join(c[2] for c in checks_S if not c[1]))
    print("\n  Détail :")
    for name, ok, detail in checks_S:
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
