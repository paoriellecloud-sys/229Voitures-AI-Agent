"""
Comparator Agent — comparaison côte à côte de 2 ou 3 propositions.
"""
import re

_ORDINAL_TO_INT = {
    "premier": 1, "première": 1, "1er": 1, "1ère": 1,
    "deuxième": 2, "deuxieme": 2, "second": 2, "seconde": 2, "2e": 2,
    "troisième": 3, "troisieme": 3, "3e": 3,
}

_COMPARE_KEYWORDS = [
    "compar", "comparaison", "lequel est mieux", "quel est le meilleur",
    "différence entre", "difference entre", "entre les deux", "entre les trois",
    "le meilleur", "le plus avantageux",
]


def detect_compare_request(message: str) -> list[int]:
    """
    Retourne la liste 1-based des propositions à comparer,
    ou [] si le message n'est pas une demande de comparaison.
    """
    msg = message.lower()

    if not any(kw in msg for kw in _COMPARE_KEYWORDS):
        return []

    indices = set()

    # Chiffres explicites : "proposition 1 et 3", "#2", etc.
    for m in re.finditer(r'(?:proposition\s*|#\s*)?(\d)\b', msg):
        n = int(m.group(1))
        if 1 <= n <= 3:
            indices.add(n)

    # Ordinaux textuels : "premier", "deuxième", etc.
    for word, n in _ORDINAL_TO_INT.items():
        if re.search(rf'\b{re.escape(word)}\b', msg):
            indices.add(n)

    # "les deux" ou "les trois" → comparer tout
    if "les deux" in msg and not indices:
        indices = {1, 2}
    if "les trois" in msg and not indices:
        indices = {1, 2, 3}

    return sorted(indices) if len(indices) >= 2 else []


def calculate_monthly_payment(price: float, rate: float = 0.0799, months: int = 72) -> float:
    """Paiement mensuel TTC estimé sur 72 mois à 7.99%."""
    total = price * 1.14975
    r = rate / 12
    return round(total * r / (1 - (1 + r) ** -months))


def _extract_field(v: dict, *keys, default=None):
    """Retourne la première clé non-nulle trouvée dans le dict."""
    for k in keys:
        val = v.get(k)
        if val is not None and val != "":
            return val
    return default


def _score_vehicle(v_info: dict, all_prices: list[float], price_max: float | None) -> int:
    score = 100
    prix = v_info["prix"] or 0
    km = v_info["km"] or 0

    # Budget
    if price_max and prix > price_max:
        score -= 30
    elif price_max and prix <= price_max:
        score += 10

    # Prix relatif aux autres propositions
    if all_prices:
        avg = sum(all_prices) / len(all_prices)
        if prix < avg * 0.95:
            score += 10
        elif prix > avg * 1.05:
            score -= 10

    # Kilométrage
    if km < 30000:
        score += 15
    elif km < 60000:
        score += 5
    elif km > 100000:
        score -= 15
    elif km > 80000:
        score -= 8

    # Traction intégrale
    traction = (v_info.get("traction") or "").lower()
    if any(t in traction for t in ["awd", "4wd", "4x4", "intégrale", "integrale"]):
        score += 5

    # Carburant hybride/PHEV
    carburant = (v_info.get("carburant") or "").lower()
    if any(c in carburant for c in ["phev", "hybride", "hybrid", "électrique"]):
        score += 5

    return max(0, min(100, score))


