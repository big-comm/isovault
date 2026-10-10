"""
Settings page shown inside the main window.

"Profile" edits the active profile (repository); "General" holds the
application preferences shared by every profile. Text fields are applied
with Enter (or their apply button), when the user leaves the page and when
the window closes; switches and choices apply immediately.
"""

import threading
from typing import Callable, Dict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from config import PAGE_STYLES  # noqa: E402
from models.settings import CONNECTION_KEYS, SettingsManager, parse_folders  # noqa: E402
from services import S3Service  # noqa: E402
from utils.i18n import _  # noqa: E402

from .pages import page_header  # noqa: E402

# Callback argument: True when the S3 connection of the active profile changed
SettingsChangedCallback = Callable[[bool], None]
# Callback argument: id of the profile that should become active
ProfileSelectedCallback = Callable[[str], None]


class SettingsPage(Gtk.Box):
    """Profile (repository) and application settings"""

    def __init__(
        self,
        settings_manager: SettingsManager,
        on_settings_changed: SettingsChangedCallback,
        on_profile_selected: ProfileSelectedCallback,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("app-page")
        self.add_css_class("settings-page")
        self.settings_manager = settings_manager
        self.on_settings_changed = on_settings_changed
        self.on_profile_selected = on_profile_selected
        self._updating_ui = False

        # profile key -> entry row of the active profile
        self.profile_rows: Dict[str, Adw.EntryRow] = {}

        self.view_stack = Adw.ViewStack(vexpand=True)
        self.view_stack.add_titled_with_icon(self._create_profile_page(), "profile", _("Profile"), "network-server-symbolic")
        self.view_stack.add_titled_with_icon(
            self._create_general_page(), "general", _("General"), "preferences-system-symbolic"
        )

        header = page_header(
            "emblem-system-symbolic",
            _("Settings"),
            _("Storage connection, public download page and application behavior."),
        )
        switcher = Adw.InlineViewSwitcher(stack=self.view_stack, valign=Gtk.Align.CENTER, can_shrink=False)
        header.append(switcher)

        self.append(header)
        self.append(self.view_stack)
        self.load_profile()

    # Construction

    def _entry_row(self, key: str, title: str, password: bool = False) -> Adw.EntryRow:
        row = (Adw.PasswordEntryRow if password else Adw.EntryRow)(title=title, show_apply_button=True)
        row.connect("apply", lambda _row: self.commit())
        self.profile_rows[key] = row
        return row

    def _create_profile_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()

        repository = Adw.PreferencesGroup(
            title=_("Profile"),
            description=_("Each profile is one repository: its storage, public download page and folders."),
        )
        repository.add(self._entry_row("name", _("Profile Name")))
        self._page_styles = list(PAGE_STYLES)
        self.page_style_row = Adw.ComboRow(
            title=_("Download Page Style"),
            subtitle=_("Look of the index.html pages published to the bucket"),
            model=Gtk.StringList.new([_("BigCommunity (cards)"), _("BigLinux (file list)")]),
        )
        self.page_style_row.connect("notify::selected", self._on_page_style_changed)
        repository.add(self.page_style_row)
        repository.add(self._entry_row("base_url", _("Base URL")))
        repository.add(self._entry_row("folders", _("Folders (comma separated, Root = bucket root)")))
        page.add(repository)

        credentials = Adw.PreferencesGroup(
            title=_("CDN77 S3 Credentials"),
            description=_("Configure your CDN77 S3 storage credentials"),
        )
        credentials.add(self._entry_row("access_key", _("Access Key")))
        credentials.add(self._entry_row("secret_key", _("Secret Key"), password=True))
        page.add(credentials)

        connection = Adw.PreferencesGroup(
            title=_("S3 Configuration"),
            description=_("S3 endpoint and bucket settings"),
        )
        connection.add(self._entry_row("endpoint_url", _("Endpoint URL")))
        connection.add(self._entry_row("region_name", _("Region")))
        connection.add(self._entry_row("bucket_name", _("Bucket Name")))

        self.test_button = Gtk.Button(label=_("Test Connection"), valign=Gtk.Align.CENTER)
        self.test_button.add_css_class("suggested-action")
        self.test_button.connect("clicked", self._on_test_connection)
        test_row = Adw.ActionRow(title=_("Test Connection"), subtitle=_("Verify S3 credentials and connection"))
        test_row.add_suffix(self.test_button)
        connection.add(test_row)
        page.add(connection)

        profiles = Adw.PreferencesGroup(title=_("Profiles"))
        new_button = Gtk.Button(label=_("New Profile"), valign=Gtk.Align.CENTER)
        new_button.connect("clicked", self._on_new_profile_clicked)
        new_row = Adw.ActionRow(title=_("New Profile"), subtitle=_("Add another repository"))
        new_row.add_suffix(new_button)
        profiles.add(new_row)

        self.delete_button = Gtk.Button(label=_("Delete"), valign=Gtk.Align.CENTER)
        self.delete_button.add_css_class("destructive-action")
        self.delete_button.connect("clicked", self._on_delete_profile_clicked)
        delete_row = Adw.ActionRow(
            title=_("Delete This Profile"), subtitle=_("Removes the profile and its saved credentials")
        )
        delete_row.add_suffix(self.delete_button)
        profiles.add(delete_row)
        page.add(profiles)
        return page

    def _create_general_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()

        behavior = Adw.PreferencesGroup(title=_("Application Behavior"))
        self.behavior_rows = {}
        for section, key, title, subtitle in (
            ("general", "auto_refresh", _("Auto Refresh"), _("Automatically refresh file list after operations")),
            ("ui", "confirm_deletions", _("Confirm Deletions"), _("Show confirmation dialog before deleting files")),
            ("ui", "auto_update_index", _("Auto Update Index"), _("Automatically update web index after file operations")),
            ("ui", "show_index_files", _("Show Index Files"), _("Display index.html files in the file list")),
        ):
            row = Adw.SwitchRow(title=title, subtitle=subtitle, active=self.settings_manager.get(section, key))
            row.connect("notify::active", self._on_behavior_toggled, section, key)
            behavior.add(row)
            self.behavior_rows[(section, key)] = row
        page.add(behavior)

        reset = Adw.PreferencesGroup(title=_("Reset"))
        reset_button = Gtk.Button(label=_("Reset"), valign=Gtk.Align.CENTER)
        reset_button.add_css_class("destructive-action")
        reset_button.connect("clicked", self._on_reset_clicked)
        reset_row = Adw.ActionRow(
            title=_("Reset to Defaults"),
            subtitle=_("Reset the application preferences to their default values (profiles are kept)"),
        )
        reset_row.add_suffix(reset_button)
        reset.add(reset_row)
        page.add(reset)
        return page

    # Active profile

    def load_profile(self) -> None:
        """Show the values of the active profile."""
        profile = self.settings_manager.profile
        self._updating_ui = True
        for key, row in self.profile_rows.items():
            row.set_text(", ".join(parse_folders(profile[key])) if key == "folders" else profile[key])
        style = profile["page_style"]
        self.page_style_row.set_selected(self._page_styles.index(style) if style in self._page_styles else 0)
        self._updating_ui = False
        self.delete_button.set_sensitive(len(self.settings_manager.profiles) > 1)

    def commit(self) -> None:
        """Save edited text fields into the active profile and notify the window."""
        profile = self.settings_manager.profile
        changed = set()
        for key, row in self.profile_rows.items():
            value = row.get_text().strip()
            current = profile[key]
            if key == "folders":
                value, current = ",".join(parse_folders(value)), ",".join(parse_folders(current))
            elif key == "name" and not value:
                value = current  # a profile always has a name
            if value != current:
                self.settings_manager.set_profile_value(key, value)
                changed.add(key)
        if changed:
            self.settings_manager.save_settings()
            self.on_settings_changed(bool(changed & set(CONNECTION_KEYS)))

    def _on_page_style_changed(self, row: Adw.ComboRow, _pspec) -> None:
        if self._updating_ui:
            return
        self.settings_manager.set_profile_value("page_style", self._page_styles[row.get_selected()])
        self.settings_manager.save_settings()

    # Creating and deleting profiles

    def _on_new_profile_clicked(self, _button) -> None:
        entry = Gtk.Entry(placeholder_text=_("Profile Name"), activates_default=True)
        dialog = Adw.AlertDialog(heading=_("New Profile"), body=_("Name of the repository, e.g. BigLinux"))
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("create", _("Create"))
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("create")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            name = entry.get_text().strip()
            if response == "create" and name:
                self.create_profile(name)

        dialog.connect("response", on_response)
        dialog.present(self)

    def create_profile(self, name: str) -> str:
        """Add a profile and make it active; returns its id."""
        profile_id = self.settings_manager.add_profile(name)
        self.settings_manager.save_settings()
        self.on_profile_selected(profile_id)
        return profile_id

    def _on_delete_profile_clicked(self, _button) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Delete Profile"),
            body=_("Delete the profile “{name}” and its saved credentials?\n\nThe files in the bucket are not touched.").format(
                name=self.settings_manager.profile["name"]
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, response: response == "delete" and self.delete_active_profile())
        dialog.present(self)

    def delete_active_profile(self) -> None:
        self.settings_manager.remove_profile(self.settings_manager.active_profile_id)
        self.settings_manager.save_settings()
        self.load_profile()  # the fields must show the new active profile before it is selected
        self.on_profile_selected(self.settings_manager.active_profile_id)

    # Application preferences

    def _on_behavior_toggled(self, row: Adw.SwitchRow, _pspec, section: str, key: str) -> None:
        if self._updating_ui:
            return
        self.settings_manager.set(section, key, row.get_active())
        self.settings_manager.save_settings()
        if key == "show_index_files":
            self.on_settings_changed(False)  # the file list must be reloaded

    def _on_reset_clicked(self, _button) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Reset Settings"),
            body=_("Are you sure you want to reset all settings to their default values?\n\nThis action cannot be undone."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("reset", _("Reset"))
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_reset_response)
        dialog.present(self)

    def _on_reset_response(self, _dialog, response: str) -> None:
        if response != "reset":
            return
        self.settings_manager.reset_to_defaults()
        self.settings_manager.save_settings()

        self._updating_ui = True
        for (section, key), row in self.behavior_rows.items():
            row.set_active(self.settings_manager.get(section, key))
        self._updating_ui = False

        self.on_settings_changed(False)

    # Connection test

    def _on_test_connection(self, button: Gtk.Button) -> None:
        """Test the values currently typed, without saving them."""
        s3_config = {key: self.profile_rows[key].get_text().strip() for key in CONNECTION_KEYS}
        button.set_sensitive(False)
        button.set_label(_("Testing..."))

        def test():
            try:
                S3Service(s3_config).check_connection()
                result = (True, _("Connection successful!"))
            except Exception as e:
                result = (False, _("Connection error: {error}").format(error=e))
            GLib.idle_add(self._show_test_result, *result)

        threading.Thread(target=test, daemon=True).start()

    def _show_test_result(self, success: bool, message: str) -> bool:
        self.test_button.set_sensitive(True)
        self.test_button.set_label(_("Test Connection"))

        dialog = Adw.AlertDialog(heading=_("Connection Test Result"), body=message)
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        if not success:
            dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.present(self)
        return False
