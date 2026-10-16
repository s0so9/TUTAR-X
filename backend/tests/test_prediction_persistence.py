"""Tests for Fix #10: Prediction persistence with database.

Verifies that PredictionPersistenceService properly saves and retrieves
prediction versions from the database.
"""
import pytest
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
from app.database.models import PredictionVersionDB
from app.services.prediction_persistence import PredictionPersistenceService
from app.prediction.prediction_version import PredictionVersion, PredictionStage


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_save_version_basic(db_session):
    """BUGFIX #10: Save prediction version to database."""
    service = PredictionPersistenceService(session=db_session)
    
    version = PredictionVersion(
        version_id=str(uuid.uuid4()),
        match_id="fotmob_123",
        stage=PredictionStage.KICKOFF,
        created_at=datetime.utcnow(),
        prediction_data={"home_win": 0.45, "draw": 0.30, "away_win": 0.25},
        model_versions={"poisson": "v1.0"},
        data_quality_score=0.8,
        confidence_score=0.7,
        notes=["Test version"]
    )
    
    service.save_version(version)
    
    # Verify saved to DB
    db_version = db_session.query(PredictionVersionDB).filter_by(match_id="fotmob_123").first()
    assert db_version is not None
    assert db_version.match_id == "fotmob_123"
    assert db_version.stage == "kickoff"


def test_get_versions_retrieves_all(db_session):
    """Retrieve all versions for a match."""
    service = PredictionPersistenceService(session=db_session)
    
    # Create multiple versions
    for stage in [PredictionStage.SEVEN_DAYS_BEFORE, PredictionStage.KICKOFF]:
        version = PredictionVersion(
            version_id=str(uuid.uuid4()),
            match_id="fotmob_456",
            stage=stage,
            created_at=datetime.utcnow(),
            prediction_data={"test": 1},
            model_versions={},
            data_quality_score=0.5,
            confidence_score=0.5,
            notes=[]
        )
        service.save_version(version)
    
    # Retrieve
    versions = service.get_versions("fotmob_456")
    
    assert len(versions) == 2


def test_save_version_with_frozen_pick(db_session):
    """BUGFIX #10: Save version with frozen pick fields."""
    service = PredictionPersistenceService(session=db_session)
    
    version = PredictionVersion(
        version_id=str(uuid.uuid4()),
        match_id="fotmob_pick",
        stage=PredictionStage.KICKOFF,
        created_at=datetime.utcnow(),
        prediction_data={"pick": "home_win"},
        model_versions={},
        data_quality_score=0.8,
        confidence_score=0.7,
        notes=[],
        selected_market="HOME_WIN",
        selection_text="Home team to win",
        selection_probability=0.65,
        selection_confidence=0.75,
        selection_odds=1.85,
        selection_fair_odds=1.54,
        selection_edge=0.15,
        value_classification="VALUE",
        risk_level="MEDIUM"
    )
    
    service.save_version(version)
    
    # Verify frozen fields saved
    db_version = db_session.query(PredictionVersionDB).filter_by(match_id="fotmob_pick").first()
    assert db_version.selected_market == "HOME_WIN"
    assert db_version.selection_probability == 0.65
