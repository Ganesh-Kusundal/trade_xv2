"""Guard tests for token file placement (P0.7).

Token JSON files must NOT live inside ``src/brokers/runtime/`` in the git
index.  They should be stored under ``~/.tradex/tokens/`` (or another
location outside the source tree).  These tests ensure the .gitignore
rules stay in place and that git doesn't re-track the files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GITIGNORE = REPO_ROOT / ".gitignore"


class TestGitignorePatterns:
    """Verify .gitignore contains the required token-exclusion patterns."""

    def _gitignore_text(self) -> str:
        return GITIGNORE.read_text()

    def test_runtime_json_pattern_present(self) -> None:
        text = self._gitignore_text()
        assert "src/brokers/runtime/*.json" in text, (
            "Missing 'src/brokers/runtime/*.json' in .gitignore — "
            "token files could be re-committed to the source tree."
        )

    def test_canonical_token_dir_present(self) -> None:
        text = self._gitignore_text()
        assert "~/.tradex/tokens/" in text, (
            "Missing '~/.tradex/tokens/' in .gitignore — "
            "the migration-target directory should be ignored."
        )


class TestTokenFilesNotTracked:
    """Ensure token JSON files are not tracked in the git index."""

    @pytest.mark.parametrize(
        "filename",
        [
            "dhan-token-1106251237.json",
            "dhan-token-TEST_CLIENT.json",
        ],
    )
    def test_token_file_not_in_git_index(self, filename: str) -> None:
        result = subprocess.run(
            ["git", "ls-files", f"src/brokers/runtime/{filename}"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.stdout.strip() == "", (
            f"'{filename}' is still tracked in git — run "
            f"'git rm --cached src/brokers/runtime/{filename}' to untrack it."
        )

    def test_no_token_jsons_in_runtime_dir(self) -> None:
        """Broader check: no *dhan-token*.json should be tracked anywhere under runtime/."""
        result = subprocess.run(
            ["git", "ls-files", "src/brokers/runtime/*token*.json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        tracked = [line for line in result.stdout.strip().splitlines() if line]
        assert not tracked, (
            f"Token JSON files still tracked in git: {tracked} — "
            "untrack them with 'git rm --cached'."
        )
