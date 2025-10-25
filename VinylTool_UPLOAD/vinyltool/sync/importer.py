from __future__ import annotations
import logging, sys, os, time, json, re, threading, queue, traceback
from typing import *
from vinyltool.core.logging import setup_logging
logger = setup_logging('importer')

# NOTE: functions take `app` (VinylToolApp) as first arg

def start_discogs_import(app):
"""Import inventory from Discogs"""
if not app.discogs_api.is_connected(): return
if not messagebox.askyesno("Confirm Import", "This will import all 'For Sale' items from Discogs.\nExisting items will be skipped.\n\nContinue?"): return
app.root.config(cursor="watch"); app.root.update()
def import_worker():
    try:
        inventory = app.discogs_api.get_inventory()
        app.safe_after(0, lambda: app._process_discogs_import(inventory))
    except Exception as e:
        app.safe_after(0, lambda: messagebox.showerror("Import Error", str(e)))
    finally:
        app.safe_after(0, lambda: app.root.config(cursor=""))
threading.Thread(target=import_worker, daemon=True).start()
    
    def _process_discogs_import(self, inventory):
"""Process Discogs import"""
new_items, skipped_items = 0, 0
try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        for listing in inventory:
            if listing.status != 'For Sale': continue
            cursor.execute("SELECT COUNT(*) FROM inventory WHERE discogs_listing_id = ?", (listing.id,))
            if cursor.fetchone()[0] > 0:
                skipped_items += 1
                continue
            new_items += 1
            artist = listing.release.artists[0].name if listing.release.artists else "Various"
            title = listing.release.title.replace(f"{artist} - ", "", 1).strip()
            sku = datetime.datetime.now().strftime(f"%Y%m%d-%H%M%S-{new_items}")
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            sql = """INSERT INTO inventory (sku, artist, title, cat_no, media_condition, sleeve_condition, price, status, discogs_release_id, discogs_listing_id, date_added, last_modified) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            media_cond = DISCOGS_GRADE_MAP.get(listing.condition, listing.condition)
            sleeve_cond = DISCOGS_GRADE_MAP.get(listing.sleeve_condition, listing.sleeve_condition)
            catno = getattr(listing.release, 'catno', '')
            cursor.execute(sql, (sku, artist, title, catno, media_cond, sleeve_cond, listing.price.value, "For Sale", listing.release.id, listing.id, now, now))
    messagebox.showinfo("Import Complete", f"Successfully imported {new_items} new item(s).\nSkipped {skipped_items} existing item(s).")
    app.populate_inventory_view()
except Exception as e:
    logger.error(f"Import failed: {e}")
    messagebox.showerror("Import Error", f"An error occurred during import:\n{e}")
    
    def toggle_auto_sync(self):
"""Toggle automatic sync"""
if not app.discogs_api.is_connected():
    messagebox.showwarning("Not Connected", "Please connect to your Discogs account first.")
    app.auto_sync_var.set(False)
    return
app.auto_sync_enabled = app.auto_sync_var.get()
app.config.save({"auto_sync_enabled": app.auto_sync_enabled})
if app.auto_sync_enabled: app.start_auto_sync()
else: app.stop_auto_sync()
    
    def toggle_two_way_sync(self):
"""Toggle two-way sync"""
app.two_way_sync_enabled = app.two_way_sync_var.get()
app.config.save({"two_way_sync_enabled": app.two_way_sync_enabled})
app.log_sync_activity(f"Two-way sync {'enabled' if app.two_way_sync_enabled else 'disabled'}")
    
    def toggle_attempt_updates(self):
"""Toggle attempt to update Discogs"""
app.attempt_discogs_updates = app.attempt_updates_var.get()
app.config.save({"attempt_discogs_updates": app.attempt_discogs_updates})
app.log_sync_activity(f"Discogs update attempts {'enabled' if app.attempt_discogs_updates else 'disabled'}")
    
    def update_sync_interval(self):
"""Update sync interval"""
try:
    minutes = int(app.sync_interval_var.get())
    app.auto_sync_interval = minutes * 60
    app.config.save({"auto_sync_interval": app.auto_sync_interval})
    app.log_sync_activity(f"Sync interval set to {minutes} minutes")
except ValueError: app.sync_interval_var.set("5")
    
    def start_auto_sync(self):
"""Start automatic sync"""
if app.auto_sync_thread and app.auto_sync_thread.is_alive(): return
app.auto_sync_stop_event.clear()
app.auto_sync_thread = threading.Thread(target=app._auto_sync_worker, daemon=True)
app.auto_sync_thread.start()
app.sync_status_var.set("Auto-sync enabled - waiting for next sync...")
app.log_sync_activity("Automatic sync started")
    
    def stop_auto_sync(self):
"""Stop automatic sync"""
app.auto_sync_stop_event.set()
app.sync_status_var.set("Auto-sync disabled")
app.log_sync_activity("Automatic sync stopped")
    
    def _auto_sync_worker(self):
"""Auto sync worker thread"""
while not app.auto_sync_stop_event.is_set():
    try:
        if app.auto_sync_stop_event.wait(app.auto_sync_interval): break
        if app.auto_sync_enabled and app.discogs_api.is_connected():
            app.safe_after(0, lambda: app.sync_status_var.set("Syncing inventory..."))
            sync_result = app._perform_inventory_sync()
            app.safe_after(0, lambda r=sync_result: app._handle_sync_result(r))
    except Exception as e:
        app.safe_after(0, lambda msg=f"Auto-sync error: {e}": app.log_sync_activity(msg))
    
    def manual_sync_now(self):
"""Perform manual sync now"""
if not app.discogs_api.is_connected():
    messagebox.showwarning("Not Connected", "Please connect to your Discogs account first.")
    return
app.sync_status_var.set("Manual sync in progress...")
app.root.config(cursor="watch"); app.root.update()
def sync_worker():
    try:
        result = app._perform_inventory_sync()
        app.safe_after(0, lambda: app._handle_sync_result(result))
    except Exception as e:
        app.safe_after(0, lambda: messagebox.showerror("Sync Error", str(e)))
    finally:
        app.safe_after(0, lambda: app.root.config(cursor=""))
threading.Thread(target=sync_worker, daemon=True).start()
    
    def _perform_inventory_sync(self):
"""Implements true "latest-wins" two-way sync logic."""
sync_start_time = datetime.datetime.now(datetime.timezone.utc)
app.log_sync_activity("=== STARTING SYNC (Latest-Wins) ===")
try:
    discogs_inventory = app.discogs_api.get_inventory()
    discogs_map = {listing.id: listing for listing in discogs_inventory}
    app.log_sync_activity(f"Retrieved {len(discogs_inventory)} active listings from Discogs.")

    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sku, discogs_listing_id, price, status, notes, last_modified, last_sync_time FROM inventory WHERE discogs_listing_id IS NOT NULL")
        local_items = [dict(row) for row in cursor.fetchall()]
        local_map = {item['discogs_listing_id']: item for item in local_items}
    app.log_sync_activity(f"Found {len(local_map)} linked local items.")

    updates_to_local, updates_to_discogs, deletions_from_local, new_sales = 0, 0, 0, 0
    
    for local_item in local_items:
        listing_id, last_mod_local_str, last_sync_str = local_item['discogs_listing_id'], local_item.get('last_modified'), app.last_successful_sync_time or local_item.get('last_sync_time')
        if not last_mod_local_str or not last_sync_str: continue
        try:
            last_mod_local, last_sync = datetime.datetime.fromisoformat(last_mod_local_str), datetime.datetime.fromisoformat(last_sync_str)
        except (ValueError, TypeError): continue

        if last_mod_local > last_sync and app.attempt_discogs_updates:
            if listing_id in discogs_map:
                app.log_sync_activity(f"→ Local change detected for SKU {local_item['sku']}. Pushing to Discogs.")
                update_payload = {"price": local_item['price'], "status": app._map_local_to_discogs_status(local_item['status']), "comments": local_item.get('notes', '')}
                if app.discogs_api.update_listing(listing_id, update_payload):
                    updates_to_discogs += 1; app.log_sync_activity(f"  ✓ Pushed update for SKU {local_item['sku']} to Discogs.")
                else: app.log_sync_activity(f"  ✗ Failed to push update for SKU {local_item['sku']}.")
            else: app.log_sync_activity(f"  - SKU {local_item['sku']} changed locally but no longer on Discogs. Skipping push.")

        elif listing_id in discogs_map:
            listing = discogs_map[listing_id]
            mapped_status = app.status_mappings.get(listing.status, "Not For Sale")
            if mapped_status != local_item['status']:
                with app.db.get_connection() as conn:
                    conn.cursor().execute("UPDATE inventory SET status = ?, last_modified = ? WHERE discogs_listing_id = ?", (mapped_status, sync_start_time.isoformat(), listing_id))
                updates_to_local += 1
                if mapped_status == 'Sold' and local_item['status'] != 'Sold': new_sales += 1
                app.log_sync_activity(f"✓ Sync from Discogs: SKU {local_item['sku']} '{local_item['status']}' → '{mapped_status}'")

    ids_to_delete_locally = set(local_map.keys()) - set(discogs_map.keys())
    if ids_to_delete_locally:
        with app.db.get_connection() as conn:
            cursor = conn.cursor()
            for listing_id in ids_to_delete_locally:
                if local_map[listing_id]['status'] == 'For Sale':
                    sku = local_map[listing_id]['sku']
                    cursor.execute("DELETE FROM inventory WHERE discogs_listing_id = ?", (listing_id,))
                    deletions_from_local += 1
                    app.log_sync_activity(f"✓ Deleted SKU {sku} locally as it's no longer on Discogs.")
    
    with app.db.get_connection() as conn:
        conn.cursor().execute("UPDATE inventory SET last_sync_time = ? WHERE discogs_listing_id IS NOT NULL", (sync_start_time.isoformat(),))
    app.last_successful_sync_time = sync_start_time.isoformat()
    app.config.save({"last_successful_sync_time": app.last_successful_sync_time})
    if updates_to_local > 0 or deletions_from_local > 0: app.safe_after(0, app.populate_inventory_view)
    app.log_sync_activity("=== SYNC COMPLETED ===")
    return {'success': True, 'updates_local': updates_to_local, 'updates_discogs': updates_to_discogs, 'deletions': deletions_from_local, 'new_sales': new_sales, 'total_checked': len(discogs_inventory)}
except Exception as e:
    logger.error(f"Sync failed: {e}", exc_info=True)
    app.log_sync_activity(f"✗ SYNC ERROR: {e}")
    return {'success': False, 'error': str(e)}

    def _map_local_to_discogs_status(self, local_status):
"""Map local status to valid Discogs status"""
return {'For Sale': 'For Sale', 'Sold': 'Sold'}.get(local_status, 'Draft')
    
    def _handle_sync_result(self, result):
"""Handle sync result"""
current_time = datetime.datetime.now().strftime("%H:%M:%S")
if result.get('success'):
    updates_local, updates_discogs, deletions = result.get('updates_local', 0), result.get('updates_discogs', 0), result.get('deletions', 0)
    total_changes = updates_local + updates_discogs + deletions
    if total_changes > 0:
        log_msg = f"[{current_time}] Sync completed: {total_changes} changes from {result['total_checked']} listings"
        if updates_local > 0: log_msg += f"\n  - Pulled from Discogs: {updates_local}"
        if updates_discogs > 0: log_msg += f"\n  - Pushed to Discogs: {updates_discogs}"
        if deletions > 0: log_msg += f"\n  - Items deleted locally: {deletions}"
        if result.get('new_sales', 0) > 0: log_msg += f"\n  - New sales detected: {result['new_sales']}"
        app.log_sync_activity(log_msg)
        status_msg = f"Sync complete - {total_changes} change(s)"
    else:
        status_msg = "Sync complete - no changes needed"
        app.log_sync_activity(f"[{current_time}] Sync completed. No changes needed.")
    app.sync_status_var.set(f"Last sync: {current_time}. {status_msg}")
else:
    app.sync_status_var.set(f"Last sync: {current_time}. FAILED.")
    app.log_sync_activity(f"[{current_time}] Sync FAILED: {result.get('error')}")

    # ========================================================================
    # ENHANCED PUBLISHING ACTION METHODS
    # ========================================================================
    
    def action_ebay_save_unpublished(self):
"""Save eBay listing data locally as 'ready to publish' without sending to eBay"""
if app.notebook.tab(app.notebook.select(), "text") == "Lister":
    # From Lister tab - save current form
    app._save_ebay_draft_from_lister()
else:
    # From Inventory tab - mark selected items as ready for eBay
    app._save_ebay_draft_from_inventory()

    def action_ebay_publish_live(self):
"""Publish directly to eBay as live listings (Inventory API)"""
if app.notebook.tab(app.notebook.select(), "text") == "Lister":
    # From Lister tab - publish current form directly
    app.list_on_ebay()
else:
    # From Inventory tab - publish selected items
    app.publish_to_ebay()



    def reconcile_from_ebay(self, skus):


"""Pull eBay state back into local DB so deletions/ends/relists are reflected.


Chooses ACTIVE offer. Prefers Item ID (listingId); falls back to offerId if listingId hasn't propagated yet.


Refreshes the grid when done.


"""


import datetime, logging, requests


logger = logging.getLogger(__name__)


    


token = app.ebay_api.get_access_token()


if not token:


    app.append_log("Cannot reconcile: missing eBay token", "red")


    return


    


headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}


changed = False


    


for sku in (skus or []):


    try:


        url = f"{app.ebay_api.base_url}/sell/inventory/v1/offer?sku={sku}"


        r = requests.get(url, headers=headers, timeout=30)


        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()


    


        if r.status_code == 200 and r.json().get("offers"):


            offers = r.json()["offers"]


            # Pick ACTIVE offer if available; otherwise first one


            active = None


            for o in offers:


                if (o.get("status") or "").upper() == "ACTIVE":


                    active = o


                    break


            offer = active or offers[0]


            status = (offer.get("status") or "").upper()


    


            listing_id = offer.get('legacyItemId') or offer.get('listingId') or (offer.get('listing') or {}).get('legacyItemId') or (offer.get('listing') or {}).get('listingId')


            offer_id = offer.get("offerId") or (offer.get("offer") or {}).get("offerId")


    


            # If ACTIVE but listingId missing, try GET /offer/{offerId} to resolve


            if status in ("ACTIVE","PUBLISHED") and not listing_id and offer_id:


                try:


                    resolved = app.ebay_api.get_offer(str(offer_id))


                    if resolved.get("success"):


                        listing_id = resolved.get('legacyItemId') or (resolved.get('listing') or {}).get('legacyItemId') or resolved.get('listingId') or (resolved.get('listing') or {}).get('listingId')


                except Exception as e:


                    logger.warning(f"[reconcile] get_offer failed for offer {offer_id}: {e}")


    


            with app.db.get_connection() as conn:


                c = conn.cursor()


                if status in ("ACTIVE","PUBLISHED"):


                    stored_id = listing_id or (offer_id if offer_id else None)


                    if stored_id:


                        c.execute("UPDATE inventory SET ebay_listing_id = ?, ebay_updated_at = ? WHERE sku = ?", (stored_id, now_iso, sku))


                        changed = True


                    else:


                        c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


                        changed = True


                else:


                    c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


                    changed = True


    


            shown = listing_id or (offer_id if (status in ("ACTIVE","PUBLISHED") and offer_id) else "—")


            label = "Item ID" if listing_id else ("Offer ID" if shown != "—" else "—")  # live


            app.append_log(f"SKU {sku}: reconciled from eBay ({status}; {label}={shown})", "blue")


        else:


            with app.db.get_connection() as conn:


                c = conn.cursor()


                c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


            changed = True


            app.append_log(f"SKU {sku}: no eBay offer found; cleared local mapping.", "orange")


    


    except Exception as e:


        logger.error(f"Reconcile error for {sku}: {e}")


        app.append_log(f"SKU {sku}: reconcile failed: {e}", "red")


    


if changed:


    try:


        app.populate_inventory_view()


    except Exception:


        pass



    def action_open_on_ebay_selected(self):



"""Open the selected item's eBay listing in the browser using stored Item ID."""



import webbrowser, requests, logging



logger = logging.getLogger(__name__)



items = app.inventory_tree.selection()



if not items:



    try:



        messagebox.showinfo("Open on eBay", "Please select a row first.")



    except Exception:



        pass



    return



iid = items[0]



vals = app.inventory_tree.item(iid, "values") or []



item_id = None



# Try visible column first



try:



    headers = [app.inventory_tree.heading(c)["text"] for c in app.inventory_tree["columns"]]



    if "eBay ID" in headers:



        idx = headers.index("eBay ID")



        if idx < len(vals):



            item_id = vals[idx]



except Exception:



    item_id = None



# Fallback: DB lookup by SKU (assumes SKU in first column)



if not item_id and vals:



    sku = vals[0]



    try:



        with app.db.get_connection() as conn:



            c = conn.cursor()



            c.execute("SELECT ebay_listing_id FROM inventory WHERE sku = ?", (sku,))



            row = c.fetchone()



            if row and row[0]:



                item_id = row[0]



    except Exception:



        pass



if not item_id:



    try:



        messagebox.showinfo("Open on eBay", "No eBay Item ID stored for the selected row.")



    except Exception:



        pass



    return



# If it's likely an offerId, try resolve to listingId on the fly



if not (str(item_id).isdigit() and len(str(item_id)) >= 12) and vals:



    try:



        token = app.ebay_api.get_access_token()



        if token:



            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}



            url = f"{app.ebay_api.base_url}/sell/inventory/v1/offer?sku={{vals[0]}}"



            r = requests.get(url, headers=headers, timeout=30)



            if r.status_code == 200 and r.json().get("offers"):



                offers = r.json()["offers"]



                active = None



                for o in offers:



                    if (o.get("status") or "").upper() == "ACTIVE":



                        active = o



                        break



                off = active or offers[0]



                lid = off.get('legacyItemId') or off.get('listingId') or (off.get('listing') or {}).get('legacyItemId') or (off.get('listing') or {}).get('listingId')



                if not lid:



                    oid = off.get("offerId") or (off.get("offer") or {}).get("offerId")



                    if oid:



                        resolved = app.ebay_api.get_offer(str(oid))



                        if resolved.get("success"):



                            lid = resolved.get('legacyItemId') or (resolved.get('listing') or {}).get('legacyItemId') or resolved.get('listingId') or (resolved.get('listing') or {}).get('listingId')



                if lid:



                    item_id = lid



    except Exception as e:



        logger.warning(f"[open] resolution failed: {e}")



try:



    webbrowser.open_new_tab(f"https://www.ebay.co.uk/itm/{item_id}")



except Exception:



    try:



        messagebox.showerror("Open on eBay", "Failed to open browser.")



    except Exception:



        pass




    # ------------------------------




    # eBay → Discogs Import (Wizard)




    # ------------------------------




    def action_import_from_ebay(self):




try:




    offers = app._fetch_all_ebay_offers()




except Exception as e:




    messagebox.showerror("Import from eBay", f"Failed to fetch eBay offers:\n{e}")




    return




work = []




