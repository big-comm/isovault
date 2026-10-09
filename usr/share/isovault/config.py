"""
Static application configuration.

User-editable settings live in models/settings.py; this module only holds
constants that never change at runtime.
"""

import os

APP_ID = "org.communitybig.isovault"
APP_NAME = "ISOVault"
APP_VERSION = "1.0.0"
APP_ICON = "isovault"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(APP_DIR, "templates")
CONFIG_FILE = os.path.expanduser("~/.config/isovault.conf")

DEFAULT_WINDOW_SIZE = (1100, 720)

DEFAULT_S3_CONFIG = {
    "access_key": "",
    "secret_key": "",
    "endpoint_url": "https://us-1.cdn77-storage.com",
    "region_name": "us-1",
    "bucket_name": "iso-comm",
}

DEFAULT_BASE_URL = "https://iso.communitybig.org"

# Folders in the bucket. "Root" is the bucket root itself (no key prefix).
ROOT_FOLDER = "Root"
DISTRO_FOLDERS = ("Gnome", "Cinnamon", "XFCE", ROOT_FOLDER)

INDEX_FILE = "index.html"

# Upload validation (extensions are compared in lowercase)
SUPPORTED_EXTENSIONS = (".iso", ".md5")
MAX_FILE_SIZE = 10 * 1024**3  # 10 GiB

# UI timings
TOAST_TIMEOUT = 3  # seconds
REFRESH_DELAY_MS = 500
