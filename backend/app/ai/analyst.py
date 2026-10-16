"""AI Analyst service for match analysis.

The AI Analyst is an explanation layer over structured AnalysisContext.
It does NOT generate predictions or invent data - it only explains
the provided context in natural language.
"""

from typing import Optional

from app.domain.analysis import AnalysisContext
from app.ai.provider import AIProvider, OllamaProvider, AIProviderError


class AIAnalyst:
    """AI-powered match analysis service.
    
    The AI Analyst:
    1. Receives structured AnalysisContext
    2. Converts context into natural language
    3. Does NOT invent statistics, probabilities, or predictions
    4. Explicitly states when information is unavailable
    
    The numerical prediction engine remains the source of truth.
    The AI Analyst only explains what is already calculated.
    """
    
    def __init__(self, provider: Optional[AIProvider] = None):
        """Initialize AI Analyst.
        
        Args:
            provider: AI provider (default: OllamaProvider)
        """
        self.provider = provider or OllamaProvider()
    
    def analyze_match(
        self,
        context: AnalysisContext,
        question: Optional[str] = None
    ) -> str:
        """Generate natural language analysis for a match.
        
        Args:
            context: Structured analysis context
            question: Optional specific question to answer
            
        Returns:
            Natural language analysis
            
        Raises:
            AIProviderError: If AI provider is unavailable
        """
        if not self.provider.is_available():
            raise AIProviderError("AI provider is not available")
        
        # Build prompt
        if question:
            prompt = question
        else:
            prompt = (
                "Provide a comprehensive analysis of this match based on "
                "the available data. Include team strength comparison, "
                "prediction probabilities, and key factors. "
                "Explicitly mention any missing or unavailable information."
            )
        
        # Generate analysis
        analysis = self.provider.generate_analysis(context, prompt)
        
        return analysis
    
    def explain_prediction(
        self,
        context: AnalysisContext,
    ) -> str:
        """Explain the prediction in natural language.
        
        Args:
            context: Analysis context with prediction
            
        Returns:
            Explanation of prediction
            
        Raises:
            AIProviderError: If AI provider is unavailable
            ValueError: If context has no prediction
        """
        if not context.model_predictions or len(context.model_predictions) == 0:
            raise ValueError("Context has no prediction to explain")
        
        prompt = (
            "Explain the match prediction in natural language. "
            "Focus on the probabilities for home win, draw, and away win. "
            "Explain the expected goals and what they mean. "
            "Discuss the BTTS probability if available. "
            "Base your explanation ONLY on the numerical values provided - "
            "do not add your own predictions or adjust the numbers."
        )
        
        return self.provider.generate_analysis(context, prompt)
    
    def compare_teams(
        self,
        context: AnalysisContext,
    ) -> str:
        """Compare the two teams based on available data.
        
        Args:
            context: Analysis context
            
        Returns:
            Team comparison analysis
            
        Raises:
            AIProviderError: If AI provider is unavailable
        """
        prompt = (
            "Compare the home and away teams based on the available data. "
            "Discuss their attack and defense strengths, recent form, "
            "and league positions if available. "
            "Use ONLY the data provided - do not invent statistics. "
            "If certain data is missing, state that explicitly."
        )
        
        return self.provider.generate_analysis(context, prompt)
    
    def identify_key_factors(
        self,
        context: AnalysisContext,
    ) -> str:
        """Identify key factors influencing the match prediction.
        
        Args:
            context: Analysis context with prediction
            
        Returns:
            Analysis of key factors
            
        Raises:
            AIProviderError: If AI provider is unavailable
        """
        prompt = (
            "Identify the key factors influencing this match prediction. "
            "What strengths or weaknesses stand out? "
            "What does the data suggest about each team's chances? "
            "Base your analysis strictly on the provided data."
        )
        
        return self.provider.generate_analysis(context, prompt)
    
    def check_availability(self) -> bool:
        """Check if AI Analyst is available.
        
        Returns:
            True if provider is available, False otherwise
        """
        return self.provider.is_available()
