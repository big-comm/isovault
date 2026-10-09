"""
GTK tests for the main window and preferences, with a fake S3 service.

Skipped automatically when no display is available.
"""

import os
import subprocess
import sys
import threading
import time

import pytest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

if not Gtk.init_check():
    pytest.skip("no display available", allow_module_level=True)
Adw.init()

import ui.preferences as preferences_module  # noqa: E402
import ui.window as window_module  # noqa: E402
from models.settings import SettingsManager  # noqa: E402
from tests.factories import make_file  # noqa: E402

APP_MAIN = os.path.join(os.path.dirname(__file__), "..", "usr", "share", "isovault", "main.py")


def wait_until(condition, timeout=5.0):
    """Run the GTK main loop until condition() is true."""
    deadline = time.monotonic() + timeout
    context = GLib.MainContext.default()
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for condition")
        context.iteration(False)
        time.sleep(0.005)


class FakeS3:
    instances = []

    def __init__(self, s3_config, base_url=""):
        self.config = s3_config
        self.base_url = base_url
        self.files = [make_file("Gnome/a.iso"), make_file("b.iso")]
        self.uploaded = []
        self.deleted = []
        self.list_calls = []
        self.fail_uploads = set()
        self.fail_deletes = set()
        self.list_error = None
        FakeS3.instances.append(self)

    def list_files(self, folder=None, include_index=False):
        self.list_calls.append((folder, include_index))
        if self.list_error:
            raise self.list_error
        return [f for f in self.files if folder is None or f["folder"] == folder]

    def upload_file(self, path, folder, progress_callback=None):
        if os.path.basename(path) in self.fail_uploads:
            raise RuntimeError("upload refused")
        for percent in (50, 100):
            progress_callback(percent)
        self.uploaded.append((os.path.basename(path), folder))

    def delete_file(self, key):
        if key in self.fail_deletes:
            raise RuntimeError("delete refused")
        self.deleted.append(key)

    def download_file(self, key, path, progress_callback=None):
        with open(path, "w") as f:
            f.write(key)
        progress_callback(100)

    def get_public_url(self, key):
        return f"{self.base_url}/{key}"


@pytest.fixture
def settings(tmp_path):
    manager = SettingsManager(str(tmp_path / "isovault.conf"))
    manager.set("s3", "access_key", "AK")
    manager.set("s3", "secret_key", "SK")
    manager.save_settings()
    return manager


@pytest.fixture
def published(monkeypatch):
    calls = []
    monkeypatch.setattr(window_module, "publish_indexes", lambda service, generator: calls.append(service) or [])
    return calls


@pytest.fixture
def window(monkeypatch, settings, published):
    FakeS3.instances = []
    monkeypatch.setattr(window_module, "S3Service", FakeS3)
    monkeypatch.setattr(window_module, "SettingsManager", lambda: settings)

    win = window_module.ISOVaultWindow()
    win.toasts = []
    monkeypatch.setattr(win, "show_toast", win.toasts.append)
    wait_until(lambda: win.file_list.file_model.get_n_items() == 2)
    yield win
    win.destroy()


def idle(win):
    wait_until(lambda: not win._busy)


class TestStartup:
    def test_loads_files(self, window):
        assert window.status_label.get_text() == "2 files"
        assert window.upload_button.get_sensitive()
        assert len(FakeS3.instances) == 1

    def test_without_credentials(self, monkeypatch, tmp_path, published):
        monkeypatch.setattr(window_module, "S3Service", FakeS3)
        monkeypatch.setattr(window_module, "SettingsManager", lambda: SettingsManager(str(tmp_path / "x.conf")))
        FakeS3.instances = []

        win = window_module.ISOVaultWindow()
        try:
            assert win.s3_service is None
            assert FakeS3.instances == []
            assert not win.upload_button.get_sensitive()
            assert not win.lookup_action("force-index").get_enabled()
        finally:
            win.destroy()

    def test_folder_filter(self, window):
        window.folder_dropdown.set_selected(window_module.DISTRO_FOLDERS.index("Gnome") + 1)
        wait_until(lambda: window.file_list.file_model.get_n_items() == 1)
        assert window.status_label.get_text() == "1 file in Gnome"

    def test_refresh_error_is_reported(self, window):
        window.s3_service.list_error = RuntimeError("offline")
        window.refresh_files()
        wait_until(lambda: window.toasts)
        assert "offline" in window.toasts[-1]


