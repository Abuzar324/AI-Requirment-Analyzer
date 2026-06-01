from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# For SQLite, we need connect_args={"check_same_thread": False}
# It allows multiple threads to access the same connection, which is fine for SQLite in dev.
if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(settings.database_url)

# SQLAlchemy 2.0: pass engine as first positional arg; `bind=` keyword was removed
SessionLocal = sessionmaker(engine, autocommit=False, autoflush=False)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
