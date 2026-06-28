SPORT_MODELS = ['mustang', 'camaro', 'challenger', 'corvette', 'supra', 'brz', 'gr86']

FAMILY_KEYWORDS = [
    'famille', 'enfants', 'enfant',
    '4 enfants', '5 enfants', '6 enfants',
    '7 places', '8 places', 'minivan',
    'fourgonnette', '3e rangee', 'troisieme rangee',
    'grand format',
]

_7PLACES_MODELS = ['sorento', 'telluride', 'palisade', 'sienna', 'traverse', 'pilot', 'carnival', 'odyssey']

_VAGUE_VUS = ['vus', 'suv', 'crossover', 'vehicule', 'véhicule', 'auto', 'voiture']

_VUS_MODELS = [
    'sportage', 'sorento', 'rogue', 'rav4',
    'tucson', 'escape', 'kona', 'seltos',
    'cr-v', 'qashqai', 'murano', 'santa fe',
    'cx-5', 'tiguan', 'outlander', 'equinox'
]

_BERLINE_MODELS = [
    'civic', 'corolla', 'elantra', 'accord',
    'camry', 'mazda3', 'legacy', 'impreza',
    'sentra', 'jetta', 'golf'
]

_STOPWORDS_FR = {
    "recherche", "cherche", "trouve", "montre", "propose", "liste",
    "donne", "veux", "voudrais", "aimerais", "besoin", "occasion",
    "usagé", "usagée", "voiture", "auto", "automobile", "vehicule",
    "véhicule", "dans", "pour", "avec", "sans", "sous", "entre",
    "environ", "autour", "Quebec", "Québec", "Canada", "province",
}


def build_search_query(message: str, session: dict, query: str = None) -> str:
    _msg_lower = message.lower()

    # 7 places : forcer les modèles familiaux
    _is_7places = any(kw in _msg_lower for kw in FAMILY_KEYWORDS)
    if _is_7places:
        if not query or not any(m in (query or '').lower() for m in _7PLACES_MODELS):
            query = "sorento telluride palisade traverse sienna carnival pilot odyssey"
            print(f"[smart_chat] Famille détectée → query 7 places forcée")

    # Query vague + budget défini → élargir aux modèles VUS courants
    price_max = session.get("context", {}).get("price_max")
    if price_max and any(w in (query or '').lower() for w in _VAGUE_VUS):
        query = "rogue kona escape tucson seltos cx-5 crv rav4 forester qashqai soul niro ioniq"
        print(f"[smart_chat] Query vague + budget → élargi aux modèles VUS courants")

    return query or ''


def get_alternatives(query: str, price_max: int = None,
                     vehicle_filter: str = None,
                     exclude_models: list = None,
                     message: str = None) -> list:
    import modules.agent_router as _router

    query_lower = (query or '').lower()
    msg_lower = (message or '').lower()

    is_vus = any(w in query_lower or w in msg_lower for w in _VUS_MODELS + ['vus', 'suv'])
    is_berline = any(w in query_lower or w in msg_lower for w in _BERLINE_MODELS + ['berline'])
    is_sport = any(w in query_lower or w in msg_lower for w in SPORT_MODELS + ['sport'])

    if is_vus:
        alt_query = " ".join(_VUS_MODELS[:8])
        _category_detected = True
    elif is_berline:
        alt_query = " ".join(_BERLINE_MODELS[:8])
        _category_detected = True
    elif is_sport:
        alt_query = " ".join(SPORT_MODELS[:5])
        _category_detected = True
    else:
        alt_query = query
        _category_detected = False

    # Chercher des alternatives dans l'inventaire (mots-clés élargis)
    # B2 : si VUS, chercher plus (limit=6) pour avoir du buffer après exclusion SPORT_MODELS
    alt_results = []
    keywords_alt = [k.strip() for k in (alt_query or '').lower().split()
                    if len(k.strip()) > 2
                    and k.strip() not in {s.lower() for s in _STOPWORDS_FR}
                    and not k.strip().isdigit()]
    _kw_limit = 4 if _category_detected else 2
    _search_limit = 6 if is_vus else 3
    for kw in keywords_alt[:_kw_limit]:
        alt_results = _router.search_inventory_cache(kw, limit=_search_limit)
        if alt_results:
            print(f"[smart_chat] Alternatives trouvées pour '{kw}': {len(alt_results)}")
            break

    # Supprimer les alternatives si aucune n'est de la marque demandée
    # (uniquement hors catégorie — en mode catégorie, les alternatives sont intentionnelles)
    if alt_results and keywords_alt and not _category_detected:
        requested_kw = keywords_alt[0].lower()
        brand_present = any(
            requested_kw in ((r.get("make") or "") + " " + (r.get("title") or "")).lower()
            for r in alt_results
        )
        if not brand_present:
            print(f"[smart_chat] Alt results ({len(alt_results)}) ignorés — '{requested_kw}' absent")
            alt_results = []

    # Filtre modèles exclus (exclude_models)
    if exclude_models and alt_results:
        alt_results = [r for r in alt_results if not any(
            ex.lower() in (r.get('model', '') or r.get('modele', '')).lower()
            for ex in exclude_models
        )]

    # Filtre sport : si contexte VUS, exclure systématiquement les modèles sport
    if is_vus and alt_results:
        before = len(alt_results)
        alt_results = [r for r in alt_results if not any(
            sport in (
                (r.get('make', '') or '') + ' ' +
                (r.get('model', '') or r.get('modele', '') or '') + ' ' +
                (r.get('title', '') or '')
            ).lower()
            for sport in SPORT_MODELS
        )]
        if len(alt_results) < before:
            print(f"[smart_chat] Filtre sport VUS: {before - len(alt_results)} résultat(s) exclus")

    # Filtre berline : si contexte VUS, exclure les berlines compactes/intermédiaires
    BERLINE_EXCLUDE = ['corolla', 'civic', 'elantra', 'sentra', 'forte', 'accent',
                       'camry', 'altima', 'mazda3', 'jetta', 'golf', 'impreza', 'legacy']
    if is_vus and alt_results:
        before = len(alt_results)
        alt_results = [r for r in alt_results if not any(
            b in (r.get('model', '') or r.get('title', '')).lower()
            for b in BERLINE_EXCLUDE
        )]
        if len(alt_results) < before:
            print(f"[smart_chat] Filtre berline VUS: {before - len(alt_results)} résultat(s) exclus")

    # Filtre budget : appliquer price_max sur les alternatives
    if price_max and alt_results:
        before = len(alt_results)
        alt_results = [r for r in alt_results
                       if (r.get('price') or r.get('prix') or 0) <= price_max]
        if len(alt_results) < before:
            print(f"[smart_chat] Filtre budget {price_max}$: {before - len(alt_results)} résultat(s) exclus")

    return alt_results
