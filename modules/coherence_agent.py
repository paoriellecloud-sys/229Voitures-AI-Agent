"""
Coherence Agent — résout les références à des propositions passées.
"""
import re

_ORDINAL_MAP = {
    "premier": 1, "première": 1, "1er": 1, "1ère": 1, "1": 1,
    "deuxième": 2, "deuxieme": 2, "second": 2, "2e": 2, "2": 2,
    "troisième": 3, "troisieme": 3, "3e": 3, "3": 3,
}

_PROXIMITY_KEYWORDS = [
    "celui-là", "celui-la", "ce véhicule", "ce vehicule",
    "l'autre", "l autre", "celui-ci", "ce dernier",
]


def resolve_reference(message: str, session: dict) -> dict | None:
    """
    Détecte si le message fait référence à une proposition passée et retourne
    le véhicule correspondant depuis session["context"]["last_results"].

    Retourne None si aucune référence n'est détectée ou si last_results est vide.
    """
    last_results = session.get("context", {}).get("last_results", [])
    if not last_results:
        return None

    msg = message.lower().strip()

    # Cherche un ordinal explicite ("le deuxième", "proposition 2", "#3", etc.)
    for token, index in _ORDINAL_MAP.items():
        pattern = rf'(?:proposition\s*|#\s*|le\s+|la\s+)?{re.escape(token)}\b'
        if re.search(pattern, msg):
            if index <= len(last_results):
                return last_results[index - 1]

    # Cherche un chiffre brut après "proposition" ou "#"
    match = re.search(r'(?:proposition\s*|#\s*)(\d+)', msg)
    if match:
        index = int(match.group(1))
        if 1 <= index <= len(last_results):
            return last_results[index - 1]

    # Cherche un mot de proximité ("celui-là", "ce véhicule", etc.)
    for kw in _PROXIMITY_KEYWORDS:
        if kw in msg:
            # Retourne le dernier véhicule montré comme référence implicite
            return last_results[-1]

    return None
