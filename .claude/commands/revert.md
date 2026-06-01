# Commande /revert
Retour au tag stable-v22 en cas de régression.

```bash
cd ~/229voitures && \
git checkout stable-v22 -- modules/agent_router.py modules/formatters.py && \
git add modules/agent_router.py modules/formatters.py && \
git commit -m "revert: retour à stable-v22" && \
git push origin main && \
sudo systemctl restart 229voitures && sleep 15
```

Après le revert, toujours relancer /test pour confirmer.
