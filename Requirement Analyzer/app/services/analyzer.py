import io
import os
import json
import re
from typing import List, Dict, Any
import spacy
from spacy.matcher import Matcher
from docx import Document
from openai import OpenAI
from PyPDF2 import PdfReader

from app.config import settings

# Load SpaCy model, with multiple fallback options to ensure no crash on startup
try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")

class RequirementAnalyzer:
    def __init__(self):
        # List of vague terms commonly found in requirements
        self.vague_terms = [
            "user-friendly", "fast", "optimized", "efficient", "flexible", 
            "scalable", "robust", "intuitive", "simple", "easy", "maximum", 
            "minimum", "quickly", "securely", "adequately", "appropriate",
            "real-time", "high-performance", "seamless", "stable"
        ]

    def split_sentences(self, text: str) -> List[str]:
        """Split a bulk text block into individual requirement sentences."""
        if not text.strip():
            return []
        doc = nlp(text)
        return [sent.text.strip() for sent in doc.sents if sent.text.strip()]

    def extract_text_from_pdf(self, file_bytes: bytes) -> str:
        """Extract text from PDF bytes."""
        stream = io.BytesIO(file_bytes)
        reader = PdfReader(stream)
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)
        text = "\n\n".join(pages_text)
        if not text.strip():
            raise ValueError("Uploaded PDF contains no extractable text.")
        return text

    def extract_text_from_docx(self, file_bytes: bytes) -> str:
        """Extract text from a Word .docx file."""
        stream = io.BytesIO(file_bytes)
        document = Document(stream)
        doc_text = [para.text for para in document.paragraphs if para.text.strip()]
        text = "\n".join(doc_text)
        if not text.strip():
            raise ValueError("Uploaded Word document contains no extractable text.")
        return text

    def extract_text_from_txt(self, file_bytes: bytes) -> str:
        """Decode plain text file contents."""
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1", errors="replace")

    def _classify_rule_based(self, text: str) -> str:
        """Categorize as FR or NFR using basic terminology heuristics."""
        text_lower = text.lower()
        nfr_keywords = [
            "security", "secure", "performance", "response time", "latency", 
            "scalable", "scaling", "backup", "recovery", "authorized", 
            "authenticate", "encrypt", "decrypt", "concurrent", "throughput", 
            "availability", "reliable", "compatibility", "maintenance"
        ]
        fr_keywords = [
            "shall", "must", "will", "should", "allows", "creates", "deletes", 
            "updates", "sends", "receives", "adds", "calculates", "generates"
        ]
        
        # Count keyword occurrences
        nfr_score = sum(1 for kw in nfr_keywords if kw in text_lower)
        fr_score = sum(1 for kw in fr_keywords if kw in text_lower)
        
        if nfr_score > fr_score:
            return "NFR"
        return "FR"

    def _split_outcome_clause(self, text: str):
        """Split the requirement into main action clause and outcome clause using common outcome triggers."""
        doc = nlp(text)
        matcher = Matcher(nlp.vocab)
        matcher.add(
            "OUTCOME_MARKER",
            [
                [{"LOWER": "so"}, {"LOWER": "that"}],
                [{"LOWER": "in"}, {"LOWER": "order"}, {"LOWER": "to"}],
                [{"LOWER": "resulting"}, {"LOWER": "in"}],
                [{"LOWER": "so"}, {"LOWER": "as"}, {"LOWER": "to"}],
                [{"LOWER": "in"}, {"LOWER": "order"}, {"LOWER": "that"}],
                [{"LOWER": "to"}, {"LOWER": "allow"}],
                [{"LOWER": "so"}, {"LOWER": "users"}, {"LOWER": "can"}],
                [{"LOWER": "so"}, {"LOWER": "the"}],
                [{"LOWER": "to"}]
            ],
            on_match=None,
        )
        matches = matcher(doc)
        if not matches:
            return text, None, None

        matches = sorted(matches, key=lambda m: (m[1], -(m[2] - m[1])))
        selected = None
        last_to = None
        for _, start, end in matches:
            marker_text = doc[start:end].text.lower()
            if marker_text == "to":
                last_to = (start, end)
                continue
            selected = (start, end)
            break
        if selected is None and last_to is not None:
            selected = last_to
        if selected is None:
            return text, None, None

        start, end = selected
        prefix_text = doc[:start].text.strip()
        suffix_text = doc[end:].text.strip()
        if not suffix_text:
            return text, None, None
        return prefix_text or text, doc[start:end].text.lower(), suffix_text

    def _detect_ambiguity(self, text: str) -> tuple[float, List[str]]:
        """Identify vague terms and calculate a score between 0.0 and 1.0."""
        text_lower = text.lower()
        found_terms = []
        
        for term in self.vague_terms:
            # Match word boundary
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text_lower):
                found_terms.append(term)
                
        vague_count = len(found_terms)
        # 0.25 ambiguity score per vague term up to 1.0
        score = min(1.0, vague_count * 0.25)
        return score, found_terms

    def _analyze_completeness(self, text: str) -> tuple[float, List[str]]:
        """
        Evaluate presence of: Actor, Action, Condition, and Expected Outcome.
        Each component has a 25% weight. Total score calculated linearly.
        """
        doc = nlp(text)
        main_clause, outcome_marker, outcome_clause_text = self._split_outcome_clause(text)
        outcome_clause = nlp(outcome_clause_text) if outcome_clause_text else None
        main_doc = nlp(main_clause) if outcome_clause_text else doc
        has_actor = False
        has_action = False
        has_condition = False
        has_outcome = False
        missing = []

        # 1. Actor Detection: look for subjects (nsubj, nsubjpass)
        subjects = [tok for tok in doc if tok.dep_ in ("nsubj", "nsubjpass")]
        if subjects:
            has_actor = True
        else:
            missing.append("Actor (Subject)")

        # 2. Action Detection: look for main clause verbs while keeping the outcome clause separate
        main_doc = nlp(main_clause) if outcome_clause is not None else doc
        root = next((tok for tok in main_doc if tok.dep_ == "ROOT"), None)
        action_token = None
        if root is not None:
            if root.pos_ in ("AUX", "VERB"):
                action_token = next(
                    (child for child in root.children if child.dep_ in ("xcomp", "ccomp") and child.pos_ == "VERB"),
                    root,
                )
            else:
                action_token = root if root.pos_ == "VERB" else None
        if action_token is None:
            action_token = next((tok for tok in main_doc if tok.pos_ == "VERB"), None)
        if action_token is not None:
            has_action = True
        else:
            missing.append("Action (Verb)")

        # 3. Condition Detection: look for prepositional modifiers, adverbial clauses, 
        # or conditional conjunctions like if, when, while, unless
        condition_conjs = {"if", "when", "while", "unless", "after", "before", "until", "whenever"}
        has_cond_word = any(tok.text.lower() in condition_conjs for tok in doc)
        has_advcl = any(tok.dep_ == "advcl" for tok in doc)
        has_mark = any(tok.dep_ == "mark" and tok.text.lower() in condition_conjs for tok in doc)
        if has_cond_word or has_advcl or has_mark:
            has_condition = True
        else:
            missing.append("Condition (if/when context)")

        # 4. Expected Outcome Detection: look for outcome trigger clauses, subordinate purposes, or result objects.
        text_lower = text.lower()
        has_outcome_phrase = outcome_clause is not None or any(
            phrase in text_lower for phrase in ["so that", "in order to", "resulting in", "results in", "to allow", "such that"]
        )
        if has_outcome_phrase:
            has_outcome = True
        else:
            missing.append("Expected Outcome")

        # Linear arithmetic calculation (25% weight per component)
        score = 0.0
        if has_actor: score += 25.0
        if has_action: score += 25.0
        if has_condition: score += 25.0
        if has_outcome: score += 25.0

        return score, missing

    def _determine_priority(self, text: str) -> str:
        """Assign MoSCoW priority based on key modal verbs."""
        text_lower = text.lower()
        
        # Must Have: shall, must, critical, mandatory
        if any(w in text_lower for w in ["must", "shall", "critical", "mandatory"]):
            return "Must Have"
        # Should Have: should, expected, important
        elif any(w in text_lower for w in ["should", "expected", "important"]):
            return "Should Have"
        # Could Have: could, may, optional, nice-to-have
        elif any(w in text_lower for w in ["could", "may", "optional", "nice to have", "nice-to-have"]):
            return "Could Have"
        # Won't Have: won't, will not, exclude, future
        elif any(w in text_lower for w in ["won't", "will not", "exclude", "future"]):
            return "Won't Have"
            
        # Default
        return "Should Have"

    def _call_llm_suggestions(self, text: str, rule_category: str, rule_priority: str, rule_issues: List[str]) -> Dict[str, Any]:
        """Query OpenAI API using gpt-4o-mini to refine classification and generate suggestions."""
        # Fallback to local rule-based results if OpenAI key is not set or placeholder
        if not settings.openai_api_key or "mock" in settings.openai_api_key or settings.openai_api_key == "your_openai_api_key_here":
            # Generate a standard templates fallback suggestion
            suggested_text = f"As a [User], I want to be able to {text.lower()} so that [Expected Outcome]."
            return {
                "category": rule_category,
                "priority": rule_priority,
                "issues": rule_issues,
                "suggestion": suggested_text
            }

        client = OpenAI(api_key=settings.openai_api_key)
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": (
                        "You are an expert requirements engineer. Analyze the following software requirement. "
                        "Determine if it is a Functional Requirement (FR) or Non-Functional Requirement (NFR). "
                        "Provide a recommended MoSCoW priority (Must Have, Should Have, Could Have, Won't Have). "
                        "List specific issues with the requirement (e.g. ambiguity, lack of details, missing actor). "
                        "Provide a rewritten, clear, measurable, and structured version of the requirement "
                        "using the standard format: 'As a [Actor], I want [Action] so that [Outcome]'. "
                        "Return ONLY a JSON object with keys: 'category', 'priority', 'issues' (list of strings), and 'suggestion' (string)."
                    )},
                    {"role": "user", "content": f"Requirement: {text}"}
                ]
            )
            result = json.loads(response.choices[0].message.content)
            return {
                "category": result.get("category", rule_category),
                "priority": result.get("priority", rule_priority),
                "issues": result.get("issues", rule_issues),
                "suggestion": result.get("suggestion", "")
            }
        except Exception as e:
            # Fallback in case of API error
            return {
                "category": rule_category,
                "priority": rule_priority,
                "issues": rule_issues + [f"LLM parsing error: {str(e)}"],
                "suggestion": f"As a [User], I want to be able to {text.lower()} so that [Expected Outcome]."
            }

    def analyze(self, text: str) -> Dict[str, Any]:
        """Perform full analysis pipeline on a single requirement sentence."""
        # 1. Rule-based checks
        rule_category = self._classify_rule_based(text)
        ambiguity_score, vague_terms = self._detect_ambiguity(text)
        completeness_pct, missing_components = self._analyze_completeness(text)
        rule_priority = self._determine_priority(text)
        
        # Accumulate issues
        issues = []
        if vague_terms:
            issues.append(f"Ambiguous terms detected: {', '.join(vague_terms)}")
        if missing_components:
            issues.append(f"Missing structural elements: {', '.join(missing_components)}")
            
        # 2. LLM enrichment & suggestion rewriting
        llm_data = self._call_llm_suggestions(text, rule_category, rule_priority, issues)
        
        # Return merged result
        return {
            "text": text,
            "category": llm_data.get("category", rule_category),
            "ambiguity_score": ambiguity_score,
            "completeness_pct": completeness_pct,
            "issues": llm_data.get("issues", issues),
            "suggestions": llm_data.get("suggestion", ""),
            "priority": llm_data.get("priority", rule_priority)
        }

    def _call_llm_suggestions_batch(self, batch_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Query OpenAI API in a single batch to analyze multiple requirements at once."""
        # Fallback to local rule-based results if OpenAI key is not set or placeholder
        if not settings.openai_api_key or "mock" in settings.openai_api_key or settings.openai_api_key == "your_openai_api_key_here":
            results = []
            for item in batch_items:
                results.append({
                    "category": item["rule_category"],
                    "priority": item["rule_priority"],
                    "issues": item["rule_issues"],
                    "suggestion": f"As a [User], I want to be able to {item['text'].lower()} so that [Expected Outcome]."
                })
            return results

        client = OpenAI(api_key=settings.openai_api_key)
        try:
            # Prepare inputs for the batch
            prompt_items = []
            for idx, item in enumerate(batch_items):
                prompt_items.append({
                    "index": idx,
                    "text": item["text"],
                    "rule_category": item["rule_category"],
                    "rule_priority": item["rule_priority"],
                    "rule_issues": item["rule_issues"]
                })
                
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": (
                        "You are an expert requirements engineer. Analyze the list of software requirements provided in the JSON array. "
                        "For each requirement: "
                        "1. Determine if it is a Functional Requirement (FR) or Non-Functional Requirement (NFR). "
                        "2. Provide a recommended MoSCoW priority (Must Have, Should Have, Could Have, Won't Have). "
                        "3. List specific issues (e.g. ambiguity, lack of details, missing actor). You can include the rule-based issues provided. "
                        "4. Provide a rewritten, clear, measurable, and structured version using the standard format: 'As a [Actor], I want [Action] so that [Outcome]'. "
                        "Return a JSON object containing a 'results' key with an array of objects. Each object must have keys: "
                        "'index' (integer matching input index), 'category' (string), 'priority' (string), 'issues' (list of strings), and 'suggestion' (string)."
                    )},
                    {"role": "user", "content": json.dumps({"requirements": prompt_items})}
                ]
            )
            
            content = json.loads(response.choices[0].message.content)
            results_list = content.get("results", [])
            
            # Map them back by index to ensure correct order
            mapped_results = {}
            for r in results_list:
                idx = r.get("index")
                if idx is not None:
                    mapped_results[int(idx)] = {
                        "category": r.get("category"),
                        "priority": r.get("priority"),
                        "issues": r.get("issues"),
                        "suggestion": r.get("suggestion", "")
                    }
                    
            final_results = []
            for idx, item in enumerate(batch_items):
                res = mapped_results.get(idx)
                if res:
                    final_results.append({
                        "category": res.get("category") or item["rule_category"],
                        "priority": res.get("priority") or item["rule_priority"],
                        "issues": res.get("issues") or item["rule_issues"],
                        "suggestion": res.get("suggestion") or f"As a [User], I want to be able to {item['text'].lower()} so that [Expected Outcome]."
                    })
                else:
                    final_results.append({
                        "category": item["rule_category"],
                        "priority": item["rule_priority"],
                        "issues": item["rule_issues"],
                        "suggestion": f"As a [User], I want to be able to {item['text'].lower()} so that [Expected Outcome]."
                    })
            return final_results
            
        except Exception as e:
            final_results = []
            for item in batch_items:
                final_results.append({
                    "category": item["rule_category"],
                    "priority": item["rule_priority"],
                    "issues": item["rule_issues"] + [f"LLM batch parsing error: {str(e)}"],
                    "suggestion": f"As a [User], I want to be able to {item['text'].lower()} so that [Expected Outcome]."
                })
            return final_results

    def analyze_batch(self, sentences: List[str]) -> List[Dict[str, Any]]:
        """Perform full analysis pipeline on a list of requirement sentences in a single optimized batch."""
        if not sentences:
            return []
            
        # 1. Perform rule-based checks locally
        batch_items = []
        for text in sentences:
            rule_category = self._classify_rule_based(text)
            ambiguity_score, vague_terms = self._detect_ambiguity(text)
            completeness_pct, missing_components = self._analyze_completeness(text)
            rule_priority = self._determine_priority(text)
            
            issues = []
            if vague_terms:
                issues.append(f"Ambiguous terms detected: {', '.join(vague_terms)}")
            if missing_components:
                issues.append(f"Missing structural elements: {', '.join(missing_components)}")
                
            batch_items.append({
                "text": text,
                "rule_category": rule_category,
                "ambiguity_score": ambiguity_score,
                "completeness_pct": completeness_pct,
                "rule_priority": rule_priority,
                "rule_issues": issues
            })
            
        # 2. Query the LLM once in batch for all suggestions
        llm_results = self._call_llm_suggestions_batch(batch_items)
        
        # 3. Merge LLM suggestions back with local scores
        merged_results = []
        for idx, item in enumerate(batch_items):
            llm_data = llm_results[idx]
            merged_results.append({
                "text": item["text"],
                "category": llm_data.get("category", item["rule_category"]),
                "ambiguity_score": item["ambiguity_score"],
                "completeness_pct": item["completeness_pct"],
                "issues": llm_data.get("issues", item["rule_issues"]),
                "suggestions": llm_data.get("suggestions") or llm_data.get("suggestion", ""),
                "priority": llm_data.get("priority", item["rule_priority"])
            })
            
        return merged_results

