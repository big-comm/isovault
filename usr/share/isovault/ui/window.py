"""
Main application window.
"""

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, List, NamedTuple, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from config import APP_NAME, DISTRO_FOLDERS, REFRESH_DELAY_MS, TOAST_TIMEOUT  # noqa: E402
from models import FileItem, SettingsManager  # noqa: E402
from services import FileValidator, HTMLGenerator, S3Service, publish_indexes  # noqa: E402
from utils.i18n import _, ngettext  # noqa: E402

from .components import FileListComponent, ProgressManager  # noqa: E402
from .dialogs import DialogManager  # noqa: E402
from .preferences import PreferencesDialog  # noqa: E402

logger = logging.getLogger(__name__)


class _BatchText(NamedTuple):
    """Translated messages of a batch operation"""

    progress_one: str  # {filename}
    progress_many: str  # {current} {total} {filename}
    done_one: str  # {filename}
    done_all: str  # {total}
    failed_one: str  # {filename}
    summary: str  # {completed} {failed}


def call_on_main(func: Callable, *args: Any) -> None:
    """Run func(*args) once on the GTK main loop (safe from any thread)."""

    def run():
        func(*args)
        return GLib.SOURCE_REMOVE

    GLib.idle_add(run)


def run_in_thread(work: Callable[[], Any], on_done: Callable[[Any], None], on_error: Callable[[Exception], None]) -> None:
    """Run work() in a daemon thread; on_done(result) / on_error(exc) run on the main loop."""

    def runner():
        try:
            result = work()
        except Exception as e:
            logger.exception("Background task failed")
            call_on_main(on_error, e)
        else:
            call_on_main(on_done, result)

    threading.Thread(target=runner, daemon=True).start()


