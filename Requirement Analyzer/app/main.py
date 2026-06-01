from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.database import Base, engine
from app.api import auth, analyze

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Triggers table creation on startup
    Base.metadata.create_all(engine)
    yield

app = FastAPI(
    title="AI Requirement Analyzer Backend",
    description="Asynchronous NLP & LLM platform for software requirements issues detection, completeness scoring, priority mapping, and JWT secure login.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configurations to allow local frontend dashboard connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production (e.g. ['http://localhost:8000'])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(auth.router)
app.include_router(analyze.router)

# ── Root redirect to login page ──────────────────────────────────
@app.get("/", tags=["Status"], include_in_schema=False)
def read_root():
    """Redirect browser visitors to the login page."""
    return RedirectResponse(url="/static/login.html")

# ── Serve frontend static files ──────────────────────────────────
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")
