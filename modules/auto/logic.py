from modules.gemini_service import explain_vehicle


def ai_vehicle_expert(vehicle):

    explanation = explain_vehicle(vehicle)

    return {
        "vehicle": vehicle,
        "ai_analysis": explanation
    }

from modules.auto.repository import VehicleRepository

class VehicleRecommendationEngine:

    def __init__(self):
        self.vehicles = VehicleRepository.get_all()

    def calculate_score(self, vehicle, budget, weights):
        score = 0

        # Price proximity
        price_ratio = vehicle["price"] / budget
        if price_ratio <= 1:
            price_score = (1 - price_ratio) * 40
            score += price_score * weights["price"]

        # Year bonus
        year_score = (vehicle["year"] - 2000) * 0.5
        score += year_score * weights["year"]

        # Mileage bonus
        mileage_score = max(0, (100000 - vehicle["mileage"]) / 5000)
        score += mileage_score * weights["mileage"]

        # Consumption bonus
        consumption_score = max(0, 10 - vehicle["consumption"])
        score += consumption_score * weights["consumption"]

        return round(score, 2)

    def filter_vehicles(self, budget, fuel_type):
        filtered = []

        for vehicle in self.vehicles:
            if vehicle["price"] is not None and vehicle["price"] <= budget:

                if fuel_type:
                    if vehicle["fuel_type"].lower() != fuel_type.lower():
                        continue

                filtered.append(vehicle)

        return filtered

    def rank_vehicles(self, vehicles, budget, weights):
        scored = []

        for vehicle in vehicles:
            score = self.calculate_score(vehicle, budget, weights)
            vehicle_copy = vehicle.copy()
            vehicle_copy["score"] = score
            scored.append(vehicle_copy)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def recommend(self, budget, fuel_type, weights):
        filtered = self.filter_vehicles(budget, fuel_type)

        if not filtered:
            return []

        return self.rank_vehicles(filtered, budget, weights)


# --- CLI Layer (interface only) ---

def get_user_weights():
    print("\nRate importance from 1 (low) to 5 (high)\n")

    try:
        return {
            "price": int(input("Importance of price: ")),
            "year": int(input("Importance of year: ")),
            "mileage": int(input("Importance of mileage: ")),
            "consumption": int(input("Importance of fuel efficiency: "))
        }
    except ValueError:
        print("Invalid input. Using default weights.")
        return {
            "price": 3,
            "year": 3,
            "mileage": 3,
            "consumption": 3
        }


def recommend_vehicle():
    engine = VehicleRecommendationEngine()

    try:
        budget = float(input("Enter your maximum budget: "))
        if budget <= 0:
            print("Budget must be greater than zero.")
            return
    except ValueError:
        print("Invalid input. Please enter a numeric value.")
        return

    fuel_type = input("Preferred fuel type (Hybrid/Diesel/Electric or leave blank): ").strip()
    weights = get_user_weights()

    results = engine.recommend(budget, fuel_type, weights)

    if not results:
        print("No vehicles found matching your criteria.")
        return

    print("\nRecommended vehicles (ranked):\n")

    for vehicle in results:
        print(f"""
Score: {vehicle['score']}
Brand: {vehicle['brand']} {vehicle['model']}
Year: {vehicle['year']}
Price: ${vehicle['price']}
Fuel Type: {vehicle['fuel_type']}
Transmission: {vehicle['transmission']}
Mileage: {vehicle['mileage']} km
Consumption: {vehicle['consumption']} L/100km
Location: {vehicle['location']}
Description: {vehicle['description']}
----------------------------------------
""")
      

