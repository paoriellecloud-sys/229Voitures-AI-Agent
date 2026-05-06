import sys
import os
sys.path.insert(0, '/home/ubuntu/229voitures')
os.chdir('/home/ubuntu/229voitures')

from modules.agent_router import detect_intent

TESTS = [
    ("parle moi des Acura", "CHAT"),
    ("c'est quoi la Volkswagen Jetta?", "CHAT"),
    ("les Honda sont-elles fiables?", "CHAT"),
    ("l'histoire de Volkswagen", "CHAT"),
    ("différence entre Kia et Hyundai", "CHAT"),
    ("Volkswagen a été créée quand?", "CHAT"),
    ("Tesla vs Toyota lequel est mieux?", "CHAT"),
    ("les problèmes du CR-V 2019?", "CHAT"),
    ("que penses-tu du RAV4?", "CHAT"),
    ("comment se fait-il que la Jetta a autant de km?", "CHAT"),
    ("as-tu des Acura?", "SEARCH"),
    ("je cherche une Acura", "SEARCH"),
    ("montre-moi des Honda", "SEARCH"),
    ("trouve-moi un RAV4", "SEARCH"),
    ("j'aimerais voir des Civic", "SEARCH"),
    ("aurais-tu des Kona?", "SEARCH"),
    ("je veux un Sorento sous 30 000$", "SEARCH"),
    ("le premier m'intéresse", "FOLLOWUP"),
    ("celui-là me plaît", "FOLLOWUP"),
    ("parle moi de celui-là", "FOLLOWUP"),
]

def main():
    print("=== TEST DETECT_INTENT ===\n")
    passed = 0
    failed = 0
    for message, expected in TESTS:
        result = detect_intent(message, {})
        intent = result.get("intent", "?")
        if intent == expected:
            passed += 1
            print(f"  [OK]   {expected} | {message}")
        else:
            failed += 1
            print(f"  [FAIL] {expected} → {intent} | {message}")
    print(f"\nRÉSULTAT : {passed}/{len(TESTS)}")

if __name__ == "__main__":
    main()
