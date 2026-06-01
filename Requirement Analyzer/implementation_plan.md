# Implementation Plan - AI Requirement Analyzer & Authentication System

This plan outlines the architecture, database schema, authentication system, core NLP and Large Language Model (LLM) analysis pipeline, and API endpoints for the **AI Requirement Analyzer** application.

---

## User Review Required

> [!IMPORTANT]
> 1. **GenAI / LLM Integration**: We will use the `openai` SDK (`gpt-4o-mini`) for generating requirements rewrite suggestions and detecting logic conflicts. You will need to provide an `OPENAI_API_KEY` in the environment `.env` file.
> 2. **SpaCy Embeddings**: We will use SpaCy's medium English model (`en_core_web_md`) because it includes word vector embeddings needed for duplicate detection. We will implement fallback loading to `en_core_web_sm` (without vectors) or basic TF-IDF if the medium model isn't installed.
> 3. **Password Hashing Security**: We'll use `passlib[bcrypt]` for secure hashing. Note that `passlib` has minor deprecation warnings in Python 3.10+ due to modern hash protocols but is standard and secure for this setup.
> 4. **On-the-Fly Preview Option**: In alignment with SRS Appendix B (data retention constraints), all analysis runs can be executed in an unsaved interactive preview state (`persist=False` or `save_to_db=False`) where nothing is saved, or optionally committed to permanent storage (`persist=True` / "Save to Dashboard").

## Decisions & Config Parameters

- **LLM Model**: `gpt-4o-mini` (configured for native JSON schema validation/Structured Outputs).
- **Access Token Expiration**: `60` minutes (providing session stability during presentations and reviews).

---

## Proposed Changes

We will create a structured, modular FastAPI codebase in the workspace directory.

### Directory Structure

```
d:/Requirement Analyzer/
├── app/
│   ├── __init__.py
│   ├── main.py            # Application initialization & startup
│   ├── config.py          # Configuration management via Pydantic Settings
│   ├── database.py        # SQLAlchemy engine and session setup
│   ├── security.py        # JWT generation & password hashing utilities
│   ├── models/            # SQLAlchemy database models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── requirement.py
│   ├── schemas/           # Pydantic data schemas
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   └── requirement.py
│   ├── api/               # API Router and endpoint functions
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   └── analyze.py
│   └── services/          # Business logic engines
│       ├── __init__.py
│       ├── analyzer.py    # RequirementAnalyzer pipeline
│       └── consistency.py # Cross-requirement duplicate/conflict detector
├── requirements.txt       # Dependencies
└── .env                   # Local settings and secrets
```

---

### 1. Database Schema & Data Models

#### [NEW] [user.py](file:///d:/Requirement%20Analyzer/app/models/user.py)
SQLAlchemy model representing a user. Contains `id`, `username`, `email`, `hashed_password`, and a relationship to the `Requirement` model.

#### [NEW] [requirement.py](file:///d:/Requirement%20Analyzer/app/models/requirement.py)
SQLAlchemy model representing a single requirement analysis run. Stores:
- Category (FR/NFR)
- Ambiguity score & detected vague terms list
- Completeness score & missing components list
- Recommended priority (MoSCoW)
- AI Suggestions text
- **`issues`**: SQLite `JSON` column to store a clean string list of structural errors and issues.
- Foreign key `user_id` mapping to the user who ran the analysis.

#### [NEW] [auth.py](file:///d:/Requirement%20Analyzer/app/schemas/auth.py)
Pydantic schemas:
- `UserCreate`: Plain text validation for registration.
- `UserOut`: Data structure for public user representation.
- `Token`: Access token return model.

#### [NEW] [requirement.py](file:///d:/Requirement%20Analyzer/app/schemas/requirement.py)
Pydantic schemas:
- `RequirementInput`: Schema accepting text blocks or lists of statements, along with a `persist` boolean (defaults to `False` for interactive unsaved preview).
- `RequirementOut`: Schema representing the detailed analysis of a single sentence.
- `AnalysisResult`: Aggregated data container including counts, average metrics, overall system risk score, and list of cross-requirement issues.

---

### 2. Utilities & Security Layer

#### [NEW] [security.py](file:///d:/Requirement%20Analyzer/app/security.py)
Provides:
- `pwd_context` using `passlib.context.CryptContext(schemes=["bcrypt"])` for hashing/verification.
- `create_access_token` and `decode_access_token` using `jose.jwt` with `HS256` and configurable secret keys.

#### [NEW] [analyze.py (Dependency)](file:///d:/Requirement%20Analyzer/app/api/analyze.py)
Contains the FastAPI dependency `get_current_user` using `OAuth2PasswordBearer` to fetch the logged-in user and enforce authentication.

---

### 3. Core Requirement Analyzer Engine

#### [NEW] [analyzer.py](file:///d:/Requirement%20Analyzer/app/services/analyzer.py)
- **Sentence Splitting**: Parse bulk plain text using SpaCy sentence boundary detection.
- **Classification**: Rule-based categorization (e.g. check for modals "shall", "must" or user actions for FRs vs non-functional traits like "latency", "securing" for NFRs) paired with an LLM prompt for precise categorization.
- **Ambiguity Detection**: Identify weak qualifiers (e.g., "fast", "optimal", "user-friendly") and calculate a score from 0.0 to 1.0 based on density.
- **Completeness Analysis**: Parse sentence dependency graphs to confirm presence of:
  1. Actor (subject) - 25%
  2. Action (verb) - 25%
  3. Condition (conditionals/adverbials) - 25%
  4. Expected Outcome - 25%
  - Total score is determined via a linear arithmetic progression (sum of weights of present components).
- **AI Suggestion Generation**: Trigger an OpenAI structured request to rewrite the requirement into standard templates (e.g., *Connextra format*).

#### [NEW] [consistency.py](file:///d:/Requirement%20Analyzer/app/services/consistency.py)
- **Duplicate Detection**: Use cosine similarity on SpaCy word vector embeddings to detect statements that overlap above a specific threshold.
- **Conflict Detection**: Check pairs of requirements. To avoid large LLM API latencies and expenses, run the validation LLM step **only on sentence pairs that share a high semantic similarity score (> 0.70)**.

---

### 4. API Endpoints & Route Protection

#### [NEW] [auth.py](file:///d:/Requirement%20Analyzer/app/api/auth.py)
Endpoints:
- `POST /api/auth/register`: Create user and save hashed password.
- `POST /api/auth/login`: Verify password and issue JWT token.

#### [NEW] [analyze.py](file:///d:/Requirement%20Analyzer/app/api/analyze.py)
Endpoints protected by `get_current_user`:
- `POST /api/analyze/text`: Processes raw text, runs analysis pipeline, saves results mapped to the current user *only* if `persist=True`, and returns metrics.
- `GET /api/dashboard/metrics`: Returns counts, distributions, risk statistics, and historical runs of the authenticated user.

---

## Verification Plan

### Automated Tests
We will write a verification script `test_system.py` in the workspace to:
- Test password hashing and verification.
- Test JWT token generation, decoding, and expiration validation.
- Run a mockup request to the `RequirementAnalyzer` to verify classification, completeness (verifying the 25% per component score), and SpaCy sentence parsing logic.

### Manual Verification
1. Run FastAPI server using `uvicorn app.main:app --reload`.
2. Access the interactive API docs at `/docs`.
3. Register a test user, log in, authorize the session, and verify that the `/api/analyze/text` and `/api/dashboard/metrics` endpoints only allow access to authenticated users and scoped data.

