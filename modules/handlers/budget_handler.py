import re

_SPORT_EXCLUDE = ['mustang', 'camaro', 'challenger', 'corvette', 'supra', 'brz', 'gr86']
_VUS_KEYWORDS = ['vus', 'suv', 'rogue', 'kona', 'escape', 'tucson', 'rav4', 'cr-v', 'seltos', 'sportage']


def extract_price_max(message: str, session: dict) -> int | None:
    _price_match = re.search(
        r'(?:sous|moins de|budget|max|maximum)[^0-9]{0,30}'
        r'(\d[\d\s]{1,})\s*(?:\$|dollars?)?',
        message.lower()
    )
    if not _price_match:
        _price_match = re.search(
            r'(\d[\d\s]{1,})\s*\$?\s*(?:/mois|par mois)',
            message.lower()
        )
    _price_max = int(_price_match.group(1).replace(' ', '')) if _price_match else None

    _monthly_keywords = ['/mois', 'par mois', 'mensuel', 'mensuellement', 'par semaine']
    _is_monthly = any(kw in message.lower() for kw in _monthly_keywords)
    if _is_monthly and _price_max and _price_max < 2000:
        _r = 0.0799 / 12
        _n = 72
        _price_total = _price_max * (1 - (1 + _r) ** -_n) / _r
        _price_max = round(_price_total / 1.14975)
        if _price_match:
            print(f"[smart_chat] Budget mensuel {_price_match.group(1).strip()}$/mois → prix total estimé {_price_max}$")

    _tout_inclus_keywords = ['tout inclus', 'taxes incluses', 'taxes comprises', 'toutes taxes', 'ttc', 'tout compris']
    if any(kw in message.lower() for kw in _tout_inclus_keywords):
        if _price_max:
            _price_max = round(_price_max / 1.14975)
            print(f"[smart_chat] Budget tout inclus → prix avant taxes estimé {_price_max}$")

    if not _price_max:
        _price_max = session.get("context", {}).get("price_max")
        if _price_max:
            print(f"[smart_chat] price_max récupéré depuis session context: {_price_max}$")

    # Fix B3 : fallback sur user_data.budget converti (budget mensuel sauvegardé tour précédent)
    if not _price_max:
        _ud_budget = session.get("user_data", {}).get("budget")
        if _ud_budget:
            _ud_budget = float(_ud_budget)
            if _ud_budget < 2000:
                _r = 0.0799 / 12
                _n = 72
                _price_total = _ud_budget * (1 - (1 + _r) ** -_n) / _r
                _price_max = round(_price_total / 1.14975)
                print(f"[budget] price_max depuis user_data.budget {_ud_budget}$/mois → {_price_max}$")
            else:
                _price_max = int(_ud_budget)
                print(f"[budget] price_max depuis user_data.budget (comptant) → {_price_max}$")

    if _price_max:
        session["context"]["price_max"] = _price_max

    return _price_max


def enforce_budget(results: list, price_max: int, query: str = None) -> list:
    if not results:
        return results
    if price_max:
        results = [r for r in results if (r.get('price') or 0) <= price_max]
    _vus_requested = any(w in (query or '').lower() for w in _VUS_KEYWORDS)
    if _vus_requested:
        results = [r for r in results if not any(
            s in (r.get('model', '') or r.get('modele', '')).lower()
            for s in _SPORT_EXCLUDE)]
    return results


def budget_unavailable_response(query: str, price_max: int, vehicle_filter: str = None) -> dict | None:
    import modules.agent_router as _router
    cheapest = _router.search_inventory_cache(query or vehicle_filter or '', limit=1)
    if not cheapest:
        return None
    v = cheapest[0]
    label = query or vehicle_filter or 'véhicule'
    return {
        "intent": "SEARCH",
        "response": (
            f"Je n'ai pas de {label} dans ton budget de {price_max:,}$ en ce moment. "
            f"Le moins cher disponible est un {v.get('year', '')} {v.get('make', '')} {v.get('model', '')} "
            f"à {v.get('price', 0):,.0f}$.\n\n"
            "Tu veux plus d'infos ou explorer d'autres options ?"
        ),
        "_html_cards": "",
        "urls_found": [],
        "scraped_count": 0,
        "source": "budget_unavailable",
    }
