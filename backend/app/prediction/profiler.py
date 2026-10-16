"""Temporary profiler for prediction pipeline latency analysis.

This module provides detailed timing instrumentation for the prediction pipeline
to identify exact bottlenecks.
"""

import time
import logging
from typing import Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TimingEntry:
    """Single timing measurement."""
    stage: str
    start_time: float
    end_time: float
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class PredictionProfiler:
    """Profiles prediction pipeline execution with detailed timing."""
    
    def __init__(self):
        self.entries: List[TimingEntry] = []
        self.current_stage: str = None
        self.stage_start: float = None
        
    def start_stage(self, stage: str, **metadata):
        """Start timing a pipeline stage."""
        # End previous stage if any
        if self.current_stage:
            self.end_stage()
        
        self.current_stage = stage
        self.stage_start = time.perf_counter()
        
    def end_stage(self, **metadata):
        """End timing current stage."""
        if not self.current_stage:
            return
        
        end_time = time.perf_counter()
        duration_ms = (end_time - self.stage_start) * 1000
        
        entry = TimingEntry(
            stage=self.current_stage,
            start_time=self.stage_start,
            end_time=end_time,
            duration_ms=duration_ms,
            metadata=metadata
        )
        
        self.entries.append(entry)
        logger.info(f"[PROFILE] {self.current_stage}: {duration_ms:.2f}ms {metadata}")
        
        self.current_stage = None
        self.stage_start = None
        
    def get_report(self) -> Dict[str, Any]:
        """Get complete timing report."""
        total_ms = sum(e.duration_ms for e in self.entries)
        
        report = {
            "total_duration_ms": total_ms,
            "stages": [
                {
                    "stage": e.stage,
                    "duration_ms": e.duration_ms,
                    "percentage": (e.duration_ms / total_ms * 100) if total_ms > 0 else 0,
                    "metadata": e.metadata
                }
                for e in self.entries
            ],
            "summary": self._generate_summary()
        }
        
        return report
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate timing summary."""
        if not self.entries:
            return {}
        
        # Group by category
        categories = {
            "provider_calls": [],
            "database": [],
            "feature_engineering": [],
            "models": [],
            "ensemble": [],
            "markets": [],
            "other": []
        }
        
        for entry in self.entries:
            stage_lower = entry.stage.lower()
            if "provider" in stage_lower or "fotmob" in stage_lower or "ryzellx" in stage_lower:
                categories["provider_calls"].append(entry)
            elif "database" in stage_lower or "db" in stage_lower or "historical" in stage_lower:
                categories["database"].append(entry)
            elif "feature" in stage_lower or "snapshot" in stage_lower or "intelligence" in stage_lower:
                categories["feature_engineering"].append(entry)
            elif any(m in stage_lower for m in ["poisson", "elo", "monte", "binomial", "dixon", "logistic", "form"]):
                categories["models"].append(entry)
            elif "ensemble" in stage_lower or "calibration" in stage_lower:
                categories["ensemble"].append(entry)
            elif "market" in stage_lower or "selector" in stage_lower:
                categories["markets"].append(entry)
            else:
                categories["other"].append(entry)
        
        summary = {}
        for category, entries in categories.items():
            if entries:
                total = sum(e.duration_ms for e in entries)
                summary[category] = {
                    "total_ms": total,
                    "count": len(entries),
                    "average_ms": total / len(entries)
                }
        
        return summary
    
    def print_report(self):
        """Print formatted timing report."""
        report = self.get_report()
        
        print("\n" + "="*80)
        print("PREDICTION PIPELINE TIMING REPORT")
        print("="*80)
        print(f"\nTotal Duration: {report['total_duration_ms']:.2f}ms ({report['total_duration_ms']/1000:.2f}s)")
        print("\nStages (sorted by duration):")
        print("-"*80)
        
        sorted_stages = sorted(report['stages'], key=lambda x: x['duration_ms'], reverse=True)
        for stage in sorted_stages:
            print(f"{stage['duration_ms']:8.2f}ms ({stage['percentage']:5.1f}%) - {stage['stage']}")
            if stage['metadata']:
                for key, value in stage['metadata'].items():
                    print(f"           {key}: {value}")
        
        print("\n" + "-"*80)
        print("Category Summary:")
        print("-"*80)
        for category, stats in report['summary'].items():
            print(f"{category:25s}: {stats['total_ms']:8.2f}ms ({stats['count']} calls, avg {stats['average_ms']:.2f}ms)")
        
        print("="*80 + "\n")


# Global profiler instance
_profiler: PredictionProfiler = None


def get_profiler() -> PredictionProfiler:
    """Get global profiler instance."""
    global _profiler
    if _profiler is None:
        _profiler = PredictionProfiler()
    return _profiler


def reset_profiler():
    """Reset global profiler."""
    global _profiler
    _profiler = PredictionProfiler()


def profile_stage(stage: str, **metadata):
    """Context manager for profiling a stage."""
    from contextlib import contextmanager
    
    @contextmanager
    def _profile():
        profiler = get_profiler()
        profiler.start_stage(stage, **metadata)
        try:
            yield
        finally:
            profiler.end_stage(**metadata)
    
    return _profile()
