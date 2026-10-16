"""Tests for AI Analyst and provider system.

This test suite verifies:
1. Provider abstraction
2. AnalysisContext serialization
3. Prompt/context construction
4. Missing data handling
5. Ollama unavailable/error handling
6. Deterministic context generation
7. AI Analyst service behavior
"""

import pytest
from datetime import datetime, date, timedelta

from app.ai import (
    AIProvider,
    OllamaProvider,
    MockAIProvider,
    AIProviderError,
    AIAnalyst,
)
from app.domain.analysis import AnalysisContext
from app.domain.match import Match
from app.domain.entities import Team, Competition
from app.domain.prediction import Prediction, Model
from app.domain.enums import MatchStatus, ModelType
from app.providers import DevelopmentProvider


@pytest.fixture
def sample_context():
    """Create sample AnalysisContext for testing."""
    match = Match(
        id="test_match",
        competition_id="test_comp",
        season_id="test_season",
        home_team_id="team_home",
        away_team_id="team_away",
        scheduled_at=datetime.now() + timedelta(days=1),
        status=MatchStatus.SCHEDULED,
    )
    
    home_team = Team(id="team_home", name="Home Team")
    away_team = Team(id="team_away", name="Away Team")
    competition = Competition(id="test_comp", name="Test League", country="Test", level=1)
    
    prediction = Prediction(
        id="test_pred",
        match_id="test_match",
        model_id="poisson_v1",
        home_win_probability=0.45,
        draw_probability=0.30,
        away_win_probability=0.25,
        home_xg=1.8,
        away_xg=1.2,
        predicted_home_score=1.8,
        predicted_away_score=1.2,
        btts_probability=0.65,
        generated_at=datetime.now(),
    )
    
    context = AnalysisContext(
        match=match,
        home_team=home_team,
        away_team=away_team,
        competition=competition,
        home_team_strength={
            "attack_strength": 1.8,
            "defense_strength": 1.1,
        },
        away_team_strength={
            "attack_strength": 1.4,
            "defense_strength": 1.3,
        },
        model_predictions=[prediction],
        data_completeness={
            "match": True,
            "teams": True,
            "prediction": True,
        },
        data_freshness=datetime.now(),
    )
    
    return context


class TestMockProvider:
    """Tests for MockAIProvider."""
    
    def test_mock_provider_initialization(self):
        """Verify mock provider can be initialized."""
        provider = MockAIProvider(default_response="Test response")
        assert provider.default_response == "Test response"
    
    def test_mock_provider_is_available(self):
        """Verify mock provider reports as available."""
        provider = MockAIProvider()
        assert provider.is_available() is True
    
    def test_mock_provider_generate_analysis(self, sample_context):
        """Verify mock provider returns default response."""
        provider = MockAIProvider(default_response="Mock analysis")
        result = provider.generate_analysis(sample_context, "Test prompt")
        assert result == "Mock analysis"


class TestOllamaProvider:
    """Tests for OllamaProvider."""
    
    def test_ollama_provider_initialization(self):
        """Verify Ollama provider can be initialized."""
        provider = OllamaProvider(
            endpoint="http://localhost:11434",
            model="qwen3-coder:30b"
        )
        assert provider.endpoint == "http://localhost:11434"
        assert provider.model == "qwen3-coder:30b"
    
    def test_ollama_provider_default_config(self):
        """Verify Ollama provider uses correct defaults."""
        provider = OllamaProvider()
        assert provider.endpoint == "http://127.0.0.1:11434"
        assert provider.model == "qwen3-coder:30b"
    
    def test_ollama_availability_check(self):
        """Verify availability check doesn't raise error."""
        provider = OllamaProvider()
        # Should return bool, not raise error
        available = provider.is_available()
        assert isinstance(available, bool)
    
    def test_ollama_generate_raises_when_unavailable(self, sample_context):
        """Verify error raised when Ollama unavailable."""
        # Use invalid endpoint
        provider = OllamaProvider(endpoint="http://invalid:99999")
        
        with pytest.raises(AIProviderError):
            provider.generate_analysis(sample_context, "Test prompt")


