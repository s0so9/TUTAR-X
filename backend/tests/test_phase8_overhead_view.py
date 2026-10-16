"""Tests for PHASE 8 - Kuşbakışı Canlı Maç Takibi"""

import pytest
from datetime import datetime
from app.providers.models import (
    ProviderLiveMatch,
    PlayerPosition,
    BallPosition,
    FieldDimensions,
    DataQualityIndicators
)
from app.domain.enums import MatchStatus


def test_provider_live_match_with_spatial_data():
    """Test that ProviderLiveMatch can handle spatial data when available."""
    
    # Create player positions
    player_positions = [
        PlayerPosition(
            player_id="player_1",
            player_name="Test Player 1",
            team_id="team_home",
            x=45.0,  # Midfield
            y=30.0,
            timestamp=datetime.utcnow()
        ),
        PlayerPosition(
            player_id="player_2", 
            player_name="Test Player 2",
            team_id="team_away",
            x=75.0,  # Attack position
            y=35.0,
            timestamp=datetime.utcnow()
        )
    ]
    
    # Create ball position
    ball_position = BallPosition(
        x=60.0,  # Center of pitch
        y=34.0,
        z=0.5,   # Ball on ground
        timestamp=datetime.utcnow()
    )
    
    # Create field dimensions 
    field_dimensions = FieldDimensions(
        length_m=105.0,  # Standard pitch
        width_m=68.0
    )
    
    # Create data quality indicators
    data_quality = DataQualityIndicators(
        has_player_positions=True,
        has_ball_tracking=True,
        has_xg=True,
        has_events=True,
        has_shots=True
    )
    
    # Create live match with spatial data
    live_match = ProviderLiveMatch(
        provider="test_provider",
        source_id="test_match_123",
        fetched_at=datetime.utcnow(),
        match_id="match_123",
        status=MatchStatus.LIVE,
        home_score=1,
        away_score=0,
        minute=67,
        last_updated=datetime.utcnow(),
        
        # Spatial data
        player_positions=player_positions,
        ball_position=ball_position,
        field_dimensions=field_dimensions,
        data_quality=data_quality
    )
    
    # Validate spatial data is preserved
    assert live_match.player_positions is not None
    assert len(live_match.player_positions) == 2
    assert live_match.player_positions[0].x == 45.0
    assert live_match.player_positions[1].team_id == "team_away"
    
    assert live_match.ball_position is not None
    assert live_match.ball_position.x == 60.0
    assert live_match.ball_position.z == 0.5
    
    assert live_match.field_dimensions is not None
    assert live_match.field_dimensions.length_m == 105.0
    
    assert live_match.data_quality is not None
    assert live_match.data_quality.has_player_positions is True
    assert live_match.data_quality.has_ball_tracking is True


def test_live_match_without_spatial_data_is_valid():
    """Test that ProviderLiveMatch works without spatial data (current reality)."""
    
    live_match = ProviderLiveMatch(
        provider="fotmob",
        source_id="real_match_456",
        fetched_at=datetime.utcnow(),
        match_id="match_456",
        status=MatchStatus.LIVE,
        home_score=2,
        away_score=1,
        minute=78,
        last_updated=datetime.utcnow()
        # No spatial data provided
    )
    
    # All spatial fields should be None (current reality)
    assert live_match.player_positions is None
    assert live_match.ball_position is None
    assert live_match.field_dimensions is None
    assert live_match.data_quality is None


def test_coordinate_validation_within_pitch_bounds():
    """Test coordinate validation for field view compatibility."""
    
    # Valid coordinates
    valid_player = PlayerPosition(
        player_id="player_test",
        team_id="team_test",
        x=52.5,  # Center line
        y=34.0,  # Center width
        timestamp=datetime.utcnow()
    )
    assert valid_player.x == 52.5
    assert valid_player.y == 34.0
    
    # Valid ball position
    valid_ball = BallPosition(
        x=105.0,  # Goal line
        y=34.0,   # Center width
        z=2.0,    # Ball in air
        timestamp=datetime.utcnow()
    )
    assert valid_ball.x == 105.0
    assert valid_ball.z == 2.0
    
    # Invalid coordinates should raise ValidationError
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError) as exc_info:
        PlayerPosition(
            player_id="invalid",
            team_id="team_test", 
            x=125.0,  # Beyond pitch length
            y=34.0,
            timestamp=datetime.utcnow()
        )
    assert "x coordinate must be between 0 and 120" in str(exc_info.value)
    
    with pytest.raises(ValidationError) as exc_info:
        BallPosition(
            x=60.0,
            y=90.0,  # Beyond pitch width
            timestamp=datetime.utcnow()
        )
    assert "y coordinate must be between 0 and 80" in str(exc_info.value)