class TestOperations:
    def _files(self, tmp_path, *names):
        paths = []
        for name in names:
            path = tmp_path / name
            path.write_bytes(b"\0" * 10)
            paths.append(str(path))
        return paths

    def test_batch_upload_continues_after_failure(self, window, tmp_path, published):
        window.s3_service.fail_uploads = {"bad.iso"}
        window._upload_files(self._files(tmp_path, "a.iso", "bad.iso", "c.iso"), "XFCE")
        idle(window)

        assert window.s3_service.uploaded == [("a.iso", "XFCE"), ("c.iso", "XFCE")]
        assert window.toasts[-1] == "Upload complete: 2 successful, 1 failed"
        assert published == [window.s3_service]  # auto update index
        assert not window.progress_manager.is_visible

    def test_failed_single_upload_does_not_publish(self, window, tmp_path, published):
        window.s3_service.fail_uploads = {"bad.iso"}
        window._upload_files(self._files(tmp_path, "bad.iso"), "XFCE")
        idle(window)

        assert "upload refused" in window.toasts[-1]
        assert published == []

    def test_only_one_operation_at_a_time(self, window):
        release = threading.Event()
        window._start_operation("busy", release.wait, lambda _r: None, "error")
        assert window._busy
        assert not window.upload_button.get_sensitive()

        window._start_operation("second", lambda: None, lambda _r: None, "error")
        assert window.toasts[-1] == "Another operation is in progress"

        release.set()
        idle(window)
        assert window.upload_button.get_sensitive()

    def test_operation_error_is_shown(self, window):
        def boom():
            raise RuntimeError("kaput")

        window._start_operation("x", boom, lambda _r: None, "It failed")
        idle(window)
        assert window.toasts[-1] == "It failed: kaput"

    def test_manual_index_update_reports_success(self, window, published):
        window.activate_action("win.force-index", None)
        idle(window)
        assert window.toasts[-1] == "Index files updated!"

    def test_stale_refresh_is_ignored(self, window):
        """A slow, older listing that finishes last must not replace the newer one."""
        service = window.s3_service
        release, stale_returned = threading.Event(), threading.Event()
        original = service.list_files
        calls = []

        def first_call_slow(folder=None, include_index=False):
            calls.append(folder)
            if len(calls) == 1:
                release.wait()
                stale_returned.set()
                return [make_file("stale.iso")]
            return original(folder, include_index)

        service.list_files = first_call_slow
        window.refresh_files()  # older request, blocks in its worker
        window.refresh_files()  # newer request, returns at once
        wait_until(lambda: len(calls) == 2 and window.status_label.get_text() == "2 files")

        release.set()  # now the older one finishes
        wait_until(stale_returned.is_set)
        time.sleep(0.05)
        wait_until(lambda: not GLib.MainContext.default().pending())

        model = window.file_list.file_model
        names = [model.get_item(i).name for i in range(model.get_n_items())]
        assert names == ["a.iso", "b.iso"]
        assert window.status_label.get_text() == "2 files"


def row_check_boxes(win):
    """Check buttons of the visible rows, top to bottom."""
    found, stack = [], [win.file_list.column_view]
    while stack:
        widget = stack.pop(0)
        if isinstance(widget, Gtk.CheckButton):
            found.append(widget)
        child = widget.get_first_child()
        while child is not None:
            stack.append(child)
            child = child.get_next_sibling()
    return found


def file_names(win):
    return [item.name for item in win.file_list.get_selected_files()]