with app.db.get_connection() as conn:




    c = conn.cursor()




    for off in offers:




        sku = (off.get("sku") or "").strip()




        if not sku:




            continue




        c.execute("SELECT discogs_listing_id FROM inventory WHERE sku = ?", (sku,))




        row = c.fetchone()




        if not row or not row[0]:




            work.append(off)




if not work:




    messagebox.showinfo("Import from eBay", "No eligible eBay listings found (all mapped).")




    return




app._start_import_wizard(work)




    




    def _fetch_all_ebay_offers(self):




token = app.ebay_api.get_access_token()




if not token:




    raise RuntimeError("Missing eBay token")




import requests




hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}




base = f"{app.ebay_api.base_url}/sell/inventory/v1/offer"




offers, limit, offset = [], 200, 0




while True:




    resp = requests.get(f"{base}?limit={limit}&offset={offset}", headers=hdrs, timeout=30)




    if resp.status_code != 200:




        raise RuntimeError(f"eBay API error {resp.status_code}: {resp.text[:300]}")




    data = resp.json()




    batch = data.get("offers") or []




    for o in batch:




        aspects = (o.get("aspects") or {})




        gtin = None




        for k in ("EAN","UPC","GTIN","ean","upc","gtin"):




            v = aspects.get(k)




            if isinstance(v, list) and v:




                gtin = v[0]; break




            if isinstance(v, str) and v.strip():




                gtin = v.strip(); break




        if not gtin:




            prod = o.get("product") or {}




            g = prod.get("gtin")




            if isinstance(g, list) and g:




                gtin = g[0]




            elif isinstance(g, str):




                gtin = g




        offers.append({




            "sku": o.get("sku"),




            "title": o.get("title") or (o.get("name") or ""),




            "offerId": o.get("offerId") or (o.get("offer") or {}).get("offerId"),




            "listingId": o.get("legacyItemId") or o.get("listingId") or (o.get("listing") or {}).get("legacyItemId") or (o.get("listing") or {}).get("listingId"),




            "price": ((o.get("pricingSummary") or {}).get("price") or {}).get("value"),




            "currency": ((o.get("pricingSummary") or {}).get("price") or {}).get("currency"),




            "quantity": o.get("availableQuantity"),




            "status": (o.get("status") or "").upper(),




            "gtin": (gtin or "").strip(),




            "catno": (aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No") or [""])[0] if isinstance(aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No"), list) else (aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No") or ""),




            "label": (aspects.get("Record Label") or aspects.get("Label") or [""])[0] if isinstance(aspects.get("Record Label") or aspects.get("Label"), list) else (aspects.get("Record Label") or aspects.get("Label") or ""),




            "format": (aspects.get("Format") or [""])[0] if isinstance(aspects.get("Format"), list) else (aspects.get("Format") or ""),




            "country": (aspects.get("Country/Region of Manufacture") or [""])[0] if isinstance(aspects.get("Country/Region of Manufacture"), list) else (aspects.get("Country/Region of Manufacture") or ""),




            "year": (aspects.get("Release Year") or [""])[0] if isinstance(aspects.get("Release Year"), list) else (aspects.get("Release Year") or ""),




        })




    total = data.get("total", 0)




    offset += len(batch)




    if offset >= total or not batch:




        break




return offers




    




    def _start_import_wizard(self, offers):




app._import_offers = [o for o in offers]




app._import_idx = 0




win = tk.Toplevel(app.root)




win.title("Import from eBay → Discogs match")




win.geometry("720x520")




app._import_win = win




app._imp_hdr = tk.Label(win, text="", font=("Helvetica", 14, "bold"))




app._imp_hdr.pack(anchor="w", padx=12, pady=(10, 6))




app._imp_info = tk.Text(win, height=10, wrap="word")




app._imp_info.pack(fill="x", padx=12)




app._imp_status = tk.Label(win, text="", fg="gray")




app._imp_status.pack(anchor="w", padx=12, pady=6)




btns = tk.Frame(win)




btns.pack(fill="x", padx=12, pady=8)




tk.Button(btns, text="Accept", command=app._import_accept).pack(side="left", padx=4)




tk.Button(btns, text="See Alternatives…", command=app._import_alternatives).pack(side="left", padx=4)




tk.Button(btns, text="Skip", command=app._import_skip).pack(side="left", padx=4)




tk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=4)




app._import_propose_current()




    




    def _import_propose_current(self):




if app._import_idx >= len(app._import_offers):




    try:




        app.populate_inventory_view()




    except Exception:




        pass




    messagebox.showinfo("Import from eBay", "Done.")




    app._import_win.destroy()




    return




o = app._import_offers[app._import_idx]




sku = o.get("sku") or ""




title = o.get("title") or ""




gtin = o.get("gtin") or ""




catno = o.get("catno") or ""




label = o.get("label") or ""




fmt = o.get("format") or ""




app._imp_hdr.config(text=f"SKU {sku} — {title}")




app._imp_info.delete("1.0", "end")




app._imp_info.insert("end", f"eBay ID: {o.get('listingId') or o.get('offerId')}\n")




app._imp_info.insert("end", f"GTIN/Barcode: {gtin or '—'}\n")




app._imp_info.insert("end", f"Cat No: {catno or '—'}\n")




app._imp_info.insert("end", f"Label: {label or '—'} | Format: {fmt or '—'}\n\n")




try:




    cands = app._discogs_find_candidates(gtin=gtin, catno=catno, title=title, label=label or None)




except Exception as e:




    app._imp_status.config(text=f"Discogs search failed: {e}")




    app._import_candidates = []




    return




app._import_candidates = cands




if not cands:




    app._imp_status.config(text="No candidates found. Click ‘See Alternatives…’ to search manually.")




else:




    top = cands[0]




    app._imp_status.config(text=f"Proposed: {top['artist']} – {top['title']} [{top['label']} • {top['year']} • {top['country']}]  ({top['method']}, {int(top['confidence']*100)}%)")




    




    def _discogs_find_candidates(self, gtin: str = "", catno: str = "", title: str = "", label: str = None):




results = []




if gtin:




    res = app.discogs_client.search(barcode=gtin, type="release", format="Vinyl")




    for r in list(res)[:10]:




        results.append({"release_id": r.id, "title": r.title,




            "artist": getattr(r, "artist", getattr(r, "artists", "")),




            "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




            "year": getattr(r, "year", "") or "",




            "country": getattr(r, "country", "") or "",




            "method": "barcode", "confidence": 1.0})




if catno:




    res = app.discogs_client.search(catno=catno, type="release", format="Vinyl")




    for r in list(res)[:10]:




        results.append({"release_id": r.id, "title": r.title,




            "artist": getattr(r, "artist", getattr(r, "artists", "")),




            "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




            "year": getattr(r, "year", "") or "",




            "country": getattr(r, "country", "") or "",




            "method": "catno", "confidence": 0.85 if not label else 0.9})




if (not results) and title:




    res = app.discogs_client.search(title=title, type="release", format="Vinyl", label=label or None)




    for r in list(res)[:10]:




        results.append({"release_id": r.id, "title": r.title,




            "artist": getattr(r, "artist", getattr(r, "artists", "")),




            "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




            "year": getattr(r, "year", "") or "",




            "country": getattr(r, "country", "") or "",




            "method": "fuzzy", "confidence": 0.6})




seen, ranked = set(), []




for r in sorted(results, key=lambda x: x["confidence"], reverse=True):




    if r["release_id"] in seen: continue




    seen.add(r["release_id"]); ranked.append(r)




return ranked




    




    def _import_accept(self):




if app._import_idx >= len(app._import_offers): return




o = app._import_offers[app._import_idx]




top = (app._import_candidates[0] if app._import_candidates else None)




if not top:




    messagebox.showinfo("Import from eBay", "No candidate to accept for this item."); return




sku = (o.get("sku") or "").strip()




now_iso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()




with app.db.get_connection() as conn:




    c = conn.cursor()




    c.execute("SELECT 1 FROM inventory WHERE sku = ?", (sku,))




    exists = c.fetchone() is not None




    if exists:




        c.execute("""UPDATE inventory




                     SET discogs_listing_id = ?,




                         discogs_match_method = ?, discogs_match_confidence = ?,




                         barcode = COALESCE(?, barcode),




                         inv_updated_at = ?




                     WHERE sku = ?""", 




                  (str(top["release_id"]), top["method"], float(top["confidence"]),




                   (o.get("gtin") or None), now_iso, sku))




    else:




        c.execute("""INSERT INTO inventory




                     (sku, artist, title, price, status, ebay_listing_id, discogs_listing_id,




                      barcode, discogs_match_method, discogs_match_confidence, inv_updated_at, date_added)




                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 




                  (sku, "", o.get("title") or "", o.get("price") or 0.0, "For Sale",




                   (o.get("listingId") or None), str(top["release_id"]),




                   (o.get("gtin") or None), top["method"], float(top["confidence"]), now_iso, now_iso))




app.append_log(f"Imported {sku} → Discogs {top['release_id']} ({top['method']}, {int(top['confidence']*100)}%)", "green")




app._import_idx += 1




app._import_propose_current()




    




    def _import_alternatives(self):




if not app._import_candidates:




    messagebox.showinfo("Alternatives", "No candidates available for this item."); return




top = tk.Toplevel(app._import_win); top.title("Choose a Discogs release")




lb = tk.Listbox(top, width=90, height=10)




for i, r in enumerate(app._import_candidates[:12]):




    lb.insert("end", f"{i+1}. {r['artist']} – {r['title']}  [{r['label']} • {r['year']} • {r['country']}]  ({r['method']}, {int(r['confidence']*100)}%)")




lb.pack(fill="both", expand=True)




def choose():




    idx = lb.curselection()




    if not idx: return




    i = idx[0]




    chosen = app._import_candidates[i]




    rest = [r for j,r in enumerate(app._import_candidates) if j != i]




    app._import_candidates = [chosen] + rest




    top.destroy()




    app._imp_status.config(text=f"Chosen: {chosen['artist']} – {chosen['title']} [{chosen['label']} • {chosen['year']} • {chosen['country']}]  ({chosen['method']}, {int(chosen['confidence']*100)}%)")




tk.Button(top, text="Use Selected", command=choose).pack(pady=6)




    




    def _import_skip(self):




app._import_idx += 1




app._import_propose_current()





    def action_ebay_sync_selected(self):

"""Sync selected inventory SKUs from eBay into local DB (status/listingId)."""

items = app.inventory_tree.selection()

if not items:

    try:

        messagebox.showinfo("Sync from eBay", "Please select one or more items in the inventory list.")

    except Exception:

        pass

    return

skus = []

for iid in items:

    vals = app.inventory_tree.item(iid, "values")

    if not vals:

        continue

    skus.append(vals[0])

try:

    app.reconcile_from_ebay(skus)

except Exception as e:

    try:

        messagebox.showerror("Sync from eBay", f"Failed to sync: {e}")

    except Exception:

        pass


    def action_discogs_save_unpublished(self):
"""Create Discogs draft listings"""
if app.notebook.tab(app.notebook.select(), "text") == "Lister":
    app._create_discogs_draft_from_lister()
else:
    app._create_discogs_draft_from_inventory()

    def action_discogs_publish_live(self):
"""Create live Discogs listings"""
if app.notebook.tab(app.notebook.select(), "text") == "Lister":
    # Create live listing instead of draft
    app._list_on_discogs_live()
else:
    # Modify existing publish_to_discogs to use "For Sale" status
    app._publish_to_discogs_live()

    def _save_ebay_draft_from_lister(self):
"""Save current lister form as eBay-ready in database with duplicate checking"""
try:
    # Validate required fields
    required_fields = ['artist', 'title', 'media_condition']
    for field in required_fields:
        if not app.entries[field.replace(' ', '_')].get().strip():
            messagebox.showwarning("Validation Error", f"Please enter {field}")
            return
    
    try:
        price = float(app.price_entry.get())
        if price <= 0:
            messagebox.showwarning("Validation Error", "Please enter a valid price")
            return
    except (ValueError, TypeError):
        messagebox.showwarning("Validation Error", "Please enter a valid price")
        return

    # Generate SKU if needed
    sku = app.editing_sku or app.sku_display_var.get() or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if not app.editing_sku and not app.temporary_sku:
        app.sku_display_var.set(sku)

    # Check for existing listings and warn user
    existing = app._check_existing_listings(sku)
    if existing['has_ebay'] or existing['has_ebay_draft']:
        warning_parts = []
        if existing['has_ebay']:
            warning_parts.append(f"Live eBay listing: {existing['ebay_listing_id']}")
        if existing['has_ebay_draft']:
            warning_parts.append(f"eBay draft: {existing['ebay_draft_id']}")
        
        warning_text = "\n".join(warning_parts)
        message = (f"SKU {sku} already has:\n\n{warning_text}\n\n"
                  f"This will update the existing record. Continue?")
        
        if not messagebox.askyesno("Existing eBay Data Found", message):
            return

    # Save to database with special status
    payload_json = json.dumps(app._serialize_form_to_payload())
    
    try:
        with app.db.get_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            if app.editing_sku:
                # Update existing
                cursor.execute("""
                    UPDATE inventory SET 
                    status = 'eBay Ready',
                    last_modified = ?,
                    lister_payload = ?
                    WHERE sku = ?
                """, (now_iso, payload_json, sku))
                message = f"Updated SKU {sku} as ready for eBay"
            else:
                # Create new with basic info
                cursor.execute("""
                    INSERT INTO inventory (
                        sku, artist, title, price, status, date_added, 
                        last_modified, lister_payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sku,
                    app.entries["artist"].get().strip(),
                    app.entries["title"].get().strip(), 
                    price,
                    'eBay Ready',
                    now_iso,
                    now_iso,
                    payload_json
                ))
                message = f"Saved SKU {sku} as ready for eBay"
            
            app.populate_inventory_view()
            app.append_log(message, "green")
            messagebox.showinfo("eBay Draft Saved", 
                f"{message}\n\n" +
                f"Note: This creates a local draft in your database.\n" + 
                f"eBay doesn't provide draft functionality via their public API.\n" +
                f"Use 'Publish Live' when ready to list on eBay.")
            
    except Exception as e:
        logger.error(f"Failed to save eBay draft: {e}")
        messagebox.showerror("Database Error", f"Failed to save: {e}")
        
except Exception as e:
    logger.error(f"Error in _save_ebay_draft_from_lister: {e}")
    messagebox.showerror("Error", f"An error occurred: {e}")

    def _save_ebay_draft_from_inventory(self):
"""Mark selected inventory items as ready for eBay"""
selected = app.inventory_tree.selection()
if not selected:
    messagebox.showwarning("No Selection", "Please select items to prepare for eBay")
    return

try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        updated_count = 0
        for item in selected:
            sku = app.inventory_tree.item(item, "values")[0]
            cursor.execute("""
                UPDATE inventory SET 
                status = 'eBay Ready',
                last_modified = ?
                WHERE sku = ?
            """, (now_iso, sku))
            updated_count += 1
        
        app.populate_inventory_view()
        message = f"Marked {updated_count} item(s) as ready for eBay"
        app.append_log(message, "green")
        messagebox.showinfo("Success", message)
        
except Exception as e:
    logger.error(f"Failed to mark items as eBay ready: {e}")
    messagebox.showerror("Database Error", f"Failed to update items: {e}")

    def _create_discogs_draft_from_lister(self):
"""Create Discogs draft from current lister form"""
if not app.discogs_api.is_connected():
    messagebox.showwarning("Not Connected", "Please connect to Discogs first")
    return
    
if not app.current_release_id:
    messagebox.showerror("Missing Release", "You must select a specific Discogs release variant first")
    return
    
try:
    price = float(app.price_entry.get())
    media_condition = app.entries["media_condition"].get()
    if not media_condition or media_condition not in REVERSE_GRADE_MAP:
        messagebox.showwarning("Validation Error", "Please select a valid media condition")
        return
except (ValueError, TypeError):
    messagebox.showwarning("Validation Error", "Please enter a valid price")
    return

listing_data = {
    'release_id': app.current_release_id,
    'price': price,
    'status': 'Draft',  # Explicitly set as draft
    'condition': REVERSE_GRADE_MAP.get(media_condition),
    'sleeve_condition': REVERSE_GRADE_MAP.get(app.entries["sleeve_condition"].get(), 'Generic'),
    'comments': app.full_desc.get("1.0", tk.END).strip()
}

app.root.config(cursor="watch")
app.root.update()

def draft_worker():
    try:
        listing_id = app._safe_discogs_publish(app.editing_sku or "NEW", listing_data, is_draft=True)
        if listing_id:
            app.safe_after(0, lambda: app._handle_discogs_draft_success(listing_id))
    except Exception as e:
        app.safe_after(0, lambda: messagebox.showerror("Draft Error", str(e)))
    finally:
        app.safe_after(0, lambda: app.root.config(cursor=""))

threading.Thread(target=draft_worker, daemon=True).start()

    def _create_discogs_draft_from_inventory(self):
"""Create Discogs drafts from selected inventory items"""
selected = app.inventory_tree.selection()
if not selected:
    messagebox.showwarning("No Selection", "Please select items to create Discogs drafts")
    return

def draft_worker():
    for item in selected:
        sku = app.inventory_tree.item(item, "values")[0]
        try:
            record = app._get_inventory_record(sku)
            if not record:
                app.append_log(f"SKU {sku}: Could not find record.", "red")
                continue
            
            errors = validate_listing("discogs", record, app.config)
            if errors:
                app.append_log(f"SKU {sku}: {', '.join(errors)}", "red")
                continue
            
            app.append_log(f"Creating Discogs draft for SKU {sku}...", "black")
            listing_data = {
                "release_id": record.get("discogs_release_id"),
                "condition": REVERSE_GRADE_MAP.get(record.get("media_condition"), "Good (G)"),
                "sleeve_condition": REVERSE_GRADE_MAP.get(record.get("sleeve_condition"), "Good (G)"),
                "price": record.get("price", 0), 
                "status": "Draft",  # Create as draft
                "comments": record.get("description", "")
            }
            
            listing_id = app.discogs_api.create_listing(listing_data)
            if listing_id:
                app.append_log(f"SKU {sku}: Created Discogs draft (ID: {listing_id})", "green")
                try:
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    with app.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE inventory SET discogs_listing_id = ?, discogs_updated_at = ? WHERE sku = ?",
                            (listing_id, now_iso, sku),
                        )
                except Exception as e:
                    logger.error(f"Failed to update inventory with Discogs listing ID: {e}")
                    app.append_log(f"SKU {sku}: Failed to save Discogs listing ID to DB: {e}", "red")
            else:
                app.append_log(f"SKU {sku}: Failed to create draft", "red")
        except Exception as e:
            app.append_log(f"SKU {sku}: Error - {e}", "red")
    
    app.safe_after(0, app.populate_inventory_view)

threading.Thread(target=draft_worker, daemon=True).start()

    def _list_on_discogs_live(self):
"""Create live Discogs listing (For Sale status) from lister form"""
if not app.discogs_api.is_connected():
    messagebox.showwarning("Not Connected", "Please connect to Discogs first")
    return
    
if not app.current_release_id:
    messagebox.showerror("Missing Release", "You must select a specific Discogs release variant first")
    return
    
try:
    price = float(app.price_entry.get())
    media_condition = app.entries["media_condition"].get()
    if not media_condition or media_condition not in REVERSE_GRADE_MAP:
        messagebox.showwarning("Validation Error", "Please select a valid media condition")
        return
