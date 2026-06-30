"""Prometheus exporter for metrics system."""
from __future__ import annotations

from typing import Any

from infrastructure.metrics.registry import metrics_registry


def _escape_label_value(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _safe_labels(raw: Any) -> dict[str, str]:
    """Coerce labels to a dict, handling accidental list/tuple passes."""
    if isinstance(raw, dict):
        return raw
    return {}


def _format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{_escape_label_value(v)}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


class PrometheusExporter:
    """Export metrics in Prometheus text format."""

    def __init__(self, registry=None) -> None:
        self._registry = registry or metrics_registry

    def generate(self) -> str:
        """Generate Prometheus-formatted metrics output."""
        lines: list[str] = []
        snap = self._registry.snapshot_detailed()

        for name, info in snap.get("counters", {}).items():
            metric_name = name.replace(" ", "_").replace("-", "_")
            desc = info.get("description", "")
            if desc:
                lines.append(f"# HELP {metric_name} {desc}")
            lines.append(f"# TYPE {metric_name} counter")
            labels = _format_labels(_safe_labels(info.get("labels")))
            lines.append(f"{metric_name}{labels} {info['value']}")

        for name, info in snap.get("gauges", {}).items():
            metric_name = name.replace(" ", "_").replace("-", "_")
            desc = info.get("description", "")
            if desc:
                lines.append(f"# HELP {metric_name} {desc}")
            lines.append(f"# TYPE {metric_name} gauge")
            labels = _format_labels(_safe_labels(info.get("labels")))
            lines.append(f"{metric_name}{labels} {info['value']}")

        for name, info in snap.get("histograms", {}).items():
            metric_name = name.replace(" ", "_").replace("-", "_")
            desc = info.get("description", "")
            if desc:
                lines.append(f"# HELP {metric_name} {desc}")
            lines.append(f"# TYPE {metric_name} histogram")
            labels = _safe_labels(info.get("labels"))
            for bound, cumulative in info.get("buckets", []):
                le = "+Inf" if bound == float("inf") else str(bound)
                label_str = _format_labels({**labels, "le": le})
                lines.append(f"{metric_name}_bucket{label_str} {cumulative}")
            lines.append(f"{metric_name}_sum{_format_labels(labels)} {info.get('sum', 0)}")
            lines.append(f"{metric_name}_count{_format_labels(labels)} {info.get('count', 0)}")

        for name, info in snap.get("timers", {}).items():
            metric_name = name.replace(" ", "_").replace("-", "_")
            desc = info.get("description", "")
            if desc:
                lines.append(f"# HELP {metric_name} {desc}")
            lines.append(f"# TYPE {metric_name} summary")
            labels = _safe_labels(info.get("labels"))
            label_str = _format_labels(labels)
            lines.append(f"{metric_name}{label_str} {info.get('avg', 0)}")
            lines.append(f"{metric_name}_sum{label_str} {info.get('sum', 0)}")
            lines.append(f"{metric_name}_count{label_str} {info.get('count', 0)}")

        return "\n".join(lines) + "\n"
