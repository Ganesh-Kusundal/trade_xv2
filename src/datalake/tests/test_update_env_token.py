"""Tests for brokers.common.auth.env_token.update_env_token — atomic env update."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fcntl")

from infrastructure.auth.env_token import update_env_token


class TestUpdateEnvToken:
    def test_updates_existing_token(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=client123\nDHAN_ACCESS_TOKEN=old_token\nDHAN_TOTP_SECRET=secret\n",
            encoding="utf-8",
        )

        update_env_token(env_file, "new_token")

        lines = env_file.read_text(encoding="utf-8").splitlines()
        assert any(line == "DHAN_ACCESS_TOKEN=new_token" for line in lines)
        assert any(line == "DHAN_CLIENT_ID=client123" for line in lines)
        assert any(line == "DHAN_TOTP_SECRET=secret" for line in lines)

    def test_appends_missing_token(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=client123\nDHAN_TOTP_SECRET=secret\n",
            encoding="utf-8",
        )

        update_env_token(env_file, "fresh_token")

        lines = env_file.read_text(encoding="utf-8").splitlines()
        assert any(line == "DHAN_ACCESS_TOKEN=fresh_token" for line in lines)
        assert any(line == "DHAN_CLIENT_ID=client123" for line in lines)
        assert any(line == "DHAN_TOTP_SECRET=secret" for line in lines)

    def test_preserves_comments_and_blanks(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        original = (
            "# Dhan credentials\n"
            "\n"
            "DHAN_CLIENT_ID=client123\n"
            "\n"
            "# Token rotates daily\n"
            "DHAN_ACCESS_TOKEN=old_token\n"
            "\n"
            "DHAN_TOTP_SECRET=secret\n"
        )
        env_file.write_text(original, encoding="utf-8")

        update_env_token(env_file, "new_token")

        content = env_file.read_text(encoding="utf-8")
        assert "# Dhan credentials" in content
        assert "# Token rotates daily" in content
        assert "DHAN_CLIENT_ID=client123" in content
        assert "DHAN_ACCESS_TOKEN=new_token" in content
        assert "DHAN_TOTP_SECRET=secret" in content

    def test_noop_when_env_file_missing(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        update_env_token(env_file, "token")
        assert not env_file.exists()

    def test_uses_atomic_rename(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text("DHAN_ACCESS_TOKEN=old\n", encoding="utf-8")

        observed_tmp: list[Path] = []
        original_replace = os.replace

        def _tracking_replace(src: str | os.PathLike, dst: str | os.PathLike) -> None:
            observed_tmp.append(Path(src))
            original_replace(src, dst)

        with patch("brokers.dhan.token_manager.os.replace", side_effect=_tracking_replace):
            update_env_token(env_file, "new")

        assert len(observed_tmp) == 1
        assert observed_tmp[0].suffix == ".tmp"
        assert observed_tmp[0].parent == env_file.parent

    def test_temp_file_cleaned_on_failure(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text("DHAN_ACCESS_TOKEN=old\n", encoding="utf-8")

        with patch("brokers.dhan.token_manager.os.replace", side_effect=RuntimeError("disk full")):
            update_env_token(env_file, "new")

        assert not (tmp_path / ".env.local.tmp").exists()

    def test_concurrent_writes_are_safe(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text("DHAN_ACCESS_TOKEN=initial\n", encoding="utf-8")

        tokens = [f"token_{i}" for i in range(20)]
        errors: list[Exception] = []

        def _worker(token: str) -> None:
            try:
                update_env_token(env_file, token)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(t,)) for t in tokens]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        content = env_file.read_text(encoding="utf-8")
        # The final token must be one of the written tokens and the line must
        # be well-formed.
        token_line = [
            line for line in content.splitlines() if line.startswith("DHAN_ACCESS_TOKEN=")
        ]
        assert len(token_line) == 1
        assert token_line[0].split("=", 1)[1] in tokens
