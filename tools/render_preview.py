#!/usr/bin/env python3
"""
Render the public index page with sample data, for previewing the design.

Usage: python3 tools/render_preview.py [output.html] [bigcommunity|biglinux]
       (defaults: preview-index.html, bigcommunity)
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "usr", "share", "isovault"))

from config import DEFAULT_FOLDERS  # noqa: E402
from services.html_generator import create_html_generator  # noqa: E402
from utils.helpers import format_file_size  # noqa: E402

SAMPLE = {
    "bigcommunity": [
        ("Gnome", "bigcommunity-gnome-2026-04-01.iso", 4_200_000_000),
        ("Cinnamon", "bigcommunity-cinnamon-2026-04-01.iso", 3_900_000_000),
        ("XFCE", "bigcommunity-xfce-2026-04-01.iso", 3_100_000_000),
        ("KDE", "bigcommunity-kde-2026-04-01.iso", 4_400_000_000),
    ],
    "biglinux": [
        ("Root", "biglinux_2026-04-01_k612.iso", 5_400_000_000),
        ("Root", "biglinux_2026-04-01_k618.iso", 5_450_000_000),
        ("Root", "biglinux_2026-04-15_k618.iso", 5_480_000_000),
    ],
}
# Extra files published next to each ISO, per style
EXTRAS = {"bigcommunity": ((".md5", 70),), "biglinux": ((".md5", 76), (".pkgs", 40_000), (".torrent", 52_000))}


def sample_files(style):
    files, hashes = [], {}
    for index, (folder, name, size) in enumerate(SAMPLE[style]):
        prefix = "" if folder == "Root" else f"{folder}/"
        modified = datetime(2026, 4, 1 + index, 12, 0, tzinfo=timezone.utc)
        for extension, extra_size in ((("", size),) + EXTRAS[style]):
            files.append({"name": name + extension, "folder": folder, "key": prefix + name + extension,
                          "size": extra_size, "modified": modified, "size_formatted": format_file_size(extra_size)})
        hashes[f"{prefix}{name}.md5"] = f"{index + 10:02x}" * 16 + f"  {name}\n"  # 32 hex chars
    return files, hashes


def main() -> None:
    output = sys.argv[1] if len(sys.argv) > 1 else "preview-index.html"
    style = sys.argv[2] if len(sys.argv) > 2 else "bigcommunity"
    files, hashes = sample_files(style)
    present = {f["folder"] for f in files}
    folders = [f for f in DEFAULT_FOLDERS if f in present]
    generator = create_html_generator(style, lambda key: key, lang="en", folders=folders)
    with open(output, "w", encoding="utf-8") as f:
        f.write(generator.generate_main_index(files, hashes))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
