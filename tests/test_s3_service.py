"""Tests for S3Service (boto3 client mocked)."""

import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from services.s3_service import S3Service, _ProgressTracker, folder_of_key, object_key

S3_CONFIG = {
    "access_key": "AK",
    "secret_key": "SK",
    "endpoint_url": "https://s3.example.com",
    "region_name": "us-1",
    "bucket_name": "bucket",
}


@pytest.fixture
def client():
    with patch("services.s3_service.boto3.client") as factory:
        yield factory.return_value


@pytest.fixture
def service(client):
    return S3Service(S3_CONFIG, "https://cdn.example.com/")


def page(*keys, day=1):
    return {
        "Contents": [
            {"Key": key, "Size": 2048, "LastModified": datetime(2026, 1, day + i, tzinfo=timezone.utc)}
            for i, key in enumerate(keys)
        ]
    }


def set_pages(client, *pages):
    client.get_paginator.return_value.paginate.return_value = list(pages)


class TestKeys:
    @pytest.mark.parametrize(
        "folder, key", [("Root", "a.iso"), ("Gnome", "Gnome/a.iso"), ("XFCE", "XFCE/a.iso")]
    )
    def test_object_key(self, folder, key):
        assert object_key(folder, "a.iso") == key

    @pytest.mark.parametrize(
        "key, folder", [("a.iso", "Root"), ("Gnome/a.iso", "Gnome"), ("XFCE/sub/a.iso", "XFCE")]
    )
    def test_folder_of_key(self, key, folder):
        assert folder_of_key(key) == folder


class TestConstruction:
    @pytest.mark.parametrize("missing", ["access_key", "secret_key", "endpoint_url", "bucket_name"])
    def test_missing_config_raises(self, missing):
        with pytest.raises(ValueError, match=missing):
            S3Service({**S3_CONFIG, missing: ""})

    def test_no_network_in_constructor(self, client):
        S3Service(S3_CONFIG)
        client.head_bucket.assert_not_called()
        client.list_objects_v2.assert_not_called()

    def test_check_connection_propagates_errors(self, service, client):
        client.head_bucket.side_effect = ClientError({"Error": {"Code": "403"}}, "HeadBucket")
        with pytest.raises(ClientError):
            service.check_connection()


class TestListFiles:
    def test_all_pages_are_read(self, service, client):
        set_pages(client, page("Gnome/a.iso"), page("XFCE/b.iso"))
        assert {f["name"] for f in service.list_files()} == {"a.iso", "b.iso"}
        client.get_paginator.assert_called_once_with("list_objects_v2")

    def test_entry_fields(self, service, client):
        set_pages(client, page("Gnome/sub/a.iso"))
        [entry] = service.list_files()
        assert entry["name"] == "a.iso"
        assert entry["folder"] == "Gnome"
        assert entry["key"] == "Gnome/sub/a.iso"
        assert entry["size"] == 2048
        assert entry["size_formatted"] == "2.0 KB"

    def test_newest_first(self, service, client):
        set_pages(client, page("old.iso", "mid.iso", "new.iso"))
        assert [f["name"] for f in service.list_files()] == ["new.iso", "mid.iso", "old.iso"]

    def test_folder_uses_prefix(self, service, client):
        set_pages(client, page("Gnome/a.iso"))
        service.list_files("Gnome")
        client.get_paginator.return_value.paginate.assert_called_once_with(Bucket="bucket", Prefix="Gnome/")

    def test_root_lists_only_top_level(self, service, client):
        set_pages(client, page("a.iso"))
        files = service.list_files("Root")
        client.get_paginator.return_value.paginate.assert_called_once_with(Bucket="bucket", Delimiter="/")
        assert [f["folder"] for f in files] == ["Root"]

    def test_skips_folder_placeholders(self, service, client):
        set_pages(client, page("Gnome/", "Gnome/a.iso"))
        assert [f["key"] for f in service.list_files()] == ["Gnome/a.iso"]

    def test_index_files_hidden_by_default(self, service, client):
        set_pages(client, page("index.html", "Gnome/INDEX.HTML", "Gnome/a.iso"))
        assert [f["name"] for f in service.list_files()] == ["a.iso"]
        set_pages(client, page("index.html", "Gnome/a.iso"))
        assert len(service.list_files(include_index=True)) == 2

    def test_empty_bucket(self, service, client):
        set_pages(client, {})
        assert service.list_files() == []