except (ValueError, TypeError):
    messagebox.showwarning("Validation Error", "Please enter a valid price")
    return

listing_data = {
    'release_id': app.current_release_id,
    'price': price,
    'status': 'For Sale',  # Live listing
    'condition': REVERSE_GRADE_MAP.get(media_condition),
    'sleeve_condition': REVERSE_GRADE_MAP.get(app.entries["sleeve_condition"].get(), 'Generic'),
    'comments': app.full_desc.get("1.0", tk.END).strip()
}

app.root.config(cursor="watch")
app.root.update()

def live_worker():
    try:
        listing_id = app.discogs_api.create_listing(listing_data)
        if listing_id:
            app.safe_after(0, lambda: app._handle_discogs_live_success(listing_id))
    except Exception as e:
        app.safe_after(0, lambda: messagebox.showerror("Listing Error", str(e)))
    finally:
        app.safe_after(0, lambda: app.root.config(cursor=""))

threading.Thread(target=live_worker, daemon=True).start()

    def _publish_to_discogs_live(self):
"""Publish selected items to Discogs as live (For Sale) listings"""
selected = app.inventory_tree.selection()
if not selected: 
    return

def live_worker():
    for item in selected:
        sku = app.inventory_tree.item(item, "values")[0]
        try:
            record = app._get_inventory_record(sku)
            if not record:
                app.append_log(f"SKU {sku}: Could not find record.", "red")
                continue
            
            errors = validate_listing("discogs", record, app.config)
            if errors:
                app.append_log(f"SKU {sku}: {', '.join(errors)}", "red")
                continue
            
            app.append_log(f"Publishing SKU {sku} live to Discogs...", "black")
            listing_data = {
                "release_id": record.get("discogs_release_id"),
                "condition": REVERSE_GRADE_MAP.get(record.get("media_condition"), "Good (G)"),
                "sleeve_condition": REVERSE_GRADE_MAP.get(record.get("sleeve_condition"), "Good (G)"),
                "price": record.get("price", 0), 
                "status": "For Sale",  # Live listing
                "comments": record.get("description", "")
            }
            
            listing_id = app.discogs_api.create_listing(listing_data)
            if listing_id:
                app.append_log(f"SKU {sku}: Published live to Discogs (ID: {listing_id})", "green")
                try:
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    with app.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE inventory SET discogs_listing_id = ?, discogs_updated_at = ? WHERE sku = ?",
                            (listing_id, now_iso, sku),
                        )
                except Exception as e:
                    logger.error(f"Failed to update inventory with Discogs listing ID: {e}")
                    app.append_log(f"SKU {sku}: Failed to save Discogs listing ID to DB: {e}", "red")
            else:
                app.append_log(f"SKU {sku}: Failed to create live listing", "red")
        except Exception as e:
            app.append_log(f"SKU {sku}: Error - {e}", "red")
    
    app.safe_after(0, app.populate_inventory_view)

threading.Thread(target=live_worker, daemon=True).start()

    def _handle_discogs_draft_success(self, listing_id):
"""Handle successful Discogs draft creation"""
messagebox.showinfo("Success", f"Successfully created Discogs DRAFT (Listing ID: {listing_id})")
if app.editing_sku:
    try:
        with app.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE inventory SET discogs_listing_id = ? WHERE sku = ?", (listing_id, app.editing_sku))
    except Exception as e:
        logger.error(f"Failed to update inventory with listing ID: {e}")

    def _handle_discogs_live_success(self, listing_id):
"""Handle successful Discogs live listing creation"""
messagebox.showinfo("Success", f"Successfully published LIVE to Discogs (Listing ID: {listing_id})")
if app.editing_sku:
    try:
        with app.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE inventory SET discogs_listing_id = ? WHERE sku = ?", (listing_id, app.editing_sku))
    except Exception as e:
        logger.error(f"Failed to update inventory with listing ID: {e}")

    def _prepare_ebay_listing_data(self, sku):
"""Prepare all eBay listing data from current form"""
format_val = app.entries["format"].get() or "LP"
media_cond_str = app.entries["media_condition"].get()

condition_enum = EBAY_INVENTORY_CONDITION_MAP.get(media_cond_str, "USED_GOOD")
condition_id_numeric = EBAY_CONDITION_MAP_NUMERIC.get(media_cond_str, "3000")
category_id = EBAY_VINYL_CATEGORIES.get(format_val, "176985")

ebay_title = app.entries["listing_title"].get() or f"{app.entries['artist'].get()} - {app.entries['title'].get()}"
description_html = app.full_desc.get("1.0", tk.END).strip()

return {
    "sku": sku,
    "title": ebay_title[:80],
    "description": description_html,
    "categoryId": str(category_id),
    "price": float(app.price_entry.get()),
    "quantity": 1,
    "condition_enum": condition_enum,
    "condition_id_numeric": condition_id_numeric,
    "media_condition": app.entries["media_condition"].get(),
    "sleeve_condition": app.entries["sleeve_condition"].get(),
    "currency": "GBP",
    "marketplaceId": app.config.get("marketplace_id", "EBAY_GB"),
    "paymentPolicyId": app.config.get("ebay_payment_policy_id"),
    "returnPolicyId": app.config.get("ebay_return_policy_id"),
    "shippingPolicyId": app.config.get("ebay_shipping_policy_id"),
    "images": app.image_paths,
}


    def refresh_button_states(self):
"""Refresh all button states based on current connection status"""
app._update_connection_status()
# Trigger inventory selection update if items are selected
if hasattr(self, 'inventory_tree') and app.inventory_tree.selection():
    app.on_inventory_selection()


    # ========================================================================
    # DUPLICATE PREVENTION SYSTEM
    # ========================================================================
    
    def _check_existing_listings(self, sku: str) -> dict:
"""Check what listings already exist for this SKU"""
try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ebay_listing_id, discogs_listing_id, ebay_item_draft_id, status 
            FROM inventory WHERE sku = ?
        """, (sku,))
        row = cursor.fetchone()
        
        if row:
            return {
                'ebay_listing_id': row[0],
                'discogs_listing_id': row[1], 
                'ebay_draft_id': row[2],
                'status': row[3],
                'has_ebay': bool(row[0]),
                'has_discogs': bool(row[1]),
                'has_ebay_draft': bool(row[2])
            }
        else:
            return {
                'ebay_listing_id': None,
                'discogs_listing_id': None,
                'ebay_draft_id': None,
                'status': None,
                'has_ebay': False,
                'has_discogs': False,
                'has_ebay_draft': False
            }
except Exception as e:
    logger.error(f"Error checking existing listings for {sku}: {e}")
    return {'has_ebay': False, 'has_discogs': False, 'has_ebay_draft': False}

    def _confirm_overwrite_action(self, platform: str, sku: str, existing_info: dict) -> bool:
"""Ask user to confirm if they want to overwrite/update existing listing"""
existing_ids = []
if platform.lower() == 'ebay':
    if existing_info.get('has_ebay'):
        existing_ids.append(f"Live eBay listing: {existing_info.get('ebay_listing_id')}")
    if existing_info.get('has_ebay_draft'):
        existing_ids.append(f"eBay draft: {existing_info.get('ebay_draft_id')}")
elif platform.lower() == 'discogs':
    if existing_info.get('has_discogs'):
        existing_ids.append(f"Discogs listing: {existing_info.get('discogs_listing_id')}")

if not existing_ids:
    return True  # No existing listings, safe to proceed

existing_text = "\n".join(existing_ids)
message = (
    f"SKU {sku} already has existing {platform} listing(s):\n\n"
    f"{existing_text}\n\n"
    f"Do you want to UPDATE the existing listing instead of creating a duplicate?\n\n"
    f"Choose 'Yes' to update existing listing\n"
    f"Choose 'No' to cancel and avoid duplicates"
)

return messagebox.askyesno(f"Existing {platform} Listing Found", message)

    def _safe_ebay_publish(self, sku: str, listing_data: dict, is_draft: bool = False) -> dict:
"""Safely publish to eBay with duplicate prevention"""
# Check for existing listings
existing = app._check_existing_listings(sku)

# Determine what action to take
action_type = "draft" if is_draft else "live"

if existing['has_ebay'] and not is_draft:
    # Has live listing, asking to publish live again
    if not app._confirm_overwrite_action('eBay', sku, existing):
        return {'success': False, 'cancelled': True, 'reason': 'User cancelled to avoid duplicate'}
    
    # User wants to update - modify existing listing
    app.append_log(f"SKU {sku}: Updating existing eBay listing {existing['ebay_listing_id']}", "blue")
    # Use existing eBay update logic here
    return app.ebay_api.create_draft_listing(listing_data)  # This handles updates
    
elif existing['has_ebay_draft'] and is_draft:
    # Has draft, asking to create another draft
    if not app._confirm_overwrite_action('eBay', sku, existing):
        return {'success': False, 'cancelled': True, 'reason': 'User cancelled to avoid duplicate'}
    
    app.append_log(f"SKU {sku}: Updating existing eBay draft", "blue")
    # Proceed with update
    
elif existing['has_ebay'] and is_draft:
    # Has live listing, wants to create draft - warn but allow
    message = (f"SKU {sku} already has a LIVE eBay listing.\n\n"
              f"Creating a draft will not affect the live listing.\n"
              f"Continue?")
    if not messagebox.askyesno("Live Listing Exists", message):
        return {'success': False, 'cancelled': True, 'reason': 'User cancelled'}

# Proceed with creation/update
result = app.ebay_api.create_draft_listing(listing_data)

# Log the action
if result.get('success'):
    action_desc = "draft saved" if is_draft else "published live"
    app.append_log(f"SKU {sku}: eBay listing {action_desc} successfully", "green")

return result

    def _safe_discogs_publish(self, sku: str, listing_data: dict, is_draft: bool = False) -> int:
"""Safely publish to Discogs with duplicate prevention"""
existing = app._check_existing_listings(sku)

if existing['has_discogs']:
    if not app._confirm_overwrite_action('Discogs', sku, existing):
        app.append_log(f"SKU {sku}: Discogs publish cancelled to avoid duplicate", "orange")
        return None
    
    # User wants to update existing listing
    discogs_id = existing['discogs_listing_id']
    app.append_log(f"SKU {sku}: Updating existing Discogs listing {discogs_id}", "blue")
    
    # Update instead of create
    success = app.discogs_api.update_listing(discogs_id, listing_data)
    if success:
        app.append_log(f"SKU {sku}: Discogs listing updated successfully", "green")
        return discogs_id
    else:
        app.append_log(f"SKU {sku}: Failed to update Discogs listing", "red") 
        return None

# No existing listing, safe to create new
action_desc = "draft" if is_draft else "live listing"
app.append_log(f"SKU {sku}: Creating new Discogs {action_desc}", "black")

listing_id = app.discogs_api.create_listing(listing_data)
if listing_id:
    app.append_log(f"SKU {sku}: Discogs {action_desc} created successfully (ID: {listing_id})", "green")

return listing_id


    def log_sync_activity(self, message):
"""Log sync activity to the text widget"""
def do_log():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    app.sync_log_text.config(state="normal")
    app.sync_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
    app.sync_log_text.see(tk.END)
    app.sync_log_text.config(state="disabled")
app.safe_after(0, do_log)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    if sys.version_info < (3, 7):
messagebox.showerror("Unsupported Python Version", "This application requires Python 3.7 or higher.")
sys.exit(1)

    try:
# Before starting, check for requests_toolbelt
try:
    import requests_toolbelt
except ImportError:
     messagebox.showerror("Missing Dependency", "The 'requests-toolbelt' library is required for this version.\n\nPlease install it by running:\npip install requests-toolbelt")
     sys.exit(1)

root = tk.Tk()
app = VinylToolApp(root)
root.mainloop()
    except Exception as e:
# Create a simple Tk window to show the error if the main app fails
try:
    root = tk.Tk()
    root.withdraw() # Hide the main window
    messagebox.showerror("Fatal Application Error", f"A critical error occurred:\n\n{e}\n\n{traceback.format_exc()}")
except:
    # Fallback to console if GUI fails completely
    print(f"FATAL ERROR: {e}\n{traceback.format_exc()}")
sys.exit(1)

# --- Auto-backup on exit (active profile + core files) ---
import atexit, tarfile, datetime, json
from pathlib import Path as _Path

def _auto_backup_to_backups_dir():
    try:
src_dir = _Path(__file__).resolve().parent
backups = src_dir / "backups"
backups.mkdir(exist_ok=True)
active_profile = "dev"
active_file = src_dir / "profiles" / "active_profile.json"
try:
    data = json.loads(active_file.read_text())
    if isinstance(data, dict) and data.get("profile"):
        active_profile = str(data["profile"])
except Exception:
    pass
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
fname = backups / f"backup_{ts}.tar.gz"
with tarfile.open(fname, "w:gz") as tar:
    for name in ["config.json","api_clients.py","inventory.db","geometry.conf"]:
        p = src_dir / name
        if p.exists():
            tar.add(p, arcname=p.name)
    prof = src_dir / "profiles" / active_profile / "data"
    if prof.exists():
        tar.add(prof, arcname=f"profiles/{active_profile}/data")
print(f"[AutoBackup] Saved {fname}")
    except Exception as e:
print("[AutoBackup] Failed:", e)

atexit.register(_auto_backup_to_backups_dir)
# --- End auto-backup ---


def import_worker(app):
try:
    inventory = app.discogs_api.get_inventory()
    app.safe_after(0, lambda: app._process_discogs_import(inventory))
except Exception as e:
    app.safe_after(0, lambda: messagebox.showerror("Import Error", str(e)))
finally:
    app.safe_after(0, lambda: app.root.config(cursor=""))
        threading.Thread(target=import_worker, daemon=True).start()
    
    def _process_discogs_import(self, inventory):
        """Process Discogs import"""
        new_items, skipped_items = 0, 0
        try:
with app.db.get_connection() as conn:
    cursor = conn.cursor()
    for listing in inventory:
        if listing.status != 'For Sale': continue
        cursor.execute("SELECT COUNT(*) FROM inventory WHERE discogs_listing_id = ?", (listing.id,))
        if cursor.fetchone()[0] > 0:
            skipped_items += 1
            continue
        new_items += 1
        artist = listing.release.artists[0].name if listing.release.artists else "Various"
        title = listing.release.title.replace(f"{artist} - ", "", 1).strip()
        sku = datetime.datetime.now().strftime(f"%Y%m%d-%H%M%S-{new_items}")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sql = """INSERT INTO inventory (sku, artist, title, cat_no, media_condition, sleeve_condition, price, status, discogs_release_id, discogs_listing_id, date_added, last_modified) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        media_cond = DISCOGS_GRADE_MAP.get(listing.condition, listing.condition)
        sleeve_cond = DISCOGS_GRADE_MAP.get(listing.sleeve_condition, listing.sleeve_condition)
        catno = getattr(listing.release, 'catno', '')
        cursor.execute(sql, (sku, artist, title, catno, media_cond, sleeve_cond, listing.price.value, "For Sale", listing.release.id, listing.id, now, now))
messagebox.showinfo("Import Complete", f"Successfully imported {new_items} new item(s).\nSkipped {skipped_items} existing item(s).")
app.populate_inventory_view()
        except Exception as e:
logger.error(f"Import failed: {e}")
messagebox.showerror("Import Error", f"An error occurred during import:\n{e}")
    
    def toggle_auto_sync(self):
        """Toggle automatic sync"""
        if not app.discogs_api.is_connected():
messagebox.showwarning("Not Connected", "Please connect to your Discogs account first.")
app.auto_sync_var.set(False)
return
        app.auto_sync_enabled = app.auto_sync_var.get()
        app.config.save({"auto_sync_enabled": app.auto_sync_enabled})
        if app.auto_sync_enabled: app.start_auto_sync()
        else: app.stop_auto_sync()
    
    def toggle_two_way_sync(self):
        """Toggle two-way sync"""
        app.two_way_sync_enabled = app.two_way_sync_var.get()
        app.config.save({"two_way_sync_enabled": app.two_way_sync_enabled})
        app.log_sync_activity(f"Two-way sync {'enabled' if app.two_way_sync_enabled else 'disabled'}")
    
    def toggle_attempt_updates(self):
        """Toggle attempt to update Discogs"""
        app.attempt_discogs_updates = app.attempt_updates_var.get()
        app.config.save({"attempt_discogs_updates": app.attempt_discogs_updates})
        app.log_sync_activity(f"Discogs update attempts {'enabled' if app.attempt_discogs_updates else 'disabled'}")
    
    def update_sync_interval(self):
        """Update sync interval"""
        try:
minutes = int(app.sync_interval_var.get())
app.auto_sync_interval = minutes * 60
app.config.save({"auto_sync_interval": app.auto_sync_interval})
app.log_sync_activity(f"Sync interval set to {minutes} minutes")
        except ValueError: app.sync_interval_var.set("5")
    
    def start_auto_sync(self):
        """Start automatic sync"""
        if app.auto_sync_thread and app.auto_sync_thread.is_alive(): return
        app.auto_sync_stop_event.clear()
        app.auto_sync_thread = threading.Thread(target=app._auto_sync_worker, daemon=True)
        app.auto_sync_thread.start()
        app.sync_status_var.set("Auto-sync enabled - waiting for next sync...")
        app.log_sync_activity("Automatic sync started")
    
    def stop_auto_sync(self):
        """Stop automatic sync"""
        app.auto_sync_stop_event.set()
        app.sync_status_var.set("Auto-sync disabled")
        app.log_sync_activity("Automatic sync stopped")
    
    def _auto_sync_worker(self):
        """Auto sync worker thread"""
        while not app.auto_sync_stop_event.is_set():
try:
    if app.auto_sync_stop_event.wait(app.auto_sync_interval): break
    if app.auto_sync_enabled and app.discogs_api.is_connected():
        app.safe_after(0, lambda: app.sync_status_var.set("Syncing inventory..."))
        sync_result = app._perform_inventory_sync()
        app.safe_after(0, lambda r=sync_result: app._handle_sync_result(r))
except Exception as e:
    app.safe_after(0, lambda msg=f"Auto-sync error: {e}": app.log_sync_activity(msg))
    
    def manual_sync_now(self):
        """Perform manual sync now"""
        if not app.discogs_api.is_connected():
messagebox.showwarning("Not Connected", "Please connect to your Discogs account first.")
return
        app.sync_status_var.set("Manual sync in progress...")
        app.root.config(cursor="watch"); app.root.update()
        def sync_worker():
try:
    result = app._perform_inventory_sync()
    app.safe_after(0, lambda: app._handle_sync_result(result))
except Exception as e:
    app.safe_after(0, lambda: messagebox.showerror("Sync Error", str(e)))
finally:
    app.safe_after(0, lambda: app.root.config(cursor=""))
        threading.Thread(target=sync_worker, daemon=True).start()
    
    def _perform_inventory_sync(self):
        """Implements true "latest-wins" two-way sync logic."""
        sync_start_time = datetime.datetime.now(datetime.timezone.utc)
        app.log_sync_activity("=== STARTING SYNC (Latest-Wins) ===")
        try:
discogs_inventory = app.discogs_api.get_inventory()
discogs_map = {listing.id: listing for listing in discogs_inventory}
app.log_sync_activity(f"Retrieved {len(discogs_inventory)} active listings from Discogs.")

