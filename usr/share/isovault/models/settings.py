"""
User settings persisted in an INI file (~/.config/isovault.conf).

The file holds the S3 secret, so it is always written with mode 0600.
When libsecret is available the credentials are also mirrored to the
system keyring and used as a fallback if the file has none.
"""

import configparser
import copy
import logging
import os
import stat
import tempfile
from typing import Any, Dict, Tuple

from config import CONFIG_FILE, DEFAULT_BASE_URL, DEFAULT_S3_CONFIG, DEFAULT_WINDOW_SIZE

logger = logging.getLogger(__name__)

try:
    import gi

    gi.require_version("Secret", "1")
    from gi.repository import Secret

    _SECRET_SCHEMA = Secret.Schema.new(
        "org.communitybig.isovault",
        Secret.SchemaFlags.NONE,
        {"key_type": Secret.SchemaAttributeType.STRING},
    )
    _HAS_LIBSECRET = True
except (ImportError, ValueError):
    _HAS_LIBSECRET = False

CREDENTIAL_KEYS = ("access_key", "secret_key")

# Every known setting and its default value; the type of the default
# decides how the value is parsed from the file.
DEFAULT_SETTINGS: Dict[str, Dict[str, Any]] = {
    "general": {
        "last_directory": "",
        "last_upload_folder": "",
        "window_width": DEFAULT_WINDOW_SIZE[0],
        "window_height": DEFAULT_WINDOW_SIZE[1],
        "auto_refresh": True,
    },
    "s3": dict(DEFAULT_S3_CONFIG),
    "web": {
        "base_url": DEFAULT_BASE_URL,
        "show_index_files": False,
    },
    "ui": {
        "confirm_deletions": True,
        "auto_update_index": True,
    },
}


class SettingsManager:
    """Loads, holds and saves the user settings"""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self._keyring_cache: Dict[str, str] = {}
        self.load_settings()

    def load_settings(self) -> bool:
        """Read the config file over the defaults. Returns False if it doesn't exist or can't be read."""
        if not os.path.exists(self.config_file):
            logger.info("Config file not found: %s", self.config_file)
            self._load_credentials_from_keyring()
            return False

        self._restrict_permissions()

        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(self.config_file, encoding="utf-8")
        except configparser.Error as e:
            logger.error("Invalid config file %s: %s", self.config_file, e)
            return False

        for section, defaults in DEFAULT_SETTINGS.items():
            if not parser.has_section(section):
                continue
            for key, default in defaults.items():
                if not parser.has_option(section, key):
                    continue
                try:
                    if isinstance(default, bool):
                        value = parser.getboolean(section, key)
                    elif isinstance(default, int):
                        value = parser.getint(section, key)
                    else:
                        value = parser.get(section, key)
                except ValueError:
                    logger.warning("Ignoring invalid value for [%s] %s", section, key)
                    continue
                self.settings[section][key] = value

        if not self.settings["s3"]["access_key"]:
            self._load_credentials_from_keyring()

        return True

    def save_settings(self) -> bool:
        """Write all settings atomically with mode 0600."""
        parser = configparser.ConfigParser(interpolation=None)
        for section, values in self.settings.items():
            parser[section] = {key: str(value) for key, value in values.items()}

        config_dir = os.path.dirname(self.config_file)
        try:
            os.makedirs(config_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=config_dir, prefix=".isovault-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:  # mkstemp creates it as 0600
                    parser.write(f)
                os.replace(tmp_path, self.config_file)
            except BaseException:
                os.unlink(tmp_path)
                raise
        except OSError as e:
            logger.error("Error saving settings to %s: %s", self.config_file, e)
            return False

        self._store_credentials_in_keyring()
        return True

    def get(self, section: str, key: str) -> Any:
        """Current value of a setting (KeyError for unknown settings)."""
        return self.settings[section][key]

    def set(self, section: str, key: str, value: Any) -> None:
        """Change a setting in memory; call save_settings() to persist."""
        if key not in DEFAULT_SETTINGS.get(section, {}):
            raise KeyError(f"Unknown setting [{section}] {key}")
        self.settings[section][key] = value

    def reset_to_defaults(self) -> None:
        """Restore defaults for everything except the S3 credentials."""
        credentials = {key: self.settings["s3"][key] for key in CREDENTIAL_KEYS}
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.settings["s3"].update(credentials)

    def get_s3_config(self) -> Dict[str, str]:
        return dict(self.settings["s3"])

    def has_s3_credentials(self) -> bool:
        """True when every value needed to connect is filled in."""
        s3 = self.settings["s3"]
        return all(s3[key] for key in ("access_key", "secret_key", "endpoint_url", "bucket_name"))

    def get_window_size(self) -> Tuple[int, int]:
        return self.settings["general"]["window_width"], self.settings["general"]["window_height"]

    def set_window_size(self, width: int, height: int) -> None:
        if width > 0 and height > 0:
            self.settings["general"]["window_width"] = width
            self.settings["general"]["window_height"] = height

    # Internals

    def _restrict_permissions(self) -> None:
        """Older versions wrote the file world-readable; fix it on load."""
        try:
            mode = stat.S_IMODE(os.stat(self.config_file).st_mode)
            if mode & 0o077:
                os.chmod(self.config_file, 0o600)
        except OSError as e:
            logger.warning("Could not restrict permissions of %s: %s", self.config_file, e)

    def _load_credentials_from_keyring(self) -> None:
        if not _HAS_LIBSECRET:
            return
        for key in CREDENTIAL_KEYS:
            try:
                value = Secret.password_lookup_sync(_SECRET_SCHEMA, {"key_type": key}, None)
            except Exception as e:  # keyring is optional
                logger.debug("Keyring lookup failed: %s", e)
                return
            if value:
                self.settings["s3"][key] = value
                self._keyring_cache[key] = value

    def _store_credentials_in_keyring(self) -> None:
        if not _HAS_LIBSECRET:
            return
        for key in CREDENTIAL_KEYS:
            value = self.settings["s3"][key]
            if not value or self._keyring_cache.get(key) == value:
                continue
            try:
                Secret.password_store_sync(
                    _SECRET_SCHEMA,
                    {"key_type": key},
                    Secret.COLLECTION_DEFAULT,
                    f"isovault-{key}",
                    value,
                    None,
                )
                self._keyring_cache[key] = value
            except Exception as e:  # keyring is optional, the file is the primary store
                logger.debug("Keyring store failed: %s", e)
                return
