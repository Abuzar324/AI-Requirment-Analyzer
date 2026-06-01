import sys, os
# Add project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.analyzer import RequirementAnalyzer
from app.services.consistency import CrossRequirementConsistency
from app.api.analyze import calculate_risk

TESTS = [
    {
        "name": "Perfect Requirement",
        "text": "When the user clicks the 'Checkout' button, the system shall calculate the total order price including tax so that the user receives an accurate final invoice."
    },
    {
        "name": "Moderate Requirement",
        "text": "The system shall process user payments to ensure all transactions are handled securely."
    },
    {
        "name": "Broken/Conflict Requirement",
        "text": "The system must be fully offline. The system must be connected to the cloud to perform live updates."
    }
]

analyzer = RequirementAnalyzer()
consistency = CrossRequirementConsistency()

for test in TESTS:
    print(f"\n=== {test['name']} ===")
    sentences = analyzer.split_sentences(test['text'])
    analyzed = [analyzer.analyze(s) for s in sentences]
    for idx, a in enumerate(analyzed, 1):
        print(f"[Sentence {idx}] {a['text']}")
        print(f"  Completeness: {a['completeness_pct']}%")
        print(f"  Ambiguity Score: {a['ambiguity_score']}")
        if a['issues']:
            print(f"  Issues: {a['issues']}")
    conflicts = consistency.detect_conflicts(analyzed, threshold=0.70)
    print(f"Conflicts detected: {len(conflicts)}")
    for i, c in enumerate(conflicts, 1):
        print(f"  Conflict {i}: {c['conflict_description']}")
    total = len(analyzed)
    avg_amb = sum(a['ambiguity_score'] for a in analyzed) / total if total else 0.0
    avg_comp = sum(a['completeness_pct'] for a in analyzed) / total if total else 100.0
    risk = calculate_risk(avg_comp, avg_amb, len(conflicts) > 0)
    print(f"Overall risk score: {risk}\n")
