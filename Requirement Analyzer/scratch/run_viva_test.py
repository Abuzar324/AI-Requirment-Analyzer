import sys
import os

# Add root folder to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.services.analyzer import RequirementAnalyzer
from app.services.consistency import CrossRequirementConsistency
from app.api.analyze import calculate_risk

def run_viva_demo():
    print("======================================================================")
    print("        🚀 RUNNING VIVA DEMO PROMPT THROUGH ANALYSIS PIPELINE         ")
    print("======================================================================\n")
    
    text = (
        "The system must operate in a strictly offline environment to ensure data sovereignty. "
        "The system shall provide real-time updates to all users via a public cloud-based dashboard. "
        "The application is required to grant full read/write access to all guest users without authentication. "
        "The system must restrict all file modifications to authorized administrators only."
    )
    
    print("👉 INPUT PROMPT:")
    print(text)
    print("\n----------------------------------------------------------------------")
    print("1. SENTENCE SPLITTING & CHARACTERISTICS ANALYSIS")
    print("----------------------------------------------------------------------")
    
    analyzer = RequirementAnalyzer()
    consistency = CrossRequirementConsistency()
    
    sentences = analyzer.split_sentences(text)
    analyzed_list = []
    
    for idx, sent in enumerate(sentences, 1):
        res = analyzer.analyze(sent)
        analyzed_list.append(res)
        print(f"\n[Sentence {idx}]: \"{res['text']}\"")
        print(f"  - Category: {res['category']}")
        print(f"  - Priority: {res['priority']}")
        print(f"  - Completeness: {res['completeness_pct']}%")
        print(f"  - Ambiguity Score: {res['ambiguity_score']}")
        if res['issues']:
            print(f"  - Issues Detected: {res['issues']}")
            
    print("\n----------------------------------------------------------------------")
    print("2. CONSISTENCY & LOGICAL CONFLICT DETECTION")
    print("----------------------------------------------------------------------")
    
    conflicts = consistency.detect_conflicts(analyzed_list, threshold=0.70)
    
    if conflicts:
        print(f"🔥 {len(conflicts)} CONFLICT(S) IDENTIFIED:")
        for idx, c in enumerate(conflicts, 1):
            print(f"\n  [Conflict {idx}]:")
            print(f"    Req A: \"{c['requirement_a']}\"")
            print(f"    Req B: \"{c['requirement_b']}\"")
            print(f"    Description: {c['conflict_description']}")
    else:
        print("✅ No conflicts identified.")
        
    print("\n----------------------------------------------------------------------")
    print("3. OVERALL RISK SCORING")
    print("----------------------------------------------------------------------")
    
    total_count = len(analyzed_list)
    average_ambiguity = sum(r['ambiguity_score'] for r in analyzed_list) / total_count if total_count > 0 else 0.0
    average_completeness = sum(r['completeness_pct'] for r in analyzed_list) / total_count if total_count > 0 else 100.0

    overall_risk_score = calculate_risk(average_completeness, average_ambiguity, len(conflicts) > 0)
    
    print(f"📊 Metrics:")
    print(f"  - Total Requirements Checked: {total_count}")
    print(f"  - Average Ambiguity Score: {average_ambiguity:.2f}")
    print(f"  - Number of Active Conflicts: {len(conflicts)}")
    print(f"  - FINAL OVERALL SYSTEM RISK SCORE: {overall_risk_score} (Range: 0.0 - 1.0)")
    
    print("\n======================================================================")

if __name__ == "__main__":
    run_viva_demo()
