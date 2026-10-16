"""Comprehensive API performance benchmarking script.

Measures p50, p95 latencies for critical endpoints with multiple iterations.
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
import httpx
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8003/api/v1"


class BenchmarkResult:
    def __init__(self, endpoint: str, iterations: int):
        self.endpoint = endpoint
        self.iterations = iterations
        self.latencies: List[float] = []
        self.errors: List[str] = []
        self.response_counts: List[int] = []
    
    def add_result(self, latency_ms: float, count: int = 0, error: str = None):
        if error:
            self.errors.append(error)
        else:
            self.latencies.append(latency_ms)
            self.response_counts.append(count)
    
    def p50(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0
    
    def p95(self) -> float:
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx]
    
    def mean(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0
    
    def min_latency(self) -> float:
        return min(self.latencies) if self.latencies else 0
    
    def max_latency(self) -> float:
        return max(self.latencies) if self.latencies else 0
    
    def avg_count(self) -> float:
        return statistics.mean(self.response_counts) if self.response_counts else 0
    
    def error_rate(self) -> float:
        total = len(self.latencies) + len(self.errors)
        return (len(self.errors) / total * 100) if total > 0 else 0
    
    def print_summary(self):
        logger.info(f"\n{'='*70}")
        logger.info(f"Endpoint: {self.endpoint}")
        logger.info(f"{'='*70}")
        logger.info(f"Iterations:    {self.iterations}")
        logger.info(f"Successful:    {len(self.latencies)}")
        logger.info(f"Failed:        {len(self.errors)}")
        logger.info(f"Error Rate:    {self.error_rate():.1f}%")
        
        if self.latencies:
            logger.info(f"\nLatency Statistics:")
            logger.info(f"  Min:         {self.min_latency():.2f}ms")
            logger.info(f"  Mean:        {self.mean():.2f}ms")
            logger.info(f"  Median (p50): {self.p50():.2f}ms")
            logger.info(f"  p95:         {self.p95():.2f}ms")
            logger.info(f"  Max:         {self.max_latency():.2f}ms")
        
        if self.response_counts:
            logger.info(f"\nAvg Response Count: {self.avg_count():.1f} items")
        
        if self.errors:
            logger.info(f"\nSample Errors:")
            for error in self.errors[:3]:
                logger.info(f"  - {error}")


async def benchmark_endpoint(
    endpoint: str,
    iterations: int = 10,
    warmup: int = 2
) -> BenchmarkResult:
    """Benchmark a single endpoint with warmup and multiple iterations.
    
    Args:
        endpoint: API endpoint to test (e.g., "/matches?status=scheduled")
        iterations: Number of benchmark iterations (after warmup)
        warmup: Number of warmup iterations (not counted)
    
    Returns:
        BenchmarkResult with timing statistics
    """
    result = BenchmarkResult(endpoint, iterations)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        url = f"{API_BASE}{endpoint}"
        
        # Warmup phase
        logger.info(f"\n🔥 Warming up: {endpoint}")
        for i in range(warmup):
            try:
                await client.get(url)
            except Exception as e:
                logger.warning(f"Warmup iteration {i+1} failed: {e}")
        
        # Benchmark phase
        logger.info(f"📊 Benchmarking: {endpoint} ({iterations} iterations)")
        
        for i in range(iterations):
            try:
                start_time = time.perf_counter()
                response = await client.get(url)
                latency_ms = (time.perf_counter() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    count = len(data.get("matches", []))
                    result.add_result(latency_ms, count)
                    
                    # Print progress every 5 iterations
                    if (i + 1) % 5 == 0:
                        logger.info(f"  Iteration {i+1}/{iterations}: {latency_ms:.2f}ms")
                else:
                    result.add_result(0, 0, f"HTTP {response.status_code}")
            
            except Exception as e:
                result.add_result(0, 0, str(e))
            
            # Small delay between requests
            await asyncio.sleep(0.1)
    
    return result


async def main():
    """Run comprehensive API benchmarks."""
    logger.info("="*70)
    logger.info("TUTAR X API PERFORMANCE BENCHMARK")
    logger.info("="*70)
    
    endpoints = [
        ("/matches?status=scheduled&limit=50", "Scheduled matches (50)"),
        ("/matches?status=live&limit=50", "Live matches (50)"),
        ("/matches?limit=20", "All matches (20)"),
        ("/matches?limit=100", "All matches (100)"),
    ]
    
    results: Dict[str, BenchmarkResult] = {}
    
    for endpoint, description in endpoints:
        logger.info(f"\n{'='*70}")
        logger.info(f"Testing: {description}")
        logger.info(f"{'='*70}")
        
        result = await benchmark_endpoint(endpoint, iterations=10, warmup=2)
        results[description] = result
        result.print_summary()
    
    # Summary comparison
    logger.info(f"\n{'='*70}")
    logger.info("SUMMARY COMPARISON")
    logger.info(f"{'='*70}")
    logger.info(f"\n{'Endpoint':<35} {'p50':<12} {'p95':<12} {'Avg Items':<10}")
    logger.info("-" * 70)
    
    for desc, result in results.items():
        logger.info(
            f"{desc:<35} "
            f"{result.p50():<12.2f} "
            f"{result.p95():<12.2f} "
            f"{result.avg_count():<10.1f}"
        )
    
    logger.info(f"\n{'='*70}")
    logger.info("BENCHMARK COMPLETE")
    logger.info(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
