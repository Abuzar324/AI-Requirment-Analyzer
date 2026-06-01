from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import os
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.requirement import Requirement
from app.schemas.requirement import RequirementInput, RequirementOut, AnalysisResult, ConflictDetail, TaskStatus
from app.security import decode_access_token
from app.services.analyzer import RequirementAnalyzer
from app.services.consistency import CrossRequirementConsistency

# Global in-memory storage for task progress tracking
tasks_db: Dict[str, Any] = {}
tasks_lock = threading.Lock()

def update_task(task_id: str, **kwargs):
    with tasks_lock:
        if task_id in tasks_db:
            tasks_db[task_id].update(kwargs)

def check_logical_contradiction(text: str) -> float:
    """Detect simple opposing semantic pairs and return a penalty.

    Each matching opposing pair contributes 0.3, capped at 0.6 total.
    """
    contradiction_pairs = [
        ("offline", "online"),
        ("purge", "maintain"),
        ("invisible", "strict"),
    ]

    conflict_count = 0
    lowered = (text or "").lower()
    for term1, term2 in contradiction_pairs:
        if term1 in lowered and term2 in lowered:
            conflict_count += 1

    return min(conflict_count * 0.3, 0.6)


def risk_breakdown(completeness: float, ambiguity_score: float, conflict_found: bool):
    """Return a breakdown of intermediate penalties and the final risk value."""
    ambiguity_penalty = ambiguity_score * 0.2
    conflict_penalty = 0.5 if conflict_found else 0.0
    incompleteness_deficit = (100.0 - float(completeness)) / 100.0
    incompleteness_risk = incompleteness_deficit * 0.7

    final_risk = ambiguity_penalty + conflict_penalty + incompleteness_risk
    high_risk_boost = False
    if completeness < 30.0:
        final_risk += 0.2
        high_risk_boost = True

    final_risk = min(final_risk, 1.0)

    return {
        "ambiguity_penalty": round(ambiguity_penalty, 3),
        "conflict_penalty": round(conflict_penalty, 3),
        "incompleteness_risk": round(incompleteness_risk, 3),
        "high_risk_boost_applied": high_risk_boost,
        "final_risk": round(final_risk, 3),
    }


def calculate_risk(completeness: float, ambiguity_score: float, conflict_found: bool) -> float:
    """Calculate risk using the Multiplier approach described by the user.

    - `completeness`: percentage 0-100
    - `ambiguity_score`: normalized 0-1
    - `conflict_found`: boolean indicating presence of conflicts
    """
    # 1. Base Risks
    ambiguity_penalty = ambiguity_score * 0.2
    conflict_penalty = 0.5 if conflict_found else 0.0

    # 2. Dynamic Incompleteness Weight (deficit from 100%)
    incompleteness_deficit = (100.0 - float(completeness)) / 100.0

    # 3. The Multiplier Effect
    incompleteness_risk = incompleteness_deficit * 0.7

    # 4. Final Aggregation
    final_risk = ambiguity_penalty + conflict_penalty + incompleteness_risk

    # Optional: High risk boost for very poor completeness
    if completeness < 30.0:
        final_risk += 0.2

    return min(final_risk, 1.0)


