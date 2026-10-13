"""Enhanced benchmark script with profiler integration.

This script tests match prediction performance with detailed profiling
to identify exact bottlenecks in the pipeline.
"""

import sys
import time
import json
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

import requests
from app.prediction.profiler import get_profiler, reset_profiler


def test_prediction_with_profiling(match_id: str = "12345", iterations: int = 3):
    """Test prediction endpoint with profiler output.

    Args:
        match_id: Match ID to test
        iterations: Number of test iterations
    """
    base_url = "http://localhost:8003"
    endpoint = f"/api/v1/matches/{match_id}/prediction"

    print("="*80)
    print("PROFILED PREDICTION PERFORMANCE BENCHMARK")
    print("="*80)
    print(f"Endpoint: {endpoint}")
    print(f"Iterations: {iterations}")
    print("="*80)
    print()

    results = []

    for i in range(iterations):
        print(f"\n--- Iteration {i+1}/{iterations} ---")

        # Reset profiler for clean measurement
        reset_profiler()

        start = time.time()
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=60)
            elapsed = time.time() - start

            if response.status_code == 200:
                data = response.json()
                results.append({
                    "iteration": i + 1,
                    "status": "success",
                    "elapsed_ms": elapsed * 1000,
                    "has_prediction": data.get("prediction") is not None,
                    "has_pick": data.get("mensione_pick") is not None
                })
                print(f"✓ Success: {elapsed*1000:.2f}ms")

                # Show key prediction info
                if data.get("prediction"):
                    pred = data["prediction"]
                    print(f"  Probabilities: H={pred.get('home_win_probability', 0):.3f} "
                          f"D={pred.get('draw_probability', 0):.3f} "
                          f"A={pred.get('away_win_probability', 0):.3f}")
                    print(f"  Confidence: {pred.get('confidence_score', 0):.3f}")

                if data.get("mensione_pick"):
                    pick = data["mensione_pick"]
                    if pick.get("pass_decision"):
                        print(f"  Pick: PASS - {pick.get('pass_reason', 'unknown')}")
                    else:
                        print(f"  Pick: {pick.get('market', 'unknown')} - {pick.get('selection', 'unknown')} "
                              f"(prob={pick.get('probability', 0):.3f}, conf={pick.get('confidence', 0):.3f})")
            else:
                elapsed = time.time() - start
                results.append({
                    "iteration": i + 1,
                    "status": "failed",
                    "elapsed_ms": elapsed * 1000,
                    "status_code": response.status_code,
                    "error": response.text[:200]
                })
                print(f"✗ Failed: HTTP {response.status_code} after {elapsed*1000:.2f}ms")
                print(f"  Error: {response.text[:200]}")

        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            results.append({
                "iteration": i + 1,
                "status": "timeout",
                "elapsed_ms": elapsed * 1000
            })
            print(f"✗ Timeout after {elapsed*1000:.2f}ms")

        except Exception as e:
            elapsed = time.time() - start
            results.append({
                "iteration": i + 1,
                "status": "error",
                "elapsed_ms": elapsed * 1000,
                "error": str(e)
            })
            print(f"✗ Error: {e}")

    # Summary statistics
    print("\n" + "="*80)
    print("BENCHMARK SUMMARY")
    print("="*80)

    successful = [r for r in results if r["status"] == "success"]
    if successful:
        times = [r["elapsed_ms"] for r in successful]
        print(f"Successful requests: {len(successful)}/{iterations}")
        print(f"Average time: {sum(times)/len(times):.2f}ms")
        print(f"Min time: {min(times):.2f}ms")
        print(f"Max time: {max(times):.2f}ms")

        if len(times) > 1:
            import statistics
            print(f"Std deviation: {statistics.stdev(times):.2f}ms")
    else:
        print("No successful requests")

    failed = len([r for r in results if r["status"] != "success"])
    if failed > 0:
        print(f"\nFailed requests: {failed}/{iterations}")

    print("="*80)

    return results


def analyze_profiler_logs():
    """Analyze profiler output from backend logs.

    Note: The profiler logs are output by the backend server.
    Check the backend console for [PROFILE] log entries.
    """
    print("\n" + "="*80)
    print("PROFILER ANALYSIS")
    print("="*80)
    print()
    print("The profiler outputs detailed timing for each pipeline stage.")
    print("Check the backend server console for [PROFILE] log entries showing:")
    print("  - FEATURE_EXTRACTION: Time to extract match features")
    print("  - MODEL_ORCHESTRATOR: Time to run all prediction models")
    print("  - ENSEMBLE: Time to combine model predictions")
    print("  - CALIBRATION: Time to calibrate probabilities")
    print("  - CONFIDENCE: Time to assess confidence")
    print("  - MARKET_DERIVATION: Time to derive market probabilities")
    print("  - SHOT_MARKETS: Time to predict shot markets")
    print("  - MARKET_SELECTOR: Time to select best pick")
    print("  - ANALYSIS_CONTEXT: Time to build analysis context")
    print()
    print("Look for stages with high duration_ms values - these are the bottlenecks.")
    print("="*80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark prediction endpoint with profiling")
    parser.add_argument("--match-id", default="12345", help="Match ID to test")
    parser.add_argument("--iterations", type=int, default=3, help="Number of iterations")
    parser.add_argument("--analyze", action="store_true", help="Show profiler analysis guide")

    args = parser.parse_args()

    # Run benchmark
    results = test_prediction_with_profiling(
        match_id=args.match_id,
        iterations=args.iterations
    )

    # Show profiler analysis guide
    if args.analyze:
        analyze_profiler_logs()

    # Save results
    output_file = "benchmark_profiled_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")