with app.db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT sku, discogs_listing_id, price, status, notes, last_modified, last_sync_time FROM inventory WHERE discogs_listing_id IS NOT NULL")
    local_items = [dict(row) for row in cursor.fetchall()]
    local_map = {item['discogs_listing_id']: item for item in local_items}
app.log_sync_activity(f"Found {len(local_map)} linked local items.")

updates_to_local, updates_to_discogs, deletions_from_local, new_sales = 0, 0, 0, 0

for local_item in local_items:
    listing_id, last_mod_local_str, last_sync_str = local_item['discogs_listing_id'], local_item.get('last_modified'), app.last_successful_sync_time or local_item.get('last_sync_time')
    if not last_mod_local_str or not last_sync_str: continue
    try:
        last_mod_local, last_sync = datetime.datetime.fromisoformat(last_mod_local_str), datetime.datetime.fromisoformat(last_sync_str)
    except (ValueError, TypeError): continue

    if last_mod_local > last_sync and app.attempt_discogs_updates:
        if listing_id in discogs_map:
            app.log_sync_activity(f"→ Local change detected for SKU {local_item['sku']}. Pushing to Discogs.")
            update_payload = {"price": local_item['price'], "status": app._map_local_to_discogs_status(local_item['status']), "comments": local_item.get('notes', '')}
            if app.discogs_api.update_listing(listing_id, update_payload):
                updates_to_discogs += 1; app.log_sync_activity(f"  ✓ Pushed update for SKU {local_item['sku']} to Discogs.")
            else: app.log_sync_activity(f"  ✗ Failed to push update for SKU {local_item['sku']}.")
        else: app.log_sync_activity(f"  - SKU {local_item['sku']} changed locally but no longer on Discogs. Skipping push.")

    elif listing_id in discogs_map:
        listing = discogs_map[listing_id]
        mapped_status = app.status_mappings.get(listing.status, "Not For Sale")
        if mapped_status != local_item['status']:
            with app.db.get_connection() as conn:
                conn.cursor().execute("UPDATE inventory SET status = ?, last_modified = ? WHERE discogs_listing_id = ?", (mapped_status, sync_start_time.isoformat(), listing_id))
            updates_to_local += 1
            if mapped_status == 'Sold' and local_item['status'] != 'Sold': new_sales += 1
            app.log_sync_activity(f"✓ Sync from Discogs: SKU {local_item['sku']} '{local_item['status']}' → '{mapped_status}'")

ids_to_delete_locally = set(local_map.keys()) - set(discogs_map.keys())
if ids_to_delete_locally:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        for listing_id in ids_to_delete_locally:
            if local_map[listing_id]['status'] == 'For Sale':
                sku = local_map[listing_id]['sku']
                cursor.execute("DELETE FROM inventory WHERE discogs_listing_id = ?", (listing_id,))
                deletions_from_local += 1
                app.log_sync_activity(f"✓ Deleted SKU {sku} locally as it's no longer on Discogs.")

with app.db.get_connection() as conn:
    conn.cursor().execute("UPDATE inventory SET last_sync_time = ? WHERE discogs_listing_id IS NOT NULL", (sync_start_time.isoformat(),))
app.last_successful_sync_time = sync_start_time.isoformat()
app.config.save({"last_successful_sync_time": app.last_successful_sync_time})
if updates_to_local > 0 or deletions_from_local > 0: app.safe_after(0, app.populate_inventory_view)
app.log_sync_activity("=== SYNC COMPLETED ===")
return {'success': True, 'updates_local': updates_to_local, 'updates_discogs': updates_to_discogs, 'deletions': deletions_from_local, 'new_sales': new_sales, 'total_checked': len(discogs_inventory)}
        except Exception as e:
logger.error(f"Sync failed: {e}", exc_info=True)
app.log_sync_activity(f"✗ SYNC ERROR: {e}")
return {'success': False, 'error': str(e)}

    def _map_local_to_discogs_status(self, local_status):
        """Map local status to valid Discogs status"""
        return {'For Sale': 'For Sale', 'Sold': 'Sold'}.get(local_status, 'Draft')
    
    def _handle_sync_result(self, result):
        """Handle sync result"""
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        if result.get('success'):
updates_local, updates_discogs, deletions = result.get('updates_local', 0), result.get('updates_discogs', 0), result.get('deletions', 0)
total_changes = updates_local + updates_discogs + deletions
if total_changes > 0:
    log_msg = f"[{current_time}] Sync completed: {total_changes} changes from {result['total_checked']} listings"
    if updates_local > 0: log_msg += f"\n  - Pulled from Discogs: {updates_local}"
    if updates_discogs > 0: log_msg += f"\n  - Pushed to Discogs: {updates_discogs}"
    if deletions > 0: log_msg += f"\n  - Items deleted locally: {deletions}"
    if result.get('new_sales', 0) > 0: log_msg += f"\n  - New sales detected: {result['new_sales']}"
    app.log_sync_activity(log_msg)
    status_msg = f"Sync complete - {total_changes} change(s)"
else:
    status_msg = "Sync complete - no changes needed"
    app.log_sync_activity(f"[{current_time}] Sync completed. No changes needed.")
app.sync_status_var.set(f"Last sync: {current_time}. {status_msg}")
        else:
app.sync_status_var.set(f"Last sync: {current_time}. FAILED.")
app.log_sync_activity(f"[{current_time}] Sync FAILED: {result.get('error')}")

    # ========================================================================
    # ENHANCED PUBLISHING ACTION METHODS
    # ========================================================================
    
    def action_ebay_save_unpublished(self):
        """Save eBay listing data locally as 'ready to publish' without sending to eBay"""
        if app.notebook.tab(app.notebook.select(), "text") == "Lister":
# From Lister tab - save current form
app._save_ebay_draft_from_lister()
        else:
# From Inventory tab - mark selected items as ready for eBay
app._save_ebay_draft_from_inventory()

    def action_ebay_publish_live(self):
        """Publish directly to eBay as live listings (Inventory API)"""
        if app.notebook.tab(app.notebook.select(), "text") == "Lister":
# From Lister tab - publish current form directly
app.list_on_ebay()
        else:
# From Inventory tab - publish selected items
app.publish_to_ebay()



    def reconcile_from_ebay(self, skus):


        """Pull eBay state back into local DB so deletions/ends/relists are reflected.


        Chooses ACTIVE offer. Prefers Item ID (listingId); falls back to offerId if listingId hasn't propagated yet.


        Refreshes the grid when done.


        """


        import datetime, logging, requests


        logger = logging.getLogger(__name__)


    


        token = app.ebay_api.get_access_token()


        if not token:


app.append_log("Cannot reconcile: missing eBay token", "red")


return


    


        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}


        changed = False


    


        for sku in (skus or []):


try:


    url = f"{app.ebay_api.base_url}/sell/inventory/v1/offer?sku={sku}"


    r = requests.get(url, headers=headers, timeout=30)


    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()


    


    if r.status_code == 200 and r.json().get("offers"):


        offers = r.json()["offers"]


        # Pick ACTIVE offer if available; otherwise first one


        active = None


        for o in offers:


            if (o.get("status") or "").upper() == "ACTIVE":


                active = o


                break


        offer = active or offers[0]


        status = (offer.get("status") or "").upper()


    


        listing_id = offer.get('legacyItemId') or offer.get('listingId') or (offer.get('listing') or {}).get('legacyItemId') or (offer.get('listing') or {}).get('listingId')


        offer_id = offer.get("offerId") or (offer.get("offer") or {}).get("offerId")


    


        # If ACTIVE but listingId missing, try GET /offer/{offerId} to resolve


        if status in ("ACTIVE","PUBLISHED") and not listing_id and offer_id:


            try:


                resolved = app.ebay_api.get_offer(str(offer_id))


                if resolved.get("success"):


                    listing_id = resolved.get('legacyItemId') or (resolved.get('listing') or {}).get('legacyItemId') or resolved.get('listingId') or (resolved.get('listing') or {}).get('listingId')


            except Exception as e:


                logger.warning(f"[reconcile] get_offer failed for offer {offer_id}: {e}")


    


        with app.db.get_connection() as conn:


            c = conn.cursor()


            if status in ("ACTIVE","PUBLISHED"):


                stored_id = listing_id or (offer_id if offer_id else None)


                if stored_id:


                    c.execute("UPDATE inventory SET ebay_listing_id = ?, ebay_updated_at = ? WHERE sku = ?", (stored_id, now_iso, sku))


                    changed = True


                else:


                    c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


                    changed = True


            else:


                c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


                changed = True


    


        shown = listing_id or (offer_id if (status in ("ACTIVE","PUBLISHED") and offer_id) else "—")


        label = "Item ID" if listing_id else ("Offer ID" if shown != "—" else "—")  # live


        app.append_log(f"SKU {sku}: reconciled from eBay ({status}; {label}={shown})", "blue")


    else:


        with app.db.get_connection() as conn:


            c = conn.cursor()


            c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


        changed = True


        app.append_log(f"SKU {sku}: no eBay offer found; cleared local mapping.", "orange")


    


except Exception as e:


    logger.error(f"Reconcile error for {sku}: {e}")


    app.append_log(f"SKU {sku}: reconcile failed: {e}", "red")


    


        if changed:


try:


    app.populate_inventory_view()


except Exception:


    pass



    def action_open_on_ebay_selected(self):



        """Open the selected item's eBay listing in the browser using stored Item ID."""



        import webbrowser, requests, logging



        logger = logging.getLogger(__name__)



        items = app.inventory_tree.selection()



        if not items:



try:



    messagebox.showinfo("Open on eBay", "Please select a row first.")



except Exception:



    pass



return



        iid = items[0]



        vals = app.inventory_tree.item(iid, "values") or []



        item_id = None



        # Try visible column first



        try:



headers = [app.inventory_tree.heading(c)["text"] for c in app.inventory_tree["columns"]]



if "eBay ID" in headers:



    idx = headers.index("eBay ID")



    if idx < len(vals):



        item_id = vals[idx]



        except Exception:



item_id = None



        # Fallback: DB lookup by SKU (assumes SKU in first column)



        if not item_id and vals:



sku = vals[0]



try:



    with app.db.get_connection() as conn:



        c = conn.cursor()



        c.execute("SELECT ebay_listing_id FROM inventory WHERE sku = ?", (sku,))



        row = c.fetchone()



        if row and row[0]:



            item_id = row[0]



except Exception:



    pass



        if not item_id:



try:



    messagebox.showinfo("Open on eBay", "No eBay Item ID stored for the selected row.")



except Exception:



    pass



return



        # If it's likely an offerId, try resolve to listingId on the fly



        if not (str(item_id).isdigit() and len(str(item_id)) >= 12) and vals:



try:



    token = app.ebay_api.get_access_token()



    if token:



        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}



        url = f"{app.ebay_api.base_url}/sell/inventory/v1/offer?sku={{vals[0]}}"



        r = requests.get(url, headers=headers, timeout=30)



        if r.status_code == 200 and r.json().get("offers"):



            offers = r.json()["offers"]



            active = None



            for o in offers:



                if (o.get("status") or "").upper() == "ACTIVE":



                    active = o



                    break



            off = active or offers[0]



            lid = off.get('legacyItemId') or off.get('listingId') or (off.get('listing') or {}).get('legacyItemId') or (off.get('listing') or {}).get('listingId')



            if not lid:



                oid = off.get("offerId") or (off.get("offer") or {}).get("offerId")



                if oid:



                    resolved = app.ebay_api.get_offer(str(oid))



                    if resolved.get("success"):



                        lid = resolved.get('legacyItemId') or (resolved.get('listing') or {}).get('legacyItemId') or resolved.get('listingId') or (resolved.get('listing') or {}).get('listingId')



            if lid:



                item_id = lid



except Exception as e:



    logger.warning(f"[open] resolution failed: {e}")



        try:



webbrowser.open_new_tab(f"https://www.ebay.co.uk/itm/{item_id}")



        except Exception:



try:



    messagebox.showerror("Open on eBay", "Failed to open browser.")



except Exception:



    pass




    # ------------------------------




    # eBay → Discogs Import (Wizard)




    # ------------------------------




    def action_import_from_ebay(self):




        try:




offers = app._fetch_all_ebay_offers()




        except Exception as e:




messagebox.showerror("Import from eBay", f"Failed to fetch eBay offers:\n{e}")




return




        work = []




        with app.db.get_connection() as conn:




c = conn.cursor()




for off in offers:




    sku = (off.get("sku") or "").strip()




    if not sku:




        continue




    c.execute("SELECT discogs_listing_id FROM inventory WHERE sku = ?", (sku,))




    row = c.fetchone()




    if not row or not row[0]:




        work.append(off)




        if not work:




messagebox.showinfo("Import from eBay", "No eligible eBay listings found (all mapped).")




return




        app._start_import_wizard(work)




    




    def _fetch_all_ebay_offers(self):




        token = app.ebay_api.get_access_token()




        if not token:




raise RuntimeError("Missing eBay token")




        import requests




        hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}




        base = f"{app.ebay_api.base_url}/sell/inventory/v1/offer"




        offers, limit, offset = [], 200, 0




        while True:




resp = requests.get(f"{base}?limit={limit}&offset={offset}", headers=hdrs, timeout=30)




if resp.status_code != 200:




    raise RuntimeError(f"eBay API error {resp.status_code}: {resp.text[:300]}")




data = resp.json()




batch = data.get("offers") or []




for o in batch:




    aspects = (o.get("aspects") or {})




    gtin = None




    for k in ("EAN","UPC","GTIN","ean","upc","gtin"):




        v = aspects.get(k)




        if isinstance(v, list) and v:




            gtin = v[0]; break




        if isinstance(v, str) and v.strip():




            gtin = v.strip(); break




    if not gtin:




        prod = o.get("product") or {}




        g = prod.get("gtin")




        if isinstance(g, list) and g:




            gtin = g[0]




        elif isinstance(g, str):




            gtin = g




    offers.append({




        "sku": o.get("sku"),




        "title": o.get("title") or (o.get("name") or ""),




        "offerId": o.get("offerId") or (o.get("offer") or {}).get("offerId"),




        "listingId": o.get("legacyItemId") or o.get("listingId") or (o.get("listing") or {}).get("legacyItemId") or (o.get("listing") or {}).get("listingId"),




        "price": ((o.get("pricingSummary") or {}).get("price") or {}).get("value"),




        "currency": ((o.get("pricingSummary") or {}).get("price") or {}).get("currency"),




        "quantity": o.get("availableQuantity"),




        "status": (o.get("status") or "").upper(),




        "gtin": (gtin or "").strip(),




        "catno": (aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No") or [""])[0] if isinstance(aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No"), list) else (aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No") or ""),




        "label": (aspects.get("Record Label") or aspects.get("Label") or [""])[0] if isinstance(aspects.get("Record Label") or aspects.get("Label"), list) else (aspects.get("Record Label") or aspects.get("Label") or ""),




        "format": (aspects.get("Format") or [""])[0] if isinstance(aspects.get("Format"), list) else (aspects.get("Format") or ""),




        "country": (aspects.get("Country/Region of Manufacture") or [""])[0] if isinstance(aspects.get("Country/Region of Manufacture"), list) else (aspects.get("Country/Region of Manufacture") or ""),




        "year": (aspects.get("Release Year") or [""])[0] if isinstance(aspects.get("Release Year"), list) else (aspects.get("Release Year") or ""),




    })




total = data.get("total", 0)




offset += len(batch)




if offset >= total or not batch:




    break




        return offers




    




    def _start_import_wizard(self, offers):




        app._import_offers = [o for o in offers]




        app._import_idx = 0




        win = tk.Toplevel(app.root)




        win.title("Import from eBay → Discogs match")




        win.geometry("720x520")




        app._import_win = win




        app._imp_hdr = tk.Label(win, text="", font=("Helvetica", 14, "bold"))




        app._imp_hdr.pack(anchor="w", padx=12, pady=(10, 6))




        app._imp_info = tk.Text(win, height=10, wrap="word")




        app._imp_info.pack(fill="x", padx=12)




        app._imp_status = tk.Label(win, text="", fg="gray")




        app._imp_status.pack(anchor="w", padx=12, pady=6)




        btns = tk.Frame(win)




        btns.pack(fill="x", padx=12, pady=8)




        tk.Button(btns, text="Accept", command=app._import_accept).pack(side="left", padx=4)




        tk.Button(btns, text="See Alternatives…", command=app._import_alternatives).pack(side="left", padx=4)




        tk.Button(btns, text="Skip", command=app._import_skip).pack(side="left", padx=4)




        tk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=4)




        app._import_propose_current()




    




    def _import_propose_current(self):




        if app._import_idx >= len(app._import_offers):




try:




    app.populate_inventory_view()




except Exception:




    pass




messagebox.showinfo("Import from eBay", "Done.")




app._import_win.destroy()




return




        o = app._import_offers[app._import_idx]




        sku = o.get("sku") or ""




        title = o.get("title") or ""




        gtin = o.get("gtin") or ""




        catno = o.get("catno") or ""




        label = o.get("label") or ""




        fmt = o.get("format") or ""




        app._imp_hdr.config(text=f"SKU {sku} — {title}")




        app._imp_info.delete("1.0", "end")




        app._imp_info.insert("end", f"eBay ID: {o.get('listingId') or o.get('offerId')}\n")




        app._imp_info.insert("end", f"GTIN/Barcode: {gtin or '—'}\n")




        app._imp_info.insert("end", f"Cat No: {catno or '—'}\n")




        app._imp_info.insert("end", f"Label: {label or '—'} | Format: {fmt or '—'}\n\n")




        try:




cands = app._discogs_find_candidates(gtin=gtin, catno=catno, title=title, label=label or None)




        except Exception as e:




app._imp_status.config(text=f"Discogs search failed: {e}")




app._import_candidates = []




return




        app._import_candidates = cands




        if not cands:




app._imp_status.config(text="No candidates found. Click ‘See Alternatives…’ to search manually.")




        else:




top = cands[0]




app._imp_status.config(text=f"Proposed: {top['artist']} – {top['title']} [{top['label']} • {top['year']} • {top['country']}]  ({top['method']}, {int(top['confidence']*100)}%)")




    




    def _discogs_find_candidates(self, gtin: str = "", catno: str = "", title: str = "", label: str = None):




        results = []




        if gtin:




res = app.discogs_client.search(barcode=gtin, type="release", format="Vinyl")




for r in list(res)[:10]:




    results.append({"release_id": r.id, "title": r.title,




        "artist": getattr(r, "artist", getattr(r, "artists", "")),




        "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




        "year": getattr(r, "year", "") or "",




        "country": getattr(r, "country", "") or "",




        "method": "barcode", "confidence": 1.0})




        if catno:




res = app.discogs_client.search(catno=catno, type="release", format="Vinyl")




for r in list(res)[:10]:




    results.append({"release_id": r.id, "title": r.title,




        "artist": getattr(r, "artist", getattr(r, "artists", "")),




        "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




        "year": getattr(r, "year", "") or "",




        "country": getattr(r, "country", "") or "",




        "method": "catno", "confidence": 0.85 if not label else 0.9})




        if (not results) and title:




