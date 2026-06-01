import re
import json
from typing import List, Dict, Any
from openai import OpenAI
import spacy
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import settings
from app.services.analyzer import nlp

class CrossRequirementConsistency:
    def __init__(self):
        pass

    def detect_duplicates(self, requirements: List[Dict[str, Any]], threshold: float = 0.80) -> List[Dict[str, Any]]:
        """Identify potential duplicate requirements in a batch, optimized by pre-parsing SpaCy Docs."""
        duplicates = []
        n = len(requirements)
        if n == 0:
            return duplicates

        # 1. Pre-parse all sentences once to avoid O(N^2) parsing overhead
        docs = []
        tokens_list = []
        has_vectors = nlp.vocab.vectors.size > 0

        for req in requirements:
            text = req["text"]
            doc = nlp(text)
            docs.append(doc)
            
            # If falling back to Jaccard similarity (no vectors)
            if not has_vectors:
                tokens = set()
                for tok in doc:
                    if tok.is_stop or tok.is_punct or tok.is_space:
                        continue
                    lemma = tok.lemma_.lower().strip()
                    if not lemma or lemma == "-pron-":
                        continue
                    tokens.add(lemma)
                tokens_list.append(tokens)

        # 2. Compute similarity using pre-parsed objects
        for i in range(n):
            for j in range(i + 1, n):
                if has_vectors:
                    doc1 = docs[i]
                    doc2 = docs[j]
                    if doc1.vector_norm and doc2.vector_norm:
                        sim = float(doc1.similarity(doc2))
                    else:
                        sim = 0.0
                else:
                    words1 = tokens_list[i]
                    words2 = tokens_list[j]
                    if not words1 or not words2:
                        sim = 0.0
                    else:
                        sim = float(len(words1.intersection(words2)) / len(words1.union(words2)))

                if sim >= threshold:
                    duplicates.append({
                        "requirement_a": requirements[i]["text"],
                        "requirement_b": requirements[j]["text"],
                        "similarity_score": round(sim, 2)
                    })
        return duplicates

    def detect_conflicts(self, requirements: List[Dict[str, Any]], threshold: float = 0.70) -> List[Dict[str, Any]]:
        """
        Identify logical conflicts or contradictions in a batch.
        Optimized by pre-parsing Docs and running OpenAI conflict checks in parallel.
        """
        conflicts = []
        n = len(requirements)
        if n == 0:
            return conflicts
            
        # 1. Pre-parse all sentences once
        docs = []
        tokens_list = []
        has_vectors = nlp.vocab.vectors.size > 0

        for req in requirements:
            text = req["text"]
            doc = nlp(text)
            docs.append(doc)
            
            if not has_vectors:
                tokens = set()
                for tok in doc:
                    if tok.is_stop or tok.is_punct or tok.is_space:
                        continue
                    lemma = tok.lemma_.lower().strip()
                    if not lemma or lemma == "-pron-":
                        continue
                    tokens.add(lemma)
                tokens_list.append(tokens)
        
        # 2. Filter high-similarity pairs
        pairs_to_check = []
        for i in range(n):
            for j in range(i + 1, n):
                if has_vectors:
                    doc1 = docs[i]
                    doc2 = docs[j]
                    if doc1.vector_norm and doc2.vector_norm:
                        sim = float(doc1.similarity(doc2))
                    else:
                        sim = 0.0
                else:
                    words1 = tokens_list[i]
                    words2 = tokens_list[j]
                    if not words1 or not words2:
                        sim = 0.0
                    else:
                        sim = float(len(words1.intersection(words2)) / len(words1.union(words2)))

                if sim >= threshold or n <= 15:
                    pairs_to_check.append((requirements[i]["text"], requirements[j]["text"]))
        
        # If no similar pairs, skip LLM calls entirely
        if not pairs_to_check:
            return conflicts

        # 3. LLM check on the filtered pairs
        # Fallback to simple rule-based mock logic if OpenAI key is not set or placeholder
        if not settings.openai_api_key or "mock" in settings.openai_api_key or settings.openai_api_key == "your_openai_api_key_here":
            mock_conflicts = []
            for text_a, text_b in pairs_to_check:
                ta = text_a.lower()
                tb = text_b.lower()
                
                # Check for allow vs deny opposites
                has_a_allow = any(w in ta for w in ["allow", "permit", "enable", "access"])
                has_a_deny = any(w in ta for w in ["deny", "restrict", "prevent", "forbid", "only", "disable"])
                has_b_allow = any(w in tb for w in ["allow", "permit", "enable", "access"])
                has_b_deny = any(w in tb for w in ["deny", "restrict", "prevent", "forbid", "only", "disable"])
                
                # Check for offline vs online opposites
                has_a_offline = "offline" in ta
                has_a_online = any(w in ta for w in ["online", "cloud", "internet", "cloud-connected", "internet-connected", "connected to cloud", "connected to internet", "cloud-based", "internet-based"])
                has_b_offline = "offline" in tb
                has_b_online = any(w in tb for w in ["online", "cloud", "internet", "cloud-connected", "internet-connected", "connected to cloud", "connected to internet", "cloud-based", "internet-based"])
                
                # Check for encrypt vs decrypt/plain opposites
                has_a_encrypt = any(w in ta for w in ["encrypt", "secure"])
                has_a_decrypt = any(w in ta for w in ["decrypt", "plain", "unencrypted"])
                has_b_encrypt = any(w in tb for w in ["encrypt", "secure"])
                has_b_decrypt = any(w in tb for w in ["decrypt", "plain", "unencrypted"])

                conflict_desc = None
                if (has_a_allow and has_b_deny) or (has_a_deny and has_b_allow):
                    conflict_desc = "Detected opposing permissions/constraints (e.g. allow vs restrict)."
                elif (has_a_offline and has_b_online) or (has_a_online and has_b_offline):
                    conflict_desc = "Detected mutually exclusive conditions (e.g. offline vs online/cloud-connected)."
                elif (has_a_encrypt and has_b_decrypt) or (has_a_decrypt and has_b_encrypt):
                    conflict_desc = "Detected conflicting data security constraints (e.g. encrypt vs plain text/decrypt)."

                if conflict_desc:
                    mock_conflicts.append({
                        "requirement_a": text_a,
                        "requirement_b": text_b,
                        "conflict_description": conflict_desc
                    })
            return mock_conflicts

        client = OpenAI(api_key=settings.openai_api_key)
        
        def check_pair(text_a: str, text_b: str):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": (
                            "You are a requirements consistency analyzer. Evaluate if the two given requirement statements "
                            "contradict, conflict, or oppose each other logically. (e.g. one statement allows something, "
                            "while the other restricts it; or they set incompatible limits). "
                            "If a conflict exists, return a JSON object with: 'conflict': true, and 'description': (explanation of the contradiction). "
                            "If no conflict exists, return a JSON object with: 'conflict': false, and 'description': ''."
                        )},
                        {"role": "user", "content": f"Requirement A: {text_a}\nRequirement B: {text_b}"}
                    ]
                )
                result = json.loads(response.choices[0].message.content)
                if result.get("conflict"):
                    return {
                        "requirement_a": text_a,
                        "requirement_b": text_b,
                        "conflict_description": result.get("description", "Contradicting rules between requirements.")
                    }
            except Exception:
                pass
            return None

        # Execute conflict check requests concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_pair, ta, tb) for ta, tb in pairs_to_check]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    conflicts.append(res)
                
        return conflicts
