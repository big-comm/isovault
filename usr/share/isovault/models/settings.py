"""
User settings persisted in an INI file (~/.config/isovault.conf).

Application preferences live in [general] and [ui]; every repository the
user manages is a profile in its own [profile:<id>] section.

The file holds S3 secrets, so it is always written with mode 0600. When
libsecret is available the credentials are also mirrored to the system
keyring (per profile) and used as a fallback if the file has none.
"""

import configparser
import copy
import logging
import os
import re
import stat
import tempfile
from typing import Any, Dict, List, Tuple

from config import (
    BUILTIN_PROFILES,
    CONFIG_FILE,
    DEFAULT_PROFILE,
    DEFAULT_WINDOW_SIZE,
    NEW_PROFILE,
    PROFILE_KEYS,
    ROOT_FOLDER,
)

logger = logging.getLogger(__name__)

try:
    import gi

    gi.require_version("Secret", "1")
    from gi.repository import Secret

    _SECRET_SCHEMA = Secret.Schema.new(
        "org.communitybig.isovault",
        Secret.SchemaFlags.NONE,
        {"key_type": Secret.SchemaAttributeType.STRING, "profile": Secret.SchemaAttributeType.STRING},
    )
    _HAS_LIBSECRET = True
except (ImportError, ValueError):
    _HAS_LIBSECRET = False

CREDENTIAL_KEYS = ("access_key", "secret_key")
CONNECTION_KEYS = ("access_key", "secret_key", "endpoint_url", "region_name", "bucket_name")
_PROFILE_SECTION = "profile:"

# Application preferences and their defaults; the type of the default
# decides how the value is parsed from the file.
DEFAULT_SETTINGS: Dict[str, Dict[str, Any]] = {
    "general": {
        "active_profile": DEFAULT_PROFILE,
        "last_directory": "",
        "last_upload_folder": "",
        "window_width": DEFAULT_WINDOW_SIZE[0],
        "window_height": DEFAULT_WINDOW_SIZE[1],
        "auto_refresh": True,
    },
    "ui": {
        "confirm_deletions": True,
        "auto_update_index": True,
        "show_index_files": False,
    },
}


def parse_folders(text: str) -> List[str]:
    """
    Folder list of a profile from "Gnome, XFCE, Root": trimmed, without
    duplicates or "/" (each folder is one level of the bucket). Never empty.
    """
    folders = []
    for name in text.split(","):
        name = name.replace("/", "").strip()
        if name and name.lower() not in (f.lower() for f in folders):
            folders.append(ROOT_FOLDER if name.lower() == ROOT_FOLDER.lower() else name)
    return folders or [ROOT_FOLDER]


