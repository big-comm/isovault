"""
File item data model for the file list.
"""

from datetime import datetime
from typing import Dict, List, Optional

from gi.repository import GObject


class FileItem(GObject.Object):
    """
    One S3 object shown in the file list, or a folder entry (opens_folder
    set) used when browsing the bucket root.
    """

    __gtype_name__ = "FileItem"

    def __init__(
        self,
        name: str,
        folder: str,
        key: str,
        size: int,
        modified: Optional[datetime],
        size_formatted: str,
        opens_folder: Optional[str] = None,
        file_count: int = 0,
    ):
        super().__init__()
        self.name = name
        self.folder = folder
        self.key = key
        self.size = size
        self.modified = modified
        self.size_formatted = size_formatted
        self.opens_folder = opens_folder
        self.file_count = file_count

    @property
    def is_folder(self) -> bool:
        return self.opens_folder is not None

    @classmethod
    def folder_entry(cls, folder: str, files: List["FileItem"], parent: str, size_formatted: str) -> "FileItem":
        """Entry that represents a bucket folder inside its parent (the root)."""
        return cls(
            name=folder,
            folder=parent,
            key=f"{folder}/",
            size=sum(f.size for f in files),
            modified=max((f.modified for f in files), default=None),
            size_formatted=size_formatted,
            opens_folder=folder,
            file_count=len(files),
        )

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
