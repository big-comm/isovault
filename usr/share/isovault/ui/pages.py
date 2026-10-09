"""
Secondary pages of the main window (transfers, statistics) and the
storage card shown in the sidebar.
"""

import math
from datetime import datetime
from typing import Dict, List, Sequence

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from config import DEFAULT_FOLDERS  # noqa: E402
from models import FileItem  # noqa: E402
from utils.helpers import format_file_size  # noqa: E402
from utils.i18n import _, ngettext  # noqa: E402

# Distribution colors used where CSS can't reach (the storage bar is drawn with cairo)
DISTRO_COLORS = {"Gnome": "#9141ac", "Cinnamon": "#e66100", "XFCE": "#3584e4", "KDE": "#1d99f3", "Root": "#2ec27e"}

_TRANSFER_ICONS = {
    "upload": "document-send-symbolic",
    "download": "folder-download-symbolic",
    "delete": "user-trash-symbolic",
    "index": "view-refresh-symbolic",
}


def folders_in_use(files: List[FileItem], folders: Sequence[str]) -> List[str]:
    """The profile folders, then any other folder that has files in the bucket."""
    extra = sorted({f.folder for f in files} - set(folders))
    return list(folders) + extra


def page_header(icon_name: str, title: str, subtitle: str) -> Gtk.Box:
    """Big icon + title + subtitle used at the top of every page."""
    icon = Gtk.Image.new_from_icon_name(icon_name)
    icon.set_pixel_size(24)
    icon_box = Gtk.Box(valign=Gtk.Align.CENTER)
    icon_box.add_css_class("page-icon")
    icon_box.append(icon)

    title_label = Gtk.Label(label=title, xalign=0)
    title_label.add_css_class("title-1")
    subtitle_label = Gtk.Label(label=subtitle, xalign=0, wrap=True)
    subtitle_label.add_css_class("dim-label")

    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, hexpand=True)
    text.append(title_label)
    text.append(subtitle_label)

    header = Gtk.Box(spacing=16)
    header.add_css_class("page-header")
    header.append(icon_box)
    header.append(text)
    header.subtitle_label = subtitle_label
    return header


class Transfer:
    """One operation shown in the transfers page"""

    def __init__(self, row: Adw.ActionRow, progress: Gtk.ProgressBar, status: Gtk.Stack):
        self._row = row
        self._progress = progress
        self._status = status
        self.finished = False

    def update(self, message: str, percent: float) -> None:
        self._row.set_subtitle(message)
        self._progress.set_fraction(max(0.0, min(percent, 100.0)) / 100.0)

    def finish(self, summary: str, success: bool) -> None:
        self.finished = True
        self._row.set_subtitle(f"{datetime.now().strftime('%H:%M')} · {summary}")
        self._status.set_visible_child_name("done" if success else "failed")


class TransfersPage(Gtk.Box):
    """History of the operations started in this session"""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.add_css_class("app-page")
        self.append(
            page_header(
                "isovault-transfers-symbolic",
                _("Transfers"),
                _("Uploads, downloads and deletions made in this session."),
            )
        )

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START)
        self.list.add_css_class("boxed-list")
        self.empty = Adw.StatusPage(
            icon_name="isovault-transfers-symbolic",
            title=_("No transfers yet"),
            description=_("Uploads, downloads and deletions will appear here."),
            vexpand=True,
        )
        self.empty.add_css_class("compact")

        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.list)
        self.stack = Gtk.Stack(vexpand=True)
        self.stack.add_named(self.empty, "empty")
        self.stack.add_named(scroll, "list")
        self.append(self.stack)
        self._transfers: List[Transfer] = []

    @property
    def count(self) -> int:
        return len(self._transfers)

    @property
    def active_count(self) -> int:
        return sum(1 for transfer in self._transfers if not transfer.finished)

    def add(self, kind: str, title: str) -> Transfer:
        """Add an operation at the top of the list and return its handle."""
        row = Adw.ActionRow(title=title, title_lines=1)
        icon = Gtk.Image.new_from_icon_name(_TRANSFER_ICONS[kind])
        icon.add_css_class(f"transfer-{kind}")
        row.add_prefix(icon)

        progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=140)
        done = Gtk.Image.new_from_icon_name("object-select-symbolic")
        done.add_css_class("success")
        failed = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        failed.add_css_class("warning")
        status = Gtk.Stack()
        status.add_named(progress, "running")
        status.add_named(done, "done")
        status.add_named(failed, "failed")
        row.add_suffix(status)

        self.list.prepend(row)
        self.stack.set_visible_child_name("list")
        transfer = Transfer(row, progress, status)
        self._transfers.append(transfer)
        return transfer


