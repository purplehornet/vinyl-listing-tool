from __future__ import annotations
import threading, traceback
from tkinter import Tk

def run_bg(root: Tk, fn, on_ok=None, on_err=None, busy_cursor=True, name="worker"):
    """
    Run a function on a daemon thread and marshal callbacks back to Tk safely.
      - fn: callable with no args (use lambda/partial to bind args)
      - on_ok(result): called on main thread if fn returns
      - on_err(exc, tb): called on main thread if fn raises
    """
    def set_busy(busy: bool):
        try:
            root.config(cursor="watch" if busy else "")
            root.update_idletasks()
        except Exception:
            # Root may be closing; ignore
            pass

    def _worker():
        try:
            res = fn()
        except Exception as exc:
            tb = traceback.format_exc()
            root.after(0, lambda: (on_err and on_err(exc, tb), set_busy(False)))
        else:
            root.after(0, lambda: (on_ok and on_ok(res), set_busy(False)))

    if busy_cursor:
        set_busy(True)
    t = threading.Thread(target=_worker, name=name, daemon=True)
    t.start()
    return t
