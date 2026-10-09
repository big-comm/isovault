"""Tests for SettingsManager."""

import os
import stat

import pytest

import models.settings as settings_module
from models.settings import DEFAULT_SETTINGS, SettingsManager


@pytest.fixture
def config_file(tmp_path):
    return str(tmp_path / "config" / "isovault.conf")


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class TestDefaults:
    def test_missing_file_gives_defaults(self, config_file):
        manager = SettingsManager(config_file)
        assert manager.settings == DEFAULT_SETTINGS
        assert manager.settings is not DEFAULT_SETTINGS
        assert not os.path.exists(config_file)

    def test_defaults_are_not_shared(self, config_file):
        SettingsManager(config_file).set("web", "base_url", "changed")
        assert SettingsManager(config_file).get("web", "base_url") == DEFAULT_SETTINGS["web"]["base_url"]


class TestSaveAndLoad:
    def test_round_trip_keeps_types(self, config_file):
        manager = SettingsManager(config_file)
        manager.set("general", "auto_refresh", False)
        manager.set_window_size(800, 600)
        manager.set("web", "base_url", "https://example.com")
        assert manager.save_settings()

        loaded = SettingsManager(config_file)
        assert loaded.get("general", "auto_refresh") is False
        assert loaded.get_window_size() == (800, 600)
        assert loaded.get("web", "base_url") == "https://example.com"

    def test_percent_sign_in_secret(self, config_file):
        """Regression: configparser interpolation broke on "%" in secrets."""
        manager = SettingsManager(config_file)
        manager.set("s3", "secret_key", "a%b%%c")
        manager.save_settings()
        assert SettingsManager(config_file).get("s3", "secret_key") == "a%b%%c"

    def test_file_is_private(self, config_file):
        manager = SettingsManager(config_file)
        manager.set("s3", "secret_key", "secret")
        manager.save_settings()
        assert mode_of(config_file) == 0o600

    def test_existing_world_readable_file_is_fixed_on_load(self, config_file):
        os.makedirs(os.path.dirname(config_file))
        with open(config_file, "w") as f:
            f.write("[s3]\nsecret_key = secret\n")
        os.chmod(config_file, 0o644)

        SettingsManager(config_file)
        assert mode_of(config_file) == 0o600

    def test_no_temp_files_left(self, config_file):
        SettingsManager(config_file).save_settings()
        assert os.listdir(os.path.dirname(config_file)) == ["isovault.conf"]

    def test_invalid_values_keep_defaults(self, config_file):
        os.makedirs(os.path.dirname(config_file))
        with open(config_file, "w") as f:
            f.write("[general]\nwindow_width = wide\nauto_refresh = maybe\nwindow_height = 500\n")

        manager = SettingsManager(config_file)
        assert manager.get("general", "window_width") == DEFAULT_SETTINGS["general"]["window_width"]
        assert manager.get("general", "auto_refresh") is True
        assert manager.get("general", "window_height") == 500

    def test_legacy_keys_are_dropped(self, config_file):
        os.makedirs(os.path.dirname(config_file))
        with open(config_file, "w") as f:
            f.write("[web]\nindex_file = index.html\n[ui]\nshow_progress_details = True\n")

        manager = SettingsManager(config_file)
        manager.save_settings()
        content = open(config_file).read()
        assert "\nindex_file" not in content
        assert "show_progress_details" not in content

    def test_corrupt_file_keeps_defaults(self, config_file):
        os.makedirs(os.path.dirname(config_file))
        with open(config_file, "w") as f:
            f.write("not an ini file")
        assert SettingsManager(config_file).settings == DEFAULT_SETTINGS

    def test_save_failure_returns_false(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("")
        manager = SettingsManager(str(blocker / "isovault.conf"))
        assert manager.save_settings() is False


class TestAccessors:
    def test_set_unknown_key_raises(self, config_file):
        with pytest.raises(KeyError):
            SettingsManager(config_file).set("web", "typo", "x")

    def test_has_s3_credentials_requires_every_field(self, config_file):
        manager = SettingsManager(config_file)
        assert manager.has_s3_credentials() is False
        manager.set("s3", "access_key", "a")
        manager.set("s3", "secret_key", "b")
        assert manager.has_s3_credentials() is True
        manager.set("s3", "bucket_name", "")
        assert manager.has_s3_credentials() is False

    def test_window_size_ignores_invalid(self, config_file):
        manager = SettingsManager(config_file)
        before = manager.get_window_size()
        manager.set_window_size(0, 500)
        assert manager.get_window_size() == before

    def test_reset_keeps_credentials(self, config_file):
        manager = SettingsManager(config_file)
        manager.set("s3", "access_key", "AK")
        manager.set("s3", "secret_key", "SK")
        manager.set("s3", "bucket_name", "other")
        manager.set("ui", "confirm_deletions", False)

        manager.reset_to_defaults()

        assert manager.get("s3", "access_key") == "AK"
        assert manager.get("s3", "secret_key") == "SK"
        assert manager.get("s3", "bucket_name") == DEFAULT_SETTINGS["s3"]["bucket_name"]
        assert manager.get("ui", "confirm_deletions") is True


class FakeSecret:
    """Minimal stand-in for gi.repository.Secret."""

    COLLECTION_DEFAULT = "default"

    def __init__(self, stored=None):
        self.stored = dict(stored or {})
        self.store_calls = 0

    def password_lookup_sync(self, _schema, attributes, _cancellable):
        return self.stored.get(attributes["key_type"])

    def password_store_sync(self, _schema, attributes, _collection, _label, value, _cancellable):
        self.store_calls += 1
        self.stored[attributes["key_type"]] = value
        return True


class TestKeyring:
    @pytest.fixture
    def secret(self, monkeypatch):
        fake = FakeSecret({"access_key": "KR-AK", "secret_key": "KR-SK"})
        monkeypatch.setattr(settings_module, "_HAS_LIBSECRET", True)
        monkeypatch.setattr(settings_module, "Secret", fake, raising=False)
        monkeypatch.setattr(settings_module, "_SECRET_SCHEMA", None, raising=False)
        return fake

    def test_credentials_fall_back_to_keyring(self, config_file, secret):
        manager = SettingsManager(config_file)
        assert manager.get("s3", "access_key") == "KR-AK"
        assert manager.get("s3", "secret_key") == "KR-SK"

    def test_file_credentials_win(self, config_file, secret):
        os.makedirs(os.path.dirname(config_file))
        with open(config_file, "w") as f:
            f.write("[s3]\naccess_key = FILE-AK\nsecret_key = FILE-SK\n")
        assert SettingsManager(config_file).get("s3", "access_key") == "FILE-AK"

    def test_keyring_written_only_when_changed(self, config_file, secret):
        manager = SettingsManager(config_file)
        manager.save_settings()
        manager.save_settings()
        assert secret.store_calls == 0  # values came from the keyring already

        manager.set("s3", "secret_key", "NEW")
        manager.save_settings()
        manager.save_settings()
        assert secret.store_calls == 1
        assert secret.stored["secret_key"] == "NEW"
