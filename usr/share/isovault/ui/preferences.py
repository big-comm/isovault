"""
Preferences dialog.

Text fields are applied when the dialog closes (not on every keystroke);
switches apply immediately. The quick toggles (auto refresh, confirm
deletions, auto update index) live only in the main window sidebar.
"""

import threading
from typing import Callable, Dict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from models.settings import SettingsManager  # noqa: E402
from services import S3Service  # noqa: E402
from utils.i18n import _  # noqa: E402

# Callback argument: True when the S3 connection settings changed
SettingsChangedCallback = Callable[[bool], None]


class PreferencesDialog(Adw.PreferencesDialog):
    """Preferences dialog for application settings"""

    def __init__(self, settings_manager: SettingsManager, on_settings_changed: SettingsChangedCallback):
        super().__init__(title=_("Preferences"))
        self.settings_manager = settings_manager
        self.on_settings_changed = on_settings_changed
        self._updating_ui = False

        # setting key -> entry row, per section
        self.s3_rows: Dict[str, Adw.EntryRow] = {}
        self.web_rows: Dict[str, Adw.EntryRow] = {}

        self.add(self._create_s3_page())
        self.add(self._create_general_page())
        self.connect("closed", self._on_closed)

    def _create_s3_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(name="s3", title=_("S3 Config"), icon_name="network-server-symbolic")

        credentials = Adw.PreferencesGroup(
            title=_("CDN77 S3 Credentials"),
            description=_("Configure your CDN77 S3 storage credentials"),
        )
        self.s3_rows["access_key"] = Adw.EntryRow(title=_("Access Key"))
        self.s3_rows["secret_key"] = Adw.PasswordEntryRow(title=_("Secret Key"))
        credentials.add(self.s3_rows["access_key"])
        credentials.add(self.s3_rows["secret_key"])
        page.add(credentials)

        connection = Adw.PreferencesGroup(
            title=_("S3 Configuration"),
            description=_("S3 endpoint and bucket settings"),
        )
        for key, title in (
            ("endpoint_url", _("Endpoint URL")),
            ("region_name", _("Region")),
            ("bucket_name", _("Bucket Name")),
        ):
            self.s3_rows[key] = Adw.EntryRow(title=title)
            connection.add(self.s3_rows[key])

        self.test_button = Gtk.Button(label=_("Test Connection"), valign=Gtk.Align.CENTER)
        self.test_button.add_css_class("suggested-action")
        self.test_button.connect("clicked", self._on_test_connection)
        test_row = Adw.ActionRow(
            title=_("Test Connection"),
            subtitle=_("Verify S3 credentials and connection"),
        )
        test_row.add_suffix(self.test_button)
        connection.add(test_row)
        page.add(connection)

        for key, row in self.s3_rows.items():
            row.set_text(self.settings_manager.get("s3", key))
        return page

    def _create_general_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(name="general", title=_("General"), icon_name="preferences-system-symbolic")

        web = Adw.PreferencesGroup(
            title=_("Web Settings"),
            description=_("Configure web URLs for public file access"),
        )
        self.web_rows["base_url"] = Adw.EntryRow(title=_("Base URL"))
        self.web_rows["base_url"].set_text(self.settings_manager.get("web", "base_url"))
        web.add(self.web_rows["base_url"])

        self.show_index_row = Adw.SwitchRow(
            title=_("Show Index Files"),
            subtitle=_("Display index.html files in the file list"),
            active=self.settings_manager.get("web", "show_index_files"),
        )
        self.show_index_row.connect("notify::active", self._on_show_index_toggled)
        web.add(self.show_index_row)
        page.add(web)

        reset = Adw.PreferencesGroup(title=_("Reset"))
        reset_button = Gtk.Button(label=_("Reset"), valign=Gtk.Align.CENTER)
        reset_button.add_css_class("destructive-action")
        reset_button.connect("clicked", self._on_reset_clicked)
        reset_row = Adw.ActionRow(
            title=_("Reset to Defaults"),
            subtitle=_("Reset all settings to their default values (S3 credentials are kept)"),
        )
        reset_row.add_suffix(reset_button)
        reset.add(reset_row)
        page.add(reset)

        return page

    # Applying changes

    def _on_closed(self, _dialog) -> None:
        """Commit edited text fields."""
        s3_changed = self._commit_rows("s3", self.s3_rows)
        web_changed = self._commit_rows("web", self.web_rows)
        if s3_changed or web_changed:
            self.settings_manager.save_settings()
            self.on_settings_changed(s3_changed)

    def _commit_rows(self, section: str, rows: Dict[str, Adw.EntryRow]) -> bool:
        changed = False
        for key, row in rows.items():
            value = row.get_text().strip()
            if value != self.settings_manager.get(section, key):
                self.settings_manager.set(section, key, value)
                changed = True
        return changed

    def _on_show_index_toggled(self, row, _pspec) -> None:
        if self._updating_ui:
            return
        self.settings_manager.set("web", "show_index_files", row.get_active())
        self.settings_manager.save_settings()
        self.on_settings_changed(False)

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
        for key, row in self.s3_rows.items():
            row.set_text(self.settings_manager.get("s3", key))
        self.web_rows["base_url"].set_text(self.settings_manager.get("web", "base_url"))
        self.show_index_row.set_active(self.settings_manager.get("web", "show_index_files"))
        self._updating_ui = False

        self.on_settings_changed(True)

    # Connection test

    def _on_test_connection(self, button: Gtk.Button) -> None:
        """Test the values currently typed, without saving them."""
        s3_config = {key: row.get_text().strip() for key, row in self.s3_rows.items()}
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