class SettingsManager:
    """Loads, holds and saves preferences and profiles"""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.profiles: Dict[str, Dict[str, str]] = {}
        self._keyring_cache: Dict[Tuple[str, str], str] = {}
        self.load_settings()

    # Loading and saving

    def load_settings(self) -> bool:
        """Read the config file over the defaults. Returns False if it doesn't exist or can't be read."""
        parser = configparser.ConfigParser(interpolation=None)
        exists = os.path.exists(self.config_file)
        if exists:
            self._restrict_permissions()
            try:
                parser.read(self.config_file, encoding="utf-8")
            except configparser.Error as e:
                logger.error("Invalid config file %s: %s", self.config_file, e)
                parser = configparser.ConfigParser(interpolation=None)
                exists = False
        else:
            logger.info("Config file not found: %s", self.config_file)

        self._load_preferences(parser)
        self._load_profiles(parser)
        if self.settings["general"]["active_profile"] not in self.profiles:
            self.settings["general"]["active_profile"] = next(iter(self.profiles))
        for profile_id, profile in self.profiles.items():
            if not profile["access_key"]:
                self._load_credentials_from_keyring(profile_id, legacy=profile_id == DEFAULT_PROFILE)
        return exists

    def _load_preferences(self, parser: configparser.ConfigParser) -> None:
        # [web] show_index_files is read for files written before profiles existed
        sources = {("ui", "show_index_files"): ("web", "show_index_files")}
        for section, defaults in DEFAULT_SETTINGS.items():
            for key, default in defaults.items():
                where = (section, key)
                if not parser.has_option(section, key) and where in sources and parser.has_option(*sources[where]):
                    where = sources[where]
                if not parser.has_option(*where):
                    continue
                try:
                    if isinstance(default, bool):
                        value = parser.getboolean(*where)
                    elif isinstance(default, int):
                        value = parser.getint(*where)
                    else:
                        value = parser.get(*where)
                except ValueError:
                    logger.warning("Ignoring invalid value for [%s] %s", *where)
                    continue
                self.settings[section][key] = value

    def _load_profiles(self, parser: configparser.ConfigParser) -> None:
        self.profiles = {}
        for section in parser.sections():
            if section.startswith(_PROFILE_SECTION):
                profile_id = section[len(_PROFILE_SECTION):]
                profile = dict(NEW_PROFILE)
                profile.update({key: parser.get(section, key) for key in PROFILE_KEYS if parser.has_option(section, key)})
                profile["name"] = profile["name"] or profile_id
                # Built-in profiles saved before their bucket was known get it now
                if not profile["bucket_name"] and profile_id in BUILTIN_PROFILES:
                    profile["bucket_name"] = BUILTIN_PROFILES[profile_id]["bucket_name"]
                self.profiles[profile_id] = profile
        if self.profiles:
            return

        # First run, or a file from before profiles: create the built-in ones and
        # move the old single [s3]/[web] configuration into the default profile
        self.profiles = copy.deepcopy(BUILTIN_PROFILES)
        legacy = self.profiles[DEFAULT_PROFILE]
        for section, keys in (("s3", CONNECTION_KEYS), ("web", ("base_url", "page_style"))):
            for key in keys:
                if parser.has_option(section, key):
                    legacy[key] = parser.get(section, key)

    def save_settings(self) -> bool:
        """Write everything atomically with mode 0600."""
        parser = configparser.ConfigParser(interpolation=None)
        for section, values in self.settings.items():
            parser[section] = {key: str(value) for key, value in values.items()}
        for profile_id, profile in self.profiles.items():
            parser[_PROFILE_SECTION + profile_id] = {key: profile[key] for key in PROFILE_KEYS}

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

        for profile_id in self.profiles:
            self._store_credentials_in_keyring(profile_id)
        return True

    # Preferences

    def get(self, section: str, key: str) -> Any:
        """Current value of a preference (KeyError for unknown ones)."""
        return self.settings[section][key]

    def set(self, section: str, key: str, value: Any) -> None:
        """Change a preference in memory; call save_settings() to persist."""
        if key not in DEFAULT_SETTINGS.get(section, {}):
            raise KeyError(f"Unknown setting [{section}] {key}")
        self.settings[section][key] = value

    def reset_to_defaults(self) -> None:
        """Restore the application preferences; profiles are kept."""
        active = self.active_profile_id
        size = self.get_window_size()
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.settings["general"]["active_profile"] = active
        self.set_window_size(*size)

    def get_window_size(self) -> Tuple[int, int]:
        return self.settings["general"]["window_width"], self.settings["general"]["window_height"]

    def set_window_size(self, width: int, height: int) -> None:
        if width > 0 and height > 0:
            self.settings["general"]["window_width"] = width
            self.settings["general"]["window_height"] = height

    # Profiles

    @property
    def active_profile_id(self) -> str:
        return self.settings["general"]["active_profile"]

    @active_profile_id.setter
    def active_profile_id(self, profile_id: str) -> None:
        if profile_id not in self.profiles:
            raise KeyError(f"Unknown profile {profile_id}")
        self.settings["general"]["active_profile"] = profile_id

    @property
    def profile(self) -> Dict[str, str]:
        """The active profile (read-only view; use set_profile_value to change it)."""
        return dict(self.profiles[self.active_profile_id])

    def set_profile_value(self, key: str, value: str) -> None:
        """Change a value of the active profile in memory."""
        if key not in PROFILE_KEYS:
            raise KeyError(f"Unknown profile setting {key}")
        if key == "folders":
            value = ",".join(parse_folders(value))
        self.profiles[self.active_profile_id][key] = value

    def folders(self) -> List[str]:
        """Bucket folders of the active profile."""
        return parse_folders(self.profiles[self.active_profile_id]["folders"])

    def add_profile(self, name: str) -> str:
        """Create an empty profile and return its id (it does not become active)."""
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "profile"
        profile_id, number = base, 2
        while profile_id in self.profiles:
            profile_id, number = f"{base}-{number}", number + 1
        self.profiles[profile_id] = {**NEW_PROFILE, "name": name.strip() or profile_id}
        return profile_id

    def remove_profile(self, profile_id: str) -> None:
        """Delete a profile (the last one can't be removed)."""
        if len(self.profiles) <= 1:
            raise ValueError("At least one profile is required")
        del self.profiles[profile_id]
        self._delete_credentials_from_keyring(profile_id)
        if self.active_profile_id not in self.profiles:
            self.active_profile_id = next(iter(self.profiles))

    def get_s3_config(self) -> Dict[str, str]:
        profile = self.profiles[self.active_profile_id]
        return {key: profile[key] for key in CONNECTION_KEYS}

    def missing_connection_fields(self) -> List[str]:
        """Required connection values the active profile doesn't have yet."""
        s3 = self.get_s3_config()
        return [key for key in ("access_key", "secret_key", "endpoint_url", "bucket_name") if not s3[key]]

    def has_s3_credentials(self) -> bool:
        """True when the active profile has every value needed to connect."""
        s3 = self.get_s3_config()
        return all(s3[key] for key in ("access_key", "secret_key", "endpoint_url", "bucket_name"))

    # Internals

    def _restrict_permissions(self) -> None:
        """Older versions wrote the file world-readable; fix it on load."""
        try:
            mode = stat.S_IMODE(os.stat(self.config_file).st_mode)
            if mode & 0o077:
                os.chmod(self.config_file, 0o600)
        except OSError as e:
            logger.warning("Could not restrict permissions of %s: %s", self.config_file, e)

    def _load_credentials_from_keyring(self, profile_id: str, legacy: bool = False) -> None:
        """Fill missing credentials from the keyring; legacy also accepts entries saved before profiles."""
        if not _HAS_LIBSECRET:
            return
        for key in CREDENTIAL_KEYS:
            try:
                value = Secret.password_lookup_sync(_SECRET_SCHEMA, {"key_type": key, "profile": profile_id}, None)
                if not value and legacy:
                    value = self._lookup_legacy_credential(key)
            except Exception as e:  # keyring is optional
                logger.debug("Keyring lookup failed: %s", e)
                return
            if value:
                self.profiles[profile_id][key] = value

    @staticmethod
    def _lookup_legacy_credential(key: str) -> str:
        """
        Credential stored before profiles existed (no "profile" attribute).
        A plain lookup by key_type would also match other profiles' entries.
        """
        flags = Secret.SearchFlags.ALL | Secret.SearchFlags.UNLOCK
        for item in Secret.password_search_sync(_SECRET_SCHEMA, {"key_type": key}, flags, None) or []:
            if "profile" not in item.get_attributes():
                # Retrievable interface method: works with every libsecret backend
                secret = item.retrieve_secret_sync(None)
                return secret.get_text() if secret else ""
        return ""

    def _store_credentials_in_keyring(self, profile_id: str) -> None:
        if not _HAS_LIBSECRET:
            return
        for key in CREDENTIAL_KEYS:
            value = self.profiles[profile_id][key]
            if not value or self._keyring_cache.get((profile_id, key)) == value:
                continue
            try:
                Secret.password_store_sync(
                    _SECRET_SCHEMA,
                    {"key_type": key, "profile": profile_id},
                    Secret.COLLECTION_DEFAULT,
                    f"isovault-{profile_id}-{key}",
                    value,
                    None,
                )
                self._keyring_cache[(profile_id, key)] = value
            except Exception as e:  # keyring is optional, the file is the primary store
                logger.debug("Keyring store failed: %s", e)
                return

    def _delete_credentials_from_keyring(self, profile_id: str) -> None:
        if not _HAS_LIBSECRET:
            return
        for key in CREDENTIAL_KEYS:
            self._keyring_cache.pop((profile_id, key), None)
            try:
                Secret.password_clear_sync(_SECRET_SCHEMA, {"key_type": key, "profile": profile_id}, None)
            except Exception as e:
                logger.debug("Keyring clear failed: %s", e)
