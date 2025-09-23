#!/usr/bin/env python3
"""
ISOVault - ISO file manager for CDN77 storage.
Main application entry point.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')

from gi.repository import Gtk, Adw, Gio, GLib, Gdk
import sys
import os
import signal

from config import APP_CONFIG
from ui import ISOVaultWindow
from utils.i18n import _


class ISOVaultApplication(Adw.Application):
    """Main application class"""
    
    def __init__(self, **kwargs):
        """Initialize application"""
        super().__init__(
            application_id=APP_CONFIG['app_id'],
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            **kwargs
        )
        
        self.window = None
        
        # Connect signals
        self.connect('activate', self._on_activate)
        self.connect('startup', self._on_startup)
        self.connect('shutdown', self._on_shutdown)
        
        # Handle command line arguments
        self.add_main_option(
            "version",
            ord('v'),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Show version information"),
            None
        )
        
        self.add_main_option(
            "debug",
            ord('d'),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Enable debug mode"),
            None
        )
        
        self.connect('handle-local-options', self._on_handle_local_options)
    
    def _on_startup(self, app):
        """Handle application startup"""
        print(_("Starting {app_name} v{version}").format(
            app_name=APP_CONFIG['app_name'], 
            version=APP_CONFIG['version']
        ))
        
        # Set up application-level resources
        self._setup_css()
        self._setup_keyboard_shortcuts()
    
    def _on_activate(self, app):
        """Handle application activation"""
        if not self.window:
            self.window = ISOVaultWindow(application=app)
        
        self.window.present()
    
    def _on_shutdown(self, app):
        """Handle application shutdown"""
        print(_("Shutting down {app_name}").format(app_name=APP_CONFIG['app_name']))
        
        # Save window state and settings
        if self.window and hasattr(self.window, 'settings_manager'):
            # Save window size before closing
            width = self.window.get_width()
            height = self.window.get_height()
            if width > 0 and height > 0:
                self.window.settings_manager.set_window_size(width, height)
            
            # Save all settings
            self.window.settings_manager.save_settings()
    
    def _on_handle_local_options(self, app, options):
        """Handle command line options"""
        if options.contains("version"):
            print(f"{APP_CONFIG['app_name']} {APP_CONFIG['version']}")
            return 0
        
        if options.contains("debug"):
            print(_("Debug mode enabled"))
            os.environ['G_MESSAGES_DEBUG'] = 'all'
            import logging
            logging.basicConfig(level=logging.DEBUG)
        
        return -1  # Continue normal processing
    
    def _setup_css(self):
        """Setup application CSS"""
        css_provider = Gtk.CssProvider()
        
        # Custom CSS for the application
        css_data = """
        /* Custom application styles */
        .toast {
            border-radius: 8px;
        }
        
        .folder-icon {
            color: @accent_color;
        }
        
        .file-card {
            transition: all 0.2s ease;
        }
        
        .file-card:hover {
            background: alpha(@accent_color, 0.1);
        }
        
        .destructive-action {
            color: @error_color;
        }
        
        .destructive-action:hover {
            background: alpha(@error_color, 0.1);
        }
        
        .suggested-action {
            background: @accent_color;
            color: @accent_fg_color;
        }
        
        .progress-bar {
            border-radius: 4px;
        }
        
        .status-bar {
            border-top: 1px solid @borders;
            background: @headerbar_bg_color;
        }
        
        /* Make dialogs more modern */
        dialog.background {
            border-radius: 12px;
        }
        
        /* Improve file list appearance */
        columnview {
            border-radius: 8px;
        }
        
        columnview row:hover {
            background: alpha(@accent_color, 0.05);
        }
        
        columnview row:selected {
            background: alpha(@accent_color, 0.15);
        }
        """
        
        css_provider.load_from_data(css_data.encode('utf-8'))
        
        # Apply CSS to default display
        try:
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
        except Exception as e:
            print(_("Warning: Could not apply CSS: {error}").format(error=e))
    
    def _setup_keyboard_shortcuts(self):
        """Setup application keyboard shortcuts"""
        try:
            # Refresh shortcut
            self.set_accels_for_action("app.refresh", ["<Ctrl>r", "F5"])
            
            # Preferences shortcut
            self.set_accels_for_action("app.preferences", ["<Ctrl>comma"])
            
            # Quit shortcut
            self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        except Exception as e:
            print(_("Warning: Could not set keyboard shortcuts: {error}").format(error=e))
    
    def do_activate(self):
        """GTK activate signal handler"""
        self._on_activate(self)
    
    def do_startup(self):
        """GTK startup signal handler"""
        Adw.Application.do_startup(self)
        self._on_startup(self)
    
    def do_shutdown(self):
        """GTK shutdown signal handler"""
        self._on_shutdown(self)
        Adw.Application.do_shutdown(self)


def handle_signal(signum, frame):
    """Handle system signals gracefully"""
    print(_("\nReceived signal {signum}, shutting down gracefully...").format(signum=signum))
    
    # Get the current application instance
    app = Gio.Application.get_default()
    if app:
        app.quit()
    else:
        sys.exit(0)


def check_dependencies():
    """Check if all required dependencies are available"""
    missing_deps = []
    
    try:
        import boto3
    except ImportError:
        missing_deps.append("boto3")
    
    try:
        import configparser
    except ImportError:
        missing_deps.append("configparser")
    
    if missing_deps:
        print(_("Error: Missing required dependencies:"))
        for dep in missing_deps:
            print(f"  - {dep}")
        print(_("\nInstall them with: pip install {deps}").format(deps=" ".join(missing_deps)))
        return False
    
    return True


def setup_environment():
    """Setup application environment"""
    try:
        # Set application name for better integration
        GLib.set_application_name(APP_CONFIG['app_name'])
    except Exception as e:
        print(_("Warning: Could not set application name: {error}").format(error=e))
    
    # Set up signal handlers for graceful shutdown
    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
    except Exception as e:
        print(_("Warning: Could not set signal handlers: {error}").format(error=e))
    
    # Ensure config directory exists
    try:
        config_dir = os.path.dirname(APP_CONFIG['config_file'])
        os.makedirs(config_dir, exist_ok=True)
    except Exception as e:
        print(_("Warning: Could not create config directory: {error}").format(error=e))


def main():
    """Main entry point"""
    # Check dependencies
    if not check_dependencies():
        return 1
    
    # Setup environment
    setup_environment()
    
    # Create and run application
    try:
        app = ISOVaultApplication()
        return app.run(sys.argv)
    except KeyboardInterrupt:
        print(_("\nInterrupted by user"))
        return 0
    except Exception as e:
        print(_("Fatal error: {error}").format(error=e))
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)