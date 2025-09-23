"""
File item data model for the file list.
"""

from gi.repository import GObject
from datetime import datetime


class FileItem(GObject.Object):
    """Data model for file items in the file list"""
    __gtype_name__ = 'FileItem'
    
    def __init__(self, name: str, folder: str, key: str, size: int, 
                 modified: datetime, size_formatted: str):
        """
        Initialize a file item.
        
        Args:
            name: File name
            folder: Folder name where the file is located
            key: S3 object key
            size: File size in bytes
            modified: Last modified datetime
            size_formatted: Human-readable file size string
        """
        super().__init__()
        self.name = name
        self.folder = folder 
        self.key = key
        self.size = size
        self.modified = modified
        self.size_formatted = size_formatted
    
    def __str__(self) -> str:
        """String representation of the file item"""
        return f"FileItem(name='{self.name}', folder='{self.folder}', size='{self.size_formatted}')"
    
    def __repr__(self) -> str:
        """Detailed representation of the file item"""
        return (f"FileItem(name='{self.name}', folder='{self.folder}', "
                f"key='{self.key}', size={self.size}, modified={self.modified})")