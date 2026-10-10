"""Builders for test data."""

from datetime import datetime, timezone

from services.s3_service import folder_of_key
from utils.helpers import format_file_size


def make_file(key, size=1024, modified=None):
    """Entry shaped like S3Service.list_files() output."""
    return {
        "name": key.rsplit("/", 1)[-1],
        "folder": folder_of_key(key),
        "key": key,
        "size": size,
        "modified": modified or datetime(2026, 1, 1, tzinfo=timezone.utc),
        "size_formatted": format_file_size(size),
    }