def _build_avantages_inconvenients(v_info: dict, all_prices: list[float], price_max: float | None) -> tuple[list, list]:
    prix = v_info["prix"] or 0
    km = v_info["km"] or 0
    avantages, inconvenients = [], []

    # Budget
    if price_max:
        if prix <= price_max:
            avantages.append("Dans le budget")
        else:
            inconvenients.append(f"Hors budget ({int(prix - price_max):,}$ de plus)".replace(",", " "))

    # Prix vs groupe
    if all_prices and len(all_prices) > 1:
        avg = sum(all_prices) / len(all_prices)
        if prix < avg * 0.95:
            avantages.append("Prix sous la moyenne du groupe")
        elif prix > avg * 1.05:
            inconvenients.append("Prix au-dessus de la moyenne")

    # Kilométrage
    if km < 30000:
        avantages.append(f"Faible kilométrage ({km:,} km)".replace(",", " "))
    elif km < 60000:
        avantages.append(f"Kilométrage raisonnable ({km:,} km)".replace(",", " "))
    elif km > 100000:
        inconvenients.append(f"Kilométrage élevé ({km:,} km)".replace(",", " "))
    elif km > 80000:
        inconvenients.append(f"Kilométrage important ({km:,} km)".replace(",", " "))

    # Traction
    traction = (v_info.get("traction") or "").lower()
    if any(t in traction for t in ["awd", "4wd", "4x4", "intégrale"]):
        avantages.append("Traction intégrale")

    # Carburant
    carburant = (v_info.get("carburant") or "").lower()
    if "phev" in carburant or "hybride branchable" in carburant:
        avantages.append("PHEV — faible consommation")
    elif "hybride" in carburant or "hybrid" in carburant:
        avantages.append("Hybride — économique")
    elif "électrique" in carburant:
        avantages.append("Électrique — 0 émission")

    return avantages, inconvenients


def build_comparison(
    vehicles: list[dict],
    indices: list[int],
    price_max: float = None,
    user_profile: dict = None,
) -> dict:
    """
    Construit la structure de comparaison entre les véhicules aux indices donnés (1-based).
    """
    selected = []
    for i in indices:
        if 1 <= i <= len(vehicles) and vehicles[i - 1]:
            v = vehicles[i - 1]
            prix = float(_extract_field(v, "price", "prix", default=0) or 0)
            km = int(_extract_field(v, "mileage", "kilometrage", "km", default=0) or 0)
            year = _extract_field(v, "year", "annee", default="")
            make = _extract_field(v, "make", "marque", default="")
            model = _extract_field(v, "model", "modele", default="")
            titre = f"{year} {make} {model}".strip() or f"Proposition {i}"
            selected.append({
                "proposition": i,
                "titre": titre,
                "prix": prix,
                "mensuel": calculate_monthly_payment(prix) if prix else 0,
                "km": km,
                "traction": _extract_field(v, "drivetrain", "traction", default="N/D"),
                "carburant": _extract_field(v, "fuel_type", "carburant", default="N/D"),
                "dans_budget": (prix <= price_max) if (price_max and prix) else True,
                "_raw": v,
            })

    all_prices = [s["prix"] for s in selected if s["prix"]]

    result_vehicles = []
    for s in selected:
        avantages, inconvenients = _build_avantages_inconvenients(s, all_prices, price_max)
        score = _score_vehicle(s, all_prices, price_max)
        result_vehicles.append({
            "proposition": s["proposition"],
            "titre": s["titre"],
            "prix": s["prix"],
            "mensuel": s["mensuel"],
            "km": s["km"],
            "traction": s["traction"],
            "carburant": s["carburant"],
            "dans_budget": s["dans_budget"],
            "avantages": avantages,
            "inconvenients": inconvenients,
            "score": score,
        })

    # Choisir la recommandation (meilleur score, privilégier dans le budget)
    best = max(result_vehicles, key=lambda x: (x["dans_budget"], x["score"]))
    raison = "Meilleur rapport qualité-prix"
    if price_max and best["dans_budget"]:
        raison = "Meilleur rapport qualité-prix dans le budget"
    elif not best["dans_budget"]:
        raison = "Meilleur score global malgré le dépassement de budget"

    return {
        "vehicles": result_vehicles,
        "recommandation": best["proposition"],
        "raison": raison,
    }