class TestSelection:
    def test_nothing_selected_at_start(self, window):
        assert window.file_list.selected_count == 0
        assert window.selection_group.get_description() == "No files selected"
        assert not window.delete_row.get_sensitive()
        assert not window.select_none_button.get_sensitive()
        assert window.select_all_button.get_sensitive()

    def test_select_all_and_none(self, window):
        window.select_all_button.emit("clicked")
        assert file_names(window) == ["a.iso", "b.iso"]
        assert window.selection_group.get_description() == "2 of 2 files selected"
        assert window.delete_row.get_sensitive()
        assert not window.select_all_button.get_sensitive()

        window.select_none_button.emit("clicked")
        assert window.file_list.selected_count == 0
        assert not window.delete_row.get_sensitive()

    def test_check_boxes_follow_and_drive_selection(self, window):
        window.present()
        wait_until(lambda: len(row_check_boxes(window)) == 2)
        checks = dict(zip(["a.iso", "b.iso"], row_check_boxes(window)))  # rows are in list order

        checks["a.iso"].set_active(True)
        checks["b.iso"].set_active(True)  # adds to the selection instead of replacing it
        assert file_names(window) == ["a.iso", "b.iso"]

        checks["a.iso"].set_active(False)
        assert file_names(window) == ["b.iso"]

        window.file_list.select_all()
        assert all(check.get_active() for check in checks.values())
        window.file_list.unselect_all()
        assert not any(check.get_active() for check in checks.values())

    def test_selection_survives_refresh(self, window):
        window.file_list.selection_model.select_item(1, True)
        assert file_names(window) == ["b.iso"]

        window.s3_service.files.insert(0, make_file("XFCE/new.iso"))
        window.refresh_files()
        wait_until(lambda: window.file_list.file_model.get_n_items() == 3)

        assert file_names(window) == ["b.iso"]


class TestBatchActions:
    def test_delete_several_without_confirmation(self, window, settings, published):
        settings.set("ui", "confirm_deletions", False)
        window.file_list.select_all()

        window.on_delete_clicked()
        idle(window)

        assert window.s3_service.deleted == ["Gnome/a.iso", "b.iso"]
        assert window.toasts[-1] == "Successfully deleted all 2 files!"
        assert published == [window.s3_service]  # index updated once

    def test_delete_asks_once_for_all_files(self, window, monkeypatch):
        asked = []
        monkeypatch.setattr(window.dialogs, "confirm_delete", lambda items, callback: asked.append(items))
        window.file_list.select_all()

        window.on_delete_clicked()

        assert [[item.name for item in items] for items in asked] == [["a.iso", "b.iso"]]
        assert window.s3_service.deleted == []

    def test_delete_partial_failure(self, window, settings, published):
        settings.set("ui", "confirm_deletions", False)
        window.s3_service.fail_deletes = {"b.iso"}
        window.file_list.select_all()

        window.on_delete_clicked()
        idle(window)

        assert window.s3_service.deleted == ["Gnome/a.iso"]
        assert window.toasts[-1] == "Delete complete: 1 successful, 1 failed"
        assert published == [window.s3_service]

    def test_copy_several_links(self, window, monkeypatch):
        copied = []
        monkeypatch.setattr(window, "get_clipboard", lambda: type("Clip", (), {"set": lambda _self, text: copied.append(text)})())
        window.s3_service.base_url = "https://cdn"
        window.file_list.select_all()

        window.on_copy_link_clicked()

        assert copied == ["https://cdn/Gnome/a.iso\nhttps://cdn/b.iso"]
        assert window.toasts[-1] == "2 links copied"

    def test_download_several_into_folder(self, window, monkeypatch, tmp_path):
        (tmp_path / "b.iso").write_text("keep me")
        monkeypatch.setattr(window.dialogs, "choose_download_folder", lambda callback: callback(str(tmp_path)))
        window.file_list.select_all()

        window.on_download_clicked()
        idle(window)

        assert (tmp_path / "a.iso").read_text() == "Gnome/a.iso"
        assert (tmp_path / "b.iso").read_text() == "keep me"  # never overwritten
        assert window.toasts[-1] == "Download complete: 1 successful, 1 failed"

    def test_download_single_uses_save_dialog(self, window, monkeypatch, tmp_path):
        target = tmp_path / "chosen.iso"
        target.write_text("old")  # the save dialog already confirmed overwriting
        monkeypatch.setattr(window.dialogs, "choose_download_path", lambda name, callback: callback(str(target)))
        window.file_list.selection_model.select_item(0, True)

        window.on_download_clicked()
        idle(window)

        assert target.read_text() == "Gnome/a.iso"
        assert window.toasts[-1] == "Successfully downloaded a.iso"