def test_data_quality_flags_for_field_view():
    """Test data quality flags that drive field view features."""
    
    # Test with all capabilities enabled
    full_quality = DataQualityIndicators(
        has_player_positions=True,
        has_ball_tracking=True,
        has_xg=True,
        has_events=True,
        has_shots=True,
        has_shot_coordinates=True,
        has_live_statistics=True
    )
    
    assert full_quality.has_player_positions is True
    assert full_quality.has_ball_tracking is True
    assert full_quality.has_shot_coordinates is True
    
    # Test with minimal capabilities (current reality)
    minimal_quality = DataQualityIndicators(
        has_events=True,
        has_shots=False  # Most providers don't have shot coordinates
    )
    
    assert minimal_quality.has_player_positions is False
    assert minimal_quality.has_ball_tracking is False
    assert minimal_quality.has_shot_coordinates is False
    assert minimal_quality.has_events is True


def test_field_dimensions_fifa_compliance():
    """Test field dimensions validation for FIFA standard pitches."""
    
    # Standard FIFA pitch
    standard_pitch = FieldDimensions(
        length_m=105.0,
        width_m=68.0
    )
    assert standard_pitch.length_m == 105.0
    assert standard_pitch.width_m == 68.0
    
    # Minimum FIFA pitch
    min_pitch = FieldDimensions(
        length_m=90.0,
        width_m=45.0
    )
    assert min_pitch.length_m == 90.0
    
    # Maximum FIFA pitch  
    max_pitch = FieldDimensions(
        length_m=120.0,
        width_m=90.0
    )
    assert max_pitch.width_m == 90.0
    
    # Invalid dimensions should raise ValidationError
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError) as exc_info:
        FieldDimensions(
            length_m=85.0,  # Below FIFA minimum
            width_m=68.0
        )
    assert "Pitch length must be between 90 and 120" in str(exc_info.value)
    
    with pytest.raises(ValidationError) as exc_info:
        FieldDimensions(
            length_m=105.0,
            width_m=100.0  # Above FIFA maximum  
        )
    assert "Pitch width must be between 45 and 90" in str(exc_info.value)


class TestPhase8Integration:
    """Integration tests for Phase 8 overhead field view."""
    
    def test_phase8_requirements_satisfied(self):
        """Test that Phase 8 requirements are architecturally satisfied."""
        
        # 1. Data models support coordinate data ✓
        live_match_fields = ProviderLiveMatch.model_fields
        assert 'player_positions' in live_match_fields
        assert 'ball_position' in live_match_fields
        assert 'field_dimensions' in live_match_fields
        
        # 2. Coordinate validation exists ✓
        assert hasattr(PlayerPosition, 'validate_x')
        assert hasattr(PlayerPosition, 'validate_y')
        assert hasattr(BallPosition, 'validate_x')
        assert hasattr(BallPosition, 'validate_y')
        
        # 3. Data quality indicators available ✓
        quality = DataQualityIndicators()
        quality_fields = DataQualityIndicators.model_fields
        assert 'has_player_positions' in quality_fields
        assert 'has_ball_tracking' in quality_fields
        assert 'has_shot_coordinates' in quality_fields
        
        # 4. Future-ready architecture ✓
        # When providers start supplying coordinate data,
        # the models are ready to handle it
        
    def test_current_provider_reality_supported(self):
        """Test that current provider limitations are handled gracefully."""
        
        # Current reality: Most providers don't supply coordinates
        current_match = ProviderLiveMatch(
            provider="fotmob",
            source_id="current_reality",
            fetched_at=datetime.utcnow(),
            match_id="no_coordinates",
            status=MatchStatus.LIVE,
            home_score=0,
            away_score=0,
            last_updated=datetime.utcnow()
            # No spatial data - this is the current reality
        )
        
        # Should work without issues
        assert current_match.player_positions is None
        assert current_match.ball_position is None
        assert current_match.data_quality is None
        
        # Frontend should handle this gracefully by showing
        # "Koordinat verisi mevcut değil" message