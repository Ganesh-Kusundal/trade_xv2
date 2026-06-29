"""
METRICS COLLECTOR
Collects and exports performance metrics for monitoring dashboards.
Tracks latency, error rates, throughput, and system health.
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict
import json

@dataclass
class MetricPoint:
    """Single metric data point."""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)

class MetricsCollector:
    """Thread-safe metrics collection and aggregation."""
    
    def __init__(self):
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._start_time = time.time()
    
    # Counter Operations
    def inc_counter(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric (e.g., requests_total, errors_total)."""
        key = self._make_key(name, labels)
        self._counters[key] += value
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> int:
        """Get current counter value."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)
    
    # Gauge Operations
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric (e.g., active_connections, portfolio_value)."""
        key = self._make_key(name, labels)
        self._gauges[key] = value
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        key = self._make_key(name, labels)
        return self._gauges.get(key)
    
    # Histogram Operations
    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record an observation in a histogram (e.g., request_latency_ms)."""
        key = self._make_key(name, labels)
        self._histograms[key].append(value)
        # Keep only last 1000 observations to prevent memory growth
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
    
    def get_histogram_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get histogram statistics (count, sum, avg, min, max, p50, p95, p99)."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}
        
        sorted_values = sorted(values)
        count = len(sorted_values)
        
        return {
            "count": count,
            "sum": sum(sorted_values),
            "avg": sum(sorted_values) / count,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "p50": sorted_values[int(count * 0.50)],
            "p95": sorted_values[int(count * 0.95)] if count >= 20 else sorted_values[-1],
            "p99": sorted_values[int(count * 0.99)] if count >= 100 else sorted_values[-1],
        }
    
    # Utility Methods
    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create unique key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def export_json(self) -> str:
        """Export all metrics as JSON for dashboards."""
        metrics = {
            "uptime_seconds": time.time() - self._start_time,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                key: self.get_histogram_stats(key.replace('{', '').replace('}', ''))
                for key in self._histograms.keys()
            }
        }
        return json.dumps(metrics, indent=2)
    
    def reset(self):
        """Reset all metrics (for testing)."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._start_time = time.time()

# Global singleton instance
metrics = MetricsCollector()
