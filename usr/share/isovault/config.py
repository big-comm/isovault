import os

# Application Configuration
APP_CONFIG = {
    'app_id': 'org.communitybig.isovault',
    'app_name': 'ISOVault',
    'version': '1.0.0',
    'window_title': 'ISOVault - ISO Manager',
    'window_width': 900,
    'window_height': 600,
    'config_file': os.path.expanduser('~/.config/isovault.conf')
}

# Default S3 Configuration (non-sensitive defaults)
DEFAULT_S3_CONFIG = {
    'endpoint_url': 'https://us-1.cdn77-storage.com',
    'region_name': 'us-1',
    'bucket_name': 'iso-comm'
}

# Supported folders in the bucket
DISTRO_FOLDERS = ['Gnome', 'Cinnamon', 'XFCE', 'Root']

# Default CDN/Web Configuration
DEFAULT_WEB_CONFIG = {
    'base_url': 'https://iso.communitybig.org',
    'index_file': 'index.html'
}

# File validation
SUPPORTED_EXTENSIONS = ['.iso', '.ISO', '.md5', '.MD5']
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB in bytes

# UI Constants
UI_CONSTANTS = {
    'TOAST_TIMEOUT': 3,
    'PROGRESS_UPDATE_INTERVAL': 100,
    'REFRESH_DELAY': 500
}