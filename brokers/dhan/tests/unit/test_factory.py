"""Unit tests for BrokerFactory helper functions."""

import base64
import json
import os
import time


from brokers.dhan.factory import _is_token_expired, _load_dotenv, _update_env_token


def _make_jwt(payload: dict) -> str:
    """Build a minimal JWT-like string with the given payload."""
    header = base64.b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    body = base64.b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = base64.b64encode(b"fakesignature").decode().rstrip("=")
    return f"{header}.{body}.{signature}"


def test_is_token_expired_with_expired_token():
    """A token whose exp is in the past should be reported as expired."""
    past_exp = int(time.time()) - 3600  # 1 hour ago
    token = _make_jwt({"exp": past_exp, "sub": "user123"})
    assert _is_token_expired(token) is True


def test_is_token_expired_with_valid_token():
    """A token whose exp is well in the future should not be expired."""
    future_exp = int(time.time()) + 7200  # 2 hours from now
    token = _make_jwt({"exp": future_exp, "sub": "user123"})
    assert _is_token_expired(token) is False


def test_is_token_expired_with_malformed_token():
    """A malformed token (not 3 dot-separated parts) should be treated as expired."""
    assert _is_token_expired("not-a-jwt") is True
    assert _is_token_expired("") is True
    assert _is_token_expired("a.b") is True


def test_is_token_expired_within_buffer():
    """A token expiring within the 5-minute buffer should be treated as expired."""
    # Expires in 60 seconds — within the default 300-second buffer
    near_exp = int(time.time()) + 60
    token = _make_jwt({"exp": near_exp})
    assert _is_token_expired(token) is True


def test_load_dotenv(tmp_path):
    """_load_dotenv should parse key=value pairs and set os.environ."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DHAN_CLIENT_ID=MYCLIENT\n"
        'DHAN_ACCESS_TOKEN="mytoken123"\n'
        "# This is a comment\n"
        "SIMPLE_VAR=hello\n"
        "\n"
        "QUOTED_VAR='single_quoted'\n"
    )

    _load_dotenv(env_file)

    assert os.environ.get("DHAN_CLIENT_ID") == "MYCLIENT"
    assert os.environ.get("DHAN_ACCESS_TOKEN") == "mytoken123"
    assert os.environ.get("SIMPLE_VAR") == "hello"
    assert os.environ.get("QUOTED_VAR") == "single_quoted"

    # Clean up
    for key in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN", "SIMPLE_VAR", "QUOTED_VAR"):
        os.environ.pop(key, None)


def test_load_dotenv_ignores_comments_and_blanks(tmp_path):
    """Comments and blank lines should be skipped."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# full comment\n"
        "\n"
        "   \n"
        "VALID_KEY=valid_value\n"
    )

    _load_dotenv(env_file)

    assert os.environ.get("VALID_KEY") == "valid_value"

    # Clean up
    os.environ.pop("VALID_KEY", None)


def test_update_env_token(tmp_path):
    """_update_env_token should replace the DHAN_ACCESS_TOKEN value in the file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DHAN_CLIENT_ID=MYCLIENT\n"
        "DHAN_ACCESS_TOKEN=old_token_value\n"
        "OTHER_VAR=untouched\n"
    )

    _update_env_token(env_file, "new_token_value")

    content = env_file.read_text()
    assert "DHAN_ACCESS_TOKEN=new_token_value" in content
    assert "old_token_value" not in content
    # Other lines should be untouched
    assert "DHAN_CLIENT_ID=MYCLIENT" in content
    assert "OTHER_VAR=untouched" in content


def test_update_env_token_no_file(tmp_path):
    """_update_env_token should silently do nothing if the file does not exist."""
    missing = tmp_path / "nonexistent.env"
    # Should not raise
    _update_env_token(missing, "some_token")