class TestSettings:
    def test_s3_change_recreates_service(self, window, settings):
        old = window.s3_service
        settings.set("s3", "bucket_name", "other")
        window._on_settings_changed(s3_changed=True)
        wait_until(lambda: window.s3_service is not old)
        assert window.s3_service.config["bucket_name"] == "other"

    def test_base_url_change_updates_service(self, window, settings):
        service = window.s3_service
        settings.set("web", "base_url", "https://new.example/")
        window._on_settings_changed(s3_changed=False)
        assert window.s3_service is service
        assert service.base_url == "https://new.example"

    def test_quick_toggles_follow_reset(self, window, settings):
        row = window.quick_setting_rows[("ui", "confirm_deletions")]
        row.set_active(False)
        assert settings.get("ui", "confirm_deletions") is False

        settings.reset_to_defaults()
        window._on_settings_changed(s3_changed=False)
        assert row.get_active() is True

    def test_close_saves_window_size(self, window, settings):
        window.set_default_size(900, 640)
        window._on_close_request(window)
        reloaded = SettingsManager(settings.config_file)
        assert reloaded.get_window_size() == (900, 640)


class TestUploadDialog:
    def _dialog(self, tmp_path, initial=None, invalid=()):
        from ui.upload_dialog import UploadDialog

        paths = []
        for name, size in (("a.iso", 2048), ("a.iso.md5", 70)):
            (tmp_path / name).write_bytes(b"\0" * size)
            paths.append(str(tmp_path / name))
        chosen = []
        return UploadDialog(paths, list(invalid), chosen.append, initial), chosen

    def test_preselects_last_folder(self, tmp_path):
        dialog, _chosen = self._dialog(tmp_path, initial="XFCE")
        assert dialog.selected_folder == "XFCE"
        assert dialog.upload_button.get_label() == "Upload to XFCE"

    def test_unknown_initial_folder_falls_back(self, tmp_path):
        dialog, _chosen = self._dialog(tmp_path, initial="gone")
        assert dialog.selected_folder == window_module.DISTRO_FOLDERS[0]

    def test_folders_are_exclusive(self, tmp_path):
        dialog, _chosen = self._dialog(tmp_path, initial="XFCE")
        dialog.folder_buttons["Root"].set_active(True)
        assert [f for f, b in dialog.folder_buttons.items() if b.get_active()] == ["Root"]
        assert dialog.upload_button.get_label() == "Upload to Root"

    def test_upload_returns_chosen_folder(self, tmp_path):
        dialog, chosen = self._dialog(tmp_path, initial="Gnome")
        dialog.folder_buttons["Cinnamon"].set_active(True)
        dialog.upload_button.emit("clicked")
        assert chosen == ["Cinnamon"]

    def test_cancel_uploads_nothing(self, tmp_path):
        dialog, chosen = self._dialog(tmp_path)
        dialog.close()
        assert chosen == []

    def test_window_remembers_folder(self, window, tmp_path, settings, monkeypatch):
        path = tmp_path / "new.iso"
        path.write_bytes(b"\0")
        shown = []
        monkeypatch.setattr(window.dialogs, "choose_upload_folder", lambda valid, invalid, cb, initial: shown.append((initial, cb)))

        window._on_files_chosen([str(path)], str(tmp_path))
        initial, upload = shown[0]
        assert initial == ""
        upload("XFCE")
        idle(window)

        assert settings.get("general", "last_upload_folder") == "XFCE"
        assert window.s3_service.uploaded == [("new.iso", "XFCE")]
        window._on_files_chosen([str(path)], str(tmp_path))
        assert shown[1][0] == "XFCE"