res = app.discogs_client.search(title=title, type="release", format="Vinyl", label=label or None)




for r in list(res)[:10]:




    results.append({"release_id": r.id, "title": r.title,




        "artist": getattr(r, "artist", getattr(r, "artists", "")),




        "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




        "year": getattr(r, "year", "") or "",




        "country": getattr(r, "country", "") or "",




        "method": "fuzzy", "confidence": 0.6})




        seen, ranked = set(), []




        for r in sorted(results, key=lambda x: x["confidence"], reverse=True):




if r["release_id"] in seen: continue




seen.add(r["release_id"]); ranked.append(r)




        return ranked




    




    def _import_accept(self):




        if app._import_idx >= len(app._import_offers): return




        o = app._import_offers[app._import_idx]




        top = (app._import_candidates[0] if app._import_candidates else None)




        if not top:




messagebox.showinfo("Import from eBay", "No candidate to accept for this item."); return




        sku = (o.get("sku") or "").strip()




        now_iso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()




        with app.db.get_connection() as conn:




c = conn.cursor()




c.execute("SELECT 1 FROM inventory WHERE sku = ?", (sku,))




exists = c.fetchone() is not None




if exists:




    c.execute("""UPDATE inventory




                 SET discogs_listing_id = ?,




                     discogs_match_method = ?, discogs_match_confidence = ?,




                     barcode = COALESCE(?, barcode),




                     inv_updated_at = ?




                 WHERE sku = ?""", 




              (str(top["release_id"]), top["method"], float(top["confidence"]),




               (o.get("gtin") or None), now_iso, sku))




else:




    c.execute("""INSERT INTO inventory




                 (sku, artist, title, price, status, ebay_listing_id, discogs_listing_id,




                  barcode, discogs_match_method, discogs_match_confidence, inv_updated_at, date_added)




                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 




              (sku, "", o.get("title") or "", o.get("price") or 0.0, "For Sale",




               (o.get("listingId") or None), str(top["release_id"]),




               (o.get("gtin") or None), top["method"], float(top["confidence"]), now_iso, now_iso))




        app.append_log(f"Imported {sku} → Discogs {top['release_id']} ({top['method']}, {int(top['confidence']*100)}%)", "green")




        app._import_idx += 1




        app._import_propose_current()




    




    def _import_alternatives(self):




        if not app._import_candidates:




messagebox.showinfo("Alternatives", "No candidates available for this item."); return




        top = tk.Toplevel(app._import_win); top.title("Choose a Discogs release")




        lb = tk.Listbox(top, width=90, height=10)




        for i, r in enumerate(app._import_candidates[:12]):




lb.insert("end", f"{i+1}. {r['artist']} – {r['title']}  [{r['label']} • {r['year']} • {r['country']}]  ({r['method']}, {int(r['confidence']*100)}%)")




        lb.pack(fill="both", expand=True)




        def choose():




idx = lb.curselection()




if not idx: return




i = idx[0]




chosen = app._import_candidates[i]




rest = [r for j,r in enumerate(app._import_candidates) if j != i]




app._import_candidates = [chosen] + rest




top.destroy()




app._imp_status.config(text=f"Chosen: {chosen['artist']} – {chosen['title']} [{chosen['label']} • {chosen['year']} • {chosen['country']}]  ({chosen['method']}, {int(chosen['confidence']*100)}%)")




        tk.Button(top, text="Use Selected", command=choose).pack(pady=6)




    




    def _import_skip(self):




        app._import_idx += 1




        app._import_propose_current()





    def action_ebay_sync_selected(self):

        """Sync selected inventory SKUs from eBay into local DB (status/listingId)."""

        items = app.inventory_tree.selection()

        if not items:

try:

    messagebox.showinfo("Sync from eBay", "Please select one or more items in the inventory list.")

except Exception:

    pass

return

        skus = []

        for iid in items:

vals = app.inventory_tree.item(iid, "values")

if not vals:

    continue

skus.append(vals[0])

        try:

app.reconcile_from_ebay(skus)

        except Exception as e:

try:

    messagebox.showerror("Sync from eBay", f"Failed to sync: {e}")

except Exception:

    pass


    def action_discogs_save_unpublished(self):
        """Create Discogs draft listings"""
        if app.notebook.tab(app.notebook.select(), "text") == "Lister":
app._create_discogs_draft_from_lister()
        else:
app._create_discogs_draft_from_inventory()

    def action_discogs_publish_live(self):
        """Create live Discogs listings"""
        if app.notebook.tab(app.notebook.select(), "text") == "Lister":
# Create live listing instead of draft
app._list_on_discogs_live()
        else:
# Modify existing publish_to_discogs to use "For Sale" status
app._publish_to_discogs_live()

    def _save_ebay_draft_from_lister(self):
        """Save current lister form as eBay-ready in database with duplicate checking"""
        try:
# Validate required fields
required_fields = ['artist', 'title', 'media_condition']
for field in required_fields:
    if not app.entries[field.replace(' ', '_')].get().strip():
        messagebox.showwarning("Validation Error", f"Please enter {field}")
        return

try:
    price = float(app.price_entry.get())
    if price <= 0:
        messagebox.showwarning("Validation Error", "Please enter a valid price")
        return
except (ValueError, TypeError):
    messagebox.showwarning("Validation Error", "Please enter a valid price")
    return

# Generate SKU if needed
sku = app.editing_sku or app.sku_display_var.get() or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
if not app.editing_sku and not app.temporary_sku:
    app.sku_display_var.set(sku)

# Check for existing listings and warn user
existing = app._check_existing_listings(sku)
if existing['has_ebay'] or existing['has_ebay_draft']:
    warning_parts = []
    if existing['has_ebay']:
        warning_parts.append(f"Live eBay listing: {existing['ebay_listing_id']}")
    if existing['has_ebay_draft']:
        warning_parts.append(f"eBay draft: {existing['ebay_draft_id']}")
    
    warning_text = "\n".join(warning_parts)
    message = (f"SKU {sku} already has:\n\n{warning_text}\n\n"
              f"This will update the existing record. Continue?")
    
    if not messagebox.askyesno("Existing eBay Data Found", message):
        return

# Save to database with special status
payload_json = json.dumps(app._serialize_form_to_payload())

try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        if app.editing_sku:
            # Update existing
            cursor.execute("""
                UPDATE inventory SET 
                status = 'eBay Ready',
                last_modified = ?,
                lister_payload = ?
                WHERE sku = ?
            """, (now_iso, payload_json, sku))
            message = f"Updated SKU {sku} as ready for eBay"
        else:
            # Create new with basic info
            cursor.execute("""
                INSERT INTO inventory (
                    sku, artist, title, price, status, date_added, 
                    last_modified, lister_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sku,
                app.entries["artist"].get().strip(),
                app.entries["title"].get().strip(), 
                price,
                'eBay Ready',
                now_iso,
                now_iso,
                payload_json
            ))
            message = f"Saved SKU {sku} as ready for eBay"
        
        app.populate_inventory_view()
        app.append_log(message, "green")
        messagebox.showinfo("eBay Draft Saved", 
            f"{message}\n\n" +
            f"Note: This creates a local draft in your database.\n" + 
            f"eBay doesn't provide draft functionality via their public API.\n" +
            f"Use 'Publish Live' when ready to list on eBay.")
        
except Exception as e:
    logger.error(f"Failed to save eBay draft: {e}")
    messagebox.showerror("Database Error", f"Failed to save: {e}")
    
        except Exception as e:
logger.error(f"Error in _save_ebay_draft_from_lister: {e}")
messagebox.showerror("Error", f"An error occurred: {e}")

    def _save_ebay_draft_from_inventory(self):
        """Mark selected inventory items as ready for eBay"""
        selected = app.inventory_tree.selection()
        if not selected:
messagebox.showwarning("No Selection", "Please select items to prepare for eBay")
return
        
        try:
with app.db.get_connection() as conn:
    cursor = conn.cursor()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    updated_count = 0
    for item in selected:
        sku = app.inventory_tree.item(item, "values")[0]
        cursor.execute("""
            UPDATE inventory SET 
            status = 'eBay Ready',
            last_modified = ?
            WHERE sku = ?
        """, (now_iso, sku))
        updated_count += 1
    
    app.populate_inventory_view()
    message = f"Marked {updated_count} item(s) as ready for eBay"
    app.append_log(message, "green")
    messagebox.showinfo("Success", message)
    
        except Exception as e:
logger.error(f"Failed to mark items as eBay ready: {e}")
messagebox.showerror("Database Error", f"Failed to update items: {e}")

    def _create_discogs_draft_from_lister(self):
        """Create Discogs draft from current lister form"""
        if not app.discogs_api.is_connected():
messagebox.showwarning("Not Connected", "Please connect to Discogs first")
return

        if not app.current_release_id:
messagebox.showerror("Missing Release", "You must select a specific Discogs release variant first")
return

        try:
price = float(app.price_entry.get())
media_condition = app.entries["media_condition"].get()
if not media_condition or media_condition not in REVERSE_GRADE_MAP:
    messagebox.showwarning("Validation Error", "Please select a valid media condition")
    return
        except (ValueError, TypeError):
messagebox.showwarning("Validation Error", "Please enter a valid price")
return
        
        listing_data = {
'release_id': app.current_release_id,
'price': price,
'status': 'Draft',  # Explicitly set as draft
'condition': REVERSE_GRADE_MAP.get(media_condition),
'sleeve_condition': REVERSE_GRADE_MAP.get(app.entries["sleeve_condition"].get(), 'Generic'),
'comments': app.full_desc.get("1.0", tk.END).strip()
        }
        
        app.root.config(cursor="watch")
        app.root.update()
        
        def draft_worker():
try:
    listing_id = app._safe_discogs_publish(app.editing_sku or "NEW", listing_data, is_draft=True)
    if listing_id:
        app.safe_after(0, lambda: app._handle_discogs_draft_success(listing_id))
except Exception as e:
    app.safe_after(0, lambda: messagebox.showerror("Draft Error", str(e)))
finally:
    app.safe_after(0, lambda: app.root.config(cursor=""))
        
        threading.Thread(target=draft_worker, daemon=True).start()

    def _create_discogs_draft_from_inventory(self):
        """Create Discogs drafts from selected inventory items"""
        selected = app.inventory_tree.selection()
        if not selected:
messagebox.showwarning("No Selection", "Please select items to create Discogs drafts")
return
        
        def draft_worker():
for item in selected:
    sku = app.inventory_tree.item(item, "values")[0]
    try:
        record = app._get_inventory_record(sku)
        if not record:
            app.append_log(f"SKU {sku}: Could not find record.", "red")
            continue
        
        errors = validate_listing("discogs", record, app.config)
        if errors:
            app.append_log(f"SKU {sku}: {', '.join(errors)}", "red")
            continue
        
        app.append_log(f"Creating Discogs draft for SKU {sku}...", "black")
        listing_data = {
            "release_id": record.get("discogs_release_id"),
            "condition": REVERSE_GRADE_MAP.get(record.get("media_condition"), "Good (G)"),
            "sleeve_condition": REVERSE_GRADE_MAP.get(record.get("sleeve_condition"), "Good (G)"),
            "price": record.get("price", 0), 
            "status": "Draft",  # Create as draft
            "comments": record.get("description", "")
        }
        
        listing_id = app.discogs_api.create_listing(listing_data)
        if listing_id:
            app.append_log(f"SKU {sku}: Created Discogs draft (ID: {listing_id})", "green")
            try:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                with app.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE inventory SET discogs_listing_id = ?, discogs_updated_at = ? WHERE sku = ?",
                        (listing_id, now_iso, sku),
                    )
            except Exception as e:
                logger.error(f"Failed to update inventory with Discogs listing ID: {e}")
                app.append_log(f"SKU {sku}: Failed to save Discogs listing ID to DB: {e}", "red")
        else:
            app.append_log(f"SKU {sku}: Failed to create draft", "red")
    except Exception as e:
        app.append_log(f"SKU {sku}: Error - {e}", "red")

app.safe_after(0, app.populate_inventory_view)
        
        threading.Thread(target=draft_worker, daemon=True).start()

    def _list_on_discogs_live(self):
        """Create live Discogs listing (For Sale status) from lister form"""
        if not app.discogs_api.is_connected():
messagebox.showwarning("Not Connected", "Please connect to Discogs first")
return

        if not app.current_release_id:
messagebox.showerror("Missing Release", "You must select a specific Discogs release variant first")
return

        try:
price = float(app.price_entry.get())
media_condition = app.entries["media_condition"].get()
if not media_condition or media_condition not in REVERSE_GRADE_MAP:
    messagebox.showwarning("Validation Error", "Please select a valid media condition")
    return
        except (ValueError, TypeError):
messagebox.showwarning("Validation Error", "Please enter a valid price")
return
        
        listing_data = {
'release_id': app.current_release_id,
'price': price,
'status': 'For Sale',  # Live listing
'condition': REVERSE_GRADE_MAP.get(media_condition),
'sleeve_condition': REVERSE_GRADE_MAP.get(app.entries["sleeve_condition"].get(), 'Generic'),
'comments': app.full_desc.get("1.0", tk.END).strip()
        }
        
        app.root.config(cursor="watch")
        app.root.update()
        
        def live_worker():
try:
    listing_id = app.discogs_api.create_listing(listing_data)
    if listing_id:
        app.safe_after(0, lambda: app._handle_discogs_live_success(listing_id))
except Exception as e:
    app.safe_after(0, lambda: messagebox.showerror("Listing Error", str(e)))
finally:
    app.safe_after(0, lambda: app.root.config(cursor=""))
        
        threading.Thread(target=live_worker, daemon=True).start()

    def _publish_to_discogs_live(self):
        """Publish selected items to Discogs as live (For Sale) listings"""
        selected = app.inventory_tree.selection()
        if not selected: 
return
        
        def live_worker():
for item in selected:
    sku = app.inventory_tree.item(item, "values")[0]
    try:
        record = app._get_inventory_record(sku)
        if not record:
            app.append_log(f"SKU {sku}: Could not find record.", "red")
            continue
        
        errors = validate_listing("discogs", record, app.config)
        if errors:
            app.append_log(f"SKU {sku}: {', '.join(errors)}", "red")
            continue
        
        app.append_log(f"Publishing SKU {sku} live to Discogs...", "black")
        listing_data = {
            "release_id": record.get("discogs_release_id"),
            "condition": REVERSE_GRADE_MAP.get(record.get("media_condition"), "Good (G)"),
            "sleeve_condition": REVERSE_GRADE_MAP.get(record.get("sleeve_condition"), "Good (G)"),
            "price": record.get("price", 0), 
            "status": "For Sale",  # Live listing
            "comments": record.get("description", "")
        }
        
        listing_id = app.discogs_api.create_listing(listing_data)
        if listing_id:
            app.append_log(f"SKU {sku}: Published live to Discogs (ID: {listing_id})", "green")
            try:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                with app.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE inventory SET discogs_listing_id = ?, discogs_updated_at = ? WHERE sku = ?",
                        (listing_id, now_iso, sku),
                    )
            except Exception as e:
                logger.error(f"Failed to update inventory with Discogs listing ID: {e}")
                app.append_log(f"SKU {sku}: Failed to save Discogs listing ID to DB: {e}", "red")
        else:
            app.append_log(f"SKU {sku}: Failed to create live listing", "red")
    except Exception as e:
        app.append_log(f"SKU {sku}: Error - {e}", "red")

app.safe_after(0, app.populate_inventory_view)
        
        threading.Thread(target=live_worker, daemon=True).start()

    def _handle_discogs_draft_success(self, listing_id):
        """Handle successful Discogs draft creation"""
        messagebox.showinfo("Success", f"Successfully created Discogs DRAFT (Listing ID: {listing_id})")
        if app.editing_sku:
try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE inventory SET discogs_listing_id = ? WHERE sku = ?", (listing_id, app.editing_sku))
except Exception as e:
    logger.error(f"Failed to update inventory with listing ID: {e}")

    def _handle_discogs_live_success(self, listing_id):
        """Handle successful Discogs live listing creation"""
        messagebox.showinfo("Success", f"Successfully published LIVE to Discogs (Listing ID: {listing_id})")
        if app.editing_sku:
try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE inventory SET discogs_listing_id = ? WHERE sku = ?", (listing_id, app.editing_sku))
except Exception as e:
    logger.error(f"Failed to update inventory with listing ID: {e}")

    def _prepare_ebay_listing_data(self, sku):
        """Prepare all eBay listing data from current form"""
        format_val = app.entries["format"].get() or "LP"
        media_cond_str = app.entries["media_condition"].get()
        
        condition_enum = EBAY_INVENTORY_CONDITION_MAP.get(media_cond_str, "USED_GOOD")
        condition_id_numeric = EBAY_CONDITION_MAP_NUMERIC.get(media_cond_str, "3000")
        category_id = EBAY_VINYL_CATEGORIES.get(format_val, "176985")
        
        ebay_title = app.entries["listing_title"].get() or f"{app.entries['artist'].get()} - {app.entries['title'].get()}"
        description_html = app.full_desc.get("1.0", tk.END).strip()

        return {
"sku": sku,
"title": ebay_title[:80],
"description": description_html,
"categoryId": str(category_id),
"price": float(app.price_entry.get()),
"quantity": 1,
"condition_enum": condition_enum,
"condition_id_numeric": condition_id_numeric,
"media_condition": app.entries["media_condition"].get(),
"sleeve_condition": app.entries["sleeve_condition"].get(),
"currency": "GBP",
"marketplaceId": app.config.get("marketplace_id", "EBAY_GB"),
"paymentPolicyId": app.config.get("ebay_payment_policy_id"),
"returnPolicyId": app.config.get("ebay_return_policy_id"),
"shippingPolicyId": app.config.get("ebay_shipping_policy_id"),
"images": app.image_paths,
        }


    def refresh_button_states(self):
        """Refresh all button states based on current connection status"""
        app._update_connection_status()
        # Trigger inventory selection update if items are selected
        if hasattr(self, 'inventory_tree') and app.inventory_tree.selection():
app.on_inventory_selection()


    # ========================================================================
    # DUPLICATE PREVENTION SYSTEM
    # ========================================================================
    
    def _check_existing_listings(self, sku: str) -> dict:
        """Check what listings already exist for this SKU"""
        try:
