"""Build / version metadata for the observability surface (REF-30).

Exposes ``BUILD_VERSION``, ``BUILD_COMMIT``, and ``BUILD_TIME`` so the
HTTP observability server can advertise them on ``/version``.

The values are populated at module-import time by reading environment
variables and a few standard files. They are *expected* to be empty
in development (``__version__ = "0.0.0+local"``); production
deployments inject the real values via CI build steps.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _detect_git_sha() -> str:
    """Return the current git short SHA, or empty string on failure.

    We swallow all errors: a misconfigured build environment should
    not crash the import of this module — operators still want
    ``/healthz`` to answer.
    """
    try:
        # Walk up from this file looking for a git root.
        here = Path(__file__).resolve()
        for ancestor in [here, *here.parents]:
            if (ancestor / ".git").exists():
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=ancestor,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
                return ""
    except Exception:
        pass
    return ""


# These names are intentionally stable: external dashboards may
# scrape them. Renaming is a breaking change.
BUILD_VERSION: str = os.environ.get("TRADE_XV2_VERSION", "0.0.0+local")
BUILD_COMMIT: str = os.environ.get("TRADE_XV2_COMMIT") or _detect_git_sha()
BUILD_TIME: str = os.environ.get("TRADE_XV2_BUILD_TIME", "")


def build_info_dict() -> dict[str, str]:
    """Return the build info as a JSON-serializable dict.

    Use this in HTTP handlers to avoid hard-coding the same field
    list in three places.
    """
    return {
        "version": BUILD_VERSION,
        "commit": BUILD_COMMIT,
        "build_time": BUILD_TIME,
    }


__all__ = ["BUILD_COMMIT", "BUILD_TIME", "BUILD_VERSION", "build_info_dict"]
