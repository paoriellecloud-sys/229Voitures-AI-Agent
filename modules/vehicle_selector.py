"""
Vehicle Selector - 229Voitures
Responsabilite UNIQUE : identifier quel vehicule l'utilisateur mentionne
parmi les propositions affichees.
100% Python - aucun appel Gemini.
"""

import re


COLOR_ALIASES = {
    'noir': ['noir', 'noire', 'black'],
    'blanc': ['blanc', 'blanche', 'white'],
    'bleu': ['bleu', 'bleue', 'blue', 'marine'],
    'rouge': ['rouge', 'red', 'bordeaux'],
    'gris': ['gris', 'grise', 'grey', 'gray', 'argent', 'silver'],
    'vert': ['vert', 'verte', 'green'],
    'brun': ['brun', 'brune', 'brown', 'beige'],
    'orange': ['orange'],
    'jaune': ['jaune', 'yellow'],
}

FUEL_ALIASES = {
    'hybrid': ['hybrid', 'hybride', 'phev', 'plug-in', 'rechargeable'],
    'electrique': ['electrique', 'électrique', 'ev', 'electric'],
    'essence': ['essence', 'gasoline', 'gas'],
    'diesel': ['diesel'],
}

DRIVETRAIN_ALIASES = {
    'integrale': ['integrale', 'intégrale', 'awd', '4x4', '4wd'],
    'avant': ['avant', 'traction avant', 'fwd'],
    'propulsion': ['propulsion', 'rwd', 'arriere'],
}

DEALER_ALIASES = {
    'donnacona': ['donnacona'],
    'québec': ['kia québec', 'kia quebec', 'québec', 'quebec'],
    'val-bélair': ['val-bélair', 'val belair', 'val-belair'],
    'ste-foy': ['ste-foy', 'ste foy', 'sainte-foy'],
    'lévis': ['lévis', 'levis'],
}

ORDINAL_MAP = {
    'premi': 1, 'premier': 1, 'première': 1, 'premiere': 1,
    'deuxiem': 2, 'deuxième': 2,
    'troisiem': 3, 'troisième': 3,
}


def select_vehicle(message: str, vehicle_shown: dict) -> dict | None:
    """
    Point d'entree principal.
    1. Numero de proposition explicite (priorite absolue)
    2. Scoring par caracteristiques
    """
    if not vehicle_shown:
        return None

    if len(vehicle_shown) == 1:
        return list(vehicle_shown.values())[0]

    # Priorite 1 : numero explicite
    by_number = _select_by_number(message, vehicle_shown)
    if by_number is not None:
        return by_number

    # Priorite 2 : scoring
    return _select_by_score(message, vehicle_shown)


def _select_by_number(message: str, vehicle_shown: dict) -> dict | None:
    msg = message.lower()

    # Ordinaux textuels
    for ordinal, num in ORDINAL_MAP.items():
        if ordinal in msg and num in vehicle_shown:
            return vehicle_shown[num]

    # Numero direct : "proposition 2", "le 2", "la 2"
    match = re.search(r'(?:proposition|option|le|la)\s*(\d)', msg)
    if match:
        num = int(match.group(1))
        if num in vehicle_shown:
            return vehicle_shown[num]

    return None


def _select_by_score(message: str, vehicle_shown: dict) -> dict | None:
    msg = message.lower().strip()
    scores = {int(k): _score(msg, v) for k, v in vehicle_shown.items()}
    best_key = max(scores, key=lambda k: scores[k])
    best_score = scores[best_key]

    if best_score < 2:
        return None

    top_keys = [k for k, s in scores.items() if s == best_score]
    best = min(top_keys)
    return vehicle_shown.get(best) or vehicle_shown.get(str(best))


def _score(msg: str, vehicle: dict) -> int:
    score = 0

    make = str(vehicle.get('make', '')).lower()
    model = str(vehicle.get('model', '')).lower()
    year = str(vehicle.get('year', ''))
    dealer = str(vehicle.get('dealer_name', '')).lower()
    city = str(vehicle.get('city', '')).lower()
    color = str(vehicle.get('color', '')).lower()
    fuel = str(vehicle.get('fuel_type', '')).lower()
    drivetrain = str(vehicle.get('drivetrain', '')).lower()
    price = float(vehicle.get('price', 0))

    if year and year in msg:
        score += 4
    if model and model in msg:
        score += 3
    if make and make in msg:
        score += 1

    for canonical, aliases in DEALER_ALIASES.items():
        if any(a in dealer or a in city for a in aliases):
            if any(a in msg for a in aliases) or canonical in msg:
                score += 3
                break

    for canonical, aliases in COLOR_ALIASES.items():
        if any(a in color for a in aliases):
            if any(a in msg for a in aliases) or canonical in msg:
                score += 3
                break

    for canonical, aliases in FUEL_ALIASES.items():
        if any(a in fuel for a in aliases):
            if any(a in msg for a in aliases) or canonical in msg:
                score += 2
                break

    for canonical, aliases in DRIVETRAIN_ALIASES.items():
        if any(a in drivetrain for a in aliases):
            if any(a in msg for a in aliases) or canonical in msg:
                score += 2
                break

    price_match = re.search(r'(\d[\d\s]*)\s*\$', msg)
    if price_match:
        mentioned = float(price_match.group(1).replace(' ', ''))
        if abs(mentioned - price) < 500:
            score += 3

    return score