class TestTransfers:
    def test_upload_key_and_progress(self, service, client, tmp_path):
        path = tmp_path / "a.iso"
        path.write_bytes(b"\0" * 100)

        def fake_upload(_path, _bucket, _key, Callback):
            Callback(40)
            Callback(60)

        client.upload_file.side_effect = fake_upload
        progress = []

        key = service.upload_file(str(path), "Gnome", progress.append)

        assert key == "Gnome/a.iso"
        assert client.upload_file.call_args[0][:3] == (str(path), "bucket", "Gnome/a.iso")
        assert progress == [40.0, 100.0]

    def test_upload_to_root(self, service, client, tmp_path):
        path = tmp_path / "a.iso"
        path.write_bytes(b"\0")
        assert service.upload_file(str(path), "Root") == "a.iso"

    def test_upload_invalid_folder(self, service, client, tmp_path):
        with pytest.raises(ValueError):
            service.upload_file(str(tmp_path / "a.iso"), "../etc")
        client.upload_file.assert_not_called()

    def test_upload_errors_propagate(self, service, client, tmp_path):
        path = tmp_path / "a.iso"
        path.write_bytes(b"\0")
        client.upload_file.side_effect = ClientError({"Error": {"Code": "500"}}, "PutObject")
        with pytest.raises(ClientError):
            service.upload_file(str(path), "Gnome")

    def test_download_empty_object(self, service, client):
        """Regression: a 0-byte object used to raise ZeroDivisionError."""
        client.head_object.return_value = {"ContentLength": 0}
        client.download_file.side_effect = lambda *_args, Callback: Callback(0)
        progress = []
        service.download_file("a.md5", "/tmp/x", progress.append)
        assert progress == [100.0]

    def test_delete(self, service, client):
        service.delete_file("Gnome/a.iso")
        client.delete_object.assert_called_once_with(Bucket="bucket", Key="Gnome/a.iso")

    def test_upload_text_is_public_utf8(self, service, client):
        service.upload_text("olá", "index.html", "text/html")
        kwargs = client.put_object.call_args.kwargs
        assert kwargs["Body"] == "olá".encode()
        assert kwargs["ContentType"] == "text/html; charset=utf-8"
        assert kwargs["ACL"] == "public-read"

    def test_read_text(self, service, client):
        client.get_object.return_value = {"Body": MagicMock(read=lambda: b"abc  a.iso\n")}
        assert service.read_text("a.md5") == "abc  a.iso\n"


class TestProgressTracker:
    def test_updates_happen_under_lock(self):
        """boto3 calls the callback from several threads; the counter must be guarded."""

        class RecordingLock:
            def __init__(self):
                self.held = False

            def __enter__(self):
                self.held = True

            def __exit__(self, *_exc):
                self.held = False

        tracker = _ProgressTracker(100, lambda _p: None)
        lock = tracker._lock = RecordingLock()

        class GuardedInt(int):
            def __add__(self, other):
                assert lock.held, "progress counter updated without the lock"
                return GuardedInt(int(self) + other)

        tracker._done = GuardedInt(0)
        tracker(10)
        tracker(20)
        assert tracker._done == 30

    def test_concurrent_calls_reach_100(self):
        progress = []
        tracker = _ProgressTracker(8 * 1000, progress.append)
        threads = [threading.Thread(target=lambda: [tracker(1) for _ in range(1000)]) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert max(progress) == pytest.approx(100.0)

    def test_never_exceeds_100(self):
        progress = []
        tracker = _ProgressTracker(10, progress.append)
        tracker(30)
        assert progress == [100.0]

    def test_without_callback(self):
        _ProgressTracker(10, None)(5)  # must not raise


class TestPublicUrl:
    def test_uses_base_url_without_double_slash(self, service):
        assert service.get_public_url("/Gnome/a.iso") == "https://cdn.example.com/Gnome/a.iso"

    def test_percent_encodes_names(self, service):
        assert service.get_public_url("Gnome/my file#1.iso") == "https://cdn.example.com/Gnome/my%20file%231.iso"

    def test_fallback_without_base_url(self, client):
        assert S3Service(S3_CONFIG).get_public_url("a.iso") == "https://bucket/a.iso"
