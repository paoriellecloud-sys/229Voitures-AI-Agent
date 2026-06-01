# Agent Filtre Sport
Empêche les modèles sport d'apparaître dans les recherches VUS.

## Responsabilité
- Exclure Mustang, Camaro, Challenger, Corvette quand VUS demandé
- Appliquer le filtre sur cache_results ET alt_results ET chat_cache

## Fichier concerné
modules/agent_router.py — chercher "_filter_sport" ou "_SPORT_EXCLUDE"

## Règle
Ne modifier que la fonction _filter_sport et ses 4 points d'application.
