"""Provider health monitoring system.

This module implements health monitoring service that tracks provider
availability and failure modes.

CRITICAL: Never logs or exposes API keys, secrets, or tokens.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field
import httpx

from app.providers.capabilities import ProviderCapabilityMatrix


class ProviderAvailabilityCode(str, Enum):
    """Provider availability status codes."""
    
    AVAILABLE = "AVAILABLE"  # Provider responding successfully
    UNAVAILABLE = "UNAVAILABLE"  # Provider not responding or erroring
    NOT_CONFIGURED = "NOT_CONFIGURED"  # Provider not configured or connection failed
    AUTH_REQUIRED = "AUTH_REQUIRED"  # Authentication required (401/403)
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"  # Payment required (402)
    RATE_LIMITED = "RATE_LIMITED"  # Rate limited (429)
    ENDPOINT_INVALID = "ENDPOINT_INVALID"  # Endpoint not found (404)
    TIMEOUT = "TIMEOUT"  # Request timed out
    UNKNOWN_ERROR = "UNKNOWN_ERROR"  # Other error


class ProviderHealthStatus(BaseModel):
    """Health status for a football data provider."""
    
    provider_name: str = Field(..., description="Provider identifier")
    
    availability_code: ProviderAvailabilityCode = Field(
        ...,
        description="Availability status code"
    )
    
    is_available: bool = Field(
        ...,
        description="True if provider is currently available"
    )
    
    last_check_utc: datetime = Field(
        ...,
        description="Last health check timestamp"
    )
    
    last_success_utc: Optional[datetime] = Field(
        None,
        description="Last successful health check timestamp"
    )
    
    consecutive_failures: int = Field(
        0,
        description="Count of consecutive failures"
    )
    
    error_detail: Optional[str] = Field(
        None,
        description="Sanitized error detail (NEVER contains secrets)"
    )
    
    capabilities: Optional[ProviderCapabilityMatrix] = Field(
        None,
        description="Provider capability matrix"
    )


class ProviderHealthService:
    """Service for monitoring provider health and availability.
    
    Tracks provider availability through lightweight health checks
    and maintains in-memory cache of health status.
    
    CRITICAL: NEVER logs or exposes API keys, secrets, or tokens.
    """
    
    def __init__(
        self,
        provider_configs: Dict[str, Dict[str, Any]],
        timeout_seconds: float = 10.0,
    ):
        """Initialize health service.
        
        Args:
            provider_configs: Dict mapping provider_name to config dict
                Expected config keys:
                - base_url: str
                - test_endpoints: List[str] (endpoint paths to test)
            timeout_seconds: HTTP request timeout
        """
        self._provider_configs = provider_configs
        self._timeout_seconds = timeout_seconds
        self._health_cache: Dict[str, ProviderHealthStatus] = {}
    
    async def check_provider(
        self,
        provider_name: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> ProviderHealthStatus:
        """Check health of a specific provider.
        
        Makes lightweight HTTP request to test endpoint and maps
        response to availability status.
        
        Args:
            provider_name: Provider identifier
            http_client: Optional pre-configured HTTP client
            
        Returns:
            ProviderHealthStatus with current availability
        """
        # Get provider config
        config = self._provider_configs.get(provider_name)
        if not config:
            # Provider not configured
            status = ProviderHealthStatus(
                provider_name=provider_name,
                availability_code=ProviderAvailabilityCode.NOT_CONFIGURED,
                is_available=False,
                last_check_utc=datetime.utcnow(),
                error_detail="Provider not configured",
            )
            self._health_cache[provider_name] = status
            return status
        
        base_url = config.get("base_url")
        test_endpoints = config.get("test_endpoints", [])
        
        if not base_url or not test_endpoints:
            status = ProviderHealthStatus(
                provider_name=provider_name,
                availability_code=ProviderAvailabilityCode.NOT_CONFIGURED,
                is_available=False,
                last_check_utc=datetime.utcnow(),
                error_detail="Missing base_url or test_endpoints",
            )
            self._health_cache[provider_name] = status
            return status
        
        # Create HTTP client if not provided
        close_client = False
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=self._timeout_seconds)
            close_client = True
        
        # Get cached status for consecutive failure tracking
        cached = self._health_cache.get(provider_name)
        consecutive_failures = cached.consecutive_failures if cached else 0
        last_success_utc = cached.last_success_utc if cached else None
        
        try:
            # Test first endpoint
            test_endpoint = test_endpoints[0]
            url = f"{base_url.rstrip('/')}/{test_endpoint.lstrip('/')}"
            
            response = await http_client.get(url)
            
            # Map HTTP status code to availability code
            if response.status_code == 200:
                # Success
                status = ProviderHealthStatus(
                    provider_name=provider_name,
                    availability_code=ProviderAvailabilityCode.AVAILABLE,
                    is_available=True,
                    last_check_utc=datetime.utcnow(),
                    last_success_utc=datetime.utcnow(),
                    consecutive_failures=0,
                )
                
            elif response.status_code == 402:
                # Payment required (treat as known state, not failure)
                status = ProviderHealthStatus(
                    provider_name=provider_name,
                    availability_code=ProviderAvailabilityCode.PAYMENT_REQUIRED,
                    is_available=False,
                    last_check_utc=datetime.utcnow(),
                    last_success_utc=last_success_utc,
                    consecutive_failures=consecutive_failures + 1,
                    error_detail="Payment required (HTTP 402)",
                )
                
            elif response.status_code in (401, 403):
                # Auth required
                status = ProviderHealthStatus(
                    provider_name=provider_name,
                    availability_code=ProviderAvailabilityCode.AUTH_REQUIRED,
                    is_available=False,
                    last_check_utc=datetime.utcnow(),
                    last_success_utc=last_success_utc,
                    consecutive_failures=consecutive_failures + 1,
                    error_detail=f"Authentication required (HTTP {response.status_code})",
                )
                
            elif response.status_code == 404:
                # Endpoint not found
                status = ProviderHealthStatus(
                    provider_name=provider_name,
                    availability_code=ProviderAvailabilityCode.ENDPOINT_INVALID,
                    is_available=False,
                    last_check_utc=datetime.utcnow(),
                    last_success_utc=last_success_utc,
                    consecutive_failures=consecutive_failures + 1,
                    error_detail="Endpoint not found (HTTP 404)",
                )
                
            elif response.status_code == 429:
                # Rate limited
                status = ProviderHealthStatus(
                    provider_name=provider_name,
                    availability_code=ProviderAvailabilityCode.RATE_LIMITED,
                    is_available=False,
                    last_check_utc=datetime.utcnow(),
                    last_success_utc=last_success_utc,
                    consecutive_failures=consecutive_failures + 1,
                    error_detail="Rate limited (HTTP 429)",
                )
                
            else:
                # Other error status
                status = ProviderHealthStatus(
                    provider_name=provider_name,
                    availability_code=ProviderAvailabilityCode.UNKNOWN_ERROR,
                    is_available=False,
                    last_check_utc=datetime.utcnow(),
                    last_success_utc=last_success_utc,
                    consecutive_failures=consecutive_failures + 1,
                    error_detail=f"HTTP {response.status_code}",
                )
                
        except httpx.TimeoutException:
            status = ProviderHealthStatus(
                provider_name=provider_name,
                availability_code=ProviderAvailabilityCode.TIMEOUT,
                is_available=False,
                last_check_utc=datetime.utcnow(),
                last_success_utc=last_success_utc,
                consecutive_failures=consecutive_failures + 1,
                error_detail="Request timeout",
            )
            
        except httpx.ConnectError:
            status = ProviderHealthStatus(
                provider_name=provider_name,
                availability_code=ProviderAvailabilityCode.NOT_CONFIGURED,
                is_available=False,
                last_check_utc=datetime.utcnow(),
                last_success_utc=last_success_utc,
                consecutive_failures=consecutive_failures + 1,
                error_detail="Connection failed",
            )
            
        except Exception as e:
            # Other error - NEVER expose secrets
            status = ProviderHealthStatus(
                provider_name=provider_name,
                availability_code=ProviderAvailabilityCode.UNKNOWN_ERROR,
                is_available=False,
                last_check_utc=datetime.utcnow(),
                last_success_utc=last_success_utc,
                consecutive_failures=consecutive_failures + 1,
                error_detail=f"Error: {type(e).__name__}",
            )
            
        finally:
            if close_client:
                await http_client.aclose()
        
        # Update cache
        self._health_cache[provider_name] = status
        return status
    
    async def check_all(self) -> Dict[str, ProviderHealthStatus]:
        """Check health of all configured providers.
        
        Returns:
            Dict mapping provider_name to ProviderHealthStatus
        """
        results = {}
        for provider_name in self._provider_configs.keys():
            status = await self.check_provider(provider_name)
            results[provider_name] = status
        return results
    
    def get_cached_status(self, provider_name: str) -> Optional[ProviderHealthStatus]:
        """Get cached health status for a provider.
        
        Args:
            provider_name: Provider identifier
            
        Returns:
            Cached ProviderHealthStatus or None if not yet checked
        """
        return self._health_cache.get(provider_name)
    
    def get_all_cached_statuses(self) -> Dict[str, ProviderHealthStatus]:
        """Get all cached health statuses.
        
        Returns:
            Dict mapping provider_name to cached ProviderHealthStatus
        """
        return self._health_cache.copy()