def generate_comparison_html(comparison: dict) -> str:
    """Génère le tableau HTML de comparaison aux couleurs 229Voitures."""
    vehicles = comparison.get("vehicles", [])
    recommandation = comparison.get("recommandation")
    raison = comparison.get("raison", "")

    if not vehicles:
        return ""

    # Styles communs
    _S_TABLE = (
        'style="background:#1a1a2e;border-radius:12px;overflow:hidden;'
        'font-family:Inter,sans-serif;margin:12px 0;width:100%;"'
    )
    _S_HEADER_ROW = (
        'style="display:grid;grid-template-columns:130px '
        + " ".join(["1fr"] * len(vehicles))
        + ';background:#0d0d1a;padding:12px 16px;gap:8px;"'
    )
    _S_ROW = (
        'style="display:grid;grid-template-columns:130px '
        + " ".join(["1fr"] * len(vehicles))
        + ';padding:10px 16px;gap:8px;border-top:1px solid rgba(255,255,255,0.06);"'
    )
    _S_LABEL = 'style="font-size:12px;color:#888;font-weight:500;"'
    _S_VAL = 'style="font-size:13px;color:#f0f0f0;font-weight:600;text-align:center;"'
    _S_IN = 'style="font-size:13px;color:#4ade80;font-weight:600;text-align:center;"'
    _S_OUT = 'style="font-size:13px;color:#f87171;font-weight:600;text-align:center;"'
    _S_HEAD_CELL = 'style="font-size:12px;color:#FAC775;font-weight:700;text-align:center;"'

    def _row(label: str, values: list[tuple[str, bool | None]]) -> str:
        cells = ""
        for val, is_good in values:
            if is_good is True:
                cells += f'<div class="in-budget" {_S_IN}>{val}</div>'
            elif is_good is False:
                cells += f'<div class="over-budget" {_S_OUT}>{val}</div>'
            else:
                cells += f'<div {_S_VAL}>{val}</div>'
        return f'<div class="comp-row" {_S_ROW}><div {_S_LABEL}>{label}</div>{cells}</div>'

    def _fmt_prix(p: float) -> str:
        return f"{int(p):,}$".replace(",", " ") if p else "N/D"

    def _fmt_km(k: int) -> str:
        return f"{k:,} km".replace(",", " ") if k else "N/D"

    # En-tête
    header_cells = "".join(
        f'<div {_S_HEAD_CELL}>Proposition {v["proposition"]}</div>'
        for v in vehicles
    )
    header = (
        f'<div class="comp-header" {_S_HEADER_ROW}>'
        f'<div {_S_LABEL}>Critère</div>{header_cells}</div>'
    )

    # Lignes
    rows = ""
    rows += _row("Prix", [(_fmt_prix(v["prix"]), v["dans_budget"] or None) for v in vehicles])
    rows += _row("Mensuel ~", [(f"{v['mensuel']} $/mois", None) for v in vehicles])
    rows += _row("Kilométrage", [(_fmt_km(v["km"]), None) for v in vehicles])
    rows += _row("Traction", [(v["traction"] or "N/D", None) for v in vehicles])
    rows += _row("Carburant", [(v["carburant"] or "N/D", None) for v in vehicles])

    # Ligne score
    max_score = max(v["score"] for v in vehicles)
    rows += _row("Score", [
        (f'{v["score"]}/100', True if v["score"] == max_score else None)
        for v in vehicles
    ])

    # Avantages / inconvénients par colonne
    adv_row = f'<div {_S_ROW}><div {_S_LABEL}>✅ Avantages</div>'
    for v in vehicles:
        items = "".join(f'<div style="font-size:11px;color:#4ade80;">• {a}</div>' for a in v["avantages"][:3])
        adv_row += f'<div style="text-align:left;">{items or "—"}</div>'
    adv_row += "</div>"
    rows += adv_row

    inc_row = f'<div {_S_ROW}><div {_S_LABEL}>⚠️ Points</div>'
    for v in vehicles:
        items = "".join(f'<div style="font-size:11px;color:#f87171;">• {c}</div>' for c in v["inconvenients"][:2])
        inc_row += f'<div style="text-align:left;">{items or "—"}</div>'
    inc_row += "</div>"
    rows += inc_row

    # Bannière recommandation
    winner = (
        '<div class="comp-winner" style="'
        'background:linear-gradient(135deg,#1e3a5f,#0d2137);'
        'padding:14px 18px;text-align:center;border-top:2px solid #FAC775;">'
        f'<div style="font-size:14px;color:#FAC775;font-weight:700;">'
        f'⭐ Recommandation : Proposition {recommandation}</div>'
        f'<div style="font-size:12px;color:#aaa;margin-top:4px;">{raison}</div>'
        "</div>"
    )

    return f'<div class="comparison-table" {_S_TABLE}>{header}{rows}{winner}</div>'
