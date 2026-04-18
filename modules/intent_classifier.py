"""
Intent Classifier - 229Voitures
Responsabilite UNIQUE : determiner l'intention de l'utilisateur.
100% Python - aucun appel Gemini.
"""

import re

RDV_PATTERNS = [
    r'\brdv\b', r'rendez.vous', r'prendre contact',
    r'je veux le voir', r'je veux la voir',
    r'je suis pr[ee]t', r'je le prends', r'je la prends',
    r'contacter le concessionnaire', r'appeler',
    r'formulaire', r'envoyer ma demande',
    r'je veux proc[ee]der', r'on y va',
    r'book', r'r[ee]server', r'mets.moi en contact',
    r'met.moi en contact', r'prendre rendez',
    r'je veux visiter', r'aller le voir', r'aller la voir',
    r'aller voir', r'je veux y aller',
    r'pr[eê]t [àa] aller', r'pret a aller',
]

SEARCH_TRIGGERS = [
    r'cherche', r'recherche', r'trouve', r'montre',
    r'propose', r'aurais.tu', r'as.tu', r'avez.vous',
    r'est.ce que tu as', r'y a.t.il', r'je veux un',
    r'je me magasine', r'je me cherche',
    r'show me', r'do you have', r'got any',
    r'qu\'est.ce que t\'as', r'c\'est quoi tes',
    r'aurais tu', r'as tu', r't\'as.tu',
]

KNOWN_MAKES = [
    'toyota', 'honda', 'ford', 'chevrolet', 'gmc',
    'dodge', 'ram', 'jeep', 'hyundai', 'kia',
    'mazda', 'nissan', 'subaru', 'volkswagen', 'audi',
    'bmw', 'mercedes', 'lexus', 'acura', 'infiniti',
    'cadillac', 'lincoln', 'volvo', 'tesla', 'rivian',
    'genesis', 'mitsubishi', 'chrysler', 'buick',
    'pontiac', 'saturn', 'oldsmobile', 'mercury',
    'fiat', 'alfa', 'porsche', 'jaguar', 'land rover',
    'mini', 'smart', 'scion', 'suzuki', 'isuzu',
]

KNOWN_MODELS = [
    'civic', 'corolla', 'camry', 'accord', 'elantra',
    'sonata', 'mazda3', 'altima', 'jetta', 'golf',
    'forte', 'optima', 'stinger', 'rav4', 'cr-v', 'crv',
    'escape', 'equinox', 'rogue', 'tucson', 'sportage',
    'seltos', 'kona', 'venue', 'qashqai', 'kicks',
    'rdx', 'mdx', 'explorer', 'pilot', 'highlander',
    'pathfinder', 'durango', 'traverse', 'tahoe',
    'suburban', 'expedition', 'bronco', 'wrangler',
    'cherokee', 'compass', 'trailblazer', 'blazer',
    'murano', 'outlander', 'santa fe', 'palisade',
    'telluride', 'sorento', 'carnival', 'sienna',
    'odyssey', 'pacifica', 'f-150', 'f150', 'silverado',
    'tundra', 'tacoma', 'frontier', 'titan', 'colorado',
    'ranger', 'maverick', 'sierra', 'ram 1500', 'ram1500',
    'bolt', 'leaf', 'ioniq', 'ev6', 'ev9', 'model 3',
    'model s', 'model x', 'model y', 'mach-e', 'id.4',
    'prius', 'insight', 'cx-5', 'cx5', 'cx-3', 'cx3',
    'cx-30', 'cx30', 'cx-9', 'cx9', 'rx', 'nx', 'ux',
    'x3', 'x5', 'x1', 'x2', '3 series', '5 series',
    'a4', 'a3', 'q5', 'q3', 'q7', 'glc', 'gle', 'c-class',
    'navigator', 'escalade', 'acadia', 'enclave',
    'encore', 'envision', 'xt4', 'xt5', 'xt6',
]

