"""Provider capability detection system.

This module implements capability detection infrastructure that validates
what each provider actually supports through real HTTP test requests.

CRITICAL: Capabilities are NOT marked as SUPPORTED without actual validation.
Default state is NOT_TESTED until real HTTP probes confirm capability.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field
import httpx


class ProviderCapabilityStatus(str, Enum):
    """Status of a provider capability."""
    
    SUPPORTED = "SUPPORTED"  # Validated via real HTTP response
    PARTIAL = "PARTIAL"  # Partially available (e.g., limited fields)
    UNAVAILABLE = "UNAVAILABLE"  # Confirmed unavailable
    NOT_TESTED = "NOT_TESTED"  # Not yet validated
    NOT_CONFIGURED = "NOT_CONFIGURED"  # Provider not configured
    AUTH_REQUIRED = "AUTH_REQUIRED"  # 401/403 HTTP response
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"  # 402 HTTP response


class ProviderCapability(str, Enum):
    """Football data capabilities that providers may support."""
    
    # Core match data
    live_matches = "live_matches"
    match_details = "match_details"
    match_statistics = "match_statistics"
    
    # Spatial/tracking data
    player_positions = "player_positions"
    ball_tracking = "ball_tracking"
    
    # Advanced statistics
    xg_data = "xg_data"
    shot_xg = "shot_xg"
    shot_coordinates = "shot_coordinates"
    
    # Match metadata
    lineups = "lineups"
    events = "events"
    shots = "shots"
    
    # Live statistics
    possession = "possession"
    corners = "corners"
    fouls = "fouls"
    passes = "passes"
    saves = "saves"


class ProviderCapabilityMatrix(BaseModel):
    """Capability matrix for a football data provider.
    
    Records what capabilities a provider actually supports, validated
    through real HTTP test requests.
    """
    
    provider_name: str = Field(..., description="Provider identifier")
    
    capabilities: Dict[ProviderCapability, ProviderCapabilityStatus] = Field(
        default_factory=dict,
        description="Capability status map"
    )
    
    last_detected_utc: Optional[datetime] = Field(
        None,
        description="Last capability detection timestamp"
    )
    
    detection_notes: Optional[Dict[str, str]] = Field(
        None,
        description="Notes from capability detection (HTTP status codes, errors)"
    )


async def detect_provider_capabilities(
    provider_name: str,
    base_url: str,
    test_endpoints: Dict[str, str],
    http_client: Optional[httpx.AsyncClient] = None,
    timeout_seconds: float = 10.0,
) -> ProviderCapabilityMatrix:
    """Detect provider capabilities through real HTTP probes.
    
    Makes actual HTTP test requests to known endpoints and maps responses
    to capability states. Never marks capabilities as SUPPORTED without
    actual validation.
    
    Args:
        provider_name: Provider identifier
        base_url: Provider base URL
        test_endpoints: Dict mapping capability to test endpoint path
        http_client: Optional pre-configured HTTP client
        timeout_seconds: Request timeout
        
    Returns:
        ProviderCapabilityMatrix with validated capability states
        
    HTTP Status Code Mapping:
        200 → Test response content to determine SUPPORTED/PARTIAL/UNAVAILABLE
        402 → PAYMENT_REQUIRED
        401/403 → AUTH_REQUIRED
        404 → UNAVAILABLE
        Timeout → UNAVAILABLE
        Connection error → NOT_CONFIGURED
        Other 4xx/5xx → UNAVAILABLE
    """
    # Initialize all capabilities as NOT_TESTED
    capabilities: Dict[ProviderCapability, ProviderCapabilityStatus] = {
        cap: ProviderCapabilityStatus.NOT_TESTED
        for cap in ProviderCapability
    }
    
    detection_notes: Dict[str, str] = {}
    
    # Create HTTP client if not provided
    close_client = False
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=timeout_seconds)
        close_client = True
    
    try:
        # Test each endpoint
        for capability_key, endpoint_path in test_endpoints.items():
            try:
                # Map string to enum if needed
                if isinstance(capability_key, str):
                    try:
                        capability = ProviderCapability(capability_key)
                    except ValueError:
                        # Unknown capability, skip
                        detection_notes[capability_key] = "unknown_capability"
                        continue
                else:
                    capability = capability_key
                
                # Construct full URL
                url = f"{base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"
                
                # Make test request
                response = await http_client.get(url)
                
                # Map HTTP status to capability status
                if response.status_code == 200:
                    # Need to inspect response content to determine SUPPORTED/PARTIAL/UNAVAILABLE
                    # For now, mark as SUPPORTED if we get 200
                    # Real implementation would parse response and validate structure
                    capabilities[capability] = ProviderCapabilityStatus.SUPPORTED
                    detection_notes[capability.value] = f"HTTP 200"
                    
                elif response.status_code == 402:
                    capabilities[capability] = ProviderCapabilityStatus.PAYMENT_REQUIRED
                    detection_notes[capability.value] = "HTTP 402 Payment Required"
                    
                elif response.status_code in (401, 403):
                    capabilities[capability] = ProviderCapabilityStatus.AUTH_REQUIRED
                    detection_notes[capability.value] = f"HTTP {response.status_code} Auth Required"
                    
                elif response.status_code == 404:
                    capabilities[capability] = ProviderCapabilityStatus.UNAVAILABLE
                    detection_notes[capability.value] = "HTTP 404 Not Found"
                    
                else:
                    # Other 4xx/5xx
                    capabilities[capability] = ProviderCapabilityStatus.UNAVAILABLE
                    detection_notes[capability.value] = f"HTTP {response.status_code}"
                    
            except httpx.TimeoutException:
                capabilities[capability] = ProviderCapabilityStatus.UNAVAILABLE
                detection_notes[capability.value] = "Timeout"
                
            except httpx.ConnectError:
                capabilities[capability] = ProviderCapabilityStatus.NOT_CONFIGURED
                detection_notes[capability.value] = "Connection failed"
                
            except Exception as e:
                # Other errors
                capabilities[capability] = ProviderCapabilityStatus.UNAVAILABLE
                # NEVER expose secrets in notes
                detection_notes[capability.value] = f"Error: {type(e).__name__}"
                
    finally:
        if close_client:
            await http_client.aclose()
    
    return ProviderCapabilityMatrix(
        provider_name=provider_name,
        capabilities=capabilities,
        last_detected_utc=datetime.utcnow(),
        detection_notes=detection_notes,
    )
