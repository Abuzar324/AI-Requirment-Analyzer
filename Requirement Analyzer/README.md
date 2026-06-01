# AI Requirement Analyzer Backend

This repository contains the backend service for the **AI Requirement Analyzer** (Final Year Project). The system uses Natural Language Processing (SpaCy) and Large Language Models (GPT-4o-mini) to identify quality issues, assess completeness, assign MoSCoW priorities, and suggest rewrites for software requirement statements.

---

## Technical Stack
- **Framework**: FastAPI (Python 3.10+)
- **NLP Engine**: SpaCy (English model)
- **GenAI**: OpenAI API (`gpt-4o-mini` with strict JSON validation)
- **Database**: SQLite with SQLAlchemy ORM
- **Security**: Passlib (bcrypt password hashing) and python-jose (JWT authorization)

---

## Directory Layout
```
d:/Requirement Analyzer/
├── app/
│   ├── main.py            # FastAPI Application Entry & Startup
│   ├── config.py          # Environment configuration loading
│   ├── database.py        # SQLAlchemy SQLite engine & session
│   ├── security.py        # Password hashing & JWT tokens
│   ├── models/            # SQLAlchemy database tables
│   │   ├── user.py        # User table
│   │   └── requirement.py # Requirements table with JSON issue lists
│   ├── schemas/           # Pydantic schemas (V2)
│   │   ├── auth.py        # User create & token payload definitions
│   │   └── requirement.py # Core analysis input/output models
│   ├── api/               # API Router and protected endpoints
│   │   ├── auth.py        # User registration and token issues
│   │   └── analyze.py     # Secure text analyzer & dashboard aggregates
│   └── services/          # Business logic engines
│       ├── analyzer.py    # RequirementAnalyzer (NLP + LLM)
│       └── consistency.py # Cross-requirement duplicate/conflict checks
├── requirements.txt       # Project package dependencies
├── .env                   # Configuration parameters
├── test_system.py         # Verification test suite
└── frontend_blueprint.md  # Client-side JWT guide & UI mock HTML template
```

---

## Installation & Setup

1. **Install Dependencies**:
   Open a terminal and run the following command to install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**:
   Open the `.env` file and fill in your OpenAI API Key to enable GenAI-driven suggestions and conflict checks (it will automatically fallback to rule-based mock logic if left unchanged):
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   ```

3. **Verify the Installation**:
   Execute the automated test script to verify that password hashing, token operations, SpaCy sentence parsing, completeness scoring, and duplicate checkers function correctly:
   ```bash
   python test_system.py
   ```

4. **Launch the Server**:
   Start the FastAPI development server using Uvicorn:
   ```bash
   uvicorn app.main:app --reload
   ```
   Open your browser to `http://127.0.0.1:8000/docs` to interact with the Swagger API documentation.