class ISOVaultWindow(Adw.ApplicationWindow):
    """Main window: sidebar with actions, file list, status bar"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.settings_manager = SettingsManager()
        self.s3_service: Optional[S3Service] = None
        self.dialogs = DialogManager(self)

        # Only one transfer/delete/publish runs at a time; listing is independent
        self._busy = False
        # Incremented on every refresh so late results from older ones are dropped
        self._refresh_generation = 0

        self.set_title(APP_NAME)
        self.set_default_size(*self.settings_manager.get_window_size())
        self.connect("close-request", self._on_close_request)

        self.set_content(self._build_ui())
        self._setup_actions()
        self._update_sensitivity()
        self._connect_service()

    # UI construction

    def _build_ui(self) -> Gtk.Widget:
        self.toast_overlay = Adw.ToastOverlay()

        split_view = Adw.OverlaySplitView()
        split_view.set_min_sidebar_width(260)
        split_view.set_max_sidebar_width(320)
        split_view.set_sidebar_width_fraction(0.32)
        split_view.set_sidebar(self._build_sidebar())
        split_view.set_content(self._build_content())

        self.toast_overlay.set_child(split_view)
        return self.toast_overlay

    def _build_sidebar(self) -> Adw.ToolbarView:
        header = Adw.HeaderBar(show_end_title_buttons=False)
        title = Gtk.Label(label=APP_NAME)
        title.add_css_class("heading")
        header.set_title_widget(title)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(6)
        box.set_margin_bottom(12)

        # Folder filter
        self.folder_dropdown = Adw.ComboRow(title=_("Filter by folder"))
        self.folder_dropdown.set_model(Gtk.StringList.new([_("All folders"), *DISTRO_FOLDERS]))
        self.folder_dropdown.connect("notify::selected", lambda *_args: self.refresh_files())
        filter_group = Adw.PreferencesGroup()
        filter_group.add(self.folder_dropdown)
        box.append(filter_group)

        # Selection: counter plus select all / none
        self.selection_group = Adw.PreferencesGroup(title=_("Selection"))
        self.select_all_button = Gtk.Button(label=_("Select All"))
        self.select_all_button.connect("clicked", lambda _button: self.file_list.select_all())
        self.select_none_button = Gtk.Button(label=_("Select None"))
        self.select_none_button.connect("clicked", lambda _button: self.file_list.unselect_all())
        selection_buttons = Gtk.Box(spacing=6, homogeneous=True)
        selection_buttons.append(self.select_all_button)
        selection_buttons.append(self.select_none_button)
        self.selection_group.add(selection_buttons)
        box.append(self.selection_group)

        # Actions on the selected files
        actions_group = Adw.PreferencesGroup()
        self.copy_link_row = self._action_row(_("Copy Link"), _("Copy public URL"), "edit-copy-symbolic", self.on_copy_link_clicked)
        self.download_row = self._action_row(_("Download"), _("Save file locally"), "folder-download-symbolic", self.on_download_clicked)
        self.delete_row = self._action_row(_("Delete"), _("Remove from storage"), "user-trash-symbolic", self.on_delete_clicked, destructive=True)
        for row in (self.copy_link_row, self.download_row, self.delete_row):
            actions_group.add(row)
        box.append(actions_group)

        # Quick settings (the only place where these toggles live)
        settings_group = Adw.PreferencesGroup()
        self.quick_setting_rows = {}
        for section, key, title in (
            ("general", "auto_refresh", _("Auto Refresh")),
            ("ui", "confirm_deletions", _("Confirm Deletions")),
            ("ui", "auto_update_index", _("Auto Update Index")),
        ):
            row = Adw.SwitchRow(title=title, active=self.settings_manager.get(section, key))
            row.connect("notify::active", self._on_quick_setting_toggled, section, key)
            settings_group.add(row)
            self.quick_setting_rows[(section, key)] = row
        box.append(settings_group)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(box)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(scroll)
        return toolbar

    def _action_row(self, title: str, subtitle: str, icon: str, handler: Callable[[], None], destructive: bool = False) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
        button = Gtk.Button(icon_name="go-next-symbolic", valign=Gtk.Align.CENTER, tooltip_text=title)
        if destructive:
            button.add_css_class("destructive-action")
        button.connect("clicked", lambda _button: handler())
        row.add_suffix(button)
        row.set_activatable_widget(button)
        return row

    def _build_content(self) -> Adw.ToolbarView:
        header = Adw.HeaderBar(show_start_title_buttons=False)

        self.upload_button = Gtk.Button(label=_("Upload ISO"))
        self.upload_button.add_css_class("suggested-action")
        self.upload_button.connect("clicked", lambda _button: self.on_upload_clicked())
        header.set_title_widget(self.upload_button)

        main_section = Gio.Menu()
        main_section.append(_("Preferences"), "win.preferences")
        main_section.append(_("Force Update Index"), "win.force-index")
        main_section.append(_("Refresh"), "win.refresh")
        about_section = Gio.Menu()
        about_section.append(_("About"), "win.about")
        menu = Gio.Menu()
        menu.append_section(None, main_section)
        menu.append_section(None, about_section)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text=_("Application menu")))

        self.file_list = FileListComponent(on_selection_changed=lambda _count: self._update_sensitivity())

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self.file_list.widget)
        toolbar.add_bottom_bar(self._build_status_bar())
        return toolbar

    def _build_status_bar(self) -> Gtk.Box:
        self.status_label = Gtk.Label(label=_("Ready"), halign=Gtk.Align.START, hexpand=True)
        progress_bar = Gtk.ProgressBar(show_text=True, visible=False)
        progress_bar.set_size_request(300, -1)
        self.progress_manager = ProgressManager(progress_bar, self.status_label)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.append(self.status_label)
        box.append(progress_bar)
        return box

    def _setup_actions(self) -> None:
        for name, handler in (
            ("preferences", self._on_preferences_action),
            ("force-index", lambda *_args: self._publish_index(manual=True)),
            ("refresh", lambda *_args: self.refresh_files()),
            ("about", lambda *_args: self.dialogs.show_about()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

    # State

    def _connect_service(self) -> None:
        """(Re)create the S3 service from the current settings and load the list."""
        self.s3_service = None
        self.file_list.set_files([])

        if not self.settings_manager.has_s3_credentials():
            self.status_label.set_text(_("Please configure S3 credentials in Preferences"))
            self.show_toast(_("Please configure S3 credentials in Preferences"))
            self._update_sensitivity()
            return

        try:
            self.s3_service = S3Service(
                self.settings_manager.get_s3_config(),
                self.settings_manager.get("web", "base_url"),
            )
        except Exception as e:
            logger.exception("Could not create S3 client")
            self.status_label.set_text(_("Warning: Could not connect to S3 storage"))
            self.show_toast(_("Warning: Could not connect to S3 storage") + f": {e}")

        self._update_sensitivity()
        self.refresh_files()

    def _update_sensitivity(self) -> None:
        connected = self.s3_service is not None
        selected = self.file_list.selected_count
        total = self.file_list.file_model.get_n_items()
        has_selection = selected > 0

        if has_selection:
            self.selection_group.set_description(
                ngettext("{selected} of {total} file selected", "{selected} of {total} files selected", total).format(
                    selected=selected, total=total
                )
            )
        else:
            self.selection_group.set_description(_("No files selected"))
        self.select_all_button.set_sensitive(selected < total)
        self.select_none_button.set_sensitive(has_selection)

        self.upload_button.set_sensitive(connected and not self._busy)
        self.copy_link_row.set_sensitive(connected and has_selection)
        self.download_row.set_sensitive(connected and has_selection and not self._busy)
        self.delete_row.set_sensitive(connected and has_selection and not self._busy)
        for name in ("force-index", "refresh"):
            self.lookup_action(name).set_enabled(connected and (name == "refresh" or not self._busy))

    def get_selected_folder(self) -> Optional[str]:
        """Folder chosen in the sidebar filter (None = all folders)."""
        selected = self.folder_dropdown.get_selected()
        return DISTRO_FOLDERS[selected - 1] if selected > 0 else None

    # Exclusive operations (upload, download, delete, publish)

    def _start_operation(self, message: str, work: Callable[[], Any], on_done: Callable[[Any], None], error_message: str) -> None:
        if self._busy:
            self.show_toast(_("Another operation is in progress"))
            return

        self._busy = True
        self._update_sensitivity()
        self.progress_manager.show(message)

        def finish():
            self._busy = False
            self.progress_manager.hide()
            self._update_sensitivity()

        def done(result):
            finish()
            on_done(result)

        def failed(error):
            finish()
            self.show_toast(f"{error_message}: {error}")

        run_in_thread(work, done, failed)

    def _progress_reporter(self, start: float = 0.0, span: float = 100.0) -> Callable[[float], None]:
        """
        Progress callback for worker threads, mapped into [start, start + span]
        of the bar. Only whole-percent changes reach the main loop.
        """
        last = [-1]

        def report(percent: float) -> None:
            overall = start + span * percent / 100.0
            if int(overall) != last[0]:
                last[0] = int(overall)
                call_on_main(self.progress_manager.update, overall)

        return report

    def _after_bucket_changed(self) -> None:
        """Refresh the list and republish the index, as configured."""
        if self.settings_manager.get("general", "auto_refresh"):
            GLib.timeout_add(REFRESH_DELAY_MS, self._delayed_refresh)
        if self.settings_manager.get("ui", "auto_update_index"):
            self._publish_index(manual=False)

    def _delayed_refresh(self) -> bool:
        self.refresh_files()
        return GLib.SOURCE_REMOVE

    # Upload

    def on_upload_clicked(self) -> None:
        if not self.s3_service:
            self.show_toast(_("Please configure S3 credentials first"))
            return
        self.dialogs.choose_files_to_upload(
            self._on_files_chosen, self.settings_manager.get("general", "last_directory")
        )

    def _on_files_chosen(self, file_paths: List[str], parent_directory: Optional[str]) -> None:
        if parent_directory:
            self.settings_manager.set("general", "last_directory", parent_directory)
            self.settings_manager.save_settings()

        valid_files, invalid_files = FileValidator.validate_multiple_files(file_paths)
        if not valid_files:
            self.dialogs.show_invalid_files(invalid_files)
            return

        def upload(folder: str) -> None:
            self.settings_manager.set("general", "last_upload_folder", folder)
            self.settings_manager.save_settings()
            self._upload_files(valid_files, folder)

        self.dialogs.choose_upload_folder(
            valid_files, invalid_files, upload, self.settings_manager.get("general", "last_upload_folder")
        )

    def _upload_files(self, file_paths: List[str], folder: str) -> None:
        """Upload files one after another; a failed file doesn't stop the rest."""
        service = self.s3_service
        self._run_batch(
            [Path(path).name for path in file_paths],
            lambda index, report: service.upload_file(file_paths[index], folder, report),
            _BatchText(
                progress_one=_("Uploading {filename}..."),
                progress_many=_("Uploading {current}/{total}: {filename}"),
                done_one=_("Successfully uploaded {filename}"),
                done_all=_("Successfully uploaded all {total} files!"),
                failed_one=_("Failed to upload {filename}"),
                summary=_("Upload complete: {completed} successful, {failed} failed"),
            ),
            on_finished=self._after_bucket_changed,
        )

    # Selected file actions

    def on_copy_link_clicked(self) -> None:
        selected = self.file_list.get_selected_files()
        if not selected or not self.s3_service:
            return
        urls = [self.s3_service.get_public_url(item.key) for item in selected]
        self.get_clipboard().set("\n".join(urls))
        if len(urls) == 1:
            self.show_toast(_("Link copied: {url}").format(url=urls[0]))
        else:
            self.show_toast(ngettext("{count} link copied", "{count} links copied", len(urls)).format(count=len(urls)))

    def on_download_clicked(self) -> None:
        selected = self.file_list.get_selected_files()
        if len(selected) == 1:
            item = selected[0]
            self.dialogs.choose_download_path(item.name, lambda path: self._download_files(selected, [path]))
        elif selected:
            self.dialogs.choose_download_folder(
                lambda folder: self._download_files(selected, [os.path.join(folder, item.name) for item in selected])
            )

    def _download_files(self, items: List[FileItem], save_paths: List[str]) -> None:
        """Download each item to the matching path. In a folder download, existing files are not overwritten."""
        service = self.s3_service
        overwrite = len(items) == 1  # the save dialog already asked about overwriting

        def step(index, report):
            if not overwrite and os.path.exists(save_paths[index]):
                raise FileExistsError(_("File already exists"))
            service.download_file(items[index].key, save_paths[index], report)

        self._run_batch(
            [item.name for item in items],
            step,
            _BatchText(
                progress_one=_("Downloading {filename}..."),
                progress_many=_("Downloading {current}/{total}: {filename}"),
                done_one=_("Successfully downloaded {filename}"),
                done_all=_("Successfully downloaded all {total} files!"),
                failed_one=_("Failed to download {filename}"),
                summary=_("Download complete: {completed} successful, {failed} failed"),
            ),
            on_finished=None,
        )

    def on_delete_clicked(self) -> None:
        selected = self.file_list.get_selected_files()
        if not selected:
            return
        if self.settings_manager.get("ui", "confirm_deletions"):
            self.dialogs.confirm_delete([item.name for item in selected], lambda: self._delete_files(selected))
        else:
            self._delete_files(selected)

    def _delete_files(self, items: List[FileItem]) -> None:
        service = self.s3_service
        self._run_batch(
            [item.name for item in items],
            lambda index, _report: service.delete_file(items[index].key),
            _BatchText(
                progress_one=_("Deleting {filename}..."),
                progress_many=_("Deleting {current}/{total}: {filename}"),
                done_one=_("Successfully deleted {filename}"),
                done_all=_("Successfully deleted all {total} files!"),
                failed_one=_("Failed to delete {filename}"),
                summary=_("Delete complete: {completed} successful, {failed} failed"),
            ),
            on_finished=self._after_bucket_changed,
        )

    def _run_batch(
        self,
        names: List[str],
        step: Callable[[int, Callable[[float], None]], None],
        text: "_BatchText",
        on_finished: Optional[Callable[[], None]],
    ) -> None:
        """
        Run step(index, progress_callback) for each file in one worker thread.

        A failing file doesn't stop the others; the result is summarized in a
        toast. on_finished runs if at least one file succeeded.
        """
        total = len(names)

        def progress_message(index: int) -> str:
            if total == 1:
                return text.progress_one.format(filename=names[0])
            return text.progress_many.format(current=index + 1, total=total, filename=names[index])

        def work():
            failures = []
            for index, name in enumerate(names):
                call_on_main(self.status_label.set_text, progress_message(index))
                try:
                    step(index, self._progress_reporter(index * 100 / total, 100 / total))
                except Exception as e:
                    logger.exception("%s failed", progress_message(index))
                    failures.append((name, str(e)))
            return failures

        def done(failures):
            if not failures:
                if total == 1:
                    self.show_toast(text.done_one.format(filename=names[0]))
                else:
                    self.show_toast(text.done_all.format(total=total))
            elif total == 1:
                self.show_toast(text.failed_one.format(filename=failures[0][0]) + f": {failures[0][1]}")
            else:
                self.show_toast(text.summary.format(completed=total - len(failures), failed=len(failures)))
            if on_finished and len(failures) < total:
                on_finished()

        self._start_operation(progress_message(0), work, done, text.failed_one.format(filename=names[0]))

    # Index pages

    def _publish_index(self, manual: bool) -> None:
        """Regenerate the public index pages. Success is only announced when requested manually."""
        service = self.s3_service
        if not service:
            self.show_toast(_("Please configure S3 credentials first"))
            return

        def done(_uploaded):
            if manual:
                self.show_toast(_("Index files updated!"))

        self._start_operation(
            _("Updating index files..."),
            lambda: publish_indexes(service, HTMLGenerator(service.get_public_url)),
            done,
            _("Failed to update index files"),
        )

    # File list

    def refresh_files(self) -> None:
        """Reload the file list in the background."""
        service = self.s3_service
        if not service:
            return

        self._refresh_generation += 1
        generation = self._refresh_generation
        folder = self.get_selected_folder()
        include_index = self.settings_manager.get("web", "show_index_files")
        if not self._busy:
            self.status_label.set_text(_("Loading files..."))

        def done(files):
            if generation != self._refresh_generation:
                return  # a newer refresh was started meanwhile
            self.file_list.set_files(files)
            self._update_sensitivity()
            if not self._busy:
                self.status_label.set_text(self._files_status_text(len(files), folder))

        def failed(error):
            if generation != self._refresh_generation:
                return
            if not self._busy:
                self.status_label.set_text(_("Failed to refresh file list"))
            self.show_toast(_("Failed to connect to S3 storage. Check credentials and connection.") + f" ({error})")

        run_in_thread(lambda: service.list_files(folder, include_index), done, failed)

    @staticmethod
    def _files_status_text(count: int, folder: Optional[str]) -> str:
        if folder:
            return ngettext("{count} file in {folder}", "{count} files in {folder}", count).format(count=count, folder=folder)
        return ngettext("{count} file", "{count} files", count).format(count=count)

    # Settings

    def _on_quick_setting_toggled(self, row: Adw.SwitchRow, _pspec, section: str, key: str) -> None:
        self.settings_manager.set(section, key, row.get_active())
        self.settings_manager.save_settings()

    def _on_preferences_action(self, *_args) -> None:
        PreferencesDialog(self.settings_manager, self._on_settings_changed).present(self)

    def _on_settings_changed(self, s3_changed: bool) -> None:
        # Preferences may have reset the quick toggles
        for (section, key), row in self.quick_setting_rows.items():
            if row.get_active() != self.settings_manager.get(section, key):
                row.set_active(self.settings_manager.get(section, key))

        if s3_changed:
            self._connect_service()
            return

        if self.s3_service:
            self.s3_service.base_url = self.settings_manager.get("web", "base_url").rstrip("/")
        self.refresh_files()

    def _on_close_request(self, _window) -> bool:
        width, height = self.get_default_size()
        self.settings_manager.set_window_size(width, height)
        self.settings_manager.save_settings()
        return False  # let the window close

    def show_toast(self, message: str) -> None:
        # Plain text: file names may contain markup characters such as "&"
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=TOAST_TIMEOUT, use_markup=False))
