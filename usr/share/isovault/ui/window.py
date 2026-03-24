"""
Main application window.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, GLib
import threading
from typing import Optional, List
from pathlib import Path

from config import APP_CONFIG, DISTRO_FOLDERS, UI_CONSTANTS
from models import SettingsManager, FileItem
from services import S3Service, HTMLGenerator, FileValidator
from .components import ProgressManager, ToastManager, FileListComponent
from .dialogs import DialogManager, ValidationDialogMixin
from .preferences import PreferencesDialog
from utils.i18n import _


class ISOVaultWindow(Adw.ApplicationWindow):
    """Main application window"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Initialize managers and services
        self.settings_manager = SettingsManager()
        self.s3_service = None
        self.html_generator = None
        self.dialog_manager = DialogManager(self)
        
        # UI components
        self.progress_manager = None
        self.toast_manager = None
        self.file_list_component = None

        # Sidebar widgets
        self.folder_dropdown = None
        self.copy_link_btn = None
        self.download_btn = None
        self.delete_btn = None
        
        # State
        self.current_batch = None
        
        # Setup application
        self._setup_window()
        self._setup_ui()
        self._setup_services()
        self._setup_actions()
        
        # Initial load
        self._load_initial_data()
    
    def _setup_window(self) -> None:
        """Setup window properties"""
        self.set_title(_(APP_CONFIG['window_title']))
        
        # Load window size from settings
        width, height = self.settings_manager.get_window_size()
        self.set_default_size(width, height)
        
        # Connect window size tracking
        self.connect("notify::default-width", self._on_window_size_changed)
        self.connect("notify::default-height", self._on_window_size_changed)
    
    def _setup_ui(self) -> None:
        """Setup the main UI with Adwaita OverlaySplitView"""
        # Main toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        self.toast_manager = ToastManager(self.toast_overlay)

        # Split view
        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_min_sidebar_width(260)
        self.split_view.set_max_sidebar_width(320)
        self.split_view.set_sidebar_width_fraction(0.32)
        self.toast_overlay.set_child(self.split_view)

        # Build sidebar and content panes
        self.split_view.set_sidebar(self._build_sidebar())
        self.split_view.set_content(self._build_content())

    def _build_sidebar(self) -> Adw.ToolbarView:
        """Build the sidebar pane with options"""
        toolbar = Adw.ToolbarView()

        # Sidebar header bar
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)

        # Centered title
        title = Gtk.Label(label=APP_CONFIG["app_name"])
        title.add_css_class("heading")
        header.set_title_widget(title)

        toolbar.add_top_bar(header)

        # Scrollable content
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(6)
        box.set_margin_bottom(12)

        # --- Folder filter group ---
        filter_group = Adw.PreferencesGroup()

        self.folder_dropdown = Adw.ComboRow(title=_("Filter by folder"))
        folder_list = [_("All folders")] + list(DISTRO_FOLDERS)
        self.folder_dropdown.set_model(Gtk.StringList.new(folder_list))
        self.folder_dropdown.connect("notify::selected", self._on_folder_filter_changed)
        filter_group.add(self.folder_dropdown)

        box.append(filter_group)

        # --- File actions group ---
        actions_group = Adw.PreferencesGroup()

        # Copy Link
        copy_row = Adw.ActionRow(title=_("Copy Link"))
        copy_row.set_subtitle(_("Copy public URL"))
        copy_icon = Gtk.Image.new_from_icon_name("edit-copy-symbolic")
        copy_row.add_prefix(copy_icon)
        self.copy_link_btn = Gtk.Button(icon_name="go-next-symbolic")
        self.copy_link_btn.set_valign(Gtk.Align.CENTER)
        self.copy_link_btn.set_sensitive(False)
        self.copy_link_btn.connect("clicked", lambda b: self.on_copy_link_clicked())
        copy_row.add_suffix(self.copy_link_btn)
        copy_row.set_activatable_widget(self.copy_link_btn)
        actions_group.add(copy_row)

        # Download
        download_row = Adw.ActionRow(title=_("Download"))
        download_row.set_subtitle(_("Save file locally"))
        dl_icon = Gtk.Image.new_from_icon_name("folder-download-symbolic")
        download_row.add_prefix(dl_icon)
        self.download_btn = Gtk.Button(icon_name="go-next-symbolic")
        self.download_btn.set_valign(Gtk.Align.CENTER)
        self.download_btn.set_sensitive(False)
        self.download_btn.connect("clicked", lambda b: self.on_download_clicked())
        download_row.add_suffix(self.download_btn)
        download_row.set_activatable_widget(self.download_btn)
        actions_group.add(download_row)

        # Delete
        delete_row = Adw.ActionRow(title=_("Delete"))
        delete_row.set_subtitle(_("Remove from storage"))
        del_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic")
        delete_row.add_prefix(del_icon)
        self.delete_btn = Gtk.Button(icon_name="go-next-symbolic")
        self.delete_btn.set_valign(Gtk.Align.CENTER)
        self.delete_btn.add_css_class("destructive-action")
        self.delete_btn.set_sensitive(False)
        self.delete_btn.connect("clicked", lambda b: self.on_delete_clicked())
        delete_row.add_suffix(self.delete_btn)
        delete_row.set_activatable_widget(self.delete_btn)
        actions_group.add(delete_row)

        box.append(actions_group)

        # --- Quick settings group ---
        settings_group = Adw.PreferencesGroup()

        # Auto Refresh
        auto_refresh_row = Adw.SwitchRow(title=_("Auto Refresh"))
        auto_refresh_row.set_active(
            self.settings_manager.get("general", "auto_refresh", True)
        )
        auto_refresh_row.connect(
            "notify::active",
            lambda row, p: self._on_quick_setting_changed(
                "general", "auto_refresh", row.get_active()
            ),
        )
        settings_group.add(auto_refresh_row)

        # Confirm Deletions
        confirm_row = Adw.SwitchRow(title=_("Confirm Deletions"))
        confirm_row.set_active(
            self.settings_manager.get("ui", "confirm_deletions", True)
        )
        confirm_row.connect(
            "notify::active",
            lambda row, p: self._on_quick_setting_changed(
                "ui", "confirm_deletions", row.get_active()
            ),
        )
        settings_group.add(confirm_row)

        # Auto Update Index
        auto_index_row = Adw.SwitchRow(title=_("Auto Update Index"))
        auto_index_row.set_active(
            self.settings_manager.get("ui", "auto_update_index", True)
        )
        auto_index_row.connect(
            "notify::active",
            lambda row, p: self._on_quick_setting_changed(
                "ui", "auto_update_index", row.get_active()
            ),
        )
        settings_group.add(auto_index_row)

        box.append(settings_group)

        scroll.set_child(box)
        toolbar.set_content(scroll)

        return toolbar

    def _build_content(self) -> Adw.ToolbarView:
        """Build the content pane with file list"""
        toolbar = Adw.ToolbarView()

        # Content header bar
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)

        # Main action button centered
        upload_btn = Gtk.Button(label=_("Upload ISO"))
        upload_btn.add_css_class("suggested-action")
        upload_btn.connect("clicked", lambda b: self.on_upload_clicked())
        header.set_title_widget(upload_btn)

        # Menu button on the right
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_tooltip_text(_("Application menu"))

        menu_model = Gio.Menu()

        main_section = Gio.Menu()
        main_section.append(_("Preferences"), "app.preferences")
        main_section.append(_("Force Update Index"), "app.force_index")
        main_section.append(_("Refresh"), "app.refresh")
        menu_model.append_section(None, main_section)

        about_section = Gio.Menu()
        about_section.append(_("About"), "app.about")
        menu_model.append_section(None, about_section)

        menu_btn.set_menu_model(menu_model)
        header.pack_end(menu_btn)

        toolbar.add_top_bar(header)

        # File list as main content
        self.file_list_component = FileListComponent(self)
        file_list_scrolled = self.file_list_component.setup_file_list()
        toolbar.set_content(file_list_scrolled)

        # Status bar at bottom
        status_bar = self._build_status_bar()
        toolbar.add_bottom_bar(status_bar)

        return toolbar

    def _build_status_bar(self) -> Gtk.Box:
        """Build the status bar for the content bottom"""
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status_box.set_margin_top(6)
        status_box.set_margin_bottom(6)
        status_box.set_margin_start(12)
        status_box.set_margin_end(12)

        self.status_label = Gtk.Label(label=_("Ready"))
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_hexpand(True)
        status_box.append(self.status_label)
        
        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(300, -1)
        self.progress_bar.set_visible(False)
        self.progress_bar.set_show_text(True)
        status_box.append(self.progress_bar)
        
        # Initialize progress manager
        self.progress_manager = ProgressManager(self.progress_bar, self.status_label)

        return status_box

    def _on_folder_filter_changed(self, combo_row, pspec) -> None:
        """Handle folder filter change from sidebar ComboRow"""
        self.refresh_files()

    def _on_quick_setting_changed(self, section: str, key: str, value: bool) -> None:
        """Handle quick setting toggle in sidebar"""
        self.settings_manager.set(section, key, value)
        self.settings_manager.save_settings()

    def get_selected_folder(self) -> Optional[str]:
        """Get currently selected folder from sidebar dropdown"""
        selected = self.folder_dropdown.get_selected()
        if selected == 0:  # "All folders"
            return None
        return DISTRO_FOLDERS[selected - 1]

    def _setup_services(self) -> None:
        """Setup S3 service and related services"""
        s3_config = self.settings_manager.get_s3_config()
        web_config = self.settings_manager.get_web_config()

        if self.settings_manager.has_s3_credentials():
            self.s3_service = S3Service(s3_config, web_config)
            self.html_generator = HTMLGenerator(self.s3_service)

            # Test connection and create folders in background
            self._test_connection_and_setup()
        else:
            print("No S3 credentials configured")
            self.show_toast(_("Please configure S3 credentials in Preferences"))

    def _setup_actions(self) -> None:
        """Setup application actions"""
        # Create action group
        action_group = Gio.SimpleActionGroup()
        self.insert_action_group("app", action_group)

        # Preferences action
        preferences_action = Gio.SimpleAction.new("preferences", None)
        preferences_action.connect("activate", self._on_preferences_action)
        action_group.add_action(preferences_action)

        # Force index update action
        force_index_action = Gio.SimpleAction.new("force_index", None)
        force_index_action.connect("activate", self._on_force_index_action)
        action_group.add_action(force_index_action)

        # Refresh action
        refresh_action = Gio.SimpleAction.new("refresh", None)
        refresh_action.connect("activate", self._on_refresh_action)
        action_group.add_action(refresh_action)

        # About action
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about_action)
        action_group.add_action(about_action)

    def _load_initial_data(self) -> None:
        """Load initial data"""
        if self.s3_service:
            self.refresh_files()

    def _test_connection_and_setup(self) -> None:
        """Test S3 connection and setup folders in background"""
        if not self.s3_service:
            return

        def connection_thread():
            connected = self.s3_service.test_connection()
            if connected:
                self.s3_service.create_folders()
                GLib.idle_add(self._on_connection_success)
            else:
                GLib.idle_add(self._on_connection_failed)

        self._run_in_thread(connection_thread, _("Connection test failed"))
    
    def _on_connection_success(self) -> bool:
        """Handle successful S3 connection"""
        print("S3 connection successful")
        return False  # Remove from GLib idle
    
    def _on_connection_failed(self) -> bool:
        """Handle failed S3 connection"""
        self.show_toast(_("Warning: Could not connect to S3 storage"))
        return False  # Remove from GLib idle
    
    # UI Event Handlers
    def on_file_selection_changed(self, has_selection: bool) -> None:
        """Handle file selection changes"""
        self.copy_link_btn.set_sensitive(has_selection)
        self.download_btn.set_sensitive(has_selection)
        self.delete_btn.set_sensitive(has_selection)
    
    def on_upload_clicked(self) -> None:
        """Handle upload button click"""
        if not self.s3_service:
            self.show_toast(_("Please configure S3 credentials first"))
            return
        
        last_dir = self.settings_manager.get('general', 'last_directory')
        self.dialog_manager.show_upload_dialog(self._on_files_selected, last_dir)
    
    def on_copy_link_clicked(self) -> None:
        """Handle copy link button click"""
        selected_file = self.file_list_component.get_selected_file()
        if not selected_file or not self.s3_service:
            return
        
        # Generate public URL
        public_url = self.s3_service.get_public_url(selected_file.key)
        
        # Copy to clipboard
        clipboard = self.get_clipboard()
        clipboard.set(public_url)
        
        # Show confirmation
        self.show_toast(_("Link copied: {url}").format(url=public_url))
    
    def on_download_clicked(self) -> None:
        """Handle download button click"""
        selected_file = self.file_list_component.get_selected_file()
        if not selected_file:
            return
        
        self.dialog_manager.show_download_dialog(
            selected_file.name, 
            lambda path: self._start_download(selected_file, path)
        )
    
    def on_delete_clicked(self) -> None:
        """Handle delete button click"""
        selected_file = self.file_list_component.get_selected_file()
        if not selected_file:
            return
        
        if self.settings_manager.get('ui', 'confirm_deletions', True):
            self.dialog_manager.show_delete_confirmation_dialog(
                selected_file.name,
                lambda confirmed: self._delete_file_if_confirmed(selected_file, confirmed)
            )
        else:
            self._delete_file(selected_file)
    
    # File Operations
    def _on_files_selected(self, file_paths: List[str], parent_directory: Optional[str]) -> None:
        """Handle files selected for upload"""
        if parent_directory:
            self.settings_manager.set('general', 'last_directory', parent_directory)
            self.settings_manager.save_settings()
        
        # Validate files
        valid_files, invalid_files = FileValidator.validate_multiple_files(file_paths)
        
        # Show validation results if there are invalid files
        if invalid_files:
            validation_dialog = ValidationDialogMixin()
            validation_dialog.show_validation_results(valid_files, invalid_files, self)
        
        if valid_files:
            # Show folder selection dialog
            self.dialog_manager.show_folder_selection_dialog(
                valid_files, 
                self._on_folder_selected
            )
    
    def _on_folder_selected(self, file_paths, folder: str) -> None:
        """Handle folder selection for uploads"""
        if isinstance(file_paths, str):
            # Single file
            self._upload_single_file(file_paths, folder)
        else:
            # Multiple files
            self._upload_multiple_files(file_paths, folder)
    
    def _upload_single_file(self, file_path: str, folder: str) -> None:
        """Upload single file"""
        filename = Path(file_path).name
        self.progress_manager.show(_("Uploading {filename}...").format(filename=filename))
        
        def upload_thread():
            def progress_callback(progress):
                GLib.idle_add(self.progress_manager.update, progress)

            success = self.s3_service.upload_file(file_path, folder, progress_callback)
            GLib.idle_add(self._upload_complete, success, filename)

        self._run_in_thread(
            upload_thread, _("Upload failed for {filename}").format(filename=filename)
        )
    
    def _upload_multiple_files(self, file_paths: List[str], folder: str) -> None:
        """Upload multiple files in sequence"""
        print(_("Starting batch upload: {file_count} files to folder: {folder}").format(
            file_count=len(file_paths), folder=folder
        ))
        
        self.current_batch = {
            'files': file_paths,
            'folder': folder,
            'current_index': 0,
            'total_count': len(file_paths),
            'completed': 0,
            'failed': 0
        }
        
        self._upload_next_file_in_batch()
    
    def _upload_next_file_in_batch(self) -> None:
        """Upload the next file in the current batch"""
        batch = self.current_batch
        
        if batch['current_index'] >= len(batch['files']):
            # Batch complete
            self._batch_upload_complete()
            return
        
        current_file = batch['files'][batch['current_index']]
        filename = Path(current_file).name
        
        # Update progress message
        progress_msg = _("Uploading {current}/{total}: {filename}").format(
            current=batch['current_index'] + 1,
            total=batch['total_count'],
            filename=filename
        )
        self.progress_manager.show(progress_msg)
        
        def upload_thread():
            def progress_callback(progress):
                # Calculate overall progress
                file_progress = progress / 100.0
                overall_progress = ((batch['current_index'] + file_progress) / batch['total_count']) * 100
                GLib.idle_add(self.progress_manager.update, overall_progress)

            success = self.s3_service.upload_file(
                current_file, batch["folder"], progress_callback
            )
            GLib.idle_add(self._single_file_upload_complete, success, filename)

        self._run_in_thread(
            upload_thread,
            _("Batch upload error for {filename}").format(filename=filename),
        )
    
    def _single_file_upload_complete(self, success: bool, filename: str) -> bool:
        """Handle completion of a single file in batch upload"""
        batch = self.current_batch
        
        if success:
            batch['completed'] += 1
        else:
            batch['failed'] += 1
        
        batch['current_index'] += 1
        
        # Continue with next file
        self._upload_next_file_in_batch()
        return False
    
    def _batch_upload_complete(self) -> None:
        """Handle completion of entire batch upload"""
        batch = self.current_batch
        self.progress_manager.hide()
        
        # Show results
        total = batch['total_count']
        completed = batch['completed']
        failed = batch['failed']
        
        if failed == 0:
            self.show_toast(_("Successfully uploaded all {total} files!").format(total=total))
        else:
            self.show_toast(_("Upload complete: {completed} successful, {failed} failed").format(
                completed=completed, failed=failed
            ))
        
        # Refresh file list
        if self.settings_manager.get('general', 'auto_refresh', True):
            GLib.timeout_add(UI_CONSTANTS['REFRESH_DELAY'], self.refresh_files)
        
        # Update index if auto-update is enabled
        if self.settings_manager.get('ui', 'auto_update_index', True):
            self._update_html_index()
        
        # Clear batch info
        self.current_batch = None
    
    def _upload_complete(self, success: bool, filename: str) -> bool:
        """Handle single upload completion"""
        self.progress_manager.hide()
        
        if success:
            self.show_toast(_("Successfully uploaded {filename}").format(filename=filename))
            
            # Refresh file list
            if self.settings_manager.get('general', 'auto_refresh', True):
                GLib.timeout_add(UI_CONSTANTS['REFRESH_DELAY'], self.refresh_files)
            
            # Update index if auto-update is enabled
            if self.settings_manager.get('ui', 'auto_update_index', True):
                self._update_html_index()
        else:
            self.show_toast(_("Failed to upload {filename}").format(filename=filename))
        
        return False
    
    def _start_download(self, file_item: FileItem, save_path: str) -> None:
        """Start file download"""
        self.progress_manager.show(_("Downloading {filename}...").format(filename=file_item.name))
        
        def download_thread():
            def progress_callback(progress):
                GLib.idle_add(self.progress_manager.update, progress)
            
            success = self.s3_service.download_file(file_item.key, save_path, progress_callback)
            GLib.idle_add(self._download_complete, success, file_item.name)

        self._run_in_thread(
            download_thread,
            _("Download failed for {filename}").format(filename=file_item.name),
        )

    def _download_complete(self, success: bool, filename: str) -> bool:
        """Handle download completion"""
        self.progress_manager.hide()

        if success:
            self.show_toast(
                _("Successfully downloaded {filename}").format(filename=filename)
            )
        else:
            self.show_toast(
                _("Failed to download {filename}").format(filename=filename)
            )

        return False

    def _delete_file_if_confirmed(self, file_item: FileItem, confirmed: bool) -> None:
        """Delete file if confirmed"""
        if confirmed:
            self._delete_file(file_item)

    def _delete_file(self, file_item: FileItem) -> None:
        """Delete file from S3"""
        self.progress_manager.show(
            _("Deleting {filename}...").format(filename=file_item.name)
        )

        def delete_thread():
            success = self.s3_service.delete_file(file_item.key)
            GLib.idle_add(self._delete_complete, success, file_item.name)

        self._run_in_thread(
            delete_thread,
            _("Delete failed for {filename}").format(filename=file_item.name),
        )
    
    def _delete_complete(self, success: bool, filename: str) -> bool:
        """Handle delete completion"""
        self.progress_manager.hide()
        
        if success:
            self.show_toast(_("Successfully deleted {filename}").format(filename=filename))
            
            # Refresh file list
            if self.settings_manager.get('general', 'auto_refresh', True):
                self.refresh_files()
            
            # Update index if auto-update is enabled
            if self.settings_manager.get('ui', 'auto_update_index', True):
                self._update_html_index()
        else:
            self.show_toast(_("Failed to delete {filename}").format(filename=filename))
        
        return False
    
    def refresh_files(self) -> bool:
        """Refresh file list from S3"""
        if not self.s3_service:
            return False

        current_folder = self.get_selected_folder()
        print(_("Refreshing files for folder: {folder}").format(folder=current_folder))

        self.progress_manager.show(_("Loading files..."))

        def refresh_thread():
            if not self.s3_service.test_connection():
                GLib.idle_add(self._refresh_connection_error)
                return

            files = self.s3_service.list_files(current_folder)
            GLib.idle_add(self._files_loaded, files, current_folder)

        self._run_in_thread(refresh_thread, _("Failed to refresh file list"))
        return False

    def _refresh_connection_error(self) -> bool:
        """Handle refresh connection error"""
        self.progress_manager.hide()
        self.show_toast(
            _("Failed to connect to S3 storage. Check credentials and connection.")
        )
        return False

    def _files_loaded(self, files: List[dict], folder_filter: Optional[str]) -> bool:
        """Handle files loaded from S3"""
        self.progress_manager.hide()

        # Update file list
        self.file_list_component.set_files(files)

        # Update status
        count = len(files)
        folder_text = f" in {folder_filter}" if folder_filter else ""

        if count == 1:
            status_text = _("1 file{folder_text}").format(folder_text=folder_text)
        else:
            status_text = _("{count} files{folder_text}").format(
                count=count, folder_text=folder_text
            )

        self.status_label.set_text(status_text)

        return False

    def _update_html_index(self) -> None:
        """Update HTML index files"""
        if not self.html_generator:
            return

        def update_thread():
            # Get all files for index generation
            all_files = self.s3_service.list_files()

            # Generate and upload main index
            html_content = self.html_generator.generate_main_index(all_files)
            success = self.s3_service.upload_content(
                html_content, "index.html", "text/html"
            )

            if success:
                # Generate folder indexes
                for folder in ["Gnome", "Cinnamon", "XFCE"]:
                    folder_files = self.s3_service.list_files(folder)
                    if folder_files:
                        folder_html = self.html_generator.generate_folder_index(
                            folder, folder_files
                        )
                        self.s3_service.upload_content(
                            folder_html, f"{folder}/index.html", "text/html"
                        )

            GLib.idle_add(self._index_update_complete, success)

        self._run_in_thread(update_thread, _("Failed to update index files"))
    
    def _index_update_complete(self, success: bool) -> bool:
        """Handle index update completion"""
        if success:
            print("Index files updated successfully")
        else:
            print("Failed to update index files")
        
        return False
    
    # Action Handlers
    def _on_preferences_action(self, action, param) -> None:
        """Handle preferences action"""
        preferences_dialog = PreferencesDialog(
            self, 
            self.settings_manager,
            self._on_settings_changed
        )
        preferences_dialog.show_dialog()
    
    def _on_force_index_action(self, action, param) -> None:
        """Handle force index update action"""
        if not self.s3_service:
            self.show_toast(_("Please configure S3 credentials first"))
            return
        
        self.progress_manager.show(_("Updating index files..."))
        self._update_html_index()
        
        # Show completion after a delay
        def show_result():
            self.progress_manager.hide()
            self.show_toast(_("Index files updated!"))
            return False
        
        GLib.timeout_add(3000, show_result)
    
    def _on_refresh_action(self, action, param) -> None:
        """Handle refresh action"""
        self.refresh_files()
    
    def _on_about_action(self, action, param) -> None:
        """Handle about action"""
        self.dialog_manager.show_about_dialog()
    
    def _on_settings_changed(self) -> None:
        """Handle settings changes"""
        print("Settings changed, updating services...")
        
        # Get updated configurations
        s3_config = self.settings_manager.get_s3_config()
        web_config = self.settings_manager.get_web_config()
        
        if self.settings_manager.has_s3_credentials():
            # If S3Service exists, just update web config
            if self.s3_service:
                self.s3_service.update_web_config(web_config)
            else:
                # Create new S3Service if it doesn't exist
                self.s3_service = S3Service(s3_config, web_config)
                self.html_generator = HTMLGenerator(self.s3_service)
                
                # Test new connection
                self._test_connection_and_setup()
            
            # Refresh data to apply new filters
            self.refresh_files()
        else:
            self.s3_service = None
            self.html_generator = None
            self.show_toast(_("S3 credentials removed"))
    
    def _on_window_size_changed(self, window, param) -> None:
        """Handle window size changes"""
        # Save window size to settings
        width = self.get_width()
        height = self.get_height()
        
        if width > 0 and height > 0:
            self.settings_manager.set_window_size(width, height)
    
    # Utility Methods
    def _run_in_thread(self, target, error_message: str = "") -> None:
        """Run a function in a daemon thread with centralized error handling."""

        def wrapper():
            try:
                target()
            except Exception as e:
                print(f"Thread error: {e}")
                msg = error_message or _("An unexpected error occurred")
                GLib.idle_add(self._on_thread_error, msg, str(e))

        threading.Thread(target=wrapper, daemon=True).start()

    def _on_thread_error(self, message: str, detail: str) -> bool:
        """Handle thread errors by hiding progress and showing error to the user."""
        self.progress_manager.hide()
        self.show_toast(f"{message}: {detail}")
        return False

    def show_toast(self, message: str) -> None:
        """Show toast notification"""
        self.toast_manager.show(message)