"""
File validation service for validating uploads.
"""

import os
from pathlib import Path
from typing import List, Tuple
from config import SUPPORTED_EXTENSIONS, MAX_FILE_SIZE


class FileValidator:
    """Handles file validation for uploads"""
    
    @staticmethod
    def validate_file(file_path: str) -> Tuple[bool, str]:
        """
        Validate if a file is supported for upload.
        
        Args:
            file_path: Path to the file to validate
            
        Returns:
            Tuple of (is_valid, message)
        """
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        # Check if it's a file (not directory)
        if not os.path.isfile(file_path):
            return False, "Path is not a file"
        
        # Check extension
        file_ext = Path(file_path).suffix
        if file_ext not in SUPPORTED_EXTENSIONS:
            supported = ', '.join(SUPPORTED_EXTENSIONS)
            return False, f"Unsupported file type. Only {supported} are allowed"
        
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            max_size_gb = MAX_FILE_SIZE // (1024**3)
            return False, f"File too large. Maximum size: {max_size_gb}GB"
        
        if file_size == 0:
            return False, "File is empty"
        
        return True, "File is valid"
    
    @staticmethod
    def validate_multiple_files(file_paths: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        Validate multiple files and return valid and invalid lists.
        
        Args:
            file_paths: List of file paths to validate
            
        Returns:
            Tuple of (valid_files, invalid_files_with_reasons)
        """
        valid_files = []
        invalid_files = []
        
        for file_path in file_paths:
            is_valid, message = FileValidator.validate_file(file_path)
            if is_valid:
                valid_files.append(file_path)
            else:
                invalid_files.append((Path(file_path).name, message))
        
        return valid_files, invalid_files
    
    @staticmethod
    def is_iso_file(filename: str) -> bool:
        """Check if filename is an ISO file"""
        return Path(filename).suffix.lower() == '.iso'
    
    @staticmethod
    def is_md5_file(filename: str) -> bool:
        """Check if filename is an MD5 file"""
        return Path(filename).suffix.lower() == '.md5'
    
    @staticmethod
    def get_file_type(filename: str) -> str:
        """Get human-readable file type"""
        ext = Path(filename).suffix.lower()
        if ext == '.iso':
            return 'ISO Image'
        elif ext == '.md5':
            return 'MD5 Checksum'
        else:
            return 'Unknown'
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        size = float(size_bytes)
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        return f"{size:.1f} {units[unit_index]}"