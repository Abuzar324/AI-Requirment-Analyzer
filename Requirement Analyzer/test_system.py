import os
import sys

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.security import get_password_hash, verify_password, create_access_token, decode_access_token
from app.services.analyzer import RequirementAnalyzer
from app.services.consistency import CrossRequirementConsistency

def test_security_utilities():
    print("--- 1. Testing Security Utilities ---")
    password = "SuperSecretPassword123"
    
    # Password hashing and verification
    h = get_password_hash(password)
    assert h != password, "Password should be hashed securely"
    assert verify_password(password, h) is True, "Password verification failed"
    assert verify_password("wrong_password", h) is False, "Password verification should fail for invalid passwords"
    print("✓ Password hashing & verification successful.")
    
    # JWT creation & decoding
    user_id = 42
    token = create_access_token(subject=user_id)
    subject = decode_access_token(token)
    assert subject == str(user_id), f"JWT decode failed, expected {user_id}, got {subject}"
    print("✓ JWT token creation & decoding successful.")
    print()

def test_analyzer_sentence_splitting():
    print("--- 2. Testing Sentence Splitting ---")
    analyzer = RequirementAnalyzer()
    bulk_text = "The system shall allow user login. The system must secure all databases immediately."
    sents = analyzer.split_sentences(bulk_text)
    assert len(sents) == 2, f"Expected 2 sentences, got {len(sents)}"
    assert sents[0] == "The system shall allow user login.", f"First sentence mismatch: {sents[0]}"
    print("✓ Sentence boundary parsing successful.")
    print()

def test_completeness_and_ambiguity():
    print("--- 3. Testing Completeness and Ambiguity Logic ---")
    analyzer = RequirementAnalyzer()
    
    # Test a 100% complete requirement: Actor (user), Action (export data), Condition (when authorized), Outcome (to local disk)
    req_complete = "The user shall export data when authorized to local disk."
    res_complete = analyzer.analyze(req_complete)
    
    print(f"Analyzed requirement: '{req_complete}'")
    print(f"  - Completeness: {res_complete['completeness_pct']}%")
    print(f"  - Issues: {res_complete['issues']}")
    print(f"  - Priority: {res_complete['priority']}")
    
    # Actor (user) + Action (export) + Condition (when...) + Outcome (to...) -> all 4 elements are present
    assert res_complete['completeness_pct'] == 100.0, f"Expected 100.0% completeness, got {res_complete['completeness_pct']}%"

    # Regression test for complex outcome clauses separated by purpose markers
    req_complex = "When the user is authenticated, the user shall export data so that the team can analyze reports."
    res_complex = analyzer.analyze(req_complex)
    assert res_complex['completeness_pct'] == 100.0, f"Expected 100.0% completeness for complex outcome clause, got {res_complex['completeness_pct']}%"
    
    # Test an ambiguous and incomplete requirement: missing Actor, missing Condition, missing Outcome, has vague term "user-friendly"
    req_incomplete = "Generate a user-friendly report."
    res_incomplete = analyzer.analyze(req_incomplete)
    
    print(f"Analyzed requirement: '{req_incomplete}'")
    print(f"  - Completeness: {res_incomplete['completeness_pct']}%")
    print(f"  - Ambiguity Score: {res_incomplete['ambiguity_score']}")
    print(f"  - Issues: {res_incomplete['issues']}")
    
    # Ambiguity score should be positive due to "user-friendly"
    assert res_incomplete['ambiguity_score'] > 0.0, "Expected positive ambiguity score for vague terms"
    assert "user-friendly" in res_incomplete['issues'][0], "Expected 'user-friendly' to be flagged in issues"
    
    # "Generate" is action, but missing Actor, Condition, and Outcome (25.0% completeness)
    assert res_incomplete['completeness_pct'] == 25.0, f"Expected 25.0% completeness, got {res_incomplete['completeness_pct']}%"
    print("✓ Completeness weights (25% per component) & ambiguity metrics verified.")
    print()

