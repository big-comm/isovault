"""
File item data model for the file list.
"""

from datetime import datetime
from typing import Dict

from gi.repository import GObject


class FileItem(GObject.Object):
    """One S3 object shown in the file list"""

    __gtype_name__ = "FileItem"

    def __init__(self, name: str, folder: str, key: str, size: int, modified: datetime, size_formatted: str):
        super().__init__()
        self.name = name
        self.folder = folder
        self.key = key
        self.size = size
        self.modified = modified
        self.size_formatted = size_formatted

    @classmethod
    def from_dict(cls, data: Dict) -> "FileItem":
        """Build from an entry returned by S3Service.list_files()."""
        return cls(
            name=data["name"],
            folder=data["folder"],
            key=data["key"],
            size=data["size"],
            modified=data["modified"],
            size_formatted=data["size_formatted"],
        )

    def __repr__(self) -> str:
        return f"FileItem(key={self.key!r}, size={self.size}, modified={self.modified})"
