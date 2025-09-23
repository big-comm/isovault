"""
S3 service for handling all S3 operations.
"""

import boto3
import os
from pathlib import Path
from typing import List, Dict, Optional, Callable
from botocore.exceptions import ClientError, NoCredentialsError
from datetime import datetime

from config import DISTRO_FOLDERS
from .file_validator import FileValidator
from utils.i18n import _


class S3Service:
    """Handles all S3 operations"""
    
    def __init__(self, s3_config: Dict[str, str], web_config: Optional[Dict[str, str]] = None):
        """
        Initialize S3 service with configuration.
        
        Args:
            s3_config: S3 configuration dictionary
            web_config: Web configuration dictionary (optional)
        """
        self.s3_client = None
        self.bucket_name = s3_config.get('bucket_name')
        self.config = s3_config
        self.web_config = web_config or {'base_url': '', 'index_file': 'index.html', 'show_index_files': False}
        self._connect()
    
    def update_web_config(self, web_config: Dict[str, str]) -> None:
        """Update web configuration"""
        self.web_config = web_config or {'base_url': '', 'index_file': 'index.html', 'show_index_files': False}
        print(f"Updated web config: show_index_files = {self.web_config.get('show_index_files')}")
    
    def _connect(self) -> bool:
        """Initialize S3 client connection"""
        try:
            if not all([self.config.get('access_key'), 
                       self.config.get('secret_key'),
                       self.config.get('endpoint_url'),
                       self.bucket_name]):
                print("Missing required S3 configuration")
                return False
            
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.config['endpoint_url'],
                aws_access_key_id=self.config['access_key'],
                aws_secret_access_key=self.config['secret_key'],
                region_name=self.config.get('region_name', 'us-1')
            )
            
            # Test connection
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            print(f"Connected to S3 bucket: {self.bucket_name}")
            return True
            
        except (ClientError, NoCredentialsError) as e:
            print(f"S3 connection error: {e}")
            self.s3_client = None
            return False
        except Exception as e:
            print(f"Unexpected S3 error: {e}")
            self.s3_client = None
            return False
    
    def test_connection(self) -> bool:
        """Test S3 connection"""
        try:
            if self.s3_client:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                return True
        except ClientError:
            pass
        return False
    
    def create_folders(self) -> bool:
        """Create the distro folders if they don't exist"""
        if not self.s3_client:
            return False
        
        try:
            for folder in DISTRO_FOLDERS:
                if folder == 'Root':  # Skip Root folder as it's the bucket root
                    continue
                    
                folder_key = f"{folder}/"
                
                # Check if folder exists
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=folder_key,
                    MaxKeys=1
                )
                
                # Create folder if it doesn't exist
                if 'Contents' not in response:
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=folder_key,
                        Body=''
                    )
                    print(f"Created folder: {folder}")
            
            return True
            
        except ClientError as e:
            print(f"Error creating folders: {e}")
            return False
    
    def upload_file(self, file_path: str, folder: str, 
                   progress_callback: Optional[Callable] = None) -> bool:
        """
        Upload file to specified folder with progress callback.
        
        Args:
            file_path: Local file path
            folder: Target folder name
            progress_callback: Optional progress callback function
            
        Returns:
            True if upload successful
        """
        if not self.s3_client:
            print(_("No S3 connection available"))
            return False
        
        # Validate file
        is_valid, message = FileValidator.validate_file(file_path)
        if not is_valid:
            print(_("Upload validation failed: {message}").format(message=message))
            return False
        
        if folder not in DISTRO_FOLDERS:
            print(_("Invalid folder. Must be one of: {folders}").format(folders=DISTRO_FOLDERS))
            return False
        
        try:
            file_name = Path(file_path).name
            
            # Handle Root folder (no prefix)
            if folder == 'Root':
                key = file_name
            else:
                key = f"{folder}/{file_name}"
            
            # Get file size for progress tracking
            file_size = os.path.getsize(file_path)
            uploaded = 0
            
            def upload_callback(bytes_transferred):
                nonlocal uploaded
                uploaded += bytes_transferred
                if progress_callback:
                    progress = (uploaded / file_size) * 100
                    progress_callback(progress)
            
            # Upload file
            self.s3_client.upload_file(
                file_path,
                self.bucket_name,
                key,
                Callback=upload_callback
            )
            
            print(f"Successfully uploaded {file_name} to {folder}")
            return True
            
        except ClientError as e:
            print(_("Upload failed: {error}").format(error=e))
            return False
        except Exception as e:
            print(_("Upload error: {error}").format(error=e))
            return False
    
    def list_files(self, folder: Optional[str] = None) -> List[Dict]:
        """
        List files in bucket or specific folder.
        
        Args:
            folder: Optional folder to filter by
            
        Returns:
            List of file dictionaries
        """
        if not self.s3_client:
            print(_("No S3 connection available"))
            return []
        
        try:
            # Set prefix for folder filtering
            if folder and folder in DISTRO_FOLDERS and folder != 'Root':
                prefix = f"{folder}/"
            else:
                prefix = ""
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    # Skip folder objects (ending with /)
                    if obj['Key'].endswith('/'):
                        continue
                    
                    # Extract folder and filename
                    parts = obj['Key'].split('/')
                    if len(parts) > 1:
                        folder_name = parts[0]
                        file_name = parts[-1]
                    else:
                        # File in root directory
                        folder_name = 'Root'
                        file_name = obj['Key']
                    
                    # Apply folder filter
                    if folder and folder_name != folder:
                        continue
                    
                    # Filter out index.html files if show_index_files is False
                    show_index_files = self.web_config.get('show_index_files', False)
                    if not show_index_files and file_name.lower() == 'index.html':
                        continue
                    
                    files.append({
                        'name': file_name,
                        'folder': folder_name,
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'modified': obj['LastModified'],
                        'size_formatted': FileValidator.format_file_size(obj['Size'])
                    })
            
            # Sort by modified date (newest first)
            return sorted(files, key=lambda x: x['modified'], reverse=True)
            
        except ClientError as e:
            print(_("Error listing files: {error}").format(error=e))
            return []
    
    def delete_file(self, file_key: str) -> bool:
        """
        Delete file from bucket.
        
        Args:
            file_key: S3 object key to delete
            
        Returns:
            True if deletion successful
        """
        if not self.s3_client:
            return False
        
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            print(f"Successfully deleted {file_key}")
            return True
            
        except ClientError as e:
            print(_("Delete failed: {error}").format(error=e))
            return False
    
    def download_file(self, file_key: str, local_path: str, 
                     progress_callback: Optional[Callable] = None) -> bool:
        """
        Download file from bucket.
        
        Args:
            file_key: S3 object key
            local_path: Local destination path
            progress_callback: Optional progress callback function
            
        Returns:
            True if download successful
        """
        if not self.s3_client:
            return False
        
        try:
            # Get file size for progress tracking
            response = self.s3_client.head_object(
                Bucket=self.bucket_name, 
                Key=file_key
            )
            file_size = response['ContentLength']
            downloaded = 0
            
            def download_callback(bytes_transferred):
                nonlocal downloaded
                downloaded += bytes_transferred
                if progress_callback:
                    progress = (downloaded / file_size) * 100
                    progress_callback(progress)
            
            self.s3_client.download_file(
                self.bucket_name,
                file_key,
                local_path,
                Callback=download_callback
            )
            
            print(f"Successfully downloaded {file_key}")
            return True
            
        except ClientError as e:
            print(_("Download failed: {error}").format(error=e))
            return False
    
    def get_file_info(self, file_key: str) -> Optional[Dict]:
        """Get detailed information about a file"""
        if not self.s3_client:
            return None
        
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            
            return {
                'size': response['ContentLength'],
                'modified': response['LastModified'],
                'etag': response['ETag'].strip('"'),
                'content_type': response.get('ContentType', 'application/octet-stream'),
                'size_formatted': FileValidator.format_file_size(response['ContentLength'])
            }
            
        except ClientError as e:
            print(_("Error getting file info: {error}").format(error=e))
            return None
    
    def get_public_url(self, file_key: str) -> str:
        """Generate public URL for a file"""
        if file_key.startswith('/'):
            file_key = file_key[1:]  # Remove leading slash
        base_url = self.web_config.get('base_url', '')
        if base_url:
            return f"{base_url}/{file_key}"
        else:
            return f"https://{self.bucket_name}/{file_key}"  # Fallback
    
    def upload_content(self, content: str, key: str, content_type: str = 'text/plain') -> bool:
        """
        Upload text content directly to S3.
        
        Args:
            content: Text content to upload
            key: S3 object key
            content_type: MIME type
            
        Returns:
            True if upload successful
        """
        if not self.s3_client:
            return False
        
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content.encode('utf-8'),
                ContentType=content_type,
                CacheControl='max-age=300',  # 5 minutes cache
                ACL='public-read'  # Make it publicly readable
            )
            return True
            
        except ClientError as e:
            print(_("Error uploading content: {error}").format(error=e))
            return False
    
    def read_file_content(self, file_key: str) -> Optional[str]:
        """Read text content from S3 file"""
        if not self.s3_client:
            return None
        
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            return response['Body'].read().decode('utf-8')
            
        except ClientError as e:
            print(_("Error reading file content: {error}").format(error=e))
            return None