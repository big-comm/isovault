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

# "Root" is the bucket root itself (no key prefix)
ROOT_FOLDER = "Root"
# Folders of a new profile; each profile keeps its own list
DEFAULT_FOLDERS = ("Gnome", "Cinnamon", "XFCE", "KDE", ROOT_FOLDER)

INDEX_FILE = "index.html"

# Look of the public download page: BigCommunity cards or the BigLinux file list
PAGE_STYLES = ("bigcommunity", "biglinux")
DEFAULT_PAGE_STYLE = "bigcommunity"

# A profile is one repository: S3 connection, public URL, page style and folders.
# These are created on first run; users can edit them or add their own.
PROFILE_KEYS = (
    "name",
    "access_key",
    "secret_key",
    "endpoint_url",
    "region_name",
    "bucket_name",
    "base_url",
    "page_style",
    "folders",
)

NEW_PROFILE = {
    "name": "",
    "access_key": "",
    "secret_key": "",
    "endpoint_url": "https://us-1.cdn77-storage.com",
    "region_name": "us-1",
    "bucket_name": "",
    "base_url": "",
    "page_style": DEFAULT_PAGE_STYLE,
    "folders": ROOT_FOLDER,
}

BUILTIN_PROFILES = {
    "bigcommunity": {
        **NEW_PROFILE,
        "name": "BigCommunity",
        "bucket_name": "iso-comm",
        "base_url": "https://iso.communitybig.org",
        "page_style": "bigcommunity",
        "folders": ",".join(DEFAULT_FOLDERS),
    },
    "biglinux": {
        **NEW_PROFILE,
        "name": "BigLinux",
        "base_url": "https://iso.biglinux.com.br",
        "page_style": "biglinux",
        "folders": ROOT_FOLDER,
    },
}
DEFAULT_PROFILE = "bigcommunity"

# Upload validation (extensions are compared in lowercase). Besides the image
# and its checksum, BigLinux publishes a package list and a torrent per ISO.
SUPPORTED_EXTENSIONS = (".iso", ".md5", ".pkgs", ".torrent")
MAX_FILE_SIZE = 10 * 1024**3  # 10 GiB

# UI timings
TOAST_TIMEOUT = 3  # seconds
REFRESH_DELAY_MS = 500
