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

from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

from config import APP_ICON, APP_NAME, REFRESH_DELAY_MS, ROOT_FOLDER, TOAST_TIMEOUT  # noqa: E402
from models import FileItem, SettingsManager  # noqa: E402
from services import FileValidator, S3Service, create_html_generator, publish_indexes  # noqa: E402
from utils.helpers import format_file_size  # noqa: E402
from utils.i18n import _, ngettext  # noqa: E402

from .components import ProgressManager  # noqa: E402
from .file_browser import FileBrowser  # noqa: E402
from .pages import StatisticsPage, StorageCard, Transfer, TransfersPage, page_header  # noqa: E402
from .dialogs import DialogManager  # noqa: E402
from .preferences import SettingsPage  # noqa: E402

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
    """Main window: navigation sidebar, file browser, transfers and statistics pages"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.settings_manager = SettingsManager()
        self.s3_service: Optional[S3Service] = None
        self.dialogs = DialogManager(self)

        # Only one transfer/delete/publish runs at a time; listing is independent
        self._busy = False
        # Incremented on every refresh so late results from older ones are dropped
        self._refresh_generation = 0
        self._current_transfer: Optional[Transfer] = None

        self.set_title(APP_NAME)
        self.add_css_class("isovault-window")
        style_manager = Adw.StyleManager.get_default()
        style_manager.connect("notify::dark", lambda manager, _p: self._follow_color_scheme(manager))
        self._follow_color_scheme(style_manager)
        self.set_default_size(*self.settings_manager.get_window_size())
        self.set_size_request(360, 480)
        self.connect("close-request", self._on_close_request)

        self.set_content(self._build_ui())
        self._setup_actions()
        self._update_sensitivity()
        self._connect_service()

    def _follow_color_scheme(self, style_manager: Adw.StyleManager) -> None:
        """Distribution colors need lighter variants on dark backgrounds."""
        if style_manager.get_dark():
            self.add_css_class("dark-theme")
        else:
            self.remove_css_class("dark-theme")

    # UI construction

    def _build_ui(self) -> Gtk.Widget:
        self.split_view = Adw.OverlaySplitView(min_sidebar_width=200, max_sidebar_width=280, sidebar_width_fraction=0.2)
        self.split_view.set_sidebar(self._build_sidebar())
        self.split_view.set_content(self._build_pages())

        self.toast_overlay = Adw.ToastOverlay(child=self.split_view)

        toolbar = Adw.ToolbarView(top_bar_style=Adw.ToolbarStyle.FLAT)
        toolbar.add_top_bar(self._build_header())
        # The split view owns the state; the header button only mirrors it
        self.split_view.bind_property(
            "show-sidebar", self.sidebar_button, "active", GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        toolbar.set_content(self.toast_overlay)

        # Narrow windows: the sidebar becomes an overlay opened from the header
        # Below ~1000sp the table drops the "Modified" column; below 860sp the
        # sidebar also becomes an overlay opened from the header
        compact = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 1000sp"))
        collapsed = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 860sp"))
        collapsed.add_setter(self.split_view, "collapsed", True)
        collapsed.add_setter(self.sidebar_button, "visible", True)
        collapsed.add_setter(self.search_entry, "width-request", 160)
        for breakpoint in (compact, collapsed):
            breakpoint.connect("apply", lambda _bp: self.file_list.set_compact(True))
            breakpoint.connect("unapply", lambda _bp: self.file_list.set_compact(False))
            self.add_breakpoint(breakpoint)
        return toolbar

    def _build_header(self) -> Adw.HeaderBar:
        header = Adw.HeaderBar()
        header.add_css_class("main-header")

        self.sidebar_button = Gtk.ToggleButton(icon_name="sidebar-show-symbolic", visible=False, tooltip_text=_("Show sidebar"))
        header.pack_start(self.sidebar_button)

        icon = Gtk.Image.new_from_icon_name(APP_ICON)
        icon.set_pixel_size(36)
        name = Gtk.Label(label=APP_NAME, xalign=0)
        name.add_css_class("app-name")
        # Active profile under the app name; its menu switches between repositories
        self.profile_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=18)
        self.profile_label.add_css_class("caption")
        profile_content = Gtk.Box(spacing=2)
        profile_content.append(self.profile_label)
        profile_content.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))
        self.profile_menu = Gio.Menu()
        self.profile_button = Gtk.MenuButton(
            child=profile_content, menu_model=self.profile_menu, tooltip_text=_("Switch profile"), halign=Gtk.Align.START
        )
        self.profile_button.add_css_class("flat")
        self.profile_button.add_css_class("profile-button")
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        names.append(name)
        names.append(self.profile_button)
        identity = Gtk.Box(spacing=10)
        identity.add_css_class("app-identity")
        identity.append(icon)
        identity.append(names)
        header.pack_start(identity)

        self.upload_button = Gtk.Button(child=Adw.ButtonContent(icon_name="list-add-symbolic", label=_("Upload ISO")))
        self.upload_button.add_css_class("suggested-action")
        self.upload_button.add_css_class("upload-button")
        self.upload_button.connect("clicked", lambda _button: self.on_upload_clicked())

        self.search_entry = Gtk.SearchEntry(placeholder_text=_("Search files..."), width_request=320)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("stop-search", lambda entry: entry.set_text(""))
        shortcut = Gtk.ShortcutLabel(accelerator="<Control>f", halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        shortcut.add_css_class("search-shortcut")
        shortcut.set_can_target(False)
        search = Gtk.Overlay(child=self.search_entry)
        search.add_overlay(shortcut)
        self.search_entry.connect("notify::text", lambda entry, _p: shortcut.set_visible(not entry.get_text()))

        center = Gtk.Box(spacing=12)
        center.append(self.upload_button)
        center.append(search)
        header.set_title_widget(center)

        main_section = Gio.Menu()
        main_section.append(_("Force Update Index"), "win.force-index")
        main_section.append(_("Refresh"), "win.refresh")
        about_section = Gio.Menu()
        about_section.append(_("About"), "win.about")
        menu = Gio.Menu()
        menu.append_section(None, main_section)
        menu.append_section(None, about_section)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text=_("Application menu")))
        return header

    def _build_sidebar(self) -> Gtk.Widget:
        self.nav_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav_list.add_css_class("navigation-sidebar")
        self.nav_rows = {}
        for page, icon, title in (
            ("files", "folder-symbolic", _("ISO Files")),
            ("transfers", "isovault-transfers-symbolic", _("Transfers")),
            ("settings", "emblem-system-symbolic", _("Settings")),
            ("statistics", "isovault-statistics-symbolic", _("Statistics")),
        ):
            label = Gtk.Label(label=title, xalign=0, hexpand=True)
            box = Gtk.Box(spacing=12)
            box.append(Gtk.Image.new_from_icon_name(icon))
            box.append(label)
            row = Gtk.ListBoxRow(child=box)
            row.page = page
            if page in ("files", "transfers"):
                badge = Gtk.Label(visible=False, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
                badge.add_css_class("nav-badge")
                box.append(badge)
                row.badge = badge
            self.nav_list.append(row)
            self.nav_rows[page] = row
        self.nav_list.select_row(self.nav_rows["files"])
        self.nav_list.connect("row-activated", self._on_nav_activated)

        self.storage_card = StorageCard()

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.add_css_class("app-sidebar")
        sidebar.append(self.nav_list)
        sidebar.append(Gtk.Box(vexpand=True))
        sidebar.append(self.storage_card)
        return sidebar

    def _build_pages(self) -> Gtk.Widget:
        self.page_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.page_stack.add_named(self._build_files_page(), "files")
        self.transfers_page = TransfersPage()
        self.page_stack.add_named(self.transfers_page, "transfers")
        self.statistics_page = StatisticsPage()
        self.page_stack.add_named(self.statistics_page, "statistics")
        self.settings_page = SettingsPage(self.settings_manager, self._on_settings_changed, self.switch_profile)
        self.page_stack.add_named(self.settings_page, "settings")

        setup = Adw.StatusPage(
            icon_name="network-server-symbolic",
            title=_("Connect to your storage"),
            description=_("Please configure S3 credentials in Preferences"),
        )
        open_preferences = Gtk.Button(label=_("Open Preferences"), halign=Gtk.Align.CENTER)
        open_preferences.add_css_class("pill")
        open_preferences.add_css_class("suggested-action")
        open_preferences.connect("clicked", lambda _b: self.activate_action("win.preferences", None))
        setup.set_child(open_preferences)
        self.page_stack.add_named(setup, "setup")

        content = Gtk.Box()
        content.add_css_class("app-content")
        content.append(self.page_stack)
        self.page_stack.set_hexpand(True)
        return content

    def _build_files_page(self) -> Gtk.Widget:
        header = page_header("folder-symbolic", _("ISO Files"), _("Manage your ISO files and make them available for download."))
        self.count_label = header.subtitle_label

        self.view_toggle = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
        self.view_toggle.add(Adw.Toggle(name="list", icon_name="view-list-symbolic", tooltip=_("List view")))
        self.view_toggle.add(Adw.Toggle(name="grid", icon_name="view-grid-symbolic", tooltip=_("Grid view")))
        self.view_toggle.set_active_name("list")
        self.view_toggle.connect("notify::active-name", lambda group, _p: self.file_list.set_view(group.get_active_name()))
        header.append(self.view_toggle)

        self._folders: List[str] = []
        self._folder_model = Gtk.StringList()
        self.folder_dropdown = Gtk.DropDown(model=self._folder_model)
        self.folder_dropdown.set_valign(Gtk.Align.CENTER)
        self.folder_dropdown.set_tooltip_text(_("Filter by folder"))
        self.folder_dropdown.connect("notify::selected", lambda *_args: self._on_folder_changed())
        header.append(self.folder_dropdown)

        self.refresh_spinner = Adw.Spinner(visible=False, valign=Gtk.Align.CENTER)
        header.append(self.refresh_spinner)

        self.file_list = FileBrowser(
            on_selection_changed=lambda _count: self._update_sensitivity(), on_open_folder=self.open_folder
        )

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.add_css_class("app-page")
        page.append(header)
        page.append(self.file_list.widget)
        page.append(self._build_bottom_bar())
        return page

    def _build_bottom_bar(self) -> Gtk.Widget:
        # Selection summary and actions
        self.selection_label = Gtk.Label(xalign=0)
        self.selection_label.add_css_class("heading")
        self.selection_size = Gtk.Label()
        self.selection_size.add_css_class("size-pill")
        summary = Gtk.Box(spacing=10, hexpand=True, valign=Gtk.Align.CENTER)
        summary.append(self.selection_label)
        summary.append(self.selection_size)

        self.copy_link_button = Gtk.Button(child=Adw.ButtonContent(icon_name="insert-link-symbolic", label=_("Copy Link")))
        self.copy_link_button.connect("clicked", lambda _b: self.on_copy_link_clicked())

        download_menu = Gio.Menu()
        download_menu.append(_("Save to Downloads folder"), "win.download-to-downloads")
        self.download_button = Adw.SplitButton(menu_model=download_menu, dropdown_tooltip=_("More download options"))
        self.download_button.set_child(Adw.ButtonContent(icon_name="folder-download-symbolic", label=_("Download")))
        self.download_button.connect("clicked", lambda _b: self.on_download_clicked())

        self.delete_button = Gtk.Button(child=Adw.ButtonContent(icon_name="user-trash-symbolic", label=_("Delete")))
        self.delete_button.add_css_class("destructive-action")
        self.delete_button.connect("clicked", lambda _b: self.on_delete_clicked())

        more_menu = Gio.Menu()
        more_menu.append(_("Select All"), "win.select-all")
        more_menu.append(_("Select None"), "win.select-none")
        more = Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=more_menu, tooltip_text=_("More"))

        selection = Gtk.Box(spacing=8)
        selection.append(summary)
        for widget in (self.copy_link_button, self.download_button, self.delete_button, more):
            selection.append(widget)

        # Running operation
        self.progress_message = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE)
        progress_bar = Gtk.ProgressBar(show_text=True, valign=Gtk.Align.CENTER, width_request=240)
        progress = Gtk.Box(spacing=16)
        progress.append(self.progress_message)
        progress.append(progress_bar)
        self.progress_manager = ProgressManager(progress_bar, self.progress_message, self._update_bottom_bar)

        self.bottom_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.bottom_stack.add_named(selection, "selection")
        self.bottom_stack.add_named(progress, "progress")
        self.bottom_stack.add_css_class("selection-bar")

        self.bottom_revealer = Gtk.Revealer(child=self.bottom_stack, transition_type=Gtk.RevealerTransitionType.SLIDE_UP)
        return self.bottom_revealer

    def _setup_actions(self) -> None:
        for name, handler in (
            ("preferences", self._on_preferences_action),
            ("force-index", lambda *_args: self._publish_index(manual=True)),
            ("refresh", lambda *_args: self.refresh_files()),
            ("about", lambda *_args: self.dialogs.show_about()),
            ("search", lambda *_args: self._focus_search()),
            ("select-all", lambda *_args: self.file_list.select_all()),
            ("select-none", lambda *_args: self.file_list.unselect_all()),
            ("download-to-downloads", lambda *_args: self._download_to_downloads()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        manage = Gio.SimpleAction.new("manage-profiles", None)
        manage.connect("activate", lambda *_args: self.show_page("settings", settings_tab="profile"))
        self.add_action(manage)

        # Radio items of the profile menu: the state is the active profile id
        self.profile_action = Gio.SimpleAction.new_stateful(
            "profile", GLib.VariantType.new("s"), GLib.Variant("s", self.settings_manager.active_profile_id)
        )
        self.profile_action.connect("change-state", lambda _a, value: self.switch_profile(value.get_string()))
        self.add_action(self.profile_action)

        # Row "..." menus: the parameter is the S3 key of the file
        for name, handler in (
            ("file-copy-link", self.on_copy_link_clicked),
            ("file-download", self.on_download_clicked),
            ("file-delete", self.on_delete_clicked),
        ):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", lambda _a, key, h=handler: self._run_on_file(key.get_string(), h))
            self.add_action(action)

    # Navigation

    def _on_nav_activated(self, _listbox, row: Gtk.ListBoxRow) -> None:
        self.show_page(row.page)
        if self.split_view.get_collapsed():
            self.split_view.set_show_sidebar(False)

    def show_page(self, page: str, settings_tab: Optional[str] = None) -> None:
        """
        Show "files", "transfers", "statistics" or "settings" (files falls
        back to the setup page without credentials). settings_tab picks the
        tab of the settings page ("profile" or "general").
        """
        if settings_tab:
            self.settings_page.view_stack.set_visible_child_name(settings_tab)
        if self.page_stack.get_visible_child_name() == "settings" and page != "settings":
            self.settings_page.commit()  # leaving the settings page applies pending edits
        if page == "files" and not self.settings_manager.has_s3_credentials():
            self.page_stack.set_visible_child_name("setup")
        else:
            self.page_stack.set_visible_child_name(page)
        self.nav_list.select_row(self.nav_rows[page])

    def _current_page(self) -> str:
        name = self.page_stack.get_visible_child_name()
        return "files" if name == "setup" else name

    def _focus_search(self) -> None:
        self.show_page("files")
        self.search_entry.grab_focus()

    # State

    def _connect_service(self) -> None:
        """(Re)create the S3 service from the active profile and load the list."""
        self.s3_service = None
        self._apply_profile()
        self._set_files([])

        if not self.settings_manager.has_s3_credentials():
            if self._current_page() == "files":
                self.show_page("files")
            self.show_toast(_("Please configure S3 credentials in Preferences"))
            self._update_sensitivity()
            return

        try:
            self.s3_service = S3Service(
                self.settings_manager.get_s3_config(),
                self.settings_manager.profile["base_url"],
                self.settings_manager.folders(),
            )
        except Exception as e:
            logger.exception("Could not create S3 client")
            self.show_toast(_("Warning: Could not connect to S3 storage") + f": {e}")

        if self._current_page() == "files":
            self.show_page("files")
        self._update_sensitivity()
        self.refresh_files()

    def _set_files(self, files: List[dict]) -> None:
        folders = self.settings_manager.folders()
        self.file_list.set_files(files, folders)
        everything = self.file_list.all_files()
        self.storage_card.update(everything, folders)
        self.statistics_page.update(everything, folders)
        self._update_counts()

    # Profiles

    def switch_profile(self, profile_id: str) -> None:
        """Make another profile active: its settings, folders and bucket."""
        self.settings_page.commit()  # pending edits belong to the profile being left
        if profile_id != self.settings_manager.active_profile_id:
            self.settings_manager.active_profile_id = profile_id
            self.settings_manager.save_settings()
        self.settings_page.load_profile()
        self._connect_service()

    def _apply_profile(self) -> None:
        """Show the active profile: header label, profile menu and folder filter."""
        manager = self.settings_manager
        self.profile_label.set_text(manager.profile["name"])
        self.set_title(f"{APP_NAME} – {manager.profile['name']}")

        self.profile_menu.remove_all()
        profiles = Gio.Menu()
        for profile_id, profile in manager.profiles.items():
            item = Gio.MenuItem.new(profile["name"], None)
            item.set_action_and_target_value("win.profile", GLib.Variant("s", profile_id))
            profiles.append_item(item)
        self.profile_menu.append_section(None, profiles)
        manage = Gio.Menu()
        manage.append(_("Manage Profiles"), "win.manage-profiles")
        self.profile_menu.append_section(None, manage)
        self.profile_action.set_state(GLib.Variant("s", manager.active_profile_id))

        folders = manager.folders()
        if folders != self._folders:
            self._folders = folders
            self._folder_model.splice(0, self._folder_model.get_n_items(), [_("All folders"), *folders])
            self.folder_dropdown.set_selected(0)
        if self.s3_service:
            self.s3_service.folders = tuple(folders)
            self.s3_service.base_url = manager.profile["base_url"].rstrip("/")

    def _update_counts(self) -> None:
        total = self.file_list.total_count
        visible = self.file_list.visible_count
        badge = self.nav_rows["files"].badge
        badge.set_text(str(total))
        badge.set_visible(total > 0)

        # The root holds every folder, so its view counts the whole bucket
        if visible == total or (self.get_selected_folder() == ROOT_FOLDER and not self.search_entry.get_text()):
            self.count_label.set_text(self._files_status_text(total, None))
        else:
            self.count_label.set_text(
                ngettext("{visible} of {total} file", "{visible} of {total} files", total).format(visible=visible, total=total)
            )

    def _update_sensitivity(self) -> None:
        connected = self.s3_service is not None
        selected = self.file_list.get_selected_files()
        count = len(selected)

        self.selection_label.set_text(ngettext("{count} file selected", "{count} files selected", count).format(count=count))
        self.selection_size.set_text(format_file_size(sum(item.size for item in selected)))
        self._update_bottom_bar()

        self.upload_button.set_sensitive(connected and not self._busy)
        self.copy_link_button.set_sensitive(connected and count > 0)
        for widget in (self.download_button, self.delete_button):
            widget.set_sensitive(connected and count > 0 and not self._busy)
        for name in ("force-index", "file-download", "file-delete", "download-to-downloads"):
            self.lookup_action(name).set_enabled(connected and not self._busy)
        self.lookup_action("refresh").set_enabled(connected)
        self.lookup_action("file-copy-link").set_enabled(connected)

    def _update_bottom_bar(self) -> None:
        busy = self.progress_manager.is_visible
        self.bottom_stack.set_visible_child_name("progress" if busy else "selection")
        self.bottom_revealer.set_reveal_child(busy or self.file_list.selected_count > 0)
        active = self.transfers_page.active_count
        badge = self.nav_rows["transfers"].badge
        badge.set_text(str(active))
        badge.set_visible(active > 0)

    def get_selected_folder(self) -> Optional[str]:
        """Folder chosen in the filter (None = all folders)."""
        selected = self.folder_dropdown.get_selected()
        return self._folders[selected - 1] if 0 < selected <= len(self._folders) else None

    def open_folder(self, folder: str) -> None:
        """Show one folder (used by the folder entries of the root view)."""
        if folder in self._folders:
            self.folder_dropdown.set_selected(self._folders.index(folder) + 1)
        else:  # a folder found in the bucket but not listed in the profile
            self.file_list.set_folder(folder)
            self._update_counts()

    def _on_folder_changed(self) -> None:
        self.file_list.set_folder(self.get_selected_folder())
        self._update_counts()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self.file_list.set_search(entry.get_text())
        self._update_counts()

    # Exclusive operations (upload, download, delete, publish)

    def _start_operation(
        self,
        kind: str,
        title: str,
        message: str,
        work: Callable[[], Any],
        on_done: Callable[[Any], None],
        error_message: str,
    ) -> None:
        """
        Run work() in the background as the single running operation.

        Progress is shown in the bottom bar and the operation is logged in the
        transfers page. on_done(result) should call self._finish_transfer()
        with a summary; otherwise the entry is closed quietly as successful.
        """
        if self._busy:
            self.show_toast(_("Another operation is in progress"))
            return

        self._busy = True
        self._current_transfer = self.transfers_page.add(kind, title)
        self._current_transfer.update(message, 0)
        self.progress_manager.show(message)
        self._update_sensitivity()

        def finish():
            self._busy = False
            self.progress_manager.hide()
            self._update_sensitivity()

        def done(result):
            transfer = self._current_transfer
            finish()
            on_done(result)
            if transfer is self._current_transfer and transfer and not transfer.finished:
                self._finish_transfer(message, success=True, toast=False)

        def failed(error):
            finish()
            self._finish_transfer(f"{error_message}: {error}", success=False)

        run_in_thread(work, done, failed)

    def _finish_transfer(self, summary: str, success: bool, toast: bool = True) -> None:
        """Close the current transfer entry and tell the user."""
        if self._current_transfer:
            self._current_transfer.finish(summary, success)
            self._current_transfer = None
        self._update_bottom_bar()
        if toast:
            self.show_toast(summary)

    def _set_progress_message(self, message: str) -> None:
        self.progress_manager.set_message(message)
        if self._current_transfer:
            self._current_transfer.update(message, self.progress_manager.progress_bar.get_fraction() * 100)

    def _set_progress(self, percent: float) -> None:
        self.progress_manager.update(percent)
        if self._current_transfer:
            self._current_transfer.update(self.progress_manager.message_label.get_text(), percent)

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
                call_on_main(self._set_progress, overall)

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
            valid_files,
            invalid_files,
            upload,
            self.settings_manager.get("general", "last_upload_folder"),
            self.settings_manager.folders(),
        )

    def _upload_files(self, file_paths: List[str], folder: str) -> None:
        """Upload files one after another; a failed file doesn't stop the rest."""
        service = self.s3_service
        self._run_batch(
            "upload",
            _("Upload to {folder}").format(folder=folder),
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

    def _run_on_file(self, key: str, handler: Callable[[Optional[List[FileItem]]], None]) -> None:
        """Run a selection action on the single file of a row menu."""
        item = self.file_list.find(key)
        if item:
            handler([item])

    def on_copy_link_clicked(self, items: Optional[List[FileItem]] = None) -> None:
        selected = items or self.file_list.get_selected_files()
        if not selected or not self.s3_service:
            return
        urls = [self.s3_service.get_public_url(item.key) for item in selected]
        self.get_clipboard().set("\n".join(urls))
        if len(urls) == 1:
            self.show_toast(_("Link copied: {url}").format(url=urls[0]))
        else:
            self.show_toast(ngettext("{count} link copied", "{count} links copied", len(urls)).format(count=len(urls)))

    def on_download_clicked(self, items: Optional[List[FileItem]] = None) -> None:
        selected = items or self.file_list.get_selected_files()
        if len(selected) == 1:
            item = selected[0]
            self.dialogs.choose_download_path(item.name, lambda path: self._download_files(selected, [path]))
        elif selected:
            self.dialogs.choose_download_folder(lambda folder: self._download_into(selected, folder))

    def _download_to_downloads(self) -> None:
        """Save the selected files straight into the user's Downloads folder."""
        folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or GLib.get_home_dir()
        selected = self.file_list.get_selected_files()
        if selected:
            self._download_into(selected, folder)

    def _download_into(self, items: List[FileItem], folder: str) -> None:
        self._download_files(items, [os.path.join(folder, item.name) for item in items])

    def _download_files(self, items: List[FileItem], save_paths: List[str]) -> None:
        """Download each item to the matching path. In a folder download, existing files are not overwritten."""
        service = self.s3_service
        overwrite = len(items) == 1  # the save dialog already asked about overwriting

        def step(index, report):
            if not overwrite and os.path.exists(save_paths[index]):
                raise FileExistsError(_("File already exists"))
            service.download_file(items[index].key, save_paths[index], report)

        self._run_batch(
            "download",
            _("Download"),
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

    def on_delete_clicked(self, items: Optional[List[FileItem]] = None) -> None:
        selected = items or self.file_list.get_selected_files()
        if not selected:
            return
        if self.settings_manager.get("ui", "confirm_deletions"):
            self.dialogs.confirm_delete(selected, lambda: self._delete_files(selected))
        else:
            self._delete_files(selected)

    def _delete_files(self, items: List[FileItem]) -> None:
        service = self.s3_service
        self._run_batch(
            "delete",
            _("Delete File") if len(items) == 1 else _("Delete Files"),
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
        kind: str,
        title: str,
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
                call_on_main(self._set_progress_message, progress_message(index))
                try:
                    step(index, self._progress_reporter(index * 100 / total, 100 / total))
                except Exception as e:
                    logger.exception("%s failed", progress_message(index))
                    failures.append((name, str(e)))
            return failures

        def done(failures):
            if not failures:
                summary = text.done_one.format(filename=names[0]) if total == 1 else text.done_all.format(total=total)
            elif total == 1:
                summary = text.failed_one.format(filename=failures[0][0]) + f": {failures[0][1]}"
            else:
                summary = text.summary.format(completed=total - len(failures), failed=len(failures))
            self._finish_transfer(summary, success=not failures)
            if on_finished and len(failures) < total:
                on_finished()

        self._start_operation(kind, title, progress_message(0), work, done, text.failed_one.format(filename=names[0]))

    # Index pages

    def _publish_index(self, manual: bool) -> None:
        """Regenerate the public index pages. Success is only announced when requested manually."""
        service = self.s3_service
        if not service:
            self.show_toast(_("Please configure S3 credentials first"))
            return

        def done(_uploaded):
            # Automatic updates are logged quietly; only a manual one gets a toast
            self._finish_transfer(_("Index files updated!"), success=True, toast=manual)

        self._start_operation(
            "index",
            _("Public index update"),
            _("Updating index files..."),
            lambda: publish_indexes(
                service,
                create_html_generator(
                    self.settings_manager.profile["page_style"],
                    service.get_public_url,
                    folders=self.settings_manager.folders(),
                ),
            ),
            done,
            _("Failed to update index files"),
        )

    # File list

    def refresh_files(self) -> None:
        """Reload every file in the background; folder and search filters are applied locally."""
        service = self.s3_service
        if not service:
            return

        self._refresh_generation += 1
        generation = self._refresh_generation
        include_index = self.settings_manager.get("ui", "show_index_files")
        self.refresh_spinner.set_visible(True)

        def done(files):
            if generation != self._refresh_generation:
                return  # a newer refresh was started meanwhile
            self.refresh_spinner.set_visible(False)
            self._set_files(files)
            self._update_sensitivity()

        def failed(error):
            if generation != self._refresh_generation:
                return
            self.refresh_spinner.set_visible(False)
            self.show_toast(_("Failed to connect to S3 storage. Check credentials and connection.") + f" ({error})")

        run_in_thread(lambda: service.list_files(include_index=include_index), done, failed)

    @staticmethod
    def _files_status_text(count: int, folder: Optional[str]) -> str:
        if folder:
            return ngettext("{count} file in {folder}", "{count} files in {folder}", count).format(count=count, folder=folder)
        return ngettext("{count} file", "{count} files", count).format(count=count)

    # Settings

    def _on_preferences_action(self, *_args) -> None:
        self.show_page("settings")

    def _on_settings_changed(self, s3_changed: bool) -> None:
        if s3_changed:
            self._connect_service()
            return
        self._apply_profile()  # name, folders or public URL may have changed
        self.refresh_files()

    def _on_close_request(self, _window) -> bool:
        self.settings_page.commit()
        width, height = self.get_default_size()
        self.settings_manager.set_window_size(width, height)
        self.settings_manager.save_settings()
        return False  # let the window close

    def show_toast(self, message: str) -> None:
        # Plain text: file names may contain markup characters such as "&"
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=TOAST_TIMEOUT, use_markup=False))
