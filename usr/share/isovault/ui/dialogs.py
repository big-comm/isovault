"""
Dialog management for the application.
Handles all dialogs including file selection, confirmations, etc.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio
from typing import List, Callable, Optional
from pathlib import Path
import os

from config import DISTRO_FOLDERS, SUPPORTED_EXTENSIONS


class DialogManager:
    """Manages all application dialogs"""
    
    def __init__(self, parent_window):
        """
        Initialize dialog manager.
        
        Args:
            parent_window: Parent window for dialog modality
        """
        self.parent_window = parent_window
    
    def show_upload_dialog(self, callback: Callable, last_directory: Optional[str] = None) -> None:
        """
        Show file upload dialog.
        
        Args:
            callback: Callback function for selected files
            last_directory: Last used directory
        """
        dialog = Gtk.FileChooserNative(
            title="Select ISO or MD5 files to upload",
            transient_for=self.parent_window,
            action=Gtk.FileChooserAction.OPEN
        )
        
        # Enable multiple file selection
        dialog.set_select_multiple(True)
        
        # Set last directory if available
        if last_directory and os.path.exists(last_directory):
            initial_file = Gio.File.new_for_path(last_directory)
            dialog.set_current_folder(initial_file)
        
        # Add file filters
        self._add_file_filters(dialog)
        
        dialog.connect("response", lambda d, r: self._on_upload_dialog_response(d, r, callback))
        dialog.show()
    
    def show_download_dialog(self, filename: str, callback: Callable) -> None:
        """
        Show file download dialog.
        
        Args:
            filename: Default filename
            callback: Callback function for save path
        """
        dialog = Gtk.FileChooserNative(
            title=f"Save {filename}",
            transient_for=self.parent_window,
            action=Gtk.FileChooserAction.SAVE
        )
        
        # Set initial filename
        initial_file = Gio.File.new_for_path(filename)
        dialog.set_current_file(initial_file)
        
        dialog.connect("response", lambda d, r: self._on_download_dialog_response(d, r, callback))
        dialog.show()
    
    def show_folder_selection_dialog(self, files: List[str], callback: Callable) -> None:
        """
        Show folder selection dialog for uploads.
        
        Args:
            files: List of file paths to upload
            callback: Callback function for folder selection
        """
        if len(files) == 1:
            self._show_single_file_folder_dialog(files[0], callback)
        else:
            self._show_multiple_files_folder_dialog(files, callback)
    
    def show_delete_confirmation_dialog(self, filename: str, callback: Callable) -> None:
        """
        Show delete confirmation dialog.
        
        Args:
            filename: Name of file to delete
            callback: Callback function for confirmation
        """
        dialog = Adw.AlertDialog(
            heading="Delete File",
            body=f"Are you sure you want to delete '{filename}'?\n\nThis action cannot be undone."
        )
        
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        
        dialog.connect("response", lambda d, r: callback(r == "delete"))
        dialog.present(self.parent_window)
    
    def show_about_dialog(self) -> None:
        """Show about dialog"""
        from config import APP_CONFIG
        
        dialog = Adw.AboutDialog(
            application_name=APP_CONFIG['app_name'],
            application_icon=APP_CONFIG['app_id'],
            version=APP_CONFIG['version'],
            developer_name="BigCommunity",
            website="https://communitybig.org",
            comments="ISO file manager for CDN77 storage",
            license_type=Gtk.License.GPL_3_0
        )
        
        dialog.present(self.parent_window)
    
    def show_error_dialog(self, title: str, message: str) -> None:
        """
        Show error dialog.
        
        Args:
            title: Dialog title
            message: Error message
        """
        dialog = Adw.AlertDialog(
            heading=title,
            body=message
        )
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        
        dialog.present(self.parent_window)
    
    def show_info_dialog(self, title: str, message: str, callback: Optional[Callable] = None) -> None:
        """
        Show information dialog.
        
        Args:
            title: Dialog title
            message: Information message
            callback: Optional callback for response
        """
        dialog = Adw.AlertDialog(
            heading=title,
            body=message
        )
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        
        if callback:
            dialog.connect("response", lambda d, r: callback())
        
        dialog.present(self.parent_window)
    
    def _add_file_filters(self, dialog: Gtk.FileChooserNative) -> None:
        """Add file filters to dialog"""
        # Add filter for supported files
        filter_files = Gtk.FileFilter()
        filter_files.set_name("Supported files (ISO, MD5)")
        for ext in SUPPORTED_EXTENSIONS:
            if ext.startswith('.'):
                filter_files.add_pattern(f"*{ext}")
                filter_files.add_pattern(f"*{ext.upper()}")
        dialog.add_filter(filter_files)
        
        # Add "All files" filter
        filter_all = Gtk.FileFilter()
        filter_all.set_name("All files")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)
    
    def _on_upload_dialog_response(self, dialog: Gtk.FileChooserNative, 
                                 response: int, callback: Callable) -> None:
        """Handle upload dialog response"""
        if response == Gtk.ResponseType.ACCEPT:
            files = dialog.get_files()
            if files and len(files) > 0:
                # Get file paths
                file_paths = []
                for file in files:
                    path = file.get_path()
                    if path:
                        file_paths.append(path)
                
                if file_paths:
                    # Get parent directory for settings
                    first_file = files[0]
                    parent_dir = first_file.get_parent()
                    parent_path = parent_dir.get_path() if parent_dir else None
                    
                    callback(file_paths, parent_path)
                else:
                    self.show_error_dialog("Upload Error", "Failed to get file paths")
            else:
                self.show_info_dialog("Upload", "No files selected")
        
        dialog.destroy()
    
    def _on_download_dialog_response(self, dialog: Gtk.FileChooserNative, 
                                   response: int, callback: Callable) -> None:
        """Handle download dialog response"""
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                save_path = file.get_path()
                if save_path:
                    callback(save_path)
                else:
                    self.show_error_dialog("Download Error", "Failed to get save path")
        
        dialog.destroy()
    
    def _show_single_file_folder_dialog(self, file_path: str, callback: Callable) -> None:
        """Show folder selection dialog for single file"""
        filename = Path(file_path).name
        print(f"Showing folder selection for: {file_path}")
        
        dialog = Adw.AlertDialog(
            heading="Select Destination Folder",
            body=f"Choose which folder to upload '{filename}' to:"
        )
        
        for folder in DISTRO_FOLDERS:
            dialog.add_response(folder.lower(), folder)
        
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        
        dialog.connect("response", lambda d, r: self._on_single_folder_response(d, r, file_path, callback))
        dialog.present(self.parent_window)
    
    def _show_multiple_files_folder_dialog(self, file_paths: List[str], callback: Callable) -> None:
        """Show folder selection dialog for multiple files"""
        file_count = len(file_paths)
        file_names = [Path(path).name for path in file_paths]
        
        print(f"Showing folder selection for {file_count} files: {file_names}")
        
        # Create file list for display (show max 5 files)
        file_list = "\n".join([f"• {name}" for name in file_names[:5]])
        if file_count > 5:
            file_list += f"\n... and {file_count - 5} more files"
        
        dialog = Adw.AlertDialog(
            heading="Select Destination Folder",
            body=f"Choose which folder to upload {file_count} files to:\n\n{file_list}"
        )
        
        for folder in DISTRO_FOLDERS:
            dialog.add_response(folder.lower(), folder)
        
        dialog.add_response("cancel", "Cancel")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        
        dialog.connect("response", lambda d, r: self._on_multiple_folder_response(d, r, file_paths, callback))
        dialog.present(self.parent_window)
    
    def _on_single_folder_response(self, dialog: Adw.AlertDialog, response: str, 
                                 file_path: str, callback: Callable) -> None:
        """Handle single file folder selection response"""
        print(f"Single folder dialog response: '{response}' for file: {file_path}")
        
        if response != "cancel":
            folder_map = {folder.lower(): folder for folder in DISTRO_FOLDERS}
            
            if response in folder_map:
                folder = folder_map[response]
                print(f"Selected folder: {folder}")
                callback(file_path, folder)
            else:
                print(f"Unknown response: {response}")
                self.show_error_dialog("Error", f"Unknown folder selection: {response}")
        else:
            print("Upload cancelled by user")
    
    def _on_multiple_folder_response(self, dialog: Adw.AlertDialog, response: str, 
                                   file_paths: List[str], callback: Callable) -> None:
        """Handle multiple files folder selection response"""
        print(f"Multiple folder dialog response: '{response}' for {len(file_paths)} files")
        
        if response != "cancel":
            folder_map = {folder.lower(): folder for folder in DISTRO_FOLDERS}
            
            if response in folder_map:
                folder = folder_map[response]
                print(f"Selected folder: {folder} for {len(file_paths)} files")
                callback(file_paths, folder)
            else:
                print(f"Unknown response: {response}")
                self.show_error_dialog("Error", f"Unknown folder selection: {response}")
        else:
            print("Batch upload cancelled by user")


class ValidationDialogMixin:
    """Mixin for validation-related dialogs"""
    
    def show_validation_results(self, valid_files: List[str], 
                              invalid_files: List[tuple], 
                              parent_window) -> None:
        """
        Show validation results for multiple files.
        
        Args:
            valid_files: List of valid file paths
            invalid_files: List of (filename, error_message) tuples
            parent_window: Parent window for dialog
        """
        if not invalid_files:
            return  # All files valid, nothing to show
        
        # Create message for invalid files
        invalid_count = len(invalid_files)
        valid_count = len(valid_files)
        
        invalid_list = []
        for filename, error in invalid_files[:5]:  # Show max 5 errors
            invalid_list.append(f"• {filename}: {error}")
        
        if invalid_count > 5:
            invalid_list.append(f"... and {invalid_count - 5} more files")
        
        message = f"Found {invalid_count} invalid files"
        if valid_count > 0:
            message += f" ({valid_count} valid files will be uploaded)"
        message += ":\n\n" + "\n".join(invalid_list)
        
        dialog = Adw.AlertDialog(
            heading="File Validation Results",
            body=message
        )
        
        dialog.add_response("ok", "Continue" if valid_count > 0 else "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        
        dialog.present(parent_window)