class TestDeleteDialog:
    def _dialog(self, *keys):
        from models import FileItem
        from ui.delete_dialog import DeleteDialog

        items = [FileItem.from_dict(make_file(key, size=1024**3)) for key in keys]
        confirmed = []
        return DeleteDialog(items, lambda: confirmed.append(True)), confirmed

    def test_labels_for_several_files(self):
        dialog, _confirmed = self._dialog("Gnome/a.iso", "Gnome/a.iso.md5", "b.iso")
        assert dialog.get_title() == "Delete Files"
        assert dialog.delete_button.get_label() == "Delete 3 files"

    def test_labels_for_one_file(self):
        dialog, _confirmed = self._dialog("b.iso")
        assert dialog.get_title() == "Delete File"
        assert dialog.delete_button.get_label() == "Delete 1 file"

    def test_lists_name_folder_and_size(self):
        dialog, _confirmed = self._dialog("XFCE/x.iso")
        rows = [w for w in _walk(dialog.get_child()) if isinstance(w, Adw.ActionRow)]
        assert [(r.get_title(), r.get_subtitle()) for r in rows] == [("x.iso", "XFCE · 1.0 GB")]

    def test_enter_does_not_delete(self):
        dialog, _confirmed = self._dialog("b.iso")
        assert dialog.get_default_widget() is dialog.cancel_button

    def test_confirm_and_cancel(self):
        dialog, confirmed = self._dialog("b.iso")
        dialog.cancel_button.emit("clicked")
        assert confirmed == []

        dialog, confirmed = self._dialog("b.iso")
        dialog.delete_button.emit("clicked")
        assert confirmed == [True]


def _walk(widget):
    stack = [widget]
    while stack:
        current = stack.pop(0)
        yield current
        child = current.get_first_child()
        while child is not None:
            stack.append(child)
            child = child.get_next_sibling()


class TestPreferences:
    def test_text_fields_apply_on_close(self, settings):
        changes = []
        dialog = preferences_module.PreferencesDialog(settings, changes.append)
        dialog.s3_rows["bucket_name"].set_text("  new-bucket ")
        dialog.web_rows["base_url"].set_text("https://example.org")

        assert settings.get("s3", "bucket_name") != "new-bucket"  # nothing saved while typing
        dialog._on_closed(dialog)

        assert changes == [True]
        assert SettingsManager(settings.config_file).get("s3", "bucket_name") == "new-bucket"
        assert settings.get("web", "base_url") == "https://example.org"

    def test_close_without_changes_is_silent(self, settings):
        changes = []
        dialog = preferences_module.PreferencesDialog(settings, changes.append)
        dialog._on_closed(dialog)
        assert changes == []

    def test_connection_test_uses_typed_values(self, settings, monkeypatch):
        seen = []

        class Probe:
            def __init__(self, config):
                seen.append(config)

            def check_connection(self):
                raise RuntimeError("denied")

        monkeypatch.setattr(preferences_module, "S3Service", Probe)
        results = []
        dialog = preferences_module.PreferencesDialog(settings, lambda _changed: None)
        monkeypatch.setattr(dialog, "_show_test_result", lambda ok, msg: results.append((ok, msg)))
        dialog.s3_rows["access_key"].set_text("TYPED")

        dialog._on_test_connection(dialog.test_button)
        wait_until(lambda: results)

        assert seen[0]["access_key"] == "TYPED"
        assert settings.get("s3", "access_key") == "AK"  # not saved by the test
        assert results[0][0] is False and "denied" in results[0][1]


def test_version_option():
    result = subprocess.run(
        [sys.executable, APP_MAIN, "--version"], capture_output=True, text=True, timeout=30, check=True
    )
    assert result.stdout.strip() == "ISOVault 1.0.0"
