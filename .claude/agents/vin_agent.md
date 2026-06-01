# Agent VIN
Spécialiste du décodage et rapport VIN.

## Responsabilité  
- Décoder les VIN via NHTSA API
- Afficher moteur, traction, transmission
- Afficher alertes Theta II (Kia/Hyundai 2011-2019)
- Afficher liens Transports Canada

## Fichiers concernés
- modules/vin_decoder.py
- modules/formatters.py (fonction generate_vin_report)

## Règle
Ne JAMAIS modifier agent_router.py pour les bugs VIN.
Toujours corriger dans vin_decoder.py ou formatters.py.
