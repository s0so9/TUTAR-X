"""
API Performance Test - End-to-end prediction with DB optimization
"""

import sys
import time
import json
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

import requests


def test_prediction_performance(match_id: str, port: int = 8004, iterations: int = 3):
    """Test full prediction API performance."""

    base_url = f"http://localhost:{port}"
    endpoint = f"/api/v1/matches/{match_id}/prediction"

    print("="*80)
    print("API PREDICTION PERFORMANCE TEST")
    print("="*80)
    print(f"Endpoint: {endpoint}")
    print(f"Port: {port}")
    print(f"Iterations: {iterations}")
    print("="*80)
    print()

    results = []

    for i in range(iterations):
        print(f"\n--- Iteration {i+1}/{iterations} ---")

        start = time.time()
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=60)
            elapsed = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                results.append({
                    "iteration": i + 1,
                    "status": "success",
                    "elapsed_ms": elapsed,
                    "has_prediction": data.get("prediction") is not None,
                    "has_analysis": data.get("analysis") is not None
                })

                print(f"✓ Success: {elapsed:.2f}ms")

                # Show prediction info
                if data.get("prediction"):
                    pred = data["prediction"]
                    print(f"  Home Win: {pred.get('home_win_probability', 0):.3f}")
                    print(f"  Draw: {pred.get('draw_probability', 0):.3f}")
                    print(f"  Away Win: {pred.get('away_win_probability', 0):.3f}")
                    print(f"  Confidence: {pred.get('confidence_score', 0):.3f}")

            else:
                results.append({
                    "iteration": i + 1,
                    "status": "failed",
                    "elapsed_ms": elapsed,
                    "status_code": response.status_code,
                    "error": response.text[:200]
                })
                print(f"✗ Failed: HTTP {response.status_code} after {elapsed:.2f}ms")
                print(f"  Error: {response.text[:200]}")

        except requests.exceptions.Timeout:
            elapsed = (time.time() - start) * 1000
            results.append({
                "iteration": i + 1,
                "status": "timeout",
                "elapsed_ms": elapsed
            })
            print(f"✗ Timeout after {elapsed:.2f}ms")

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            results.append({
                "iteration": i + 1,
                "status": "error",
                "elapsed_ms": elapsed,
                "error": str(e)
            })
            print(f"✗ Error: {e}")

    # Summary
    print("\n" + "="*80)
    print("PERFORMANCE SUMMARY")
    print("="*80)

    successful = [r for r in results if r["status"] == "success"]
    if successful:
        times = [r["elapsed_ms"] for r in successful]
        print(f"Successful: {len(successful)}/{iterations}")
        print(f"Average: {sum(times)/len(times):.2f}ms")
        print(f"Min: {min(times):.2f}ms")
        print(f"Max: {max(times):.2f}ms")

        if len(times) > 1:
            import statistics
            print(f"Std Dev: {statistics.stdev(times):.2f}ms")
    else:
        print("No successful requests")

    failed = len([r for r in results if r["status"] != "success"])
    if failed > 0:
        print(f"\nFailed: {failed}/{iterations}")

    print("="*80)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test API prediction performance")
    parser.add_argument("--match-id", default="e27d655d-62ea-4a46-a0be-e572b90baa27",
                        help="Match ID to test")
    parser.add_argument("--port", type=int, default=8004, help="Server port")
    parser.add_argument("--iterations", type=int, default=3, help="Number of iterations")

    args = parser.parse_args()

    results = test_prediction_performance(
        match_id=args.match_id,
        port=args.port,
        iterations=args.iterations
    )

    # Save results
    output_file = "api_performance_test_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")
