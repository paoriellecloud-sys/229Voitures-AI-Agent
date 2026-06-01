# 229Voitures AI Agent — Règles Claude Code

## PROJET
- Stack : FastAPI + Gemini 2.5 Flash, SQLite, Oracle Cloud Ubuntu 22.04
- Service : 229voitures (systemd)
- IP : 148.116.73.158
- GitHub : paoriellecloud-sys/229Voitures-AI-Agent, branche main

## RÈGLES ABSOLUES
1. JAMAIS modifier tests/ sauf correction de bug dans le dispatcher
2. TOUJOURS lancer les tests avant de commiter
3. Score minimum 18/20 avant tout push
4. Si score régresse → git revert immédiatement
5. Un bug à la fois — jamais plusieurs fixes dans le même commit
6. JAMAIS modifier agent_router.py et formatters.py dans le même commit

## TAGS STABLES
- stable-v21 : 8e87b54 — baseline 19/20
- stable-v22 : tag actuel — 19/20 + filtres sport + NHTSA VIN
- En cas de régression : git checkout stable-v22 -- modules/agent_router.py

## COMMANDES DISPONIBLES
- /test  : lancer test_comportements_critiques.py
- /deploy : restart service + test
- /revert : retour à stable-v22

## FICHIERS SENSIBLES (modifier avec précaution)
- modules/agent_router.py : 3000+ lignes, très fragile
- modules/formatters.py : génération HTML VIN et fiches
- tests/test_comportements_critiques.py : ne pas modifier les lambdas

## MODULES SPÉCIALISÉS
- memory_agent.py : persistance SQLite sessions
- coherence_agent.py : résolution références propositions  
- vin_decoder.py : décodage NHTSA + alertes Theta II
- comparator_agent.py : comparaison véhicules (pas encore intégré)
- validation_agent.py : filtre budget (pas encore intégré - trop agressif)
