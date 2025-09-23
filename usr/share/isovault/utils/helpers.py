"""
Helper utilities for various application functions.
"""

import re
from typing import List, Dict, Tuple, Optional, Callable
from pathlib import Path
from datetime import datetime
import threading
import time

from config import DEFAULT_WEB_CONFIG
from utils.i18n import _


class BatchProcessor:
    """Handles batch operations with progress tracking"""
    
    def __init__(self, items: List, operation: Callable, 
                 progress_callback: Optional[Callable] = None):
        """
        Initialize batch processor.
        
        Args:
            items: List of items to process
            operation: Function to call for each item
            progress_callback: Optional progress callback
        """
        self.items = items
        self.operation = operation
        self.progress_callback = progress_callback
        self.results = []
        self.errors = []
        self.current_index = 0
        
    def process_all(self) -> Tuple[List, List]:
        """
        Process all items and return results and errors.
        
        Returns:
            Tuple of (successful_results, error_list)
        """
        total_items = len(self.items)
        
        for index, item in enumerate(self.items):
            try:
                result = self.operation(item)
                self.results.append(result)
                
                # Update progress
                if self.progress_callback:
                    progress = ((index + 1) / total_items) * 100
                    self.progress_callback(progress)
                    
            except Exception as e:
                self.errors.append((item, str(e)))
                print(_("Error processing item {item}: {error}").format(item=item, error=e))
            
            self.current_index = index + 1
        
        return self.results, self.errors
    
    def get_progress(self) -> float:
        """Get current progress percentage"""
        if not self.items:
            return 100.0
        return (self.current_index / len(self.items)) * 100


class ConnectionTester:
    """Tests and validates connections"""
    
    @staticmethod
    def test_s3_connection(s3_service, timeout: int = 10) -> Tuple[bool, str]:
        """
        Test S3 connection with timeout.
        
        Args:
            s3_service: S3Service instance
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success, message)
        """
        if not s3_service:
            return False, _("No S3 service configured")
        
        try:
            # Use threading to implement timeout
            result = {'success': False, 'message': _('Timeout')}
            
            def test_connection():
                try:
                    if s3_service.test_connection():
                        result['success'] = True
                        result['message'] = _('Connection successful')
                    else:
                        result['message'] = _('Connection failed')
                except Exception as e:
                    result['message'] = _('Connection error: {error}').format(error=str(e))
            
            thread = threading.Thread(target=test_connection)
            thread.daemon = True
            thread.start()
            thread.join(timeout)
            
            if thread.is_alive():
                return False, _('Connection timeout')
            
            return result['success'], result['message']
            
        except Exception as e:
            return False, _('Test error: {error}').format(error=str(e))
    
    @staticmethod
    def validate_endpoint_url(url: str) -> Tuple[bool, str]:
        """
        Validate S3 endpoint URL format.
        
        Args:
            url: URL to validate
            
        Returns:
            Tuple of (is_valid, message)
        """
        if not url:
            return False, _("URL is required")
        
        if not url.startswith(('http://', 'https://')):
            return False, _("URL must start with http:// or https://")
        
        # Basic URL format validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(url):
            return False, _("Invalid URL format")
        
        return True, _("Valid URL format")


class URLGenerator:
    """Generates various types of URLs"""
    
    @staticmethod
    def generate_public_url(file_key: str) -> str:
        """
        Generate public URL for a file.
        
        Args:
            file_key: S3 object key
            
        Returns:
            Public URL
        """
        if file_key.startswith('/'):
            file_key = file_key[1:]  # Remove leading slash
        return f"{DEFAULT_WEB_CONFIG['base_url']}/{file_key}"
    
    @staticmethod
    def generate_download_filename(original_name: str, add_timestamp: bool = False) -> str:
        """
        Generate download filename with optional timestamp.
        
        Args:
            original_name: Original filename
            add_timestamp: Whether to add timestamp
            
        Returns:
            Generated filename
        """
        path = Path(original_name)
        
        if add_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"{path.stem}_{timestamp}{path.suffix}"
        
        return original_name
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename for safe storage.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Remove or replace unsafe characters
        unsafe_chars = '<>:"/\\|?*'
        sanitized = filename
        
        for char in unsafe_chars:
            sanitized = sanitized.replace(char, '_')
        
        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip(' .')
        
        # Ensure filename is not empty
        if not sanitized:
            sanitized = 'unnamed_file'
        
        return sanitized


