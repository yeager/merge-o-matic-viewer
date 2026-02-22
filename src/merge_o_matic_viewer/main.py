"""Merge-o-Matic Viewer — Visual merge helper for Ubuntu-Debian synchronization."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, Pango

import gettext
import locale
import os
import sys
import json
import datetime
import threading
import subprocess
import re

LOCALE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "po")
if not os.path.isdir(LOCALE_DIR):
    LOCALE_DIR = "/usr/share/locale"
locale.bindtextdomain("merge-o-matic-viewer", LOCALE_DIR)
gettext.bindtextdomain("merge-o-matic-viewer", LOCALE_DIR)
gettext.textdomain("merge-o-matic-viewer")
_ = gettext.gettext

APP_ID = "se.danielnylander.merge.o.matic.viewer"
SETTINGS_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "merge-o-matic-viewer"
)
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


def _load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {"welcome_shown": False}


def _save_settings(s):
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)





class MergeOMaticViewerWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("Merge-o-Matic Viewer"), default_width=1100, default_height=750)
        self.settings = _load_settings()
        self._merges = []

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header
        headerbar = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title=_("Merge-o-Matic Viewer"), subtitle="")
        headerbar.set_title_widget(title_widget)
        self._title_widget = title_widget

        
        open_btn = Gtk.Button(icon_name="document-open-symbolic", tooltip_text=_("Open merge report"))
        open_btn.connect("clicked", self._on_open)
        headerbar.pack_start(open_btn)

        # Menu
        menu = Gio.Menu()
        menu.append(_("Settings"), "app.settings")
        menu.append(_("Copy Debug Info"), "app.copy-debug")
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About Merge-o-Matic Viewer"), "app.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        headerbar.pack_end(menu_btn)

        main_box.append(headerbar)

        
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        
        # Left: merge list
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_size_request(350, -1)
        self._merge_list = Gtk.ListBox()
        self._merge_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._merge_list.add_css_class("boxed-list")
        self._merge_list.set_margin_start(8)
        self._merge_list.set_margin_end(8)
        self._merge_list.connect("row-selected", self._on_merge_selected)
        left_scroll.set_child(self._merge_list)
        paned.set_start_child(left_scroll)
        
        # Right: diff view
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right_box.set_margin_start(8)
        right_box.set_margin_end(8)
        
        self._diff_header = Gtk.Label(label="", xalign=0)
        self._diff_header.add_css_class("heading")
        self._diff_header.set_margin_top(8)
        right_box.append(self._diff_header)
        
        diff_scroll = Gtk.ScrolledWindow(vexpand=True)
        self._diff_view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self._diff_view.set_top_margin(8)
        self._diff_view.set_left_margin(8)
        diff_scroll.set_child(self._diff_view)
        right_box.append(diff_scroll)
        
        paned.set_end_child(right_box)
        paned.set_position(380)
        
        main_box.append(paned)

        # Status bar
        self._status = Gtk.Label(label=_("Ready"), xalign=0)
        self._status.set_margin_start(12)
        self._status.set_margin_end(12)
        self._status.set_margin_top(4)
        self._status.set_margin_bottom(4)
        self._status.add_css_class("dim-label")
        main_box.append(self._status)

        self.set_content(main_box)

        if not self.settings.get("welcome_shown"):
            GLib.idle_add(self._show_welcome)

    def _show_welcome(self):
        dialog = Adw.Dialog()
        dialog.set_title(_("Welcome"))
        dialog.set_content_width(420)
        dialog.set_content_height(480)

        page = Adw.StatusPage()
        page.set_icon_name("document-page-setup-symbolic")
        page.set_title(_("Welcome to Merge-o-Matic Viewer"))
        page.set_description(_("Simplify Ubuntu-Debian merges.\n\n"
            "✓ View merge conflicts visually\n"
            "✓ Side-by-side Ubuntu vs Debian comparison\n"
            "✓ changelog diff highlighting\n"
            "✓ Suggest automatic resolutions\n"
            "✓ Export merge patches"))

        btn = Gtk.Button(label=_("Get Started"))
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(12)
        btn.connect("clicked", self._on_welcome_close, dialog)
        page.set_child(btn)

        box = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_show_title(False)
        box.add_top_bar(hb)
        box.set_content(page)
        dialog.set_child(box)
        dialog.present(self)

    def _on_welcome_close(self, btn, dialog):
        self.settings["welcome_shown"] = True
        _save_settings(self.settings)
        dialog.close()

    
    def _on_open(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Open merge report or .dsc file"))
        dialog.open(self, None, self._on_file_opened)

    def _on_file_opened(self, dialog, result):
        try:
            f = dialog.open_finish(result)
            path = f.get_path()
            self._load_merge(path)
        except:
            pass

    def _load_merge(self, path):
        with open(path) as f:
            content = f.read()
        
        # Parse as a diff/merge report
        sections = content.split("\n--- ")
        self._merges = []
        
        for section in sections:
            lines = section.splitlines()
            if lines:
                self._merges.append({"title": lines[0][:80], "content": section})
        
        while True:
            row = self._merge_list.get_row_at_index(0)
            if row is None:
                break
            self._merge_list.remove(row)
        
        for i, m in enumerate(self._merges):
            row = Adw.ActionRow()
            row.set_title(m["title"])
            row._merge_idx = i
            self._merge_list.append(row)
        
        self._title_widget.set_subtitle(os.path.basename(path))
        self._status.set_text(_("Loaded %(count)d sections from %(file)s") %
                            {"count": len(self._merges), "file": os.path.basename(path)})

    def _on_merge_selected(self, listbox, row):
        if row is None:
            return
        merge = self._merges[row._merge_idx]
        self._diff_header.set_text(merge["title"])
        self._diff_view.get_buffer().set_text(merge["content"])


class MergeOMaticViewerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None

        for name, callback in [
            ("settings", self._on_settings),
            ("copy-debug", self._on_copy_debug),
            ("shortcuts", self._on_shortcuts),
            ("about", self._on_about),
            ("quit", self._on_quit),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        self.set_accels_for_action("app.shortcuts", ["<Ctrl>slash"])

    def do_activate(self):
        if not self.window:
            self.window = MergeOMaticViewerWindow(self)
        self.window.present()

    def _on_settings(self, *_args):
        if not self.window:
            return
        dialog = Adw.PreferencesDialog()
        dialog.set_title(_("Settings"))
        page = Adw.PreferencesPage()
        
        group = Adw.PreferencesGroup(title=_("Display"))
        row = Adw.SwitchRow(title=_("Show context lines"))
        row.set_active(True)
        group.add(row)
        page.add(group)
        dialog.add(page)
        dialog.present(self.window)

    def _on_copy_debug(self, *_args):
        if not self.window:
            return
        from . import __version__
        info = (
            f"Merge-o-Matic Viewer {__version__}\n"
            f"Python {sys.version}\n"
            f"GTK {Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}\n"
            f"Adw {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}\n"
            f"OS: {os.uname().sysname} {os.uname().release}\n"
        )
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(info)
        self.window._status.set_text(_("Debug info copied"))

    def _on_shortcuts(self, *_args):
        if self.window:
            dialog = Gtk.ShortcutsWindow(transient_for=self.window)
            section = Gtk.ShortcutsSection(visible=True)
            group = Gtk.ShortcutsGroup(title=_("General"), visible=True)
            for accel, title in [
                ("<Ctrl>q", _("Quit")),
                ("<Ctrl>slash", _("Keyboard shortcuts")),
            ]:
                group.append(Gtk.ShortcutsShortcut(accelerator=accel, title=title, visible=True))
            section.append(group)
            dialog.append(section)
            dialog.present()

    def _on_about(self, *_args):
        from . import __version__
        dialog = Adw.AboutDialog(
            application_name=_("Merge-o-Matic Viewer"),
            application_icon="document-page-setup-symbolic",
            version=__version__,
            developer_name="Daniel Nylander",
            website="https://github.com/yeager/merge-o-matic-viewer",
            license_type=Gtk.License.GPL_3_0,
            issue_url="https://github.com/yeager/merge-o-matic-viewer/issues",
            comments=_("Visual merge helper for Ubuntu-Debian package synchronization with conflict resolution."),
        )
        dialog.present(self.window)

    def _on_quit(self, *_args):
        self.quit()


def main():
    app = MergeOMaticViewerApp()
    app.run(sys.argv)
