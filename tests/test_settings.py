"""Tests for SettingsManager (preferences and profiles)."""

import configparser
import os
import stat

import pytest

import models.settings as settings_module
from config import BUILTIN_PROFILES, DEFAULT_PROFILE
from models.settings import DEFAULT_SETTINGS, SettingsManager, parse_folders


@pytest.fixture
def config_file(tmp_path):
    return str(tmp_path / "config" / "isovault.conf")


def write_config(path, text, mode=0o600):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, mode)


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def sections_of(path):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path)
    return parser.sections()


class TestDefaults:
    def test_first_run_creates_builtin_profiles(self, config_file):
        manager = SettingsManager(config_file)
        assert list(manager.profiles) == ["bigcommunity", "biglinux"]
        assert manager.active_profile_id == DEFAULT_PROFILE
        assert manager.profile["name"] == "BigCommunity"
        assert manager.profiles["biglinux"]["page_style"] == "biglinux"
        assert manager.settings == DEFAULT_SETTINGS
        assert not os.path.exists(config_file)

    def test_defaults_are_not_shared(self, config_file):
        SettingsManager(config_file).set_profile_value("base_url", "changed")
        assert SettingsManager(config_file).profile["base_url"] == BUILTIN_PROFILES[DEFAULT_PROFILE]["base_url"]


