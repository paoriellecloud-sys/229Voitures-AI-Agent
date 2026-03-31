from domain.auto_search import find_best_match
from domain.financing import generate_financing
from domain.analysis import analyze_vehicle


def process(user_input, state, inventory):

    text = user_input.lower()

    # 1. MATCH VEHICULE (FUZZY)
    if state.stage == "results":
        matched_car = find_best_match(user_input, state.last_results)

        if matched_car:
            state.selected_vehicle = matched_car
            state.stage = "interest"

            return f"""
🚗 {matched_car['title']}
💰 {matched_car['price']}$
📍 {matched_car.get('dealer', matched_car.get('dealer_name', ''))}

👉 Je peux maintenant :
1. Analyse complète du véhicule
2. Simulation financement

Que veux-tu voir ?
"""

    # 2. FINANCEMENT
    if "financement" in text:
        if state.selected_vehicle:
            state.stage = "financing"
            return f"""
{generate_financing(state.selected_vehicle)}

📞 Si tu veux, je peux te mettre en contact direct avec le concessionnaire.

👉 Donne-moi ton nom + téléphone + email
"""
        return "Sur quel véhicule veux-tu un financement ?"

    # 3. ANALYSE
    if "analyse" in text and state.selected_vehicle:
        return analyze_vehicle(state.selected_vehicle)

    # 4. CAPTURE LEAD
    if state.stage == "financing" and "@" in text:
        state.stage = "lead"
        return "Parfait 👍 Je prépare la mise en relation avec le concessionnaire."

    # 5. FALLBACK
    return None
