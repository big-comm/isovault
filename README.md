# ISOVault

GTK4/libadwaita app to manage the BigCommunity ISO images stored on CDN77 S3
storage: upload, download, delete, copy public links and publish the public
download page (`index.html`) with each ISO's MD5 checksum.

## Layout

```
usr/share/isovault/
├── main.py              # Adw.Application, CLI options, shortcuts
├── config.py            # constants (app id, folders, defaults)
├── models/              # SettingsManager (~/.config/isovault.conf, mode 0600), FileItem
├── services/            # S3Service, HTMLGenerator, publish_indexes, FileValidator
├── templates/           # page.html, index.css, index.js of the public page
├── ui/                  # main window, dialogs, preferences, style.css
└── utils/               # MD5 parsing/pairing, size formatting, i18n
```

A checksum is shown for `name.iso` when `name.iso.md5` or `name.md5` exists
in the same folder.

## Development

```bash
python3 usr/share/isovault/main.py --debug   # run from the source tree
python3 -m pytest                            # tests (GTK tests are skipped without a display)
ruff check usr tests tools
python3 tools/render_preview.py              # writes preview-index.html with sample data
```

## License

MIT, see [LICENSE](LICENSE).
