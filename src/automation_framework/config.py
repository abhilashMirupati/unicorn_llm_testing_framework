"""
Configuration Loader
--------------------

This module centralises configuration management.  It loads settings
from a YAML file (`config/config.yaml`) and overlays environment
variables defined in `.env` files.  When a key exists in both places
the environment variable takes precedence.

Missing or invalid settings are logged via the framework’s logger.
Consumers should use the `Config.get` method to retrieve values with
optional defaults.
"""

import os
import logging
from pathlib import Path
from typing import Any, Optional

import yaml
try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    # Provide a no-op fallback if python-dotenv is unavailable
    def load_dotenv(*args, **kwargs):  # type: ignore[no-redef]
        return None

from .utils.logger import get_logger


class Config:
    """Load YAML and environment based configuration values."""

    def __init__(self, yaml_path: Optional[str] = None) -> None:
        # Load environment variables from .env file if present
        load_dotenv()
        self.logger = get_logger(__name__)

        # Determine path to YAML configuration
        if yaml_path is None:
            # default relative path within repository
            yaml_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        self.yaml_path = Path(yaml_path)

        self.data: dict[str, Any] = {}
        if self.yaml_path.exists():
            try:
                with open(self.yaml_path, "r", encoding="utf-8") as f:
                    self.data = yaml.safe_load(f) or {}
            except Exception as exc:
                self.logger.error("Failed to load YAML config from %s: %s", self.yaml_path, exc)
        else:
            self.logger.warning("Configuration file %s not found", self.yaml_path)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Retrieve a configuration value.

        Values are looked up in the environment first, then in the YAML
        structure.  Dotted keys (e.g. `database.url`) traverse nested
        dictionaries.
        """
        env_key = dotted_key.upper().replace(".", "_")
        env_val = os.getenv(env_key)
        if env_val is not None:
            return env_val
        # Walk through nested dicts using dotted notation
        current: Any = self.data
        for part in dotted_key.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def require(self, dotted_key: str) -> Any:
        """Retrieve a configuration value or log an error if missing."""
        value = self.get(dotted_key)
        if value is None:
            self.logger.error("Missing required configuration value: %s", dotted_key)
        return value


__all__ = ["Config"]