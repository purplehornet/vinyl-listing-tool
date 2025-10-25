"""
VinylTool UI Dialogs
====================
Dialog classes for user input.
"""
from __future__ import annotations
from typing import *
import tkinter as tk
from tkinter import ttk, simpledialog, scrolledtext, messagebox

from vinyltool.core.constants import GRADE_ABBREVIATIONS, REVERSE_GRADE_MAP

class QuickListDialog(simpledialog.Dialog):
    """Dialog for streamlined Discogs listing."""
    def body(self, master):
        ttk.Label(master, text="Price (£):").grid(row=0, sticky="w")
        self.price_entry = ttk.Entry(master, width=20)
        self.price_entry.grid(row=0, column=1, pady=5)

        ttk.Label(master, text="Media Condition:").grid(row=1, sticky="w")
        self.media_cond_var = tk.StringVar()
        self.media_cond_combo = ttk.Combobox(master, textvariable=self.media_cond_var, 
                                             values=list(REVERSE_GRADE_MAP.keys()), state="readonly")
        self.media_cond_combo.grid(row=1, column=1, pady=5)
        self.media_cond_combo.set("Near Mint (NM or M-)")

        ttk.Label(master, text="Sleeve Condition:").grid(row=2, sticky="w")
        self.sleeve_cond_var = tk.StringVar()
        self.sleeve_cond_combo = ttk.Combobox(master, textvariable=self.sleeve_cond_var, 
                                              values=list(REVERSE_GRADE_MAP.keys()), state="readonly")
        self.sleeve_cond_combo.grid(row=2, column=1, pady=5)
        self.sleeve_cond_combo.set("Near Mint (NM or M-)")

        ttk.Label(master, text="Comments:").grid(row=3, sticky="nw")
        self.comments_text = scrolledtext.ScrolledText(master, width=40, height=5, wrap="word")
        self.comments_text.grid(row=3, column=1, pady=5)
        
        return self.price_entry

    def apply(self):
        try:
            price = float(self.price_entry.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Price must be a valid number.", parent=self)
            self.result = None
            return

        self.result = {
            "price": price,
            "media_condition": self.media_cond_var.get(),
            "sleeve_condition": self.sleeve_cond_var.get(),
            "comments": self.comments_text.get("1.0", "end-1c").strip()
        }


class ConditionGradingDialog(simpledialog.Dialog):
    """Dialog for setting media and sleeve condition with optional defaults."""

    def __init__(self, parent, title: Optional[str] = None,
                 media_default: Optional[str] = None, sleeve_default: Optional[str] = None):
        # Store the requested default values (full names like "Very Good Plus")
        self._media_default = media_default
        self._sleeve_default = sleeve_default
        # Ensure a title is provided; fallback to the original default
        super().__init__(parent, title=title or "Set Condition Grading")

    def body(self, master):
        # Build form elements
        ttk.Label(master, text="Media Condition:").grid(row=0, sticky="w", padx=5, pady=5)
        self.media_cond_var = tk.StringVar()
        self.media_cond_combo = ttk.Combobox(
            master,
            textvariable=self.media_cond_var,
            values=list(GRADE_ABBREVIATIONS.keys()),
            state="readonly",
            width=25
        )
        self.media_cond_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(master, text="Sleeve Condition:").grid(row=1, sticky="w", padx=5, pady=5)
        self.sleeve_cond_var = tk.StringVar()
        self.sleeve_cond_combo = ttk.Combobox(
            master,
            textvariable=self.sleeve_cond_var,
            values=list(GRADE_ABBREVIATIONS.keys()),
            state="readonly",
            width=25
        )
        self.sleeve_cond_combo.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(master, text="Asking Price (£):").grid(row=2, sticky="w", padx=5, pady=5)
        self.price_entry = ttk.Entry(master, width=27)
        self.price_entry.grid(row=2, column=1, padx=5, pady=5)

        ttk.Label(master, text="Condition Notes:").grid(row=3, sticky="nw", padx=5, pady=5)
        self.notes_text = scrolledtext.ScrolledText(master, width=30, height=4, wrap="word")
        self.notes_text.grid(row=3, column=1, padx=5, pady=5)

        # Apply any provided default values; if none, fallback to "Near Mint"
        # Only set the combo value if the default exists in the list of keys
        md = self._media_default or "Near Mint"
        if md in GRADE_ABBREVIATIONS.keys():
            self.media_cond_combo.set(md)
        else:
            self.media_cond_combo.set("Near Mint")

        sd = self._sleeve_default or "Near Mint"
        if sd in GRADE_ABBREVIATIONS.keys():
            self.sleeve_cond_combo.set(sd)
        else:
            self.sleeve_cond_combo.set("Near Mint")

        return self.media_cond_combo

    def apply(self):
        try:
            price = self.price_entry.get().strip()
            price_val = float(price) if price else 0.0
        except ValueError:
            messagebox.showerror("Invalid Input", "Price must be a valid number.", parent=self)
            self.result = None
            return

        self.result = {
            "media_condition": self.media_cond_var.get(),
            "sleeve_condition": self.sleeve_cond_var.get(),
            "price": price_val,
            "notes": self.notes_text.get("1.0", "end-1c").strip()
        }

# ============================================================================
# MAIN APPLICATION - COMPLETE WITH ALL FEATURES
# ============================================================================

