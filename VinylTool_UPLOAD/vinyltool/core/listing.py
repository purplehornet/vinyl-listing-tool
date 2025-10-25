# vinyltool/core/listing.py
from __future__ import annotations
from typing import *
import re
import tkinter as tk
from tkinter import ttk  # <<< THIS LINE WAS MISSING
from tkinter import messagebox
import threading

# --- Constants and Helpers (Restored from VinylTool_BETA1_.py) ---

# This dictionary is critical. The keys MUST match the values in your Tkinter dropdowns.
# The old monolith had the correct keys.
GRADE_ABBREVIATIONS = {
    "Mint": "M", "Near Mint": "NM", "Excellent": "EX",
    "Very Good Plus": "VG+", "Very Good": "VG", "Good Plus": "G+",
    "Good": "G", "Fair": "F", "Poor": "P", "Generic": "G"
}

# --- Helper Functions for Modular Access ---
# These functions allow the title/description logic to access the main app's UI elements.

def _get(app, key: str, default: str = "") -> str:
    """Safely get a value from the main application's UI entry widgets."""
    try:
        # Construct the key name used in the `app.entries` dictionary
        widget_key = key.lower().replace(" / ", "_").replace("/", "_").replace(" ", "_")
        widget = app.entries[widget_key]
        
        if isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return widget.get().strip()
        elif isinstance(widget, tk.Text):
            return widget.get("1.0", "end-1c").strip()
    except (KeyError, AttributeError) as e:
        print(f"Debug: Could not _get entry for key '{key}' (widget key: '{widget_key}'): {e}")

    return default

def _set_entry(app, key: str, value: str):
    """Safely set a value in the main application's UI entry widgets."""
    try:
        widget_key = key.lower().replace(" / ", "_").replace("/", "_").replace(" ", "_")
        widget = app.entries[widget_key]

        if isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            widget.delete(0, tk.END)
            widget.insert(0, value)
        elif isinstance(widget, tk.Text):
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value)
    except (KeyError, AttributeError) as e:
        print(f"Warning: Could not _set entry for key '{key}' (widget key: '{widget_key}'): {e}")


# --- Core Listing Generation Functions ---

def generate_listing_title(app):
    """
    Generates the listing title using the proven logic from the monolith.
    
    Format: ARTIST: Title (Year) [Format] Vinyl LP [CatNo] Grade
    """
    parts = []

    # 1. Gather data from the form using the _get helper
    artist = _get(app, "artist")
    title = _get(app, "title")
    year = _get(app, "year")
    cat_no = _get(app, "cat_no")
    specific_format = _get(app, "format") # e.g., "2x12\"", "LP", "7\""
    
    # 2. Artist (UPPERCASE)
    if artist:
        parts.append(f"{artist.upper()}:")

    # 3. Title
    if title:
        parts.append(title)
        
    # 4. Year
    if year:
        parts.append(f"({year})")
        
    # 5. Format Prefix and "Vinyl LP"
    format_prefix = ""
    if specific_format:
        # Extract prefixes like "2x" from "2x12\"" or "2x LP"
        match = re.match(r"^\s*(\d+x)", specific_format, re.IGNORECASE)
        if match:
            format_prefix = f"{match.group(1)} "
            
    parts.append(f"{format_prefix}Vinyl LP")
    
    # 6. CatNo (skip if it looks like a barcode)
    if cat_no and not (cat_no.isdigit() and 10 <= len(cat_no) <= 14):
        parts.append(cat_no)
        
    # 7. Grade (NM/NM, VG+/VG+, etc.)
    media_cond = _get(app, "media_condition")
    sleeve_cond = _get(app, "sleeve_condition")
    
    media_abbr = GRADE_ABBREVIATIONS.get(media_cond, "")
    sleeve_abbr = GRADE_ABBREVIATIONS.get(sleeve_cond, "")
    
    if media_abbr and sleeve_abbr:
        parts.append(f"{media_abbr}/{sleeve_abbr}")
        
    # 8. Assemble, truncate, and set the final title
    final_title = " ".join(filter(None, parts))[:80]
    _set_entry(app, "listing_title", final_title)
    
    print(f"Generated Title: {final_title}") # For debugging

def build_description(app):
    """Build full description with tracklist using the Analog Theory template."""
    if not app.current_release_id:
        messagebox.showwarning("No Release", "Please select a Discogs release first to get tracklist data.")
        # Still render the template with available data
        _render_analog_theory_description(app, None)
        return
    
    app.root.config(cursor="watch")
    app.root.update()
    
    def fetch_worker():
        try:
            # Assumes app.discogs_api.get_release exists and works
            release_data = app.discogs_api.get_release(app.current_release_id)
            app.safe_after(0, lambda: _render_analog_theory_description(app, release_data))
        except Exception as e:
            app.safe_after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            app.safe_after(0, lambda: app.root.config(cursor=""))
    
    threading.Thread(target=fetch_worker, daemon=True).start()

