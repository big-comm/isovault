"""
Delete confirmation dialog: lists the files that will be removed.
"""

from typing import Callable, List

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from models import FileItem  # noqa: E402
from utils.helpers import format_file_size  # noqa: E402
from utils.i18n import _, ngettext  # noqa: E402

from .components import file_list_group  # noqa: E402


class DeleteDialog(Adw.Dialog):
    """Ask for confirmation before deleting files from the bucket"""

    def __init__(self, items: List[FileItem], on_confirm: Callable[[], None]):
        """
        Args:
            items: Files that will be deleted
            on_confirm: Called only if the user confirms
        """
        count = len(items)
        super().__init__(title=_("Delete File") if count == 1 else _("Delete Files"), content_width=600)
        self.add_css_class("delete-dialog")
        self._on_confirm = on_confirm

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(12)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.append(
            file_list_group(
                ngettext("{count} file will be deleted", "{count} files will be deleted", count).format(count=count),
                _("Total: {size}").format(size=format_file_size(sum(item.size for item in items))),
                [(item.name, f"{item.folder} · {item.size_formatted}") for item in items],
            )
        )
        content.append(self._build_warning())

        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(content)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(scroll)
        toolbar.add_bottom_bar(self._build_action_bar(count))
        self.set_child(toolbar)

    def _build_warning(self) -> Gtk.Widget:
        icon = Gtk.Image.new_from_icon_name("user-trash-symbolic")
        icon.set_pixel_size(22)
        icon.add_css_class("delete-warning-icon")

        title = Gtk.Label(label=_("This action cannot be undone."), xalign=0, wrap=True)
        title.add_css_class("heading")
        detail = Gtk.Label(
            label=_("The files are removed from the storage and from the public download page."),
            xalign=0,
            wrap=True,
        )
        detail.add_css_class("dim-label")
        detail.add_css_class("caption")

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, hexpand=True)
        text.append(title)
        text.append(detail)

        box = Gtk.Box(spacing=12)
        box.add_css_class("delete-warning")
        box.append(icon)
        box.append(text)
        return box

    def _build_action_bar(self, count: int) -> Gtk.Widget:
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.add_css_class("pill")
        cancel.connect("clicked", lambda _button: self.close())

        self.delete_button = Gtk.Button(
            label=ngettext("Delete {count} file", "Delete {count} files", count).format(count=count)
        )
        self.delete_button.add_css_class("destructive-action")
        self.delete_button.add_css_class("pill")
        self.delete_button.connect("clicked", self._on_delete_clicked)
        # Enter cancels: deleting must be an explicit click
        self.set_default_widget(cancel)
        self.cancel_button = cancel

        bar = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        bar.set_margin_top(12)
        bar.set_margin_bottom(12)
        bar.set_margin_start(24)
        bar.set_margin_end(24)
        bar.append(cancel)
        bar.append(self.delete_button)
        return bar

    def _on_delete_clicked(self, _button) -> None:
        self.close()
        self._on_confirm()
