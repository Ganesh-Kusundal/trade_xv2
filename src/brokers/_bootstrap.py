"""Bootstrap sys.path so this repo's ``src/`` wins over shadowed editable installs."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parents[1]


def ensure_repo_src() -> None:
    """Put Trade_XV2 ``src/`` first and drop a wrongly-cached ``domain`` package."""
    src = str(_REPO_SRC)
    if src in sys.path:
        sys.path.remove(src)
    sys.path.insert(0, src)

    domain = sys.modules.get("domain")
    domain_file = getattr(domain, "__file__", "") or ""
    if domain is not None and not domain_file.startswith(src):
        for key in list(sys.modules):
            if key == "domain" or key.startswith("domain."):
                del sys.modules[key]
