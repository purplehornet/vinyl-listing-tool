import importlib.util, sys
from tkinter import Tk
from pathlib import Path as _Path

APP_PATH = "VinylTool_BETA1__PROFILE_PATCH_v5.py"

spec = importlib.util.spec_from_file_location("vinyltool_app", APP_PATH)
mod = importlib.util.module_from_spec(spec)
# Fix AutoBackup quirks up front
if not hasattr(mod, "__file__"):
    mod.__file__ = _Path(APP_PATH).resolve().as_posix()
if not hasattr(mod, "_Path"):
    mod._Path = _Path

sys.modules["vinyltool_app"] = mod
spec.loader.exec_module(mod)

# ---- Monkey-patch async Discogs handlers onto the class (if missing) ----
App = getattr(mod, "VinylToolApp", None)
if App is None:
    raise SystemExit("VinylToolApp not found")

def _gd_search_discogs(self):
    from tkinter import messagebox
    from vinyltool.core.async_utils import run_bg
    artist = self.entries.get("artist").get().strip() if "artist" in self.entries else ""
    title  = self.entries.get("title").get().strip()  if "title"  in self.entries else ""
    if not artist and not title:
        messagebox.showwarning("Input Required", "Please enter artist and/or title")
        return
    params = {"per_page": 100, "type": "release"}
    if artist: params["artist"] = artist
    if title:  params["release_title"] = title
    def do_work():
        return self.discogs_api.search(params)
    def ok(results):
        self.display_discogs_results(results)
    def err(exc, tb):
        if getattr(self, "logger", None):
            self.logger.error("Discogs search failed: %s\n%s", exc, tb)
        messagebox.showerror("Search Error", str(exc))
    run_bg(self.root, do_work, ok, err, name="discogs-search")

def _gd_apply_selected_discogs(self):
    from tkinter import messagebox
    from vinyltool.core.async_utils import run_bg
    selected = self.get_selected_discogs_result() if hasattr(self, "get_selected_discogs_result") else None
    if not selected:
        messagebox.showwarning("No selection", "Please select a Discogs result first.")
        return
    release_id = selected.get("id") or selected.get("release_id") or selected.get("master_id")
    if not release_id:
        messagebox.showwarning("Missing ID", "The selected entry has no Discogs ID.")
        return
    def do_work():
        return self.discogs_api.fetch_release_details(release_id)
    def ok(details):
        self.populate_fields_from_discogs(details)
    def err(exc, tb):
        if getattr(self, "logger", None):
            self.logger.error("Discogs details fetch failed: %s\n%s", exc, tb)
        messagebox.showerror("Discogs Error", str(exc))
    run_bg(self.root, do_work, ok, err, name="discogs-apply")

if not hasattr(App, "search_discogs"):
    App.search_discogs = _gd_search_discogs
if not hasattr(App, "apply_selected_discogs"):
    App.apply_selected_discogs = _gd_apply_selected_discogs
# ------------------------------------------------------------------------

# Launch with an explicit Tk root (your App expects it)
root = Tk()
app = App(root)
# Prefer root.mainloop if available
if hasattr(root, "mainloop"):
    root.mainloop()
elif hasattr(app, "mainloop"):
    app.mainloop()
