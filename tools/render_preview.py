#!/usr/bin/env python3
"""
Render the public index page with sample data, for previewing the design.

Usage: python3 tools/render_preview.py [output.html]   (default: preview-index.html)
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "usr", "share", "isovault"))

from services.html_generator import HTMLGenerator  # noqa: E402
from utils.helpers import format_file_size  # noqa: E402

SAMPLE = [
    ("Gnome", "biglinux-gnome-2026-04-01.iso", 4_200_000_000),
    ("Cinnamon", "biglinux-cinnamon-2026-04-01.iso", 3_900_000_000),
    ("XFCE", "biglinux-xfce-2026-04-01.iso", 3_100_000_000),
    ("Root", "bigcommunity-base-2026-04-01.iso", 2_500_000_000),
]


def sample_files():
    files, hashes = [], {}
    for index, (folder, name, size) in enumerate(SAMPLE):
        prefix = "" if folder == "Root" else f"{folder}/"
        modified = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
        files.append({"name": name, "folder": folder, "key": prefix + name, "size": size,
                      "modified": modified, "size_formatted": format_file_size(size)})
        md5_key = f"{prefix}{name}.md5"
        files.append({"name": f"{name}.md5", "folder": folder, "key": md5_key, "size": 70,
                      "modified": modified, "size_formatted": format_file_size(70)})
        hashes[md5_key] = f"{index:x}" * 32 + f"  {name}\n"
    return files, hashes


def main() -> None:
    output = sys.argv[1] if len(sys.argv) > 1 else "preview-index.html"
    files, hashes = sample_files()
    generator = HTMLGenerator(lambda key: f"https://iso.communitybig.org/{key}", lang="en")
    with open(output, "w", encoding="utf-8") as f:
        f.write(generator.generate_main_index(files, hashes))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
