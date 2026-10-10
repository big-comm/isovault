"""
Upload dialog: shows the chosen files and lets the user pick the bucket folder.
"""

import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Pango  # noqa: E402

from config import DEFAULT_FOLDERS, ROOT_FOLDER  # noqa: E402
from utils.helpers import format_file_size  # noqa: E402
from utils.i18n import _, ngettext  # noqa: E402

from .components import file_list_group  # noqa: E402

class UploadDialog(Adw.Dialog):
    """Pick the destination folder for files about to be uploaded"""

    def __init__(
        self,
        valid_files: List[str],
        invalid_files: List[Tuple[str, str]],
        on_upload: Callable[[str], None],
        initial_folder: Optional[str] = None,
        folders: Sequence[str] = DEFAULT_FOLDERS,
    ):
        """
        Args:
            valid_files: Paths that will be uploaded
            invalid_files: (file name, reason) of rejected files, shown for information
            on_upload: Called with the chosen folder when the user confirms
            initial_folder: Folder preselected (e.g. the last one used)
            folders: Destination folders offered (the profile's folders)
        """
        self.folders = list(folders)
        super().__init__(title=_("Upload Files"), content_width=600)
        self.add_css_class("upload-dialog")
        self._on_upload = on_upload
        self.folder_buttons: Dict[str, Gtk.ToggleButton] = {}

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(12)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.append(self._build_files_section(valid_files))
        if invalid_files:
            content.append(self._build_rejected_section(invalid_files))
        content.append(self._build_folder_section())

        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(content)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(scroll)
        toolbar.add_bottom_bar(self._build_action_bar())
        self.set_child(toolbar)

        start = initial_folder if initial_folder in self.folders else self.folders[0]
        self.folder_buttons[start].set_active(True)

    # Sections

    def _build_files_section(self, paths: List[str]) -> Gtk.Widget:
        sizes = [os.path.getsize(path) for path in paths]
        return file_list_group(
            ngettext("{count} file to upload", "{count} files to upload", len(paths)).format(count=len(paths)),
            _("Total: {size}").format(size=format_file_size(sum(sizes))),
            [(Path(path).name, format_file_size(size)) for path, size in zip(paths, sizes)],
        )

    def _build_rejected_section(self, invalid_files: List[Tuple[str, str]]) -> Gtk.Widget:
        expander = Adw.ExpanderRow(
            title=ngettext(
                "{count} file will be skipped", "{count} files will be skipped", len(invalid_files)
            ).format(count=len(invalid_files)),
            subtitle=_("Only non-empty ISO and MD5 files can be uploaded"),
        )
        expander.add_css_class("rejected-files")
        expander.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
        for name, reason in invalid_files:
            expander.add_row(Adw.ActionRow(title=name, subtitle=reason, title_lines=1))

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        listbox.append(expander)
        return listbox

    def _build_folder_section(self) -> Gtk.Widget:
        group = Adw.PreferencesGroup(title=_("Destination Folder"))

        grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        leader = None
        for index, folder in enumerate(self.folders):
            button = self._folder_card(folder)
            if leader is None:
                leader = button
            else:
                button.set_group(leader)
            grid.attach(button, index % 2, index // 2, 1, 1)
            self.folder_buttons[folder] = button

        group.add(grid)
        return group

    def _folder_card(self, folder: str) -> Gtk.ToggleButton:
        path = "/" if folder == ROOT_FOLDER else f"/{folder}/"

        badge = Gtk.Image.new_from_icon_name("drive-harddisk-symbolic" if folder == ROOT_FOLDER else "folder-symbolic")
        badge.set_pixel_size(22)
        badge.add_css_class("folder-badge")
        badge.add_css_class(f"badge-{folder.lower()}")

        name = Gtk.Label(label=folder, xalign=0)
        name.add_css_class("heading")
        location = Gtk.Label(label=path, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        location.add_css_class("dim-label")
        location.add_css_class("folder-path")

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, hexpand=True)
        text.append(name)
        text.append(location)

        check = Gtk.Image.new_from_icon_name("object-select-symbolic")
        check.add_css_class("selected-mark")

        box = Gtk.Box(spacing=12)
        box.append(badge)
        box.append(text)
        box.append(check)

        button = Gtk.ToggleButton(child=box)
        button.add_css_class("folder-card")
        button.update_property([Gtk.AccessibleProperty.LABEL], [f"{folder} ({path})"])
        button.connect("toggled", self._on_folder_toggled, folder)
        return button

    def _build_action_bar(self) -> Gtk.Widget:
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda _button: self.close())

        self.upload_button = Gtk.Button()
        self.upload_button.add_css_class("suggested-action")
        self.upload_button.add_css_class("pill")
        self.upload_button.connect("clicked", self._on_upload_clicked)
        self.set_default_widget(self.upload_button)

        bar = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        bar.set_margin_top(12)
        bar.set_margin_bottom(12)
        bar.set_margin_start(24)
        bar.set_margin_end(24)
        bar.append(cancel)
        bar.append(self.upload_button)
        cancel.add_css_class("pill")
        return bar

    # Behaviour

    @property
    def selected_folder(self) -> Optional[str]:
        return next((folder for folder, button in self.folder_buttons.items() if button.get_active()), None)

    def _on_folder_toggled(self, button: Gtk.ToggleButton, folder: str) -> None:
        if button.get_active():
            self.upload_button.set_label(_("Upload to {folder}").format(folder=folder))

    def _on_upload_clicked(self, _button) -> None:
        folder = self.selected_folder
        if folder:
            self.close()
            self._on_upload(folder)
