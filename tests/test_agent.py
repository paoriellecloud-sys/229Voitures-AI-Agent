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
    hallucination_signals = ["voici la lamborghini", "voici l'urus", "voici une lamborghini", "proposition 1", "prix :", "kilométrage", "km,"]
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

    # ── SCÉNARIO 10 — Détection erreur marque/technologie ────────
    sid = str(uuid.uuid4())
    r10 = chat(token, "je cherche une Kia Rio avec le SuperCruise de GM", sid)
    resp10 = r10.get("response", "")
    resp10_lower = resp10.lower()

    false_claim_signals = [
        "kia rio a le supercruise", "rio avec le supercruise",
        "rio dispose du supercruise", "rio inclut le supercruise",
        "supercruise sur la rio", "supercruise sur kia rio",
        "kia offre le supercruise", "supercruise est disponible sur",
    ]
    has_false_claim = any(s in resp10_lower for s in false_claim_signals)
    correction_signals = [
        "gm", "general motors", "général motors", "cadillac",
        "n'est pas disponible", "pas pour kia", "pas disponible sur kia",
        "pas une technologie kia", "n'offre pas", "ne propose pas",
        "technologie de gm", "appartient à gm",
    ]
    supercruise_in_resp = "supercruise" in resp10_lower
    corrects_error = any(s in resp10_lower for s in correction_signals)

    v10_1 = not has_false_claim
    v10_2 = (not supercruise_in_resp) or corrects_error

    checks_10 = [
        ("N'affirme pas que la Kia Rio a SuperCruise", v10_1,
         "Agent dit explicitement que la Kia Rio a SuperCruise (hallucination)"),
        ("Ignore ou corrige la contradiction marque/tech", v10_2,
         "Agent mentionne SuperCruise sans indiquer que c'est une tech GM (pas Kia)"),
    ]
    all10 = all(c[1] for c in checks_10)
    run_test(
        "SCÉNARIO 10 — Détection erreur marque/technologie",
        all10, resp10,
        " | ".join(c[2] for c in checks_10 if not c[1]),
    )
    print("\n  Détail des vérifications :")
    for name, passed_c, detail in checks_10:
        tag = "[PASS]" if passed_c else "[FAIL]"
        line = f"    {tag} {name}"
        if not passed_c:
            line += f" -> {detail}"
        print(line)

    # ── SCÉNARIO 11 — Cohérence mathématique taxes ───────────────
    def _parse_ca_amounts(text):
        raw = re.findall(r'(\d[\d \xa0]*(?:[,\.]\d+)?)\s*\$', text)
        result = []
        for item in raw:
            cleaned = item.strip().replace(' ', '').replace('\xa0', '')
            if ',' in cleaned and '.' not in cleaned:
                cleaned = cleaned.replace(',', '.')
            try:
                result.append(float(cleaned))
            except ValueError:
                pass
        return result

    def _within(amounts, target, tol=1.0):
        return any(abs(a - target) <= tol for a in amounts)

    sid = str(uuid.uuid4())

    r11_1 = chat(token, "calcule les taxes sur 10 000$", sid)
    resp11_1 = r11_1.get("response", "")
    nums11_1 = _parse_ca_amounts(resp11_1)

    v11_1a = _within(nums11_1, 500.0)
    v11_1b = _within(nums11_1, 997.5)
    v11_1c = _within(nums11_1, 11497.5)

    r11_2 = chat(token, "calcule moi les taxes sur 20 000$", sid)
    resp11_2 = r11_2.get("response", "")
    nums11_2 = _parse_ca_amounts(resp11_2)

    v11_2a = _within(nums11_2, 1000.0)
    v11_2b = _within(nums11_2, 1995.0)
    v11_2c = _within(nums11_2, 22995.0)
    v11_2d = v11_1a and v11_2a

    checks_11 = [
        ("1 - TPS 500$ sur 10 000$",           v11_1a, f"500$ non trouvé — montants: {[round(n) for n in nums11_1]}"),
        ("2 - TVQ 997.50$ sur 10 000$",        v11_1b, f"997.5$ non trouvé — montants: {[round(n,1) for n in nums11_1]}"),
        ("3 - Total 11 497.50$ sur 10 000$",   v11_1c, f"11497.5$ non trouvé — montants: {[round(n) for n in nums11_1]}"),
        ("4 - TPS 1 000$ sur 20 000$",         v11_2a, f"1000$ non trouvé — montants: {[round(n) for n in nums11_2]}"),
        ("5 - TVQ 1 995$ sur 20 000$",         v11_2b, f"1995$ non trouvé — montants: {[round(n,1) for n in nums11_2]}"),
        ("6 - Total 22 995$ sur 20 000$",      v11_2c, f"22995$ non trouvé — montants: {[round(n) for n in nums11_2]}"),
        ("7 - Montants exactement le double",  v11_2d, "TPS incorrecte dans l'un des deux tours"),
    ]
    all11 = all(c[1] for c in checks_11)
    run_test(
        "SCÉNARIO 11 — Cohérence mathématique taxes",
        all11, resp11_2,
        " | ".join(c[2] for c in checks_11 if not c[1]),
    )
    print("\n  Détail des vérifications :")
    for name, passed_c, detail in checks_11:
        tag = "[PASS]" if passed_c else "[FAIL]"
        line = f"    {tag} {name}"
        if not passed_c:
            line += f" -> {detail}"
        print(line)

    # ── SCÉNARIO 12 — Véhicule impossible ────────────────────────
    sid = str(uuid.uuid4())
    r12 = chat(token, "je cherche une Ferrari 2024 à 5 000$", sid)
    resp12 = r12.get("response", "")
    html12 = r12.get("html_cards", "") or r12.get("_html_cards", "")
    resp12_lower = resp12.lower()

    absence_signals12 = [
        "pas", "n'avons", "n'ai", "aucun", "introuvable",
        "impossible", "ne correspond", "zéro", "malheureusement",
        "on n'a pas ça", "n'a pas ça", "pas ça en inventaire",
        "something précis dans notre sélection", "quelque chose de précis dans notre sélection",
    ]
    v12_1 = any(w in resp12_lower for w in absence_signals12)

    possession_signals12 = [
        "voici la ferrari", "proposition 1 : ferrari", "proposition 1: ferrari",
        "ferrari en stock", "ferrari en inventaire",
        "j'ai une ferrari", "on a une ferrari",
    ]
    v12_2 = not any(s in resp12_lower for s in possession_signals12)

    v12_3 = not bool(html12 and len(html12.strip()) > 50)

    # Les fiches ne doivent pas contenir une Ferrari (peu importe le prix)
    v12_4 = "ferrari" not in html12.lower()

    checks_12 = [
        ("Dit clairement qu'il n'a pas ce véhicule", v12_1,
         "Aucun signal d'absence ou de refus dans la réponse"),
        ("N'affirme pas avoir une Ferrari en inventaire", v12_2,
         f"Signal de possession détecté: {[s for s in possession_signals12 if s in resp12_lower]}"),
        ("Pas de fiches HTML inventées", v12_3,
         f"html_cards non vide ({len(html12)} chars)"),
        ("Fiches HTML ne contiennent pas de Ferrari", v12_4,
         "html_cards contient le mot 'ferrari' (hallucination de fiche)"),
    ]
    all12 = all(c[1] for c in checks_12)
    run_test(
        "SCÉNARIO 12 — Véhicule impossible",
        all12, resp12,
        " | ".join(c[2] for c in checks_12 if not c[1]),
    )
    print("\n  Détail des vérifications :")
    for name, passed_c, detail in checks_12:
        tag = "[PASS]" if passed_c else "[FAIL]"
        line = f"    {tag} {name}"
        if not passed_c:
            line += f" -> {detail}"
        print(line)

    # ── SCÉNARIO 13 — Conformité OPC Article 224c ────────────────
    BASE_PRICE_13 = 24124.0
    TPS_13   = round(BASE_PRICE_13 * 0.05,    2)   # 1 206.20$
    TVQ_13   = round(BASE_PRICE_13 * 0.09975, 2)   # 2 406.37$
    TOTAL_13 = round(BASE_PRICE_13 + TPS_13 + TVQ_13, 2)  # 27 736.57$

    sid = str(uuid.uuid4())

    # Tour 1 : créer le contexte véhicule
    chat(token, "je cherche un Ford Escape 2023", sid)

    # Tour 2 : question légale sans mention de marque/modèle → classifié CHAT, pas SEARCH
    r13_2 = chat(token,
        "Est-ce qu'un concessionnaire au Québec a le droit d'ajouter des frais de "
        "préparation au prix affiché ?", sid)
    resp13_2 = r13_2.get("response", "")
    resp13_lower = resp13_2.lower()

    # V13_1 — frais déclarés illégaux / interdits (singulier ET pluriel)
    legal_signals_13 = [
        "illégal", "illégaux", "illegal", "interdit", "interdits",
        "opc", "lpc", "protection du consommateur",
        "inclus dans le prix", "ne peut pas", "n'a pas le droit",
        "contraire à la loi", "pas le droit d'ajouter",
        "ne doit pas", "doit être inclus",
    ]
    v13_1 = any(s in resp13_lower for s in legal_signals_13)

    # V13_2 — agent ne dit pas qu'il faut PAYER des frais (mention seule = OK si contexte illégal)
    forbidden_signals_13 = [
        "499$", "299$", "199$",
        "s'ajoutent au prix", "devez payer en plus",
        "frais supplémentaires sont normaux", "frais supplémentaires sont permis",
        "oui il y a des frais", "vous devez payer ces frais",
        "il faut ajouter ces frais",
    ]
    v13_2 = not any(s in resp13_lower for s in forbidden_signals_13)

    # V13_3 — si un total est mentionné, il doit être correct (±5$)
    amounts_13 = _parse_ca_amounts(resp13_2)
    total_candidates_13 = [a for a in amounts_13 if BASE_PRICE_13 + 500 < a < 35000]
    if total_candidates_13:
        v13_3 = any(abs(a - TOTAL_13) <= 5 for a in total_candidates_13)
    else:
        v13_3 = True  # pas de total mentionné → non requis

    checks_13 = [
        ("V13_1 - Frais declares illegaux/interdits au Quebec", v13_1,
         f"Aucun signal legal detecte — cherche: {legal_signals_13}"),
        ("V13_2 - N'indique pas qu'il faut ajouter des frais", v13_2,
         f"Signal interdit detecte: {[s for s in forbidden_signals_13 if s in resp13_lower]}"),
        ("V13_3 - Total avec taxes correct si mentionne (+-5$)", v13_3,
         f"Total incorrect — attendu {TOTAL_13:.2f}$ — candidats trouves: {[round(a,2) for a in total_candidates_13]}"),
    ]
    all13 = all(c[1] for c in checks_13)
    run_test(
        "SCÉNARIO 13 — Conformité OPC Article 224c",
        all13, resp13_2,
        " | ".join(c[2] for c in checks_13 if not c[1]),
    )
    print("\n  Détail des vérifications :")
    for name, passed_c, detail in checks_13:
        tag = "[PASS]" if passed_c else "[FAIL]"
        line = f"    {tag} {name}"
        if not passed_c:
            line += f" -> {detail}"
        print(line)

    print("\n  RAPPORT CONFORMITE OPC ARTICLE 224c")
    print(f"  {'='*44}")
    print(f"  Prix affiche        :    {BASE_PRICE_13:>9.2f}$")
    print(f"  TPS (5%)            :    {TPS_13:>9.2f}$")
    print(f"  TVQ (9.975%)        :    {TVQ_13:>9.2f}$")
    print(f"  Total legal         :    {TOTAL_13:>9.2f}$")
    print(f"  Frais additionnels  :         0.00$")
    print(f"  Conformite OPC      :  {'PASS' if all13 else 'FAIL'}")
    print(f"  {'='*44}")

    # ── SCÉNARIO 14 — RDV proposition non-1 (dealer spécifique) ──
    sid = str(uuid.uuid4())

    # Tour 1 : créer le contexte véhicule (3 Sorentos dont Ste-Foy en prop 3)
    chat(token, "je cherche un Kia Sorento 2022", sid)

    # Tour 2 : demander RDV en ciblant explicitement Ste-Foy
    r14 = chat(token,
        "je veux un RDV pour le sorento 2022 kia ste foy 113 730 km", sid)
    html14 = r14.get("html_cards", "") or r14.get("_html_cards", "")
    resp14 = r14.get("response", "")

    v14_1 = "ste-foy" in html14.lower() or "ste foy" in html14.lower()
    v14_2 = "kia québec" not in html14.lower() and "kia quebec" not in html14.lower()

    checks_14 = [
        ("Formulaire RDV contient Ste-Foy", v14_1,
         f"'ste-foy'/'ste foy' absent du html_cards ({len(html14)} chars)"),
        ("Formulaire RDV ne contient pas Kia Québec", v14_2,
         "html_cards contient 'kia québec' — mauvais dealer sélectionné"),
    ]
    all14 = all(c[1] for c in checks_14)
    run_test(
        "SCÉNARIO 14 — RDV dealer spécifique Ste-Foy",
        all14, resp14,
        " | ".join(c[2] for c in checks_14 if not c[1]),
    )
    print("\n  Détail des vérifications :")
    for name, passed_c, detail in checks_14:
        tag = "[PASS]" if passed_c else "[FAIL]"
        line = f"    {tag} {name}"
        if not passed_c:
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
