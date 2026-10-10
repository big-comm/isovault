"""Shared fixtures for ISOVault tests."""

import os
import sys

import pytest

# Untranslated strings regardless of the machine locale (gettext reads this per call)
os.environ["LANGUAGE"] = "C"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "usr", "share", "isovault"))

import models.settings as settings_module  # noqa: E402


@pytest.fixture(autouse=True)
def no_keyring(monkeypatch):
    """Never touch the real system keyring."""
    monkeypatch.setattr(settings_module, "_HAS_LIBSECRET", False)
