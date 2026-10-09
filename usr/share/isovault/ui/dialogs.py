"""
Dialogs used by the main window (file choosers, confirmations, about).
"""

import logging
import os
from typing import Callable, List, Optional, Sequence, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from config import APP_ICON, APP_NAME, APP_VERSION, DEFAULT_FOLDERS, SUPPORTED_EXTENSIONS  # noqa: E402
from models import FileItem  # noqa: E402
from utils.i18n import _  # noqa: E402

from .delete_dialog import DeleteDialog  # noqa: E402
from .upload_dialog import UploadDialog  # noqa: E402

logger = logging.getLogger(__name__)

_MAX_LISTED_FILES = 5


def _bullet_list(lines: List[str]) -> str:
    """Bulleted text, truncated to a few entries."""
    text = "\n".join(f"• {line}" for line in lines[:_MAX_LISTED_FILES])
    if len(lines) > _MAX_LISTED_FILES:
        text += "\n" + _("... and {more_count} more files").format(more_count=len(lines) - _MAX_LISTED_FILES)
    return text


def _was_dismissed(error: GLib.Error) -> bool:
    return error.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED) or error.matches(
        Gtk.DialogError.quark(), Gtk.DialogError.CANCELLED
    )


class DialogManager:
    """Creates the dialogs, always transient for the main window"""

    def __init__(self, parent_window: Gtk.Window):
        self.parent_window = parent_window

    def choose_files_to_upload(
        self, callback: Callable[[List[str], Optional[str]], None], last_directory: str = ""
    ) -> None:
        """Ask for files; callback(paths, parent_directory) runs only if something was picked."""
        supported = Gtk.FileFilter()
        supported.set_name(_("Supported files (ISO, MD5)"))
        for ext in SUPPORTED_EXTENSIONS:
            supported.add_suffix(ext.lstrip("."))  # add_suffix is case-insensitive

        all_files = Gtk.FileFilter()
        all_files.set_name(_("All files"))
        all_files.add_pattern("*")

        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        filters.append(supported)
        filters.append(all_files)

        dialog = Gtk.FileDialog(title=_("Select ISO or MD5 files to upload"), modal=True)
        dialog.set_filters(filters)
        dialog.set_default_filter(supported)
        if last_directory and os.path.isdir(last_directory):
            dialog.set_initial_folder(Gio.File.new_for_path(last_directory))

        def on_done(dialog, result):
            try:
                files = dialog.open_multiple_finish(result)
            except GLib.Error as e:
                if not _was_dismissed(e):
                    self.show_error(_("Upload Error"), e.message)
                return

            paths = [path for path in (f.get_path() for f in files) if path]
            if not paths:
                self.show_error(_("Upload Error"), _("Failed to get file paths"))
                return
            callback(paths, os.path.dirname(paths[0]))

        dialog.open_multiple(self.parent_window, None, on_done)

    def choose_download_path(self, filename: str, callback: Callable[[str], None]) -> None:
        """Ask where to save a file; callback(path) runs only if accepted."""
        dialog = Gtk.FileDialog(title=_("Save {filename}").format(filename=filename), modal=True)
        dialog.set_initial_name(filename)

        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads and os.path.isdir(downloads):
            dialog.set_initial_folder(Gio.File.new_for_path(downloads))

        def on_done(dialog, result):
            try:
                file = dialog.save_finish(result)
            except GLib.Error as e:
                if not _was_dismissed(e):
                    self.show_error(_("Download Error"), e.message)
                return

            path = file.get_path() if file else None
            if path:
                callback(path)
            else:
                self.show_error(_("Download Error"), _("Failed to get save path"))

        dialog.save(self.parent_window, None, on_done)

    def choose_download_folder(self, callback: Callable[[str], None]) -> None:
        """Ask for a local folder to save several files; callback(path) runs only if accepted."""
        dialog = Gtk.FileDialog(title=_("Choose where to save the files"), modal=True)
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads and os.path.isdir(downloads):
            dialog.set_initial_folder(Gio.File.new_for_path(downloads))

        def on_done(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error as e:
                if not _was_dismissed(e):
                    self.show_error(_("Download Error"), e.message)
                return

            path = folder.get_path() if folder else None
            if path:
                callback(path)
            else:
                self.show_error(_("Download Error"), _("Failed to get save path"))

        dialog.select_folder(self.parent_window, None, on_done)

    def choose_upload_folder(
        self,
        valid_files: List[str],
        invalid_files: List[Tuple[str, str]],
        callback: Callable[[str], None],
        initial_folder: Optional[str] = None,
        folders: Sequence[str] = DEFAULT_FOLDERS,
    ) -> None:
        """
        Show the files about to be uploaded (and any rejected ones) and ask the
        destination folder. callback(folder) runs only if the user confirms.
        """
        UploadDialog(valid_files, invalid_files, callback, initial_folder, folders).present(self.parent_window)

    def show_invalid_files(self, invalid_files: List[Tuple[str, str]]) -> None:
        """Explain why none of the selected files can be uploaded."""
        body = _("Found {invalid_count} invalid files").format(invalid_count=len(invalid_files))
        body += ":\n\n" + _bullet_list([f"{name}: {reason}" for name, reason in invalid_files])
        self.show_error(_("File Validation Results"), body)

    def confirm_delete(self, items: List[FileItem], callback: Callable[[], None]) -> None:
        """List the files that will be deleted; callback() runs only if the user confirms."""
        DeleteDialog(items, callback).present(self.parent_window)

    def show_about(self) -> None:
        dialog = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ICON,
            version=APP_VERSION,
            developer_name="BigCommunity",
            website="https://communitybig.org",
            issue_url="https://github.com/big-comm/isovault/issues",
            comments=_("ISO file manager for CDN77 storage"),
            license_type=Gtk.License.MIT_X11,
        )
        dialog.present(self.parent_window)

    def show_error(self, title: str, message: str) -> None:
        dialog = Adw.AlertDialog(heading=title, body=message)
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self.parent_window)
