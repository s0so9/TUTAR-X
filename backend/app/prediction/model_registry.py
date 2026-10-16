"""Model registry for prediction engine.

Manages registration, retrieval, and metadata for all prediction models.
"""

from typing import Dict, List, Optional, Union
from app.prediction.interfaces import PredictionModel, PredictionModelMetadata
from app.domain.enums import ModelType


class ModelRegistry:
    """Registry for managing prediction models.
    
    Provides centralized model registration and retrieval.
    Supports querying by model ID or model type.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._models: Dict[str, PredictionModel] = {}

    def register(self, model: PredictionModel) -> None:
        """Register a model in the registry.

        Args:
            model: PredictionModel instance to register

        Raises:
            ValueError: If model_id already registered
        """
        metadata = model.get_metadata()
        model_id = metadata.model_id

        if model_id in self._models:
            raise ValueError(f"Model {model_id} is already registered")

        self._models[model_id] = model

    def get(self, model_id: str) -> Optional[PredictionModel]:
        """Retrieve a model by ID.

        Args:
            model_id: Model identifier

        Returns:
            PredictionModel if found, None otherwise
        """
        return self._models.get(model_id)

    def list_models(self) -> List[PredictionModelMetadata]:
        """List all registered models.

        Returns:
            List of PredictionModelMetadata for all registered models
        """
        return [model.get_metadata() for model in self._models.values()]

    def get_by_type(self, model_type: Union[ModelType, str]) -> List[PredictionModel]:
        """Retrieve all models of a specific type.

        Args:
            model_type: Model type (enum or string e.g., ModelType.POISSON or "poisson")

        Returns:
            List of PredictionModel instances matching the type
        """
        # Normalize to string
        type_str = model_type.value if isinstance(model_type, ModelType) else model_type
        
        matching_models = []
        for model in self._models.values():
            metadata = model.get_metadata()
            if metadata.model_type.value == type_str:
                matching_models.append(model)
        return matching_models

    def clear(self) -> None:
        """Clear all registered models (useful for testing)."""
        self._models.clear()

    def __len__(self) -> int:
        """Return number of registered models."""
        return len(self._models)
