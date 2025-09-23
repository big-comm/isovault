"""
Preferences dialog for application settings.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw
from typing import Callable, Optional
from models.settings import SettingsManager


class PreferencesDialog(Adw.PreferencesDialog):
    """Preferences dialog for application settings"""
    
    def __init__(self, parent_window, settings_manager: SettingsManager, 
                 on_settings_changed: Optional[Callable] = None):
        """
        Initialize preferences dialog.
        
        Args:
            parent_window: Parent window
            settings_manager: Settings manager instance
            on_settings_changed: Callback when settings change
        """
        super().__init__()
        
        self.set_title("Preferences")
        self.parent_window = parent_window
        self.settings_manager = settings_manager
        self.on_settings_changed = on_settings_changed
        
        # Track changes to avoid multiple callbacks
        self.has_changes = False
        self.updating_ui = False
        
        # Create preference pages
        self._create_s3_page()
        self._create_web_page()
        self._create_general_page()
        self._create_ui_page()
    
    def show_dialog(self):
        """Show the preferences dialog"""
        self.present(self.parent_window)
    
    def _create_s3_page(self) -> None:
        """Create S3 configuration page"""
        page = Adw.PreferencesPage()
        page.set_title("S3 Configuration")
        page.set_name("s3")
        page.set_icon_name("network-server-symbolic")
        self.add(page)
        
        # S3 Credentials Group
        credentials_group = Adw.PreferencesGroup()
        credentials_group.set_title("CDN77 S3 Credentials")
        credentials_group.set_description("Configure your CDN77 S3 storage credentials")
        page.add(credentials_group)
        
        # Access Key
        self.access_key_row = Adw.EntryRow()
        self.access_key_row.set_title("Access Key")
        self.access_key_row.set_text(self.settings_manager.get('s3', 'access_key', ''))
        self.access_key_row.connect("changed", self._on_s3_setting_changed)
        credentials_group.add(self.access_key_row)
        
        # Secret Key
        self.secret_key_row = Adw.PasswordEntryRow()
        self.secret_key_row.set_title("Secret Key")
        self.secret_key_row.set_text(self.settings_manager.get('s3', 'secret_key', ''))
        self.secret_key_row.connect("changed", self._on_s3_setting_changed)
        credentials_group.add(self.secret_key_row)
        
        # S3 Configuration Group
        config_group = Adw.PreferencesGroup()
        config_group.set_title("S3 Configuration")
        config_group.set_description("S3 endpoint and bucket settings")
        page.add(config_group)
        
        # Endpoint URL
        self.endpoint_row = Adw.EntryRow()
        self.endpoint_row.set_title("Endpoint URL")
        self.endpoint_row.set_text(self.settings_manager.get('s3', 'endpoint_url', ''))
        self.endpoint_row.connect("changed", self._on_s3_setting_changed)
        config_group.add(self.endpoint_row)
        
        # Region
        self.region_row = Adw.EntryRow()
        self.region_row.set_title("Region")
        self.region_row.set_text(self.settings_manager.get('s3', 'region_name', ''))
        self.region_row.connect("changed", self._on_s3_setting_changed)
        config_group.add(self.region_row)
        
        # Bucket Name
        self.bucket_row = Adw.EntryRow()
        self.bucket_row.set_title("Bucket Name")
        self.bucket_row.set_text(self.settings_manager.get('s3', 'bucket_name', ''))
        self.bucket_row.connect("changed", self._on_s3_setting_changed)
        config_group.add(self.bucket_row)
        
        # Test Connection Button
        test_button_row = Adw.ActionRow()
        test_button_row.set_title("Test Connection")
        test_button_row.set_subtitle("Verify S3 credentials and connection")
        
        self.test_button = Gtk.Button(label="Test Connection")
        self.test_button.set_valign(Gtk.Align.CENTER)
        self.test_button.add_css_class("suggested-action")
        self.test_button.connect("clicked", self._on_test_connection)
        test_button_row.add_suffix(self.test_button)
        
        config_group.add(test_button_row)
    
    def _create_web_page(self) -> None:
        """Create web configuration page"""
        page = Adw.PreferencesPage()
        page.set_title("Web Configuration")
        page.set_name("web")
        page.set_icon_name("applications-internet-symbolic")
        self.add(page)
        
        # Web Settings Group
        web_group = Adw.PreferencesGroup()
        web_group.set_title("Web Settings")
        web_group.set_description("Configure web URLs for public file access")
        page.add(web_group)
        
        # Base URL
        self.base_url_row = Adw.EntryRow()
        self.base_url_row.set_title("Base URL")
        self.base_url_row.set_text(self.settings_manager.get('web', 'base_url', ''))
        self.base_url_row.connect("changed", self._on_web_setting_changed)
        web_group.add(self.base_url_row)
        
        # Index File
        self.index_file_row = Adw.EntryRow()
        self.index_file_row.set_title("Index File")
        self.index_file_row.set_text(self.settings_manager.get('web', 'index_file', 'index.html'))
        self.index_file_row.connect("changed", self._on_web_setting_changed)
        web_group.add(self.index_file_row)
    
    def _create_general_page(self) -> None:
        """Create general settings page"""
        page = Adw.PreferencesPage()
        page.set_title("General")
        page.set_name("general")
        page.set_icon_name("preferences-system-symbolic")
        self.add(page)
        
        # Application Behavior Group
        behavior_group = Adw.PreferencesGroup()
        behavior_group.set_title("Application Behavior")
        page.add(behavior_group)
        
        # Auto Refresh
        auto_refresh_row = Adw.SwitchRow()
        auto_refresh_row.set_title("Auto Refresh")
        auto_refresh_row.set_subtitle("Automatically refresh file list after operations")
        auto_refresh_row.set_active(self.settings_manager.get('general', 'auto_refresh', True))
        auto_refresh_row.connect("notify::active", lambda row, param: self._on_switch_changed('general', 'auto_refresh', row.get_active()))
        behavior_group.add(auto_refresh_row)
        
        # Window Settings Group
        window_group = Adw.PreferencesGroup()
        window_group.set_title("Window Settings")
        page.add(window_group)
        
        # Window Size
        width, height = self.settings_manager.get_window_size()
        
        width_row = Adw.SpinRow()
        width_row.set_title("Window Width")
        width_adjustment = Gtk.Adjustment(value=width, lower=800, upper=2000, step_increment=50)
        width_row.set_adjustment(width_adjustment)
        width_row.connect("changed", lambda row: self._on_spin_changed('general', 'window_width', int(row.get_value())))
        window_group.add(width_row)
        
        height_row = Adw.SpinRow()
        height_row.set_title("Window Height")
        height_adjustment = Gtk.Adjustment(value=height, lower=600, upper=1500, step_increment=50)
        height_row.set_adjustment(height_adjustment)
        height_row.connect("changed", lambda row: self._on_spin_changed('general', 'window_height', int(row.get_value())))
        window_group.add(height_row)
    
    def _create_ui_page(self) -> None:
        """Create UI settings page"""
        page = Adw.PreferencesPage()
        page.set_title("Interface")
        page.set_name("ui")
        page.set_icon_name("preferences-desktop-theme-symbolic")
        self.add(page)
        
        # Progress and Feedback Group
        feedback_group = Adw.PreferencesGroup()
        feedback_group.set_title("Progress and Feedback")
        page.add(feedback_group)
        
        # Show Progress Details
        progress_details_row = Adw.SwitchRow()
        progress_details_row.set_title("Show Progress Details")
        progress_details_row.set_subtitle("Display detailed progress information during operations")
        progress_details_row.set_active(self.settings_manager.get('ui', 'show_progress_details', True))
        progress_details_row.connect("notify::active", lambda row, param: self._on_switch_changed('ui', 'show_progress_details', row.get_active()))
        feedback_group.add(progress_details_row)
        
        # Safety Group
        safety_group = Adw.PreferencesGroup()
        safety_group.set_title("Safety")
        page.add(safety_group)
        
        # Confirm Deletions
        confirm_deletions_row = Adw.SwitchRow()
        confirm_deletions_row.set_title("Confirm Deletions")
        confirm_deletions_row.set_subtitle("Show confirmation dialog before deleting files")
        confirm_deletions_row.set_active(self.settings_manager.get('ui', 'confirm_deletions', True))
        confirm_deletions_row.connect("notify::active", lambda row, param: self._on_switch_changed('ui', 'confirm_deletions', row.get_active()))
        safety_group.add(confirm_deletions_row)
        
        # Automation Group
        automation_group = Adw.PreferencesGroup()
        automation_group.set_title("Automation")
        page.add(automation_group)
        
        # Auto Update Index
        auto_update_row = Adw.SwitchRow()
        auto_update_row.set_title("Auto Update Index")
        auto_update_row.set_subtitle("Automatically update web index after file operations")
        auto_update_row.set_active(self.settings_manager.get('ui', 'auto_update_index', True))
        auto_update_row.connect("notify::active", lambda row, param: self._on_switch_changed('ui', 'auto_update_index', row.get_active()))
        automation_group.add(auto_update_row)
        
        # Reset Settings Group
        reset_group = Adw.PreferencesGroup()
        reset_group.set_title("Reset")
        page.add(reset_group)
        
        # Reset to Defaults Button
        reset_row = Adw.ActionRow()
        reset_row.set_title("Reset to Defaults")
        reset_row.set_subtitle("Reset all settings to their default values")
        
        reset_button = Gtk.Button(label="Reset")
        reset_button.set_valign(Gtk.Align.CENTER)
        reset_button.add_css_class("destructive-action")
        reset_button.connect("clicked", self._on_reset_settings)
        reset_row.add_suffix(reset_button)
        
        reset_group.add(reset_row)
    
    def _on_s3_setting_changed(self, entry_row) -> None:
        """Handle S3 setting change from entry row"""
        if self.updating_ui:
            return
        self.has_changes = True
        # Save only when user stops typing (with delay)
        from gi.repository import GLib
        # Remove previous timeout if any
        if hasattr(self, '_s3_save_timeout'):
            GLib.source_remove(self._s3_save_timeout)
        # Set new timeout
        self._s3_save_timeout = GLib.timeout_add(1000, self._save_s3_settings_delayed)
    
    def _on_web_setting_changed(self, entry_row) -> None:
        """Handle web setting change from entry row"""
        if self.updating_ui:
            return
        self.has_changes = True
        # Save web settings immediately
        self._save_web_settings()
    
    def _save_s3_settings_delayed(self) -> bool:
        """Save S3 settings with delay"""
        self._save_s3_settings()
        if hasattr(self, '_s3_save_timeout'):
            delattr(self, '_s3_save_timeout')
        return False  # Remove timeout
    
    def _on_switch_changed(self, section: str, key: str, value: bool) -> None:
        """Handle switch setting change"""
        if self.updating_ui:
            return
        self.settings_manager.set(section, key, value)
        self.has_changes = True
        self.settings_manager.save_settings()
        # Only notify for non-S3 changes to avoid reconnection spam
        if section != 's3' and self.on_settings_changed:
            self.on_settings_changed()
    
    def _on_spin_changed(self, section: str, key: str, value: int) -> None:
        """Handle spin button setting change"""
        if self.updating_ui:
            return
        self.settings_manager.set(section, key, value)
        self.has_changes = True
        self.settings_manager.save_settings()
        # Window size changes don't need service updates
    
    def _on_test_connection(self, button) -> None:
        """Test S3 connection with current settings"""
        # Save current S3 settings first
        self._save_s3_settings()
        
        # Update button state
        button.set_sensitive(False)
        button.set_label("Testing...")
        
        # Show modal dialog for test result
        self._show_connection_test_dialog(button)
    
    def _show_connection_test_dialog(self, button) -> None:
        """Show modal dialog for connection test"""
        import threading
        from services import S3Service
        
        def test_thread():
            try:
                # Create temporary S3 service with current settings
                s3_config = self.settings_manager.get_s3_config()
                temp_s3_service = S3Service(s3_config)
                
                # Test connection
                success = temp_s3_service.test_connection()
                message = "Connection successful!" if success else "Connection failed. Check your credentials."
                
                from gi.repository import GLib
                GLib.idle_add(self._show_test_result_dialog, success, message, button)
                
            except Exception as e:
                from gi.repository import GLib
                GLib.idle_add(self._show_test_result_dialog, False, f"Connection error: {str(e)}", button)
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def _show_test_result_dialog(self, success: bool, message: str, button: Gtk.Button) -> bool:
        """Show test result in modal dialog"""
        # Restore button state
        button.set_sensitive(True)
        button.set_label("Test Connection")
        
        # Create modal dialog
        dialog = Adw.AlertDialog(
            heading="Connection Test Result",
            body=message
        )
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        
        # Set appearance based on result
        if success:
            # dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
            pass
        else:
            dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        
        dialog.present(self)
        
        return False  # Remove from GLib idle
    
    def _on_reset_settings(self, button) -> None:
        """Show reset confirmation dialog"""
        dialog = Adw.AlertDialog(
            heading="Reset Settings",
            body="Are you sure you want to reset all settings to their default values?\n\nThis action cannot be undone."
        )
        
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        
        dialog.connect("response", self._on_reset_confirmed)
        dialog.present(self)
    
    def _on_reset_confirmed(self, dialog, response) -> None:
        """Handle reset confirmation"""
        if response == "reset":
            self.updating_ui = True
            # Reset settings to defaults
            self.settings_manager.settings = self.settings_manager._load_default_settings()
            self._refresh_ui()
            self.has_changes = True
            # Save the reset settings
            self.settings_manager.save_settings()
            self.updating_ui = False
            if self.on_settings_changed:
                self.on_settings_changed()
    
    def _save_s3_settings(self) -> None:
        """Save S3 settings from UI to settings manager"""
        self.settings_manager.set('s3', 'access_key', self.access_key_row.get_text())
        self.settings_manager.set('s3', 'secret_key', self.secret_key_row.get_text())
        self.settings_manager.set('s3', 'endpoint_url', self.endpoint_row.get_text())
        self.settings_manager.set('s3', 'region_name', self.region_row.get_text())
        self.settings_manager.set('s3', 'bucket_name', self.bucket_row.get_text())
        
        # Save to file
        self.settings_manager.save_settings()
        
        # Notify about S3 changes only once
        if self.on_settings_changed:
            self.on_settings_changed()
    
    def _save_web_settings(self) -> None:
        """Save web settings from UI to settings manager"""
        self.settings_manager.set('web', 'base_url', self.base_url_row.get_text())
        self.settings_manager.set('web', 'index_file', self.index_file_row.get_text())
        
        # Save to file
        self.settings_manager.save_settings()
    
    def _refresh_ui(self) -> None:
        """Refresh UI with current settings"""
        # Refresh S3 settings
        self.access_key_row.set_text(self.settings_manager.get('s3', 'access_key', ''))
        self.secret_key_row.set_text(self.settings_manager.get('s3', 'secret_key', ''))
        self.endpoint_row.set_text(self.settings_manager.get('s3', 'endpoint_url', ''))
        self.region_row.set_text(self.settings_manager.get('s3', 'region_name', ''))
        self.bucket_row.set_text(self.settings_manager.get('s3', 'bucket_name', ''))
        
        # Refresh web settings
        self.base_url_row.set_text(self.settings_manager.get('web', 'base_url', ''))
        self.index_file_row.set_text(self.settings_manager.get('web', 'index_file', 'index.html'))