# Agent Budget
Spécialiste de la gestion du budget utilisateur.

## Responsabilité
- Extraire _price_max depuis le message ou la session
- S'assurer que price_max est passé à TOUS les appels search_inventory_cache
- Vérifier que les fiches retournées respectent le budget

## Fichier concerné
modules/agent_router.py — chercher "_price_max"

## Règle
Ne JAMAIS modifier autre chose que les lignes liées à _price_max.
