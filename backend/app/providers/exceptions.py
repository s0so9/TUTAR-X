"""Provider-specific exceptions for football data integration.

All provider exceptions carry provider_name, operation, and a sanitized message
that does not expose secrets or sensitive internal details.
"""


class ProviderError(Exception):
    """Base exception for all provider errors.
    
    Attributes:
        provider_name: Name of the provider that raised the error
        operation: The operation being performed (e.g., 'get_match', 'get_standings')
        message: Sanitized error message safe for logging/display
        original_error: Original exception if wrapped (not exposed in logs)
    """
    
    def __init__(
        self,
        provider_name: str,
        operation: str,
        message: str,
        original_error: Exception = None
    ):
        self.provider_name = provider_name
        self.operation = operation
        self.message = message
        self.original_error = original_error
        super().__init__(f"[{provider_name}] {operation}: {message}")
    
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"provider_name={self.provider_name!r}, "
            f"operation={self.operation!r}, "
            f"message={self.message!r})"
        )


class ProviderTimeoutError(ProviderError):
    """Provider request timed out.
    
    Raised when a provider request exceeds the configured timeout duration.
    This is typically a transient error and may succeed on retry.
    """
    pass


class ProviderHTTPError(ProviderError):
    """Provider returned an HTTP error response.
    
    Attributes:
        status_code: HTTP status code returned by the provider
    """
    
    def __init__(
        self,
        provider_name: str,
        operation: str,
        message: str,
        status_code: int,
        original_error: Exception = None
    ):
        super().__init__(provider_name, operation, message, original_error)
        self.status_code = status_code
    
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"provider_name={self.provider_name!r}, "
            f"operation={self.operation!r}, "
            f"status_code={self.status_code}, "
            f"message={self.message!r})"
        )


class ProviderInvalidDataError(ProviderError):
    """Provider returned data that could not be parsed or validated.
    
    Raised when:
    - JSON parsing fails
    - Required fields are missing
    - Data format is unexpected
    - Pydantic validation fails
    """
    pass


class ProviderNotFoundError(ProviderError):
    """Requested resource was not found by the provider.
    
    Raised when a specific resource (match, team, player, etc.) does not exist
    or is not available from the provider.
    """
    pass
