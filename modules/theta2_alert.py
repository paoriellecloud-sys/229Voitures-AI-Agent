"""
Theta II Alert — détecte les véhicules Kia/Hyundai couverts par la garantie
étendue moteur issue du recours collectif canadien sur le moteur Theta II GDI.

Véhicules visés : Kia Sportage/Sorento et Hyundai Tucson/Santa Fe, 2011-2019,
équipés du moteur Theta II 2.0L ou 2.4L GDI (pas le 1.6T ni le 3.3L/3.8L).

Couverture : 200 000 km (recours collectif Canada, jugement 2021-2023).
"""

# ── Critères de couverture ───────────────────────────────────────────────────

_THETA2_MAKES_MODELS = {
    "kia":     ["sportage", "sorento"],
    "hyundai": ["tucson", "santa fe", "santafe", "santa-fe"],
}

_THETA2_YEARS = set(range(2011, 2020))  # 2011–2019 inclus

# Moteurs Theta II visés (cylindrée exprimée dans le champ engine)
_THETA2_ENGINE_MARKERS = ["2.0", "2.4"]

# Moteurs HORS portée (ne pas déclencher l'alerte)
_EXCLUDE_ENGINE_MARKERS = ["1.6", "1.4", "3.3", "3.8", "2.5", "2.2"]


# ── Fonctions ────────────────────────────────────────────────────────────────

def is_theta2_vehicle(make: str, model: str, year: int) -> bool:
    """
    Retourne True si le véhicule correspond aux critères du moteur Theta II
    (marque, modèle, année) indépendamment du moteur exact.
    """
    make_l  = (make or "").lower()
    model_l = (model or "").lower()
    try:
        yr = int(year)
    except (ValueError, TypeError):
        return False

    if yr not in _THETA2_YEARS:
        return False

    for mfr, models in _THETA2_MAKES_MODELS.items():
        if mfr in make_l and any(m in model_l for m in models):
            return True
    return False


def _engine_is_theta2(engine_str: str) -> bool | None:
    """
    Analyse la chaîne moteur et retourne :
      True  → moteur Theta II confirmé (2.0L ou 2.4L)
      False → moteur hors portée confirmé
      None  → indéterminé (champ vide ou ambiguë)
    """
    if not engine_str or engine_str in ("N/D", ""):
        return None
    e = engine_str.lower()
    if any(m in e for m in _EXCLUDE_ENGINE_MARKERS):
        return False
    if any(m in e for m in _THETA2_ENGINE_MARKERS):
        return True
    return None


def get_theta2_alert(vehicle: dict) -> str | None:
    """
    Retourne le texte de l'alerte Theta II si applicable, sinon None.

    - Alerte verte  (✅) : moteur Theta II confirmé → couvert par la garantie étendue
    - Alerte orange (⚠️) : véhicule dans la plage mais moteur non confirmé
    - None         : véhicule hors portée
    """
    make  = vehicle.get("make")  or vehicle.get("marque") or ""
    model = vehicle.get("model") or vehicle.get("modele") or ""
    engine = str(
        vehicle.get("engine") or vehicle.get("moteur") or ""
    ).strip()
    try:
        year = int(vehicle.get("year") or vehicle.get("annee") or 0)
    except (ValueError, TypeError):
        year = 0

    if not is_theta2_vehicle(make, model, year):
        return None

    engine_status = _engine_is_theta2(engine)

    if engine_status is True:
        return (
            "✅ Ce véhicule est couvert par la garantie étendue moteur "
            "Kia/Hyundai jusqu'à 200 000 km "
            "(recours collectif Canada — moteur Theta II GDI)"
        )
    elif engine_status is False:
        # Hors portée (ex : Sportage 1.6T) — pas d'alerte
        return None
    else:
        # Moteur indéterminé → alerte prudence orange
        return (
            "⚠️ Moteur Theta II possible — demander l'historique "
            "d'entretien huile moteur au concessionnaire. "
            "Garantie étendue jusqu'à 200 000 km si moteur 2.0L ou 2.4L GDI."
        )
