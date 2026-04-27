"""
Tests automatisés de l'agent 229Voitures
Usage : python tests/test_agent.py
"""

import uuid
import requests

BASE_URL = "http://148.116.73.158:8000"
CHAT_URL = f"{BASE_URL}/agent/chat"
TEST_USER = "test_agent_auto"
TEST_PASS = "testpass_229"

# ──────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────

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


# ──────────────────────────────────────
# Test runner
# ──────────────────────────────────────

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


# ──────────────────────────────────────
# Main
# ──────────────────────────────────────

def main():
    print("[*] Connexion...")
    token = get_token()
    print("[OK] Token obtenu\n")

    # ── SCÉNARIO 1 — Cohérence prix ──────────────────────────────
    sid = str(uuid.uuid4())
    r1 = chat(token, "je cherche un RAV4", sid)
    resp1 = r1.get("response", "")
    r2 = chat(token, "c'est quoi le prix exact de la proposition 1?", sid)
    resp2 = r2.get("response", "")
    # Vérification : la réponse au suivi ne doit pas inventer de prix hors contexte
    # On s'assure qu'elle contient un chiffre ou "proposition 1"
    passed1 = any(c.isdigit() for c in resp2) or "proposition" in resp2.lower() or "rav4" in resp2.lower()
    detail1 = "Réponse vide ou sans référence au véhicule" if not passed1 else ""
    run_test("SCÉNARIO 1 — Cohérence prix", passed1, resp2, detail1)

    # ── SCÉNARIO 2 — Budget respecté ─────────────────────────────
    sid = str(uuid.uuid4())
    r = chat(token, "je cherche un VUS à moins de 15 000$", sid)
    resp = r.get("response", "")
    html = r.get("html_cards", "") or r.get("_html_cards", "")
    # Chercher les prix dans le HTML des fiches (format: XX XXX $)
    import re
    prices_raw = re.findall(r'(\d[\d\s]{2,})\s*\$', html)
    over_budget = []
    for p in prices_raw:
        try:
            val = int(p.replace(" ", "").replace(" ", ""))
            if val > 15000:
                over_budget.append(val)
        except ValueError:
            pass
    passed2 = len(over_budget) == 0
    detail2 = f"Véhicules hors budget trouvés : {over_budget}" if not passed2 else ""
    run_test("SCÉNARIO 2 — Budget respecté", passed2, resp, detail2)

    # ── SCÉNARIO 3 — Hallucination modèle inexistant ─────────────
    sid = str(uuid.uuid4())
    r = chat(token, "as-tu une Lamborghini Urus 2023?", sid)
    resp = r.get("response", "")
    resp_lower = resp.lower()
    # L'agent ne doit pas affirmer qu'il a une Lamborghini
    hallucination_signals = ["voici", "proposition 1", "prix :", "kilométrage", "km,"]
    no_hallucination = not any(s in resp_lower for s in hallucination_signals)
    # Et doit indiquer l'absence
    absence_signals = ["pas", "n'avons", "n'ai", "inventaire", "hors", "disponible", "aucun", "trouv"]
    acknowledges_absence = any(s in resp_lower for s in absence_signals)
    passed3 = no_hallucination and acknowledges_absence
    detail3 = (
        f"Hallucination détectée (contient {[s for s in hallucination_signals if s in resp_lower]})"
        if not no_hallucination else
        "N'indique pas clairement l'absence du véhicule"
    )
    run_test("SCÉNARIO 3 — Hallucination modèle inexistant", passed3, resp, detail3)

    # ── SCÉNARIO 4 — Frais illégaux ──────────────────────────────
    sid = str(uuid.uuid4())
    r = chat(token, "le vendeur me demande 800$ de frais de préparation, c'est normal?", sid)
    resp = r.get("response", "")
    resp_lower = resp.lower()
    mentions_opc = any(w in resp_lower for w in ["opc", "office de la protection", "illégal", "illegal", "interdit", "refuser", "contraire"])
    passed4 = mentions_opc
    detail4 = "Ne mentionne pas l'OPC ni le caractère illégal des frais" if not passed4 else ""
    run_test("SCÉNARIO 4 — Frais illégaux", passed4, resp, detail4)

    # ── SCÉNARIO 5 — Rabais gouvernementaux ──────────────────────
    sid = str(uuid.uuid4())
    r = chat(token, "est-ce que le RAV4 Prime usagé est admissible aux rabais gouvernementaux?", sid)
    resp = r.get("response", "")
    resp_lower = resp.lower()
    says_no = any(w in resp_lower for w in ["non", "pas admissible", "ne s'applique pas", "uniquement neuf", "seulement neuf", "neuf", "pas éligible"])
    passed5 = says_no
    detail5 = "Ne dit pas clairement NON aux rabais sur les véhicules d'occasion" if not passed5 else ""
    run_test("SCÉNARIO 5 — Rabais gouvernementaux usagés", passed5, resp, detail5)

    # ── SCÉNARIO 6 — Tutoiement ──────────────────────────────────
    sid = str(uuid.uuid4())
    r = chat(token, "bonjour", sid)
    resp = r.get("response", "")
    resp_lower = resp.lower()
    uses_vous = any(w in resp_lower for w in [" vous ", "votre ", "vos ", "pouvez-vous"])
    uses_tu = any(w in resp_lower for w in [" tu ", " te ", " ton ", " ta ", " tes ", "t'"])
    passed6 = not uses_vous or uses_tu
    detail6 = f"Utilise le vouvoiement : {[w for w in [' vous ', 'votre ', 'vos '] if w in resp_lower]}" if not passed6 else ""
    run_test("SCÉNARIO 6 — Tutoiement", passed6, resp, detail6)

    # ── SCÉNARIO 7 — Opinion sans fiches ─────────────────────────
    sid = str(uuid.uuid4())
    r = chat(token, "que penses-tu du Kia Seltos 2022?", sid)
    resp = r.get("response", "")
    html = r.get("html_cards", "") or r.get("_html_cards", "")
    has_cards = bool(html and len(html.strip()) > 50)
    passed7 = not has_cards
    detail7 = f"Des fiches HTML ont été retournées ({len(html)} chars)" if not passed7 else ""
    run_test("SCÉNARIO 7 — Opinion sans fiches", passed7, resp, detail7)

    # ── SCÉNARIO 8 — 7 places ────────────────────────────────────
    sid = str(uuid.uuid4())
    r = chat(token, "je cherche un véhicule 7 places pour ma famille", sid)
    resp = r.get("response", "")
    resp_lower = resp.lower()
    html = r.get("html_cards", "") or r.get("_html_cards", "")
    compact_5_seats = ["kona", "seltos", "civic", "corolla", "elantra", "yaris", "accent", "fit", "versa"]
    found_compact = [m for m in compact_5_seats if m in (resp_lower + html.lower())]
    passed8 = len(found_compact) == 0
    detail8 = f"Véhicules 5 places proposés : {found_compact}" if not passed8 else ""
    run_test("SCÉNARIO 8 — 7 places (pas de compactes)", passed8, resp, detail8)

    # ── SCÉNARIO 9 — QA conversation multi-tours ─────────────────
    import re as _re9
    sid = str(uuid.uuid4())

    # ── Tour 1 : recherche avec budget ──
    r9_1 = chat(token, "Cherche des Ford Escape 2021 à 25 000$", sid)
    resp9_1 = r9_1.get("response", "")
    html9_1 = r9_1.get("html_cards", "") or r9_1.get("_html_cards", "")

    v1a = bool(html9_1 and "escape" in html9_1.lower())
    prices_raw = _re9.findall(r'(\d[\d \s]{2,})\s*\$', html9_1)
    over_25k = []
    for p in prices_raw:
        try:
            val = int(p.replace(" ", "").replace(" ", "").replace(" ", ""))
            if val > 25000:
                over_25k.append(val)
        except ValueError:
            pass
    v1b = len(over_25k) == 0
    v1c = bool(html9_1 and len(html9_1.strip()) > 50)

    # ── Tour 2 : question générale fiscalité ──
    r9_2 = chat(token, "Explique-moi le calcul de la TVQ", sid)
    resp9_2 = r9_2.get("response", "")
    html9_2 = r9_2.get("html_cards", "") or r9_2.get("_html_cards", "")

    v2a = "9.975" in resp9_2 or "9,975" in resp9_2
    v2b = "5" in resp9_2 and "tps" in resp9_2.lower()
    v2c = not bool(html9_2 and len(html9_2.strip()) > 50)

    # ── Tour 3 : RDV sur le véhicule du tour 1 ──
    r9_3 = chat(token, "Ok, prends le premier Escape et prépare un RDV pour samedi", sid)
    resp9_3 = r9_3.get("response", "")
    html9_3 = r9_3.get("html_cards", "") or r9_3.get("_html_cards", "")

    v3a = bool(html9_3 and len(html9_3.strip()) > 50)
    v3b = "escape" in html9_3.lower()
    v3c = "2021" in html9_3
    v3d = not any(w in resp9_3.lower() for w in [
        "faites une recherche", "cherchez d'abord", "recherche d'abord",
        "trouver un véhicule d'abord", "aucun véhicule sélectionné",
    ])

    checks_9 = [
        ("1a - Fiches Escape retournées",       v1a, f"html_cards vide ou sans 'escape' ({len(html9_1)} chars)"),
        ("1b - Prix <= 25 000$",                v1b, f"Véhicules hors budget: {over_25k}"),
        ("1c - vehicle_shown non vide",         v1c, "Aucune fiche retournée après recherche"),
        ("2a - TVQ 9.975% mentionnée",          v2a, "Pas de '9.975' dans la réponse"),
        ("2b - TPS 5% mentionnée",              v2b, "Pas de référence TPS + 5%"),
        ("2c - Pas de fiches (question fisc.)", v2c, f"Fiches inattendues ({len(html9_2)} chars)"),
        ("3a - Formulaire RDV affiché",         v3a, f"html_cards vide après demande RDV ({len(html9_3)} chars)"),
        ("3b - Formulaire contient 'Escape'",   v3b, "Mot 'Escape' absent du formulaire"),
        ("3c - Formulaire contient '2021'",     v3c, "Année '2021' absente du formulaire"),
        ("3d - Pas de 'recherche d'abord'",     v3d, "Message demandant une recherche préalable détecté"),
    ]

    all9 = all(c[1] for c in checks_9)
    run_test(
        "SCÉNARIO 9 — QA conversation multi-tours",
        all9,
        resp9_3,
        " | ".join(c[2] for c in checks_9 if not c[1]),
    )
    print("\n  Détail des vérifications :")
    for name, passed_check, detail in checks_9:
        tag = "[PASS]" if passed_check else "[FAIL]"
        line = f"    {tag} {name}"
        if not passed_check:
            line += f" -> {detail}"
        print(line)

    # ── Résumé ───────────────────────────────────────────────────
    total = len(results)
    passed = sum(results)
    print(f"\n{'='*60}")
    print(f"RESULTAT FINAL : {passed}/{total} tests passes")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
