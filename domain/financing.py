from math import pow

TPS = 0.05
TVQ = 0.09975


def calculate_total_with_tax(price: float) -> float:
    return round(price * (1 + TPS + TVQ), 2)


def estimate_payment(amount, rate=7.99, months=72):
    monthly_rate = rate / 100 / 12
    return round(
        (amount * monthly_rate) / (1 - pow(1 + monthly_rate, -months)), 2
    )


def generate_financing(car):
    base_price = car["price"]
    total_price = calculate_total_with_tax(base_price)
    payment = estimate_payment(total_price)

    return f"""
💰 Financement estimé (QC)

• Prix affiché : {base_price}$
• Prix avec taxes (TPS + TVQ) : {total_price}$
• Paiement estimé : ~{payment}$/mois (72 mois)

📊 Détails taxes :
• TPS (5%) + TVQ (9.975%)

⚠️ À surveiller :
❌ Assurance prêt souvent inutile
❌ Produits esthétiques (marge élevée)

✔ Recommandé :
✔ Garantie prolongée adaptée au km

👉 Veux-tu voir une simulation sur 60 mois ou avec mise de fonds ?
"""
