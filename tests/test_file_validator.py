"""Tests for FileValidator."""

import pytest

import services.file_validator as validator_module
from services.file_validator import FileValidator


def write(path, size):
    path.write_bytes(b"\0" * size)
    return str(path)


class TestValidateFile:
    @pytest.mark.parametrize("name", ["a.iso", "a.md5", "a.ISO", "a.MD5", "a.Iso"])
    def test_supported_extensions_any_case(self, tmp_path, name):
        ok, _msg = FileValidator.validate_file(write(tmp_path / name, 10))
        assert ok is True

    def test_nonexistent(self, tmp_path):
        ok, _msg = FileValidator.validate_file(str(tmp_path / "missing.iso"))
        assert ok is False

    def test_directory(self, tmp_path):
        ok, _msg = FileValidator.validate_file(str(tmp_path))
        assert ok is False

    def test_unsupported_extension(self, tmp_path):
        ok, _msg = FileValidator.validate_file(write(tmp_path / "a.txt", 10))
        assert ok is False

    def test_empty(self, tmp_path):
        ok, _msg = FileValidator.validate_file(write(tmp_path / "a.iso", 0))
        assert ok is False

    def test_too_large(self, tmp_path, monkeypatch):
        monkeypatch.setattr(validator_module, "MAX_FILE_SIZE", 100)
        assert FileValidator.validate_file(write(tmp_path / "a.iso", 100))[0] is True
        assert FileValidator.validate_file(write(tmp_path / "b.iso", 101))[0] is False


class TestValidateMultipleFiles:
    def test_splits_valid_and_invalid(self, tmp_path):
        good = write(tmp_path / "good.iso", 10)
        bad = write(tmp_path / "bad.txt", 10)

        valid, invalid = FileValidator.validate_multiple_files([good, bad])

        assert valid == [good]
        assert [name for name, _reason in invalid] == ["bad.txt"]