class TestPromptBuilding:
    """Tests for prompt construction from AnalysisContext."""
    
    def test_prompt_contains_match_info(self, sample_context):
        """Verify prompt includes match information."""
        provider = OllamaProvider()
        prompt = provider._build_prompt(sample_context, "Analyze this match")
        
        assert "Home Team" in prompt
        assert "Away Team" in prompt
        assert "Test League" in prompt
    
    def test_prompt_contains_team_strength(self, sample_context):
        """Verify prompt includes team strength data."""
        provider = OllamaProvider()
        prompt = provider._build_prompt(sample_context, "Analyze this match")
        
        assert "Attack Strength" in prompt
        assert "Defense Strength" in prompt
        assert "1.8" in prompt  # Home attack
        assert "1.4" in prompt  # Away attack
    
    def test_prompt_contains_prediction(self, sample_context):
        """Verify prompt includes prediction data."""
        provider = OllamaProvider()
        prompt = provider._build_prompt(sample_context, "Analyze this match")
        
        assert "MODEL PREDICTION" in prompt
        assert "Home Win Probability" in prompt
        assert "Draw Probability" in prompt
        assert "Away Win Probability" in prompt
        assert "Expected Goals" in prompt
    
    def test_prompt_contains_instruction(self, sample_context):
        """Verify prompt includes user instruction."""
        provider = OllamaProvider()
        instruction = "Explain the key factors"
        prompt = provider._build_prompt(sample_context, instruction)
        
        assert instruction in prompt
    
    def test_prompt_indicates_missing_data(self):
        """Verify prompt explicitly indicates missing data."""
        match = Match(
            id="test_match",
            competition_id="test_comp",
            season_id="test_season",
            home_team_id="team_home",
            away_team_id="team_away",
            scheduled_at=datetime.now() + timedelta(days=1),
            status=MatchStatus.SCHEDULED,
        )
        
        context = AnalysisContext(
            match=match,
            home_team=Team(id="team_home", name="Home Team"),
            away_team=Team(id="team_away", name="Away Team"),
            competition=Competition(id="test_comp", name="Test", country="Test", level=1),
            missing_data_notes=["Prediction not available", "Standings not available"],
            data_freshness=datetime.now(),
        )
        
        provider = OllamaProvider()
        prompt = provider._build_prompt(context, "Analyze")
        
        assert "MISSING/UNAVAILABLE DATA" in prompt
        assert "Prediction not available" in prompt
        assert "Standings not available" in prompt
    
    def test_prompt_warns_against_inventing_data(self, sample_context):
        """Verify prompt includes warning against inventing data."""
        provider = OllamaProvider()
        prompt = provider._build_prompt(sample_context, "Analyze")
        
        assert "do NOT invent" in prompt or "DO NOT invent" in prompt


class TestAIAnalyst:
    """Tests for AIAnalyst service."""
    
    def test_analyst_initialization(self):
        """Verify AI Analyst can be initialized."""
        analyst = AIAnalyst()
        assert analyst.provider is not None
    
    def test_analyst_with_custom_provider(self):
        """Verify AI Analyst accepts custom provider."""
        mock_provider = MockAIProvider("Custom response")
        analyst = AIAnalyst(provider=mock_provider)
        assert analyst.provider == mock_provider
    
    def test_analyze_match_with_mock_provider(self, sample_context):
        """Verify analyze_match works with mock provider."""
        mock_provider = MockAIProvider("Mock analysis")
        analyst = AIAnalyst(provider=mock_provider)
        
        result = analyst.analyze_match(sample_context)
        assert result == "Mock analysis"
    
    def test_analyze_match_with_custom_question(self, sample_context):
        """Verify analyze_match accepts custom question."""
        mock_provider = MockAIProvider("Answer to question")
        analyst = AIAnalyst(provider=mock_provider)
        
        result = analyst.analyze_match(sample_context, question="Who will win?")
        assert result == "Answer to question"
    
    def test_explain_prediction_requires_prediction(self):
        """Verify explain_prediction raises error without prediction."""
        match = Match(
            id="test_match",
            competition_id="test_comp",
            season_id="test_season",
            home_team_id="team_home",
            away_team_id="team_away",
            scheduled_at=datetime.now(),
            status=MatchStatus.SCHEDULED,
        )
        
        context = AnalysisContext(
            match=match,
            home_team=Team(id="team_home", name="Home"),
            away_team=Team(id="team_away", name="Away"),
            competition=Competition(id="test_comp", name="Test", country="Test", level=1),
            data_freshness=datetime.now(),
        )
        
        analyst = AIAnalyst(provider=MockAIProvider())
        
        with pytest.raises(ValueError, match="no prediction"):
            analyst.explain_prediction(context)
    
    def test_explain_prediction_with_prediction(self, sample_context):
        """Verify explain_prediction works when prediction exists."""
        mock_provider = MockAIProvider("Prediction explanation")
        analyst = AIAnalyst(provider=mock_provider)
        
        result = analyst.explain_prediction(sample_context)
        assert result == "Prediction explanation"
    
    def test_compare_teams(self, sample_context):
        """Verify compare_teams generates comparison."""
        mock_provider = MockAIProvider("Team comparison")
        analyst = AIAnalyst(provider=mock_provider)
        
        result = analyst.compare_teams(sample_context)
        assert result == "Team comparison"
    
    def test_identify_key_factors(self, sample_context):
        """Verify identify_key_factors generates analysis."""
        mock_provider = MockAIProvider("Key factors analysis")
        analyst = AIAnalyst(provider=mock_provider)
        
        result = analyst.identify_key_factors(sample_context)
        assert result == "Key factors analysis"
    
    def test_check_availability(self):
        """Verify check_availability works."""
        analyst = AIAnalyst(provider=MockAIProvider())
        assert analyst.check_availability() is True
    
    def test_analyze_raises_when_provider_unavailable(self, sample_context):
        """Verify error raised when provider unavailable."""
        mock_provider = MockAIProvider()
        mock_provider.available = False
        analyst = AIAnalyst(provider=mock_provider)
        
        with pytest.raises(AIProviderError):
            analyst.analyze_match(sample_context)


