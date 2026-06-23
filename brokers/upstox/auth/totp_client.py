"""Upstox TOTP client — automated token generation via upstox-totp library.

This module provides a clean wrapper around the upstox-totp library for
automated token generation without manual browser intervention.

Usage::

    from brokers.upstox.auth.totp_client import UpstoxTotpClient
    from brokers.upstox.auth.config import UpstoxConnectionSettings
    
    settings = UpstoxSettingsLoader.from_env()
    client = UpstoxTotpClient(settings)
    token = client.generate_token()
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class UpstoxTotpClient:
    """Automated Upstox token generation using TOTP (Time-based One-Time Password).
    
    Wraps the upstox-totp library to provide:
    - Token generation using mobile, PIN, and TOTP secret
    - Environment variable configuration
    - Error handling with graceful degradation
    """
    
    def __init__(self, settings: Any) -> None:
        """Initialize TOTP client with connection settings.
        
        Args:
            settings: UpstoxConnectionSettings with mobile, pin, and totp_secret populated
        """
        self._settings = settings
        self._client = None
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize the upstox-totp client with environment variables."""
        try:
            # Set environment variables for upstox-totp library
            # Map our variable names to what upstox-totp expects
            os.environ["UPSTOX_CLIENT_ID"] = self._settings.client_id
            os.environ["UPSTOX_CLIENT_SECRET"] = self._settings.client_secret
            os.environ["UPSTOX_REDIRECT_URI"] = self._settings.redirect_uri
            os.environ["UPSTOX_USERNAME"] = self._settings.mobile  # Mobile number
            os.environ["UPSTOX_PASSWORD"] = self._settings.pin     # PIN
            os.environ["UPSTOX_PIN_CODE"] = self._settings.pin     # PIN (duplicate)
            os.environ["UPSTOX_TOTP_SECRET"] = self._settings.totp_secret
            os.environ["UPSTOX_DEBUG"] = "false"
            
            from upstox_totp import UpstoxTOTP
            self._client = UpstoxTOTP()
            logger.info("Upstox TOTP client initialized successfully")
        except ImportError as exc:
            logger.error("upstox-totp library not installed: %s", exc)
            raise RuntimeError(
                "upstox-totp library is required for TOTP auth mode. "
                "Install with: pip install upstox-totp"
            ) from exc
        except Exception as exc:
            logger.error("Failed to initialize Upstox TOTP client: %s", exc)
            raise
    
    def generate_token(self) -> dict[str, Any]:
        """Generate a new access token using TOTP.
        
        Returns:
            Dictionary with token information:
            - access_token: The generated access token
            - user_name: Upstox username
            - success: Boolean indicating success
            
        Raises:
            RuntimeError: If token generation fails
        """
        if not self._client:
            raise RuntimeError("TOTP client not initialized")
        
        try:
            response = self._client.app_token.get_access_token()
            
            if response.success and response.data:
                logger.info("TOTP token generated successfully for user: %s", response.data.user_name)
                return {
                    "access_token": response.data.access_token,
                    "user_name": response.data.user_name,
                    "success": True,
                }
            else:
                error_msg = "TOTP token generation failed"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except Exception as exc:
            logger.error("TOTP token generation error: %s", exc)
            raise RuntimeError(f"TOTP token generation failed: {exc}") from exc
    
    def validate_config(self) -> bool:
        """Validate that all required TOTP configuration is present.
        
        Returns:
            True if all required fields are populated
        """
        required = {
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
            "mobile": self._settings.mobile,
            "pin": self._settings.pin,
            "totp_secret": self._settings.totp_secret,
        }
        
        missing = [key for key, value in required.items() if not value]
        if missing:
            logger.warning("Missing TOTP configuration: %s", ", ".join(missing))
            return False
        
        return True