def _render_analog_theory_description(app, release_data):
    """Renders the HTML description. (This function was mostly correct)."""
    
    # --- Gather data from UI form ---
    payload = {
        "artist": _get(app, "artist"),
        "title": _get(app, "title"),
        "cat_no": _get(app, "cat_no"),
        "year": _get(app, "year"),
        "format": _get(app, "format"),
        "media_condition": _get(app, "media_condition"),
        "sleeve_condition": _get(app, "sleeve_condition"),
        "condition_notes": _get(app, "condition_notes"),
        "matrix_runout": _get(app, "matrix_runout"),
        "condition_tags": _get(app, "condition_tags"),
        "barcode": _get(app, "barcode"),
    }

    # --- Helper functions for template ---
    def get_release_attr(data, key, default=''):
        return data.get(key, default) if data else default

    def get_label_info(data):
        if not data or not data.get('labels'): return ''
        return data['labels'][0].get('name', '')

    def get_main_format(data):
        if not data or not data.get('formats'): return payload.get('format', 'Vinyl')
        main_format = data['formats'][0].get('name', '')
        descriptions = ", ".join(data['formats'][0].get('descriptions', []))
        return f"{main_format}, {descriptions}" if descriptions else main_format

    # --- Tracklist ---
    tracklist_html = ""
    if release_data and release_data.get('tracklist'):
        tracklist_items = []
        for track in release_data['tracklist']:
            title = track.get('title', 'Unknown Track')
            position = (track.get('position', '') or '').strip()
            display = f"{position}  {title}".strip()
            tracklist_items.append(f'<li><span class="track-line">{display}</span></li>')
        tracklist_html = f'<ul class="track-listing" style="list-style:none; margin:0; padding-left:0;">{"".join(tracklist_items)}</ul>'
        tracklist_section_html = (
            '<div style="border:1px solid #d6d2c9; border-radius:8px; padding:12px; background:#ffffff; margin-top:10px;">'
            f'<h3 style="margin:0 0 12px 0; font-size:16px; font-weight:bold;">Tracklist</h3>{tracklist_html}</div>'
        ) if tracklist_html else ''
    else:
        tracklist_section_html = ''

    # --- Other HTML sections ---
    _pill = "display:inline-block; font-weight:bold; padding:6px 10px; border-radius:8px; border:1px solid #3a7d2c; background:#f1f9f1; color:#3a7d2c; margin:2px;"
    tags_raw = payload.get('condition_tags', '').strip()
    tags_list = [t.strip() for t in tags_raw.split(',') if t.strip()]
    tags_pills_html = "".join([f'<span style="{_pill}">{t}</span>' for t in tags_list])

    condition_notes_html = (
        '<div style="border-top:1px dashed #d6d2c9; padding:14px 0;"><strong>Condition Notes:</strong>'
        f'<div style="font-size:14px; color:#5c5c5c; margin-top:8px;">{payload.get("condition_notes", "").replace(chr(10), "<br>")}</div></div>'
    ) if payload.get("condition_notes") else ''

    matrix_text = payload.get('matrix_runout', '')
    matrix_details_html = (
        '<div style="border:1px solid #d6d2c9; border-radius:8px; padding:12px; background:#ffffff; margin-top:14px;">'
        '<h3 style="margin:0 0 12px 0; font-size:16px; font-weight:bold;">Matrix / Runout Details</h3>'
        f'<div style="font-size:14px; white-space:pre-wrap;">{matrix_text.replace(chr(10), "<br>")}</div></div>'
    ) if matrix_text else ''
    
    store_promise_html = (
        '<div style="border:1px solid #e3e0d8; border-radius:12px; padding:16px; background:#fffefb; margin:12px 0 16px 0;">'
          '<table role="presentation" style="width:100%; border-collapse:separate; border-spacing:8px;"><tr>'
          '<td style="width:33.33%; vertical-align:top; padding:10px; border:1px solid #e3e0d8; border-radius:10px; background:#ffffff;"><div style="display:flex; align-items:flex-start; gap:10px;"><span aria-hidden="true" style="font-size:22px; line-height:1; margin-top:2px;">✅</span><span style="font-size:18px; font-weight:600; color:#1a1a1a; line-height:1.4;">Professional, Secure Packaging</span></div></td>'
          '<td style="width:33.33%; vertical-align:top; padding:10px; border:1px solid #e3e0d8; border-radius:10px; background:#ffffff;"><div style="display:flex; align-items:flex-start; gap:10px;"><span aria-hidden="true" style="font-size:22px; line-height:1; margin-top:2px;">✅</span><span style="font-size:18px; font-weight:600; color:#1a1a1a; line-height:1.4;">Fast Dispatch Royal Mail</span></div></td>'
          '<td style="width:33.33%; vertical-align:top; padding:10px; border:1px solid #e3e0d8; border-radius:10px; background:#ffffff;"><div style="display:flex; align-items:flex-start; gap:10px;"><span aria-hidden="true" style="font-size:22px; line-height:1; margin-top:2px;">✅</span><span style="font-size:18px; font-weight:600; color:#1a1a1a; line-height:1.4;">All Stock Graded Honestly</span></div></td>'
          '</tr></table></div>'
    )

    # --- Assemble the final HTML ---
    html_template = f"""
    <div style="max-width: 860px; width: 100%; margin: 0 auto; background: #fffdf9; border: 1px solid #d6d2c9; border-radius: 12px; overflow: hidden; font-family: Arial, 'Helvetica Neue', sans-serif; color: #1a1a1a; font-size: 16px; line-height: 1.55;">
      <div style="padding: 20px 22px; border-bottom: 1px solid #d6d2c9; background: #ffffff;">
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="width: 44px; vertical-align: middle; padding-right: 16px;"><div style="width: 44px; height: 44px; border-radius: 8px; border: 1px solid #d6d2c9; background: linear-gradient(135deg, #b8e6ff, #e8f7ff);"></div></td>
            <td style="vertical-align: middle;"><h1 style="margin: 0; font-size: 20px; font-weight: bold; color: #1a1a1a;">{payload.get('artist', '')} – {payload.get('title', '')}</h1></td>
            <td style="text-align: right; vertical-align: middle;"><span style="display: inline-block; border: 1px solid #d6d2c9; color: #5c5c5c; padding: 6px 12px; border-radius: 20px; font-size: 14px;">In Stock</span></td>
          </tr>
        </table>
      </div>
      <div style="padding: 20px 22px;">
        <table style="width: 100%; border-collapse: separate; border-spacing: 10px; margin: 16px 0;">
          <tr>
            <td style="border: 1px solid #d6d2c9; border-radius: 8px; padding: 10px 12px; background: #ffffff; width: 33%; vertical-align: top;"><span style="display:block; font-size:12px; color:#5c5c5c; text-transform:uppercase; letter-spacing:0.5px;">Format</span><span style="display:block; font-weight:bold; margin-top:4px;">{get_main_format(release_data)}</span></td>
            <td style="border: 1px solid #d6d2c9; border-radius: 8px; padding: 10px 12px; background: #ffffff; width: 33%; vertical-align: top;"><span style="display:block; font-size:12px; color:#5c5c5c; text-transform:uppercase; letter-spacing:0.5px;">Cat No</span><span style="display:block; font-weight:bold; margin-top:4px;">{payload.get('cat_no', '')}</span></td>
            <td style="border: 1px solid #d6d2c9; border-radius: 8px; padding: 10px 12px; background: #ffffff; width: 33%; vertical-align: top;"><span style="display:block; font-size:12px; color:#5c5c5c; text-transform:uppercase; letter-spacing:0.5px;">Year</span><span style="display:block; font-weight:bold; margin-top:4px;">{payload.get('year', '')}</span></td>
          </tr>
          <tr>
            <td style="border: 1px solid #d6d2c9; border-radius: 8px; padding: 10px 12px; background: #ffffff; width: 33%; vertical-align: top;"><span style="display:block; font-size:12px; color:#5c5c5c; text-transform:uppercase; letter-spacing:0.5px;">Label</span><span style="display:block; font-weight:bold; margin-top:4px;">{get_label_info(release_data)}</span></td>
            <td style="border: 1px solid #d6d2c9; border-radius: 8px; padding: 10px 12px; background: #ffffff; width: 33%; vertical-align: top;"><span style="display:block; font-size:12px; color:#5c5c5c; text-transform:uppercase; letter-spacing:0.5px;">Country</span><span style="display:block; font-weight:bold; margin-top:4px;">{get_release_attr(release_data, 'country', '')}</span></td>
            <td style="border: 1px solid #d6d2c9; border-radius: 8px; padding: 10px 12px; background: #ffffff; width: 33%; vertical-align: top;"><span style="display:block; font-size:12px; color:#5c5c5c; text-transform:uppercase; letter-spacing:0.5px;">Barcode</span><span style="display:block; font-weight:bold; margin-top:4px;">{payload.get('barcode', '')}</span></td>
          </tr>
        </table>
        <div style="border-top:1px dashed #d6d2c9; padding:14px 0;">
          <div style="display:block;">
            <strong style="font-size:16px; display:block;">Condition</strong>
            <div style="font-size:14px; color:#5c5c5c; margin:6px 0 8px 0;">Graded under strong light.</div>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              <span style="{_pill}">Vinyl: {GRADE_ABBREVIATIONS.get(payload.get('media_condition', ''), '')}</span>
              <span style="{_pill}">Sleeve: {GRADE_ABBREVIATIONS.get(payload.get('sleeve_condition', ''), '')}</span>
              {tags_pills_html}
            </div>
          </div>
        </div>
      </div>
      {condition_notes_html}
      {matrix_details_html}
      {tracklist_section_html}
      {store_promise_html}
    </div>
    """
    final_html = '\n'.join([line.strip() for line in html_template.split('\n') if line.strip()])
    
    # Set the value in the main app's description widget
    app.full_desc.delete("1.0", tk.END)
    app.full_desc.insert("1.0", final_html)
