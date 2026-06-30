"""Prometheus exporter for metrics system."""
from __future__ import annotations

from infrastructure.metrics.registry import metrics_registry


class PrometheusExporter:
    """Export metrics in Prometheus text format."""
    
    def __init__(self, registry=None) -> None:
        self._registry = registry or metrics_registry
    
    def generate(self) -> str:
        """Generate Prometheus-formatted metrics output."""
        lines: list[str] = []
        snapshot = self._registry.snapshot()
        
        for name, value in snapshot.get("counters", {}).items():
            metric_name = name.replace(" ", "_").replace("-", "_")
            lines.append(f"# HELP {metric_name} Counter metric")
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f"{metric_name} {value}")
        
        for name, value in snapshot.get("gauges", {}).items():
            metric_name = name.replace(" ", "_").replace("-", "_")
            lines.append(f"# HELP {metric_name} Gauge metric")
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f"{metric_name} {value}")
        
        for name, count in snapshot.get("histograms", {}).items():
            metric_name = name.replace(" ", "_").replace("-", "_")
            lines.append(f"# HELP {metric_name} Histogram metric")
            lines.append(f"# TYPE {metric_name} histogram")
            lines.append(f"{metric_name}_count {count}")
        
        for name, count in snapshot.get("timers", {}).items():
            metric_name = name.replace(" ", "_").replace("-", "_")
            lines.append(f"# HELP {metric_name} Timer metric")
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f"{metric_name}_count {count}")
        
        return "\n".join(lines) + "\n"