def test_cross_consistency():
    print("--- 4. Testing Duplicates and Conflict Rules ---")
    consistency = CrossRequirementConsistency()
    
    req_a = {"text": "The system shall allow any user to edit the file."}
    req_b = {"text": "The system shall allow users to modify the files."}
    
    # 1. Duplicates check
    dups = consistency.detect_duplicates([req_a, req_b], threshold=0.60)
    print(f"Duplicate check result: {dups}")
    assert len(dups) > 0, "Expected a duplicate warning based on semantic overlap"
    
    # 2. Conflict check (using mock rule-based logic when OpenAI key is mock/unset)
    req_c = {"text": "The system shall allow users to access files."}
    req_d = {"text": "The system shall restrict users from accessing files."}
    conflicts = consistency.detect_conflicts([req_c, req_d], threshold=0.70)
    print(f"Conflict check result: {conflicts}")
    assert len(conflicts) > 0, "Expected conflict warning (allow vs restrict)"
    print("✓ Duplicates similarity matching and conflict rules verified.")
    print()

def test_dynamic_risk_and_offline_conflict():
    print("--- 5. Testing Dynamic Risk Scoring & Offline/Online Conflict ---")
    
    # 1. Test offline vs cloud-connected detection
    consistency = CrossRequirementConsistency()
    req_offline = {"text": "The application must be completely offline."}
    req_cloud = {"text": "The application must be cloud-connected."}
    
    conflicts = consistency.detect_conflicts([req_offline, req_cloud], threshold=0.70)
    print(f"Offline/Online Conflict result: {conflicts}")
    assert len(conflicts) > 0, "Expected a conflict to be detected for mutually exclusive conditions"
    
    # 2. Test calculate_risk function (weighted formula and conflict multiplier)
    from app.api.analyze import calculate_risk
    
    # No conflicts, low ambiguity (average_ambiguity = 0.25)
    # Assume completeness 100 for this synthetic case
    risk_no_conflicts = calculate_risk(100, 0.25, False)
    print(f"Risk with 0 conflicts, 0.25 ambiguity: {risk_no_conflicts}")
    # New weighted formula: Risk = (0.25 * 0.2) + (0.0 * 0.5) + (0.0 * 0.3) = 0.05
    assert risk_no_conflicts == 0.05, f"Expected risk score of 0.05, got {risk_no_conflicts}"
    
    # With conflicts, low ambiguity
    # weighted formula with conflict multiplier jump to [0.7, 1.0]
    risk_with_conflicts = calculate_risk(100, 0.25, True)
    print(f"Risk with 1 conflict, 0.25 ambiguity: {risk_with_conflicts}")
    # New conflict penalty is 0.5 base; expect risk to be at least 0.5
    assert 0.5 <= risk_with_conflicts <= 1.0, f"Expected risk score to be in range [0.5, 1.0], got {risk_with_conflicts}"
    
    # High ambiguity, with conflicts
    risk_high_conflicts = calculate_risk(100, 0.8, True)
    print(f"Risk with 1 conflict, 0.8 ambiguity: {risk_high_conflicts}")
    assert 0.5 <= risk_high_conflicts <= 1.0, f"Expected risk score to be in range [0.5, 1.0], got {risk_high_conflicts}"
    assert risk_high_conflicts >= risk_with_conflicts, f"Expected higher or equal ambiguity to yield non-decreasing risk, got {risk_high_conflicts} < {risk_with_conflicts}"

    print("✓ Dynamic risk and offline conflict verification successful.")
    print()

if __name__ == "__main__":
    print("Starting verification checks...\n")
    try:
        test_security_utilities()
        test_analyzer_sentence_splitting()
        test_completeness_and_ambiguity()
        test_cross_consistency()
        test_dynamic_risk_and_offline_conflict()
        print("🎉 ALL TESTS PASSED SUCCESSFULLY! The core backend architecture is correct and compliant.")
    except AssertionError as e:
        print(f"❌ ASSERTION FAILED: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {str(e)}")
        sys.exit(1)
