"""
Validation Agent — valide et filtre les réponses avant envoi à l'utilisateur.
"""
import re

_SPORT_MODELS = ["mustang", "camaro", "challenger", "corvette"]

_PRICE_PATTERN = re.compile(r'\b(\d{2})\s*(\d{3})\b')


def _extract_prices(html: str) -> list[int]:
    """Extrait tous les prix 5-chiffres depuis le HTML."""
    return [int(m.group(1) + m.group(2)) for m in _PRICE_PATTERN.finditer(html)]


def validate_budget(html_cards: str, price_max: int) -> bool:
    """
    Retourne False si au moins un prix dans html_cards dépasse price_max.
    Retourne True si html_cards est vide ou tous les prix sont dans le budget.
    """
    if not html_cards:
        return True
    prices = _extract_prices(html_cards)
    if not prices:
        return True
    return all(p <= price_max for p in prices)


def filter_cards_by_budget(html_cards: str, price_max: int) -> str:
    """
    Supprime du HTML les blocs de proposition dont le prix dépasse price_max.
    Retourne le HTML filtré (ou l'original si aucune carte n'est hors budget).
    """
    if not html_cards or validate_budget(html_cards, price_max):
        return html_cards

    # Découper par blocs de proposition (séparateur courant dans le projet)
    blocks = re.split(r'(?=<div[^>]*class=["\'][^"\']*card[^"\']*["\'])', html_cards)
    filtered = []
    for block in blocks:
        prices = _extract_prices(block)
        if not prices or all(p <= price_max for p in prices):
            filtered.append(block)
        else:
            print(f"[validation_agent] Carte supprimée — prix hors budget: {prices} > {price_max}$")

    return "".join(filtered)


def validate_category(html_cards: str, requested_category: str) -> bool:
    """
    Retourne False si un modèle sport est détecté dans html_cards
    alors que l'utilisateur a demandé la catégorie 'vus'.
    """
    if not html_cards or requested_category.lower() != "vus":
        return True
    html_lower = html_cards.lower()
    for model in _SPORT_MODELS:
        if model in html_lower:
            print(f"[validation_agent] Modèle sport détecté dans réponse VUS: {model}")
            return False
    return True
