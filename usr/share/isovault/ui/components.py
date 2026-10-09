"""
Reusable UI components for the main window.
"""

from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, Gtk, Pango  # noqa: E402

from models import FileItem  # noqa: E402
from utils.i18n import _  # noqa: E402


class ProgressManager:
    """Status label plus a progress bar shown only while an operation runs"""

    def __init__(self, progress_bar: Gtk.ProgressBar, status_label: Gtk.Label):
        self.progress_bar = progress_bar
        self.status_label = status_label

    @property
    def is_visible(self) -> bool:
        return self.progress_bar.get_visible()

    def show(self, message: str) -> None:
        self.status_label.set_text(message)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("0%")
        self.progress_bar.set_visible(True)

    def update(self, percent: float) -> bool:
        """Set progress (0-100). Returns False so it can be used with GLib.idle_add."""
        if self.is_visible:
            self.progress_bar.set_fraction(max(0.0, min(percent, 100.0)) / 100.0)
            self.progress_bar.set_text(f"{percent:.0f}%")
        return False

    def hide(self) -> None:
        self.progress_bar.set_visible(False)


class FileListComponent:
    """Column view listing the bucket files"""

    _FOLDER_CLASSES = ("folder-gnome", "folder-cinnamon", "folder-xfce", "folder-root")

    def __init__(self, on_selection_changed: Callable[[bool], None]):
        """
        Args:
            on_selection_changed: Called with True/False when a file gets (de)selected
        """
        self._on_selection_changed = on_selection_changed

        self.file_model = Gio.ListStore(item_type=FileItem)
        self.selection_model = Gtk.SingleSelection(model=self.file_model)
        self.selection_model.connect("notify::selected", self._on_selected_notify)

        self.column_view = Gtk.ColumnView(model=self.selection_model)
        self.column_view.set_show_row_separators(True)
        self.column_view.set_show_column_separators(True)

        self._add_column(_("File Name"), lambda item: item.name, expand=True, ellipsize=True)
        self._add_column(_("Folder"), lambda item: item.folder)
        self._add_column(_("Size"), lambda item: item.size_formatted, align=Gtk.Align.END)
        self._add_column(_("Modified"), lambda item: item.modified.strftime("%Y-%m-%d %H:%M"))

        self.widget = Gtk.ScrolledWindow(vexpand=True)
        self.widget.set_child(self.column_view)

    def _add_column(
        self,
        title: str,
        text_of: Callable[[FileItem], str],
        expand: bool = False,
        align: Gtk.Align = Gtk.Align.START,
        ellipsize: bool = False,
    ) -> None:
        def on_setup(_factory, list_item):
            label = Gtk.Label(halign=align, hexpand=True)
            if ellipsize:
                label.set_ellipsize(Pango.EllipsizeMode.END)
            box = Gtk.Box(hexpand=True)
            box.append(label)
            list_item.set_child(box)

        def on_bind(_factory, list_item):
            item = list_item.get_item()
            box = list_item.get_child()
            label = box.get_first_child()
            text = text_of(item)
            label.set_text(text)
            if ellipsize:
                label.set_tooltip_text(text)
            for css_class in self._FOLDER_CLASSES:
                box.remove_css_class(css_class)
            box.add_css_class(f"folder-{item.folder.lower()}")

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)

        column = Gtk.ColumnViewColumn(title=title, factory=factory)
        column.set_resizable(True)
        column.set_expand(expand)
        self.column_view.append_column(column)

    def _on_selected_notify(self, selection_model, _pspec) -> None:
        self._on_selection_changed(selection_model.get_selected() != Gtk.INVALID_LIST_POSITION)

    def get_selected_file(self) -> Optional[FileItem]:
        position = self.selection_model.get_selected()
        if position == Gtk.INVALID_LIST_POSITION:
            return None
        return self.file_model.get_item(position)

    def set_files(self, files: List[dict]) -> None:
        """Replace the whole list in a single model update."""
        items = [FileItem.from_dict(data) for data in files]
        self.file_model.splice(0, self.file_model.get_n_items(), items)
