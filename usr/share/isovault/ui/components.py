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
        print(f"{_('Progress')}: {message}")
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
        box = Gtk.Box(hexpand=True)
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(label)
        list_item.set_child(box)
    
    def _on_name_bind(self, factory, list_item):
        file_item = list_item.get_item()
        box = list_item.get_child()
        label = box.get_first_child()
        label.set_text(file_item.name)
        label.set_tooltip_text(file_item.name)
        self._apply_folder_class(box, file_item.folder)
    
    def _on_folder_setup(self, factory, list_item):
        box = Gtk.Box(hexpand=True)
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        box.append(label)
        list_item.set_child(box)
    
    def _on_folder_bind(self, factory, list_item):
        file_item = list_item.get_item()
        box = list_item.get_child()
        label = box.get_first_child()
        label.set_text(file_item.folder)
        self._apply_folder_class(box, file_item.folder)
    
    def _on_size_setup(self, factory, list_item):
        box = Gtk.Box(hexpand=True)
        label = Gtk.Label()
        label.set_halign(Gtk.Align.END)
        label.set_hexpand(True)
        box.append(label)
        list_item.set_child(box)
    
    def _on_size_bind(self, factory, list_item):
        file_item = list_item.get_item()
        box = list_item.get_child()
        label = box.get_first_child()
        label.set_text(file_item.size_formatted)
        self._apply_folder_class(box, file_item.folder)
    
    def _on_modified_setup(self, factory, list_item):
        box = Gtk.Box(hexpand=True)
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        box.append(label)
        list_item.set_child(box)
    
    def _on_modified_bind(self, factory, list_item):
        file_item = list_item.get_item()
        box = list_item.get_child()
        label = box.get_first_child()
        formatted_date = file_item.modified.strftime("%Y-%m-%d %H:%M")
        label.set_text(formatted_date)
        self._apply_folder_class(box, file_item.folder)

    def _apply_folder_class(self, widget, folder):
        """Apply CSS class based on folder name for row coloring"""
        for cls in ("folder-gnome", "folder-cinnamon", "folder-xfce", "folder-root"):
            widget.remove_css_class(cls)
        folder_lower = folder.lower()
        if folder_lower == "gnome":
            widget.add_css_class("folder-gnome")
        elif folder_lower == "cinnamon":
            widget.add_css_class("folder-cinnamon")
        elif folder_lower == "xfce":
            widget.add_css_class("folder-xfce")
        elif folder_lower == "root":
            widget.add_css_class("folder-root")
    
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
    """Legacy toolbar component - kept for backward compatibility.
    Functionality moved to ISOVaultWindow sidebar."""

    pass


class HeaderBarComponent:
    """Legacy header bar component - kept for backward compatibility.
    Functionality moved to ISOVaultWindow._build_content()."""

    pass