with app.db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ebay_listing_id, discogs_listing_id, ebay_item_draft_id, status 
        FROM inventory WHERE sku = ?
    """, (sku,))
    row = cursor.fetchone()
    
    if row:
        return {
            'ebay_listing_id': row[0],
            'discogs_listing_id': row[1], 
            'ebay_draft_id': row[2],
            'status': row[3],
            'has_ebay': bool(row[0]),
            'has_discogs': bool(row[1]),
            'has_ebay_draft': bool(row[2])
        }
    else:
        return {
            'ebay_listing_id': None,
            'discogs_listing_id': None,
            'ebay_draft_id': None,
            'status': None,
            'has_ebay': False,
            'has_discogs': False,
            'has_ebay_draft': False
        }
        except Exception as e:
logger.error(f"Error checking existing listings for {sku}: {e}")
return {'has_ebay': False, 'has_discogs': False, 'has_ebay_draft': False}

    def _confirm_overwrite_action(self, platform: str, sku: str, existing_info: dict) -> bool:
        """Ask user to confirm if they want to overwrite/update existing listing"""
        existing_ids = []
        if platform.lower() == 'ebay':
if existing_info.get('has_ebay'):
    existing_ids.append(f"Live eBay listing: {existing_info.get('ebay_listing_id')}")
if existing_info.get('has_ebay_draft'):
    existing_ids.append(f"eBay draft: {existing_info.get('ebay_draft_id')}")
        elif platform.lower() == 'discogs':
if existing_info.get('has_discogs'):
    existing_ids.append(f"Discogs listing: {existing_info.get('discogs_listing_id')}")
        
        if not existing_ids:
return True  # No existing listings, safe to proceed
        
        existing_text = "\n".join(existing_ids)
        message = (
f"SKU {sku} already has existing {platform} listing(s):\n\n"
f"{existing_text}\n\n"
f"Do you want to UPDATE the existing listing instead of creating a duplicate?\n\n"
f"Choose 'Yes' to update existing listing\n"
f"Choose 'No' to cancel and avoid duplicates"
        )
        
        return messagebox.askyesno(f"Existing {platform} Listing Found", message)

    def _safe_ebay_publish(self, sku: str, listing_data: dict, is_draft: bool = False) -> dict:
        """Safely publish to eBay with duplicate prevention"""
        # Check for existing listings
        existing = app._check_existing_listings(sku)
        
        # Determine what action to take
        action_type = "draft" if is_draft else "live"
        
        if existing['has_ebay'] and not is_draft:
# Has live listing, asking to publish live again
if not app._confirm_overwrite_action('eBay', sku, existing):
    return {'success': False, 'cancelled': True, 'reason': 'User cancelled to avoid duplicate'}

# User wants to update - modify existing listing
app.append_log(f"SKU {sku}: Updating existing eBay listing {existing['ebay_listing_id']}", "blue")
# Use existing eBay update logic here
return app.ebay_api.create_draft_listing(listing_data)  # This handles updates

        elif existing['has_ebay_draft'] and is_draft:
# Has draft, asking to create another draft
if not app._confirm_overwrite_action('eBay', sku, existing):
    return {'success': False, 'cancelled': True, 'reason': 'User cancelled to avoid duplicate'}

app.append_log(f"SKU {sku}: Updating existing eBay draft", "blue")
# Proceed with update

        elif existing['has_ebay'] and is_draft:
# Has live listing, wants to create draft - warn but allow
message = (f"SKU {sku} already has a LIVE eBay listing.\n\n"
          f"Creating a draft will not affect the live listing.\n"
          f"Continue?")
if not messagebox.askyesno("Live Listing Exists", message):
    return {'success': False, 'cancelled': True, 'reason': 'User cancelled'}
        
        # Proceed with creation/update
        result = app.ebay_api.create_draft_listing(listing_data)
        
        # Log the action
        if result.get('success'):
action_desc = "draft saved" if is_draft else "published live"
app.append_log(f"SKU {sku}: eBay listing {action_desc} successfully", "green")
        
        return result

    def _safe_discogs_publish(self, sku: str, listing_data: dict, is_draft: bool = False) -> int:
        """Safely publish to Discogs with duplicate prevention"""
        existing = app._check_existing_listings(sku)
        
        if existing['has_discogs']:
if not app._confirm_overwrite_action('Discogs', sku, existing):
    app.append_log(f"SKU {sku}: Discogs publish cancelled to avoid duplicate", "orange")
    return None

# User wants to update existing listing
discogs_id = existing['discogs_listing_id']
app.append_log(f"SKU {sku}: Updating existing Discogs listing {discogs_id}", "blue")

# Update instead of create
success = app.discogs_api.update_listing(discogs_id, listing_data)
if success:
    app.append_log(f"SKU {sku}: Discogs listing updated successfully", "green")
    return discogs_id
else:
    app.append_log(f"SKU {sku}: Failed to update Discogs listing", "red") 
    return None
        
        # No existing listing, safe to create new
        action_desc = "draft" if is_draft else "live listing"
        app.append_log(f"SKU {sku}: Creating new Discogs {action_desc}", "black")
        
        listing_id = app.discogs_api.create_listing(listing_data)
        if listing_id:
app.append_log(f"SKU {sku}: Discogs {action_desc} created successfully (ID: {listing_id})", "green")
        
        return listing_id


    def log_sync_activity(self, message):
        """Log sync activity to the text widget"""
        def do_log():
timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
app.sync_log_text.config(state="normal")
app.sync_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
app.sync_log_text.see(tk.END)
app.sync_log_text.config(state="disabled")
        app.safe_after(0, do_log)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    if sys.version_info < (3, 7):
        messagebox.showerror("Unsupported Python Version", "This application requires Python 3.7 or higher.")
        sys.exit(1)
        
    try:
        # Before starting, check for requests_toolbelt
        try:
import requests_toolbelt
        except ImportError:
 messagebox.showerror("Missing Dependency", "The 'requests-toolbelt' library is required for this version.\n\nPlease install it by running:\npip install requests-toolbelt")
 sys.exit(1)

        root = tk.Tk()
        app = VinylToolApp(root)
        root.mainloop()
    except Exception as e:
        # Create a simple Tk window to show the error if the main app fails
        try:
root = tk.Tk()
root.withdraw() # Hide the main window
messagebox.showerror("Fatal Application Error", f"A critical error occurred:\n\n{e}\n\n{traceback.format_exc()}")
        except:
# Fallback to console if GUI fails completely
print(f"FATAL ERROR: {e}\n{traceback.format_exc()}")
        sys.exit(1)

# --- Auto-backup on exit (active profile + core files) ---
import atexit, tarfile, datetime, json
from pathlib import Path as _Path

def _auto_backup_to_backups_dir():
    try:
        src_dir = _Path(__file__).resolve().parent
        backups = src_dir / "backups"
        backups.mkdir(exist_ok=True)
        active_profile = "dev"
        active_file = src_dir / "profiles" / "active_profile.json"
        try:
data = json.loads(active_file.read_text())
if isinstance(data, dict) and data.get("profile"):
    active_profile = str(data["profile"])
        except Exception:
pass
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = backups / f"backup_{ts}.tar.gz"
        with tarfile.open(fname, "w:gz") as tar:
for name in ["config.json","api_clients.py","inventory.db","geometry.conf"]:
    p = src_dir / name
    if p.exists():
        tar.add(p, arcname=p.name)
prof = src_dir / "profiles" / active_profile / "data"
if prof.exists():
    tar.add(prof, arcname=f"profiles/{active_profile}/data")
        print(f"[AutoBackup] Saved {fname}")
    except Exception as e:
        print("[AutoBackup] Failed:", e)

atexit.register(_auto_backup_to_backups_dir)
# --- End auto-backup ---


def _process_discogs_import(app, inventory):
"""Process Discogs import"""
new_items, skipped_items = 0, 0
try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        for listing in inventory:
            if listing.status != 'For Sale': continue
            cursor.execute("SELECT COUNT(*) FROM inventory WHERE discogs_listing_id = ?", (listing.id,))
            if cursor.fetchone()[0] > 0:
                skipped_items += 1
                continue
            new_items += 1
            artist = listing.release.artists[0].name if listing.release.artists else "Various"
            title = listing.release.title.replace(f"{artist} - ", "", 1).strip()
            sku = datetime.datetime.now().strftime(f"%Y%m%d-%H%M%S-{new_items}")
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            sql = """INSERT INTO inventory (sku, artist, title, cat_no, media_condition, sleeve_condition, price, status, discogs_release_id, discogs_listing_id, date_added, last_modified) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            media_cond = DISCOGS_GRADE_MAP.get(listing.condition, listing.condition)
            sleeve_cond = DISCOGS_GRADE_MAP.get(listing.sleeve_condition, listing.sleeve_condition)
            catno = getattr(listing.release, 'catno', '')
            cursor.execute(sql, (sku, artist, title, catno, media_cond, sleeve_cond, listing.price.value, "For Sale", listing.release.id, listing.id, now, now))
    messagebox.showinfo("Import Complete", f"Successfully imported {new_items} new item(s).\nSkipped {skipped_items} existing item(s).")
    app.populate_inventory_view()
except Exception as e:
    logger.error(f"Import failed: {e}")
    messagebox.showerror("Import Error", f"An error occurred during import:\n{e}")
    
    def toggle_auto_sync(self):
"""Toggle automatic sync"""
if not app.discogs_api.is_connected():
    messagebox.showwarning("Not Connected", "Please connect to your Discogs account first.")
    app.auto_sync_var.set(False)
    return
app.auto_sync_enabled = app.auto_sync_var.get()
app.config.save({"auto_sync_enabled": app.auto_sync_enabled})
if app.auto_sync_enabled: app.start_auto_sync()
else: app.stop_auto_sync()
    
    def toggle_two_way_sync(self):
"""Toggle two-way sync"""
app.two_way_sync_enabled = app.two_way_sync_var.get()
app.config.save({"two_way_sync_enabled": app.two_way_sync_enabled})
app.log_sync_activity(f"Two-way sync {'enabled' if app.two_way_sync_enabled else 'disabled'}")
    
    def toggle_attempt_updates(self):
"""Toggle attempt to update Discogs"""
app.attempt_discogs_updates = app.attempt_updates_var.get()
app.config.save({"attempt_discogs_updates": app.attempt_discogs_updates})
app.log_sync_activity(f"Discogs update attempts {'enabled' if app.attempt_discogs_updates else 'disabled'}")
    
    def update_sync_interval(self):
"""Update sync interval"""
try:
    minutes = int(app.sync_interval_var.get())
    app.auto_sync_interval = minutes * 60
    app.config.save({"auto_sync_interval": app.auto_sync_interval})
    app.log_sync_activity(f"Sync interval set to {minutes} minutes")
except ValueError: app.sync_interval_var.set("5")
    
    def start_auto_sync(self):
"""Start automatic sync"""
if app.auto_sync_thread and app.auto_sync_thread.is_alive(): return
app.auto_sync_stop_event.clear()
app.auto_sync_thread = threading.Thread(target=app._auto_sync_worker, daemon=True)
app.auto_sync_thread.start()
app.sync_status_var.set("Auto-sync enabled - waiting for next sync...")
app.log_sync_activity("Automatic sync started")
    
    def stop_auto_sync(self):
"""Stop automatic sync"""
app.auto_sync_stop_event.set()
app.sync_status_var.set("Auto-sync disabled")
app.log_sync_activity("Automatic sync stopped")
    
    def _auto_sync_worker(self):
"""Auto sync worker thread"""
while not app.auto_sync_stop_event.is_set():
    try:
        if app.auto_sync_stop_event.wait(app.auto_sync_interval): break
        if app.auto_sync_enabled and app.discogs_api.is_connected():
            app.safe_after(0, lambda: app.sync_status_var.set("Syncing inventory..."))
            sync_result = app._perform_inventory_sync()
            app.safe_after(0, lambda r=sync_result: app._handle_sync_result(r))
    except Exception as e:
        app.safe_after(0, lambda msg=f"Auto-sync error: {e}": app.log_sync_activity(msg))
    
    def manual_sync_now(self):
"""Perform manual sync now"""
if not app.discogs_api.is_connected():
    messagebox.showwarning("Not Connected", "Please connect to your Discogs account first.")
    return
app.sync_status_var.set("Manual sync in progress...")
app.root.config(cursor="watch"); app.root.update()
def sync_worker():
    try:
        result = app._perform_inventory_sync()
        app.safe_after(0, lambda: app._handle_sync_result(result))
    except Exception as e:
        app.safe_after(0, lambda: messagebox.showerror("Sync Error", str(e)))
    finally:
        app.safe_after(0, lambda: app.root.config(cursor=""))
threading.Thread(target=sync_worker, daemon=True).start()
    
    def _perform_inventory_sync(self):
"""Implements true "latest-wins" two-way sync logic."""
sync_start_time = datetime.datetime.now(datetime.timezone.utc)
app.log_sync_activity("=== STARTING SYNC (Latest-Wins) ===")
try:
    discogs_inventory = app.discogs_api.get_inventory()
    discogs_map = {listing.id: listing for listing in discogs_inventory}
    app.log_sync_activity(f"Retrieved {len(discogs_inventory)} active listings from Discogs.")

    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sku, discogs_listing_id, price, status, notes, last_modified, last_sync_time FROM inventory WHERE discogs_listing_id IS NOT NULL")
        local_items = [dict(row) for row in cursor.fetchall()]
        local_map = {item['discogs_listing_id']: item for item in local_items}
    app.log_sync_activity(f"Found {len(local_map)} linked local items.")

    updates_to_local, updates_to_discogs, deletions_from_local, new_sales = 0, 0, 0, 0
    
    for local_item in local_items:
        listing_id, last_mod_local_str, last_sync_str = local_item['discogs_listing_id'], local_item.get('last_modified'), app.last_successful_sync_time or local_item.get('last_sync_time')
        if not last_mod_local_str or not last_sync_str: continue
        try:
            last_mod_local, last_sync = datetime.datetime.fromisoformat(last_mod_local_str), datetime.datetime.fromisoformat(last_sync_str)
        except (ValueError, TypeError): continue

        if last_mod_local > last_sync and app.attempt_discogs_updates:
            if listing_id in discogs_map:
                app.log_sync_activity(f"→ Local change detected for SKU {local_item['sku']}. Pushing to Discogs.")
                update_payload = {"price": local_item['price'], "status": app._map_local_to_discogs_status(local_item['status']), "comments": local_item.get('notes', '')}
                if app.discogs_api.update_listing(listing_id, update_payload):
                    updates_to_discogs += 1; app.log_sync_activity(f"  ✓ Pushed update for SKU {local_item['sku']} to Discogs.")
                else: app.log_sync_activity(f"  ✗ Failed to push update for SKU {local_item['sku']}.")
            else: app.log_sync_activity(f"  - SKU {local_item['sku']} changed locally but no longer on Discogs. Skipping push.")

        elif listing_id in discogs_map:
            listing = discogs_map[listing_id]
            mapped_status = app.status_mappings.get(listing.status, "Not For Sale")
            if mapped_status != local_item['status']:
                with app.db.get_connection() as conn:
                    conn.cursor().execute("UPDATE inventory SET status = ?, last_modified = ? WHERE discogs_listing_id = ?", (mapped_status, sync_start_time.isoformat(), listing_id))
                updates_to_local += 1
                if mapped_status == 'Sold' and local_item['status'] != 'Sold': new_sales += 1
                app.log_sync_activity(f"✓ Sync from Discogs: SKU {local_item['sku']} '{local_item['status']}' → '{mapped_status}'")

    ids_to_delete_locally = set(local_map.keys()) - set(discogs_map.keys())
    if ids_to_delete_locally:
        with app.db.get_connection() as conn:
            cursor = conn.cursor()
            for listing_id in ids_to_delete_locally:
                if local_map[listing_id]['status'] == 'For Sale':
                    sku = local_map[listing_id]['sku']
                    cursor.execute("DELETE FROM inventory WHERE discogs_listing_id = ?", (listing_id,))
                    deletions_from_local += 1
                    app.log_sync_activity(f"✓ Deleted SKU {sku} locally as it's no longer on Discogs.")
    
    with app.db.get_connection() as conn:
        conn.cursor().execute("UPDATE inventory SET last_sync_time = ? WHERE discogs_listing_id IS NOT NULL", (sync_start_time.isoformat(),))
    app.last_successful_sync_time = sync_start_time.isoformat()
    app.config.save({"last_successful_sync_time": app.last_successful_sync_time})
    if updates_to_local > 0 or deletions_from_local > 0: app.safe_after(0, app.populate_inventory_view)
    app.log_sync_activity("=== SYNC COMPLETED ===")
    return {'success': True, 'updates_local': updates_to_local, 'updates_discogs': updates_to_discogs, 'deletions': deletions_from_local, 'new_sales': new_sales, 'total_checked': len(discogs_inventory)}
except Exception as e:
    logger.error(f"Sync failed: {e}", exc_info=True)
    app.log_sync_activity(f"✗ SYNC ERROR: {e}")
    return {'success': False, 'error': str(e)}

    def _map_local_to_discogs_status(self, local_status):
"""Map local status to valid Discogs status"""
return {'For Sale': 'For Sale', 'Sold': 'Sold'}.get(local_status, 'Draft')
    
    def _handle_sync_result(self, result):
"""Handle sync result"""
current_time = datetime.datetime.now().strftime("%H:%M:%S")
if result.get('success'):
    updates_local, updates_discogs, deletions = result.get('updates_local', 0), result.get('updates_discogs', 0), result.get('deletions', 0)
    total_changes = updates_local + updates_discogs + deletions
    if total_changes > 0:
        log_msg = f"[{current_time}] Sync completed: {total_changes} changes from {result['total_checked']} listings"
        if updates_local > 0: log_msg += f"\n  - Pulled from Discogs: {updates_local}"
        if updates_discogs > 0: log_msg += f"\n  - Pushed to Discogs: {updates_discogs}"
        if deletions > 0: log_msg += f"\n  - Items deleted locally: {deletions}"
        if result.get('new_sales', 0) > 0: log_msg += f"\n  - New sales detected: {result['new_sales']}"
        app.log_sync_activity(log_msg)
        status_msg = f"Sync complete - {total_changes} change(s)"
    else:
        status_msg = "Sync complete - no changes needed"
        app.log_sync_activity(f"[{current_time}] Sync completed. No changes needed.")
    app.sync_status_var.set(f"Last sync: {current_time}. {status_msg}")
else:
    app.sync_status_var.set(f"Last sync: {current_time}. FAILED.")
    app.log_sync_activity(f"[{current_time}] Sync FAILED: {result.get('error')}")

    # ========================================================================
    # ENHANCED PUBLISHING ACTION METHODS
    # ========================================================================
    
    def action_ebay_save_unpublished(self):
"""Save eBay listing data locally as 'ready to publish' without sending to eBay"""
if app.notebook.tab(app.notebook.select(), "text") == "Lister":
    # From Lister tab - save current form
    app._save_ebay_draft_from_lister()
else:
    # From Inventory tab - mark selected items as ready for eBay
    app._save_ebay_draft_from_inventory()

    def action_ebay_publish_live(self):
"""Publish directly to eBay as live listings (Inventory API)"""
if app.notebook.tab(app.notebook.select(), "text") == "Lister":
    # From Lister tab - publish current form directly
    app.list_on_ebay()
else:
    # From Inventory tab - publish selected items
    app.publish_to_ebay()



    def reconcile_from_ebay(self, skus):


"""Pull eBay state back into local DB so deletions/ends/relists are reflected.


Chooses ACTIVE offer. Prefers Item ID (listingId); falls back to offerId if listingId hasn't propagated yet.


Refreshes the grid when done.


"""


import datetime, logging, requests


logger = logging.getLogger(__name__)


    


token = app.ebay_api.get_access_token()


if not token:


    app.append_log("Cannot reconcile: missing eBay token", "red")


    return


    


headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}


changed = False


    


