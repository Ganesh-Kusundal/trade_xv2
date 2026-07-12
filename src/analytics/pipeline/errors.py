"""Feature pipeline errors."""

from __future__ import annotations


class FeaturePipelineError(RuntimeError):
    """Raised when a feature fails and the pipeline is in fail-closed mode."""

    def __init__(self, feature_name: str, cause: Exception) -> None:
        self.feature_name = feature_name
        self.cause = cause
        super().__init__(f"Feature {feature_name!r} failed: {cause}")