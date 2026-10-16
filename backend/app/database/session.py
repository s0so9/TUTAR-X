"""Database session management."""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings

# Create database engine
engine = create_engine(
    settings.database_url,
    echo=False,  # Disable SQL logging in production for performance
    pool_pre_ping=True,  # Verify connections before using
    future=True,  # Use SQLAlchemy 2.0 style
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_session_factory():
    """Get the session factory.
    
    Returns:
        sessionmaker instance
    """
    return SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions.
    
    Yields:
        SQLAlchemy Session
        
    Example:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
