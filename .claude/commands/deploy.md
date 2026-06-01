# Commande /deploy
Redémarre le service et lance les tests.

```bash
cd ~/229voitures && \
sudo systemctl restart 229voitures && \
sleep 15 && \
source venv/bin/activate && \
python3 tests/test_comportements_critiques.py 2>&1 | \
grep -E "SCORE GLOBAL|FAIL"
```

Score attendu : 18-19/20.
Si régression → lancer /revert immédiatement.
