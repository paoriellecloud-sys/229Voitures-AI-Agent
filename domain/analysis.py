def analyze_vehicle(car):
    analysis = []

    if car.get("km", 0) > 80000:
        analysis.append("⚠️ Kilométrage élevé → prévoir garantie")

    if car.get("price_diff", 0) > 1000:
        analysis.append("⚠️ Prix au-dessus du marché")
    elif car.get("price_diff", 0) < -1000:
        analysis.append("💰 Bon deal (sous le marché)")

    if car.get("provenance") and car["provenance"] != "QC":
        analysis.append("⚠️ Véhicule hors-province (inspection SAAQ recommandée)")

    if car.get("year", 0) <= 2018:
        analysis.append("⚠️ Véhicule plus ancien → risque entretien")

    analysis.append("✔ Vérifier CARFAX")
    analysis.append("✔ Inspection mécanique indépendante recommandée")
    analysis.append("❌ Éviter assurance prêt inutile")
    analysis.append("✔ Garantie prolongée pertinente selon usage")

    return "\n".join(analysis)
