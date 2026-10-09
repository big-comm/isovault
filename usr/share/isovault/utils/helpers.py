"""
Small, dependency-free helpers shared by services and UI.
"""

import re
from typing import Dict, List, Optional, Tuple

from utils.i18n import _

# Exactly 32 hex chars, not part of a longer hex run (e.g. a SHA-256)
MD5_PATTERN = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")


def format_file_size(size_bytes: int) -> str:
    """Format a byte count as a human readable string (1024-based)."""
    units = [_("B"), _("KB"), _("MB"), _("GB"), _("TB")]
    size = float(size_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[0]}"
    return f"{size:.1f} {units[unit_index]}"


def extract_md5(text: str) -> Optional[str]:
    """
    Return the first MD5 hash (32 hex chars) found in text, lowercased.

    Works for both `md5sum` output ("<hash>  file.iso") and file names that
    embed the hash.
    """
    if not text:
        return None
    match = MD5_PATTERN.search(text)
    return match.group().lower() if match else None


def pair_iso_with_md5(files: List[Dict]) -> List[Tuple[Dict, Optional[Dict]]]:
    """
    Pair each ISO with its checksum file, sorted by ISO name.

    For "name.iso" the accepted checksum names are "name.iso.md5" and
    "name.md5" (case-insensitive). Only exact matches are paired, so
    "big.md5" is never attached to "big-xfce.iso".
    """
    md5_by_name = {
        f["name"].lower(): f for f in files if f["name"].lower().endswith(".md5")
    }

    pairs = []
    for file_info in files:
        name = file_info["name"].lower()
        if not name.endswith(".iso"):
            continue
        stem = name[: -len(".iso")]
        md5_file = md5_by_name.get(f"{name}.md5") or md5_by_name.get(f"{stem}.md5")
        pairs.append((file_info, md5_file))

    return sorted(pairs, key=lambda pair: pair[0]["name"].lower())