for sku in (skus or []):


    try:


        url = f"{app.ebay_api.base_url}/sell/inventory/v1/offer?sku={sku}"


        r = requests.get(url, headers=headers, timeout=30)


        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()


    


        if r.status_code == 200 and r.json().get("offers"):


            offers = r.json()["offers"]


            # Pick ACTIVE offer if available; otherwise first one


            active = None


            for o in offers:


                if (o.get("status") or "").upper() == "ACTIVE":


                    active = o


                    break


            offer = active or offers[0]


            status = (offer.get("status") or "").upper()


    


            listing_id = offer.get('legacyItemId') or offer.get('listingId') or (offer.get('listing') or {}).get('legacyItemId') or (offer.get('listing') or {}).get('listingId')


            offer_id = offer.get("offerId") or (offer.get("offer") or {}).get("offerId")


    


            # If ACTIVE but listingId missing, try GET /offer/{offerId} to resolve


            if status in ("ACTIVE","PUBLISHED") and not listing_id and offer_id:


                try:


                    resolved = app.ebay_api.get_offer(str(offer_id))


                    if resolved.get("success"):


                        listing_id = resolved.get('legacyItemId') or (resolved.get('listing') or {}).get('legacyItemId') or resolved.get('listingId') or (resolved.get('listing') or {}).get('listingId')


                except Exception as e:


                    logger.warning(f"[reconcile] get_offer failed for offer {offer_id}: {e}")


    


            with app.db.get_connection() as conn:


                c = conn.cursor()


                if status in ("ACTIVE","PUBLISHED"):


                    stored_id = listing_id or (offer_id if offer_id else None)


                    if stored_id:


                        c.execute("UPDATE inventory SET ebay_listing_id = ?, ebay_updated_at = ? WHERE sku = ?", (stored_id, now_iso, sku))


                        changed = True


                    else:


                        c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


                        changed = True


                else:


                    c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


                    changed = True


    


            shown = listing_id or (offer_id if (status in ("ACTIVE","PUBLISHED") and offer_id) else "—")


            label = "Item ID" if listing_id else ("Offer ID" if shown != "—" else "—")  # live


            app.append_log(f"SKU {sku}: reconciled from eBay ({status}; {label}={shown})", "blue")


        else:


            with app.db.get_connection() as conn:


                c = conn.cursor()


                c.execute("UPDATE inventory SET ebay_listing_id = NULL, ebay_updated_at = ? WHERE sku = ?", (now_iso, sku))


            changed = True


            app.append_log(f"SKU {sku}: no eBay offer found; cleared local mapping.", "orange")


    


    except Exception as e:


        logger.error(f"Reconcile error for {sku}: {e}")


        app.append_log(f"SKU {sku}: reconcile failed: {e}", "red")


    


if changed:


    try:


        app.populate_inventory_view()


    except Exception:


        pass



    def action_open_on_ebay_selected(self):



"""Open the selected item's eBay listing in the browser using stored Item ID."""



import webbrowser, requests, logging



logger = logging.getLogger(__name__)



items = app.inventory_tree.selection()



if not items:



    try:



        messagebox.showinfo("Open on eBay", "Please select a row first.")



    except Exception:



        pass



    return



iid = items[0]



vals = app.inventory_tree.item(iid, "values") or []



item_id = None



# Try visible column first



try:



    headers = [app.inventory_tree.heading(c)["text"] for c in app.inventory_tree["columns"]]



    if "eBay ID" in headers:



        idx = headers.index("eBay ID")



        if idx < len(vals):



            item_id = vals[idx]



except Exception:



    item_id = None



# Fallback: DB lookup by SKU (assumes SKU in first column)



if not item_id and vals:



    sku = vals[0]



    try:



        with app.db.get_connection() as conn:



            c = conn.cursor()



            c.execute("SELECT ebay_listing_id FROM inventory WHERE sku = ?", (sku,))



            row = c.fetchone()



            if row and row[0]:



                item_id = row[0]



    except Exception:



        pass



if not item_id:



    try:



        messagebox.showinfo("Open on eBay", "No eBay Item ID stored for the selected row.")



    except Exception:



        pass



    return



# If it's likely an offerId, try resolve to listingId on the fly



if not (str(item_id).isdigit() and len(str(item_id)) >= 12) and vals:



    try:



        token = app.ebay_api.get_access_token()



        if token:



            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}



            url = f"{app.ebay_api.base_url}/sell/inventory/v1/offer?sku={{vals[0]}}"



            r = requests.get(url, headers=headers, timeout=30)



            if r.status_code == 200 and r.json().get("offers"):



                offers = r.json()["offers"]



                active = None



                for o in offers:



                    if (o.get("status") or "").upper() == "ACTIVE":



                        active = o



                        break



                off = active or offers[0]



                lid = off.get('legacyItemId') or off.get('listingId') or (off.get('listing') or {}).get('legacyItemId') or (off.get('listing') or {}).get('listingId')



                if not lid:



                    oid = off.get("offerId") or (off.get("offer") or {}).get("offerId")



                    if oid:



                        resolved = app.ebay_api.get_offer(str(oid))



                        if resolved.get("success"):



                            lid = resolved.get('legacyItemId') or (resolved.get('listing') or {}).get('legacyItemId') or resolved.get('listingId') or (resolved.get('listing') or {}).get('listingId')



                if lid:



                    item_id = lid



    except Exception as e:



        logger.warning(f"[open] resolution failed: {e}")



try:



    webbrowser.open_new_tab(f"https://www.ebay.co.uk/itm/{item_id}")



except Exception:



    try:



        messagebox.showerror("Open on eBay", "Failed to open browser.")



    except Exception:



        pass




    # ------------------------------




    # eBay → Discogs Import (Wizard)




    # ------------------------------




    def action_import_from_ebay(self):




try:




    offers = app._fetch_all_ebay_offers()




except Exception as e:




    messagebox.showerror("Import from eBay", f"Failed to fetch eBay offers:\n{e}")




    return




work = []




with app.db.get_connection() as conn:




    c = conn.cursor()




    for off in offers:




        sku = (off.get("sku") or "").strip()




        if not sku:




            continue




        c.execute("SELECT discogs_listing_id FROM inventory WHERE sku = ?", (sku,))




        row = c.fetchone()




        if not row or not row[0]:




            work.append(off)




if not work:




    messagebox.showinfo("Import from eBay", "No eligible eBay listings found (all mapped).")




    return




app._start_import_wizard(work)




    




    def _fetch_all_ebay_offers(self):




token = app.ebay_api.get_access_token()




if not token:




    raise RuntimeError("Missing eBay token")




import requests




hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}




base = f"{app.ebay_api.base_url}/sell/inventory/v1/offer"




offers, limit, offset = [], 200, 0




while True:




    resp = requests.get(f"{base}?limit={limit}&offset={offset}", headers=hdrs, timeout=30)




    if resp.status_code != 200:




        raise RuntimeError(f"eBay API error {resp.status_code}: {resp.text[:300]}")




    data = resp.json()




    batch = data.get("offers") or []




    for o in batch:




        aspects = (o.get("aspects") or {})




        gtin = None




        for k in ("EAN","UPC","GTIN","ean","upc","gtin"):




            v = aspects.get(k)




            if isinstance(v, list) and v:




                gtin = v[0]; break




            if isinstance(v, str) and v.strip():




                gtin = v.strip(); break




        if not gtin:




            prod = o.get("product") or {}




            g = prod.get("gtin")




            if isinstance(g, list) and g:




                gtin = g[0]




            elif isinstance(g, str):




                gtin = g




        offers.append({




            "sku": o.get("sku"),




            "title": o.get("title") or (o.get("name") or ""),




            "offerId": o.get("offerId") or (o.get("offer") or {}).get("offerId"),




            "listingId": o.get("legacyItemId") or o.get("listingId") or (o.get("listing") or {}).get("legacyItemId") or (o.get("listing") or {}).get("listingId"),




            "price": ((o.get("pricingSummary") or {}).get("price") or {}).get("value"),




            "currency": ((o.get("pricingSummary") or {}).get("price") or {}).get("currency"),




            "quantity": o.get("availableQuantity"),




            "status": (o.get("status") or "").upper(),




            "gtin": (gtin or "").strip(),




            "catno": (aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No") or [""])[0] if isinstance(aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No"), list) else (aspects.get("Catalogue Number") or aspects.get("Catalog Number") or aspects.get("Cat No") or ""),




            "label": (aspects.get("Record Label") or aspects.get("Label") or [""])[0] if isinstance(aspects.get("Record Label") or aspects.get("Label"), list) else (aspects.get("Record Label") or aspects.get("Label") or ""),




            "format": (aspects.get("Format") or [""])[0] if isinstance(aspects.get("Format"), list) else (aspects.get("Format") or ""),




            "country": (aspects.get("Country/Region of Manufacture") or [""])[0] if isinstance(aspects.get("Country/Region of Manufacture"), list) else (aspects.get("Country/Region of Manufacture") or ""),




            "year": (aspects.get("Release Year") or [""])[0] if isinstance(aspects.get("Release Year"), list) else (aspects.get("Release Year") or ""),




        })




    total = data.get("total", 0)




    offset += len(batch)




    if offset >= total or not batch:




        break




return offers




    




    def _start_import_wizard(self, offers):




app._import_offers = [o for o in offers]




app._import_idx = 0




win = tk.Toplevel(app.root)




win.title("Import from eBay → Discogs match")




win.geometry("720x520")




app._import_win = win




app._imp_hdr = tk.Label(win, text="", font=("Helvetica", 14, "bold"))




app._imp_hdr.pack(anchor="w", padx=12, pady=(10, 6))




app._imp_info = tk.Text(win, height=10, wrap="word")




app._imp_info.pack(fill="x", padx=12)




app._imp_status = tk.Label(win, text="", fg="gray")




app._imp_status.pack(anchor="w", padx=12, pady=6)




btns = tk.Frame(win)




btns.pack(fill="x", padx=12, pady=8)




tk.Button(btns, text="Accept", command=app._import_accept).pack(side="left", padx=4)




tk.Button(btns, text="See Alternatives…", command=app._import_alternatives).pack(side="left", padx=4)




tk.Button(btns, text="Skip", command=app._import_skip).pack(side="left", padx=4)




tk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=4)




app._import_propose_current()




    




    def _import_propose_current(self):




if app._import_idx >= len(app._import_offers):




    try:




        app.populate_inventory_view()




    except Exception:




        pass




    messagebox.showinfo("Import from eBay", "Done.")




    app._import_win.destroy()




    return




o = app._import_offers[app._import_idx]




sku = o.get("sku") or ""




title = o.get("title") or ""




gtin = o.get("gtin") or ""




catno = o.get("catno") or ""




label = o.get("label") or ""




fmt = o.get("format") or ""




app._imp_hdr.config(text=f"SKU {sku} — {title}")




app._imp_info.delete("1.0", "end")




app._imp_info.insert("end", f"eBay ID: {o.get('listingId') or o.get('offerId')}\n")




app._imp_info.insert("end", f"GTIN/Barcode: {gtin or '—'}\n")




app._imp_info.insert("end", f"Cat No: {catno or '—'}\n")




app._imp_info.insert("end", f"Label: {label or '—'} | Format: {fmt or '—'}\n\n")




try:




    cands = app._discogs_find_candidates(gtin=gtin, catno=catno, title=title, label=label or None)




except Exception as e:




    app._imp_status.config(text=f"Discogs search failed: {e}")




    app._import_candidates = []




    return




app._import_candidates = cands




if not cands:




    app._imp_status.config(text="No candidates found. Click ‘See Alternatives…’ to search manually.")




else:




    top = cands[0]




    app._imp_status.config(text=f"Proposed: {top['artist']} – {top['title']} [{top['label']} • {top['year']} • {top['country']}]  ({top['method']}, {int(top['confidence']*100)}%)")




    




    def _discogs_find_candidates(self, gtin: str = "", catno: str = "", title: str = "", label: str = None):




results = []




if gtin:




    res = app.discogs_client.search(barcode=gtin, type="release", format="Vinyl")




    for r in list(res)[:10]:




        results.append({"release_id": r.id, "title": r.title,




            "artist": getattr(r, "artist", getattr(r, "artists", "")),




            "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




            "year": getattr(r, "year", "") or "",




            "country": getattr(r, "country", "") or "",




            "method": "barcode", "confidence": 1.0})




if catno:




    res = app.discogs_client.search(catno=catno, type="release", format="Vinyl")




    for r in list(res)[:10]:




        results.append({"release_id": r.id, "title": r.title,




            "artist": getattr(r, "artist", getattr(r, "artists", "")),




            "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




            "year": getattr(r, "year", "") or "",




            "country": getattr(r, "country", "") or "",




            "method": "catno", "confidence": 0.85 if not label else 0.9})




if (not results) and title:




    res = app.discogs_client.search(title=title, type="release", format="Vinyl", label=label or None)




    for r in list(res)[:10]:




        results.append({"release_id": r.id, "title": r.title,




            "artist": getattr(r, "artist", getattr(r, "artists", "")),




            "label": ", ".join(getattr(r, "label", getattr(r, "labels", [])) or []),




            "year": getattr(r, "year", "") or "",




            "country": getattr(r, "country", "") or "",




            "method": "fuzzy", "confidence": 0.6})




seen, ranked = set(), []




for r in sorted(results, key=lambda x: x["confidence"], reverse=True):




    if r["release_id"] in seen: continue




    seen.add(r["release_id"]); ranked.append(r)




return ranked




    




    def _import_accept(self):




if app._import_idx >= len(app._import_offers): return




o = app._import_offers[app._import_idx]




top = (app._import_candidates[0] if app._import_candidates else None)




if not top:




    messagebox.showinfo("Import from eBay", "No candidate to accept for this item."); return




sku = (o.get("sku") or "").strip()




now_iso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()




with app.db.get_connection() as conn:




    c = conn.cursor()




    c.execute("SELECT 1 FROM inventory WHERE sku = ?", (sku,))




    exists = c.fetchone() is not None




    if exists:




        c.execute("""UPDATE inventory




                     SET discogs_listing_id = ?,




                         discogs_match_method = ?, discogs_match_confidence = ?,




                         barcode = COALESCE(?, barcode),




                         inv_updated_at = ?




                     WHERE sku = ?""", 




                  (str(top["release_id"]), top["method"], float(top["confidence"]),




                   (o.get("gtin") or None), now_iso, sku))




    else:




        c.execute("""INSERT INTO inventory




                     (sku, artist, title, price, status, ebay_listing_id, discogs_listing_id,




                      barcode, discogs_match_method, discogs_match_confidence, inv_updated_at, date_added)




                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 




                  (sku, "", o.get("title") or "", o.get("price") or 0.0, "For Sale",




                   (o.get("listingId") or None), str(top["release_id"]),




                   (o.get("gtin") or None), top["method"], float(top["confidence"]), now_iso, now_iso))




app.append_log(f"Imported {sku} → Discogs {top['release_id']} ({top['method']}, {int(top['confidence']*100)}%)", "green")




app._import_idx += 1




app._import_propose_current()




    




    def _import_alternatives(self):




if not app._import_candidates:




    messagebox.showinfo("Alternatives", "No candidates available for this item."); return




top = tk.Toplevel(app._import_win); top.title("Choose a Discogs release")




lb = tk.Listbox(top, width=90, height=10)




for i, r in enumerate(app._import_candidates[:12]):




    lb.insert("end", f"{i+1}. {r['artist']} – {r['title']}  [{r['label']} • {r['year']} • {r['country']}]  ({r['method']}, {int(r['confidence']*100)}%)")




lb.pack(fill="both", expand=True)




def choose():




    idx = lb.curselection()




    if not idx: return




    i = idx[0]




    chosen = app._import_candidates[i]




    rest = [r for j,r in enumerate(app._import_candidates) if j != i]




    app._import_candidates = [chosen] + rest




    top.destroy()




    app._imp_status.config(text=f"Chosen: {chosen['artist']} – {chosen['title']} [{chosen['label']} • {chosen['year']} • {chosen['country']}]  ({chosen['method']}, {int(chosen['confidence']*100)}%)")




tk.Button(top, text="Use Selected", command=choose).pack(pady=6)




    




    def _import_skip(self):




app._import_idx += 1




app._import_propose_current()





    def action_ebay_sync_selected(self):

"""Sync selected inventory SKUs from eBay into local DB (status/listingId)."""

items = app.inventory_tree.selection()

if not items:

    try:

        messagebox.showinfo("Sync from eBay", "Please select one or more items in the inventory list.")

    except Exception:

        pass

    return

skus = []

for iid in items:

    vals = app.inventory_tree.item(iid, "values")

    if not vals:

        continue

    skus.append(vals[0])

try:

    app.reconcile_from_ebay(skus)

except Exception as e:

    try:

        messagebox.showerror("Sync from eBay", f"Failed to sync: {e}")

    except Exception:

        pass


    def action_discogs_save_unpublished(self):
"""Create Discogs draft listings"""
if app.notebook.tab(app.notebook.select(), "text") == "Lister":
    app._create_discogs_draft_from_lister()
else:
    app._create_discogs_draft_from_inventory()

    def action_discogs_publish_live(self):
"""Create live Discogs listings"""
if app.notebook.tab(app.notebook.select(), "text") == "Lister":
    # Create live listing instead of draft
    app._list_on_discogs_live()
else:
    # Modify existing publish_to_discogs to use "For Sale" status
    app._publish_to_discogs_live()

    def _save_ebay_draft_from_lister(self):
"""Save current lister form as eBay-ready in database with duplicate checking"""
try:
    # Validate required fields
    required_fields = ['artist', 'title', 'media_condition']
    for field in required_fields:
        if not app.entries[field.replace(' ', '_')].get().strip():
            messagebox.showwarning("Validation Error", f"Please enter {field}")
            return
    
    try:
        price = float(app.price_entry.get())
        if price <= 0:
            messagebox.showwarning("Validation Error", "Please enter a valid price")
            return
    except (ValueError, TypeError):
        messagebox.showwarning("Validation Error", "Please enter a valid price")
        return

    # Generate SKU if needed
    sku = app.editing_sku or app.sku_display_var.get() or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if not app.editing_sku and not app.temporary_sku:
        app.sku_display_var.set(sku)

    # Check for existing listings and warn user
    existing = app._check_existing_listings(sku)
    if existing['has_ebay'] or existing['has_ebay_draft']:
        warning_parts = []
        if existing['has_ebay']:
            warning_parts.append(f"Live eBay listing: {existing['ebay_listing_id']}")
        if existing['has_ebay_draft']:
            warning_parts.append(f"eBay draft: {existing['ebay_draft_id']}")
        
        warning_text = "\n".join(warning_parts)
        message = (f"SKU {sku} already has:\n\n{warning_text}\n\n"
                  f"This will update the existing record. Continue?")
        
        if not messagebox.askyesno("Existing eBay Data Found", message):
            return

    # Save to database with special status
    payload_json = json.dumps(app._serialize_form_to_payload())
    
    try:
        with app.db.get_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            if app.editing_sku:
                # Update existing
                cursor.execute("""
                    UPDATE inventory SET 
                    status = 'eBay Ready',
                    last_modified = ?,
                    lister_payload = ?
                    WHERE sku = ?
                """, (now_iso, payload_json, sku))
                message = f"Updated SKU {sku} as ready for eBay"
            else:
                # Create new with basic info
                cursor.execute("""
                    INSERT INTO inventory (
                        sku, artist, title, price, status, date_added, 
                        last_modified, lister_payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sku,
                    app.entries["artist"].get().strip(),
                    app.entries["title"].get().strip(), 
                    price,
                    'eBay Ready',
                    now_iso,
                    now_iso,
                    payload_json
                ))
                message = f"Saved SKU {sku} as ready for eBay"
            
            app.populate_inventory_view()
            app.append_log(message, "green")
            messagebox.showinfo("eBay Draft Saved", 
                f"{message}\n\n" +
                f"Note: This creates a local draft in your database.\n" + 
                f"eBay doesn't provide draft functionality via their public API.\n" +
                f"Use 'Publish Live' when ready to list on eBay.")
            
    except Exception as e:
        logger.error(f"Failed to save eBay draft: {e}")
        messagebox.showerror("Database Error", f"Failed to save: {e}")
        