class TestSaveAndLoad:
    def test_round_trip(self, config_file):
        manager = SettingsManager(config_file)
        manager.set("general", "auto_refresh", False)
        manager.set_window_size(800, 600)
        manager.set_profile_value("base_url", "https://example.com")
        manager.active_profile_id = "biglinux"
        manager.set_profile_value("bucket_name", "bl-bucket")
        assert manager.save_settings()

        loaded = SettingsManager(config_file)
        assert loaded.get("general", "auto_refresh") is False
        assert loaded.get_window_size() == (800, 600)
        assert loaded.active_profile_id == "biglinux"
        assert loaded.profile["bucket_name"] == "bl-bucket"
        assert loaded.profiles["bigcommunity"]["base_url"] == "https://example.com"

    def test_profiles_are_sections(self, config_file):
        SettingsManager(config_file).save_settings()
        assert sections_of(config_file) == ["general", "ui", "profile:bigcommunity", "profile:biglinux"]

    def test_percent_sign_in_secret(self, config_file):
        """Regression: configparser interpolation broke on "%" in secrets."""
        manager = SettingsManager(config_file)
        manager.set_profile_value("secret_key", "a%b%%c")
        manager.save_settings()
        assert SettingsManager(config_file).profile["secret_key"] == "a%b%%c"

    def test_file_is_private(self, config_file):
        manager = SettingsManager(config_file)
        manager.set_profile_value("secret_key", "secret")
        manager.save_settings()
        assert mode_of(config_file) == 0o600

    def test_existing_world_readable_file_is_fixed_on_load(self, config_file):
        write_config(config_file, "[s3]\nsecret_key = secret\n", mode=0o644)
        SettingsManager(config_file)
        assert mode_of(config_file) == 0o600

    def test_no_temp_files_left(self, config_file):
        SettingsManager(config_file).save_settings()
        assert os.listdir(os.path.dirname(config_file)) == ["isovault.conf"]

    def test_invalid_values_keep_defaults(self, config_file):
        write_config(config_file, "[general]\nwindow_width = wide\nauto_refresh = maybe\nwindow_height = 500\n")
        manager = SettingsManager(config_file)
        assert manager.get("general", "window_width") == DEFAULT_SETTINGS["general"]["window_width"]
        assert manager.get("general", "auto_refresh") is True
        assert manager.get("general", "window_height") == 500

    def test_corrupt_file_keeps_defaults(self, config_file):
        write_config(config_file, "not an ini file")
        manager = SettingsManager(config_file)
        assert manager.settings == DEFAULT_SETTINGS
        assert list(manager.profiles) == ["bigcommunity", "biglinux"]

    def test_save_failure_returns_false(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("")
        assert SettingsManager(str(blocker / "isovault.conf")).save_settings() is False

    def test_unknown_active_profile_falls_back(self, config_file):
        write_config(config_file, "[general]\nactive_profile = gone\n[profile:mine]\nname = Mine\n")
        manager = SettingsManager(config_file)
        assert manager.active_profile_id == "mine"


class TestMigration:
    LEGACY = (
        "[general]\nwindow_width = 900\n"
        "[s3]\naccess_key = AK\nsecret_key = SK\nendpoint_url = https://s3.example\n"
        "region_name = eu\nbucket_name = old-bucket\n"
        "[web]\nbase_url = https://old.example\nshow_index_files = True\npage_style = biglinux\n"
        "[ui]\nconfirm_deletions = False\nshow_progress_details = True\n"
    )

    def test_single_configuration_becomes_default_profile(self, config_file):
        write_config(config_file, self.LEGACY)
        manager = SettingsManager(config_file)

        profile = manager.profiles[DEFAULT_PROFILE]
        assert (profile["access_key"], profile["secret_key"]) == ("AK", "SK")
        assert profile["endpoint_url"] == "https://s3.example"
        assert profile["region_name"] == "eu"
        assert profile["bucket_name"] == "old-bucket"
        assert profile["base_url"] == "https://old.example"
        assert profile["page_style"] == "biglinux"
        assert manager.profiles["biglinux"]["access_key"] == ""  # the new profile starts empty
        assert manager.get("ui", "show_index_files") is True
        assert manager.get("ui", "confirm_deletions") is False
        assert manager.get("general", "window_width") == 900

    def test_old_sections_are_dropped_on_save(self, config_file):
        write_config(config_file, self.LEGACY)
        SettingsManager(config_file).save_settings()
        assert "s3" not in sections_of(config_file) and "web" not in sections_of(config_file)
        assert SettingsManager(config_file).profiles[DEFAULT_PROFILE]["access_key"] == "AK"


class TestProfiles:
    def test_add_profile_unique_ids(self, config_file):
        manager = SettingsManager(config_file)
        assert manager.add_profile("My Repo!") == "my-repo"
        assert manager.add_profile("BigLinux") == "biglinux-2"
        assert manager.profiles["my-repo"]["name"] == "My Repo!"
        assert manager.active_profile_id == DEFAULT_PROFILE  # adding doesn't switch

    def test_remove_profile(self, config_file):
        manager = SettingsManager(config_file)
        manager.active_profile_id = "biglinux"
        manager.remove_profile("biglinux")
        assert list(manager.profiles) == ["bigcommunity"]
        assert manager.active_profile_id == "bigcommunity"
        with pytest.raises(ValueError):
            manager.remove_profile("bigcommunity")

    def test_unknown_keys_and_profiles(self, config_file):
        manager = SettingsManager(config_file)
        with pytest.raises(KeyError):
            manager.set_profile_value("typo", "x")
        with pytest.raises(KeyError):
            manager.active_profile_id = "nope"
        with pytest.raises(KeyError):
            manager.set("general", "typo", 1)

    def test_profile_is_a_copy(self, config_file):
        manager = SettingsManager(config_file)
        manager.profile["name"] = "changed"
        assert manager.profile["name"] == "BigCommunity"

    def test_folders(self, config_file):
        manager = SettingsManager(config_file)
        assert manager.folders() == ["Gnome", "Cinnamon", "XFCE", "KDE", "Root"]
        manager.active_profile_id = "biglinux"
        assert manager.folders() == ["Root"]
        manager.set_profile_value("folders", " KDE, root , kde, a/b ,,")
        assert manager.profile["folders"] == "KDE,Root,ab"

    @pytest.mark.parametrize(
        "text, expected",
        [("", ["Root"]), (" , ", ["Root"]), ("ROOT", ["Root"]), ("XFCE,Gnome", ["XFCE", "Gnome"]), ("a/", ["a"])],
    )
    def test_parse_folders(self, text, expected):
        assert parse_folders(text) == expected

    def test_has_s3_credentials_uses_active_profile(self, config_file):
        manager = SettingsManager(config_file)
        assert manager.has_s3_credentials() is False
        manager.set_profile_value("access_key", "a")
        manager.set_profile_value("secret_key", "b")
        assert manager.has_s3_credentials() is True
        manager.active_profile_id = "biglinux"  # no bucket and no keys yet
        assert manager.has_s3_credentials() is False

    def test_reset_keeps_profiles(self, config_file):
        manager = SettingsManager(config_file)
        manager.active_profile_id = "biglinux"
        manager.set_profile_value("access_key", "AK")
        manager.set("ui", "confirm_deletions", False)
        manager.set_window_size(900, 700)

        manager.reset_to_defaults()

        assert manager.get("ui", "confirm_deletions") is True
        assert manager.active_profile_id == "biglinux"
        assert manager.profile["access_key"] == "AK"
        assert manager.get_window_size() == (900, 700)


class FakeItem:
    def __init__(self, attributes, value):
        self._attributes, self._value = dict(attributes), value

    def get_attributes(self):
        return self._attributes

    def retrieve_secret_sync(self, _cancellable):
        return type("Value", (), {"get_text": lambda _self: self._value})()


class FakeSecret:
    """Minimal stand-in for gi.repository.Secret with attribute matching."""

    COLLECTION_DEFAULT = "default"

    class SearchFlags:
        ALL, UNLOCK = 1, 2

    def __init__(self, stored=None):
        self.stored = dict(stored or {})  # frozenset(attributes) -> value
        self.store_calls = 0

    def _find(self, query):
        query = set(query.items())
        return next((attrs for attrs in self.stored if query <= set(attrs)), None)

    def password_lookup_sync(self, _schema, attributes, _cancellable):
        found = self._find(attributes)
        return self.stored[found] if found else None

    def password_store_sync(self, _schema, attributes, _collection, _label, value, _cancellable):
        self.store_calls += 1
        self.stored[frozenset(attributes.items())] = value
        return True

    def password_search_sync(self, _schema, attributes, _flags, _cancellable):
        query = set(attributes.items())
        return [FakeItem(attrs, value) for attrs, value in self.stored.items() if query <= set(attrs)]

    def password_clear_sync(self, _schema, attributes, _cancellable):
        found = self._find(attributes)
        if found:
            del self.stored[found]
        return bool(found)


def entry(key, profile=None, value="x"):
    attrs = {"key_type": key, **({"profile": profile} if profile else {})}
    return frozenset(attrs.items()), value


class TestKeyring:
    @pytest.fixture
    def secret(self, monkeypatch):
        fake = FakeSecret()
        monkeypatch.setattr(settings_module, "_HAS_LIBSECRET", True)
        monkeypatch.setattr(settings_module, "Secret", fake, raising=False)
        monkeypatch.setattr(settings_module, "_SECRET_SCHEMA", None, raising=False)
        return fake

    def test_per_profile_credentials(self, config_file, secret):
        secret.stored.update([entry("access_key", "biglinux", "BL-AK"), entry("secret_key", "biglinux", "BL-SK")])
        manager = SettingsManager(config_file)
        assert manager.profiles["biglinux"]["access_key"] == "BL-AK"
        assert manager.profiles["bigcommunity"]["access_key"] == ""

    def test_entries_from_before_profiles_go_to_default_profile(self, config_file, secret):
        secret.stored.update([entry("access_key", value="OLD-AK"), entry("secret_key", value="OLD-SK")])
        manager = SettingsManager(config_file)
        assert manager.profiles[DEFAULT_PROFILE]["access_key"] == "OLD-AK"
        assert manager.profiles["biglinux"]["access_key"] == ""

    def test_legacy_lookup_ignores_other_profiles(self, config_file, secret):
        """Regression: a lookup by key_type alone returned another profile's key."""
        secret.stored.update([entry("access_key", "biglinux", "BL-AK"), entry("access_key", value="OLD-AK")])
        manager = SettingsManager(config_file)
        assert manager.profiles[DEFAULT_PROFILE]["access_key"] == "OLD-AK"
        assert manager.profiles["biglinux"]["access_key"] == "BL-AK"

    def test_file_credentials_win(self, config_file, secret):
        secret.stored.update([entry("access_key", DEFAULT_PROFILE, "KR")])
        write_config(config_file, "[profile:bigcommunity]\naccess_key = FILE\nsecret_key = S\n")
        assert SettingsManager(config_file).profile["access_key"] == "FILE"

    def test_written_per_profile_only_when_changed(self, config_file, secret):
        manager = SettingsManager(config_file)
        manager.set_profile_value("access_key", "AK")
        manager.set_profile_value("secret_key", "SK")
        manager.save_settings()
        manager.save_settings()
        assert secret.store_calls == 2
        assert secret.stored[frozenset({"key_type": "access_key", "profile": DEFAULT_PROFILE}.items())] == "AK"

        manager.set_profile_value("secret_key", "NEW")
        manager.save_settings()
        assert secret.store_calls == 3

    def test_removing_a_profile_clears_its_secrets(self, config_file, secret):
        manager = SettingsManager(config_file)
        manager.active_profile_id = "biglinux"
        manager.set_profile_value("access_key", "AK")
        manager.set_profile_value("secret_key", "SK")
        manager.save_settings()

        manager.remove_profile("biglinux")

        assert all(dict(attrs).get("profile") != "biglinux" for attrs in secret.stored)
