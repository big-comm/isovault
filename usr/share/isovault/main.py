#!/usr/bin/env python3
"""
ISOVault - ISO file manager for CDN77 storage.
Application entry point.
"""

import logging
import os
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from config import APP_DIR, APP_ICON, APP_ID, APP_NAME, APP_VERSION  # noqa: E402
from ui import ISOVaultWindow  # noqa: E402
from utils.i18n import _  # noqa: E402

logger = logging.getLogger(__name__)


class ISOVaultApplication(Adw.Application):
    """Main application class"""

    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

        self.add_main_option(
            "version", ord("v"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, _("Show version information"), None
        )
        self.add_main_option(
            "debug", ord("d"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, _("Enable debug mode"), None
        )

    def do_handle_local_options(self, options: GLib.VariantDict) -> int:
        if options.contains("version"):
            print(f"{APP_NAME} {APP_VERSION}")
            return 0

        debug = options.contains("debug")
        logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )
        # boto's debug output is huge and includes request headers with the access key id
        for name in ("botocore", "boto3", "s3transfer", "urllib3"):
            logging.getLogger(name).setLevel(logging.WARNING)
        return -1  # continue normal startup

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(APP_ICON)
        self._load_css()

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_args: self.quit_gracefully())
        self.add_action(quit_action)

        self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        self.set_accels_for_action("win.refresh", ["<Ctrl>r", "F5"])
        self.set_accels_for_action("win.preferences", ["<Ctrl>comma"])

    def do_activate(self) -> None:
        window = self.get_active_window() or ISOVaultWindow(application=self)
        window.present()

    def quit_gracefully(self) -> None:
        """Close windows through close-request so they save their state."""
        windows = self.get_windows()
        if not windows:
            self.quit()
        for window in windows:
            window.close()

    @staticmethod
    def _load_css() -> None:
        display = Gdk.Display.get_default()
        if not display:
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(os.path.join(APP_DIR, "ui", "style.css"))
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def _install_signal_handlers(app: ISOVaultApplication) -> None:
    """Quit cleanly on Ctrl+C / SIGTERM (Python handlers don't run inside the GLib loop)."""
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix

        add_handler = GLibUnix.signal_add
    except (ImportError, ValueError):
        add_handler = GLib.unix_signal_add

    def on_signal():
        app.quit_gracefully()
        return GLib.SOURCE_CONTINUE

    for signum in (signal.SIGINT, signal.SIGTERM):
        add_handler(GLib.PRIORITY_DEFAULT, signum, on_signal)


def main() -> int:
    GLib.set_prgname(APP_ID)
    GLib.set_application_name(APP_NAME)

    app = ISOVaultApplication()
    _install_signal_handlers(app)
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
