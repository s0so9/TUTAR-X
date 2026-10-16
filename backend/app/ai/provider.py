"""AI provider abstraction for AI Analyst.

This module defines the interface for AI providers and implements
the Ollama provider for local AI analysis.
"""

from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import json

import httpx

from app.domain.analysis import AnalysisContext


class AIProvider(ABC):
    """Abstract base class for AI providers.
    
    This abstraction allows the AI Analyst to work with different
    AI backends without changing the service layer.
    """
    
    @abstractmethod
    def generate_analysis(
        self,
        context: AnalysisContext,
        prompt: str,
        **kwargs
    ) -> str:
        """Generate analysis from context and prompt.
        
        Args:
            context: Structured analysis context
            prompt: User/system prompt
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Generated analysis text
            
        Raises:
            AIProviderError: If generation fails
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if AI provider is available.
        
        Returns:
            True if provider can be reached, False otherwise
        """
        pass


class AIProviderError(Exception):
    """Exception raised when AI provider encounters an error."""
    pass


class OllamaProvider(AIProvider):
    """Ollama AI provider for local AI analysis.
    
    Ollama provides local LLM inference without external API calls.
    Model: qwen3-coder:30b (as specified in PROJECT_SPEC.md)
    """
    
    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:11434",
        model: str = "qwen3-coder:30b",
        timeout: float = 60.0,
    ):
        """Initialize Ollama provider.
        
        Args:
            endpoint: Ollama API endpoint
            model: Model name to use
            timeout: Request timeout in seconds
        """
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout
    
    def generate_analysis(
        self,
        context: AnalysisContext,
        prompt: str,
        **kwargs
    ) -> str:
        """Generate analysis using Ollama.
        
        Args:
            context: Structured analysis context
            prompt: Analysis prompt/instruction
            **kwargs: Additional parameters (temperature, etc.)
            
        Returns:
            Generated analysis text
            
        Raises:
            AIProviderError: If Ollama is unavailable or request fails
        """
        if not self.is_available():
            raise AIProviderError("Ollama is not available at endpoint")
        
        # Build full prompt from context and instructions
        full_prompt = self._build_prompt(context, prompt)
        
        # Prepare request
        url = f"{self.endpoint}/api/generate"
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 0.9),
                "top_k": kwargs.get("top_k", 40),
            }
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                return result.get("response", "")
        
        except httpx.TimeoutException as e:
            raise AIProviderError(f"Ollama request timed out: {e}")
        except httpx.HTTPError as e:
            raise AIProviderError(f"Ollama HTTP error: {e}")
        except Exception as e:
            raise AIProviderError(f"Ollama error: {e}")
    
    def is_available(self) -> bool:
        """Check if Ollama is available.
        
        Returns:
            True if Ollama endpoint responds, False otherwise
        """
        try:
            url = f"{self.endpoint}/api/tags"
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                return response.status_code == 200
        except Exception:
            return False
    
    def _build_prompt(self, context: AnalysisContext, instruction: str) -> str:
        """Build prompt from AnalysisContext.
        
        Serializes context into structured text format for LLM consumption.
        Explicitly indicates missing information.
        
        Args:
            context: Analysis context
            instruction: User instruction/question
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = []
        
        # System instruction
        prompt_parts.append(
            "You are a football match analysis assistant. "
            "You have access to structured match data below. "
            "Use ONLY the information provided - do NOT invent statistics, "
            "probabilities, odds, or any numerical values. "
            "If information is missing or unavailable, explicitly state that."
        )
        prompt_parts.append("")
        
        # Match information
        match = context.match
        prompt_parts.append("=== MATCH INFORMATION ===")
        prompt_parts.append(f"Home Team: {context.home_team.name}")
        prompt_parts.append(f"Away Team: {context.away_team.name}")
        prompt_parts.append(f"Competition: {context.competition.name}")
        prompt_parts.append(f"Scheduled: {match.scheduled_at}")
        prompt_parts.append(f"Status: {match.status.value if hasattr(match.status, 'value') else match.status}")
        prompt_parts.append("")
        
        # Team strength
        if context.home_team_strength and context.away_team_strength:
            prompt_parts.append("=== TEAM STRENGTH ===")
            prompt_parts.append(f"Home Attack Strength: {context.home_team_strength.get('attack_strength')}")
            prompt_parts.append(f"Home Defense Strength: {context.home_team_strength.get('defense_strength')}")
            prompt_parts.append(f"Away Attack Strength: {context.away_team_strength.get('attack_strength')}")
            prompt_parts.append(f"Away Defense Strength: {context.away_team_strength.get('defense_strength')}")
            prompt_parts.append("")
        
        # Standings
        if context.home_standing and context.away_standing:
            prompt_parts.append("=== LEAGUE STANDINGS ===")
            prompt_parts.append(
                f"Home Team: Position {context.home_standing.position}, "
                f"{context.home_standing.points} points from {context.home_standing.played} matches"
            )
            prompt_parts.append(
                f"Away Team: Position {context.away_standing.position}, "
                f"{context.away_standing.points} points from {context.away_standing.played} matches"
            )
            prompt_parts.append("")
        
        # Prediction
        if context.model_predictions and len(context.model_predictions) > 0:
            pred = context.model_predictions[0]
            prompt_parts.append("=== MODEL PREDICTION ===")
            prompt_parts.append(f"Home Win Probability: {pred.home_win_probability:.2%}")
            prompt_parts.append(f"Draw Probability: {pred.draw_probability:.2%}")
            prompt_parts.append(f"Away Win Probability: {pred.away_win_probability:.2%}")
            prompt_parts.append(f"Home Expected Goals: {pred.home_xg:.2f}")
            prompt_parts.append(f"Away Expected Goals: {pred.away_xg:.2f}")
            if pred.btts_probability is not None:
                prompt_parts.append(f"BTTS Probability: {pred.btts_probability:.2%}")
            prompt_parts.append("")
        
        # Missing data
        if context.missing_data_notes:
            prompt_parts.append("=== MISSING/UNAVAILABLE DATA ===")
            for note in context.missing_data_notes:
                prompt_parts.append(f"- {note}")
            prompt_parts.append("")
        
        # User instruction
        prompt_parts.append("=== QUESTION/INSTRUCTION ===")
        prompt_parts.append(instruction)
        prompt_parts.append("")
        prompt_parts.append("Please provide analysis based ONLY on the information above:")
        
        return "\n".join(prompt_parts)


class MockAIProvider(AIProvider):
    """Mock AI provider for testing.
    
    Returns predefined responses without making actual AI calls.
    Useful for testing when Ollama is not available.
    """
    
    def __init__(self, default_response: str = "Mock analysis response"):
        """Initialize mock provider.
        
        Args:
            default_response: Response to return
        """
        self.default_response = default_response
        self.available = True
    
    def generate_analysis(
        self,
        context: AnalysisContext,
        prompt: str,
        **kwargs
    ) -> str:
        """Return mock response.
        
        Args:
            context: Analysis context (not used)
            prompt: Prompt (not used)
            **kwargs: Additional parameters (not used)
            
        Returns:
            Mock response
        """
        return self.default_response
    
    def is_available(self) -> bool:
        """Check if mock provider is available.
        
        Returns:
            True if enabled, False otherwise
        """
        return self.available
