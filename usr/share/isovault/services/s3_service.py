"""
Thin wrapper around boto3 for the operations ISOVault needs.

Methods raise on failure (botocore exceptions or ValueError) so callers can
show the real error to the user; nothing here touches the UI.
"""

import logging
import os
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence
from urllib.parse import quote

import boto3
from botocore.config import Config

from config import DEFAULT_FOLDERS, INDEX_FILE, ROOT_FOLDER
from utils.helpers import format_file_size

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float], None]

# Fail fast instead of freezing the UI on a dead network
_CLIENT_CONFIG = Config(
    connect_timeout=10,
    read_timeout=60,
    retries={"max_attempts": 3, "mode": "standard"},
)


def object_key(folder: str, file_name: str) -> str:
    """Build the S3 key for a file stored in one of the distro folders."""
    if folder == ROOT_FOLDER:
        return file_name
    return f"{folder}/{file_name}"


def folder_of_key(key: str) -> str:
    """Return the distro folder of an S3 key ("Root" for top-level keys)."""
    return key.split("/", 1)[0] if "/" in key else ROOT_FOLDER


class _ProgressTracker:
    """Turns boto3 byte callbacks (called from several threads) into percentages"""

    def __init__(self, total_bytes: int, callback: Optional[ProgressCallback]):
        self._total = total_bytes
        self._done = 0
        self._callback = callback
        self._lock = threading.Lock()

    def __call__(self, bytes_transferred: int) -> None:
        if not self._callback:
            return
        with self._lock:
            self._done += bytes_transferred
            percent = 100.0 if self._total <= 0 else min(self._done / self._total * 100, 100.0)
        self._callback(percent)


class S3Service:
    """S3 operations on a single bucket"""

    def __init__(self, s3_config: Dict[str, str], base_url: str = "", folders: Sequence[str] = DEFAULT_FOLDERS):
        """
        Create the client. No network request is made here.

        Args:
            folders: Bucket folders uploads may go to (the profile's folders)

        Raises:
            ValueError: if a required configuration value is missing.
        """
        missing = [
            key
            for key in ("access_key", "secret_key", "endpoint_url", "bucket_name")
            if not s3_config.get(key)
        ]
        if missing:
            raise ValueError(f"Missing S3 configuration: {', '.join(missing)}")

        self.bucket_name = s3_config["bucket_name"]
        self.folders = tuple(folders)
        self.base_url = base_url.rstrip("/")
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=s3_config["endpoint_url"],
            aws_access_key_id=s3_config["access_key"],
            aws_secret_access_key=s3_config["secret_key"],
            region_name=s3_config.get("region_name") or None,
            config=_CLIENT_CONFIG,
        )

    def check_connection(self) -> None:
        """Raise if the bucket is not reachable with the current credentials."""
        self.s3_client.head_bucket(Bucket=self.bucket_name)

    def list_files(self, folder: Optional[str] = None, include_index: bool = False) -> List[Dict]:
        """
        List files, newest first.

        Args:
            folder: Restrict to one distro folder (None = all folders)
            include_index: Also return generated index.html files
        """
        params = {"Bucket": self.bucket_name}
        if folder == ROOT_FOLDER:
            params["Delimiter"] = "/"  # only top-level keys
        elif folder:
            params["Prefix"] = f"{folder}/"

        files = []
        paginator = self.s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(**params):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):  # folder placeholder
                    continue

                name = key.rsplit("/", 1)[-1]
                if not include_index and name.lower() == INDEX_FILE:
                    continue

                files.append(
                    {
                        "name": name,
                        "folder": folder_of_key(key),
                        "key": key,
                        "size": obj["Size"],
                        "modified": obj["LastModified"],
                        "size_formatted": format_file_size(obj["Size"]),
                    }
                )

        return sorted(files, key=lambda f: f["modified"], reverse=True)

    def upload_file(
        self, file_path: str, folder: str, progress_callback: Optional[ProgressCallback] = None
    ) -> str:
        """Upload a local file into a distro folder and return its key."""
        if folder not in self.folders:
            raise ValueError(f"Invalid folder: {folder}")

        key = object_key(folder, Path(file_path).name)
        tracker = _ProgressTracker(os.path.getsize(file_path), progress_callback)
        self.s3_client.upload_file(file_path, self.bucket_name, key, Callback=tracker)
        logger.info("Uploaded %s", key)
        return key

    def download_file(
        self, file_key: str, local_path: str, progress_callback: Optional[ProgressCallback] = None
    ) -> None:
        """Download an object to a local path."""
        size = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_key)["ContentLength"]
        tracker = _ProgressTracker(size, progress_callback)
        self.s3_client.download_file(self.bucket_name, file_key, local_path, Callback=tracker)
        logger.info("Downloaded %s to %s", file_key, local_path)

    def delete_file(self, file_key: str) -> None:
        """Delete an object."""
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
        logger.info("Deleted %s", file_key)

    def upload_text(self, content: str, key: str, content_type: str = "text/plain") -> None:
        """Upload a small public text object (used for the index pages)."""
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType=f"{content_type}; charset=utf-8",
            CacheControl="max-age=300",
            ACL="public-read",
        )

    def read_text(self, file_key: str) -> str:
        """Read a small text object."""
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_key)
        return response["Body"].read().decode("utf-8", errors="replace")

    def get_public_url(self, file_key: str) -> str:
        """Public download URL of an object (path is percent-encoded)."""
        file_key = quote(file_key.lstrip("/"))
        if self.base_url:
            return f"{self.base_url}/{file_key}"
        return f"https://{self.bucket_name}/{file_key}"
