"""
Reusable UI components for the main window.
"""

from typing import Callable, List, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GObject, Gtk, Pango  # noqa: E402

from models import FileItem  # noqa: E402
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
    """
    Column view listing the bucket files, with multiple selection.

    The check box of each row mirrors the selection model: a plain click
    selects only that row, the check box (or Ctrl/Shift+click) adds or
    removes rows, Ctrl+A selects everything.
    """

    _FOLDER_CLASSES = ("folder-gnome", "folder-cinnamon", "folder-xfce", "folder-root")

    def __init__(self, on_selection_changed: Callable[[int], None]):
        """
        Args:
            on_selection_changed: Called with the number of selected files
        """
        self._on_selection_changed = on_selection_changed

        self.file_model = Gio.ListStore(item_type=FileItem)
        self.selection_model = Gtk.MultiSelection(model=self.file_model)
        self.selection_model.connect("selection-changed", self._on_model_selection_changed)

        self.column_view = Gtk.ColumnView(model=self.selection_model)
        self.column_view.set_show_row_separators(True)
        self.column_view.set_show_column_separators(True)

        self._add_check_column()
        self._add_column(_("File Name"), lambda item: item.name, expand=True, ellipsize=True)
        self._add_column(_("Folder"), lambda item: item.folder)
        self._add_column(_("Size"), lambda item: item.size_formatted, align=Gtk.Align.END)
        self._add_column(_("Modified"), lambda item: item.modified.strftime("%Y-%m-%d %H:%M"))

        self.widget = Gtk.ScrolledWindow(vexpand=True)
        self.widget.set_child(self.column_view)

    def _add_check_column(self) -> None:
        def on_setup(_factory, cell):
            check = Gtk.CheckButton(halign=Gtk.Align.CENTER, tooltip_text=_("Select"))
            # The check box shows the row's selection state...
            cell.bind_property("selected", check, "active", GObject.BindingFlags.SYNC_CREATE)
            # ...and clicking it adds/removes the row without touching the others
            check.connect("toggled", self._on_check_toggled, cell)
            cell.set_child(check)

        def on_bind(_factory, cell):
            cell.get_child().update_property([Gtk.AccessibleProperty.LABEL], [cell.get_item().name])

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)
        self.column_view.append_column(Gtk.ColumnViewColumn(factory=factory))

    def _on_check_toggled(self, check: Gtk.CheckButton, cell: Gtk.ColumnViewCell) -> None:
        position = cell.get_position()
        if position == Gtk.INVALID_LIST_POSITION or check.get_active() == cell.get_selected():
            return
        if check.get_active():
            self.selection_model.select_item(position, False)
        else:
            self.selection_model.unselect_item(position)

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

    def _on_model_selection_changed(self, _model, _position, _n_items) -> None:
        self._on_selection_changed(self.selected_count)

    @property
    def selected_count(self) -> int:
        return self.selection_model.get_selection().get_size()

    def get_selected_files(self) -> List[FileItem]:
        """Selected files, in list order."""
        selection = self.selection_model.get_selection()
        return [self.file_model.get_item(selection.get_nth(i)) for i in range(selection.get_size())]

    def select_all(self) -> None:
        self.selection_model.select_all()

    def unselect_all(self) -> None:
        self.selection_model.unselect_all()

    def set_files(self, files: List[dict]) -> None:
        """Replace the whole list, keeping the files that were selected (by key)."""
        selected_keys = {item.key for item in self.get_selected_files()}
        items = [FileItem.from_dict(data) for data in files]
        self.file_model.splice(0, self.file_model.get_n_items(), items)

        if selected_keys:
            keep = Gtk.Bitset.new_empty()
            for position, item in enumerate(items):
                if item.key in selected_keys:
                    keep.add(position)
            self.selection_model.set_selection(keep, keep)
