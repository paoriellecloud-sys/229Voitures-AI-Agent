"""
Logique de réponse statique professionnelle pour build_search_response.
Zéro hallucination. Adapté au contexte de 229Voitures.
"""

def build_static_response(message: str, vehicles: list, count: int) -> str:
    """
    Construit une réponse statique professionnelle adaptée au contexte.
    Zéro appel Gemini - zéro hallucination.
    """
    msg = message.lower()
    display_count = min(count, 3)

    # ── 0 résultat ──────────────────────────────────────────────────────────
    if count == 0:
        if any(w in msg for w in ['electr', 'électr', 'ev', 'bolt', 'tesla', 'ioniq']):
            return "Je n'ai pas de véhicule électrique en ce moment. Voulez-vous que je crée une alerte courriel pour vous aviser dès qu'un modèle arrive ?"
        if any(w in msg for w in ['hybride', 'hybrid', 'phev', 'plug']):
            return "Je n'ai pas de véhicule hybride disponible en ce moment. Souhaitez-vous une alerte courriel ou explorer d'autres options ?"
        if any(w in msg for w in ['luxe', 'bmw', 'mercedes', 'audi', 'lexus', 'porsche']):
            return "Je n'ai pas ce modèle de luxe en inventaire actuellement. Souhaitez-vous que je vous propose des alternatives haut de gamme disponibles ?"
        return "Je n'ai pas trouvé de véhicule correspondant à votre recherche. Voulez-vous élargir les critères ou que je crée une alerte courriel ?"

    # ── 1 résultat ──────────────────────────────────────────────────────────
    if count == 1:
        v = vehicles[0]
        dealer = v.get('dealer_name', 'un concessionnaire partenaire')
        city = v.get('city', '')
        location = f"chez {dealer}" + (f" à {city}" if city else "")
        return f"J'ai trouvé une option disponible {location}. Elle vous intéresse ?"

    # ── 2+ résultats — adapter selon le contexte ────────────────────────────

    # Budget mentionné
    if any(w in msg for w in ['budget', 'mois', 'mensuel', 'financement', 'payer', 'afford']):
        return f"Voici {display_count} véhicules qui s'inscrivent dans votre budget. Lequel vous intéresse le plus pour qu'on calcule les mensualités exactes ?"

    # Famille / espace
    if any(w in msg for w in ['famille', 'enfant', 'kids', 'bébé', 'siege', 'place', 'espace', 'grand']):
        return f"Voici {display_count} options adaptées pour une famille. Avez-vous une préférence entre un VUS ou une fourgonnette ?"

    # Électrique
    if any(w in msg for w in ['electr', 'électr', 'ev', 'bolt', 'tesla', 'ioniq', 'leaf']):
        return f"Voici {display_count} véhicules électriques disponibles. N'oubliez pas que des rabais gouvernementaux jusqu'à 4 000$ peuvent s'appliquer. Lequel vous intéresse ?"

    # Hybride / PHEV
    if any(w in msg for w in ['hybride', 'hybrid', 'phev', 'plug', 'rechargeable']):
        return f"Voici {display_count} véhicules hybrides disponibles — un bon compromis entre économie d'essence et autonomie. Lequel vous attire le plus ?"

    # Camionnette / truck
    if any(w in msg for w in ['truck', 'camion', 'pickup', 'f-150', 'ram', 'silverado', 'remorquer', 'tow']):
        return f"Voici {display_count} camionnettes disponibles. Avez-vous des besoins spécifiques en termes de capacité de remorquage ou d'usage commercial ?"

    # VUS / SUV
    if any(w in msg for w in ['vus', 'suv', 'utilitaire', '4x4', 'awd', 'intégrale']):
        return f"Voici {display_count} VUS disponibles — tous équipés pour nos hivers québécois. Lequel retient votre attention ?"

    # Première voiture / jeune
    if any(w in msg for w in ['premier', 'première', 'première voiture', 'débutant', 'jeune', '18 ans', '19 ans', '20 ans']):
        return f"Voici {display_count} options parfaites pour une première voiture — fiables et économiques. N'oubliez pas de vérifier les coûts d'assurance selon le modèle. Laquelle vous plaît ?"

    # Économique / petit budget
    if any(w in msg for w in ['économique', 'pas cher', 'abordable', 'économiser', 'petit budget']):
        return f"Voici {display_count} options abordables disponibles. Toutes sont chez nos concessionnaires partenaires Force Occasion. Laquelle vous intéresse ?"

    # Luxe
    if any(w in msg for w in ['luxe', 'premium', 'haut de gamme', 'confort', 'cuir']):
        return f"Voici {display_count} véhicules haut de gamme disponibles. Pour ce type de véhicule, je recommande particulièrement une inspection mécanique indépendante. Lequel vous intéresse ?"

    # Marque spécifique
    for make in ['toyota', 'honda', 'ford', 'hyundai', 'kia', 'mazda', 'nissan', 'chevrolet', 'dodge', 'ram', 'jeep', 'subaru', 'volkswagen', 'bmw', 'audi', 'mercedes', 'lexus']:
        if make in msg:
            make_display = make.capitalize()
            return f"Voici {display_count} {make_display} disponibles chez nos concessionnaires partenaires. Lequel vous intéresse le plus ?"

    # Défaut générique mais professionnel
    return f"Voici {display_count} véhicules qui correspondent à votre recherche. Tous sont disponibles chez nos concessionnaires partenaires Force Occasion. Lequel vous intéresse le plus ?"
