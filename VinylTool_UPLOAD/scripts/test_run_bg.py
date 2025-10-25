from tkinter import Tk, Button, messagebox
import time
from vinyltool.core.async_utils import run_bg

root = Tk()
root.title("run_bg smoke test")

def do_work():
    time.sleep(2)
    return "All good"

def on_ok(res):
    messagebox.showinfo("Result", res)

def on_err(exc, tb):
    messagebox.showerror("Error", f"{exc}\n\n{tb}")

Button(root, text="Run 2s task", command=lambda: run_bg(root, do_work, on_ok, on_err, name="demo")).pack(padx=20, pady=20)

root.mainloop()
