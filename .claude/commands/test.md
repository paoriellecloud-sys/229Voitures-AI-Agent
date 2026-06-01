# Commande /test
Lance les tests critiques et affiche le score.

```bash
cd ~/229voitures && \
source venv/bin/activate && \
python3 tests/test_comportements_critiques.py 2>&1 | \
grep -E "SCORE GLOBAL|✅|❌ B|FAIL|OK"
```

Si SCORE GLOBAL < 18/20 → identifier le FAIL et corriger avant tout push.
