"""
Reusable UI components for the main window.
"""

from typing import Callable, List, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from utils.i18n import _  # noqa: E402

_MAX_LISTED_FILES = 6


def file_list_group(title: str, description: str, files: List[Tuple[str, str]]) -> Adw.PreferencesGroup:
    """
    Boxed list of files used by the upload and delete dialogs.

    Args:
        files: (file name, subtitle) pairs; only the first few are listed
    """
    group = Adw.PreferencesGroup(title=title, description=description)
    for name, subtitle in files[:_MAX_LISTED_FILES]:
        row = Adw.ActionRow(title=name, subtitle=subtitle, title_lines=1)
        row.set_tooltip_text(name)
        is_iso = name.lower().endswith(".iso")
        icon = Gtk.Image.new_from_icon_name("media-optical-symbolic" if is_iso else "text-x-generic-symbolic")
        icon.add_css_class("file-type-icon")
        row.add_prefix(icon)
        group.add(row)

    hidden = len(files) - _MAX_LISTED_FILES
    if hidden > 0:
        more = Gtk.Label(label=_("... and {more_count} more files").format(more_count=hidden), xalign=0, margin_top=6)
        more.add_css_class("dim-label")
        group.add(more)
    return group


class ProgressManager:
    """Message + progress bar of the running operation (shown in the bottom bar)"""

    def __init__(self, progress_bar: Gtk.ProgressBar, message_label: Gtk.Label, on_visibility_changed: Callable[[], None]):
        self.progress_bar = progress_bar
        self.message_label = message_label
        self._on_visibility_changed = on_visibility_changed
        self.is_visible = False

    def show(self, message: str) -> None:
        self.message_label.set_text(message)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("0%")
        self.is_visible = True
        self._on_visibility_changed()

    def set_message(self, message: str) -> None:
        self.message_label.set_text(message)

    def update(self, percent: float) -> bool:
        """Set progress (0-100). Returns False so it can be used with GLib.idle_add."""
        if self.is_visible:
            self.progress_bar.set_fraction(max(0.0, min(percent, 100.0)) / 100.0)
            self.progress_bar.set_text(f"{percent:.0f}%")
        return False

    def hide(self) -> None:
        self.is_visible = False
        self._on_visibility_changed()
