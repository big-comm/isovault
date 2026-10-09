<div align="center">

<img src="usr/share/icons/hicolor/scalable/apps/isovault.svg" alt="ISOVault logo" width="128" height="128">

# ISOVault

**Manage Linux ISO repositories on S3 storage — upload, verify and publish them from a native GNOME app.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GTK](https://img.shields.io/badge/GTK-4-4A86CF?logo=gtk&logoColor=white)](https://www.gtk.org/)
[![libadwaita](https://img.shields.io/badge/libadwaita-1.7%2B-3584E4?logo=gnome&logoColor=white)](https://gnome.pages.gitlab.gnome.org/libadwaita/)
[![Platform](https://img.shields.io/badge/Platform-Linux-FCC624?logo=linux&logoColor=black)](https://communitybig.org)
[![Translations](https://img.shields.io/badge/Translations-28%20languages-2ec27e)](locale/)
[![BigCommunity](https://img.shields.io/badge/BigCommunity-communitybig.org-9141ac)](https://communitybig.org)

<img src="docs/screenshots/main-window-light.png" alt="ISOVault main window" width="900">

</div>

## Overview

ISOVault is the desktop tool the BigCommunity and BigLinux teams use to
maintain their ISO repositories, such as
[iso.communitybig.org](https://iso.communitybig.org) and
[iso.biglinux.com.br](https://iso.biglinux.com.br). It talks to
S3-compatible buckets (CDN77 by default), keeps each desktop edition in its
own folder and regenerates the public download page whenever the bucket
changes.

## Features

- **Profiles** — one per repository, each with its own S3 bucket and
  credentials, public URL, folders and download page style. *BigCommunity*
  and *BigLinux* profiles are included; switch between them from the header.
- **Two download page styles** — BigCommunity cards with the MD5 of every
  image, or the BigLinux file list (ISO, `.md5`, `.pkgs`, `.torrent`).
- **Upload with a destination picker** — GNOME, Cinnamon, XFCE, KDE Plasma
  or the bucket root (the folders come from the profile); invalid files are
  listed before anything is sent, and the last folder used is remembered.
- **Multiple selection** — check boxes, *Select all*, Shift/Ctrl+click; copy
  links, download or delete many files at once. A failing file never stops the
  rest of a batch.
- **List and grid views** with instant search (<kbd>Ctrl</kbd>+<kbd>F</kbd>),
  folder filter and sorting by name, distribution, size or date.
- **Public download page** — `index.html` for the whole repository and for
  each edition, pairing every ISO with its `.iso.md5` / `.md5` checksum and a
  one-click copy button.
- **Transfers** — progress and history of the uploads, downloads and
  deletions made in the session.
- **Statistics** — images and space per distribution, plus the ISOs that are
  still missing a checksum.
- **Safe by default** — confirmation before deleting, the settings file is
  private (`0600`) and the credentials are mirrored in the system keyring.
- **Native look** — GTK 4 + libadwaita, follows the system light/dark theme,
  translated into 28 languages.

<div align="center">
<img src="docs/screenshots/main-window-dark.png" alt="Dark theme" width="440">
<img src="docs/screenshots/grid-view-dark.png" alt="Grid view" width="440">
<img src="docs/screenshots/statistics-light.png" alt="Statistics" width="440">
</div>

## Installation

### BigCommunity / Arch Linux

ISOVault is packaged for BigCommunity. To build the package from this
repository:

```bash
git clone https://github.com/big-comm/isovault.git
cd isovault/pkgbuild
makepkg -si
```

### Dependencies

| Package | Purpose |
|---|---|
| `gtk4`, `libadwaita` (1.7+) | User interface |
| `python` (3.10+), `python-gobject` | Runtime |
| `python-boto3` | S3 access |
| `libsecret` *(optional)* | Store the credentials in the system keyring |

## Usage

1. Pick a profile in the header (or create one in **Settings → Profile**),
   enter the S3 access key, secret key, endpoint and bucket, then press
   **Test Connection**.
2. Press **Upload ISO**, pick the `.iso` and its `.md5`, and choose the
   destination folder.
3. The public index is updated automatically after each change (or from the
   menu with **Force Update Index**).

| Shortcut | Action |
|---|---|
| <kbd>Ctrl</kbd>+<kbd>F</kbd> | Search files |
| <kbd>Ctrl</kbd>+<kbd>A</kbd> | Select all files |
| <kbd>Ctrl</kbd>+<kbd>R</kbd> / <kbd>F5</kbd> | Refresh |
| <kbd>Ctrl</kbd>+<kbd>,</kbd> | Preferences |
| <kbd>Ctrl</kbd>+<kbd>Q</kbd> | Quit |

Settings and profiles are stored in `~/.config/isovault.conf` (mode `0600`);
older single-repository configurations become the *BigCommunity* profile
automatically.

## Development

```bash
python3 usr/share/isovault/main.py --debug   # run from the source tree
python3 -m pytest                            # tests (GTK tests are skipped without a display)
ruff check usr tests tools
python3 tools/render_preview.py              # preview the public page with sample data
```

```
usr/share/isovault/
├── main.py         application, CLI options and shortcuts
├── config.py       constants (app id, folders, defaults)
├── models/         settings and profiles (private INI file + keyring), FileItem
├── services/       S3 access, HTML generation, index publishing, validation
├── templates/      public download pages (BigCommunity cards, biglinux/ file list)
├── ui/             main window, file browser, pages, dialogs, stylesheet
└── utils/          MD5 parsing/pairing, size formatting, i18n
```

Translations live in [`locale/`](locale/) as gettext `.po` files; the compiled
catalogs are in `usr/share/locale/`.

## License

ISOVault is released under the [MIT License](LICENSE).

<div align="center">
<sub>Made with ❤ by the <a href="https://communitybig.org">BigCommunity</a> team.</sub>
</div>
