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
from .components import (
    ProgressManager, ToastManager, FileListComponent, 
    ToolbarComponent, HeaderBarComponent
)
from .dialogs import DialogManager, ValidationDialogMixin
from .preferences import PreferencesDialog


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
        self.toolbar_component = None
        
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
        self.set_title(APP_CONFIG['window_title'])
        
        # Load window size from settings
        width, height = self.settings_manager.get_window_size()
        self.set_default_size(width, height)
        
        # Connect window size tracking
        self.connect("notify::default-width", self._on_window_size_changed)
        self.connect("notify::default-height", self._on_window_size_changed)
    
    def _setup_ui(self) -> None:
        """Setup the main UI components"""
        # Main toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        self.toast_manager = ToastManager(self.toast_overlay)
        
        # Main vertical box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_box)
        
        # Header bar
        header_component = HeaderBarComponent(self)
        header_bar = header_component.create_header_bar()
        main_box.append(header_bar)
        
        # Toolbar with filter and actions
        self.toolbar_component = ToolbarComponent(self)
        toolbar = self.toolbar_component.create_toolbar()
        main_box.append(toolbar)
        
        # File list
        self.file_list_component = FileListComponent(self)
        file_list_scrolled = self.file_list_component.setup_file_list()
        main_box.append(file_list_scrolled)
        
        # Status bar
        self._setup_status_bar(main_box)
    
    def _setup_status_bar(self, parent) -> None:
        """Setup status bar"""
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        status_box.set_margin_top(6)
        status_box.set_margin_bottom(6)
        status_box.set_margin_start(12)
        status_box.set_margin_end(12)
        
        # Status label and progress in same horizontal box
        self.status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_hexpand(True)
        self.status_bar.append(self.status_label)
        
        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(300, -1)  # Fixed width
        self.progress_bar.set_visible(False)
        self.progress_bar.set_show_text(True)
        self.status_bar.append(self.progress_bar)
        
        # Initialize progress manager
        self.progress_manager = ProgressManager(self.progress_bar, self.status_label)
        
        status_box.append(self.status_bar)
        parent.append(status_box)
    
    def _setup_services(self) -> None:
        """Setup S3 service and related services"""
        s3_config = self.settings_manager.get_s3_config()
        
        if self.settings_manager.has_s3_credentials():
            self.s3_service = S3Service(s3_config)
            self.html_generator = HTMLGenerator(self.s3_service)
            
            # Test connection and create folders in background
            threading.Thread(target=self._test_connection_and_setup, daemon=True).start()
        else:
            print("No S3 credentials configured")
            self.show_toast("Please configure S3 credentials in Preferences")
    
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
        
        try:
            connected = self.s3_service.test_connection()
            if connected:
                self.s3_service.create_folders()
                GLib.idle_add(self._on_connection_success)
            else:
                GLib.idle_add(self._on_connection_failed)
        except Exception as e:
            print(f"Connection test error: {e}")
            GLib.idle_add(self._on_connection_failed)
    
    def _on_connection_success(self) -> bool:
        """Handle successful S3 connection"""
        print("S3 connection successful")
        return False  # Remove from GLib idle
    
    def _on_connection_failed(self) -> bool:
        """Handle failed S3 connection"""
        self.show_toast("Warning: Could not connect to S3 storage")
        return False  # Remove from GLib idle
    
    # UI Event Handlers
    def on_file_selection_changed(self, has_selection: bool) -> None:
        """Handle file selection changes"""
        self.toolbar_component.set_buttons_sensitive(has_selection)
    
    def on_folder_filter_changed(self) -> None:
        """Handle folder filter changes"""
        self.refresh_files()
    
    def on_upload_clicked(self) -> None:
        """Handle upload button click"""
        if not self.s3_service:
            self.show_toast("Please configure S3 credentials first")
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
        self.show_toast(f"Link copied: {public_url}")
    
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
        self.progress_manager.show(f"Uploading {filename}...")
        
        def upload_thread():
            def progress_callback(progress):
                GLib.idle_add(self.progress_manager.update, progress)
            
            try:
                success = self.s3_service.upload_file(file_path, folder, progress_callback)
                GLib.idle_add(self._upload_complete, success, filename)
            except Exception as e:
                print(f"Upload error: {e}")
                GLib.idle_add(self._upload_complete, False, filename)
        
        threading.Thread(target=upload_thread, daemon=True).start()
    
    def _upload_multiple_files(self, file_paths: List[str], folder: str) -> None:
        """Upload multiple files in sequence"""
        print(f"Starting batch upload: {len(file_paths)} files to folder: {folder}")
        
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
        progress_msg = f"Uploading {batch['current_index'] + 1}/{batch['total_count']}: {filename}"
        self.progress_manager.show(progress_msg)
        
        def upload_thread():
            def progress_callback(progress):
                # Calculate overall progress
                file_progress = progress / 100.0
                overall_progress = ((batch['current_index'] + file_progress) / batch['total_count']) * 100
                GLib.idle_add(self.progress_manager.update, overall_progress)
            
            try:
                success = self.s3_service.upload_file(current_file, batch['folder'], progress_callback)
                GLib.idle_add(self._single_file_upload_complete, success, filename)
            except Exception as e:
                print(f"Batch upload error for {filename}: {e}")
                GLib.idle_add(self._single_file_upload_complete, False, filename)
        
        threading.Thread(target=upload_thread, daemon=True).start()
    
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
            self.show_toast(f"Successfully uploaded all {total} files!")
        else:
            self.show_toast(f"Upload complete: {completed} successful, {failed} failed")
        
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
            self.show_toast(f"Successfully uploaded {filename}")
            
            # Refresh file list
            if self.settings_manager.get('general', 'auto_refresh', True):
                GLib.timeout_add(UI_CONSTANTS['REFRESH_DELAY'], self.refresh_files)
            
            # Update index if auto-update is enabled
            if self.settings_manager.get('ui', 'auto_update_index', True):
                self._update_html_index()
        else:
            self.show_toast(f"Failed to upload {filename}")
        
        return False
    
    def _start_download(self, file_item: FileItem, save_path: str) -> None:
        """Start file download"""
        self.progress_manager.show(f"Downloading {file_item.name}...")
        
        def download_thread():
            def progress_callback(progress):
                GLib.idle_add(self.progress_manager.update, progress)
            
            success = self.s3_service.download_file(file_item.key, save_path, progress_callback)
            GLib.idle_add(self._download_complete, success, file_item.name)
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def _download_complete(self, success: bool, filename: str) -> bool:
        """Handle download completion"""
        self.progress_manager.hide()
        
        if success:
            self.show_toast(f"Successfully downloaded {filename}")
        else:
            self.show_toast(f"Failed to download {filename}")
        
        return False
    
    def _delete_file_if_confirmed(self, file_item: FileItem, confirmed: bool) -> None:
        """Delete file if confirmed"""
        if confirmed:
            self._delete_file(file_item)
    
    def _delete_file(self, file_item: FileItem) -> None:
        """Delete file from S3"""
        self.progress_manager.show(f"Deleting {file_item.name}...")
        
        def delete_thread():
            success = self.s3_service.delete_file(file_item.key)
            GLib.idle_add(self._delete_complete, success, file_item.name)
        
        threading.Thread(target=delete_thread, daemon=True).start()
    
    def _delete_complete(self, success: bool, filename: str) -> bool:
        """Handle delete completion"""
        self.progress_manager.hide()
        
        if success:
            self.show_toast(f"Successfully deleted {filename}")
            
            # Refresh file list
            if self.settings_manager.get('general', 'auto_refresh', True):
                self.refresh_files()
            
            # Update index if auto-update is enabled
            if self.settings_manager.get('ui', 'auto_update_index', True):
                self._update_html_index()
        else:
            self.show_toast(f"Failed to delete {filename}")
        
        return False
    
    def refresh_files(self) -> bool:
        """Refresh file list from S3"""
        if not self.s3_service:
            return False
        
        current_folder = self.toolbar_component.get_selected_folder()
        print(f"Refreshing files for folder: {current_folder}")
        
        self.progress_manager.show("Loading files...")
        
        def refresh_thread():
            try:
                if not self.s3_service.test_connection():
                    GLib.idle_add(self._refresh_connection_error)
                    return
                
                files = self.s3_service.list_files(current_folder)
                GLib.idle_add(self._files_loaded, files, current_folder)
            except Exception as e:
                print(f"Error in refresh thread: {e}")
                GLib.idle_add(self._files_loaded, [], current_folder)
        
        threading.Thread(target=refresh_thread, daemon=True).start()
        return False
    
    def _refresh_connection_error(self) -> bool:
        """Handle refresh connection error"""
        self.progress_manager.hide()
        self.show_toast("Failed to connect to S3 storage. Check credentials and connection.")
        return False
    
    def _files_loaded(self, files: List[dict], folder_filter: Optional[str]) -> bool:
        """Handle files loaded from S3"""
        self.progress_manager.hide()
        
        # Update file list
        self.file_list_component.set_files(files)
        
        # Update status
        count = len(files)
        folder_text = f" in {folder_filter}" if folder_filter else ""
        self.status_label.set_text(f"{count} file{'s' if count != 1 else ''}{folder_text}")
        
        return False
    
    def _update_html_index(self) -> None:
        """Update HTML index files"""
        if not self.html_generator:
            return
        
        def update_thread():
            try:
                # Get all files for index generation
                all_files = self.s3_service.list_files()
                
                # Generate and upload main index
                html_content = self.html_generator.generate_main_index(all_files)
                success = self.s3_service.upload_content(
                    html_content,
                    'index.html',
                    'text/html'
                )
                
                if success:
                    # Generate folder indexes
                    for folder in ['Gnome', 'Cinnamon', 'XFCE']:
                        folder_files = self.s3_service.list_files(folder)
                        if folder_files:
                            folder_html = self.html_generator.generate_folder_index(folder, folder_files)
                            self.s3_service.upload_content(
                                folder_html,
                                f"{folder}/index.html",
                                'text/html'
                            )
                
                GLib.idle_add(self._index_update_complete, success)
                
            except Exception as e:
                print(f"Error updating index: {e}")
                GLib.idle_add(self._index_update_complete, False)
        
        threading.Thread(target=update_thread, daemon=True).start()
    
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
            self.show_toast("Please configure S3 credentials first")
            return
        
        self.progress_manager.show("Updating index files...")
        self._update_html_index()
        
        # Show completion after a delay
        def show_result():
            self.progress_manager.hide()
            self.show_toast("Index files updated!")
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
        
        # Reinitialize S3 service with new settings
        s3_config = self.settings_manager.get_s3_config()
        
        if self.settings_manager.has_s3_credentials():
            self.s3_service = S3Service(s3_config)
            self.html_generator = HTMLGenerator(self.s3_service)
            
            # Test new connection
            threading.Thread(target=self._test_connection_and_setup, daemon=True).start()
            
            # Refresh data
            self.refresh_files()
        else:
            self.s3_service = None
            self.html_generator = None
            self.show_toast("S3 credentials removed")
    
    def _on_window_size_changed(self, window, param) -> None:
        """Handle window size changes"""
        # Save window size to settings
        width = self.get_width()
        height = self.get_height()
        
        if width > 0 and height > 0:
            self.settings_manager.set_window_size(width, height)
    
    # Utility Methods
    def show_toast(self, message: str) -> None:
        """Show toast notification"""
        self.toast_manager.show(message)