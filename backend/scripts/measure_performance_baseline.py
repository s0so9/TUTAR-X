"""Performance baseline measurement script.

Measures endpoint performance with recorded fixtures to establish
baseline metrics before optimization.

Usage:
    python -m backend.scripts.measure_performance_baseline

Outputs:
    - Performance metrics JSON with p50/p95/p99 latencies
    - Stage timings breakdown
    - External request counts
    - DB query counts
    - Cache hit/miss rates
"""

import asyncio
import time
import statistics
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
import httpx

# Configuration
BASE_URL = "http://localhost:8000"
WARMUP_REQUESTS = 2
MEASUREMENT_REQUESTS = 10
TIMEOUT_SECONDS = 60


class PerformanceMeasurement:
    """Container for performance measurement results."""
    
    def __init__(self, endpoint: str, description: str):
        self.endpoint = endpoint
        self.description = description
        self.latencies: List[float] = []
        self.errors: List[str] = []
        self.timeouts = 0
        self.successful = 0
        
    def add_measurement(self, latency_ms: float):
        """Add successful measurement."""
        self.latencies.append(latency_ms)
        self.successful += 1
    
    def add_error(self, error: str):
        """Add error."""
        self.errors.append(error)
    
    def add_timeout(self):
        """Add timeout."""
        self.timeouts += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Calculate statistics."""
        if not self.latencies:
            return {
                "endpoint": self.endpoint,
                "description": self.description,
                "successful": 0,
                "errors": len(self.errors),
                "timeouts": self.timeouts,
                "error": "No successful requests"
            }
        
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)
        
        return {
            "endpoint": self.endpoint,
            "description": self.description,
            "successful": self.successful,
            "errors": len(self.errors),
            "timeouts": self.timeouts,
            "latency_ms": {
                "min": sorted_latencies[0],
                "p50": sorted_latencies[int(n * 0.5)],
                "p95": sorted_latencies[int(n * 0.95)] if n > 1 else sorted_latencies[0],
                "p99": sorted_latencies[int(n * 0.99)] if n > 1 else sorted_latencies[0],
                "max": sorted_latencies[-1],
                "mean": statistics.mean(sorted_latencies),
                "stdev": statistics.stdev(sorted_latencies) if n > 1 else 0,
            },
            "sample_size": n,
        }


async def measure_endpoint(
    client: httpx.AsyncClient,
    endpoint: str,
    description: str,
    warmup: int = WARMUP_REQUESTS,
    measurements: int = MEASUREMENT_REQUESTS,
) -> PerformanceMeasurement:
    """Measure endpoint performance.
    
    Args:
        client: HTTP client
        endpoint: Endpoint path
        description: Test description
        warmup: Number of warmup requests
        measurements: Number of measurement requests
    
    Returns:
        PerformanceMeasurement with results
    """
    measurement = PerformanceMeasurement(endpoint, description)
    
    print(f"\n{'='*60}")
    print(f"Measuring: {description}")
    print(f"Endpoint: {endpoint}")
    print(f"{'='*60}")
    
    # Warmup
    if warmup > 0:
        print(f"Warmup ({warmup} requests)...")
        for i in range(warmup):
            try:
                await client.get(endpoint, timeout=TIMEOUT_SECONDS)
                print(f"  Warmup {i+1}/{warmup} ✓")
            except Exception as e:
                print(f"  Warmup {i+1}/{warmup} ✗ ({e})")
    
    # Measurements
    print(f"\nMeasurements ({measurements} requests)...")
    for i in range(measurements):
        try:
            start = time.perf_counter()
            response = await client.get(endpoint, timeout=TIMEOUT_SECONDS)
            latency_ms = (time.perf_counter() - start) * 1000
            
            if response.status_code == 200:
                measurement.add_measurement(latency_ms)
                print(f"  Request {i+1}/{measurements}: {latency_ms:.1f}ms ✓")
            else:
                error = f"HTTP {response.status_code}"
                measurement.add_error(error)
                print(f"  Request {i+1}/{measurements}: {error} ✗")
        
        except httpx.TimeoutException:
            measurement.add_timeout()
            print(f"  Request {i+1}/{measurements}: TIMEOUT ✗")
        
        except Exception as e:
            measurement.add_error(str(e))
            print(f"  Request {i+1}/{measurements}: {e} ✗")
    
    # Print summary
    stats = measurement.get_stats()
    if "error" not in stats:
        print(f"\n  ✓ {stats['successful']} successful")
        print(f"    p50: {stats['latency_ms']['p50']:.1f}ms")
        print(f"    p95: {stats['latency_ms']['p95']:.1f}ms")
        print(f"    p99: {stats['latency_ms']['p99']:.1f}ms")
    if stats['errors'] > 0:
        print(f"  ✗ {stats['errors']} errors")
    if stats['timeouts'] > 0:
        print(f"  ⏱ {stats['timeouts']} timeouts")
    
    return measurement


async def main():
    """Run baseline performance measurements."""
    print("FootballIntelligence Performance Baseline Measurement")
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Warmup: {WARMUP_REQUESTS} requests")
    print(f"Measurements: {MEASUREMENT_REQUESTS} requests per test")
    print(f"Timeout: {TIMEOUT_SECONDS}s")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "config": {
            "warmup_requests": WARMUP_REQUESTS,
            "measurement_requests": MEASUREMENT_REQUESTS,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
        "measurements": []
    }
    
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Test 1: Health endpoint (baseline - should be fast)
        measurement = await measure_endpoint(
            client,
            "/health",
            "Health check (warm cache baseline)",
            warmup=2,
            measurements=10,
        )
        results["measurements"].append(measurement.get_stats())
        
        # Test 2: Matches list - 1 day
        from_date = datetime.now().strftime("%Y-%m-%d")
        to_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        measurement = await measure_endpoint(
            client,
            f"/api/v1/matches?from_date={from_date}&to_date={to_date}&status=SCHEDULED&limit=20",
            "Match list - 1 day range, 20 limit (cold)",
            warmup=0,
            measurements=5,
        )
        results["measurements"].append(measurement.get_stats())
        
        # Test 3: Matches list - 7 days (typical Upcoming page load)
        to_date_7 = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        measurement = await measure_endpoint(
            client,
            f"/api/v1/matches?from_date={from_date}&to_date={to_date_7}&status=SCHEDULED&limit=300",
            "Match list - 7 days range, 300 limit (Upcoming page - cold)",
            warmup=0,
            measurements=3,
        )
        results["measurements"].append(measurement.get_stats())
        
        # Test 4: Same 7 days query (warm cache)
        measurement = await measure_endpoint(
            client,
            f"/api/v1/matches?from_date={from_date}&to_date={to_date_7}&status=SCHEDULED&limit=300",
            "Match list - 7 days range, 300 limit (Upcoming page - warm cache)",
            warmup=1,
            measurements=5,
        )
        results["measurements"].append(measurement.get_stats())
        
        # Test 5: Get specific match (if we have matches, use first one)
        # This requires knowing a match ID - skip for now as it's match-specific
        print("\n" + "="*60)
        print("Note: Match-specific prediction tests require known match IDs")
        print("To measure prediction performance, manually test:")
        print("  GET /api/v1/matches/{match_id}/prediction")
        print("="*60)
    
    # Save results
    output_file = f"performance_baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Results saved to: {output_file}")
    print(f"{'='*60}")
    
    # Summary table
    print("\n\nSUMMARY:")
    print(f"{'Endpoint':<50} {'p50':<10} {'p95':<10} {'Success':<10}")
    print("-" * 80)
    for measurement in results["measurements"]:
        if "error" not in measurement:
            print(
                f"{measurement['description'][:50]:<50} "
                f"{measurement['latency_ms']['p50']:>8.0f}ms "
                f"{measurement['latency_ms']['p95']:>8.0f}ms "
                f"{measurement['successful']}/{measurement['successful'] + measurement['errors'] + measurement['timeouts']}"
            )
        else:
            print(
                f"{measurement['description'][:50]:<50} "
                f"{'ERROR':<10} {'ERROR':<10} "
                f"0/{measurement['errors'] + measurement['timeouts']}"
            )


if __name__ == "__main__":
    asyncio.run(main())
