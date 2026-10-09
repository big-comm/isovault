"""
File browser: the bucket files as a table or a grid of cards.

Model chain: ListStore (every file) -> FilterListModel (folder + search)
-> SortListModel -> MultiSelection. Both views share the same selection,
so switching between list and grid keeps the checked files.
"""

from typing import Callable, Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

from models import FileItem  # noqa: E402
from utils.i18n import _  # noqa: E402

# Fixed widths so the header lines up with the rows
_WIDTHS = {"check": 40, "icon": 36, "folder": 120, "size": 90, "modified": 150, "actions": 52}

SORT_KEYS = ("name", "folder", "size", "modified")

# Grid cards are squares at least this wide (fits the card content)
_CARD_MIN_SIZE = 176


class SquareBin(Gtk.Widget):
    """Single-child container that is always as tall as it is wide"""

    __gtype_name__ = "IsovaultSquareBin"

    def __init__(self, child: Gtk.Widget):
        super().__init__()
        self.child = child
        child.set_parent(self)

    def do_get_request_mode(self) -> Gtk.SizeRequestMode:
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation: Gtk.Orientation, for_size: int):
        minimum, natural, _mb, _nb = self.child.measure(orientation, for_size)
        if orientation == Gtk.Orientation.HORIZONTAL:
            minimum = max(minimum, _CARD_MIN_SIZE)
            return minimum, max(natural, minimum), -1, -1
        side = max(minimum, for_size if for_size > 0 else _CARD_MIN_SIZE)
        return side, side, -1, -1

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        self.child.allocate(width, height, baseline, None)

    def do_dispose(self) -> None:
        if self.child is not None:
            self.child.unparent()
            self.child = None
        Gtk.Widget.do_dispose(self)


def format_date(item: FileItem) -> str:
    """Local date and time in the user's locale format."""
    return item.modified.astimezone().strftime("%x %H:%M")


def distro_badge(folder: str) -> Gtk.Label:
    badge = Gtk.Label(label=folder, valign=Gtk.Align.CENTER, halign=Gtk.Align.START)
    badge.add_css_class("distro-badge")
    badge.add_css_class(f"distro-{folder.lower()}")
    return badge


def file_icon(item: FileItem, pixel_size: int = 16) -> Gtk.Widget:
    """Colored disc for ISOs, plain document for checksum files."""
    is_iso = item.name.lower().endswith(".iso")
    image = Gtk.Image.new_from_icon_name("media-optical-symbolic" if is_iso else "text-x-generic-symbolic")
    image.set_pixel_size(pixel_size)
    box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    box.add_css_class("file-icon")
    box.add_css_class(f"distro-{item.folder.lower()}" if is_iso else "checksum")
    box.append(image)
    return box


def row_menu(key: str) -> Gio.Menu:
    """Per-file action menu; actions are window actions taking the S3 key."""
    menu = Gio.Menu()
    for label, action in (
        (_("Copy Link"), "win.file-copy-link"),
        (_("Download"), "win.file-download"),
        (_("Delete"), "win.file-delete"),
    ):
        item = Gio.MenuItem.new(label, None)
        item.set_action_and_target_value(action, GLib.Variant("s", key))
        menu.append_item(item)
    return menu