class MD5Helper:
    """Helper functions for MD5 handling"""
    
    @staticmethod
    def extract_md5_from_content(content: str) -> Optional[str]:
        """
        Extract MD5 hash from file content.
        
        Args:
            content: Content of MD5 file
            
        Returns:
            MD5 hash if found, None otherwise
        """
        if not content:
            return None
        
        # Look for 32-character hex string (MD5 hash)
        md5_pattern = r'[a-fA-F0-9]{32}'
        match = re.search(md5_pattern, content)
        
        if match:
            return match.group().lower()
        
        return None
    
    @staticmethod
    def extract_md5_from_filename(filename: str) -> str:
        """
        Extract or generate MD5 representation from filename.
        
        Args:
            filename: MD5 filename
            
        Returns:
            MD5 hash or cleaned filename
        """
        try:
            # Remove extension
            base_name = filename.replace('.md5', '').replace('.MD5', '')
            
            # If it's just a 32-character hash
            if len(base_name) == 32 and all(c in '0123456789abcdefABCDEF' for c in base_name):
                return base_name.lower()
            
            # Try to extract hash from complex filenames
            md5_pattern = r'[a-fA-F0-9]{32}'
            match = re.search(md5_pattern, filename)
            if match:
                return match.group().lower()
            
            # If filename contains the hash after underscore
            if '_' in base_name:
                parts = base_name.split('_')
                for part in parts:
                    if len(part) == 32 and all(c in '0123456789abcdefABCDEF' for c in part):
                        return part.lower()
            
            # Fallback: return cleaned filename
            return base_name
            
        except Exception as e:
            print(_("Error extracting MD5 from {filename}: {error}").format(filename=filename, error=e))
            return filename


class FileGrouper:
    """Groups related files (ISO and MD5)"""
    
    @staticmethod
    def group_iso_with_md5(files: List[Dict]) -> List[Dict]:
        """
        Group ISO files with their corresponding MD5 files.
        
        Args:
            files: List of file dictionaries
            
        Returns:
            List of grouped file dictionaries
        """
        iso_files = [f for f in files if f['name'].lower().endswith('.iso')]
        md5_files = [f for f in files if f['name'].lower().endswith('.md5')]
        
        grouped = []
        used_md5_files = set()
        
        # Match ISO files with MD5 files
        for iso_file in iso_files:
            iso_base = iso_file['name'].lower().replace('.iso', '')
            md5_match = None
            
            # Find corresponding MD5 file
            for md5_file in md5_files:
                if md5_file in used_md5_files:
                    continue
                
                md5_base = md5_file['name'].lower().replace('.md5', '').replace('.iso.md5', '')
                
                # Exact match
                if iso_base == md5_base:
                    md5_match = md5_file
                    used_md5_files.add(md5_file)
                    break
                
                # Partial match (MD5 base name contained in ISO base name)
                if md5_base in iso_base or iso_base in md5_base:
                    md5_match = md5_file
                    used_md5_files.add(md5_file)
                    break
            
            grouped.append({
                'iso': iso_file,
                'md5': md5_match
            })
        
        # Add orphaned MD5 files (without corresponding ISO)
        for md5_file in md5_files:
            if md5_file not in used_md5_files:
                grouped.append({
                    'iso': None,
                    'md5': md5_file
                })
        
        return grouped
    
    @staticmethod
    def find_related_files(filename: str, all_files: List[Dict]) -> List[Dict]:
        """
        Find files related to the given filename.
        
        Args:
            filename: Base filename to find related files for
            all_files: List of all available files
            
        Returns:
            List of related files
        """
        base_name = Path(filename).stem.lower()
        related = []
        
        for file_info in all_files:
            file_base = Path(file_info['name']).stem.lower()
            
            # Exact match or contains base name
            if base_name in file_base or file_base in base_name:
                related.append(file_info)
        
        return related


class ProgressTracker:
    """Tracks progress across multiple operations"""
    
    def __init__(self):
        self.operations = {}
        self.total_weight = 0
    
    def add_operation(self, name: str, weight: float = 1.0) -> None:
        """
        Add an operation to track.
        
        Args:
            name: Operation name
            weight: Relative weight of this operation
        """
        self.operations[name] = {'progress': 0.0, 'weight': weight}
        self.total_weight += weight
    
    def update_operation(self, name: str, progress: float) -> None:
        """
        Update progress for an operation.
        
        Args:
            name: Operation name
            progress: Progress percentage (0-100)
        """
        if name in self.operations:
            self.operations[name]['progress'] = progress
    
    def get_overall_progress(self) -> float:
        """
        Get overall progress across all operations.
        
        Returns:
            Overall progress percentage
        """
        if self.total_weight == 0:
            return 100.0
        
        weighted_sum = sum(
            op['progress'] * op['weight'] 
            for op in self.operations.values()
        )
        
        return weighted_sum / self.total_weight
    
    def reset(self) -> None:
        """Reset all operations"""
        self.operations.clear()
        self.total_weight = 0