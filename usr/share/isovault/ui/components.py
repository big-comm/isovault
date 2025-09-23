"""
Reusable UI components for the application.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, Pango
from typing import Optional, Callable
from config import UI_CONSTANTS
from models import FileItem
from utils.i18n import _


class ProgressManager:
    """Manages progress bar display and updates"""
    
    def __init__(self, progress_bar: Gtk.ProgressBar, status_label: Gtk.Label):
        """
        Initialize progress manager.
        
        Args:
            progress_bar: GTK progress bar widget
            status_label: GTK label for status messages
        """
        self.progress_bar = progress_bar
        self.status_label = status_label
        self.is_visible = False
    
    def show(self, message: str) -> None:
        """Show progress bar with message"""
        print(_("Progress: {message}").format(message=message))
        self.status_label.set_text(message)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("0%")
        self.is_visible = True
    
    def update(self, progress: float) -> None:
        """Update progress bar"""
        if self.is_visible:
            print(_("Progress update: {progress:.1f}%").format(progress=progress))
            fraction = progress / 100.0
            self.progress_bar.set_fraction(fraction)
            self.progress_bar.set_text(f"{progress:.1f}%")
    
    def hide(self) -> None:
        """Hide progress bar"""
        print(_("Hiding progress"))
        self.progress_bar.set_visible(False)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("")
        self.is_visible = False


class ToastManager:
    """Manages toast notifications"""
    
    def __init__(self, toast_overlay: Adw.ToastOverlay):
        """
        Initialize toast manager.
        
        Args:
            toast_overlay: Adwaita toast overlay widget
        """
        self.toast_overlay = toast_overlay
    
    def show(self, message: str, timeout: int = UI_CONSTANTS['TOAST_TIMEOUT']) -> None:
        """Show toast notification"""
        toast = Adw.Toast(title=message)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)


class FileListComponent:
    """Manages the file list view and its interactions"""
    
    def __init__(self, parent_window):
        """
        Initialize file list component.
        
        Args:
            parent_window: Parent window instance
        """
        self.parent_window = parent_window
        self.file_model = None
        self.selection_model = None
        self.column_view = None
        self.setup_file_list()
    
    def setup_file_list(self) -> Gtk.ScrolledWindow:
        """Setup the file list view and return scrolled window"""
        # Create list model
        self.file_model = Gio.ListStore(item_type=FileItem)
        
        # Create selection model
        self.selection_model = Gtk.SingleSelection(model=self.file_model)
        self.selection_model.connect("notify::selected", self._on_selection_changed)
        
        # Create column view
        self.column_view = Gtk.ColumnView(model=self.selection_model)
        self.column_view.set_show_row_separators(True)
        self.column_view.set_show_column_separators(True)
        
        # Setup columns
        self._setup_columns()
        
        # Scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(self.column_view)
        
        return scrolled
    
    def _setup_columns(self) -> None:
        """Setup column view columns"""
        # Name column
        name_factory = Gtk.SignalListItemFactory()
        name_factory.connect("setup", self._on_name_setup)
        name_factory.connect("bind", self._on_name_bind)
        name_column = Gtk.ColumnViewColumn(title=_("File Name"), factory=name_factory)
        name_column.set_expand(True)
        name_column.set_resizable(True)
        self.column_view.append_column(name_column)
        
        # Folder column
        folder_factory = Gtk.SignalListItemFactory()
        folder_factory.connect("setup", self._on_folder_setup)
        folder_factory.connect("bind", self._on_folder_bind)
        folder_column = Gtk.ColumnViewColumn(title=_("Folder"), factory=folder_factory)
        folder_column.set_resizable(True)
        self.column_view.append_column(folder_column)
        
        # Size column
        size_factory = Gtk.SignalListItemFactory()
        size_factory.connect("setup", self._on_size_setup)
        size_factory.connect("bind", self._on_size_bind)
        size_column = Gtk.ColumnViewColumn(title=_("Size"), factory=size_factory)
        size_column.set_resizable(True)
        self.column_view.append_column(size_column)
        
        # Modified column
        modified_factory = Gtk.SignalListItemFactory()
        modified_factory.connect("setup", self._on_modified_setup)
        modified_factory.connect("bind", self._on_modified_bind)
        modified_column = Gtk.ColumnViewColumn(title=_("Modified"), factory=modified_factory)
        modified_column.set_resizable(True)
        self.column_view.append_column(modified_column)
    
    # Column factory setup methods
    def _on_name_setup(self, factory, list_item):
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        list_item.set_child(label)
    
    def _on_name_bind(self, factory, list_item):
        file_item = list_item.get_item()
        label = list_item.get_child()
        label.set_text(file_item.name)
    
    def _on_folder_setup(self, factory, list_item):
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        list_item.set_child(label)
    
    def _on_folder_bind(self, factory, list_item):
        file_item = list_item.get_item()
        label = list_item.get_child()
        label.set_text(file_item.folder)
    
    def _on_size_setup(self, factory, list_item):
        label = Gtk.Label()
        label.set_halign(Gtk.Align.END)
        list_item.set_child(label)
    
    def _on_size_bind(self, factory, list_item):
        file_item = list_item.get_item()
        label = list_item.get_child()
        label.set_text(file_item.size_formatted)
    
    def _on_modified_setup(self, factory, list_item):
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        list_item.set_child(label)
    
    def _on_modified_bind(self, factory, list_item):
        file_item = list_item.get_item()
        label = list_item.get_child()
        formatted_date = file_item.modified.strftime("%Y-%m-%d %H:%M")
        label.set_text(formatted_date)
    
    def _on_selection_changed(self, selection_model, pspec):
        """Handle file selection changes"""
        has_selection = selection_model.get_selected() != Gtk.INVALID_LIST_POSITION
        # Notify parent window about selection change
        if hasattr(self.parent_window, 'on_file_selection_changed'):
            self.parent_window.on_file_selection_changed(has_selection)
    
    def get_selected_file(self) -> Optional[FileItem]:
        """Get currently selected file"""
        selected_pos = self.selection_model.get_selected()
        if selected_pos != Gtk.INVALID_LIST_POSITION:
            return self.file_model.get_item(selected_pos)
        return None
    
    def clear_files(self) -> None:
        """Clear all files from the list"""
        self.file_model.remove_all()
    
    def add_file(self, file_item: FileItem) -> None:
        """Add a file to the list"""
        self.file_model.append(file_item)
    
    def set_files(self, files: list) -> None:
        """Set the entire file list"""
        self.clear_files()
        for file_data in files:
            file_item = FileItem(
                name=file_data['name'],
                folder=file_data['folder'],
                key=file_data['key'],
                size=file_data['size'],
                modified=file_data['modified'],
                size_formatted=file_data['size_formatted']
            )
            self.add_file(file_item)


class ToolbarComponent:
    """Manages the toolbar with filter and action buttons"""
    
    def __init__(self, parent_window):
        """
        Initialize toolbar component.
        
        Args:
            parent_window: Parent window instance
        """
        self.parent_window = parent_window
        self.folder_dropdown = None
        self.copy_link_btn = None
        self.download_btn = None
        self.delete_btn = None
    
    def create_toolbar(self) -> Gtk.Box:
        """Create and return the toolbar widget"""
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        toolbar.set_margin_top(12)
        toolbar.set_margin_bottom(12)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)
        
        # Filter label
        filter_label = Gtk.Label(label=_("Filter by folder:"))
        toolbar.append(filter_label)
        
        # Folder filter dropdown
        self.folder_dropdown = Gtk.DropDown()
        folder_model = Gtk.StringList()
        folder_model.append(_("All folders"))
        from config import DISTRO_FOLDERS
        for folder in DISTRO_FOLDERS:
            folder_model.append(folder)
        self.folder_dropdown.set_model(folder_model)
        self.folder_dropdown.connect("notify::selected", self._on_folder_filter_changed)
        toolbar.append(self.folder_dropdown)
        
        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)
        
        # Copy Link button
        self.copy_link_btn = Gtk.Button(label=_("Copy Link"))
        self.copy_link_btn.set_icon_name("edit-copy-symbolic")
        self.copy_link_btn.set_sensitive(False)
        self.copy_link_btn.connect("clicked", self._on_copy_link_clicked)
        toolbar.append(self.copy_link_btn)
        
        # Download button
        self.download_btn = Gtk.Button(label=_("Download"))
        self.download_btn.set_icon_name("folder-download-symbolic")
        self.download_btn.set_sensitive(False)
        self.download_btn.connect("clicked", self._on_download_clicked)
        toolbar.append(self.download_btn)
        
        # Delete button
        self.delete_btn = Gtk.Button(label=_("Delete"))
        self.delete_btn.set_icon_name("user-trash-symbolic")
        self.delete_btn.add_css_class("destructive-action")
        self.delete_btn.set_sensitive(False)
        self.delete_btn.connect("clicked", self._on_delete_clicked)
        toolbar.append(self.delete_btn)
        
        return toolbar
    
    def set_buttons_sensitive(self, sensitive: bool) -> None:
        """Enable/disable action buttons based on selection"""
        self.copy_link_btn.set_sensitive(sensitive)
        self.download_btn.set_sensitive(sensitive)
        self.delete_btn.set_sensitive(sensitive)
    
    def _on_folder_filter_changed(self, dropdown, pspec):
        """Handle folder filter changes"""
        if hasattr(self.parent_window, 'on_folder_filter_changed'):
            self.parent_window.on_folder_filter_changed()
    
    def _on_copy_link_clicked(self, button):
        """Handle copy link button click"""
        if hasattr(self.parent_window, 'on_copy_link_clicked'):
            self.parent_window.on_copy_link_clicked()
    
    def _on_download_clicked(self, button):
        """Handle download button click"""
        if hasattr(self.parent_window, 'on_download_clicked'):
            self.parent_window.on_download_clicked()
    
    def _on_delete_clicked(self, button):
        """Handle delete button click"""
        if hasattr(self.parent_window, 'on_delete_clicked'):
            self.parent_window.on_delete_clicked()
    
    def get_selected_folder(self) -> Optional[str]:
        """Get currently selected folder from dropdown"""
        selected = self.folder_dropdown.get_selected()
        if selected == 0:  # "All folders"
            return None
        else:
            from config import DISTRO_FOLDERS
            return DISTRO_FOLDERS[selected - 1]


class HeaderBarComponent:
    """Manages the header bar with menu and actions"""
    
    def __init__(self, parent_window):
        """
        Initialize header bar component.
        
        Args:
            parent_window: Parent window instance
        """
        self.parent_window = parent_window
    
    def create_header_bar(self) -> Adw.HeaderBar:
        """Create and return the header bar widget"""
        header_bar = Adw.HeaderBar()
        from config import APP_CONFIG
        header_bar.set_title_widget(Gtk.Label(label=APP_CONFIG['app_name']))
        
        # Upload button (primary action)
        upload_btn = Gtk.Button()
        upload_btn.set_icon_name("document-send-symbolic")
        upload_btn.set_tooltip_text(_("Upload ISO file"))
        upload_btn.add_css_class("suggested-action")
        upload_btn.connect("clicked", self._on_upload_clicked)
        header_bar.pack_start(upload_btn)
        
        # Menu button (hamburger menu)
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_tooltip_text(_("Application menu"))
        
        # Create menu model - Fixed for GTK4
        menu_model = Gio.Menu()
        
        # Main section
        main_section = Gio.Menu()
        main_section.append(_("Preferences"), "app.preferences")
        main_section.append(_("Force Update Index"), "app.force_index")
        main_section.append(_("Refresh"), "app.refresh")
        menu_model.append_section(None, main_section)
        
        # About section (separated)
        about_section = Gio.Menu()
        about_section.append(_("About"), "app.about")
        menu_model.append_section(None, about_section)
        
        menu_btn.set_menu_model(menu_model)
        header_bar.pack_end(menu_btn)
        
        return header_bar
    
    def _on_upload_clicked(self, button):
        """Handle upload button click"""
        if hasattr(self.parent_window, 'on_upload_clicked'):
            self.parent_window.on_upload_clicked()