except Exception as e:
    logger.error(f"Error in _save_ebay_draft_from_lister: {e}")
    messagebox.showerror("Error", f"An error occurred: {e}")

    def _save_ebay_draft_from_inventory(self):
"""Mark selected inventory items as ready for eBay"""
selected = app.inventory_tree.selection()
if not selected:
    messagebox.showwarning("No Selection", "Please select items to prepare for eBay")
    return

try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        updated_count = 0
        for item in selected:
            sku = app.inventory_tree.item(item, "values")[0]
            cursor.execute("""
                UPDATE inventory SET 
                status = 'eBay Ready',
                last_modified = ?
                WHERE sku = ?
            """, (now_iso, sku))
            updated_count += 1
        
        app.populate_inventory_view()
        message = f"Marked {updated_count} item(s) as ready for eBay"
        app.append_log(message, "green")
        messagebox.showinfo("Success", message)
        
except Exception as e:
    logger.error(f"Failed to mark items as eBay ready: {e}")
    messagebox.showerror("Database Error", f"Failed to update items: {e}")

    def _create_discogs_draft_from_lister(self):
"""Create Discogs draft from current lister form"""
if not app.discogs_api.is_connected():
    messagebox.showwarning("Not Connected", "Please connect to Discogs first")
    return
    
if not app.current_release_id:
    messagebox.showerror("Missing Release", "You must select a specific Discogs release variant first")
    return
    
try:
    price = float(app.price_entry.get())
    media_condition = app.entries["media_condition"].get()
    if not media_condition or media_condition not in REVERSE_GRADE_MAP:
        messagebox.showwarning("Validation Error", "Please select a valid media condition")
        return
except (ValueError, TypeError):
    messagebox.showwarning("Validation Error", "Please enter a valid price")
    return

listing_data = {
    'release_id': app.current_release_id,
    'price': price,
    'status': 'Draft',  # Explicitly set as draft
    'condition': REVERSE_GRADE_MAP.get(media_condition),
    'sleeve_condition': REVERSE_GRADE_MAP.get(app.entries["sleeve_condition"].get(), 'Generic'),
    'comments': app.full_desc.get("1.0", tk.END).strip()
}

app.root.config(cursor="watch")
app.root.update()

def draft_worker():
    try:
        listing_id = app._safe_discogs_publish(app.editing_sku or "NEW", listing_data, is_draft=True)
        if listing_id:
            app.safe_after(0, lambda: app._handle_discogs_draft_success(listing_id))
    except Exception as e:
        app.safe_after(0, lambda: messagebox.showerror("Draft Error", str(e)))
    finally:
        app.safe_after(0, lambda: app.root.config(cursor=""))

threading.Thread(target=draft_worker, daemon=True).start()

    def _create_discogs_draft_from_inventory(self):
"""Create Discogs drafts from selected inventory items"""
selected = app.inventory_tree.selection()
if not selected:
    messagebox.showwarning("No Selection", "Please select items to create Discogs drafts")
    return

def draft_worker():
    for item in selected:
        sku = app.inventory_tree.item(item, "values")[0]
        try:
            record = app._get_inventory_record(sku)
            if not record:
                app.append_log(f"SKU {sku}: Could not find record.", "red")
                continue
            
            errors = validate_listing("discogs", record, app.config)
            if errors:
                app.append_log(f"SKU {sku}: {', '.join(errors)}", "red")
                continue
            
            app.append_log(f"Creating Discogs draft for SKU {sku}...", "black")
            listing_data = {
                "release_id": record.get("discogs_release_id"),
                "condition": REVERSE_GRADE_MAP.get(record.get("media_condition"), "Good (G)"),
                "sleeve_condition": REVERSE_GRADE_MAP.get(record.get("sleeve_condition"), "Good (G)"),
                "price": record.get("price", 0), 
                "status": "Draft",  # Create as draft
                "comments": record.get("description", "")
            }
            
            listing_id = app.discogs_api.create_listing(listing_data)
            if listing_id:
                app.append_log(f"SKU {sku}: Created Discogs draft (ID: {listing_id})", "green")
                try:
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    with app.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE inventory SET discogs_listing_id = ?, discogs_updated_at = ? WHERE sku = ?",
                            (listing_id, now_iso, sku),
                        )
                except Exception as e:
                    logger.error(f"Failed to update inventory with Discogs listing ID: {e}")
                    app.append_log(f"SKU {sku}: Failed to save Discogs listing ID to DB: {e}", "red")
            else:
                app.append_log(f"SKU {sku}: Failed to create draft", "red")
        except Exception as e:
            app.append_log(f"SKU {sku}: Error - {e}", "red")
    
    app.safe_after(0, app.populate_inventory_view)

threading.Thread(target=draft_worker, daemon=True).start()

    def _list_on_discogs_live(self):
"""Create live Discogs listing (For Sale status) from lister form"""
if not app.discogs_api.is_connected():
    messagebox.showwarning("Not Connected", "Please connect to Discogs first")
    return
    
if not app.current_release_id:
    messagebox.showerror("Missing Release", "You must select a specific Discogs release variant first")
    return
    
try:
    price = float(app.price_entry.get())
    media_condition = app.entries["media_condition"].get()
    if not media_condition or media_condition not in REVERSE_GRADE_MAP:
        messagebox.showwarning("Validation Error", "Please select a valid media condition")
        return
except (ValueError, TypeError):
    messagebox.showwarning("Validation Error", "Please enter a valid price")
    return

listing_data = {
    'release_id': app.current_release_id,
    'price': price,
    'status': 'For Sale',  # Live listing
    'condition': REVERSE_GRADE_MAP.get(media_condition),
    'sleeve_condition': REVERSE_GRADE_MAP.get(app.entries["sleeve_condition"].get(), 'Generic'),
    'comments': app.full_desc.get("1.0", tk.END).strip()
}

app.root.config(cursor="watch")
app.root.update()

def live_worker():
    try:
        listing_id = app.discogs_api.create_listing(listing_data)
        if listing_id:
            app.safe_after(0, lambda: app._handle_discogs_live_success(listing_id))
    except Exception as e:
        app.safe_after(0, lambda: messagebox.showerror("Listing Error", str(e)))
    finally:
        app.safe_after(0, lambda: app.root.config(cursor=""))

threading.Thread(target=live_worker, daemon=True).start()

    def _publish_to_discogs_live(self):
"""Publish selected items to Discogs as live (For Sale) listings"""
selected = app.inventory_tree.selection()
if not selected: 
    return

def live_worker():
    for item in selected:
        sku = app.inventory_tree.item(item, "values")[0]
        try:
            record = app._get_inventory_record(sku)
            if not record:
                app.append_log(f"SKU {sku}: Could not find record.", "red")
                continue
            
            errors = validate_listing("discogs", record, app.config)
            if errors:
                app.append_log(f"SKU {sku}: {', '.join(errors)}", "red")
                continue
            
            app.append_log(f"Publishing SKU {sku} live to Discogs...", "black")
            listing_data = {
                "release_id": record.get("discogs_release_id"),
                "condition": REVERSE_GRADE_MAP.get(record.get("media_condition"), "Good (G)"),
                "sleeve_condition": REVERSE_GRADE_MAP.get(record.get("sleeve_condition"), "Good (G)"),
                "price": record.get("price", 0), 
                "status": "For Sale",  # Live listing
                "comments": record.get("description", "")
            }
            
            listing_id = app.discogs_api.create_listing(listing_data)
            if listing_id:
                app.append_log(f"SKU {sku}: Published live to Discogs (ID: {listing_id})", "green")
                try:
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    with app.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE inventory SET discogs_listing_id = ?, discogs_updated_at = ? WHERE sku = ?",
                            (listing_id, now_iso, sku),
                        )
                except Exception as e:
                    logger.error(f"Failed to update inventory with Discogs listing ID: {e}")
                    app.append_log(f"SKU {sku}: Failed to save Discogs listing ID to DB: {e}", "red")
            else:
                app.append_log(f"SKU {sku}: Failed to create live listing", "red")
        except Exception as e:
            app.append_log(f"SKU {sku}: Error - {e}", "red")
    
    app.safe_after(0, app.populate_inventory_view)

threading.Thread(target=live_worker, daemon=True).start()

    def _handle_discogs_draft_success(self, listing_id):
"""Handle successful Discogs draft creation"""
messagebox.showinfo("Success", f"Successfully created Discogs DRAFT (Listing ID: {listing_id})")
if app.editing_sku:
    try:
        with app.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE inventory SET discogs_listing_id = ? WHERE sku = ?", (listing_id, app.editing_sku))
    except Exception as e:
        logger.error(f"Failed to update inventory with listing ID: {e}")

    def _handle_discogs_live_success(self, listing_id):
"""Handle successful Discogs live listing creation"""
messagebox.showinfo("Success", f"Successfully published LIVE to Discogs (Listing ID: {listing_id})")
if app.editing_sku:
    try:
        with app.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE inventory SET discogs_listing_id = ? WHERE sku = ?", (listing_id, app.editing_sku))
    except Exception as e:
        logger.error(f"Failed to update inventory with listing ID: {e}")

    def _prepare_ebay_listing_data(self, sku):
"""Prepare all eBay listing data from current form"""
format_val = app.entries["format"].get() or "LP"
media_cond_str = app.entries["media_condition"].get()

condition_enum = EBAY_INVENTORY_CONDITION_MAP.get(media_cond_str, "USED_GOOD")
condition_id_numeric = EBAY_CONDITION_MAP_NUMERIC.get(media_cond_str, "3000")
category_id = EBAY_VINYL_CATEGORIES.get(format_val, "176985")

ebay_title = app.entries["listing_title"].get() or f"{app.entries['artist'].get()} - {app.entries['title'].get()}"
description_html = app.full_desc.get("1.0", tk.END).strip()

return {
    "sku": sku,
    "title": ebay_title[:80],
    "description": description_html,
    "categoryId": str(category_id),
    "price": float(app.price_entry.get()),
    "quantity": 1,
    "condition_enum": condition_enum,
    "condition_id_numeric": condition_id_numeric,
    "media_condition": app.entries["media_condition"].get(),
    "sleeve_condition": app.entries["sleeve_condition"].get(),
    "currency": "GBP",
    "marketplaceId": app.config.get("marketplace_id", "EBAY_GB"),
    "paymentPolicyId": app.config.get("ebay_payment_policy_id"),
    "returnPolicyId": app.config.get("ebay_return_policy_id"),
    "shippingPolicyId": app.config.get("ebay_shipping_policy_id"),
    "images": app.image_paths,
}


    def refresh_button_states(self):
"""Refresh all button states based on current connection status"""
app._update_connection_status()
# Trigger inventory selection update if items are selected
if hasattr(self, 'inventory_tree') and app.inventory_tree.selection():
    app.on_inventory_selection()


    # ========================================================================
    # DUPLICATE PREVENTION SYSTEM
    # ========================================================================
    
    def _check_existing_listings(self, sku: str) -> dict:
"""Check what listings already exist for this SKU"""
try:
    with app.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ebay_listing_id, discogs_listing_id, ebay_item_draft_id, status 
            FROM inventory WHERE sku = ?
        """, (sku,))
        row = cursor.fetchone()
        
        if row:
            return {
                'ebay_listing_id': row[0],
                'discogs_listing_id': row[1], 
                'ebay_draft_id': row[2],
                'status': row[3],
                'has_ebay': bool(row[0]),
                'has_discogs': bool(row[1]),
                'has_ebay_draft': bool(row[2])
            }
        else:
            return {
                'ebay_listing_id': None,
                'discogs_listing_id': None,
                'ebay_draft_id': None,
                'status': None,
                'has_ebay': False,
                'has_discogs': False,
                'has_ebay_draft': False
            }
except Exception as e:
    logger.error(f"Error checking existing listings for {sku}: {e}")
    return {'has_ebay': False, 'has_discogs': False, 'has_ebay_draft': False}

    def _confirm_overwrite_action(self, platform: str, sku: str, existing_info: dict) -> bool:
"""Ask user to confirm if they want to overwrite/update existing listing"""
existing_ids = []
if platform.lower() == 'ebay':
    if existing_info.get('has_ebay'):
        existing_ids.append(f"Live eBay listing: {existing_info.get('ebay_listing_id')}")
    if existing_info.get('has_ebay_draft'):
        existing_ids.append(f"eBay draft: {existing_info.get('ebay_draft_id')}")
elif platform.lower() == 'discogs':
    if existing_info.get('has_discogs'):
        existing_ids.append(f"Discogs listing: {existing_info.get('discogs_listing_id')}")

if not existing_ids:
    return True  # No existing listings, safe to proceed

existing_text = "\n".join(existing_ids)
message = (
    f"SKU {sku} already has existing {platform} listing(s):\n\n"
    f"{existing_text}\n\n"
    f"Do you want to UPDATE the existing listing instead of creating a duplicate?\n\n"
    f"Choose 'Yes' to update existing listing\n"
    f"Choose 'No' to cancel and avoid duplicates"
)

return messagebox.askyesno(f"Existing {platform} Listing Found", message)

    def _safe_ebay_publish(self, sku: str, listing_data: dict, is_draft: bool = False) -> dict:
"""Safely publish to eBay with duplicate prevention"""
# Check for existing listings
existing = app._check_existing_listings(sku)

# Determine what action to take
action_type = "draft" if is_draft else "live"

if existing['has_ebay'] and not is_draft:
    # Has live listing, asking to publish live again
    if not app._confirm_overwrite_action('eBay', sku, existing):
        return {'success': False, 'cancelled': True, 'reason': 'User cancelled to avoid duplicate'}
    
    # User wants to update - modify existing listing
    app.append_log(f"SKU {sku}: Updating existing eBay listing {existing['ebay_listing_id']}", "blue")
    # Use existing eBay update logic here
    return app.ebay_api.create_draft_listing(listing_data)  # This handles updates
    
elif existing['has_ebay_draft'] and is_draft:
    # Has draft, asking to create another draft
    if not app._confirm_overwrite_action('eBay', sku, existing):
        return {'success': False, 'cancelled': True, 'reason': 'User cancelled to avoid duplicate'}
    
    app.append_log(f"SKU {sku}: Updating existing eBay draft", "blue")
    # Proceed with update
    
elif existing['has_ebay'] and is_draft:
    # Has live listing, wants to create draft - warn but allow
    message = (f"SKU {sku} already has a LIVE eBay listing.\n\n"
              f"Creating a draft will not affect the live listing.\n"
              f"Continue?")
    if not messagebox.askyesno("Live Listing Exists", message):
        return {'success': False, 'cancelled': True, 'reason': 'User cancelled'}

# Proceed with creation/update
result = app.ebay_api.create_draft_listing(listing_data)

# Log the action
if result.get('success'):
    action_desc = "draft saved" if is_draft else "published live"
    app.append_log(f"SKU {sku}: eBay listing {action_desc} successfully", "green")

return result

    def _safe_discogs_publish(self, sku: str, listing_data: dict, is_draft: bool = False) -> int:
"""Safely publish to Discogs with duplicate prevention"""
existing = app._check_existing_listings(sku)

if existing['has_discogs']:
    if not app._confirm_overwrite_action('Discogs', sku, existing):
        app.append_log(f"SKU {sku}: Discogs publish cancelled to avoid duplicate", "orange")
        return None
    
    # User wants to update existing listing
    discogs_id = existing['discogs_listing_id']
    app.append_log(f"SKU {sku}: Updating existing Discogs listing {discogs_id}", "blue")
    
    # Update instead of create
    success = app.discogs_api.update_listing(discogs_id, listing_data)
    if success:
        app.append_log(f"SKU {sku}: Discogs listing updated successfully", "green")
        return discogs_id
    else:
        app.append_log(f"SKU {sku}: Failed to update Discogs listing", "red") 
        return None

# No existing listing, safe to create new
action_desc = "draft" if is_draft else "live listing"
app.append_log(f"SKU {sku}: Creating new Discogs {action_desc}", "black")

listing_id = app.discogs_api.create_listing(listing_data)
if listing_id:
    app.append_log(f"SKU {sku}: Discogs {action_desc} created successfully (ID: {listing_id})", "green")

return listing_id


    def log_sync_activity(self, message):
"""Log sync activity to the text widget"""
def do_log():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    app.sync_log_text.config(state="normal")
    app.sync_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
    app.sync_log_text.see(tk.END)
    app.sync_log_text.config(state="disabled")
app.safe_after(0, do_log)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    if sys.version_info < (3, 7):
messagebox.showerror("Unsupported Python Version", "This application requires Python 3.7 or higher.")
sys.exit(1)

    try:
# Before starting, check for requests_toolbelt
try:
    import requests_toolbelt
except ImportError:
     messagebox.showerror("Missing Dependency", "The 'requests-toolbelt' library is required for this version.\n\nPlease install it by running:\npip install requests-toolbelt")
     sys.exit(1)

root = tk.Tk()
app = VinylToolApp(root)
root.mainloop()
    except Exception as e:
# Create a simple Tk window to show the error if the main app fails
try:
    root = tk.Tk()
    root.withdraw() # Hide the main window
    messagebox.showerror("Fatal Application Error", f"A critical error occurred:\n\n{e}\n\n{traceback.format_exc()}")
except:
    # Fallback to console if GUI fails completely
    print(f"FATAL ERROR: {e}\n{traceback.format_exc()}")
sys.exit(1)

# --- Auto-backup on exit (active profile + core files) ---
import atexit, tarfile, datetime, json
from pathlib import Path as _Path

def _auto_backup_to_backups_dir():
    try:
src_dir = _Path(__file__).resolve().parent
backups = src_dir / "backups"
backups.mkdir(exist_ok=True)
active_profile = "dev"
active_file = src_dir / "profiles" / "active_profile.json"
try:
    data = json.loads(active_file.read_text())
    if isinstance(data, dict) and data.get("profile"):
        active_profile = str(data["profile"])
except Exception:
    pass
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
fname = backups / f"backup_{ts}.tar.gz"
with tarfile.open(fname, "w:gz") as tar:
    for name in ["config.json","api_clients.py","inventory.db","geometry.conf"]:
        p = src_dir / name
        if p.exists():
            tar.add(p, arcname=p.name)
    prof = src_dir / "profiles" / active_profile / "data"
    if prof.exists():
        tar.add(prof, arcname=f"profiles/{active_profile}/data")
print(f"[AutoBackup] Saved {fname}")
    except Exception as e:
print("[AutoBackup] Failed:", e)

atexit.register(_auto_backup_to_backups_dir)
# --- End auto-backup ---