class FileBrowser:
    """Filterable, sortable file list with list and grid views"""

    def __init__(self, on_selection_changed: Callable[[int], None]):
        """
        Args:
            on_selection_changed: Called with the number of selected files
        """
        self._on_selection_changed = on_selection_changed
        self._folder: Optional[str] = None
        self._search = ""
        self.sort_key = "modified"
        self.sort_descending = True
        self._updating_header = False
        self._compact = False
        self._row_widgets: List[Gtk.Box] = []  # every row created by the list factory

        self.store = Gio.ListStore(item_type=FileItem)
        self._filter = Gtk.CustomFilter.new(self._matches)
        self.filter_model = Gtk.FilterListModel(model=self.store, filter=self._filter)
        self._sorter = Gtk.CustomSorter.new(self._compare)
        self.sort_model = Gtk.SortListModel(model=self.filter_model, sorter=self._sorter)
        self.selection_model = Gtk.MultiSelection(model=self.sort_model)
        self.selection_model.connect("selection-changed", lambda *_args: self._selection_changed())
        self.filter_model.connect("items-changed", lambda *_args: self._update_empty_state())

        self.list_view = self._build_list_view()
        self.grid_view = self._build_grid_view()

        self.empty_page = Adw.StatusPage(icon_name="folder-symbolic")
        self.empty_page.add_css_class("compact")

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.stack.add_named(self._build_table(), "list")
        grid_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        grid_scroll.set_child(self.grid_view)
        self.stack.add_named(grid_scroll, "grid")
        self.stack.add_named(self.empty_page, "empty")
        self._view = "list"
        self.widget = self.stack
        self._update_empty_state()

    # Table (list view)

    def _build_table(self) -> Gtk.Widget:
        header = Gtk.Box(spacing=0)
        header.add_css_class("file-table-header")

        self.header_check = Gtk.CheckButton(tooltip_text=_("Select All"))
        self.header_check.set_size_request(_WIDTHS["check"], -1)
        self.header_check.connect("toggled", self._on_header_check_toggled)
        header.append(self.header_check)
        header.append(Gtk.Box(width_request=_WIDTHS["icon"]))

        self.sort_buttons: Dict[str, Gtk.Button] = {}
        for key, title in (
            ("name", _("File Name")),
            ("folder", _("Distribution")),
            ("size", _("Size")),
            ("modified", _("Modified")),
        ):
            label = Gtk.Label(label=title, xalign=0)
            arrow = Gtk.Image()
            content = Gtk.Box(spacing=4)
            content.append(label)
            content.append(arrow)
            button = Gtk.Button(child=content, hexpand=key == "name")
            button.add_css_class("flat")
            button.add_css_class("sort-button")
            if key != "name":
                button.set_size_request(_WIDTHS[key], -1)
            button.connect("clicked", lambda _b, k=key: self.set_sort(k))
            button.arrow = arrow
            header.append(button)
            self.sort_buttons[key] = button

        actions = Gtk.Label(label=_("Actions"), xalign=0.5)
        actions.add_css_class("column-title")
        actions.set_size_request(_WIDTHS["actions"], -1)
        header.append(actions)
        self._update_sort_arrows()

        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.list_view)

        table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        table.add_css_class("file-table")
        table.set_overflow(Gtk.Overflow.HIDDEN)  # clip rows to the rounded corners
        table.append(header)
        table.append(Gtk.Separator())
        table.append(scroll)
        return table

    def _build_list_view(self) -> Gtk.ListView:
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_row_setup)
        factory.connect("bind", self._on_row_bind)
        view = Gtk.ListView(model=self.selection_model, factory=factory, show_separators=True)
        view.add_css_class("file-rows")
        return view

    def _on_row_setup(self, _factory, list_item: Gtk.ListItem) -> None:
        row = Gtk.Box(spacing=0)
        row.add_css_class("file-row")

        check = self._make_check(list_item)
        check.set_size_request(_WIDTHS["check"], -1)
        row.append(check)

        icon_slot = Gtk.Box(width_request=_WIDTHS["icon"], halign=Gtk.Align.START)
        row.append(icon_slot)

        name = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE)
        name.add_css_class("file-name")
        row.append(name)

        badge_slot = Gtk.Box(width_request=_WIDTHS["folder"])
        row.append(badge_slot)

        size = Gtk.Label(xalign=0, width_request=_WIDTHS["size"])
        size.add_css_class("numeric")
        row.append(size)

        modified = Gtk.Label(xalign=0, width_request=_WIDTHS["modified"])
        modified.add_css_class("dim-label")
        modified.add_css_class("numeric")
        row.append(modified)

        menu = Gtk.MenuButton(icon_name="view-more-symbolic", valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        menu.add_css_class("row-menu")
        menu.set_size_request(_WIDTHS["actions"], -1)
        row.append(menu)

        modified.set_visible(not self._compact)
        row.widgets = (icon_slot, name, badge_slot, size, modified, menu)
        self._row_widgets.append(row)
        list_item.set_child(row)

    def _on_row_bind(self, _factory, list_item: Gtk.ListItem) -> None:
        item = list_item.get_item()
        icon_slot, name, badge_slot, size, modified, menu = list_item.get_child().widgets
        _replace_child(icon_slot, file_icon(item))
        _replace_child(badge_slot, distro_badge(item.folder))
        name.set_text(item.name)
        name.set_tooltip_text(item.name)
        size.set_text(item.size_formatted)
        modified.set_text(format_date(item))
        menu.set_menu_model(row_menu(item.key))
        menu.set_tooltip_text(_("Actions"))
        list_item.get_child().get_first_child().update_property([Gtk.AccessibleProperty.LABEL], [item.name])

    # Grid view

    def _build_grid_view(self) -> Gtk.GridView:
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_card_setup)
        factory.connect("bind", self._on_card_bind)
        view = Gtk.GridView(model=self.selection_model, factory=factory, min_columns=2, max_columns=6)
        view.add_css_class("file-cards")
        return view

    def _on_card_setup(self, _factory, list_item: Gtk.ListItem) -> None:
        check = self._make_check(list_item)
        menu = Gtk.MenuButton(icon_name="view-more-symbolic", halign=Gtk.Align.END, hexpand=True)
        menu.add_css_class("row-menu")
        top = Gtk.Box()
        top.append(check)
        top.append(menu)

        # The icon area takes the spare height, so content stays centered in the square
        icon_slot = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, vexpand=True, margin_bottom=4)
        name = Gtk.Label(wrap=True, lines=2, ellipsize=Pango.EllipsizeMode.END, justify=Gtk.Justification.CENTER)
        name.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        name.set_max_width_chars(22)
        name.add_css_class("file-name")

        badge_slot = Gtk.Box()
        size = Gtk.Label(hexpand=True, xalign=1)
        size.add_css_class("numeric")
        meta = Gtk.Box(spacing=6, margin_top=6)
        meta.append(badge_slot)
        meta.append(size)

        modified = Gtk.Label(xalign=0)
        modified.add_css_class("dim-label")
        modified.add_css_class("caption")

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("file-card")
        for widget in (top, icon_slot, name, meta, modified):
            card.append(widget)
        card.widgets = (icon_slot, name, badge_slot, size, modified, menu)
        list_item.set_child(SquareBin(card))

    def _on_card_bind(self, _factory, list_item: Gtk.ListItem) -> None:
        item = list_item.get_item()
        icon_slot, name, badge_slot, size, modified, menu = list_item.get_child().child.widgets
        _replace_child(icon_slot, file_icon(item, pixel_size=32))
        _replace_child(badge_slot, distro_badge(item.folder))
        name.set_text(item.name)
        name.set_tooltip_text(item.name)
        size.set_text(item.size_formatted)
        modified.set_text(format_date(item))
        menu.set_menu_model(row_menu(item.key))

    # Selection

    def _make_check(self, list_item: Gtk.ListItem) -> Gtk.CheckButton:
        check = Gtk.CheckButton(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, tooltip_text=_("Select"))
        # The check box shows the item's selection state and clicking it adds/removes
        # that item without touching the others
        list_item.bind_property("selected", check, "active", GObject.BindingFlags.SYNC_CREATE)
        check.connect("toggled", self._on_check_toggled, list_item)
        return check

    def _on_check_toggled(self, check: Gtk.CheckButton, list_item: Gtk.ListItem) -> None:
        position = list_item.get_position()
        if position == Gtk.INVALID_LIST_POSITION or check.get_active() == list_item.get_selected():
            return
        if check.get_active():
            self.selection_model.select_item(position, False)
        else:
            self.selection_model.unselect_item(position)

    def _on_header_check_toggled(self, check: Gtk.CheckButton) -> None:
        if self._updating_header:
            return
        if check.get_active() and self.selected_count < self.visible_count:
            self.select_all()
        else:
            self.unselect_all()

    def _selection_changed(self) -> None:
        count = self.selected_count
        self._updating_header = True
        self.header_check.set_inconsistent(0 < count < self.visible_count)
        self.header_check.set_active(count > 0 and count == self.visible_count)
        self._updating_header = False
        self._on_selection_changed(count)

    @property
    def selected_count(self) -> int:
        return self.selection_model.get_selection().get_size()

    @property
    def visible_count(self) -> int:
        return self.sort_model.get_n_items()

    def get_selected_files(self) -> List[FileItem]:
        """Selected files, in display order."""
        selection = self.selection_model.get_selection()
        return [self.sort_model.get_item(selection.get_nth(i)) for i in range(selection.get_size())]

    def select_all(self) -> None:
        self.selection_model.select_all()

    def unselect_all(self) -> None:
        self.selection_model.unselect_all()

    # Data, filtering and sorting

    def set_files(self, files: List[dict]) -> None:
        """Replace every file, keeping the selection (by key) of files that still exist."""
        selected_keys = {item.key for item in self.get_selected_files()}
        self.store.splice(0, self.store.get_n_items(), [FileItem.from_dict(data) for data in files])
        if selected_keys:
            keep = Gtk.Bitset.new_empty()
            for position in range(self.sort_model.get_n_items()):
                if self.sort_model.get_item(position).key in selected_keys:
                    keep.add(position)
            self.selection_model.set_selection(keep, keep)
        self._selection_changed()

    def all_files(self) -> List[FileItem]:
        return [self.store.get_item(i) for i in range(self.store.get_n_items())]

    def find(self, key: str) -> Optional[FileItem]:
        return next((item for item in self.all_files() if item.key == key), None)

    @property
    def total_count(self) -> int:
        return self.store.get_n_items()

    def set_folder(self, folder: Optional[str]) -> None:
        self._folder = folder
        self._filter.changed(Gtk.FilterChange.DIFFERENT)

    def set_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self._filter.changed(Gtk.FilterChange.DIFFERENT)

    def _matches(self, item: FileItem) -> bool:
        if self._folder and item.folder != self._folder:
            return False
        return not self._search or self._search in item.name.lower()

    def set_sort(self, key: str) -> None:
        """Sort by key; choosing the current key again reverses the order."""
        if key == self.sort_key:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_key = key
            self.sort_descending = key in ("size", "modified")  # biggest / newest first
        self._sorter.changed(Gtk.SorterChange.DIFFERENT)
        self._update_sort_arrows()

    def _compare(self, a: FileItem, b: FileItem, _data=None) -> int:
        values = {
            "name": lambda item: item.name.lower(),
            "folder": lambda item: (item.folder.lower(), item.name.lower()),
            "size": lambda item: item.size,
            "modified": lambda item: item.modified,
        }[self.sort_key]
        first, second = values(a), values(b)
        result = (first > second) - (first < second)
        return -result if self.sort_descending else result

    def _update_sort_arrows(self) -> None:
        for key, button in self.sort_buttons.items():
            if key == self.sort_key:
                button.arrow.set_from_icon_name("pan-down-symbolic" if self.sort_descending else "pan-up-symbolic")
                button.add_css_class("sorted")
            else:
                button.arrow.set_from_icon_name(None)
                button.remove_css_class("sorted")

    # Views

    def set_compact(self, compact: bool) -> None:
        """Narrow windows: hide the "Modified" column so file names keep their room."""
        self._compact = compact
        self.sort_buttons["modified"].set_visible(not compact)
        for row in self._row_widgets:
            row.widgets[4].set_visible(not compact)

    def set_view(self, view: str) -> None:
        """Show the "list" or the "grid" view."""
        self._view = view
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        if self.filter_model.get_n_items() > 0:
            self.stack.set_visible_child_name(self._view)
            return
        if self._search:
            self.empty_page.set_icon_name("system-search-symbolic")
            self.empty_page.set_title(_("No results"))
            self.empty_page.set_description(_("No file matches “{text}”").format(text=self._search))
        else:
            self.empty_page.set_icon_name("folder-symbolic")
            self.empty_page.set_title(_("No files"))
            self.empty_page.set_description(_("Upload an ISO to get started"))
        self.stack.set_visible_child_name("empty")


def _replace_child(box: Gtk.Box, widget: Gtk.Widget) -> None:
    child = box.get_first_child()
    if child is not None:
        box.remove(child)
    box.append(widget)
