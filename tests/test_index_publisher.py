"""Tests for publish_indexes."""

from unittest.mock import MagicMock

import pytest

from tests.factories import make_file
from services.html_generator import HTMLGenerator
from services.index_publisher import publish_indexes

HASH = "d41d8cd98f00b204e9800998ecf8427e"


@pytest.fixture
def s3():
    service = MagicMock()
    service.list_files.return_value = [
        make_file("root.iso"),
        make_file("Gnome/g.iso"),
        make_file("Gnome/g.iso.md5"),
        make_file("XFCE/x.iso"),
        make_file("XFCE/x.iso.md5"),
    ]
    service.read_text.side_effect = lambda key: f"{HASH}  file\n"
    return service


def uploaded_pages(s3):
    return {call.args[1]: call.args[0] for call in s3.upload_text.call_args_list}


def test_publishes_main_and_every_folder(s3):
    keys = publish_indexes(s3, HTMLGenerator(str, lang="en"))

    assert keys == ["index.html", "Gnome/index.html", "Cinnamon/index.html", "XFCE/index.html"]
    assert set(uploaded_pages(s3)) == set(keys)
    assert all(call.args[2] == "text/html" for call in s3.upload_text.call_args_list)


def test_lists_bucket_once_and_reads_each_checksum(s3):
    publish_indexes(s3, HTMLGenerator(str, lang="en"))

    s3.list_files.assert_called_once_with()
    assert sorted(call.args[0] for call in s3.read_text.call_args_list) == ["Gnome/g.iso.md5", "XFCE/x.iso.md5"]


def test_folder_pages_only_contain_their_files(s3):
    publish_indexes(s3, HTMLGenerator(str, lang="en"))
    pages = uploaded_pages(s3)

    assert "g.iso" in pages["Gnome/index.html"] and "x.iso" not in pages["Gnome/index.html"]
    assert 'class="empty-state"' in pages["Cinnamon/index.html"]  # stale pages get overwritten
    assert HASH in pages["XFCE/index.html"]


def test_unreadable_checksum_does_not_block_publishing(s3):
    def read_text(key):
        if key.startswith("Gnome/"):
            raise OSError("boom")
        return HASH

    s3.read_text.side_effect = read_text
    publish_indexes(s3, HTMLGenerator(str, lang="en"))
    pages = uploaded_pages(s3)

    assert 'class="md5-section"' not in pages["Gnome/index.html"]
    assert HASH in pages["XFCE/index.html"]


def test_upload_errors_propagate(s3):
    s3.upload_text.side_effect = RuntimeError("denied")
    with pytest.raises(RuntimeError):
        publish_indexes(s3, HTMLGenerator(str, lang="en"))