def bg_analyze_text(task_id: str, text: str, persist: bool, current_user_id: int):
    # 1. Transition task to processing state
    update_task(task_id, status="processing", progress=10.0)
    
    db = SessionLocal()
    try:
        analyzer = RequirementAnalyzer()
        consistency = CrossRequirementConsistency()
        
        sentences = analyzer.split_sentences(text)
        if not sentences:
            update_task(task_id, status="failed", error="No valid sentences found to analyze.", progress=100.0)
            return

        update_task(task_id, progress=25.0)

        # 2. Run analysis pipeline on all sentences in a single optimized batch!
        # This reduces external GenAI network latency overhead from O(N) down to a single request O(1).
        analyzed_results = analyzer.analyze_batch(sentences)

        update_task(task_id, progress=75.0)

        # 3. Persist results sequentially to database
        analyzed_list = []
        for res in analyzed_results:
            if persist:
                db_req = Requirement(
                    text=res["text"],
                    category=res["category"],
                    ambiguity_score=res["ambiguity_score"],
                    completeness_pct=res["completeness_pct"],
                    issues=res["issues"],
                    suggestions=res["suggestions"],
                    priority=res["priority"],
                    user_id=current_user_id
                )
                db.add(db_req)
                db.commit()
                db.refresh(db_req)
                
                res["id"] = db_req.id
                res["created_at"] = db_req.created_at
                
            analyzed_list.append(RequirementOut(**res))

        update_task(task_id, progress=90.0)

        # 4. Check for duplicates and contradictions first
        raw_dicts = [r.model_dump() for r in analyzed_list]
        conflicts_raw = consistency.detect_conflicts(raw_dicts, threshold=0.70)
        conflicts = [ConflictDetail(**c) for c in conflicts_raw]

        # 5. Calculate aggregate metrics
        total_count = len(analyzed_list)
        fr_count = sum(1 for r in analyzed_list if r.category == "FR")
        nfr_count = sum(1 for r in analyzed_list if r.category == "NFR")
        
        average_ambiguity = sum(r.ambiguity_score for r in analyzed_list) / total_count if total_count > 0 else 0.0
        average_completeness = sum(r.completeness_pct for r in analyzed_list) / total_count if total_count > 0 else 0.0
        
        average_ambiguity = round(average_ambiguity, 2)
        average_completeness = round(average_completeness, 2)
        # Use new calculate_risk signature: (completeness, ambiguity_score, conflict_found)
        breakdown = risk_breakdown(average_completeness, average_ambiguity, len(conflicts) > 0)
        overall_risk_score = breakdown["final_risk"]
        
        result = AnalysisResult(
            requirements=analyzed_list,
            total_count=total_count,
            fr_count=fr_count,
            nfr_count=nfr_count,
            average_ambiguity=average_ambiguity,
            average_completeness=average_completeness,
            overall_risk_score=overall_risk_score,
            ambiguity_penalty=breakdown.get("ambiguity_penalty"),
            conflict_penalty=breakdown.get("conflict_penalty"),
            incompleteness_risk=breakdown.get("incompleteness_risk"),
            contradiction_penalty=None,
            high_risk_boost_applied=breakdown.get("high_risk_boost_applied"),
            conflicts=conflicts
        )
        
        update_task(task_id, status="completed", progress=100.0, result=result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_task(task_id, status="failed", error=str(e), progress=100.0)
    finally:
        db.close()


router = APIRouter(prefix="/api", tags=["Requirement Analysis"])


# Demo endpoint (no auth) to run a sample analysis and show results in the browser.
@router.get("/demo/run_noauth", include_in_schema=False)
def demo_run_noauth():
    from fastapi.responses import HTMLResponse

    text = (
        "The system must operate in a strictly offline environment to ensure data sovereignty. "
        "The system shall provide real-time updates to all users via a public cloud-based dashboard. "
        "The application is required to grant full read/write access to all guest users without authentication. "
        "The system must restrict all file modifications to authorized administrators only."
    )

    analyzer = RequirementAnalyzer()
    consistency = CrossRequirementConsistency()

    sentences = analyzer.split_sentences(text)
    analyzed_list = [analyzer.analyze(s) for s in sentences]

    conflicts = consistency.detect_conflicts(analyzed_list, threshold=0.70)
    total_count = len(analyzed_list)
    average_ambiguity = sum(r['ambiguity_score'] for r in analyzed_list) / total_count if total_count > 0 else 0.0
    average_completeness = sum(r['completeness_pct'] for r in analyzed_list) / total_count if total_count > 0 else 100.0

    breakdown = risk_breakdown(average_completeness, average_ambiguity, len(conflicts) > 0)

    html_parts = ["<html><head><title>Demo Analysis</title></head><body>"]
    html_parts.append(f"<h2>Demo Analysis Results</h2>")
    html_parts.append(f"<p><strong>Total sentences:</strong> {total_count}</p>")
    html_parts.append(f"<p><strong>Average ambiguity:</strong> {average_ambiguity:.3f}</p>")
    html_parts.append(f"<p><strong>Average completeness:</strong> {average_completeness:.1f}%</p>")
    html_parts.append(f"<p><strong>Conflicts detected:</strong> {len(conflicts)}</p>")
    html_parts.append("<h3>Penalty Breakdown</h3>")
    html_parts.append("<ul>")
    html_parts.append(f"<li>Ambiguity penalty: {breakdown['ambiguity_penalty']}</li>")
    html_parts.append(f"<li>Conflict penalty: {breakdown['conflict_penalty']}</li>")
    html_parts.append(f"<li>Incompleteness risk: {breakdown['incompleteness_risk']}</li>")
    html_parts.append(f"<li>High risk boost applied: {breakdown['high_risk_boost_applied']}</li>")
    html_parts.append(f"<li><strong>Final risk:</strong> {breakdown['final_risk']}</li>")
    html_parts.append("</ul>")
    html_parts.append("<h3>Sentences</h3>")
    html_parts.append("<ol>")
    for r in analyzed_list:
        html_parts.append(f"<li>{r['text']}<br/><small>Completeness: {r['completeness_pct']}% — Ambiguity: {r['ambiguity_score']}</small></li>")
    html_parts.append("</ol>")
    html_parts.append("</body></html>")

    return HTMLResponse(content='\n'.join(html_parts))

# OAuth2 scheme config pointing to our login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """FastAPI security dependency to extract and validate the user from the JWT access token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Decode subject (user_id) from token
    subject = decode_access_token(token)
    if subject is None:
        raise credentials_exception
    try:
        user_id = int(subject)
    except ValueError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

@router.post("/analyze/text", response_model=TaskStatus)
def analyze_text(
    input_data: RequirementInput,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Accepts raw requirement text blocks, generates a task ID, starts analysis in background,
    and immediately returns the task details.
    """
    task_id = uuid.uuid4().hex
    
    # Initialize task status
    task = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "result": None,
        "error": None
    }
    
    with tasks_lock:
        tasks_db[task_id] = task
        
    # Queue task for execution
    background_tasks.add_task(
        bg_analyze_text,
        task_id=task_id,
        text=input_data.text,
        persist=input_data.persist,
        current_user_id=current_user.id
    )
    
    return task


@router.post("/analyze/file", response_model=TaskStatus)
async def analyze_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    persist: bool = Form(False),
    current_user: User = Depends(get_current_user)
):
    """Accepts a PDF, Word document, or plain text file, extracts text, starts analysis in background, and returns the task."""
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Upload a .pdf, .docx, or .txt file."
        )

    content = await file.read()
    analyzer = RequirementAnalyzer()
    try:
        if ext == ".pdf":
            text = analyzer.extract_text_from_pdf(content)
        elif ext == ".docx":
            text = analyzer.extract_text_from_docx(content)
        else:
            text = analyzer.extract_text_from_txt(content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

    sentences = analyzer.split_sentences(text)
    if not sentences:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extractable requirements found in the uploaded file."
        )

    task_id = uuid.uuid4().hex
    task = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "result": None,
        "error": None
    }
    
    with tasks_lock:
        tasks_db[task_id] = task
        
    background_tasks.add_task(
        bg_analyze_text,
        task_id=task_id,
        text=text,
        persist=persist,
        current_user_id=current_user.id
    )
    
    return task


@router.get("/analyze/tasks/{task_id}", response_model=TaskStatus)
def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Retrieve the current state and progress of a background analysis task."""
    with tasks_lock:
        task = tasks_db.get(task_id)
        
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found."
        )
    return task


@router.get("/dashboard/metrics", response_model=AnalysisResult)
def get_dashboard_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Computes aggregate metrics and lists history for the logged-in user.
    Enforces user data isolation (users can only access their own data).
    """
    # Fetch user's requirements
    db_requirements = db.query(Requirement).filter(
        Requirement.user_id == current_user.id
    ).order_by(Requirement.created_at.desc()).all()
    
    requirements_out = [RequirementOut.model_validate(r) for r in db_requirements]
    total_count = len(requirements_out)
    
    if total_count == 0:
        return AnalysisResult(
            requirements=[],
            total_count=0,
            fr_count=0,
            nfr_count=0,
            average_ambiguity=0.0,
            average_completeness=0.0,
            overall_risk_score=0.0,
            conflicts=[]
        )
        
    fr_count = sum(1 for r in requirements_out if r.category == "FR")
    nfr_count = sum(1 for r in requirements_out if r.category == "NFR")
    
    # Check for contradictions across the user's stored database requirements first
    consistency = CrossRequirementConsistency()
    raw_dicts = [r.model_dump() for r in requirements_out]
    conflicts_raw = consistency.detect_conflicts(raw_dicts, threshold=0.70)
    conflicts = [ConflictDetail(**c) for c in conflicts_raw]

    average_ambiguity = sum(r.ambiguity_score for r in requirements_out) / total_count
    average_completeness = sum(r.completeness_pct for r in requirements_out) / total_count
    
    average_ambiguity = round(average_ambiguity, 2)
    average_completeness = round(average_completeness, 2)
    # Concatenate stored requirement texts to check for semantic contradictions across user's history
    all_text = " ".join(r.text for r in requirements_out)
    breakdown = risk_breakdown(average_completeness, average_ambiguity, len(conflicts) > 0)
    overall_risk_score = breakdown["final_risk"]
    
    return AnalysisResult(
        requirements=requirements_out,
        total_count=total_count,
        fr_count=fr_count,
        nfr_count=nfr_count,
        average_ambiguity=average_ambiguity,
        average_completeness=average_completeness,
        overall_risk_score=overall_risk_score,
        ambiguity_penalty=breakdown.get("ambiguity_penalty"),
        conflict_penalty=breakdown.get("conflict_penalty"),
        incompleteness_risk=breakdown.get("incompleteness_risk"),
        contradiction_penalty=None,
        high_risk_boost_applied=breakdown.get("high_risk_boost_applied"),
        conflicts=conflicts
    )
