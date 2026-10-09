"""Tests for utils.helpers."""

import pytest

from tests.factories import make_file
from utils.helpers import extract_md5, format_file_size, format_size_short, pair_iso_with_md5

HASH = "d41d8cd98f00b204e9800998ecf8427e"


class TestFormatFileSize:
    @pytest.mark.parametrize(
        "size, expected",
        [
            (0, "0 B"),
            (1023, "1023 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (5 * 1024**2, "5.0 MB"),
            (int(3.5 * 1024**3), "3.5 GB"),
            (2 * 1024**4, "2.0 TB"),
            (3 * 1024**5, "3072.0 TB"),  # TB is the largest unit
        ],
    )
    def test_values(self, size, expected):
        assert format_file_size(size) == expected


class TestFormatSizeShort:
    @pytest.mark.parametrize(
        "size, expected",
        [
            (0, "0"),
            (72, "72"),
            (1023, "1023"),
            (4096, "4,0K"),
            (40 * 1024, "40K"),
            (int(5.04 * 1024**3), "5,0G"),
            (int(5.1 * 1024**3), "5,1G"),
            (12 * 1024**4, "12T"),
        ],
    )
    def test_values(self, size, expected):
        assert format_size_short(size) == expected


class TestExtractMD5:
    def test_md5sum_output(self):
        assert extract_md5(f"{HASH}  biglinux.iso\n") == HASH

    def test_uppercase_is_lowered(self):
        assert extract_md5(HASH.upper()) == HASH

    def test_hash_inside_filename(self):
        assert extract_md5(f"image_{HASH}.md5") == HASH

    def test_sha256_is_not_an_md5(self):
        assert extract_md5("a" * 64) is None

    @pytest.mark.parametrize("text", ["", "no hash here", "abc123", "'); alert('xss'); //"])
    def test_no_hash(self, text):
        assert extract_md5(text) is None


class TestPairIsoWithMD5:
    def test_iso_md5_suffix(self):
        files = [make_file("XFCE/big.iso"), make_file("XFCE/big.iso.md5")]
        [(iso, md5)] = pair_iso_with_md5(files)
        assert iso["name"] == "big.iso"
        assert md5["name"] == "big.iso.md5"

    def test_plain_md5_suffix(self):
        files = [make_file("big.iso"), make_file("big.md5")]
        [(_iso, md5)] = pair_iso_with_md5(files)
        assert md5["name"] == "big.md5"

    def test_case_insensitive(self):
        files = [make_file("Big.ISO"), make_file("big.iso.MD5")]
        [(_iso, md5)] = pair_iso_with_md5(files)
        assert md5 is not None

    def test_no_partial_matches(self):
        """Regression: "big.md5" used to be attached to every ISO containing "big"."""
        files = [
            make_file("big-xfce.iso"),
            make_file("big-xfce.iso.md5"),
            make_file("big-gnome.iso"),
            make_file("big.md5"),
        ]
        pairs = {iso["name"]: md5 and md5["name"] for iso, md5 in pair_iso_with_md5(files)}
        assert pairs == {"big-xfce.iso": "big-xfce.iso.md5", "big-gnome.iso": None}

    def test_iso_without_md5(self):
        [(_iso, md5)] = pair_iso_with_md5([make_file("lonely.iso")])
        assert md5 is None

    def test_orphan_md5_and_other_files_ignored(self):
        assert pair_iso_with_md5([make_file("orphan.md5"), make_file("index.html")]) == []

    def test_sorted_by_name(self):
        files = [make_file("c.iso"), make_file("A.iso"), make_file("b.iso")]
        assert [iso["name"] for iso, _ in pair_iso_with_md5(files)] == ["A.iso", "b.iso", "c.iso"]