VEHICLE_CATEGORIES = [
    'vus', 'suv', 'berline', 'sedan', 'berlin',
    'camionnette', 'truck', 'pickup', 'pick-up',
    'fourgonnette', 'minivan', 'van',
    'electrique', 'hybride', 'phev', 'plug-in',
    'compacte', 'sous-compacte', 'luxe', 'sport',
    'coupe', 'familiale', 'economique',
]

VIN_PATTERN = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')

FOLLOWUP_PATTERNS = [
    r'\bcelle\b', r'\bcelui\b',
    r'\ble premier\b', r'\bla premi[ee]re\b',
    r'\bproposition\s*\d\b', r'\ble \d\b', r'\bla \d\b',
    r'\bcet(?:te)?\b', r'\bce mod[ee]le\b',
    r'dis.m[\'e]en plus', r'en savoir plus',
    r'plus de d[ee]tails', r'que penses.tu de',
    r'entre .+ et', r'\bla \d{4}\b',
    r'\bcelle de \d{4}\b', r'\bcelui de \d{4}\b',
    r'\bla (?:noire|blanche|bleue|rouge|grise|verte)\b',
    r'\bcelui (?:noir|blanc|bleu|rouge|gris|vert)\b',
    r'\bla moins ch[ee]re\b', r'\bla plus r[ee]cente\b',
    r'\bla plus abordable\b', r'\bla hybrid\b',
    r'\bcelui de donnacona\b', r'\bcelle de qu[ee]bec\b',
    r'\bcelle de ste.foy\b', r'\bcelle de val.b[ee]lair\b',
]


def classify(message: str, vehicle_shown: dict = None) -> dict:
    msg = message.lower().strip()
    vehicle_shown = vehicle_shown or {}

    # 1. VIN
    if VIN_PATTERN.search(message.upper()):
        return {"intent": "VIN", "vehicle_ref": None, "confidence": 99}

    # 2. RDV
    for pattern in RDV_PATTERNS:
        if re.search(pattern, msg):
            return {"intent": "RDV", "vehicle_ref": None, "confidence": 95}

    # 3. FOLLOWUP si propositions actives
    if vehicle_shown:
        for pattern in FOLLOWUP_PATTERNS:
            if re.search(pattern, msg):
                return {"intent": "FOLLOWUP", "vehicle_ref": None, "confidence": 85}

    # 4. SEARCH - trigger explicite
    for pattern in SEARCH_TRIGGERS:
        if re.search(pattern, msg):
            return {"intent": "SEARCH", "vehicle_ref": _extract_vehicle_ref(msg), "confidence": 90}

    # 5. SEARCH - marque connue
    for make in KNOWN_MAKES:
        if make in msg:
            return {"intent": "SEARCH", "vehicle_ref": make, "confidence": 85}

    # 6. SEARCH - modele connu
    for model in KNOWN_MODELS:
        if model in msg:
            return {"intent": "SEARCH", "vehicle_ref": model, "confidence": 85}

    # 7. SEARCH - categorie
    for cat in VEHICLE_CATEGORIES:
        if cat in msg:
            return {"intent": "SEARCH", "vehicle_ref": cat, "confidence": 80}

    # 8. CHAT par defaut
    return {"intent": "CHAT", "vehicle_ref": None, "confidence": 70}


def _extract_vehicle_ref(msg: str) -> str:
    for model in KNOWN_MODELS:
        if model in msg:
            return model
    for make in KNOWN_MAKES:
        if make in msg:
            return make
    for cat in VEHICLE_CATEGORIES:
        if cat in msg:
            return cat
    return None


def is_rdv_intent(message: str) -> bool:
    return classify(message)["intent"] == "RDV"


def is_search_intent(message: str, vehicle_shown: dict = None) -> bool:
    return classify(message, vehicle_shown)["intent"] == "SEARCH"


def is_followup_intent(message: str, vehicle_shown: dict = None) -> bool:
    return classify(message, vehicle_shown)["intent"] == "FOLLOWUP"
