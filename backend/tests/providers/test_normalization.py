"""Tests for spatial data models and normalization."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.providers.models import (
    PlayerPosition,
    BallPosition,
    FieldDimensions,
    DataQualityIndicators,
    ProviderLiveMatch,
)
from app.domain.enums import MatchStatus


def test_player_position_valid_coordinates():
    """Test that valid player position coordinates are accepted."""
    position = PlayerPosition(
        player_id="player_123",
        player_name="Test Player",
        team_id="team_456",
        x=60.0,  # Center of pitch
        y=40.0,  # Center of pitch width
        timestamp=datetime.utcnow(),
    )
    
    assert position.x == 60.0
    assert position.y == 40.0


def test_player_position_rejects_out_of_bounds():
    """Test that out-of-bounds coordinates are rejected."""
    # X coordinate too large
    with pytest.raises(ValidationError) as exc_info:
        PlayerPosition(
            player_id="player_123",
            team_id="team_456",
            x=150.0,  # Beyond pitch length
            y=40.0,
            timestamp=datetime.utcnow(),
        )
    assert "x coordinate must be between 0 and 120" in str(exc_info.value)
    
    # Y coordinate negative
    with pytest.raises(ValidationError) as exc_info:
        PlayerPosition(
            player_id="player_123",
            team_id="team_456",
            x=60.0,
            y=-10.0,  # Negative
            timestamp=datetime.utcnow(),
        )
    assert "y coordinate must be between 0 and 80" in str(exc_info.value)


def test_ball_position_valid():
    """Test that valid ball position is accepted."""
    ball = BallPosition(
        x=60.0,
        y=40.0,
        z=1.5,  # Ball in air
        timestamp=datetime.utcnow(),
    )
    
    assert ball.x == 60.0
    assert ball.y == 40.0
    assert ball.z == 1.5


def test_ball_position_rejects_out_of_bounds():
    """Test that out-of-bounds ball coordinates are rejected."""
    # X coordinate too large
    with pytest.raises(ValidationError) as exc_info:
        BallPosition(
            x=130.0,  # Beyond pitch
            y=40.0,
            timestamp=datetime.utcnow(),
        )
    assert "x coordinate must be between 0 and 120" in str(exc_info.value)
    
    # Z coordinate too high
    with pytest.raises(ValidationError) as exc_info:
        BallPosition(
            x=60.0,
            y=40.0,
            z=50.0,  # Too high
            timestamp=datetime.utcnow(),
        )
    assert "z coordinate must be between 0 and 30" in str(exc_info.value)


def test_field_dimensions_valid():
    """Test that valid field dimensions are accepted."""
    field = FieldDimensions(
        length_m=105.0,  # Standard pitch
        width_m=68.0,  # Standard pitch
    )
    
    assert field.length_m == 105.0
    assert field.width_m == 68.0


def test_field_dimensions_rejects_out_of_range():
    """Test that out-of-range field dimensions are rejected."""
    # Length too small
    with pytest.raises(ValidationError) as exc_info:
        FieldDimensions(
            length_m=80.0,  # Below FIFA minimum
            width_m=68.0,
        )
    assert "Pitch length must be between 90 and 120" in str(exc_info.value)
    
    # Width too large
    with pytest.raises(ValidationError) as exc_info:
        FieldDimensions(
            length_m=105.0,
            width_m=100.0,  # Beyond FIFA maximum
        )
    assert "Pitch width must be between 45 and 90" in str(exc_info.value)


def test_live_match_spatial_fields_default_to_none():
    """Test that spatial fields default to None in ProviderLiveMatch."""
    match = ProviderLiveMatch(
        provider="test",
        source_id="123",
        fetched_at=datetime.utcnow(),
        match_id="match_123",
        status=MatchStatus.LIVE,
        home_score=1,
        away_score=0,
        last_updated=datetime.utcnow(),
    )
    
    # Spatial fields should default to None
    assert match.player_positions is None
    assert match.ball_position is None
    assert match.field_dimensions is None
    assert match.data_quality is None


def test_data_quality_defaults_all_false():
    """Test that DataQualityIndicators defaults all flags to False."""
    quality = DataQualityIndicators()
    
    assert quality.has_player_positions is False
    assert quality.has_ball_tracking is False
    assert quality.has_xg is False
    assert quality.has_shots is False
    assert quality.has_events is False
    assert quality.has_shot_coordinates is False
    assert quality.has_live_statistics is False


def test_live_match_with_spatial_data():
    """Test that ProviderLiveMatch accepts valid spatial data."""
    player_pos = PlayerPosition(
        player_id="player_1",
        team_id="team_1",
        x=50.0,
        y=30.0,
        timestamp=datetime.utcnow(),
    )
    
    ball_pos = BallPosition(
        x=60.0,
        y=40.0,
        z=0.5,
        timestamp=datetime.utcnow(),
    )
    
    field = FieldDimensions(
        length_m=105.0,
        width_m=68.0,
    )
    
    quality = DataQualityIndicators(
        has_player_positions=True,
        has_ball_tracking=True,
    )
    
    match = ProviderLiveMatch(
        provider="test",
        source_id="123",
        fetched_at=datetime.utcnow(),
        match_id="match_123",
        status=MatchStatus.LIVE,
        home_score=1,
        away_score=0,
        last_updated=datetime.utcnow(),
        player_positions=[player_pos],
        ball_position=ball_pos,
        field_dimensions=field,
        data_quality=quality,
    )
    
    assert match.player_positions is not None
    assert len(match.player_positions) == 1
    assert match.ball_position is not None
    assert match.field_dimensions is not None
    assert match.data_quality.has_player_positions is True