class StatisticsPage(Gtk.Box):
    """Numbers about the bucket content"""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.add_css_class("app-page")
        self.append(
            page_header("isovault-statistics-symbolic", _("Statistics"), _("Overview of the ISO repository."))
        )
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.content)
        self.append(scroll)
        self.update([])

    def update(self, files: List[FileItem], folders: Sequence[str] = DEFAULT_FOLDERS) -> None:
        """Rebuild the page from the current file list."""
        while child := self.content.get_first_child():
            self.content.remove(child)

        isos = [f for f in files if f.name.lower().endswith(".iso")]
        checksums = [f for f in files if f.name.lower().endswith(".md5")]

        cards = Gtk.Box(spacing=12, homogeneous=True)
        for value, caption in (
            (str(len(isos)), _("ISO images")),
            (str(len(checksums)), _("MD5 checksums")),
            (format_file_size(sum(f.size for f in files)), _("Space used")),
        ):
            cards.append(_stat_card(value, caption))
        self.content.append(cards)

        per_folder = Adw.PreferencesGroup(title=_("By distribution"))
        for folder in folders_in_use(files, folders):
            folder_files = [f for f in files if f.folder == folder]
            if not folder_files:
                continue
            folder_isos = [f for f in folder_files if f.name.lower().endswith(".iso")]
            row = Adw.ActionRow(
                title=folder,
                subtitle=ngettext("{count} ISO · {size}", "{count} ISOs · {size}", len(folder_isos)).format(
                    count=len(folder_isos), size=format_file_size(sum(f.size for f in folder_files))
                ),
            )
            dot = Gtk.Box(valign=Gtk.Align.CENTER)
            dot.add_css_class("legend-dot")
            dot.add_css_class(f"distro-{folder.lower()}")
            row.add_prefix(dot)
            if folder_isos:
                newest = max(folder_isos, key=lambda f: f.modified)
                latest = Gtk.Label(
                    label=_("Latest: {date}").format(date=newest.modified.astimezone().strftime("%x")),
                    tooltip_text=newest.name,
                )
                latest.add_css_class("dim-label")
                row.add_suffix(latest)
            per_folder.add(row)
        if files:
            self.content.append(per_folder)

        missing = _isos_without_checksum(files)
        checksum_group = Adw.PreferencesGroup(
            title=_("Integrity"),
            description=_("ISOs need a .md5 file to show their checksum on the download page."),
        )
        if missing:
            for iso in missing:
                row = Adw.ActionRow(title=iso.name, subtitle=_("No MD5 checksum"), title_lines=1)
                icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
                icon.add_css_class("warning")
                row.add_prefix(icon)
                checksum_group.add(row)
        elif isos:
            row = Adw.ActionRow(title=_("Every ISO has an MD5 checksum"))
            icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
            icon.add_css_class("success")
            row.add_prefix(icon)
            checksum_group.add(row)
        if files:
            self.content.append(checksum_group)


def _stat_card(value: str, caption: str) -> Gtk.Widget:
    value_label = Gtk.Label(label=value, xalign=0)
    value_label.add_css_class("stat-value")
    caption_label = Gtk.Label(label=caption, xalign=0)
    caption_label.add_css_class("dim-label")
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.add_css_class("stat-card")
    card.append(value_label)
    card.append(caption_label)
    return card


def _isos_without_checksum(files: List[FileItem]) -> List[FileItem]:
    names = {f.name.lower() for f in files}
    missing = []
    for item in files:
        name = item.name.lower()
        if name.endswith(".iso") and f"{name}.md5" not in names and f"{name[:-4]}.md5" not in names:
            missing.append(item)
    return sorted(missing, key=lambda f: f.name.lower())


class StorageCard(Gtk.Box):
    """Sidebar card: space used, split by distribution"""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("storage-card")

        title = Gtk.Label(label=_("Storage"), xalign=0)
        title.add_css_class("heading")
        self.append(title)

        self._sizes: Dict[str, int] = {}
        self.bar = Gtk.DrawingArea(content_height=8, hexpand=True)
        self.bar.set_draw_func(self._draw)
        self.append(self.bar)

        self.summary = Gtk.Label(xalign=0)
        self.summary.add_css_class("dim-label")
        self.summary.add_css_class("caption")
        self.append(self.summary)
        self.update([])

    def update(self, files: List[FileItem], folders: Sequence[str] = DEFAULT_FOLDERS) -> None:
        self._sizes = {
            folder: sum(f.size for f in files if f.folder == folder) for folder in folders_in_use(files, folders)
        }
        total = sum(self._sizes.values())
        self.summary.set_text(
            ngettext("{size} in {count} file", "{size} in {count} files", len(files)).format(
                size=format_file_size(total), count=len(files)
            )
        )
        self.bar.set_tooltip_text(
            "\n".join(f"{folder}: {format_file_size(size)}" for folder, size in self._sizes.items() if size)
        )
        self.bar.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        radius = height / 2
        total = sum(self._sizes.values())

        # Track
        _rounded_rect(cr, 0, 0, width, height, radius)
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.18)
        cr.fill()
        if not total:
            return

        _rounded_rect(cr, 0, 0, width, height, radius)
        cr.clip()
        x = 0.0
        for folder, size in self._sizes.items():
            if not size:
                continue
            segment = width * size / total
            color = Gdk.RGBA()
            color.parse(DISTRO_COLORS.get(folder, "#77767b"))  # gray for folders without a known color
            cr.set_source_rgba(color.red, color.green, color.blue, 1)
            cr.rectangle(x, 0, segment, height)
            cr.fill()
            x += segment


def _rounded_rect(cr, x: float, y: float, width: float, height: float, radius: float) -> None:
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()