class TestContextSerialization:
    """Tests for AnalysisContext serialization to prompt."""
    
    def test_deterministic_prompt_generation(self, sample_context):
        """Verify same context produces same prompt."""
        provider = OllamaProvider()
        
        prompt1 = provider._build_prompt(sample_context, "Test")
        prompt2 = provider._build_prompt(sample_context, "Test")
        
        assert prompt1 == prompt2
    
    def test_different_contexts_different_prompts(self):
        """Verify different contexts produce different prompts."""
        match1 = Match(
            id="match1",
            competition_id="comp1",
            season_id="season1",
            home_team_id="team_a",
            away_team_id="team_b",
            scheduled_at=datetime.now(),
            status=MatchStatus.SCHEDULED,
        )
        
        match2 = Match(
            id="match2",
            competition_id="comp1",
            season_id="season1",
            home_team_id="team_c",
            away_team_id="team_d",
            scheduled_at=datetime.now(),
            status=MatchStatus.SCHEDULED,
        )
        
        context1 = AnalysisContext(
            match=match1,
            home_team=Team(id="team_a", name="Team A"),
            away_team=Team(id="team_b", name="Team B"),
            competition=Competition(id="comp1", name="League", country="Test", level=1),
            data_freshness=datetime.now(),
        )
        
        context2 = AnalysisContext(
            match=match2,
            home_team=Team(id="team_c", name="Team C"),
            away_team=Team(id="team_d", name="Team D"),
            competition=Competition(id="comp1", name="League", country="Test", level=1),
            data_freshness=datetime.now(),
        )
        
        provider = OllamaProvider()
        prompt1 = provider._build_prompt(context1, "Test")
        prompt2 = provider._build_prompt(context2, "Test")
        
        assert prompt1 != prompt2


class TestIntegrationWithRealProvider:
    """Integration tests with real DevelopmentProvider."""
    
    def test_analyst_with_development_provider_context(self):
        """Verify AI Analyst works with real development context."""
        provider = DevelopmentProvider()
        matches = provider.get_matches()
        
        if matches:
            match = matches[0]
            
            # Create minimal context
            context = AnalysisContext(
                match=match,
                home_team=Team(id=match.home_team_id, name=match.home_team_id),
                away_team=Team(id=match.away_team_id, name=match.away_team_id),
                competition=Competition(id=match.competition_id, name="Test", country="Test", level=1),
                data_freshness=datetime.now(),
            )
            
            # Use mock provider to avoid Ollama dependency
            mock_provider = MockAIProvider("Analysis of development data")
            analyst = AIAnalyst(provider=mock_provider)
            
            result = analyst.analyze_match(context)
            assert isinstance(result, str)
            assert len(result) > 0
