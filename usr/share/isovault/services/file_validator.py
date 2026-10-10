"""
Validation of local files before upload.
"""

import os
from pathlib import Path
from typing import List, Tuple

from config import MAX_FILE_SIZE, SUPPORTED_EXTENSIONS
from utils.i18n import _


class FileValidator:
    """Checks whether local files can be uploaded"""

    @staticmethod
    def validate_file(file_path: str) -> Tuple[bool, str]:
        """
        Validate a single file.

        Returns:
            Tuple of (is_valid, message)
        """
        if not os.path.exists(file_path):
            return False, _("File does not exist")

        if not os.path.isfile(file_path):
            return False, _("Path is not a file")

        if Path(file_path).suffix.lower() not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(SUPPORTED_EXTENSIONS)
            return False, _("Unsupported file type. Only {supported} are allowed").format(
                supported=supported
            )

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False, _("File is empty")

        if file_size > MAX_FILE_SIZE:
            max_size_gb = MAX_FILE_SIZE // 1024**3
            return False, _("File too large. Maximum size: {max_size}GB").format(
                max_size=max_size_gb
            )

        return True, _("File is valid")

    @staticmethod
    def validate_multiple_files(
        file_paths: List[str],
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        Split paths into valid files and (file name, reason) pairs for invalid ones.
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
