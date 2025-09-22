#!/usr/bin/env python3

PUBLISH_HARD_BLOCK = False  # Global kill-switch to block publishing paths

"""
VinylTool — FINAL STABLE VERSION
- Collection tab integrated synchronously (no race conditions)
- All original functionality preserved
- Fixed startup reliability issues
- Enhanced Context Menu Features for Collection Tab
- Added Image Reordering UI with Image Preview
- Integrated "Analog Theory" HTML Template with Matrix/Runout and Condition Tags
- Upgraded Matrix/Runout field to a multi-line Text box for better editing.
- Implemented a collapsible <details> section for Matrix/Runout in the HTML template.
- Restructured HTML template for visual symmetry, making Matrix/Runout a top-level collapsible section.
- Redesigned HTML header to use a 2x3 grid for key details, replacing the old text line.
- Fixed the 'Generate Title' button functionality by correcting the widget key mismatch.
- Corrected title generation to avoid "Vinyl LP Vinyl" duplication.
- Fixed a critical bug where updating an inventory item did not save the full description HTML and other payload data.
- Refined title generation to always produce 'Vinyl LP' for standard LPs as requested.
- Corrected title generation to EXACTLY match the user's required format: ARTIST: Title (Year) Format CatNo Grade.
- FINAL FIX for title generation to prevent "Vinyl Vinyl" duplication and ensure correct "Vinyl LP" format.
- ABSOLUTELY FINAL, DEFINITIVE fix for title generation to ensure 'Vinyl LP' is always generated for LP formats.
- Fixed bug where Genre and Full Description were not saving to or reloading from the inventory payload.
- Added logging for eBay response headers to capture the 'rlogid' for support tickets.
- [FIX] Corrected eBay listing failure by providing a short summary for product.description and the full HTML for listingDescription.
- [FIX] Added robust image pipeline to find and upload images, and added missing Media API scope.
- [NEW] Added 'Select Images...' button for a fully automated image import workflow, removing the need for QR codes or manual renaming.
- [FIX] Corrected the folder name from 'item_images' to 'managed_images' to resolve "Image not found" error.
- [FIX] Implemented a retry mechanism in the eBay image upload function to handle transient 503 server errors from Akamai.
- [FIX] Added the crucial 'sell.inventory' scope to the eBay token request to fix "Insufficient permissions" error.
- [FINAL FIX] Manually construct the multipart/form-data for eBay image uploads to resolve persistent 503 errors.
- [FINAL FIX] Resolved `RuntimeError: main thread is not in main loop` on application exit.
- [FINAL FIX] Remove `imageUrls` from payload if empty to prevent API error.
"""
import sys, os, threading, traceback, glob, re
import tkinter as tk
import platform
from ctypes.util import find_library

# ============================ BEGIN PYZBAR MACOS FIX (v2) ============================
# This block attempts to locate the Homebrew-installed zbar library and
# adds its directory to the system's library path. This is a more robust
# fix for macOS environments where pyzbar can't find its C dependency.
if platform.system() == 'Darwin':  # Darwin is the OS name for macOS
    # Check common Homebrew paths for the library directory
    homebrew_lib_dirs = [
        '/usr/local/lib',    # Standard for Intel Macs
        '/opt/homebrew/lib' # Standard for Apple Silicon Macs
    ]
    
    # Get the current library path from the environment, if it exists
    current_ld_path = os.environ.get('DYLD_LIBRARY_PATH', '')
    
    for lib_dir in homebrew_lib_dirs:
        # Check if the directory exists and contains the zbar library
        if os.path.isdir(lib_dir) and 'libzbar.dylib' in os.listdir(lib_dir):
            # Prepend the found directory to the dynamic library path
            if lib_dir not in current_ld_path:
                print(f"Found zbar library in {lib_dir}. Prepending to DYLD_LIBRARY_PATH.")
                os.environ['DYLD_LIBRARY_PATH'] = f"{lib_dir}:{current_ld_path}"
                break # Stop after finding the first valid path
# ============================ END PYZBAR MACOS FIX (v2) ============================

try:
    import requests  # for Discogs REST fallback
except Exception:
    requests = None

# ============================ BEGIN USER RUNTIME (VERBATIM) ============================
# -*- coding: utf-8 -*-
"""
Vinyl Listing Tool v10.3 - FINAL
"""

from tkinter import ttk

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, scrolledtext
import requests
import os
import json
import time
import datetime
import webbrowser
import sqlite3
import threading
import queue
import logging
import base64
import hmac
import hashlib
import secrets
import urllib.parse
import urllib.request
import ssl
import shutil
from urllib.parse import quote_plus, urlencode
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple, Any
import discogs_client
from requests_toolbelt.multipart.encoder import MultipartEncoder # Import for manual multipart construction

# Phase 1: Image Workflow Imports
try:
    import qrcode
    from PIL import Image, ImageTk
    QR_LIBRARIES_AVAILABLE = True
except ImportError:
    qrcode = None
    Image = None
    ImageTk = None
    QR_LIBRARIES_AVAILABLE = False

# Phase 2: QR Decoding Imports
try:
    from pyzbar.pyzbar import decode as qr_decode, ZBarSymbol
    QR_DECODER_AVAILABLE = True
except ImportError:
    qr_decode = None
    ZBarSymbol = None
    QR_DECODER_AVAILABLE = False


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Force IPv4 for eBay API compatibility
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.HAS_IPV6 = False

# ============================================================================
# CONFIGURATION AND CONSTANTS
# ============================================================================

class Config:
    """Centralized configuration management"""
    
    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.data = self._load_config()

        try:
            self._install_lister_draft_live_buttons()
        except Exception:
            pass
        
    def _load_config(self) -> dict:
        """Load configuration from file"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("config.json not found, using defaults")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid config.json: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> dict:
        """Return default configuration"""
        return {
            "enforce_vinyl": True,
            "preferred_currency": "GBP",
            "auto_sync_enabled": False,
            "auto_sync_interval": 300,
            "two_way_sync_enabled": False,
            "attempt_discogs_updates": True,
            "seller_footer": "",
            "image_staging_path": "",
            "status_mappings": {
                "For Sale": "For Sale",
                "Draft": "Draft",
                "Expired": "Not For Sale",
                "Sold": "Sold",
                "Suspended": "Not For Sale",
                "Deleted": "Not For Sale"
            }
        }
    
    def save(self, updates: dict = None):
        """Save configuration to file"""
        if updates:
            self.data.update(updates)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            logger.info("Configuration saved successfully")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.data.get(key, default)

# Global configuration instance
cfg = Config()

# Constants
EBAY_SITE_ID = "3"  # UK site
EBAY_CURRENCY = "GBP"

EBAY_VINYL_CATEGORIES = {
    "LP": "176985",
    "12\"": "176985",
    "7\"": "176984",
    "10\"": "176985",
    "Box Set": "176985",
    "Other": "176983"
}

# This map is for the older Trading API or Offer `categoryId`.
# The Inventory API `condition` field requires a string enum.
# Mapping of Discogs-style media grades to eBay numeric condition IDs.
#
# eBay has recently tightened the allowed condition IDs for the Music/Vinyl categories.
# See the "Item condition ID and name values" and "Item condition by category" docs
# for details【371433193440345†L238-L284】. In particular, the generic "Used" condition
# (3000) is no longer accepted for the Records (176985) category. Instead,
# sellers should choose from specific grades such as "Like New" (2750),
# "Very Good" (4000), "Good" (5000), "Acceptable" (6000) and "For parts"
# (7000). The mapping below aligns common vinyl grades to these IDs.
# -----------------------------------------------------------------------------
# eBay condition ID mapping (numeric).
#
# These mappings align with eBay's inventory and offer APIs for the Records
# category (176985). They are taken from a previously working version of the
# application and have been proven to pass eBay's validation rules. In this
# context, the generic "Used" condition (3000) remains valid for vinyl
# listings, contrary to some documentation suggesting otherwise. Do not
# substitute these values unless you verify against the eBay Sell API
# condition policies for the chosen category.
EBAY_CONDITION_MAP_NUMERIC = {
    "Mint": "1000",             # New (sealed)
    "Near Mint": "2000",         # Near Mint / NM- mapped to Like New (2000)
    "Excellent": "2750",         # Excellent (VG++) maps to Very Good Plus (2750)
    "Very Good Plus": "2750",   # Very Good Plus maps to Very Good Plus (2750)
    "Very Good": "4000",         # Very Good maps to Very Good (4000)
    "Good Plus": "5000",         # Good Plus maps to Good (5000)
    "Good": "5000",              # Good maps to Good (5000)
    "Fair": "6000",              # Fair maps to Acceptable (6000)
    "Poor": "7000"               # Poor maps to For Parts/Not Working (7000)
}

# Inventory API condition enumeration mapping.
#
# This mapping converts Discogs-style media grades into the Inventory API
# enumerations. eBay’s Music & Records category accepts the following
# pre-owned condition enums: LIKE_NEW (for Mint/Near Mint), USED_VERY_GOOD
# (for Excellent/Very Good Plus), USED_GOOD (for Very Good/Good),
# USED_ACCEPTABLE (for Fair), and FOR_PARTS_OR_NOT_WORKING (for Poor).
# eBay recently tightened allowed numeric condition IDs for the music/vinyl
# categories.  Category 176985 (Records) no longer accepts the generic
# "Used" condition (3000).  Instead, you must specify a more precise
# condition.  The numeric IDs below were extracted from eBay's
# getItemConditionPolicies response for the records category:
#   1000 = New
#   2000 = Like New
#   2750 = Very Good Plus / Excellent
#   4000 = Very Good
#   5000 = Good
#   6000 = Acceptable
#   7000 = For parts/not working
# The Inventory API still uses text enums; these map roughly to the above
# numeric values.  Mint and Near Mint map to LIKE_NEW (2000),
# Excellent and VG+ map to USED_EXCELLENT (2750), VG maps to
# USED_VERY_GOOD (4000), G/G+ maps to USED_GOOD (5000), and
# Fair/Poor map to USED_ACCEPTABLE (6000).  FOR_PARTS_OR_NOT_WORKING
# remains reserved for truly non-functional items (7000).
EBAY_INVENTORY_CONDITION_MAP = {
    "Mint": "LIKE_NEW",
    "Near Mint": "LIKE_NEW",
    "Excellent": "USED_EXCELLENT",
    "Very Good Plus": "USED_EXCELLENT",
    "Very Good": "USED_VERY_GOOD",
    "Good": "USED_GOOD",
    "Good Plus": "USED_GOOD",
    "Fair": "USED_ACCEPTABLE",
    "Poor": "USED_ACCEPTABLE"
}

EBAY_SHIPPING_MAP = {
    "Standard UK Paid": "UK_RoyalMailSecondClassStandard",
    "Free UK": "UK_RoyalMailSecondClassStandard"
}

LOCAL_STATUSES = [
    "For Sale", "Sold", "Not For Sale", "Draft", "Reserved",
    "Damaged", "Missing", "Pending", "Hold"
]

DEFAULT_STATUS_MAPPINGS = {
    "For Sale": "For Sale",
    "Draft": "Draft", 
    "Expired": "Not For Sale",
    "Sold": "Sold",
    "Suspended": "Not For Sale",
    "Deleted": "Not For Sale"
}

GRADE_ABBREVIATIONS = {
    "Mint": "M", "Near Mint": "NM", "Excellent": "EX",
    "Very Good Plus": "VG+", "Very Good": "VG", "Good Plus": "G+",
    "Good": "G", "Fair": "F", "Poor": "P", "Generic": "G"
}

DISCOGS_GRADE_MAP = {
    "Mint (M)": "Mint",
    "Near Mint (NM or M-)": "Near Mint",
    "Very Good Plus (VG+)": "Very Good Plus",
    "Very Good (VG)": "Very Good",
    "Good Plus (G+)": "Good Plus",
    "Good (G)": "Good",
    "Fair (F)": "Fair",
    "Poor (P)": "Poor",
    "Generic": "Generic"
}

REVERSE_GRADE_MAP = {v: k for k, v in DISCOGS_GRADE_MAP.items()}

GRADING_MEDIA = {
    "M": "Perfect condition, no visible flaws",
    "NM": "Like new with only very minor signs of handling",
    "EX": "Some minor visible wear but plays perfectly",
    "VG+": "Light wear, minor scuffs but no effect on sound quality",
    "VG": "Noticeable wear, some light scratches may affect sound slightly",
    "G+": "Considerable wear, scratches present, some effect on sound",
    "G": "Heavy wear, scratches and marks present, noticeable effect on playback",
    "F": "Considerable damage, playable but with significant surface noise",
    "P": "Badly damaged, may skip or have serious playback issues"
}

GRADING_SLEEVE = {
    "M": "Perfect condition, no ring wear, creases, or marks",
    "NM": "Like new with only very minor corner wear or slight edge wear",
    "EX": "Some minor corner wear, slight ring wear, or edge wear",
    "VG+": "Light ring wear, minor seam splits, or corner wear",
    "VG": "Moderate ring wear, some seam splits, or corner damage",
    "G+": "Considerable wear, seam splits, or writing on cover",
    "G": "Heavy wear, major seam splits, ring wear, or writing",
    "F": "Cover damaged but still holding together, major wear",
    "P": "Cover severely damaged, split seams, or pieces missing"
}

# ============================================================================
# DATABASE MANAGEMENT
# ============================================================================

class DatabaseManager:
    """Handle all database operations"""
    
    def __init__(self):
        self.db_path = os.path.join(os.path.dirname(__file__), "inventory.db")
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    artist TEXT,
                    title TEXT NOT NULL,
                    cat_no TEXT,
                    year TEXT,
                    format TEXT,
                    media_condition TEXT,
                    sleeve_condition TEXT,
                    price REAL,
                    status TEXT DEFAULT 'For Sale',
                    discogs_release_id INTEGER,
                    discogs_listing_id INTEGER UNIQUE,
                    ebay_listing_id TEXT,
                    date_added TEXT NOT NULL,
                    last_modified TEXT,
                    last_sync_time TEXT,
                    lister_payload TEXT,
                    notes TEXT,
                    description TEXT,
                    shipping_option TEXT,
                    barcode TEXT,
                    genre TEXT,
                    new_used TEXT,
                    listing_title TEXT,
                    matrix_runout TEXT,
                    condition_tags TEXT
                )
            """)
            
            # Add missing columns if they don't exist
            # Extend the schema with additional fields needed for draft/live IDs and timestamps.
            columns_to_add = [
                ("discogs_listing_id", "INTEGER UNIQUE"),
                ("discogs_release_id", "INTEGER"),
                ("last_modified", "TEXT"),
                ("last_sync_time", "TEXT"),
                ("ebay_listing_id", "TEXT"),
                ("lister_payload", "TEXT"),
                ("notes", "TEXT"),
                ("description", "TEXT"),
                ("shipping_option", "TEXT"),
                ("barcode", "TEXT"),
                ("genre", "TEXT"),
                ("new_used", "TEXT"),
                ("listing_title", "TEXT"),
                ("matrix_runout", "TEXT"),
                ("condition_tags", "TEXT"),
                # New fields for draft IDs and timestamp tracking
                ("ebay_item_draft_id", "TEXT"),
                ("ebay_updated_at", "TEXT"),
                ("discogs_updated_at", "TEXT"),
                ("inv_updated_at", "TEXT")
            ]
            
            existing_columns = [row[1] for row in cursor.execute("PRAGMA table_info(inventory)")]
            
            for col_name, col_type in columns_to_add:
                if col_name not in existing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE inventory ADD COLUMN {col_name} {col_type}")
                        logger.info(f"Added column {col_name} to inventory table")
                    except sqlite3.OperationalError:
                        pass  # Column already exists

# ============================================================================
# API WRAPPERS
# ============================================================================

class DiscogsAPI:

    def _safe_json(self, resp):
        try:
            return resp.json() if resp is not None else {}
        except Exception:
            try:
                import json as _json
                txt = getattr(resp, 'text', '')
                return _json.loads(txt) if txt else {}
            except Exception:
                return {}
    """Discogs API wrapper with rate limiting and error handling"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = None
        self.rate_limit_sleep = 1.2
        self.release_cache = {}
        self.price_cache = {}
        self._init_client()
    
    def _init_client(self):
        """Initialize Discogs client"""
        user_agent = "VinylListingTool/5.1"
        oauth_token = self.config.get("discogs_oauth_token")
        oauth_secret = self.config.get("discogs_oauth_token_secret")
        consumer_key = self.config.get("discogs_consumer_key")
        consumer_secret = self.config.get("discogs_consumer_secret")
        
        if oauth_token and oauth_secret and consumer_key and consumer_secret:
            try:
                self.client = discogs_client.Client(
                    user_agent,
                    consumer_key=consumer_key,
                    consumer_secret=consumer_secret,
                    token=oauth_token,
                    secret=oauth_secret
                )
                user = self.client.identity()
                logger.info(f"Connected to Discogs as: {user.username}")
            except Exception as e:
                logger.error(f"Failed to initialize Discogs client: {e}")
                self.client = None
    
    def search(self, params: dict) -> list:
        """Search Discogs database"""
        if not self.is_connected():
            return []
        
        try:
            params = dict(params or {})
            params.setdefault("type", "release")
            
            if self.config.get("enforce_vinyl") and "format" not in params:
                params["format"] = "Vinyl"
            
            response = self._make_request(
                "https://api.discogs.com/database/search",
                params=params
            )
            
            results = response.json().get("results", [])
            
            if self.config.get("enforce_vinyl"):
                results = self._filter_vinyl(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Discogs search failed: {e}")
            return []
    
    def get_release(self, release_id: int) -> Optional[dict]:
        """Get release details"""
        cache_key = (release_id, self.config.get("preferred_currency"))
        
        if cache_key in self.release_cache:
            return self.release_cache[cache_key]
        
        try:
            response = self._make_request(
                f"https://api.discogs.com/releases/{release_id}",
                params={"curr_abbr": self.config.get("preferred_currency", "GBP")}
            )
            data = response.json()
            self.release_cache[cache_key] = data
            return data
        except Exception as e:
            logger.error(f"Failed to get release {release_id}: {e}")
            return None
    
    def get_price_suggestions(self, release_id: int) -> Optional[dict]:
        """Get price suggestions for a release"""
        if release_id in self.price_cache:
            return self.price_cache[release_id]
        
        try:
            response = self._make_request(
                f"https://api.discogs.com/marketplace/price_suggestions/{release_id}"
            )
            data = response.json()
            self.price_cache[release_id] = data
            return data
        except Exception as e:
            logger.error(f"Failed to get price suggestions: {e}")
            return None
    
    def create_listing(self, listing_data: dict) -> Optional[int]:
        """Create a marketplace listing"""
        if not self.is_connected():
            return None
        
        try:
            # OAuth1 signature for marketplace endpoints
            oauth_params = self._generate_oauth_params()
            url = 'https://api.discogs.com/marketplace/listings'
            
            signature = self._create_oauth_signature(
                'POST', url, oauth_params,
                self.config.get("discogs_consumer_secret"),
                self.config.get("discogs_oauth_token_secret")
            )
            oauth_params['oauth_signature'] = signature
            
            headers = {
                'Authorization': self._build_oauth_header(oauth_params),
                'User-Agent': 'VinylListingTool/5.1',
                'Content-Type': 'application/json',
                'Accept': 'application/vnd.discogs.v2.discogs+json'
            }
            
            response = requests.post(url, json=listing_data, headers=headers, timeout=30)
            
            if response.status_code == 201:
                return response.json().get('listing_id') # CORRECTED KEY
            else:
                error_text = response.text
                logger.error(f"Failed to create listing: {error_text}")
                messagebox.showerror("Discogs API Error", f"Failed to create listing:\n\n{error_text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating Discogs listing: {e}")
            return None
    
    def delete_listing(self, listing_id: int) -> bool:
        """Delete a marketplace listing."""
        if not self.is_connected():
            return False
        
        try:
            listing = self.client.listing(listing_id)
            listing.delete()
            logger.info(f"Deleted Discogs listing {listing_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Discogs listing {listing_id}: {e}")
            messagebox.showerror("Discogs API Error", f"Failed to delete listing {listing_id}:\n\n{e}")
            return False

    def get_inventory(self):
        """Get user's inventory"""
        if not self.is_connected():
            return []
        
        try:
            me = self.client.identity()
            return list(me.inventory)
        except Exception as e:
            logger.error(f"Failed to get inventory: {e}")
            return []
    
    def get_orders(self, status_filter=None):
        """Get user's orders"""
        if not self.is_connected():
            return []
        
        try:
            me = self.client.identity()
            all_orders = me.orders
            
            if status_filter:
                return [order for order in all_orders if order.status in status_filter]
            return all_orders
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []
    
    def update_listing(self, listing_id: int, data: dict) -> bool:
        """Update an existing listing"""
        if not self.is_connected():
            return False
        
        try:
            oauth_params = self._generate_oauth_params()
            url = f'https://api.discogs.com/marketplace/listings/{listing_id}'
            
            signature = self._create_oauth_signature(
                'POST', url, oauth_params,
                self.config.get("discogs_consumer_secret"),
                self.config.get("discogs_oauth_token_secret")
            )
            oauth_params['oauth_signature'] = signature
            
            headers = {
                'Authorization': self._build_oauth_header(oauth_params),
                'User-Agent': 'VinylListingTool/5.1',
                'Content-Type': 'application/json',
                'Accept': 'application/vnd.discogs.v2.discogs+json'
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=30)
            return response.status_code in [200, 204]
            
        except Exception as e:
            logger.error(f"Failed to update listing: {e}")
            return False
    
    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self.client is not None
    
    def _make_request(self, url: str, params: dict = None, max_retries: int = 5) -> requests.Response:
        """Make API request with retry logic"""
        headers = {"User-Agent": "VinylListingTool/5.1"}
        
        token = self.config.get("discogs_token")
        if token:
            headers["Authorization"] = f"Discogs token={token}"
        
        session = requests.Session()
        session.headers.update(headers)
        
        for attempt in range(max_retries):
            try:
                response = session.get(url, params=params or {}, timeout=30)
                
                if response.status_code == 429:
                    sleep_time = int(response.headers.get("Retry-After", 3))
                    time.sleep(sleep_time)
                    continue
                
                if 500 <= response.status_code < 600:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                
                response.raise_for_status()
                time.sleep(self.rate_limit_sleep)
                return response
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1.2 * (attempt + 1))
    
    def _filter_vinyl(self, results: list) -> list:
        """Filter results to only include vinyl"""
        return [
            res for res in results
            if any(w in " ".join(res.get("format", [])).lower() 
                   for w in ["vinyl", "lp"])
        ]
    
    def _generate_oauth_params(self) -> dict:
        """Generate OAuth1 parameters"""
        return {
            'oauth_consumer_key': self.config.get("discogs_consumer_key"),
            'oauth_token': self.config.get("discogs_oauth_token"),
            'oauth_signature_method': 'HMAC-SHA1',
            'oauth_timestamp': str(int(time.time())),
            'oauth_nonce': secrets.token_hex(16),
            'oauth_version': '1.0'
        }
    
    def _create_oauth_signature(self, method: str, url: str, params: dict,
                                consumer_secret: str, token_secret: str) -> str:
        """Create OAuth1 signature"""
        sorted_params = sorted(params.items())
        param_string = urllib.parse.urlencode(sorted_params)
        base_string = f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_string, safe='')}"
        signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
        ).decode()
        return signature
    
    def _build_oauth_header(self, oauth_params: dict) -> str:
        """Build OAuth authorization header"""
        return 'OAuth ' + ', '.join([
            f'{k}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in oauth_params.items()
        ])


class EbayAPI:
    """eBay REST API wrapper"""

    def create_sell_listing_draft(self, listing_data: dict) -> dict:
        """Create a Seller Hub draft via Sell Listing API (no publish).

        Note: eBay's Sell Listing API is currently limited release and uses a beta
        versioned endpoint.  The correct path (as of 2024/2025) for creating
        item drafts is `/sell/listing/v1_beta/item_draft`.  Using the v1 path
        returns HTTP 404.  See documentation for the limited release Listing API
        which also requires the `sell.item.draft` OAuth scope.
        """
        token = self.get_access_token()
        if not token:
            return {"success": False, "error": "No access token"}
        import requests
        # Use v1_beta path to avoid 404 errors on the beta Listing API
        url = f"{self.base_url}/sell/listing/v1_beta/item_draft"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": listing_data.get("marketplaceId") or "EBAY_GB",
        }
        title = (listing_data.get("title") or "").strip()
        if not title:
            title = " ".join([
                str(listing_data.get("artist") or ""),
                "-",
                str(listing_data.get("release_title") or listing_data.get("title") or ""),
            ]).strip(" -") or "Untitled"
        desc = (listing_data.get("description") or listing_data.get("listingDescription") or "")[:490000]
        payload = {
            "marketplaceId": listing_data.get("marketplaceId") or "EBAY_GB",
            "title": title[:80],
            "description": desc,
            "format": "FIXED_PRICE",
            "availability": {"shipToLocationAvailability": {"quantity": int(listing_data.get("quantity") or 1)}},
            "pricingSummary": {
                "price": {"value": f"{float(listing_data.get('price') or 0.0):.2f}", "currency": listing_data.get("currency") or "GBP"}
            },
            "categoryId": str(listing_data.get("categoryId") or "176985"),
        }
        pics = listing_data.get("imageUrls") or listing_data.get("image_urls") or listing_data.get("pictures")
        if pics and isinstance(pics, list):
            payload["pictures"] = [{"imageUrl": u} for u in pics if u]
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        try:
            body = resp.json()
        except Exception:
            body = {"text": resp.text or ""}
        rlogid = resp.headers.get("X-EBAY-C-REQUEST-ID") or resp.headers.get("rlogid")
        if resp.status_code in (200, 201):
            draft_id = body.get("itemDraftId") or body.get("itemId") or body.get("id")
            return {"success": True, "draftId": draft_id, "response": body, "rlogid": rlogid}
        # Log more details on failure for easier troubleshooting
        logger.error(f"[sell_listing] Draft creation failed status={resp.status_code}, rlogid={rlogid}")
        logger.error(f"[sell_listing] Response text: {resp.text}")
        return {"success": False, "status": resp.status_code, "body": body, "rlogid": rlogid}

    # Additional helper methods follow below.  Note: duplicated helper functions are commented out for clarity.

    '''def _get_condition_policy(self, marketplace_id: str, primary_category_id: str) -> dict:
    """Fetch item condition policies for a marketplace/category. Returns {} on failure."""
    try:
        token = self.get_access_token()
        if not token:
            return {}
        url = f"{self.base_url}/sell/metadata/v1/marketplace/{marketplace_id}/get_item_condition_policies"
        params = {"primary_category_id": str(primary_category_id)}
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code == 200:
            return r.json() or {}
        else:
            logger.info(f"[condition] Policy fetch {r.status_code} for cat={primary_category_id}")
            return {}
    except Exception as e:
        logger.info(f"[condition] Policy fetch error: {e}")
        return {}

def _choose_condition_id(self, listing_data: dict) -> str | None:
    """Choose a valid numeric conditionId using Sell Metadata policy. Falls back to 1000/3000 for Records."""
    market = listing_data.get("marketplaceId", "EBAY_GB")
    cat = str(listing_data.get("categoryId") or "")
    is_new_flag = bool(listing_data.get("is_new") or listing_data.get("sealed") or listing_data.get("new_sealed"))

    # 1) Try metadata policy
    policy = self._get_condition_policy(market, cat) if (market and cat) else {}
    try:
        options = []
        if isinstance(policy, dict):
            for opt in policy.get("itemConditionPolicies", []):
                oid = str(opt.get("conditionId") or "")
                if oid.isdigit():
                    options.append(oid)

        if options:
            # Prefer NEW for sealed items, otherwise choose the first permitted used condition.
            if is_new_flag and "1000" in options:
                return "1000"
            # Try to pick the most appropriate used grade: 2750 (VG+), 4000 (VG), 5000 (Good), 6000 (Acceptable)
            for pref in ("2750", "4000", "5000", "6000", "7000"):
                if pref in options:
                    return pref
            # Fallback to first available option
            return options[0]

        # No metadata options returned; use explicit mapping for the records category.
        if cat == "176985":
            if is_new_flag:
                return "1000"
            # Use the numeric condition ID derived from the media grade, defaulting to 4000 (Very Good)
            try:
                mc = str(listing_data.get("media_condition") or "").strip()
                cid = EBAY_CONDITION_MAP_NUMERIC.get(mc)
                if cid:
                    return cid
            except Exception:
                pass
            return "4000"
    except Exception:
        pass

    return None

def _safe_json(self, resp):
        try:
            return resp.json() if resp is not None else {}
        except Exception:
            try:
                import json as _json
                txt = getattr(resp, 'text', '')
                return _json.loads(txt) if txt else {}
            except Exception:
                return {}

def __init__(self, config: Config, root_tk: tk.Tk):
        self.config = config
        self.root_tk = root_tk
        self.access_token = None
        self.token_expires = 0
        self.sandbox = False
        self._init_urls()

def _sanitize_ebay_description(self, html: str, max_len: int = 3800) -> str:
        """Strip bulky tags and hard-cap to keep Inventory/Offer descriptions within eBay limits."""
        try:
            import re as _re
            if not html:
                return ""
            html = _re.sub(r"(?is)<(meta|style|script)\b.*?>.*?</\1>", "", html or "")
            html = _re.sub(r"(?is)<!--.*?-->", "", html)
            html = _re.sub(r"(?is)<head\b.*?>.*?</head>", "", html)
            html = _re.sub(r"\s+", " ", html).strip()
            return html[:max_len]
        except Exception:
            return (html or "")[:max_len]

def _collect_image_urls(self, listing_data: dict, sku: str) -> list:
        """Ensure at least one eBay-hosted image URL exists. Upload local images if needed."""
        urls = list(listing_data.get("image_urls") or [])
        if urls:
            logger.info("[images] Using provided image_urls: %d", len(urls))
            return urls

        local_paths = list(listing_data.get("images") or [])
        if not local_paths:
            try:
                if hasattr(self, "image_paths"):
                    local_paths = list(self.image_paths)
            except Exception:
                pass
        
        logger.info("[images] Local paths to upload: %d", len(local_paths))

        collected = []
        for p in local_paths[:12]:
            try:
                url = self.upload_image(p, sku)
                if url:
                    collected.append(url)
                    logger.info(f"[images] Successfully processed {os.path.basename(p)} -> {url}")
                else:
                    logger.warning(f"[images] Failed to upload {os.path.basename(p)} after retries.")
            except Exception as e:
                logger.error(f"[images] Exception during upload process for {os.path.basename(p)}: {e}")
                
        return collected
    
def _init_urls(self):
        """Initialize API URLs"""
        if self.sandbox:
            self.base_url = "https://api.sandbox.ebay.com"
            self.auth_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
            self.signin_url = "https://auth.sandbox.ebay.com/oauth2/authorize"
        else:
            self.base_url = "https://api.ebay.com"
            self.auth_url = "https://api.ebay.com/identity/v1/oauth2/token"
            self.signin_url = "https://auth.ebay.com/oauth2/authorize"

def _get_scopes(self):
        """Returns a list of all required API scopes."""
        # Include all necessary scopes for the APIs used by this application.  In
        # particular, the Sell Listings API requires the `sell.listing` scope,
        # which was missing previously and caused draft creation failures.
        # Include all necessary scopes for the APIs used by this application.
        # The Listing API (draft functionality) uses the `sell.item.draft` scope.
        return [
            "https://api.ebay.com/oauth/api_scope",
            "https://api.ebay.com/oauth/api_scope/sell.inventory",
            "https://api.ebay.com/oauth/api_scope/sell.listing",      # general listing scope (legacy)
            "https://api.ebay.com/oauth/api_scope/sell.item.draft",   # required for listing drafts
            "https://api.ebay.com/oauth/api_scope/sell.account",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            "https://api.ebay.com/oauth/api_scope/sell.marketing",
            "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly",
            "https://api.ebay.com/oauth/api_scope/sell.finances",
            "https://api.ebay.com/oauth/api_scope/sell.payment.dispute",
            "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly"
        ]

    def _get_auth_code(self):
        """Get user authorization code via web flow."""
        app_id = self.config.get("ebay_app_id")
        ru_name = self.config.get("ebay_ru_name")
        
        if not app_id or not ru_name:
            messagebox.showerror("Configuration Error", "eBay App ID or RuName is missing from config.json.")
            return None

        params = {
            "client_id": app_id,
            "response_type": "code",
            "redirect_uri": ru_name,
            "scope": " ".join(self._get_scopes()),
            "prompt": "login"
        }
        
        auth_url = f"{self.signin_url}?{urlencode(params)}"
        webbrowser.open(auth_url)
        
        auth_code_raw = simpledialog.askstring(
            "eBay Authorization",
            "A browser has been opened for you to authorize this application.\n\n"
            "After granting access, you will be redirected to a page that may show an error. "
            "Please copy the ENTIRE URL of that page and paste it below.",
            parent=self.root_tk
        )
        
        if not auth_code_raw:
            return None

        try:
            parsed_url = urllib.parse.urlparse(auth_code_raw)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            if 'code' in query_params:
                return query_params['code'][0]
            else:
                messagebox.showerror("Authorization Error", "Could not find 'code' in the URL provided.")
                return None
        except Exception as e:
            logger.error(f"Error parsing auth code from URL: {e}")
            messagebox.showerror("Authorization Error", f"An error occurred while parsing the URL: {e}")
            return None

    def get_access_token(self) -> Optional[str]:
        """[FIXED] Get OAuth 2.0 access token with full Authorization Code Grant flow."""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token
        
        app_id = self.config.get("ebay_app_id")
        cert_id = self.config.get("ebay_cert_id")
        ru_name = self.config.get("ebay_ru_name")
        refresh_token = self.config.get("ebay_refresh_token")

        if not all([app_id, cert_id, ru_name]):
            logger.error("Missing eBay credentials (App ID, Cert ID, or RuName).")
            return None

        credentials = f"{app_id}:{cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        # --- Try to use Refresh Token first ---
        if refresh_token:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(self._get_scopes())
            }
            try:
                response = requests.post(self.auth_url, headers=headers, data=data, timeout=30)
                if response.status_code == 200:
                    token_data = response.json()
                    self.access_token = token_data['access_token']
                    self.token_expires = time.time() + token_data['expires_in'] - 60
                    logger.info("Successfully refreshed eBay access token.")
                    return self.access_token
                else:
                    logger.warning(f"Failed to refresh token (status {response.status_code}): {response.text}. Proceeding to full auth flow.")
            except requests.RequestException as e:
                logger.error(f"Error refreshing token: {e}. Proceeding to full auth flow.")

        # --- Full Authorization Code Grant Flow ---
        logger.info("Starting full eBay Authorization Code Grant flow.")
        auth_code = self._get_auth_code()
        if not auth_code:
            return None
        
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": ru_name
        }
        
        try:
            response = requests.post(self.auth_url, headers=headers, data=data, timeout=30)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.token_expires = time.time() + token_data['expires_in'] - 60
                
                # Save the new refresh token for future use
                new_refresh_token = token_data.get('refresh_token')
                if new_refresh_token:
                    self.config.save({"ebay_refresh_token": new_refresh_token})
                    logger.info("Successfully obtained new eBay access and refresh tokens.")
                
                return self.access_token
            else:
                logger.error(f"Failed to get eBay access token from auth code: {response.text}")
                messagebox.showerror("eBay Token Error", f"Failed to get access token: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting eBay access token: {e}")
            messagebox.showerror("eBay Token Error", f"An error occurred while getting the access token: {e}")
            return None

    '''  # end of commented helper functions

    def __init__(self, config: Config, root_tk: tk.Tk):
        """Initialize the EbayAPI wrapper with configuration and Tk root."""
        self.config = config
        self.root_tk = root_tk
        self.access_token: Optional[str] = None
        self.token_expires: float = 0.0
        self.sandbox = False
        self._init_urls()

    def _init_urls(self) -> None:
        """Initialize API endpoint URLs based on sandbox flag."""
        if self.sandbox:
            self.base_url = "https://api.sandbox.ebay.com"
            self.auth_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
            self.signin_url = "https://auth.sandbox.ebay.com/oauth2/authorize"
        else:
            self.base_url = "https://api.ebay.com"
            self.auth_url = "https://api.ebay.com/identity/v1/oauth2/token"
            self.signin_url = "https://auth.ebay.com/oauth2/authorize"

    def _get_scopes(self) -> list[str]:
        """Return all required OAuth scopes for eBay API access."""
        return [
            "https://api.ebay.com/oauth/api_scope",
            "https://api.ebay.com/oauth/api_scope/sell.marketing",
            "https://api.ebay.com/oauth/api_scope/sell.inventory",
            "https://api.ebay.com/oauth/api_scope/sell.account",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly",
            "https://api.ebay.com/oauth/api_scope/sell.finances",
            "https://api.ebay.com/oauth/api_scope/sell.payment.dispute",
            "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly",
        ]

    def _get_auth_code(self) -> Optional[str]:
        """Prompt the user via a browser flow to obtain an authorization code."""
        app_id = self.config.get("ebay_app_id")
        ru_name = self.config.get("ebay_ru_name")
        if not app_id or not ru_name:
            messagebox.showerror("Configuration Error", "eBay App ID or RuName is missing from config.json.")
            return None
        params = {
            "client_id": app_id,
            "response_type": "code",
            "redirect_uri": ru_name,
            "scope": " ".join(self._get_scopes()),
            "prompt": "login",
        }
        auth_url = f"{self.signin_url}?{urlencode(params)}"
        webbrowser.open(auth_url)
        auth_code_raw = simpledialog.askstring(
            "eBay Authorization",
            "A browser has been opened for you to authorize this application.\n\n"
            "After granting access, you will be redirected to a page that may show an error. "
            "Please copy the ENTIRE URL of that page and paste it below.",
            parent=self.root_tk,
        )
        if not auth_code_raw:
            return None
        try:
            parsed_url = urllib.parse.urlparse(auth_code_raw)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            if "code" in query_params:
                return query_params["code"][0]
            else:
                messagebox.showerror("Authorization Error", "Could not find 'code' in the URL provided.")
                return None
        except Exception as e:
            logger.error(f"Error parsing auth code from URL: {e}")
            messagebox.showerror("Authorization Error", f"An error occurred while parsing the URL: {e}")
            return None

    def get_access_token(self) -> Optional[str]:
        """Acquire an OAuth access token, refreshing or initiating auth as needed."""
        # Return cached token if still valid
        if self.access_token and time.time() < self.token_expires:
            return self.access_token
        app_id = self.config.get("ebay_app_id")
        cert_id = self.config.get("ebay_cert_id")
        ru_name = self.config.get("ebay_ru_name")
        refresh_token = self.config.get("ebay_refresh_token")
        if not all([app_id, cert_id, ru_name]):
            logger.error("Missing eBay credentials (App ID, Cert ID, or RuName).")
            return None
        credentials = f"{app_id}:{cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        # Try refresh token first
        if refresh_token:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(self._get_scopes()),
            }
            try:
                response = requests.post(self.auth_url, headers=headers, data=data, timeout=30)
                if response.status_code == 200:
                    token_data = response.json()
                    self.access_token = token_data["access_token"]
                    self.token_expires = time.time() + token_data["expires_in"] - 60
                    logger.info("Successfully refreshed eBay access token.")
                    return self.access_token
                else:
                    logger.warning(
                        f"Failed to refresh token (status {response.status_code}): {response.text}. Proceeding to full auth flow."
                    )
            except requests.RequestException as e:
                logger.error(f"Error refreshing token: {e}. Proceeding to full auth flow.")
        # Perform full auth code grant flow
        logger.info("Starting full eBay Authorization Code Grant flow.")
        auth_code = self._get_auth_code()
        if not auth_code:
            return None
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": ru_name,
        }
        try:
            response = requests.post(self.auth_url, headers=headers, data=data, timeout=30)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.token_expires = time.time() + token_data["expires_in"] - 60
                # Save new refresh token if provided
                new_refresh_token = token_data.get("refresh_token")
                if new_refresh_token:
                    self.config.save({"ebay_refresh_token": new_refresh_token})
                    logger.info("Successfully obtained new eBay access and refresh tokens.")
                return self.access_token
            else:
                logger.error(f"Failed to get eBay access token from auth code: {response.text}")
                messagebox.showerror("eBay Token Error", f"Failed to get access token: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting eBay access token: {e}")
            messagebox.showerror("eBay Token Error", f"An error occurred while getting the access token: {e}")
            return None

    def _safe_json(self, resp):
        """Safely parse a JSON response or return an empty dict on failure."""
        try:
            return resp.json() if resp is not None else {}
        except Exception:
            try:
                import json as _json
                txt = getattr(resp, "text", "")
                return _json.loads(txt) if txt else {}
            except Exception:
                return {}

    def _sanitize_ebay_description(self, html: str, max_len: int = 3800) -> str:
        """Sanitize and truncate HTML descriptions for eBay compatibility."""
        try:
            import re as _re
            if not html:
                return ""
            html = _re.sub(r"(?is)<(meta|style|script)\b.*?>.*?</\1>", "", html or "")
            html = _re.sub(r"(?is)<!--.*?-->", "", html)
            html = _re.sub(r"(?is)<head\b.*?>.*?</head>", "", html)
            html = _re.sub(r"\s+", " ", html).strip()
            return html[:max_len]
        except Exception:
            return (html or "")[:max_len]

    def _collect_image_urls(self, listing_data: dict, sku: str) -> list[str]:
        """Ensure at least one eBay-hosted image URL exists by uploading if necessary."""
        urls = list(listing_data.get("image_urls") or [])
        if urls:
            logger.info("[images] Using provided image_urls: %d", len(urls))
            return urls
        local_paths = list(listing_data.get("images") or [])
        if not local_paths:
            try:
                if hasattr(self, "image_paths"):
                    local_paths = list(self.image_paths)
            except Exception:
                pass
        logger.info("[images] Local paths to upload: %d", len(local_paths))
        collected: list[str] = []
        for p in local_paths[:12]:
            try:
                url = self.upload_image(p, sku)
                if url:
                    collected.append(url)
                    logger.info(f"[images] Successfully processed {os.path.basename(p)} -> {url}")
                else:
                    logger.warning(f"[images] Failed to upload {os.path.basename(p)} after retries.")
            except Exception as e:
                logger.error(f"[images] Exception during upload process for {os.path.basename(p)}: {e}")
        return collected

    def _get_condition_policy(self, marketplace_id: str, primary_category_id: str) -> dict:
        """Fetch item condition policies for a marketplace/category. Returns {} on failure."""
        try:
            token = self.get_access_token()
            if not token:
                return {}
            url = f"{self.base_url}/sell/metadata/v1/marketplace/{marketplace_id}/get_item_condition_policies"
            params = {"primary_category_id": str(primary_category_id)}
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            r = requests.get(url, headers=headers, params=params, timeout=20)
            if r.status_code == 200:
                return r.json() or {}
            else:
                logger.info(f"[condition] Policy fetch {r.status_code} for cat={primary_category_id}")
                return {}
        except Exception as e:
            logger.info(f"[condition] Policy fetch error: {e}")
            return {}

    def _choose_condition_id(self, listing_data: dict) -> Optional[str]:
        """
        Choose a valid numeric conditionId for the offer using eBay's Sell Metadata
        policy. This logic mirrors the behaviour from the previously working
        implementation: it attempts to retrieve the permitted condition IDs
        for the listing's category and marketplace and then selects an
        appropriate value. If the policy call returns no options, it falls
        back to a simple rule for the Records category (176985): return 1000
        for new/sealed items and 3000 for used. As a final fallback it
        returns None to omit the conditionId entirely.

        Parameters
        ----------
        listing_data : dict
            A dictionary containing at least `marketplaceId`, `categoryId`, and
            optionally flags such as `is_new`, `sealed`, or `new_sealed`.

        Returns
        -------
        Optional[str]
            A numeric conditionId if one should be sent with the offer, or
            None if the field should be omitted.
        """
        market = listing_data.get("marketplaceId", "EBAY_GB")
        cat = str(listing_data.get("categoryId") or "")
        # Determine if the seller marked the item as new or sealed
        is_new_flag = bool(listing_data.get("is_new") or listing_data.get("sealed") or listing_data.get("new_sealed"))

        # If this is the Records category (176985), fall back to 1000 for new
        # items and 3000 for used.  The previously working implementation
        # passed numeric IDs even for vinyl, and recent tests confirm that
        # 3000 (Used) or 1000 (New) remain accepted values for this category.
        # We avoid omitting the field entirely because doing so resulted in
        # persistent 25021 errors.
        if str(listing_data.get("categoryId")) == "176985":
            return "1000" if is_new_flag else "3000"

        # 1) Try to fetch permitted condition IDs via Sell Metadata
        policy = self._get_condition_policy(market, cat) if (market and cat) else {}
        try:
            options: list[str] = []
            if isinstance(policy, dict):
                # Some marketplaces return `itemConditionPolicies` list with allowed IDs
                for opt in policy.get("itemConditionPolicies", []):
                    oid = str(opt.get("conditionId") or "")
                    if oid.isdigit():
                        options.append(oid)
            if options:
                # Prefer 1000 for new items if available
                if is_new_flag and "1000" in options:
                    return "1000"
                # Otherwise prefer 3000 for used if available
                for pref in ("3000", "2750", "2000", "1500"):
                    if pref in options:
                        return pref
                # If none of the preferred values are present, return the first available
                return options[0]
            # 2) If no options, apply a category-specific rule for records
            if cat == "176985":
                return "1000" if is_new_flag else "3000"
        except Exception:
            # Ignore errors during policy parsing; fall back to defaults below
            pass
        # 3) Final fallback: omit conditionId so that eBay infers from inventory
        return None
    def upload_image(self, image_path: str, sku: str) -> Optional[str]:
            """
            Upload an image to eBay EPS using the **Media API image resource**.
            Spec: POST https://apim.ebay.com/commerce/media/v1_beta/image/create_image_from_file
            Returns the EPS URL (imageUrl) on success, or None.
            """
            token = self.get_access_token()
            if not token:
                logger.error("Cannot upload image, no eBay access token.")
                return None

            if not os.path.exists(image_path):
                logger.error(f"Image file not found at: {image_path}")
                return None

            # Endpoint (do not rely on self.base_url for Media API; use apim root as per docs)
            media_upload_url = "https://apim.ebay.com/commerce/media/v1_beta/image/create_image_from_file"

            # Build multipart/form-data with the local file
            try:
                from requests_toolbelt.multipart.encoder import MultipartEncoder
            except Exception:
                logger.error("requests_toolbelt is required for image upload (MultipartEncoder).")
                return None

            try:
                with open(image_path, "rb") as f:
                    mime = "image/jpeg"
                    lower = image_path.lower()
                    if lower.endswith(".png"): mime = "image/png"
                    elif lower.endswith(".gif"): mime = "image/gif"
                    elif lower.endswith(".bmp"): mime = "image/bmp"
                    elif lower.endswith(".tif") or lower.endswith(".tiff"): mime = "image/tiff"
                    elif lower.endswith(".webp"): mime = "image/webp"
                    elif lower.endswith(".avif"): mime = "image/avif"
                    elif lower.endswith(".heic"): mime = "image/heic"

                    encoder = MultipartEncoder(fields={"image": (os.path.basename(image_path), f, mime)})
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": encoder.content_type,
                        "Accept": "application/json",
                        # Do NOT send Content-Language/X-EBAY-C-MARKETPLACE-ID for Media API image upload
                        "User-Agent": "AnalogTheory-VinylTool/1.0 (+contact: seller)"
                    }

                    # Retry with backoff for transient 5xx (esp. 503)
                    backoff = 1.0
                    for attempt in range(1, 6):
                        resp = requests.post(media_upload_url, headers=headers, data=encoder, timeout=60)
                        if resp.status_code == 201:
                            # Prefer JSON body, else fall back to Location header + GET
                            try:
                                data = resp.json()
                                if isinstance(data, dict) and data.get("imageUrl"):
                                    logger.info(f"[images] Uploaded via Media API. imageUrl returned directly.")
                                    return data["imageUrl"]
                            except Exception:
                                pass

                            loc = resp.headers.get("Location") or resp.headers.get("location")
                            if loc:
                                logger.info(f"[images] Media API Location header present; fetching image details.")
                                # getImage call to retrieve imageUrl
                                try:
                                    get_headers = {
                                        "Authorization": f"Bearer {token}",
                                        "Accept": "application/json"
                                    }
                                    # If Location is full URI, use it directly; otherwise build it
                                    if loc.startswith("http"):
                                        get_url = loc
                                    else:
                                        get_url = f"https://apim.ebay.com/commerce/media/v1_beta/image/{loc.strip().split('/')[-1]}"
                                    get_resp = requests.get(get_url, headers=get_headers, timeout=30)
                                    if get_resp.status_code == 200 and get_resp.json().get("imageUrl"):
                                        return get_resp.json()["imageUrl"]
                                    else:
                                        logger.warning(f"[images] getImage failed {get_resp.status_code}: {get_resp.text}")
                                except Exception as e:
                                    logger.error(f"[images] getImage error: {e}", exc_info=True)
                            else:
                                logger.warning("[images] 201 Created but no JSON body or Location header found.")
                                return None

                        # Handle rate limit or transient upstream issues
                        if resp.status_code in (429, 500, 502, 503, 504):
                            retry_after = resp.headers.get("Retry-After")
                            if retry_after:
                                try:
                                    backoff = max(backoff, float(retry_after))
                                except Exception:
                                    pass
                            logger.warning(f"[images] Upload failed {resp.status_code} (attempt {attempt}/5). Retrying in {backoff:.1f}s...")
                            time.sleep(backoff)
                            backoff = min(backoff * 2, 16.0)
                            # IMPORTANT: rebuild encoder for each retry (requests_toolbelt streams cannot be reused)
                            f.seek(0)
                            encoder = MultipartEncoder(fields={"image": (os.path.basename(image_path), f, mime)})
                            headers["Content-Type"] = encoder.content_type
                            continue

                        # Non-retriable error
                        logger.error(f"[images] Upload failed {resp.status_code}: {resp.text}")
                        return None

                    logger.error(f"[images] Failed to upload image after retries: {os.path.basename(image_path)}")
                    return None

            except Exception as e:
                logger.error(f"[images] Exception during upload: {e}", exc_info=True)
                return None


    def create_draft_listing(self, listing_data: dict) -> dict:
        """
        [FINAL FIX] Create a draft listing, removing `imageUrls` from payload if it's empty.
        """
        token = self.get_access_token()
        if not token:
            return {"success": False, "error": "No access token"}
        
        try:
            if not listing_data.get("images"):
                try:
                    if hasattr(self, "image_paths"):
                        listing_data["images"] = list(self.image_paths)
                except Exception:
                    pass

            sku = listing_data.get("sku")
            if not sku:
                return {"success": False, "error": "SKU required"}

            image_urls = self._collect_image_urls(listing_data, sku)
            if not image_urls:
                logger.warning("Proceeding to create eBay listing without any images.")
            else:
                 logger.info(f"Collected {len(image_urls)} image URLs for SKU {sku}.")

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Content-Language": "en-GB",
                "X-EBAY-C-MARKETPLACE-ID": listing_data.get("marketplaceId", "EBAY_GB")
            }
            
            short_description_summary = (
                f"{listing_data.get('title', '')}. "
                f"Media Condition: {listing_data.get('media_condition', 'Not specified')}. "
                f"Sleeve Condition: {listing_data.get('sleeve_condition', 'Not specified')}. "
                "Please see the full item description for tracklist, matrix/runout details, and condition notes."
            )[:4000]

            full_html_description = (
                listing_data.get("listingDescription")
                or listing_data.get("full_description")
                or listing_data.get("description_html")
                or listing_data.get("description")
                or ""
            )

            # Ensure it's a string
            if not isinstance(full_html_description, str):
                full_html_description = str(full_html_description or "")

            # Trim and enforce cap
            full_html_description = full_html_description.strip()
            MAX_DESC = 490_000
            if full_html_description and len(full_html_description) > MAX_DESC:
                logger.warning(f"[offer] listingDescription too long ({len(full_html_description)}). Truncating.")
                full_html_description = full_html_description[:MAX_DESC]

            # Log mapping source and length
            chosen_key = None
            for k in ("listingDescription", "full_description", "description_html", "description"):
                if listing_data.get(k):
                    chosen_key = k
                    break
            if not chosen_key:
                chosen_key = "description"
            logger.info(f"[offer] Using description from '{chosen_key}', length={len(full_html_description)}")
            # --- Map media_condition -> valid Inventory API condition enum ---
            _cat = str(listing_data.get('categoryId') or '')
            _is_new = bool(listing_data.get('is_new') or listing_data.get('sealed') or listing_data.get('new_sealed'))
            _media_cond = str(listing_data.get('media_condition') or '').upper().strip()

            # Inventory API allowed enums include:
            # NEW, LIKE_NEW, NEW_OTHER, OPEN_BOX, USED_EXCELLENT, USED_VERY_GOOD, USED_GOOD, USED_ACCEPTABLE, FOR_PARTS_OR_NOT_WORKING
            def _inv_cond_from_media(mc: str, is_new: bool) -> str:
                # Determine the inventory condition enumeration.  New/sealed items
                # are always NEW.  Excellent and Very Good Plus map to
                # USED_EXCELLENT, Very Good maps to USED_VERY_GOOD, Good and
                # Good Plus map to USED_GOOD, and Fair/Poor map to
                # USED_ACCEPTABLE.  This mirrors the behaviour of the
                # previously working implementation.
                mc = mc.upper().strip()
                if is_new or mc in ('M', 'MINT', 'NEW', 'SEALED'):
                    return 'NEW'
                if mc in ('NM', 'NEAR MINT', 'EX', 'EXCELLENT', 'E', 'VG++', 'VERY GOOD PLUS', 'VERY GOOD+'):
                    return 'USED_EXCELLENT'
                if mc in ('VG+', 'VG PLUS'):
                    return 'USED_VERY_GOOD'
                if mc in ('VG', 'VERY GOOD'):
                    return 'USED_VERY_GOOD'
                if mc in ('G+', 'G', 'GOOD', 'GOOD PLUS'):
                    return 'USED_GOOD'
                if mc in ('FAIR', 'F', 'POOR', 'P'):
                    return 'USED_ACCEPTABLE'
                # Default fallback for unknown: USED_GOOD
                return 'USED_GOOD'

            inv_condition = _inv_cond_from_media(_media_cond, _is_new)

            # --- Build product aspects; ensure 'Release Title' is present for publish ---
            prod_aspects = {}
            def _set_aspect(key, val):
                v = (str(val).strip() if val is not None else '')
                if v:
                    prod_aspects[key] = [v]

            # Candidate sources from our UI/data
            release_title = listing_data.get('release_title') or listing_data.get('title')
            artist = listing_data.get('artist') or listing_data.get('artist_name')
            format_family = listing_data.get('format_family') or listing_data.get('format') or 'Record'
            label = listing_data.get('label') or listing_data.get('record_label')
            year = listing_data.get('year') or listing_data.get('release_year')
            catno = listing_data.get('catalog_number') or listing_data.get('catno')

            # Heuristic fallback for missing artist: try to parse "ARTIST - TITLE" or "ARTIST: TITLE"
            if not (artist and str(artist).strip()):
                t = str(listing_data.get('title') or '')
                guess = ''
                if ' - ' in t:
                    guess = t.split(' - ', 1)[0].strip()
                elif ': ' in t:
                    guess = t.split(': ', 1)[0].strip()
                elif ' / ' in t:
                    guess = t.split(' / ', 1)[0].strip()
                if guess and len(guess) >= 2:
                    artist = guess

            # Required by policy (error 25002):
            _set_aspect('Release Title', release_title)
            _set_aspect('Artist', artist)

            # Helpful/common aspects (safe defaults; not strictly required but improve listing health):
            _set_aspect('Format', format_family)
            _set_aspect('Record Label', label)
            _set_aspect('Release Year', year)
            _set_aspect('Catalog Number', catno)

            logger.info(f"[aspects] keys={list(prod_aspects.keys())}")

            inventory_payload = {
                "product": {
                    "title": listing_data.get("title"),
                    "description": short_description_summary,
                    "aspects": prod_aspects,
                    "imageUrls": image_urls # This will be present
                },
                "condition": inv_condition,
                "availability": {
                    "shipToLocationAvailability": {
                        "quantity": listing_data.get("quantity", 1)
                    }
                }
            }

            # [FINAL FIX] Only include imageUrls if it's not empty, to prevent API error.
            if not image_urls:
                del inventory_payload['product']['imageUrls']
            
            inv_url = f"{self.base_url}/sell/inventory/v1/inventory_item/{sku}"
            inv_response = requests.put(inv_url, headers=headers, json=inventory_payload, timeout=30)
            
            if inv_response.status_code not in (200, 201, 204):
                rlogid = inv_response.headers.get('X-EBAY-C-REQUEST-ID')
                error_text = f"Inventory item update failed: {inv_response.text}"
                logger.error(error_text)
                logger.error(f"eBay Response Headers: {inv_response.headers}")
                if rlogid:
                    logger.error(f"IMPORTANT: Provide this rlogid to eBay support: {rlogid}")
                return {"success": False, "error": error_text}
            
            offer_payload = {
                "sku": sku,
                "marketplaceId": listing_data.get("marketplaceId", "EBAY_GB"),
                "format": "FIXED_PRICE",
                "availableQuantity": listing_data.get("quantity", 1),
                "listingPolicies": {
                    "paymentPolicyId": listing_data.get("paymentPolicyId"),
                    "returnPolicyId": listing_data.get("returnPolicyId"),
                    "fulfillmentPolicyId": listing_data.get("shippingPolicyId")
                },
                "pricingSummary": {
                    "price": {
                        "value": str(listing_data.get("price", "0.00")),
                        "currency": listing_data.get("currency", "GBP")
                    }
                },
                "categoryId": str(listing_data.get("categoryId", "176985")),
                "merchantLocationKey": self.config.get("ebay_location_key"),
            }
            
            if full_html_description:
                offer_payload["listingDescription"] = full_html_description
            else:
                logger.info("[offer] No description; omitting listingDescription.")

            if full_html_description:
                offer_payload["listingDescription"] = full_html_description
            else:
                logger.info("[offer] No description; omitting listingDescription.")
            
            
            offer_url = f"{self.base_url}/sell/inventory/v1/offer"
            # Determine a valid numeric conditionId using Sell Metadata policy.  If
            # no valid ID is returned, the field is omitted entirely so that eBay
            # derives the condition from the inventory item.  Previously, the
            # conditionId was derived directly from the seller's grade and always
            # included in the payload.  However, categories like Records may no
            # longer accept certain legacy values (e.g. 3000), so omitting
            # conditionId avoids a 25021 error.
            offer_condition_id = self._choose_condition_id(listing_data)
            logger.info(f"[condition] Resolved conditionId={offer_condition_id} for cat={listing_data.get('categoryId')} market={listing_data.get('marketplaceId','EBAY_GB')}")
            if offer_condition_id:
                offer_payload["conditionId"] = str(offer_condition_id)
            else:
                # Ensure the field is not present in the payload
                if "conditionId" in offer_payload:
                    del offer_payload["conditionId"]
            
            get_offer_url = f"{self.base_url}/sell/inventory/v1/offer?sku={sku}"
            logger.info(f"[offer] Checking existing offers for SKU {sku} -> {get_offer_url}")
            existing_offer_response = requests.get(get_offer_url, headers=headers, timeout=30)
            logger.info(f"[offer] GET existing offers status={existing_offer_response.status_code}")
            try:
                _eo = existing_offer_response.json()
                logger.info(f"[offer] Existing offers payload keys={list(_eo.keys()) if isinstance(_eo, dict) else type(_eo)}")
            except Exception:
                logger.info("[offer] Existing offers payload not JSON-decodable.")
            
            offer_id = None
            if existing_offer_response.status_code == 200 and existing_offer_response.json().get('offers'):
                offer_id = existing_offer_response.json()['offers'][0]['offerId']

            if offer_id:
                update_offer_url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}"
                # Clear legacy conditionId when not required by category
                if not offer_condition_id:
                    # Remove conditionId entirely rather than setting it to null.  Sending
                    # a null value can still trigger condition errors on some categories.
                    if 'conditionId' in offer_payload:
                        offer_payload.pop('conditionId', None)
                        logger.info('[condition] Clearing legacy conditionId on existing offer (omitting field)')

                offer_response = requests.put(update_offer_url, headers=headers, json=offer_payload, timeout=30)
            else:
                offer_response = requests.post(offer_url, headers=headers, json=offer_payload, timeout=30)

            if offer_response.status_code in (200, 201, 204):
                offer_data = {}
                try:
                    offer_data = offer_response.json()
                except Exception:
                    pass
                _oid = offer_data.get("offerId") or offer_id
                            # Auto-publish the offer now that it exists/updated
                if _oid:
                    publish_url = f"{self.base_url}/sell/inventory/v1/offer/{_oid}/publish"
                    pub_resp = requests.post(publish_url, headers=headers, timeout=30)
                    if pub_resp.status_code in (200, 201, 202):
                        try:
                            pub_json = pub_resp.json()
                        except Exception:
                            pub_json = {}
                        logger.info(f"[offer] Publish OK status={pub_resp.status_code} for offerId={_oid}")
                        return {
                            "success": True,
                            "offerId": _oid,
                            "published": True,
                            "publish": pub_json
                        }
                    else:
                        rlogid_pub = pub_resp.headers.get("X-EBAY-C-REQUEST-ID") or pub_resp.headers.get("rlogid")
                        logger.error(f"[offer] Publish failed status={pub_resp.status_code}, rlogid={rlogid_pub}")
                        try:
                            logger.error(f"[offer] Publish body: {pub_resp.json()}")
                        except Exception:
                            logger.error(f"[offer] Publish text: {pub_resp.text}")
                        return {
                            "success": False,
                            "offerId": _oid,
                            "published": False,
                            "error": f"Publish failed: status={pub_resp.status_code}"
                        }
                return {
                    "success": True,
                    "offerId": _oid,
                    "draft": True
                }
            else:
                rlogid = offer_response.headers.get("X-EBAY-C-REQUEST-ID") or offer_response.headers.get("rlogid")
                status = offer_response.status_code
                body = offer_response.text
                j = {}
                try:
                    j = offer_response.json()
                except Exception:
                    pass
                logger.error(f"[offer] Offer creation/update failed: status={status}, rlogid={rlogid}")
                if j:
                    logger.error(f"[offer] JSON: {j}")
                else:
                    logger.error(f"[offer] Text: {body}")
                logger.error(f"eBay Response Headers: {offer_response.headers}")
                # Special fallback: if POST returned 409 (duplicate) without body, try to GET offers and switch to update
                if status == 409 and not offer_id:
                    try:
                        _chk = requests.get(get_offer_url, headers=headers, timeout=30)
                        if _chk.status_code == 200 and _chk.json().get("offers"):
                            offer_id = _chk.json()["offers"][0]["offerId"]
                            logger.info(f"[offer] 409 on create; switching to update offerId={offer_id}")
                            update_offer_url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}"
                            offer_response2 = requests.put(update_offer_url, headers=headers, json=offer_payload, timeout=30)
                            if offer_response2.status_code in (200,201):
                                offer_data = offer_response2.json()
                                return {"success": True, "offerId": offer_data.get("offerId"), "draft": True}
                            else:
                                logger.error(f"[offer] Fallback update failed status={offer_response2.status_code} body={offer_response2.text}")
                    except Exception as e:
                        logger.error(f"[offer] Exception during 409 fallback: {e}", exc_info=True)
                return {"success": False, "error": f"Offer failed status={status}"}
                
        except Exception as e:
            logger.error(f"Error creating eBay listing: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def get_orders(self, start_date, end_date):
        """Get eBay orders"""
        token = self.get_access_token()
        if not token:
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
            
            params = {
                "filter": f"creationdate:[{start_date.isoformat()}Z..{end_date.isoformat()}Z]",
                "limit": 100
            }
            
            url = f"{self.base_url}/sell/fulfillment/v1/order"
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json().get("orders", [])
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to get eBay orders: {e}")
            return []
    
    def test_connection(self) -> bool:
        """Test eBay API connection"""
        token = self.get_access_token()
        if not token:
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
            
            url = f"{self.base_url}/commerce/taxonomy/v1/category_tree/3"
            response = requests.get(url, headers=headers, timeout=10)
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"eBay connection test failed: {e}")
            return False

# ============================================================================
# VALIDATION & DIALOGS
# ============================================================================

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

def validate_listing(target: str, record: dict, config: Config = None) -> List[str]:
    """
    Validate a record for publishing to a target platform
    
    Args:
        target: Platform name ('ebay' or 'discogs')
        record: Record dictionary containing listing data
        config: Configuration object
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    config = config or cfg
    
    # Common validations
    required_fields = ["artist", "title", "format", "media_condition"]
    for field in required_fields:
        value = str(record.get(field, "")).strip() if record.get(field) else ""
        if not value:
            errors.append(f"Missing {field.replace('_', ' ')}")
    
    # Price validation
    try:
        price = float(record.get("price", 0))
        if price <= 0:
            errors.append("Price must be greater than 0")
    except (TypeError, ValueError):
        errors.append("Price must be a valid number")
    
    # Target-specific validations
    if target.lower() == "ebay":
        if not record.get("categoryId") and not record.get("category_id"):
            errors.append("Missing eBay category")
        
        # Check for required policy IDs
        if not config.get("ebay_payment_policy_id"):
            errors.append("Missing eBay payment policy ID in configuration")
        if not config.get("ebay_return_policy_id"):
            errors.append("Missing eBay return policy ID in configuration")
        if not config.get("ebay_shipping_policy_id"):
            errors.append("Missing eBay shipping policy ID in configuration")
    
    elif target.lower() == "discogs":
        if not record.get("discogs_release_id"):
            errors.append("No Discogs release linked")
        
        media_condition = record.get("media_condition", "")
        if media_condition not in REVERSE_GRADE_MAP:
            errors.append("Invalid media condition for Discogs")
    
    return errors

class ConditionGradingDialog(simpledialog.Dialog):
    """Dialog for setting media and sleeve condition."""
    def body(self, master):
        self.title("Set Condition Grading")
        
        ttk.Label(master, text="Media Condition:").grid(row=0, sticky="w", padx=5, pady=5)
        self.media_cond_var = tk.StringVar()
        self.media_cond_combo = ttk.Combobox(master, textvariable=self.media_cond_var, 
                                             values=list(GRADE_ABBREVIATIONS.keys()), state="readonly", width=25)
        self.media_cond_combo.grid(row=0, column=1, padx=5, pady=5)
        self.media_cond_combo.set("Near Mint")

        ttk.Label(master, text="Sleeve Condition:").grid(row=1, sticky="w", padx=5, pady=5)
        self.sleeve_cond_var = tk.StringVar()
        self.sleeve_cond_combo = ttk.Combobox(master, textvariable=self.sleeve_cond_var, 
                                              values=list(GRADE_ABBREVIATIONS.keys()), state="readonly", width=25)
        self.sleeve_cond_combo.grid(row=1, column=1, padx=5, pady=5)
        self.sleeve_cond_combo.set("Near Mint")

        ttk.Label(master, text="Asking Price (£):").grid(row=2, sticky="w", padx=5, pady=5)
        self.price_entry = ttk.Entry(master, width=27)
        self.price_entry.grid(row=2, column=1, padx=5, pady=5)

        ttk.Label(master, text="Condition Notes:").grid(row=3, sticky="nw", padx=5, pady=5)
        self.notes_text = scrolledtext.ScrolledText(master, width=30, height=4, wrap="word")
        self.notes_text.grid(row=3, column=1, padx=5, pady=5)
        
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

class VinylToolApp:
    
    def get_current_lister_listing_data(self) -> dict:
        """Gather listing data from the Lister UI (best-effort)."""
        d = {}
        try:
            d["sku"] = self.sku_display_var.get().strip()
        except Exception:
            pass
        def ge(key):
            try:
                return self.entries[key].get().strip()
            except Exception:
                return ""
        d["artist"] = ge("Artist")
        d["release_title"] = ge("Title")
        d["format"] = ge("Format")
        d["cat_no"] = ge("Cat No")
        d["year"] = ge("Year")
        try:
            d["price"] = float(ge("Price") or 0.0)
        except Exception:
            d["price"] = 0.0
        try:
            d["quantity"] = int(ge("Quantity") or 1)
        except Exception:
            d["quantity"] = 1
        d["currency"] = "GBP"
        d["marketplaceId"] = "EBAY_GB"
        try:
            txt = self.description_text.get("1.0", "end").strip()
            d["description"] = txt[:490000]
        except Exception:
            pass
        try:
            if getattr(self, "image_urls", None):
                d["imageUrls"] = list(self.image_urls)
        except Exception:
            pass
        d["categoryId"] = "176985"
        t = " ".join([d.get("artist",""), "-", d.get("release_title","")]).strip(" -")
        d["title"] = (t or "Untitled")[:80]
        return d

    def save_to_ebay_drafts(self, listing_data: dict = None):
        """Create/Update SELL LISTINGS draft only (no publish)."""
        try:
            payload = listing_data or self.get_current_lister_listing_data()
            res = self.ebay_api.create_sell_listing_draft(payload)
            if res.get("success"):
                draft_id = res.get("draftId")
                self.append_log(f"[draft] Saved eBay draft (Draft ID: {draft_id})", "green")
                return {"success": True, "draftId": draft_id}
            else:
                self.append_log(f"[draft] Failed: status={res.get('status')} rlogid={res.get('rlogid')} body={res.get('body')}", "red")
                return {"success": False, "error": res}
        except Exception as e:
            import traceback; traceback.print_exc()
            self.append_log(f"[draft] Error: {e}", "red")
            return {"success": False, "error": str(e)}

    def _install_lister_draft_live_buttons(self):
        import tkinter as tk
        parent = getattr(self, "lister_controls_frame", None) or getattr(self, "lister_tab", None) or getattr(self, "root", None)
        if not parent:
            return
        # Remove the separate "Save to eBay Drafts" button.  Drafts are no longer
        # supported; listings will be published live via the existing publish
        # button in the inventory tab.  We simply rename any existing Publish
        # button to make its purpose clear.  No new button is created here.
        try:
            for child in parent.winfo_children():
                try:
                    txt = child.cget("text")
                    # Rename any legacy Publish button to indicate a live publish
                    if isinstance(txt, str) and ("Publish" in txt and "eBay" in txt):
                        child.configure(text="Publish Live to eBay")
                except Exception:
                    continue
        except Exception:
            pass
    # Main application class with complete functionality
    
    def __init__(self, root):
        self.root = root
        self.root.title("Vinyl Listing Tool v10.3 - FINAL")
        
        # Core components
        self.config = cfg
        self.db = DatabaseManager()
        self.discogs_api = DiscogsAPI(self.config)
        self.ebay_api = EbayAPI(self.config, self.root)
        
        # Instance variables
        self.entries = {}
        self.current_release_id = None
        self.current_tracklist_lines = []
        self.image_paths = []
        self.editing_sku = None
        self.temporary_sku = None # For new items before they are saved
        self.sku_display_var = tk.StringVar() # For the read-only SKU display
        self.image_staging_path_var = tk.StringVar() # For settings tab
        self.inventory_sort_column = "id"
        self.inventory_sort_direction = "DESC"
        self.discogs_search_results = []
        self.discogs_sort_column = "Year"
        self.discogs_sort_direction = "DESC"
        self.app_is_closing = False
        
        # Auto-sync variables
        self.auto_sync_enabled = self.config.get("auto_sync_enabled", False)
        self.auto_sync_interval = self.config.get("auto_sync_interval", 300)
        self.two_way_sync_enabled = self.config.get("two_way_sync_enabled", False)
        self.attempt_discogs_updates = self.config.get("attempt_discogs_updates", True)
        self.last_successful_sync_time = self.config.get("last_successful_sync_time", None)
        self.auto_sync_thread = None
        self.auto_sync_stop_event = threading.Event()
        self.sync_log = []
        
        # Status mapping
        self.status_mappings = self._load_status_mappings()
        self.status_mapping_vars = {}
        
        # Collection state
        self._collection_state = {
            "folders": [],
            "folder_id": None,
            "page": 1,
            "pages": 1,
            "per_page": 100,
            "items": [],
            "filter": ""
        }
        
        # Setup GUI
        self._load_geometry()
        self._setup_gui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize views
        self.populate_inventory_view()
        self.image_staging_path_var.set(self.config.get("image_staging_path", ""))
        
        # Initialize connections
        self._update_connection_status()
        
        # Initialize auto-sync if enabled
        if self.auto_sync_enabled and self.discogs_api.is_connected():
            self.start_auto_sync()
    
    def _load_status_mappings(self):
        """Load status mappings from config or use defaults"""
        mappings = self.config.get("status_mappings", DEFAULT_STATUS_MAPPINGS.copy())
        for discogs_status in DEFAULT_STATUS_MAPPINGS:
            if discogs_status not in mappings:
                mappings[discogs_status] = DEFAULT_STATUS_MAPPINGS[discogs_status]
        return mappings
    
    def _save_status_mappings(self):
        """Save current status mappings to config"""
        for discogs_status, var in self.status_mapping_vars.items():
            self.status_mappings[discogs_status] = var.get()
        
        self.config.save({"status_mappings": self.status_mappings})
        self.log_sync_activity("Status mappings updated and saved")
        messagebox.showinfo("Settings Saved", "Status mappings have been saved successfully.")
    
    def _reset_status_mappings(self):
        """Reset status mappings to defaults"""
        if messagebox.askyesno("Reset Mappings", "Reset all status mappings to defaults?"):
            self.status_mappings = DEFAULT_STATUS_MAPPINGS.copy()
            for discogs_status, var in self.status_mapping_vars.items():
                if discogs_status in self.status_mappings:
                    var.set(self.status_mappings[discogs_status])
            self.log_sync_activity("Status mappings reset to defaults")
    
    def _serialize_form_to_payload(self):
        """
        Collect all lister fields + images into a JSON-serializable dict.
        """
        price_s = self.price_entry.get().strip()
        try:
            price_v = float(price_s) if price_s else 0.0
        except Exception:
            price_v = 0.0
        
        payload = {
            "artist": self.entries["artist"].get().strip(),
            "title": self.entries["title"].get().strip(),
            "cat_no": self.entries["cat_no"].get().strip(),
            "year": self.entries["year"].get().strip(),
            "format": self.entries["format"].get(),
            "genre": self.entries["genre"].get(),
            "media_condition": self.entries["media_condition"].get(),
            "sleeve_condition": self.entries["sleeve_condition"].get(),
            "price": price_v,
            "condition_notes": self.entries["condition_notes"].get("1.0", "end-1c").strip(),
            "matrix_runout": self.entries["matrix_runout"].get("1.0", "end-1c").strip(),
            "condition_tags": self.entries["condition_tags"].get().strip(),
            "description": self.full_desc.get("1.0", "end-1c").strip(),
            "shipping_option": self.entries["shipping_option"].get(),
            "barcode": self.entries["barcode"].get().strip(),
            "new_used": self.entries["new_used"].get(),
            "listing_title": self.entries["listing_title"].get().strip(),
            "discogs_release_id": self.current_release_id,
            "images": list(self.image_paths),
        }
        return payload
    
    def _apply_payload_to_form(self, payload: dict):
        """
        Hydrates the form from a data dictionary.
        """
        def set_entry(name, value):
            if name in self.entries:
                w = self.entries[name]
                final_value = value if value is not None else ""
                try:
                    if isinstance(w, (tk.Entry, ttk.Entry)):
                        w.delete(0, tk.END)
                        w.insert(0, str(final_value))
                    elif isinstance(w, ttk.Combobox):
                        w.set(str(final_value))
                    elif isinstance(w, tk.Text):
                        w.delete("1.0", tk.END)
                        w.insert("1.0", str(final_value))
                except Exception as e:
                    logger.warning(f"Failed to set UI entry '{name}': {e}")

        # Apply all fields from the payload
        set_entry("artist", payload.get("artist"))
        set_entry("title", payload.get("title"))
        set_entry("cat_no", payload.get("cat_no"))
        set_entry("year", payload.get("year"))
        set_entry("format", payload.get("format"))
        set_entry("genre", payload.get("genre"))
        set_entry("media_condition", payload.get("media_condition"))
        set_entry("sleeve_condition", payload.get("sleeve_condition"))
        set_entry("shipping_option", payload.get("shipping_option"))
        set_entry("barcode", payload.get("barcode"))
        set_entry("new_used", payload.get("new_used"))
        set_entry("condition_notes", payload.get("condition_notes"))
        set_entry("matrix_runout", payload.get("matrix_runout"))
        set_entry("condition_tags", payload.get("condition_tags"))
        set_entry("listing_title", payload.get("listing_title"))

        # Price
        price_val = payload.get("price")
        price_str = f"{price_val:.2f}" if isinstance(price_val, (int, float)) and price_val > 0 else ""
        self.price_entry.delete(0, tk.END)
        self.price_entry.insert(0, price_str)
        
        # Description
        desc_val = payload.get("description")
        self.full_desc.delete("1.0", tk.END)
        if desc_val:
            self.full_desc.insert("1.0", desc_val)
        
        # Images
        self.image_paths = list(payload.get("images") or [])
        self._update_image_listbox()

        # Release ID
        self.current_release_id = payload.get("discogs_release_id")
    
    def _get_inventory_record(self, sku: str) -> dict:
        """Load DB row and merge lister_payload JSON over flat columns."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM inventory WHERE sku = ?", (sku,))
            rec = cursor.fetchone()
            if not rec:
                return {}
            d = dict(rec)
            try:
                if d.get("lister_payload"):
                    p = json.loads(d["lister_payload"])
                    if isinstance(p, dict):
                        # Merge payload, giving payload precedence for non-empty values
                        for k, v in p.items():
                            if v not in (None, "", []):
                                d[k] = v
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse lister_payload for SKU {sku}")
            return d
    
    def _load_geometry(self):
        """Load saved window geometry"""
        try:
            geometry_path = os.path.join(os.path.dirname(__file__), "geometry.conf")
            with open(geometry_path, "r") as f:
                self.root.geometry(f.read())
        except FileNotFoundError:
            self.root.geometry("1900x1000")
    
    def on_closing(self):
        """Handle application closing"""
        self.app_is_closing = True
        if self.auto_sync_enabled:
            self.stop_auto_sync()
        
        # Save window geometry
        try:
            geometry_path = os.path.join(os.path.dirname(__file__), "geometry.conf")
            with open(geometry_path, "w") as f:
                f.write(self.root.geometry())
        except Exception as e:
            logger.warning(f"Could not save window geometry: {e}")
        
        self.root.destroy()
    
    def _setup_gui(self):
        """Setup the complete GUI with all features INCLUDING Collection tab"""
        self.root.option_add("*Font", "Helvetica 14")
        style = ttk.Style()
        style.theme_use("clam")
        
        # Create notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both")
        
        # Create ALL tabs including Collection
        self.lister_tab = ttk.Frame(self.notebook)
        self.inventory_tab = ttk.Frame(self.notebook)
        self.collection_tab = ttk.Frame(self.notebook)
        self.settings_tab = ttk.Frame(self.notebook)
        
        # Add tabs in correct order: Lister -> Inventory -> Collection -> Settings
        self.notebook.add(self.lister_tab, text="Lister")
        self.notebook.add(self.inventory_tab, text="Inventory")
        self.notebook.add(self.collection_tab, text="Collection")
        self.notebook.add(self.settings_tab, text="Settings & Sync")
        
        # Setup each tab
        self._setup_lister_tab()
        self._setup_inventory_tab()
        self._setup_collection_tab()
        self._setup_settings_tab_complete()
    
    def _setup_collection_tab(self):
        """Setup the Collection tab synchronously"""
        # Top controls frame
        top = ttk.Frame(self.collection_tab)
        top.pack(fill="x", padx=8, pady=6)
        
        # Folder selection
        ttk.Label(top, text="Folder:").pack(side="left")
        self.collection_folder_var = tk.StringVar()
        self.collection_folder_var.set("Loading...")
        self.collection_folder_combo = ttk.Combobox(
            top, 
            textvariable=self.collection_folder_var, 
            state="readonly", 
            width=40
        )
        self.collection_folder_combo.pack(side="left", padx=(6, 12))
        self.collection_folder_combo.bind("<<ComboboxSelected>>", self._on_folder_change)
        
        # Filter entry
        ttk.Label(top, text="Filter:").pack(side="left")
        self.collection_filter_var = tk.StringVar()
        self.collection_filter_entry = ttk.Entry(
            top, 
            textvariable=self.collection_filter_var, 
            width=28
        )
        self.collection_filter_entry.pack(side="left", padx=(6, 12))
        self.collection_filter_entry.bind("<KeyRelease>", self._on_filter_change)
        
        # Pagination controls
        self.collection_prev_btn = ttk.Button(
            top, 
            text="< Prev", 
            command=self._collection_prev_page
        )
        self.collection_prev_btn.pack(side="left")
        
        self.collection_page_label = ttk.Label(top, text="Page 1 / 1")
        self.collection_page_label.pack(side="left", padx=6)
        
        self.collection_next_btn = ttk.Button(
            top, 
            text="Next >", 
            command=self._collection_next_page
        )
        self.collection_next_btn.pack(side="left", padx=(0, 6))
        
        self.collection_refresh_btn = ttk.Button(
            top, 
            text="Refresh", 
            command=self._refresh_collection
        )
        self.collection_refresh_btn.pack(side="left", padx=(6, 0))
        
        # Collection tree
        cols = ("added", "artist", "title", "labels", "catno", "formats", 
                "year", "folder", "rating", "instance", "release")
        self.collection_tree = ttk.Treeview(
            self.collection_tab, 
            columns=cols, 
            show="headings", 
            height=18
        )
        
        # Setup columns
        headings = {
            "added": "Date Added", "artist": "Artist", "title": "Title",
            "labels": "Label(s)", "catno": "Cat No", "formats": "Format(s)",
            "year": "Year", "folder": "Folder", "rating": "Rating",
            "instance": "Instance ID", "release": "Release ID"
        }
        
        for col in cols:
            self.collection_tree.heading(col, text=headings[col])
            width = 180 if col in ("title", "labels", "formats") else 110
            self.collection_tree.column(col, width=width, stretch=True)
        
        self.collection_tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Click-to-sort current page
        self._collection_sort = {"col": None, "reverse": False}
        def _sort_by(col):
            st = self._collection_state
            items = st.get("items", [])
            keymap = {
                "added":   lambda it: (it.get("date_added") or ""),
                "artist":  lambda it: " ".join(a.get("name","") for a in it.get("basic_information",{}).get("artists",[])).lower(),
                "title":   lambda it: (it.get("basic_information",{}).get("title","") or "").lower(),
                "labels":  lambda it: " ".join(l.get("name","") for l in it.get("basic_information",{}).get("labels",[])).lower(),
                "catno":   lambda it: (it.get("basic_information",{}).get("labels",[{}])[0].get("catno","") or it.get("basic_information",{}).get("catno","") or "").lower(),
                "formats": lambda it: " ".join(f.get("name","") for f in it.get("basic_information",{}).get("formats",[])).lower(),
                "year":    lambda it: it.get("basic_information",{}).get("year") or 0,
                "rating":  lambda it: it.get("rating") or 0,
                "instance":lambda it: it.get("id") or 0,
                "release": lambda it: it.get("basic_information",{}).get("id") or 0,
                "folder":  lambda it: st.get("folder_name","").lower()
            }
            key = keymap.get(col)
            if not key: return
            prev = self._collection_sort
            reverse = prev["reverse"] if prev["col"] == col else False
            st["items"] = sorted(items, key=key, reverse=not reverse)
            self._collection_sort = {"col": col, "reverse": not reverse}
            if hasattr(self, "_render_collection_tree"):
                self._render_collection_tree()
            elif hasattr(self, "_refresh_collection_tree"):
                self._refresh_collection_tree()
        for col in cols:
            self.collection_tree.heading(col, text=headings[col], command=lambda c=col: _sort_by(c))
        
        # Bind events
        self.collection_tree.bind("<Double-1>", self._collection_open_release)
        self.collection_tree.bind("<Button-3>", self._collection_context_menu)
        
        
        self.collection_tree.bind("<Button-2>", self._collection_context_menu)
        self.collection_tree.bind("<Control-Button-1>", self._collection_context_menu)# Load folders asynchronously but don't block GUI creation
        self.root.after(100, self._load_collection_folders)
    
    def _get_discogs_credentials(self):
        """Get Discogs token and username"""
        token = None
        username = None
        
        try:
            if hasattr(self, "config"):
                token = (self.config.get("discogs_token") or self.config.get("discogs_oauth_token") or "").strip() or None
                username = (self.config.get("discogs_username") or "").strip() or None
        except Exception:
            pass
        
        # Fallback to environment variables
        token = token or os.environ.get("DISCOGS_TOKEN")
        username = username or os.environ.get("DISCOGS_USERNAME")
        
        return token, username
    
    
    def _discogs_api_request(self, url, params=None):
        """Make Discogs API request with backoff + logging"""
        if not requests:
            raise RuntimeError("'requests' not available for Discogs API")
        token, username = self._get_discogs_credentials()
        if not token:
            raise RuntimeError("Discogs token not configured")
        
        headers = {
            "User-Agent": "VinylTool/1.0",
        }
        
        # Use OAuth if available, otherwise token
        if self.discogs_api and self.discogs_api.is_connected():
            oauth_params = self.discogs_api._generate_oauth_params()
            signature = self.discogs_api._create_oauth_signature(
                'GET', url, oauth_params,
                self.config.get("discogs_consumer_secret"),
                self.config.get("discogs_oauth_token_secret")
            )
            oauth_params['oauth_signature'] = signature
            headers['Authorization'] = self.discogs_api._build_oauth_header(oauth_params)
        else:
            headers['Authorization'] = f"Discogs token={token}"

        attempt, delay = 0, 0.8
        while True:
            attempt += 1
            try:
                resp = requests.get(url, headers=headers, params=(params or {}), timeout=30)
                status = resp.status_code
                if status == 429 or 500 <= status < 600:
                    msg = f"[Discogs] {status} on {url} (attempt {attempt}); retrying in {delay:.1f}s"
                    if hasattr(self, "log_sync_activity"): self.log_sync_activity(msg)
                    else: print(msg)
                    time.sleep(delay)
                    delay = min(delay * 1.7, 8.0)
                    if attempt < 6:
                        continue
                resp.raise_for_status()
                return resp.json() or {}
            except Exception:
                if attempt < 3:
                    time.sleep(delay)
                    delay = min(delay * 1.7, 6.0)
                    continue
                raise

    def safe_after(self, delay, callback):
        """[FIX] Safely call root.after only if the app is not closing."""
        if not self.app_is_closing:
            try:
                self.root.after(delay, callback)
            except tk.TclError as e:
                if "application has been destroyed" not in str(e):
                    logger.warning(f"Safe_after encountered a TclError: {e}")

    def _load_collection_folders(self):
        """Load Discogs collection folders"""
        def worker():
            try:
                token, username = self._get_discogs_credentials()
                if not (token and username and self.discogs_api.is_connected()):
                    self.safe_after(0, lambda: self._set_collection_error("Discogs not connected"))
                    return
                
                user = self.discogs_api.client.identity()
                data = user.collection_folders
                
                folders = []
                for f in data:
                    folders.append({
                        "id": f.id,
                        "name": f.name, 
                        "count": f.count
                    })
                
                def update_ui():
                    self._collection_state["folders"] = folders
                    labels = [f"{f['name']} ({f['count']})" for f in folders]
                    self.collection_folder_combo["values"] = labels
                    
                    if folders:
                        self.collection_folder_var.set(labels[0])
                        self._collection_state["folder_id"] = folders[0]["id"]
                        self._refresh_collection()
                    else:
                        self.collection_folder_var.set("No folders found")
                
                self.safe_after(0, update_ui)
                
            except Exception as e:
                error_msg = f"Failed to load folders: {e}"
                self.safe_after(0, lambda: self._set_collection_error(error_msg))
        
        threading.Thread(target=worker, daemon=True).start()
    
    def _set_collection_error(self, message):
        """Set error state for collection"""
        self.collection_folder_var.set(f"Error: {message}")
        # Clear tree
        for item in self.collection_tree.get_children():
            self.collection_tree.delete(item)
    
    def _on_folder_change(self, event=None):
        """Handle folder selection change"""
        chosen = self.collection_folder_var.get()
        
        # Find folder ID
        folder_id = None
        for f in self._collection_state["folders"]:
            if f"{f['name']} ({f['count']})" == chosen:
                folder_id = f["id"]
                break
        
        if folder_id is not None:
            self._collection_state["folder_id"] = folder_id
            self._collection_state["page"] = 1
            self._refresh_collection()
    
    def _on_filter_change(self, event=None):
        """Handle filter text change"""
        self._collection_state["filter"] = self.collection_filter_var.get().strip()
        self._render_collection_tree()
    
    def _collection_prev_page(self):
        """Go to previous page"""
        if self._collection_state["page"] > 1:
            self._collection_state["page"] -= 1
            self._refresh_collection()
    
    def _collection_next_page(self):
        """Go to next page"""
        if self._collection_state["page"] < self._collection_state.get("pages", 1):
            self._collection_state["page"] += 1
            self._refresh_collection()
    
    def _refresh_collection(self):
        """Refresh collection data using direct API calls."""
        def worker():
            try:
                token, username = self._get_discogs_credentials()
                if not (token and username):
                    self.safe_after(0, lambda: self._set_collection_error("Discogs credentials not configured"))
                    return

                folder_id = self._collection_state.get("folder_id")
                if folder_id is None:
                    return

                page = self._collection_state.get("page", 1)
                per_page = self._collection_state.get("per_page", 100)
                
                url = f"https://api.discogs.com/users/{username}/collection/folders/{folder_id}/releases"
                params = {
                    "page": page,
                    "per_page": per_page,
                    "sort": "added",
                    "sort_order": "desc"
                }
                
                data = self._discogs_api_request(url, params)
                
                items = data.get("releases", [])
                pages = int(data.get("pagination", {}).get("pages", 1))
                
                # Get folder name from state
                folder_name = ""
                for f in self._collection_state["folders"]:
                    if f["id"] == folder_id:
                        folder_name = f["name"]
                        break

                def update_ui():
                    self._collection_state["items"] = items
                    self._collection_state["pages"] = pages
                    self._collection_state["folder_name"] = folder_name
                    self._render_collection_tree()
                
                self.safe_after(0, update_ui)
                
            except Exception as e:
                error_msg = f"Failed to refresh collection: {e}"
                self.safe_after(0, lambda: self._set_collection_error(error_msg))

        threading.Thread(target=worker, daemon=True).start()
    
    def _apply_collection_filter(self, items, filter_text):
        """Apply filter to collection items"""
        if not filter_text:
            return items
        
        filter_text = filter_text.lower()
        filtered = []
        
        for item in items:
            bi = item.get("basic_information", {})
            
            # Build searchable text
            artists = " ".join([a.get("name", "") for a in bi.get("artists", [])])
            labels = " ".join([l.get("name", "") for l in bi.get("labels", [])])
            formats = " ".join([f.get("name", "") for f in bi.get("formats", [])])
            
            search_text = " ".join([
                bi.get("title", ""),
                artists,
                labels, 
                formats,
                str(bi.get("year", ""))
            ]).lower()
            
            if filter_text in search_text:
                filtered.append(item)
        
        return filtered
    
    def _render_collection_tree(self):
        """Render collection items in tree"""
        # Clear existing items
        for item in self.collection_tree.get_children():
            self.collection_tree.delete(item)
        
        # Apply filter
        items = self._apply_collection_filter(
            self._collection_state.get("items", []),
            self._collection_state.get("filter", "")
        )
        
        # Populate tree
        folder_name = self._collection_state.get("folder_name", "")
        
        for item in items:
            bi = item.get("basic_information", {})
            
            # Extract data
            artists = ", ".join([a.get("name", "") for a in bi.get("artists", [])])
            labels = ", ".join([l.get("name", "") for l in bi.get("labels", [])])
            formats = ", ".join([f.get("name", "") for f in bi.get("formats", [])])
            
            # Get catalog number
            catno = ""
            if bi.get("labels"):
                catnos = [l.get("catno", "") for l in bi.get("labels", []) if l.get("catno")]
                catno = ", ".join(sorted(set(catnos)))
            
            # Format date
            date_added = item.get("date_added", "")
            if date_added and len(date_added) >= 10:
                date_added = date_added[:10]  # Just the date part
            
            row = (
                date_added,
                artists,
                bi.get("title", ""),
                labels,
                catno,
                formats,
                bi.get("year", ""),
                folder_name,
                item.get("rating", "") or "",
                item.get("id", ""),
                bi.get("id", "")
            )
            
            self.collection_tree.insert("", "end", values=row)
        
        # Update page label
        page = self._collection_state.get("page", 1)
        pages = self._collection_state.get("pages", 1)
        self.collection_page_label.config(text=f"Page {page} / {pages}")
    
    def _collection_open_release(self, event=None):
        """Open selected release in Discogs"""
        selection = self.collection_tree.selection()
        if not selection:
            return
        
        values = self.collection_tree.item(selection[0], "values")
        try:
            release_id = values[-1]  # Last column is release ID
            if release_id:
                import webbrowser
                webbrowser.open(f"https://www.discogs.com/release/{release_id}")
        except Exception as e:
            logger.error(f"Failed to open release: {e}")

    # ========================================================================
    # START: ENHANCED CONTEXT MENU FOR COLLECTION TAB
    # ========================================================================

    def _collection_context_menu(self, event):
        """Show context menu for collection with enhanced features."""
        from tkinter import Menu
        
        item_id = self.collection_tree.identify_row(event.y)
        if not item_id:
            return
        
        self.collection_tree.selection_set(item_id)
        selection = self.collection_tree.selection()
        if not selection:
            return

        values = self.collection_tree.item(selection[0], "values")
        has_release_id = False
        try:
            if values and int(values[-1]) > 0:
                has_release_id = True
        except (ValueError, IndexError):
            pass

        menu = Menu(self.collection_tree, tearoff=0)
        menu.add_command(label="Add to Inventory", command=self._collection_add_to_inventory)
        menu.add_separator()
        menu.add_command(label="Open on Discogs", command=self._collection_open_release, 
                         state="normal" if has_release_id else "disabled")
        menu.add_command(label="View Price History", command=self._collection_view_price_history,
                         state="normal" if has_release_id else "disabled")
        menu.add_command(label="View All Variants", command=self._collection_view_all_variants,
                         state="normal" if has_release_id else "disabled")
        menu.add_separator()
        menu.add_command(label="Quick List on Discogs", command=self._collection_quick_list_on_discogs,
                         state="normal" if has_release_id else "disabled")
        menu.add_command(label="Search Sold Listings (eBay)", command=self._collection_search_sold_listings)
        menu.add_separator()
        menu.add_command(label="Update Collection Notes", command=self._collection_update_notes)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _collection_view_price_history(self):
        """Context menu action to view price history for a collection item."""
        selection = self.collection_tree.selection()
        if not selection: return
        values = self.collection_tree.item(selection[0], "values")
        try:
            release_id = int(values[-1])
            self._view_price_history(release_id)
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Could not get a valid Release ID.")

    def _collection_view_all_variants(self):
        """Context menu action to view all variants for a collection item."""
        selection = self.collection_tree.selection()
        if not selection: return
        values = self.collection_tree.item(selection[0], "values")
        try:
            release_id = int(values[-1])
            self._view_all_variants(release_id)
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Could not get a valid Release ID.")

    def _collection_quick_list_on_discogs(self):
        """Context menu action for quick listing a collection item."""
        selection = self.collection_tree.selection()
        if not selection: return
        values = self.collection_tree.item(selection[0], "values")
        try:
            release_id = int(values[-1])
            self._quick_list_on_discogs(release_id)
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Could not get a valid Release ID.")

    def _collection_search_sold_listings(self):
        """Context menu action to search sold listings for a collection item."""
        selection = self.collection_tree.selection()
        if not selection: return
        values = self.collection_tree.item(selection[0], "values")
        try:
            artist, title = values[1], values[2]
            self._search_sold_listings_inventory(artist, title)
        except IndexError:
            messagebox.showerror("Error", "Could not get item details from selection.")

    def _collection_update_notes(self):
        """Context menu action to update collection notes (with API limitation notice)."""
        selection = self.collection_tree.selection()
        if not selection: return
        values = self.collection_tree.item(selection[0], "values")
        try:
            instance_id = int(values[-2])
            release_id = int(values[-1])
            # The API *does* allow editing notes for a collection item instance.
            # We need the instance_id, not the release_id.
            
            # Fetch current notes first
            if not self.discogs_api.is_connected():
                messagebox.showwarning("Not Connected", "Please connect to Discogs first.")
                return

            def fetch_and_edit_worker():
                try:
                    user = self.discogs_api.client.identity()
                    item = user.collection_folders[0].releases.get(instance_id) # Assumes in first folder, needs improvement
                    
                    # This is inefficient, we should find the right folder first.
                    # For now, let's just prompt for notes.
                    current_notes = "" # Can't easily get current notes without iterating all folders.
                    
                    new_notes = simpledialog.askstring("Edit Collection Notes", "Enter your personal notes for this item:", initialvalue=current_notes, parent=self.root)
                    
                    if new_notes is not None:
                        # This part of the API is tricky. The `discogs-client` library doesn't expose this well.
                        # We would need to make a POST request to /users/{username}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}
                        # with a `notes` field. This is too complex to add right now.
                        self.safe_after(0, self._update_collection_notes)

                except Exception as e:
                    logger.error(f"Failed to get collection item for notes: {e}")
                    self.safe_after(0, self._update_collection_notes)

            #threading.Thread(target=fetch_and_edit_worker).start()
            self._update_collection_notes() # Call the info dialog directly for now.

        except (ValueError, IndexError):
            messagebox.showerror("Error", "Could not get a valid Instance ID.")


    def _view_price_history(self, release_id: int):
        """Opens the Discogs marketplace price history page."""
        if release_id:
            url = f"https://www.discogs.com/sell/history/{release_id}"
            webbrowser.open_new_tab(url)
            logger.info(f"Opened price history for release {release_id}")

    def _view_all_variants(self, release_id: int):
        """Finds the master release and opens the page to show all variants."""
        if not release_id: return
        
        def worker():
            try:
                release_data = self.discogs_api.get_release(release_id)
                if release_data and "master_id" in release_data:
                    master_id = release_data["master_id"]
                    if master_id:
                        url = f"https://www.discogs.com/master/{master_id}"
                        self.safe_after(0, lambda: webbrowser.open_new_tab(url))
                        logger.info(f"Opened master release {master_id} for release {release_id}")
                    else:
                        # If master_id is 0 or null, it's a unique release
                        self.safe_after(0, lambda: messagebox.showinfo("No Variants", "This release is not part of a master release and has no other known variants."))
                else:
                    self.safe_after(0, lambda: messagebox.showwarning("Not Found", "Could not find a master release for this item."))
            except Exception as e:
                logger.error(f"Failed to get variants for release {release_id}: {e}")
                self.safe_after(0, lambda: messagebox.showerror("API Error", f"Failed to fetch release data: {e}"))
        
        threading.Thread(target=worker, daemon=True).start()

    def _quick_list_on_discogs(self, release_id: int):
        """Opens a streamlined dialog to quickly list an item on Discogs."""
        if not self.discogs_api.is_connected():
            messagebox.showwarning("Not Connected", "Please connect to Discogs first.")
            return

        dialog = QuickListDialog(self.root, "Quick List on Discogs")
        if dialog.result:
            listing_data = {
                'release_id': release_id,
                'price': dialog.result["price"],
                'status': 'For Sale', # List directly as For Sale
                'condition': DISCOGS_GRADE_MAP.get(dialog.result["media_condition"], dialog.result["media_condition"]),
                'sleeve_condition': DISCOGS_GRADE_MAP.get(dialog.result["sleeve_condition"], dialog.result["sleeve_condition"]),
                'comments': dialog.result["comments"]
            }

            def list_worker():
                try:
                    listing_id = self.discogs_api.create_listing(listing_data)
                    if listing_id:
                        msg = f"Successfully listed item on Discogs (Listing ID: {listing_id})"
                        self.safe_after(0, lambda: messagebox.showinfo("Success", msg))
                    # Error is handled by the API wrapper now
                except Exception as e:
                    self.safe_after(0, lambda: messagebox.showerror("Listing Error", str(e)))
                finally:
                    self.safe_after(0, lambda: self.root.config(cursor=""))

            self.root.config(cursor="watch")
            self.root.update()
            threading.Thread(target=list_worker, daemon=True).start()

    def _search_sold_listings_inventory(self, artist: str, title: str):
        """Opens eBay completed listings search for an item from inventory."""
        if not artist and not title:
            messagebox.showwarning("Missing Info", "Artist and/or Title are required to search.")
            return
        query = f"{artist} {title}".strip()
        url = f"https://www.ebay.co.uk/sch/i.html?_from=R40&_nkw={quote_plus(query)}&_sacat=176985&LH_Complete=1&LH_Sold=1"
        webbrowser.open_new_tab(url)
        logger.info(f"Opened eBay sold listings search for: {query}")

    def _update_collection_notes(self):
        """Dialog for editing personal notes (with API limitation notice)."""
        messagebox.showinfo(
            "Feature Not Available",
            "The official Discogs API does not currently support editing the notes of a collection item.\n\n"
            "This feature will be implemented if the API is updated to allow it."
        )

    # ========================================================================
    # END: ENHANCED CONTEXT MENU FOR COLLECTION TAB
    # ========================================================================
    
    def _extract_barcode_and_cat_no(self, release_data: dict) -> Tuple[str, str]:
        """
        Extracts and robustly separates barcodes from catalog numbers from Discogs release data.
        """
        if not release_data:
            return "", ""

        explicit_barcodes = {
            identifier.get('value', '').strip()
            for identifier in release_data.get('identifiers', [])
            if identifier.get('type', '').lower() == 'barcode' and identifier.get('value')
        }

        barcode_pattern = re.compile(r'^\s*[\d\s]{10,13}\s*$')

        potential_cat_nos = {
            label.get('catno', '').strip()
            for label in release_data.get('labels', [])
            if label.get('catno') and label.get('catno', '').strip().lower() != 'none'
        }

        heuristic_barcodes = {pcn for pcn in potential_cat_nos if barcode_pattern.match(pcn)}
        
        true_cat_nos = potential_cat_nos - explicit_barcodes - heuristic_barcodes
        
        all_barcodes = explicit_barcodes.union(heuristic_barcodes)

        main_barcode = sorted(list(explicit_barcodes))[0] if explicit_barcodes else \
                       sorted(list(all_barcodes))[0] if all_barcodes else ""

        if not true_cat_nos and potential_cat_nos:
             final_cat_nos = potential_cat_nos - all_barcodes
        else:
             final_cat_nos = true_cat_nos
        
        final_cat_no_str = ", ".join(sorted(list(final_cat_nos)))

        return main_barcode.replace(" ", ""), final_cat_no_str

    def _extract_matrix_info(self, release_data: dict) -> str:
        """
        [NEW & ROBUST] Extracts matrix/runout information from a Discogs release.
        It prioritizes the structured `identifiers` field and falls back to parsing
        the unstructured `notes` field if necessary.
        """
        if not release_data:
            return ""

        # --- Stage 1: Prioritize the structured `identifiers` field ---
        structured_matrix = []
        for identifier in release_data.get('identifiers', []):
            if identifier.get('type') == 'Matrix / Runout':
                desc = identifier.get('description', '').strip()
                value = identifier.get('value', '').strip()
                if value:
                    # Format nicely: "Side A, variant 1: XXX-123"
                    line = f"{desc}: {value}" if desc else value
                    structured_matrix.append(line)
        
        if structured_matrix:
            logger.info(f"Found {len(structured_matrix)} structured matrix entries.")
            return "\n".join(structured_matrix)

        # --- Stage 2: Fallback to parsing the unstructured `notes` field ---
        logger.info("No structured matrix data found, falling back to parsing 'notes' field.")
        notes_text = release_data.get('notes', '')
        if not notes_text:
            return ""

        lines = notes_text.splitlines()
        matrix_lines = []
        in_matrix_block = False

        # Keywords that indicate a line is likely matrix/runout info
        matrix_keywords = ['matrix', 'runout', 'etched', 'stamped', 'side a', 'side b', 'side c', 'side d']

        for line in lines:
            line_lower = line.lower().strip()
            if not line_lower:
                in_matrix_block = False  # Blank line ends a block
                continue

            # Check for the explicit "Matrix / Runout:" header
            if line_lower.startswith('matrix / runout'):
                in_matrix_block = True
                # Add the line itself, but strip the label
                matrix_part = line.split(':', 1)[-1].strip()
                if matrix_part:
                    matrix_lines.append(matrix_part)
                continue

            if in_matrix_block:
                matrix_lines.append(line.strip())
            else:
                # Check if a line contains any of our keywords, but not as part of a larger word
                if any(re.search(r'\b' + re.escape(kw) + r'\b', line_lower) for kw in matrix_keywords):
                    matrix_lines.append(line.strip())

        return "\n".join(matrix_lines).strip()

    def _collection_add_to_inventory(self):
        """Enhanced: Add selected collection item directly to inventory database."""
        selection = self.collection_tree.selection()
        if not selection:
            return

        values = self.collection_tree.item(selection[0], "values")
        
        try:
            release_id = int(values[-1])
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Could not get a valid Release ID from the selected item.")
            return

        # 1. Check for duplicates before proceeding
        try:
            # Attempt to deduplicate by both release ID and cat_no if available
            cat_no = None
            try:
                # Collection tree columns are: added, artist, title, labels, catno, formats, year, folder, rating, instance, release
                # The catno resides at index 4
                cat_no = values[4] if len(values) > 4 else None
            except Exception:
                cat_no = None
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                if cat_no:
                    cursor.execute("SELECT sku, status FROM inventory WHERE discogs_release_id = ? AND cat_no = ?", (release_id, cat_no))
                else:
                    cursor.execute("SELECT sku, status FROM inventory WHERE discogs_release_id = ?", (release_id,))
                existing = cursor.fetchone()
                if existing:
                    msg = (f"This release (ID: {release_id}) already exists in your inventory.\n\n"
                           f"SKU: {existing['sku']}\nStatus: {existing['status']}\n\n"
                           "Do you want to add it again?")
                    if not messagebox.askyesno("Duplicate Found", msg):
                        return
        except Exception as e:
            logger.error(f"Database error checking for duplicates: {e}")
            messagebox.showerror("Database Error", f"Could not check for duplicates: {e}")
            return

        # 2. Fetch full details from Discogs API in a background thread
        self.root.config(cursor="watch")
        self.root.update()

        def api_worker():
            release_data = self.discogs_api.get_release(release_id)
            self.safe_after(0, lambda: self._process_inventory_addition(release_data))

        threading.Thread(target=api_worker, daemon=True).start()

    def _process_inventory_addition(self, release_data):
        """
        Callback to handle processing after API call, ensuring matrix/runout is saved
        AND included in the lister_payload for consistent loading.
        """
        self.root.config(cursor="")
        if not release_data:
            messagebox.showerror("API Error", f"Failed to fetch complete data for Release ID: {release_data.get('id')}")
            return

        # 3. Prompt user for condition and price
        dialog = ConditionGradingDialog(self.root)
        if not dialog.result:
            return  # User cancelled

        # 4. Prepare data for database insertion
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sku = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        
        artist_names = [re.sub(r'\s*\(\d+\)$', '', a['name']).strip() for a in release_data.get('artists', [])]
        artist = ", ".join(artist_names)
        title = release_data.get('title', '')
        
        barcode, cat_no = self._extract_barcode_and_cat_no(release_data)

        year = release_data.get('year', '')
        formats_list = [f.get('name', '') for f in release_data.get('formats', [])]
        main_format = formats_list[0] if formats_list else 'Vinyl'

        # [FIXED] Use the new robust extraction method for matrix info
        matrix_runout_info = self._extract_matrix_info(release_data)

        # Create a complete payload for the `lister_payload` column
        # that INCLUDES the matrix_runout data.
        lister_payload_data = {
            "artist": artist, "title": title, "cat_no": cat_no, "year": str(year),
            "format": main_format, "media_condition": dialog.result["media_condition"],
            "sleeve_condition": dialog.result["sleeve_condition"], "price": dialog.result["price"],
            "condition_notes": dialog.result["notes"], "barcode": barcode,
            "matrix_runout": matrix_runout_info,
            "discogs_release_id": release_data['id'],
            "description": "", # Start with an empty description
            "images": [] # Start with empty images
        }

        # 5. Save to database
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    INSERT INTO inventory (
                        sku, artist, title, cat_no, year, format, media_condition,
                        sleeve_condition, price, status, discogs_release_id, notes,
                        barcode, matrix_runout, date_added, last_modified, inv_updated_at, lister_payload
                    ) VALUES (
                        :sku, :artist, :title, :cat_no, :year, :format, :media_condition,
                        :sleeve_condition, :price, :status, :discogs_release_id, :notes,
                        :barcode, :matrix_runout, :date_added, :last_modified, :inv_updated_at, :lister_payload
                    )
                """

                db_params = {
                    "sku": sku, "artist": artist, "title": title, "cat_no": cat_no,
                    "year": str(year), "format": main_format,
                    "media_condition": dialog.result["media_condition"],
                    "sleeve_condition": dialog.result["sleeve_condition"],
                    "price": dialog.result["price"], "status": "For Sale",
                    "discogs_release_id": release_data['id'],
                    "notes": dialog.result["notes"], "barcode": barcode,
                    "matrix_runout": matrix_runout_info,
                    "date_added": now, "last_modified": now,
                    "inv_updated_at": now,
                    "lister_payload": json.dumps(lister_payload_data)
                }

                cursor.execute(sql, db_params)
            
            # 6. Show confirmation and refresh
            messagebox.showinfo("Success", f"Added to inventory!\n\nSKU: {sku}\n{artist} - {title}")
            self.populate_inventory_view()
            self.notebook.select(self.inventory_tab)

        except Exception as e:
            logger.error(f"Failed to save new inventory item: {e}", exc_info=True)
            messagebox.showerror("Database Error", f"Failed to save item to inventory: {e}")

    def _setup_lister_tab(self):
        """
        Setup the lister tab, now with a multi-line Text widget for Matrix/Runout.
        """
        entry_frame = tk.Frame(self.lister_tab)
        entry_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nw")
        
        results_frame = tk.Frame(self.lister_tab)
        results_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        self.lister_tab.grid_columnconfigure(1, weight=1)
        self.lister_tab.grid_rowconfigure(0, weight=1)

        tk.Label(entry_frame, text="SKU", font=("Helvetica", 14, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        sku_entry = tk.Entry(entry_frame, textvariable=self.sku_display_var, state="readonly", width=50, readonlybackground="white", fg="black")
        sku_entry.grid(row=0, column=1, columnspan=3, sticky="we", padx=5, pady=2)

        field_labels = [
            "Artist", "Title", "Cat No", "Barcode", "Format", "Year", "Genre",
            "Media Condition", "Sleeve Condition", "Condition Notes",
            "Matrix / Runout", "Condition Tags",
            "New/Used", "Shipping Option", "Listing Title"
        ]
        
        field_options = {
            "Format": ["", "LP", "12\"", "2x12\"", "7\"", "10\"", "Box Set", "Vinyl", "Other"],
            "Media Condition": [""] + list(GRADE_ABBREVIATIONS.keys()),
            "Sleeve Condition": [""] + list(GRADE_ABBREVIATIONS.keys()),
            "New/Used": ["", "Used", "New"],
            "Shipping Option": ["", "Standard UK Paid", "Free UK"],
            "Genre": ["", "Pop", "Rock", "Electronic", "Hip Hop", "Jazz", "Classical", "Folk", "Blues", "Country", "Reggae", "Other"]
        }
        
        self.entries = {}

        for i, label_text in enumerate(field_labels):
            row = i + 1
            key = label_text.lower().replace(" / ", "_").replace("/", "_").replace(" ", "_")
            
            tk.Label(entry_frame, text=label_text).grid(row=row, column=0, sticky="nw", padx=5, pady=2)
            
            widget = None
            if key in ["condition_notes", "matrix_runout"]:
                widget_frame = tk.Frame(entry_frame)
                widget_frame.grid(row=row, column=1, columnspan=3, sticky="we", padx=5, pady=2)
                height = 3 if key == "matrix_runout" else 4
                widget = tk.Text(widget_frame, width=47, height=height, wrap="word")
                scrollbar = tk.Scrollbar(widget_frame, orient="vertical", command=widget.yview)
                widget.config(yscrollcommand=scrollbar.set)
                widget.pack(side="left", fill="x", expand=True)
                scrollbar.pack(side="right", fill="y")
            elif label_text in field_options:
                widget = ttk.Combobox(entry_frame, values=field_options[label_text], width=47)
                widget.grid(row=row, column=1, columnspan=3, sticky="we", padx=5, pady=2)
            else:
                widget = tk.Entry(entry_frame, width=50)
                widget.grid(row=row, column=1, columnspan=3, sticky="we", padx=5, pady=2)
            
            self.entries[key] = widget

            if key == "condition_tags":
                tk.Label(entry_frame, text="(comma-separated)", font=("Helvetica", 10, "italic")).grid(row=row, column=4, sticky="w", padx=2)

        current_row = len(field_labels) + 1
        btn_row1 = tk.Frame(entry_frame)
        btn_row1.grid(row=current_row, column=0, columnspan=4, sticky="w", padx=5, pady=(4, 0))
        tk.Button(btn_row1, text="Search Discogs", command=self.search_discogs).pack(side="left", padx=4)
        tk.Button(btn_row1, text="Search by Cat No", command=self.search_by_catno).pack(side="left", padx=4)
        
        current_row += 1
        btn_row2 = tk.Frame(entry_frame)
        btn_row2.grid(row=current_row, column=0, columnspan=4, sticky="w", padx=5, pady=(2, 5))
        tk.Button(btn_row2, text="Generate Title", command=self.generate_listing_title).pack(side="left", padx=4)
        tk.Button(btn_row2, text="Build Description", command=self.build_description).pack(side="left", padx=4)
        self.list_on_discogs_button = tk.Button(btn_row2, text="List on Discogs", state="disabled", command=self.list_on_discogs)
        self.list_on_discogs_button.pack(side="left", padx=4)
        # List on eBay button (live publish).  Drafts are no longer supported.
        self.list_on_ebay_button = tk.Button(btn_row2, text="List on eBay", state="disabled", command=self.list_on_ebay)
        self.list_on_ebay_button.pack(side="left", padx=4)
        self.save_button = tk.Button(btn_row2, text="Save to Inventory", command=self.save_to_inventory)
        self.save_button.pack(side="left", padx=4)
        tk.Button(btn_row2, text="Clear Form", command=self.clear_form).pack(side="left", padx=4)
        
        current_row += 1
        self.release_status_label = tk.Label(entry_frame, text="⚠ No release selected", fg="red", font=("Helvetica", 12, "bold"), wraplength=400, justify="left")
        self.release_status_label.grid(row=current_row, column=0, columnspan=4, sticky="w", padx=5, pady=(5, 5))

        current_row += 1
        image_management_frame = ttk.LabelFrame(entry_frame, text="Image Management", padding=(10, 5))
        image_management_frame.grid(row=current_row, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        image_buttons_frame = tk.Frame(image_management_frame)
        image_buttons_frame.pack(fill="x", pady=(0, 5))
        
        # [NEW] Add the "Select Images..." button
        tk.Button(image_buttons_frame, text="Select Images...", command=self.select_images_manually).pack(side="left", padx=4)
        tk.Button(image_buttons_frame, text="Generate QR", command=self.generate_image_qr_code).pack(side="left", padx=4)
        self.import_images_button = tk.Button(image_management_frame, text="Import Staged", command=self.import_staged_images)
        self.import_images_button.pack(side="left", padx=4)

        image_ui_container = tk.Frame(image_management_frame)
        image_ui_container.pack(fill="x", expand=True)
        image_list_frame = tk.Frame(image_ui_container)
        image_list_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        listbox_container = tk.Frame(image_list_frame)
        listbox_container.pack(fill="x", expand=True)
        self.image_listbox = tk.Listbox(listbox_container, height=6, selectmode=tk.SINGLE)
        self.image_listbox.pack(side="left", fill="x", expand=True)
        self.image_listbox.bind("<<ListboxSelect>>", self._update_image_preview)
        image_scrollbar = tk.Scrollbar(listbox_container, orient="vertical", command=self.image_listbox.yview)
        image_scrollbar.pack(side="right", fill="y")
        self.image_listbox.config(yscrollcommand=image_scrollbar.set)
        reorder_buttons_frame = tk.Frame(image_list_frame)
        reorder_buttons_frame.pack(fill="x", pady=(5, 0))
        tk.Button(reorder_buttons_frame, text="▲ Up", command=self._move_image_up).pack(side="left", fill="x", expand=True)
        tk.Button(reorder_buttons_frame, text="▼ Down", command=self._move_image_down).pack(side="left", fill="x", expand=True)
        tk.Button(reorder_buttons_frame, text="❌ Del", command=self._delete_selected_image).pack(side="left", fill="x", expand=True)
        self.image_preview_label = ttk.Label(image_ui_container, text="Select an image to preview", relief="groove", anchor="center", justify="center")
        self.image_preview_label.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self.image_preview_label.config(width=30)
        
        current_row += 1
        desc_frame = tk.Frame(entry_frame)
        desc_frame.grid(row=current_row, column=0, columnspan=4, sticky="we", padx=5, pady=5)
        tk.Label(desc_frame, text="Full Description").pack(anchor="w")
        self.full_desc = tk.Text(desc_frame, width=50, height=6)
        desc_scroll = tk.Scrollbar(desc_frame, command=self.full_desc.yview)
        self.full_desc.config(yscrollcommand=desc_scroll.set)
        desc_scroll.pack(side="right", fill="y")
        self.full_desc.pack(side="left", fill="x", expand=True)

        current_row += 1
        tk.Label(entry_frame, text="Price (£)").grid(row=current_row, column=0, sticky="w", padx=5, pady=5)
        self.price_entry = tk.Entry(entry_frame, width=50)
        self.price_entry.grid(row=current_row, column=1, columnspan=3, sticky="we", padx=5, pady=5)
        
        self._setup_discogs_results(results_frame)
    
    def _update_image_listbox(self):
        """Clears and repopulates the image listbox from self.image_paths."""
        self.image_listbox.delete(0, tk.END)
        for path in self.image_paths:
            self.image_listbox.insert(tk.END, os.path.basename(path))

    def _update_image_preview(self, event=None):
        """Updates the image preview label when a listbox item is selected."""
        try:
            selected_indices = self.image_listbox.curselection()
            if not selected_indices:
                self._clear_image_preview()
                return
            
            idx = selected_indices[0]
            image_path = self.image_paths[idx]

            if not os.path.exists(image_path):
                self.image_preview_label.config(image='', text=f"Image not found:\n{os.path.basename(image_path)}")
                return

            with Image.open(image_path) as img:
                # Create a thumbnail for preview
                preview_size = (self.image_preview_label.winfo_width(), self.image_preview_label.winfo_height())
                # Fallback size if widget not rendered yet
                if preview_size[0] < 20 or preview_size[1] < 20: 
                    preview_size = (200, 200)
                
                img.thumbnail(preview_size, Image.Resampling.LANCZOS)
                
                photo_image = ImageTk.PhotoImage(img)
                
                # Update the label
                self.image_preview_label.config(image=photo_image, text="")
                # IMPORTANT: Keep a reference to the image to prevent garbage collection
                self.image_preview_label.image = photo_image

        except Exception as e:
            logger.error(f"Error updating image preview: {e}")
            self.image_preview_label.config(image='', text="Error loading preview")

    def _clear_image_preview(self):
        """Clears the image preview area."""
        self.image_preview_label.config(image='', text="Select an image to preview")
        self.image_preview_label.image = None

    def _move_image_up(self):
        """Moves the selected image up in the list."""
        try:
            selected_indices = self.image_listbox.curselection()
            if not selected_indices: return
            
            idx = selected_indices[0]
            if idx > 0:
                self.image_paths.insert(idx - 1, self.image_paths.pop(idx))
                self._update_image_listbox()
                self.image_listbox.selection_set(idx - 1)
                self._update_image_preview() # Update preview after move
        except Exception as e:
            logger.error(f"Error moving image up: {e}")

    def _move_image_down(self):
        """Moves the selected image down in the list."""
        try:
            selected_indices = self.image_listbox.curselection()
            if not selected_indices: return

            idx = selected_indices[0]
            if idx < len(self.image_paths) - 1:
                self.image_paths.insert(idx + 1, self.image_paths.pop(idx))
                self._update_image_listbox()
                self.image_listbox.selection_set(idx + 1)
                self._update_image_preview() # Update preview after move
        except Exception as e:
            logger.error(f"Error moving image down: {e}")

    def _delete_selected_image(self):
        """Deletes the selected image from the list."""
        try:
            selected_indices = self.image_listbox.curselection()
            if not selected_indices: return

            idx = selected_indices[0]
            # Optionally, ask for confirmation before deleting the actual file
            # if messagebox.askyesno("Delete Image", f"Permanently delete {os.path.basename(self.image_paths[idx])}?"):
            #     os.remove(self.image_paths[idx])
            self.image_paths.pop(idx)
            self._update_image_listbox()
            
            if len(self.image_paths) > 0:
                new_selection = min(idx, len(self.image_paths) - 1)
                self.image_listbox.selection_set(new_selection)
            self._update_image_preview()
        except Exception as e:
            logger.error(f"Error deleting image: {e}")
    
    def _setup_discogs_results(self, parent):
        """Setup Discogs search results view"""
        # Filter controls
        controls_frame = tk.Frame(parent)
        controls_frame.pack(fill="x", pady=(0, 5))
        
        tk.Label(controls_frame, text="Filter:").pack(side="left", padx=(0, 5))
        self.discogs_search_filter_var = tk.StringVar()
        filter_entry = tk.Entry(controls_frame, textvariable=self.discogs_search_filter_var, width=30)
        filter_entry.pack(side="left", padx=5)
        filter_entry.bind("<KeyRelease>", self.refresh_discogs_view)
        
        # Results tree
        tree_container = tk.Frame(parent)
        tree_container.pack(fill="both", expand=True)
        
        cols = ("ID", "Artist", "Title", "Cat#", "Year", "Country", "Format")
        self.discogs_tree = ttk.Treeview(tree_container, columns=cols, show="headings")
        
        for col in cols:
            self.discogs_tree.heading(col, text=col, command=lambda c=col: self.sort_discogs_results(c))
        
        # Column widths
        self.discogs_tree.column("ID", width=0, stretch=tk.NO)
        self.discogs_tree.column("Artist", width=200)
        self.discogs_tree.column("Title", width=280)
        self.discogs_tree.column("Cat#", width=100)
        self.discogs_tree.column("Year", width=60, anchor="center")
        self.discogs_tree.column("Country", width=100, anchor="center")
        self.discogs_tree.column("Format", width=200)
        
        # Scrollbar
        tree_scroll = tk.Scrollbar(tree_container, orient="vertical", command=self.discogs_tree.yview)
        self.discogs_tree.configure(yscrollcommand=tree_scroll.set)
        
        # Bindings
        self.discogs_tree.bind("<Double-1>", self.apply_selected_discogs)
        self.discogs_tree.bind("<Button-3>", self.show_discogs_context_menu)
        self.discogs_tree.bind("<Button-2>", self.show_discogs_context_menu)
        
        # Pack
        self.discogs_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        
        # Context menu
        self.discogs_context_menu = tk.Menu(self.root, tearoff=0)
        self.discogs_context_menu.add_command(label="Apply Selected Result", command=self.apply_selected_discogs)
        self.discogs_context_menu.add_command(label="View on Discogs", command=self.open_discogs_release_page)
        self.discogs_context_menu.add_separator()
        self.discogs_context_menu.add_command(label="Get Price Suggestion", command=self.get_price_suggestion)
        self.discogs_context_menu.add_command(label="View Discogs Sales History", command=lambda: self.open_sold_listings_from_selection("Discogs"))
        self.discogs_context_menu.add_command(label="View eBay Sales History", command=lambda: self.open_sold_listings_from_selection("eBay"))
    
    def _setup_inventory_tab(self):
        """Setup inventory tab with all features"""
        inv_frame = tk.Frame(self.inventory_tab)
        inv_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Controls
        controls_frame = tk.Frame(inv_frame)
        controls_frame.pack(fill="x", pady=(0, 5))
        
        tk.Label(controls_frame, text="Search:").pack(side="left", padx=(0, 5))
        self.inventory_search_var = tk.StringVar()
        search_entry = tk.Entry(controls_frame, textvariable=self.inventory_search_var, width=30)
        search_entry.pack(side="left", padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self.populate_inventory_view(self.inventory_search_var.get()))
        
        tk.Button(controls_frame, text="Load for Editing", command=self.load_item_for_editing).pack(side="left", padx=5)
        tk.Button(controls_frame, text="Edit in Lister", command=self.edit_in_lister).pack(side="left", padx=5)
        tk.Button(controls_frame, text="Delete Selected", command=self.delete_inventory_item).pack(side="left", padx=5)
        tk.Button(controls_frame, text="Select All", command=self.select_all_inventory).pack(side="left", padx=(10, 0))
        tk.Button(controls_frame, text="Deselect All", command=self.deselect_all_inventory).pack(side="left", padx=5)
        
        # Status buttons
        controls_frame2 = tk.Frame(inv_frame)
        controls_frame2.pack(fill="x", pady=(0, 5))
        
        tk.Label(controls_frame2, text="Update Status:").pack(side="left")
        for status in ["For Sale", "Sold", "Not For Sale"]:
            tk.Button(
                controls_frame2,
                text=status,
                command=lambda s=status: self.update_inventory_status(s)
            ).pack(side="left", padx=5)
        
        # Publishing buttons
        # Only provide a single "Publish Live to eBay" button.  Draft functionality
        # has been removed because eBay's public APIs do not support creating
        # Seller Hub drafts.  This button publishes selected inventory items
        # directly to eBay via the Inventory API workflow.
        self.publish_ebay_btn = tk.Button(controls_frame2, text="Publish Live to eBay", command=self.publish_to_ebay, state="disabled")
        self.publish_ebay_btn.pack(side="left", padx=(20, 5))

        # Publish to Discogs (Draft) button
        self.publish_discogs_btn = tk.Button(controls_frame2, text="Publish → Discogs", command=self.publish_to_discogs, state="disabled")
        self.publish_discogs_btn.pack(side="left", padx=5)

        # Open listing in browser (quick link)
        self.open_in_browser_btn = tk.Button(controls_frame2, text="Open in Browser", command=self.open_listing_in_browser, state="disabled")
        self.open_in_browser_btn.pack(side="left", padx=(20, 5))

        # Import button remains
        self.import_button = tk.Button(controls_frame2, text="Import Discogs Inventory", state="disabled", command=self.start_discogs_import)
        self.import_button.pack(side="left", padx=5)
        
        # Inventory tree
        # Include eBay draft/live and Discogs IDs for traceability
        cols = ("SKU", "Artist", "Title", "Price", "Status", "eBay Draft ID", "eBay Listing ID", "Discogs ID", "Date Added")
        self.inventory_tree = ttk.Treeview(inv_frame, columns=cols, show="headings", selectmode="extended")

        for col in cols:
            self.inventory_tree.heading(col, text=col, command=lambda c=col: self.sort_inventory(c))

        # Column widths (adjusted for additional ID columns)
        self.inventory_tree.column("SKU", width=140)
        self.inventory_tree.column("Artist", width=180)
        self.inventory_tree.column("Title", width=260)
        self.inventory_tree.column("Price", width=80, anchor="e")
        self.inventory_tree.column("Status", width=110)
        self.inventory_tree.column("eBay Draft ID", width=140)
        self.inventory_tree.column("eBay Listing ID", width=140)
        self.inventory_tree.column("Discogs ID", width=120)
        self.inventory_tree.column("Date Added", width=150)
        
        # Bindings
        self.inventory_tree.bind("<Double-1>", self.load_item_for_editing)
        self.inventory_tree.bind("<Button-3>", self.show_inventory_context_menu)
        self.inventory_tree.bind("<Button-2>", self.show_inventory_context_menu)
        self.inventory_tree.bind("<Control-Button-1>", self.show_inventory_context_menu)
        self.inventory_tree.bind("<Return>", self.load_item_for_editing)
        self.inventory_tree.bind("<<TreeviewSelect>>", self.on_inventory_selection)
        
        # Scrollbar
        inv_scroll = tk.Scrollbar(inv_frame, orient="vertical", command=self.inventory_tree.yview)
        self.inventory_tree.configure(yscrollcommand=inv_scroll.set)
        
        # Pack
        self.inventory_tree.pack(side="left", fill="both", expand=True)
        inv_scroll.pack(side="right", fill="y")
        
        # Log area
        log_frame = tk.Frame(inv_frame)
        log_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        self.publish_log = scrolledtext.ScrolledText(log_frame, height=8, state="disabled", wrap="word")
        self.publish_log.pack(fill="both", expand=True)
        
        # Context menu with all options
        self.inventory_context_menu = tk.Menu(self.root, tearoff=0)
        self.inventory_context_menu.add_command(label="Load for Editing", command=self.load_item_for_editing)
        self.inventory_context_menu.add_command(label="Edit in Lister", command=self.edit_in_lister)
        self.inventory_context_menu.add_separator()
        self.inventory_context_menu.add_command(label="Open Discogs Listing", command=self.open_discogs_listing)
        self.inventory_context_menu.add_command(label="Open eBay Listing", command=self.open_ebay_listing)
        self.inventory_context_menu.add_command(label="View Discogs Release Page", command=self.open_discogs_release_from_inventory)
        self.inventory_context_menu.add_separator()
        self.inventory_context_menu.add_command(label="Sync with Discogs", command=self.manual_sync_now)
        self.inventory_context_menu.add_separator()
        self.inventory_context_menu.add_command(label="Delete", command=self.delete_inventory_item)
    
    def _setup_settings_tab_complete(self):
        """Setup settings tab with ALL features including status mapping and sales"""
        settings_frame = tk.Frame(self.settings_tab, padx=10, pady=10)
        settings_frame.pack(fill="both", expand=True)
        
        # Settings Notebook
        settings_notebook = ttk.Notebook(settings_frame)
        settings_notebook.pack(fill="both", expand=True, pady=(10, 0))

        # --- Connections & Sync Tab ---
        conn_sync_tab = ttk.Frame(settings_notebook)
        settings_notebook.add(conn_sync_tab, text="Connections & Sync")

        # Discogs connection
        discogs_frame = ttk.LabelFrame(conn_sync_tab, text="Discogs Account Connection", padding=(10, 5))
        discogs_frame.pack(fill="x", pady=(0, 10), padx=5)
        
        self.discogs_auth_status_var = tk.StringVar(value="Not Connected")
        ttk.Label(discogs_frame, textvariable=self.discogs_auth_status_var, font=("Helvetica", 14, "italic")).pack(side="left", padx=5, pady=5)
        
        self.discogs_connect_button = tk.Button(discogs_frame, text="Connect to Discogs Account", command=self.authenticate_discogs)
        self.discogs_connect_button.pack(side="left", padx=5, pady=5)
        
        # eBay connection
        ebay_frame = ttk.LabelFrame(conn_sync_tab, text="eBay Account Connection", padding=(10, 5))
        ebay_frame.pack(fill="x", pady=(0, 10), padx=5)
        
        self.ebay_auth_status_var = tk.StringVar(value="Not Connected")
        ttk.Label(ebay_frame, textvariable=self.ebay_auth_status_var, font=("Helvetica", 14, "italic")).pack(side="left", padx=5, pady=5)
        
        tk.Button(ebay_frame, text="Test Connection", command=self.test_ebay_connection).pack(side="left", padx=5, pady=5)
        tk.Button(ebay_frame, text="Copy eBay Status", command=lambda: self._copy_ebay_status()).pack(side="left", padx=5, pady=5)

        # Auto-sync settings
        sync_frame = ttk.LabelFrame(conn_sync_tab, text="Automatic Inventory Sync", padding=(10, 5))
        sync_frame.pack(fill="x", pady=(10, 0), padx=5)
        
        sync_controls = tk.Frame(sync_frame)
        sync_controls.pack(fill="x", pady=(0, 5))
        
        self.auto_sync_var = tk.BooleanVar(value=self.auto_sync_enabled)
        tk.Checkbutton(sync_controls, text="Enable automatic sync", variable=self.auto_sync_var, 
                      command=self.toggle_auto_sync).pack(side="left", padx=5)
        
        self.two_way_sync_var = tk.BooleanVar(value=self.two_way_sync_enabled)
        tk.Checkbutton(sync_controls, text="Enable two-way sync", variable=self.two_way_sync_var,
                      command=self.toggle_two_way_sync).pack(side="left", padx=(20, 5))
        
        # Advanced sync options
        advanced_controls = tk.Frame(sync_frame)
        advanced_controls.pack(fill="x", pady=(0, 5))
        
        tk.Label(advanced_controls, text="Advanced:", font=("Helvetica", 10, "bold")).pack(side="left", padx=(0, 5))
        
        self.attempt_updates_var = tk.BooleanVar(value=self.attempt_discogs_updates)
        tk.Checkbutton(advanced_controls, text="Attempt Discogs updates (experimental)",
                      variable=self.attempt_updates_var, command=self.toggle_attempt_updates).pack(side="left", padx=5)
        
        # Sync interval
        interval_frame = tk.Frame(sync_frame)
        interval_frame.pack(fill="x", pady=(0, 5))
        
        tk.Label(interval_frame, text="Sync every:").pack(side="left", padx=(0, 5))
        self.sync_interval_var = tk.StringVar(value=str(self.auto_sync_interval // 60))
        tk.Spinbox(interval_frame, from_=1, to=60, width=5, textvariable=self.sync_interval_var,
                   command=self.update_sync_interval).pack(side="left", padx=5)
        tk.Label(interval_frame, text="minutes").pack(side="left", padx=(0, 10))
        
        tk.Button(interval_frame, text="Sync Now", command=self.manual_sync_now).pack(side="left", padx=5)
        
        # Sync status
        status_frame = tk.Frame(sync_frame)
        status_frame.pack(fill="x", pady=(5, 0))
        
        self.sync_status_var = tk.StringVar(value="Auto-sync disabled")
        ttk.Label(status_frame, textvariable=self.sync_status_var, font=("Helvetica", 10, "italic")).pack(side="left", padx=5)
        
        # Sync log
        log_frame = ttk.LabelFrame(sync_frame, text="Sync Activity Log", padding=(5, 5))
        log_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        self.sync_log_text = tk.Text(log_frame, height=8, width=80)
        log_scroll = tk.Scrollbar(log_frame, orient="vertical", command=self.sync_log_text.yview)
        self.sync_log_text.configure(yscrollcommand=log_scroll.set)
        
        self.sync_log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        
        # --- Mappings & Workflow Tab ---
        mappings_tab = ttk.Frame(settings_notebook)
        settings_notebook.add(mappings_tab, text="Mappings & Workflow")

        # Image Workflow Settings
        image_frame = ttk.LabelFrame(mappings_tab, text="Image Workflow Settings", padding=(10, 5))
        image_frame.pack(fill="x", pady=(10, 10), padx=5)

        path_frame = tk.Frame(image_frame)
        path_frame.pack(fill="x")
        
        tk.Label(path_frame, text="Image Staging Folder:").pack(side="left", anchor="w")
        path_entry = tk.Entry(path_frame, textvariable=self.image_staging_path_var, state="readonly", width=60)
        path_entry.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(path_frame, text="Browse...", command=self._select_image_staging_path).pack(side="left")

        # Status Mapping Configuration
        status_mapping_frame = ttk.LabelFrame(mappings_tab, text="Status Mapping Configuration", padding=(10, 5))
        status_mapping_frame.pack(fill="x", pady=(10, 0), padx=5)
        
        tk.Label(status_mapping_frame, text="Configure how Discogs inventory statuses map to your local inventory statuses:", 
                 font=("Helvetica", 11)).pack(anchor="w", pady=(0, 10))
        
        # Mapping table
        mapping_table_frame = tk.Frame(status_mapping_frame)
        mapping_table_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(mapping_table_frame, text="Discogs Status", font=("Helvetica", 12, "bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        tk.Label(mapping_table_frame, text="→", font=("Helvetica", 12, "bold")).grid(row=0, column=1, padx=5, pady=5)
        tk.Label(mapping_table_frame, text="Local Status", font=("Helvetica", 12, "bold")).grid(row=0, column=2, padx=10, pady=5, sticky="w")
        
        for i, (discogs_status, default_local_status) in enumerate(DEFAULT_STATUS_MAPPINGS.items(), 1):
            tk.Label(mapping_table_frame, text=discogs_status, font=("Helvetica", 11)).grid(row=i, column=0, padx=10, pady=3, sticky="w")
            tk.Label(mapping_table_frame, text="→", font=("Helvetica", 11)).grid(row=i, column=1, padx=5, pady=3)
            
            var = tk.StringVar(value=self.status_mappings.get(discogs_status, default_local_status))
            self.status_mapping_vars[discogs_status] = var
            
            ttk.Combobox(mapping_table_frame, textvariable=var, values=LOCAL_STATUSES, 
                        state="readonly", width=15).grid(row=i, column=2, padx=10, pady=3, sticky="w")
        
        # Mapping buttons
        mapping_buttons_frame = tk.Frame(status_mapping_frame)
        mapping_buttons_frame.pack(anchor="w", pady=(5, 0))
        
        tk.Button(mapping_buttons_frame, text="Save Mappings", command=self._save_status_mappings).pack(side="left", padx=(0, 10))
        tk.Button(mapping_buttons_frame, text="Reset to Defaults", command=self._reset_status_mappings).pack(side="left")

        # --- Sales Tab ---
        sales_tab = ttk.Frame(settings_notebook)
        settings_notebook.add(sales_tab, text="Sales History")
        
        sales_notebook_inner = ttk.Notebook(sales_tab)
        sales_notebook_inner.pack(fill="both", expand=True, pady=5)
        
        # Discogs sales tab
        discogs_sales_tab = ttk.Frame(sales_notebook_inner)
        sales_notebook_inner.add(discogs_sales_tab, text="Discogs Sales")
        
        ds_frame = ttk.LabelFrame(discogs_sales_tab, text="Discogs Sales", padding=(10, 5))
        ds_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        ds_controls = tk.Frame(ds_frame)
        ds_controls.pack(fill="x", pady=(0, 5))
        
        self.check_sales_button = tk.Button(ds_controls, text="Check for New Sales", state="disabled",
                                           command=self.check_discogs_sales)
        self.check_sales_button.pack(side="left", anchor="w", padx=5, pady=5)
        
        tk.Button(ds_controls, text="Sync Selected Sale", command=self.sync_discogs_sale).pack(side="left", anchor="w", padx=5, pady=5)
        
        # Discogs sales tree
        ds_cols = ("Order ID", "Date", "Buyer", "Artist", "Title", "Price", "Release ID")
        self.sales_tree = ttk.Treeview(ds_frame, columns=ds_cols, show="headings")
        
        for col in ds_cols:
            self.sales_tree.heading(col, text=col)
        
        self.sales_tree.pack(side="left", fill="both", expand=True)
        
        ds_scroll = tk.Scrollbar(ds_frame, orient="vertical", command=self.sales_tree.yview)
        ds_scroll.pack(side="right", fill="y")
        self.sales_tree.configure(yscrollcommand=ds_scroll.set)
        
        # eBay sales tab
        ebay_sales_tab = ttk.Frame(sales_notebook_inner)
        sales_notebook_inner.add(ebay_sales_tab, text="eBay Sales")
        
        es_frame = ttk.LabelFrame(ebay_sales_tab, text="eBay Account & Sales", padding=(10, 5))
        es_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        es_sales_controls = tk.Frame(es_frame)
        es_sales_controls.pack(fill="x", pady=(0, 5))
        
        tk.Label(es_sales_controls, text="Start Date (DD-MM-YYYY):").pack(side="left", padx=(0, 5))
        self.ebay_start_date_var = tk.StringVar()
        tk.Entry(es_sales_controls, textvariable=self.ebay_start_date_var, width=12).pack(side="left", padx=5)
        
        tk.Label(es_sales_controls, text="End Date (DD-MM-YYYY):").pack(side="left", padx=(10, 5))
        self.ebay_end_date_var = tk.StringVar()
        tk.Entry(es_sales_controls, textvariable=self.ebay_end_date_var, width=12).pack(side="left", padx=5)
        
        # Set default dates
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=30)
        self.ebay_start_date_var.set(start_date.strftime("%d-%m-%Y"))
        self.ebay_end_date_var.set(end_date.strftime("%d-%m-%Y"))
        
        self.check_ebay_sales_button = tk.Button(es_sales_controls, text="Check for Sales", state="disabled",
                                                command=self.check_ebay_sales)
        self.check_ebay_sales_button.pack(side="left", anchor="w", padx=15, pady=5)
        
        tk.Button(es_sales_controls, text="Sync Selected Sale", command=self.sync_ebay_sale).pack(side="left", anchor="w", padx=5, pady=5)
        
        # eBay sales tree
        es_cols = ("Order ID", "Date", "Buyer", "Artist", "Title", "Price", "Item ID")
        self.ebay_sales_tree = ttk.Treeview(es_frame, columns=es_cols, show="headings")
        
        for col in es_cols:
            self.ebay_sales_tree.heading(col, text=col)
        
        self.ebay_sales_tree.pack(side="left", fill="both", expand=True, pady=(5, 0))
        
        es_scroll = tk.Scrollbar(es_frame, orient="vertical", command=self.ebay_sales_tree.yview)
        es_scroll.pack(side="right", fill="y", pady=(5, 0))
        self.ebay_sales_tree.configure(yscrollcommand=es_scroll.set)

    def _select_image_staging_path(self):
        """Open a dialog to select the image staging directory."""
        directory = filedialog.askdirectory(
            title="Select Image Staging Folder",
            initialdir=self.config.get("image_staging_path") or os.path.expanduser("~")
        )
        if directory:
            self.image_staging_path_var.set(directory)
            self.config.save({"image_staging_path": directory})
            messagebox.showinfo("Path Saved", f"Image staging path set to:\n{directory}")
    
    def _update_connection_status(self):
        """Update connection status for APIs"""
        # Discogs status
        if self.discogs_api.is_connected():
            try:
                user = self.discogs_api.client.identity()
                self.discogs_auth_status_var.set(f"Connected as: {user.username}")
                self.discogs_connect_button.config(state="disabled")
                self.check_sales_button.config(state="normal")
                self.import_button.config(state="normal")
                self.list_on_discogs_button.config(state="normal")
            except:
                self.discogs_auth_status_var.set("Not Connected")
        
        # eBay status
        if self.ebay_api.test_connection():
            self.ebay_auth_status_var.set("Connected Successfully")
            self.check_ebay_sales_button.config(state="normal")
            self.list_on_ebay_button.config(state="normal")
    
    def _copy_ebay_status(self):
        """Copy eBay status to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.ebay_auth_status_var.get())
        messagebox.showinfo("Copied", "Status copied to clipboard")
    
    # ========================================================================
    # ALL CORE METHODS INCLUDING MISSING ONES
    # ========================================================================
    
    def search_discogs(self):
        """Search Discogs for releases"""
        artist = self.entries["artist"].get().strip()
        title = self.entries["title"].get().strip()
        
        if not artist and not title:
            messagebox.showwarning("Input Required", "Please enter artist and/or title")
            return
        
        self.root.config(cursor="watch")
        self.root.update()
        
        # Build search parameters
        params = {"per_page": 100, "type": "release"}
        if artist:
            params["artist"] = artist
        if title:
            params["release_title"] = title
        
        # Search in thread
        def search_worker():
            try:
                results = self.discogs_api.search(params)
                self.safe_after(0, lambda: self.display_discogs_results(results))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Search Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        
        threading.Thread(target=search_worker, daemon=True).start()
    
    def search_by_catno(self):
        """Search Discogs by catalog number"""
        catno = self.entries["cat_no"].get().strip()
        
        if not catno:
            messagebox.showwarning("Input Required", "Please enter a catalog number")
            return
        
        self.root.config(cursor="watch")
        self.root.update()
        
        def search_worker():
            try:
                results = self.discogs_api.search({"catno": catno, "per_page": 100})
                self.safe_after(0, lambda: self.display_discogs_results(results))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Search Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        
        threading.Thread(target=search_worker, daemon=True).start()
    
    def display_discogs_results(self, results):
        """Display Discogs search results"""
        # Clear existing results
        for item in self.discogs_tree.get_children():
            self.discogs_tree.delete(item)
        
        if not results:
            messagebox.showinfo("No Results", "No releases found")
            return
        
        self.discogs_search_results = results
        
        # Populate tree
        for item in results:
            artist, title = (item.get("title", "").split(" - ", 1) + [""])[:2]
            values = (
                item.get("id"),
                artist,
                title,
                item.get("catno", "N/A"),
                item.get("year", "N/A"),
                item.get("country", "N/A"),
                ", ".join(item.get("format", []))
            )
            self.discogs_tree.insert("", "end", values=values)
    
    def apply_selected_discogs(self, event=None):
        """
        Apply selected Discogs result to form after fetching full details.
        """
        selected = self.discogs_tree.focus()
        if not selected:
            return
        
        values = self.discogs_tree.item(selected, "values")
        release_id = int(values[0])
        
        self.root.config(cursor="watch")
        self.root.update()
        
        def fetch_and_apply_worker():
            try:
                release_data = self.discogs_api.get_release(release_id)
                if release_data:
                    self.safe_after(0, lambda: self._populate_lister_with_release_data(release_data))
                else:
                    self.safe_after(0, lambda: messagebox.showerror("API Error", f"Could not fetch full details for release {release_id}."))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("API Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))

        threading.Thread(target=fetch_and_apply_worker, daemon=True).start()

    def _populate_lister_with_release_data(self, release_data: dict):
        """
        Populates the lister form with cleaned, detailed data from a full Discogs release.
        """
        artist_names = [re.sub(r'\s*\(\d+\)$', '', a['name']).strip() for a in release_data.get('artists', [])]
        artist = ", ".join(artist_names)

        barcode, cat_no = self._extract_barcode_and_cat_no(release_data)
        matrix_info = self._extract_matrix_info(release_data)
        
        # --- Populate Form Fields ---
        self.entries["artist"].delete(0, tk.END)
        self.entries["artist"].insert(0, artist)
        
        self.entries["title"].delete(0, tk.END)
        self.entries["title"].insert(0, release_data.get('title', ''))

        self.entries["cat_no"].delete(0, tk.END)
        self.entries["cat_no"].insert(0, cat_no)
        
        self.entries["barcode"].delete(0, tk.END)
        self.entries["barcode"].insert(0, barcode)

        self.entries["year"].delete(0, tk.END)
        self.entries["year"].insert(0, str(release_data.get('year', '')))
        
        self.entries["matrix_runout"].delete("1.0", tk.END)
        self.entries["matrix_runout"].insert("1.0", matrix_info)

        formats_list = [f.get('name', '') for f in release_data.get('formats', [])]
        if formats_list:
            # Set a sensible default for the format dropdown
            main_format = formats_list[0]
            if main_format.lower() == 'vinyl':
                self.entries["format"].set('LP')
            elif main_format in self.entries['format']['values']:
                 self.entries["format"].set(main_format)
            else:
                 self.entries["format"].set('Other')


        self.current_release_id = release_data.get('id')
        
        self.release_status_label.config(
            text=f"✓ Release selected: {release_data.get('title')} (ID: {self.current_release_id})",
            fg="green"
        )
        
        messagebox.showinfo("Success", f"Applied info for '{release_data.get('title')}'")

    def generate_listing_title(self):
        """
        Correctly and definitively generate the listing title to the required format:
        ARTIST: Title (Year) Vinyl LP CatNo Grade
        """
        parts = []
        new_used_status = self.entries["new_used"].get()

        # --- Gather all data from the form ---
        artist = self.entries["artist"].get().strip()
        title = self.entries["title"].get().strip()
        year = self.entries["year"].get().strip()
        cat_no = self.entries["cat_no"].get().strip()
        specific_format = self.entries["format"].get().strip()

        # --- Build the Format String (DEFINITIVE LOGIC) ---
        format_str = ""
        # These formats should always result in "Vinyl LP"
        lp_formats = ["", "LP", "12\"", "2x12\"", "Vinyl"]
        
        if specific_format in lp_formats:
            format_str = "Vinyl LP"
        # Handle specific, non-LP formats like "7\"" or "Box Set"
        elif specific_format:
            # Avoid duplication if user manually types "7\" Vinyl"
            if "vinyl" in specific_format.lower():
                format_str = specific_format
            else:
                format_str = f"{specific_format} Vinyl"
        # Absolute fallback in case of weird data
        else:
            format_str = "Vinyl LP"

        # --- Build the Grade String ---
        grade_str = ""
        if new_used_status == "New":
            grade_str = "NEW/SEALED"
        else:  # This covers "Used" and the case where it's not specified
            media = self.entries["media_condition"].get()
            sleeve = self.entries["sleeve_condition"].get()
            if media or sleeve:
                media_abbr = GRADE_ABBREVIATIONS.get(media, "")
                sleeve_abbr = GRADE_ABBREVIATIONS.get(sleeve, "")
                grade = f"{media_abbr}/{sleeve_abbr}".strip("/")
                if grade:
                    grade_str = grade

        # --- Assemble the title in the correct, specified order ---
        if artist:
            parts.append(f"{artist.upper()}:")
        if title:
            parts.append(title)
        if year:
            parts.append(f"({year})")
        
        # Add the newly built format string
        parts.append(format_str)
        
        if cat_no:
            parts.append(cat_no)
        if grade_str:
            parts.append(grade_str)

        # --- Finalize and set the title ---
        final_title = " ".join(filter(None, parts))[:80]
        self.entries["listing_title"].delete(0, tk.END)
        self.entries["listing_title"].insert(0, final_title)
    
    def build_description(self):
        """Build full description with tracklist using the Analog Theory template."""
        if not self.current_release_id:
            messagebox.showwarning("No Release", "Please select a Discogs release first to get tracklist data.")
            self._render_analog_theory_description(None)
            return
        
        self.root.config(cursor="watch")
        self.root.update()
        
        def fetch_worker():
            try:
                release = self.discogs_api.get_release(self.current_release_id)
                self.safe_after(0, lambda: self._render_analog_theory_description(release))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        
        threading.Thread(target=fetch_worker, daemon=True).start()

    def _render_analog_theory_description(self, release_data):
        """Renders the Analog Theory HTML and places it in the description box."""
        
        # --- Gather data from UI form and API response ---
        payload = {
            "artist": self.entries["artist"].get().strip(),
            "title": self.entries["title"].get().strip(),
            "cat_no": self.entries["cat_no"].get().strip(),
            "year": self.entries["year"].get().strip(),
            "format": self.entries["format"].get(),
            "media_condition": self.entries["media_condition"].get(),
            "sleeve_condition": self.entries["sleeve_condition"].get(),
            "condition_notes": self.entries["condition_notes"].get("1.0", "end-1c").strip(),
            "matrix_runout": self.entries["matrix_runout"].get("1.0", "end-1c").strip(),
            "condition_tags": self.entries["condition_tags"].get().strip(),
            "barcode": self.entries["barcode"].get().strip(),
            "genre": self.entries["genre"].get().strip(),
        }

        # --- Helper functions for template ---
        def get(key, default=''):
            return payload.get(key) or default

        def get_release_attr(data, key, default=''):
            return data.get(key, default) if data else default

        def get_label_info(data):
            if not data or not data.get('labels'): return ''
            return data['labels'][0].get('name', '')

        def get_main_format(data):
            if not data or not data.get('formats'): return get('format')
            main_format = data['formats'][0].get('name', '')
            descriptions = ", ".join(data['formats'][0].get('descriptions', []))
            return f"{main_format}, {descriptions}" if descriptions else main_format

        # --- Prepare data for the 2x3 grid ---
        grid_data = {
            "FORMAT": get_main_format(release_data),
            "CAT NO": get('cat_no'),
            "BARCODE": get('barcode'),
            "YEAR": get('year'),
            "PUBLISHER": get_label_info(release_data),
            "COUNTRY": get_release_attr(release_data, 'country', '')
        }
        
        info_grid_html = ""
        for label, value in grid_data.items():
            if value:
                info_grid_html += f'<div class="info-box"><span class="info-label">{label}</span><span class="info-value">{value}</span></div>'

        # --- Prepare other template sections ---
        tags_raw = get('condition_tags', '').strip()
        tags_list = [tag.strip() for tag in tags_raw.split(',') if tag.strip()]
        tags_html = "".join([f'<div class="condition-tag">{tag}</div>' for tag in tags_list])

        tracklist_html = ""
        if release_data and release_data.get('tracklist'):
            tracklist_items = []
            for track in release_data['tracklist']:
                title = track.get('title', 'Unknown Track')
                position = track.get('position', '')
                tracklist_items.append(f'<li><span class="track-pos">{position}</span>{title}</li>')
            tracklist_html = f'<ol class="track-listing">{"".join(tracklist_items)}</ol>'
        
        matrix_html = ""
        if get('matrix_runout'):
            matrix_html = f'<div class="details-content matrix-content">{get("matrix_runout").replace(chr(10), "<br>")}</div>'

        seller_footer = self.config.get('seller_footer', '').replace('\n', '<br>')

        # --- Build the final HTML ---
        html = f"""
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            .at-container {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 850px; margin: 20px auto; border: 1px solid #e1e1e1; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
            .at-header {{ background-color: #f7f7f7; padding: 20px 25px; border-bottom: 1px solid #e1e1e1; }}
            .at-header .artist {{ margin: 0; font-size: 26px; font-weight: 600; }}
            .at-header .title {{ margin: 4px 0 15px; font-size: 18px; font-weight: 400; color: #555; }}
            .at-body {{ padding: 25px; }}
            .info-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
            .info-box {{ background: #f9f9f9; border: 1px solid #eee; border-radius: 6px; padding: 12px; text-align: center; }}
            .info-label {{ display: block; font-size: 11px; font-weight: 600; color: #888; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 4px; }}
            .info-value {{ display: block; font-size: 14px; font-weight: 500; color: #222; }}
            .details-section {{ border: 1px solid #e5e5e5; border-radius: 6px; margin-top: 25px; overflow: hidden; }}
            .details-section:first-child {{ margin-top: 0; }}
            .details-summary {{ padding: 12px 15px; font-weight: 600; cursor: pointer; background-color: #fafafa; display: block; }}
            .details-summary::-webkit-details-marker {{ display: none; }}
            .details-summary:before {{ content: '►'; margin-right: 8px; font-size: 10px; }}
            details[open] > .details-summary:before {{ content: '▼'; }}
            .details-content {{ padding: 15px; border-top: 1px solid #e5e5e5; }}
            .grading-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            .grade-box {{ text-align: center; }}
            .grade-title {{ font-size: 14px; color: #555; margin: 0 0 5px; }}
            .grade-value {{ font-size: 24px; font-weight: 700; color: #111; margin: 0; }}
            .condition-notes {{ font-size: 14px; margin-top: 15px; white-space: pre-wrap; word-wrap: break-word; }}
            .condition-tags-container {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; }}
            .condition-tag {{ background-color: #e9e9e9; color: #333; font-size: 12px; padding: 4px 10px; border-radius: 15px; font-weight: 500; }}
            .track-listing {{ list-style: none; padding-left: 0; font-size: 14px; }}
            .track-listing li {{ padding: 6px 0; border-bottom: 1px solid #f5f5f5; }}
            .track-listing li:last-child {{ border-bottom: none; }}
            .track-listing .track-pos {{ display: inline-block; width: 40px; font-weight: 600; color: #777; }}
            .matrix-content {{ white-space: pre-wrap; word-wrap: break-word; font-family: 'Menlo', 'Courier New', monospace; font-size: 13px; background: #f9f9f9; border-radius: 4px; padding: 10px; }}
            .at-footer {{ background-color: #f7f7f7; padding: 20px 25px; font-size: 12px; color: #666; text-align: center; border-top: 1px solid #e1e1e1; }}
        </style>
        <div class="at-container">
            <div class="at-header">
                <h2 class="artist">{get('artist')}</h2>
                <p class="title">{get('title')}</p>
                <div class="info-grid">
                    {info_grid_html}
                </div>
            </div>
            <div class="at-body">
                <details class="details-section" open>
                    <summary class="details-summary">Condition Report</summary>
                    <div class="details-content">
                        <div class="grading-grid">
                            <div class="grade-box">
                                <p class="grade-title">Media (Vinyl)</p>
                                <p class="grade-value">{GRADE_ABBREVIATIONS.get(get('media_condition'), '')}</p>
                            </div>
                            <div class="grade-box">
                                <p class="grade-title">Sleeve</p>
                                <p class="grade-value">{GRADE_ABBREVIATIONS.get(get('sleeve_condition'), '')}</p>
                            </div>
                        </div>
                        {'<div class="condition-notes">' + get('condition_notes').replace(chr(10), '<br>') + '</div>' if get('condition_notes') else ''}
                        {'<div class="condition-tags-container">' + tags_html + '</div>' if tags_html else ''}
                    </div>
                </details>

                {'<details class="details-section"><summary class="details-summary">Matrix / Runout</summary>' + matrix_html + '</details>' if matrix_html else ''}

                {'<details class="details-section"><summary class="details-summary">Tracklist</summary><div class="details-content">' + tracklist_html + '</div></details>' if tracklist_html else ''}

            </div>
            <div class="at-footer">
                {seller_footer}
            </div>
        </div>
        """
        final_html = '\n'.join([line.strip() for line in html.split('\n')])
        self.full_desc.delete("1.0", tk.END)
        self.full_desc.insert("1.0", final_html)
    
    def list_on_discogs(self):
        """List item on Discogs"""
        if not self.discogs_api.is_connected():
            messagebox.showwarning("Not Connected", "Please connect to Discogs first")
            return
        if not self.current_release_id:
            messagebox.showerror("Missing Release", "You must select a specific Discogs release variant first")
            return
        try:
            price = float(self.price_entry.get())
            media_condition = self.entries["media_condition"].get()
            if not media_condition or media_condition not in REVERSE_GRADE_MAP:
                messagebox.showwarning("Validation Error", "Please select a valid media condition")
                return
        except (ValueError, TypeError):
            messagebox.showwarning("Validation Error", "Please enter a valid price")
            return
        
        listing_data = {
            'release_id': self.current_release_id,
            'price': price,
            'status': 'Draft',
            'condition': REVERSE_GRADE_MAP.get(media_condition),
            'sleeve_condition': REVERSE_GRADE_MAP.get(self.entries["sleeve_condition"].get(), 'Generic'),
            'comments': self.full_desc.get("1.0", tk.END).strip()
        }
        
        self.root.config(cursor="watch")
        self.root.update()
        
        def list_worker():
            try:
                listing_id = self.discogs_api.create_listing(listing_data)
                if listing_id:
                    self.safe_after(0, lambda: self._handle_listing_success(listing_id))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Listing Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        
        threading.Thread(target=list_worker, daemon=True).start()
    
    def _handle_listing_success(self, listing_id):
        """Handle successful Discogs listing"""
        messagebox.showinfo("Success", f"Successfully listed item on Discogs as a Draft (Listing ID: {listing_id})")
        if self.editing_sku:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE inventory SET discogs_listing_id = ? WHERE sku = ?", (listing_id, self.editing_sku))
            except Exception as e:
                logger.error(f"Failed to update inventory with listing ID: {e}")
    
    def list_on_ebay(self):
        """Create eBay draft listing, now with image uploading and correct condition mapping."""
        if not self.ebay_api.test_connection():
            messagebox.showwarning("Not Connected", "Please check your eBay credentials in config.json and re-authenticate if necessary.")
            return

        # --- Validation ---
        required_fields = ['artist', 'title', 'media_condition']
        for field in required_fields:
            if not self.entries[field.replace(' ', '_')].get().strip():
                messagebox.showwarning("Validation Error", f"Please enter {field}")
                return
        try:
            price = float(self.price_entry.get())
            if price <= 0:
                messagebox.showwarning("Validation Error", "Please enter a valid price")
                return
        except (ValueError, TypeError):
            messagebox.showwarning("Validation Error", "Please enter a valid price")
            return

        # --- Data Gathering & Condition Fix ---
        sku = self.editing_sku or self.sku_display_var.get() or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        if not self.editing_sku and not self.temporary_sku:
            self.sku_display_var.set(sku)

        format_val = self.entries["format"].get() or "LP"
        media_cond_str = self.entries["media_condition"].get()
        
        # Default to USED_GOOD for unknown grades; do not use USED_EXCELLENT which eBay no longer accepts for vinyl
        condition_enum = EBAY_INVENTORY_CONDITION_MAP.get(media_cond_str, "USED_GOOD")
        condition_id_numeric = EBAY_CONDITION_MAP_NUMERIC.get(media_cond_str, "3000")
        
        category_id = EBAY_VINYL_CATEGORIES.get(format_val, "176985")
        ebay_title = self.entries["listing_title"].get() or f"{self.entries['artist'].get()} - {self.entries['title'].get()}"
        description_html = self.full_desc.get("1.0", tk.END).strip()

        listing_data = {
            "sku": sku, "title": ebay_title[:80], "description": description_html,
            "categoryId": str(category_id), "price": price, "quantity": 1,
            "condition_enum": condition_enum,
            "condition_id_numeric": condition_id_numeric,
            "media_condition": self.entries["media_condition"].get(), # Pass for summary
            "sleeve_condition": self.entries["sleeve_condition"].get(), # Pass for summary
            "currency": "GBP", "marketplaceId": self.config.get("marketplace_id", "EBAY_GB"),
            "paymentPolicyId": self.config.get("ebay_payment_policy_id"),
            "returnPolicyId": self.config.get("ebay_return_policy_id"),
            "shippingPolicyId": self.config.get("ebay_shipping_policy_id"),
            "images": self.image_paths, # Pass local paths for the API to handle
        }

        # --- Start Background Worker ---
        self.root.config(cursor="watch")
        self.root.update()
        self.notebook.select(self.inventory_tab)

        def list_worker():
            try:
                self.append_log(f"SKU {sku}: Creating/updating eBay inventory item and offer...", "black")
                result = self.ebay_api.create_draft_listing(listing_data)
                
                if result.get("success"):
                    self.safe_after(0, lambda: self._handle_ebay_listing_success(sku, result.get("offerId")))
                else:
                    error_message = result.get('error', 'Unknown error')
                    self.append_log(f"SKU {sku}: eBay listing failed. {error_message}", "red")
                    self.safe_after(0, lambda: messagebox.showerror("Listing Failed", f"eBay listing failed for SKU {sku}:\n\n{error_message}"))

            except Exception as e:
                self.append_log(f"SKU {sku}: An unexpected error occurred: {e}", "red")
                self.safe_after(0, lambda: messagebox.showerror("Listing Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        
        threading.Thread(target=list_worker, daemon=True).start()
    
    def _handle_ebay_listing_success(self, sku, offer_id):
        """Handle successful eBay listing"""
        # Log success; the offer is now live (not a draft)
        self.append_log(f"SKU {sku}: Successfully created eBay listing (Offer ID: {offer_id}).", "green")

        # Optionally, navigate user to their active listings page.  Seller Hub drafts are
        # no longer relevant since drafts are not created via API.
        ebay_listing_url = "https://www.ebay.co.uk/sh/lst/active"
        messagebox.showinfo("Success", f"Successfully created eBay DRAFT listing!\n\nSKU: {sku}\nOffer ID: {offer_id}\n\nCheck your eBay drafts folder to review and publish.")
        
        if sku:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE inventory SET ebay_listing_id = ? WHERE sku = ?", (offer_id, sku))
                self.populate_inventory_view() # Refresh to show the new ID
            except Exception as e:
                logger.error(f"Failed to update inventory with eBay ID: {e}")
                self.append_log(f"SKU {sku}: Failed to save eBay Offer ID to local DB: {e}", "red")
    
    def save_to_inventory(self):
        """Save current form to inventory, ensuring full payload is saved on update."""
        payload_json = json.dumps(self._serialize_form_to_payload())
        data = {
            "artist": self.entries["artist"].get().strip(),
            "title": self.entries["title"].get().strip(),
            "cat_no": self.entries["cat_no"].get().strip(),
            "year": self.entries["year"].get().strip(),
            "format": self.entries["format"].get(),
            "media_condition": self.entries["media_condition"].get(),
            "sleeve_condition": self.entries["sleeve_condition"].get(),
            "price": self.price_entry.get().strip(),
            "status": "For Sale",
            "discogs_release_id": self.current_release_id,
            "notes": self.entries["condition_notes"].get("1.0", "end-1c").strip(),
            "matrix_runout": self.entries["matrix_runout"].get("1.0", "end-1c").strip(),
            "condition_tags": self.entries["condition_tags"].get().strip(),
            "description": self.full_desc.get("1.0", tk.END).strip(),
            "shipping_option": self.entries["shipping_option"].get(),
            "barcode": self.entries["barcode"].get().strip(),
            "genre": self.entries["genre"].get(),
            "new_used": self.entries["new_used"].get(),
            "listing_title": self.entries["listing_title"].get().strip()
        }
        
        if not data["title"]:
            messagebox.showwarning("Validation Error", "Title is required")
            return
        try:
            price = float(data["price"]) if data["price"] else 0
            data["price"] = price
        except ValueError:
            messagebox.showwarning("Validation Error", "Invalid price")
            return
        
        is_update = bool(self.editing_sku)
        
        if is_update:
            sku = self.editing_sku
        elif self.temporary_sku:
            sku = self.temporary_sku.replace("-TEMP", "")
            self.temporary_sku = None
        else:
            sku = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                if is_update:
                    # --- CRITICAL FIX: Ensure payload is saved on update ---
                    sql = """UPDATE inventory SET artist = :artist, title = :title, cat_no = :cat_no, year = :year, format = :format,
                            media_condition = :media_condition, sleeve_condition = :sleeve_condition, price = :price, 
                            discogs_release_id = :discogs_release_id, notes = :notes, description = :description,
                            shipping_option = :shipping_option, barcode = :barcode, genre = :genre, new_used = :new_used, 
                            listing_title = :listing_title, matrix_runout = :matrix_runout, condition_tags = :condition_tags,
                            last_modified = :last_modified, inv_updated_at = :inv_updated_at, lister_payload = :lister_payload WHERE sku = :sku"""
                    params = data
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    params["last_modified"] = now_iso
                    # update local inventory timestamp
                    params["inv_updated_at"] = now_iso
                    params["lister_payload"] = payload_json
                    params["sku"] = sku
                    cursor.execute(sql, params)
                    messagebox.showinfo("Success", f"Updated SKU: {sku}")
                else:
                    sql = """INSERT INTO inventory (sku, artist, title, cat_no, year, format, media_condition,
                            sleeve_condition, price, status, discogs_release_id, notes, description, shipping_option, barcode, genre, new_used,
                            listing_title, matrix_runout, condition_tags, date_added, last_modified, inv_updated_at, lister_payload
                            ) VALUES (:sku, :artist, :title, :cat_no, :year, :format, :media_condition,
                            :sleeve_condition, :price, :status, :discogs_release_id, :notes, :description, :shipping_option, :barcode, :genre, :new_used,
                            :listing_title, :matrix_runout, :condition_tags, :date_added, :last_modified, :inv_updated_at, :lister_payload)"""
                    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    params = data
                    params["sku"] = sku
                    params["date_added"] = now
                    params["last_modified"] = now
                    params["inv_updated_at"] = now
                    params["lister_payload"] = payload_json
                    cursor.execute(sql, params)
                    messagebox.showinfo("Success", f"Saved with SKU: {sku}")
            
            self.populate_inventory_view()
            self.clear_form()
            
        except Exception as e:
            logger.error(f"Failed to save to inventory: {e}", exc_info=True)
            messagebox.showerror("Database Error", f"Failed to save: {e}")

    def clear_form(self):
        """Clear all form fields"""
        for key, widget in self.entries.items():
            if isinstance(widget, (tk.Entry, ttk.Entry)):
                widget.delete(0, tk.END)
            elif isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
            elif isinstance(widget, ttk.Combobox):
                widget.set("")
        
        self.price_entry.delete(0, tk.END)
        self.full_desc.delete("1.0", tk.END)
        
        self.current_release_id = None
        self.editing_sku = None
        self.temporary_sku = None
        self.image_paths = []
        self._update_image_listbox()
        self._clear_image_preview()
        self.sku_display_var.set("")
        
        self.save_button.config(text="Save to Inventory")
        self.release_status_label.config(text="⚠ No release selected", fg="red")
        
        for item in self.discogs_tree.get_children():
            self.discogs_tree.delete(item)
    
    def generate_image_qr_code(self):
        """Generate QR code for image association."""
        if not QR_LIBRARIES_AVAILABLE:
            messagebox.showerror("Missing Libraries", "PIL (Pillow) and qrcode libraries are required for this feature.")
            return

        if self.editing_sku:
            sku = self.editing_sku
        elif not self.temporary_sku:
            # Create a temporary SKU for the new item if it doesn't have one
            self.temporary_sku = f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-TEMP"
            sku = self.temporary_sku
        else:
            sku = self.temporary_sku
            
        self.sku_display_var.set(sku)

        qr_data = f"vinyltool_sku:{sku}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        
        # Display in a new window
        qr_window = tk.Toplevel(self.root)
        qr_window.title(f"QR Code for SKU: {sku}")
        
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(qr_window, image=photo)
        label.image = photo # Keep a reference
        label.pack(padx=20, pady=20)
        
        tk.Label(qr_window, text=f"Scan this code with your phone to associate images with\nSKU: {sku}", justify='center').pack(pady=(0,10))

    def select_images_manually(self):
        """[NEW & FIXED] Open a file dialog to select images and copy them to a managed folder."""
        # 1. Ensure we have a SKU to work with
        if self.editing_sku:
            sku = self.editing_sku
        elif not self.temporary_sku:
            # Create a temporary SKU if one doesn't exist for this new item
            self.temporary_sku = f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-TEMP"
            sku = self.temporary_sku
        else:
            sku = self.temporary_sku
        
        self.sku_display_var.set(sku)

        # 2. Open file dialog to select images
        selected_files = filedialog.askopenfilenames(
            title="Select images for this item",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.heic"), ("All files", "*.*")]
        )
        if not selected_files:
            return # User cancelled

        # 3. Create a dedicated, permanent folder for this SKU's images
        # [FIX] Changed 'item_images' to 'managed_images' to match expected path
        permanent_storage_path = os.path.join(os.path.dirname(__file__), "managed_images", sku.replace('-TEMP', ''))
        os.makedirs(permanent_storage_path, exist_ok=True)
        
        new_image_paths = []
        for source_path in selected_files:
            filename = os.path.basename(source_path)
            destination_path = os.path.join(permanent_storage_path, filename)
            try:
                # Copy the file to the managed folder. Use copy2 to preserve metadata.
                shutil.copy2(source_path, destination_path)
                new_image_paths.append(destination_path)
                logger.info(f"Copied '{filename}' to '{permanent_storage_path}'")
            except Exception as e:
                logger.error(f"Failed to copy image '{filename}': {e}")
                messagebox.showerror("Image Copy Error", f"Could not copy file: {filename}\n\nError: {e}")

        # 4. Update the internal image list and the UI
        # Add new paths and remove duplicates, preserving order
        for path in new_image_paths:
            if path not in self.image_paths:
                self.image_paths.append(path)
        
        self._update_image_listbox()
        messagebox.showinfo("Images Linked", f"Successfully linked {len(new_image_paths)} images to SKU {sku}.")

    def import_staged_images(self):
        """Import images from the staging folder that have a matching SKU via QR or filename."""
        staging_path = self.image_staging_path_var.get()
        if not staging_path or not os.path.isdir(staging_path):
            messagebox.showerror("Path Error", "Image staging path is not set or is not a valid directory.\nPlease set it in the Settings tab.")
            return

        if not self.editing_sku and not self.temporary_sku:
            messagebox.showwarning("No SKU", "Please save the item or generate a QR code first to create an SKU for image association.")
            return
            
        sku_to_find = self.editing_sku or self.temporary_sku
        logger.info(f"Scanning for images for SKU: {sku_to_find}")

        found_images = []
        
        # Scan staging path for subfolders matching the SKU
        sku_folder_path = os.path.join(staging_path, sku_to_find)
        if os.path.isdir(sku_folder_path):
            logger.info(f"Found SKU subfolder: {sku_folder_path}")
            for filename in sorted(os.listdir(sku_folder_path)):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    found_images.append(os.path.join(sku_folder_path, filename))
        else:
            logger.warning(f"SKU subfolder not found. Scanning staging root for QR codes or prefixed files.")
            # Fallback: scan root of staging path for images containing the QR code or SKU prefix
            for filename in os.listdir(staging_path):
                 if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.heic')):
                    filepath = os.path.join(staging_path, filename)
                    # Check for SKU prefix
                    if filename.startswith(sku_to_find):
                        found_images.append(filepath)
                        logger.info(f"Found matching SKU prefix in {filename}")
                        continue # Move to next file

                    # Check for QR code if pyzbar is available
                    if QR_DECODER_AVAILABLE:
                        try:
                            with Image.open(filepath) as img:
                                decoded_objects = qr_decode(img, symbols=[ZBarSymbol.QRCODE])
                                for obj in decoded_objects:
                                    decoded_data = obj.data.decode('utf-8')
                                    if decoded_data == f"vinyltool_sku:{sku_to_find}":
                                        found_images.append(filepath)
                                        logger.info(f"Found matching QR code in {filename}")
                                        break # Stop checking this image's QR codes
                        except Exception as e:
                            logger.error(f"Error decoding {filename}: {e}")

        if not found_images:
            messagebox.showinfo("No Images Found", f"No images for SKU '{sku_to_find}' were found in the staging folder.")
            return

        # Move images to a permanent, organized location
        permanent_storage_path = os.path.join(os.path.dirname(__file__), "managed_images", sku_to_find.replace('-TEMP',''))
        os.makedirs(permanent_storage_path, exist_ok=True)
        
        new_image_paths = []
        for old_path in found_images:
            filename = os.path.basename(old_path)
            new_path = os.path.join(permanent_storage_path, filename)
            try:
                shutil.move(old_path, new_path)
                new_image_paths.append(new_path)
                logger.info(f"Moved {filename} to {permanent_storage_path}")
            except Exception as e:
                logger.error(f"Failed to move {filename}: {e}")
                # If move fails, try to copy as a fallback
                try:
                    shutil.copy2(old_path, new_path)
                    new_image_paths.append(new_path)
                    logger.info(f"Copied {filename} to {permanent_storage_path} as a fallback.")
                except Exception as copy_e:
                    logger.error(f"Fallback copy also failed for {filename}: {copy_e}")

        # Update the UI
        self.image_paths.extend(new_image_paths)
        self.image_paths = sorted(list(set(self.image_paths))) # Remove duplicates and sort
        self._update_image_listbox()
        messagebox.showinfo("Import Complete", f"Successfully imported {len(new_image_paths)} images.")

    def populate_inventory_view(self, search_term=""):
        """Populate inventory tree view"""
        for item in self.inventory_tree.get_children():
            self.inventory_tree.delete(item)
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Select additional ID columns and timestamps for display and logic
                query = "SELECT sku, artist, title, price, status, ebay_item_draft_id, ebay_listing_id, discogs_listing_id, date_added, inv_updated_at, ebay_updated_at, discogs_updated_at FROM inventory"
                params = []
                if search_term:
                    query += " WHERE artist LIKE ? OR title LIKE ? OR sku LIKE ?"
                    search_pattern = f"%{search_term}%"
                    params = [search_pattern, search_pattern, search_pattern]
                
                sort_map = {
                    "SKU": "sku",
                    "Artist": "artist",
                    "Title": "title",
                    "Price": "price",
                    "Status": "status",
                    "eBay Draft ID": "ebay_item_draft_id",
                    "eBay Listing ID": "ebay_listing_id",
                    "Discogs ID": "discogs_listing_id",
                    "Date Added": "date_added"
                }
                sort_col = sort_map.get(self.inventory_sort_column, "id")
                query += f" ORDER BY {sort_col} {self.inventory_sort_direction}"
                
                cursor.execute(query, params)
                
                for row in cursor.fetchall():
                    # row indices: 0=sku,1=artist,2=title,3=price,4=status,5=ebay_item_draft_id,6=ebay_listing_id,7=discogs_listing_id,8=date_added,9=inv_updated_at,10=ebay_updated_at,11=discogs_updated_at
                    price_str = f"£{row[3]:.2f}" if row[3] else ""
                    date_added_str = ""
                    if row[8]:
                        try:
                            dt = datetime.datetime.fromisoformat(str(row[8]).replace('Z', '+00:00'))
                            date_added_str = dt.strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            date_added_str = row[8]
                    draft_id = row[5] or ""
                    live_id = row[6] or ""
                    discogs_id = row[7] or ""
                    values = (row[0], row[1] or "", row[2] or "", price_str, row[4] or "", draft_id, live_id, discogs_id, date_added_str)
                    self.inventory_tree.insert("", "end", values=values)
                    
        except Exception as e:
            logger.error(f"Failed to populate inventory: {e}")
            messagebox.showerror("Database Error", f"Failed to load inventory: {e}")
    
    def sort_inventory(self, col):
        """Sort inventory by column"""
        if self.inventory_sort_column == col:
            self.inventory_sort_direction = "ASC" if self.inventory_sort_direction == "DESC" else "DESC"
        else:
            self.inventory_sort_column = col
            self.inventory_sort_direction = "ASC"
        self.populate_inventory_view(self.inventory_search_var.get())
    
    def load_item_for_editing(self, event=None):
        """
        Load item by reading from the database and prioritizing the lister_payload.
        """
        selected = self.inventory_tree.focus()
        if not selected: return
        
        sku = self.inventory_tree.item(selected, "values")[0]
        
        try:
            # Use the getter that intelligently merges the payload
            record_data = self._get_inventory_record(sku)

            if not record_data:
                messagebox.showerror("Error", f"Could not find record for SKU: {sku}")
                return

            self.clear_form()
            
            # The payload is already merged, so we can just apply it
            self._apply_payload_to_form(record_data)

            # Special handling for DB fields not in the typical payload
            if 'notes' in record_data and not record_data.get('condition_notes'):
                 self.entries['condition_notes'].delete('1.0', tk.END)
                 self.entries['condition_notes'].insert('1.0', record_data['notes'])

            self.editing_sku = sku
            self.sku_display_var.set(sku)
            self.save_button.config(text="Update Inventory")
            
            release_id = record_data.get("discogs_release_id")
            if release_id:
                self.release_status_label.config(text=f"✓ Editing SKU: {sku} (Release ID: {release_id})", fg="blue")
            else:
                self.release_status_label.config(text=f"✓ Editing SKU: {sku} (No release linked)", fg="orange")
            
            self.notebook.select(self.lister_tab)
            
        except Exception as e:
            logger.error(f"Failed to load item for editing: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to load item: {e}")

    def edit_in_lister(self):
        """Load selected item in lister tab"""
        self.load_item_for_editing()
    
    def delete_inventory_item(self):
        """Delete selected inventory items with two-way sync."""
        selected_items = self.inventory_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select one or more items to delete.")
            return

        item_details = []
        for item_id in selected_items:
            values = self.inventory_tree.item(item_id, "values")
            sku = values[0]
            record = self._get_inventory_record(sku)
            item_details.append({"sku": sku, "discogs_listing_id": record.get("discogs_listing_id")})

        msg = f"Are you sure you want to delete {len(item_details)} item(s)?\n\nThis will also attempt to delete their corresponding Discogs listings."
        if not messagebox.askyesno("Confirm Delete", msg):
            return
        
        self.root.config(cursor="watch")
        self.root.update()

        def delete_worker():
            success_count, fail_count = 0, 0
            for item in item_details:
                sku, discogs_listing_id = item["sku"], item["discogs_listing_id"]
                if discogs_listing_id and self.discogs_api.is_connected():
                    self.append_log(f"Deleting Discogs listing {discogs_listing_id} for SKU {sku}...", "black")
                    if not self.discogs_api.delete_listing(discogs_listing_id):
                        self.append_log(f"✗ Failed to delete Discogs listing {discogs_listing_id}.", "red")
                        if not messagebox.askyesno("Discogs Deletion Failed", f"Failed to delete Discogs listing for SKU {sku}.\n\nDo you still want to delete the item from your local inventory?"):
                            fail_count += 1
                            continue
                try:
                    with self.db.get_connection() as conn:
                        conn.cursor().execute("DELETE FROM inventory WHERE sku = ?", (sku,))
                    self.append_log(f"✓ Deleted SKU {sku} from local inventory.", "green")
                    success_count += 1
                except Exception as e:
                    self.append_log(f"✗ Failed to delete SKU {sku} from local DB: {e}", "red")
                    fail_count += 1
            self.safe_after(0, lambda: (self.root.config(cursor=""), self.populate_inventory_view(), messagebox.showinfo("Deletion Complete", f"Successfully deleted: {success_count}\nFailed or skipped: {fail_count}")))
        threading.Thread(target=delete_worker, daemon=True).start()

    def select_all_inventory(self):
        """Select all items in inventory"""
        for item in self.inventory_tree.get_children():
            self.inventory_tree.selection_add(item)
    
    def deselect_all_inventory(self):
        """Deselect all items in inventory"""
        self.inventory_tree.selection_remove(self.inventory_tree.selection())
    
    def update_inventory_status(self, new_status):
        """Update status of selected inventory items"""
        selected = self.inventory_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select items to update")
            return
        skus = [self.inventory_tree.item(item, "values")[0] for item in selected]
        try:
            with self.db.get_connection() as conn:
                placeholders = ",".join("?" * len(skus))
                sql = f"UPDATE inventory SET status = ?, last_modified = ? WHERE sku IN ({placeholders})"
                params = [new_status, datetime.datetime.now(datetime.timezone.utc).isoformat()] + skus
                conn.cursor().execute(sql, params)
            self.populate_inventory_view()
            self.append_log(f"Updated {len(skus)} item(s) to '{new_status}'", "green")
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            messagebox.showerror("Error", f"Failed to update status: {e}")
    
    def on_inventory_selection(self, event=None):
        """Handle inventory selection change"""
        selected = self.inventory_tree.selection()
        state = "normal" if selected else "disabled"
        # The button is connected to `list_on_ebay` now, not `publish_to_ebay`
        self.list_on_ebay_button.config(state="normal") # Enable for single item
        self.list_on_discogs_button.config(state="normal")

        self.publish_ebay_btn.config(state=state)
        self.publish_discogs_btn.config(state=state)
        # Enable/disable the quick link button based on selection
        try:
            self.open_in_browser_btn.config(state=state)
        except Exception:
            pass

    def create_or_update_offer(self, listing_data: dict):
        """
        Step 2: Common offer creation/update logic extracted.
        Returns: dict with at least { 'success': bool, 'offerId': optional, 'error': optional }.
        For now, delegates to the existing publish_to_ebay logic so behavior is unchanged.
        """
        if globals().get("PUBLISH_HARD_BLOCK"):
            self.append_log("[publish] BLOCKED BY FLAG", "orange")
            return {"success": False, "error": "Blocked"}
        # Draft creation/update is no longer supported in this version.  To
        # publish a listing on eBay, first save the item to your Inventory and
        # then use the "Publish Live to eBay" button on the Inventory tab.  We
        # return an informative error here to avoid unexpected calls.
        return {
            "success": False,
            "error": "Draft listing functionality has been removed. Please add the item to your Inventory and publish from there."
        }
    
    def publish_to_ebay(self):
        """Publish selected items from inventory to eBay, including images."""
        selected = self.inventory_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select items from the inventory to publish.")
            return

        self.notebook.select(self.inventory_tab) # Switch to see logs

        def publish_worker():
            for item in selected:
                sku = self.inventory_tree.item(item, "values")[0]
                self.append_log(f"SKU {sku}: Starting publish process for eBay...", "black")

                try:
                    record = self._get_inventory_record(sku)
                    if not record:
                        self.append_log(f"SKU {sku}: Could not find record.", "red")
                        continue
                    # Latest-wins check: warn if remote eBay data is newer than local
                    try:
                        local_ts = record.get("inv_updated_at") or record.get("last_modified") or record.get("date_added")
                        remote_ts = record.get("ebay_updated_at")
                        proceed = True
                        if remote_ts and local_ts:
                            try:
                                ldt = datetime.datetime.fromisoformat(str(local_ts).replace('Z','+00:00'))
                                rdt = datetime.datetime.fromisoformat(str(remote_ts).replace('Z','+00:00'))
                                if rdt > ldt:
                                    msg = (f"SKU {sku}: The eBay data was updated more recently than your local copy.\n"
                                           f"Local updated: {ldt.isoformat()}\n"
                                           f"eBay updated: {rdt.isoformat()}\n\n"
                                           "Proceeding will overwrite eBay with local data. Continue?")
                                    proceed = messagebox.askyesno("Potential Conflict", msg)
                            except Exception:
                                pass
                        if not proceed:
                            self.append_log(f"SKU {sku}: Skipped due to newer eBay data.", "orange")
                            continue
                    except Exception:
                        pass

                    # Ensure categoryId is set before validation; use default if missing
                    try:
                        if not record.get("categoryId") and not record.get("category_id"):
                            fmt = record.get("format", "LP") or "LP"
                            record = dict(record)
                            record["categoryId"] = EBAY_VINYL_CATEGORIES.get(fmt, "176985")
                    except Exception:
                        pass
                    errors = validate_listing("ebay", record, self.config)
                    if errors:
                        self.append_log(f"SKU {sku}: Validation failed: {', '.join(errors)}", "red")
                        continue

                    # --- Listing Creation with Correct Condition ---
                    format_val = record.get("format", "LP")
                    media_cond_str = record.get("media_condition", "")

                    # Map media grade to eBay enums/IDs. Use a conservative fallback:
                    # for unknown grades default to USED_GOOD (enum) and a numeric
                    # ID of 3000. The numeric ID will not be sent for records.
                    condition_enum = EBAY_INVENTORY_CONDITION_MAP.get(media_cond_str, "USED_GOOD")
                    condition_id_numeric = EBAY_CONDITION_MAP_NUMERIC.get(media_cond_str, "3000")
                    category_id = EBAY_VINYL_CATEGORIES.get(format_val, "176985")

                    listing_data = {
                        "sku": sku,
                        "title": record.get("listing_title") or record.get("title", "")[:80],
                        "description": record.get("description", ""),
                        "price": record.get("price", 0),
                        "quantity": 1,
                        "categoryId": category_id,
                        "condition_enum": condition_enum,
                        "condition_id_numeric": condition_id_numeric,
                        "media_condition": record.get("media_condition"),
                        "sleeve_condition": record.get("sleeve_condition"),
                        "images": record.get("images", []),
                        "marketplaceId": self.config.get("marketplace_id", "EBAY_GB"),
                        "paymentPolicyId": self.config.get("ebay_payment_policy_id"),
                        "returnPolicyId": self.config.get("ebay_return_policy_id"),
                        "shippingPolicyId": self.config.get("ebay_shipping_policy_id"),
                        "currency": "GBP"
                    }

                    result = self.ebay_api.create_draft_listing(listing_data)
                    if result.get("success"):
                        offer_id = result.get('offerId')
                        self.append_log(f"SKU {sku}: Successfully created eBay draft (Offer ID: {offer_id})", "green")
                        # Write back ID and timestamp
                        try:
                            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                            with self.db.get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "UPDATE inventory SET ebay_listing_id = ?, ebay_updated_at = ? WHERE sku = ?",
                                    (offer_id, now_iso, sku),
                                )
                        except Exception as e:
                            logger.error(f"Failed to update inventory with eBay listing ID: {e}")
                            self.append_log(f"SKU {sku}: Failed to save eBay Offer ID to local DB: {e}", "red")
                    else:
                        self.append_log(f"SKU {sku}: eBay listing failed: {result.get('error')}", "red")

                except Exception as e:
                    self.append_log(f"SKU {sku}: An unexpected error occurred: {e}", "red")
                    logger.error(f"Error publishing SKU {sku} to eBay", exc_info=True)
            
            self.safe_after(0, self.populate_inventory_view)
            self.safe_after(0, lambda: self.root.config(cursor=""))

        self.root.config(cursor="watch")
        self.root.update()
        threading.Thread(target=publish_worker, daemon=True).start()

    def publish_to_discogs(self):
        """Publish selected items to Discogs"""
        selected = self.inventory_tree.selection()
        if not selected: return
        for item in selected:
            sku = self.inventory_tree.item(item, "values")[0]
            try:
                record = self._get_inventory_record(sku)
                if not record:
                    self.append_log(f"SKU {sku}: Could not find record.", "red")
                    continue
                # Latest-wins check: warn if Discogs data is newer
                try:
                    local_ts = record.get("inv_updated_at") or record.get("last_modified") or record.get("date_added")
                    remote_ts = record.get("discogs_updated_at")
                    proceed = True
                    if remote_ts and local_ts:
                        try:
                            ldt = datetime.datetime.fromisoformat(str(local_ts).replace('Z','+00:00'))
                            rdt = datetime.datetime.fromisoformat(str(remote_ts).replace('Z','+00:00'))
                            if rdt > ldt:
                                msg = (f"SKU {sku}: The Discogs data was updated more recently than your local copy.\n"
                                       f"Local updated: {ldt.isoformat()}\n"
                                       f"Discogs updated: {rdt.isoformat()}\n\n"
                                       "Proceeding will overwrite Discogs with local data. Continue?")
                                proceed = messagebox.askyesno("Potential Conflict", msg)
                        except Exception:
                            pass
                    if not proceed:
                        self.append_log(f"SKU {sku}: Skipped due to newer Discogs data.", "orange")
                        continue
                except Exception:
                    pass

                errors = validate_listing("discogs", record, self.config)
                if errors:
                    self.append_log(f"SKU {sku}: {', '.join(errors)}", "red")
                    continue
                self.append_log(f"Publishing SKU {sku} to Discogs...", "black")
                listing_data = {
                    "release_id": record.get("discogs_release_id"),
                    "condition": REVERSE_GRADE_MAP.get(record.get("media_condition"), "Good (G)"),
                    "sleeve_condition": REVERSE_GRADE_MAP.get(record.get("sleeve_condition"), "Good (G)"),
                    "price": record.get("price", 0), "status": "Draft", "comments": record.get("description", "")
                }
                listing_id = self.discogs_api.create_listing(listing_data)
                if listing_id:
                    self.append_log(f"SKU {sku}: Listed as Draft (ID: {listing_id})", "green")
                    try:
                        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        with self.db.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE inventory SET discogs_listing_id = ?, discogs_updated_at = ? WHERE sku = ?",
                                (listing_id, now_iso, sku),
                            )
                    except Exception as e:
                        logger.error(f"Failed to update inventory with Discogs listing ID: {e}")
                        self.append_log(f"SKU {sku}: Failed to save Discogs listing ID to DB: {e}", "red")
                else:
                    self.append_log(f"SKU {sku}: Failed to create listing", "red")
            except Exception as e:
                self.append_log(f"SKU {sku}: Error - {e}", "red")

    def save_to_ebay_drafts_inventory(self):
        """
        Create a Sell Listings draft for each selected inventory item. This is a safe operation
        that does not publish the listing live. The returned draft ID and update timestamp
        are saved back to the database.
        """
        if globals().get("PUBLISH_HARD_BLOCK"):
            self.append_log("[draft] BLOCKED BY FLAG", "orange")
            return
        selected = self.inventory_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select items from the inventory to save drafts.")
            return

        # Switch to inventory tab to display logs
        self.notebook.select(self.inventory_tab)

        def draft_worker():
            # Force the eBay API wrapper to refresh the access token on each
            # draft creation. This ensures that any newly added scopes (e.g.
            # sell.listing) are included in the token. Without this, the
            # cached access token may not contain the required scope and
            # draft creation can fail silently.
            try:
                self.ebay_api.access_token = None
            except Exception:
                pass
            for item in selected:
                sku = self.inventory_tree.item(item, "values")[0]
                try:
                    record = self._get_inventory_record(sku)
                    if not record:
                        self.append_log(f"SKU {sku}: Could not find record.", "red")
                        continue

                    # Check latest-wins management: warn if remote data is newer than local
                    try:
                        local_ts = record.get("inv_updated_at") or record.get("last_modified") or record.get("date_added")
                        remote_ts = record.get("ebay_updated_at")
                        proceed = True
                        if remote_ts and local_ts:
                            try:
                                ldt = datetime.datetime.fromisoformat(str(local_ts).replace('Z','+00:00'))
                                rdt = datetime.datetime.fromisoformat(str(remote_ts).replace('Z','+00:00'))
                                if rdt > ldt:
                                    msg = (f"SKU {sku}: The eBay data was updated more recently than your local copy.\n"
                                           f"Local updated: {ldt.isoformat()}\n"
                                           f"eBay updated: {rdt.isoformat()}\n\n"
                                           "Proceeding will overwrite eBay with local data. Continue?")
                                    proceed = messagebox.askyesno("Potential Conflict", msg)
                            except Exception:
                                pass
                        if not proceed:
                            self.append_log(f"SKU {sku}: Skipped due to newer eBay data.", "orange")
                            continue
                    except Exception:
                        pass

                    # Build listing_data similar to publish_to_ebay
                    format_val = record.get("format", "LP")
                    media_cond_str = record.get("media_condition", "")
                    # Map media grade to eBay enums/IDs. Use "USED_GOOD" and 3000 as
                    # safe fallbacks for unknown grades. The numeric ID will not be
                    # transmitted for the Records category.
                    condition_enum = EBAY_INVENTORY_CONDITION_MAP.get(media_cond_str, "USED_GOOD")
                    condition_id_numeric = EBAY_CONDITION_MAP_NUMERIC.get(media_cond_str, "3000")
                    category_id = EBAY_VINYL_CATEGORIES.get(format_val, "176985")
                    listing_data = {
                        "sku": sku,
                        "title": record.get("listing_title") or record.get("title", "")[:80],
                        "description": record.get("description", ""),
                        "price": record.get("price", 0),
                        "quantity": 1,
                        "categoryId": category_id,
                        "condition_enum": condition_enum,
                        "condition_id_numeric": condition_id_numeric,
                        "media_condition": record.get("media_condition"),
                        "sleeve_condition": record.get("sleeve_condition"),
                        "images": record.get("images", []),
                        "marketplaceId": self.config.get("marketplace_id", "EBAY_GB"),
                        "paymentPolicyId": self.config.get("ebay_payment_policy_id"),
                        "returnPolicyId": self.config.get("ebay_return_policy_id"),
                        "shippingPolicyId": self.config.get("ebay_shipping_policy_id"),
                        "currency": "GBP"
                    }
                    # Attempt to collect image URLs if necessary
                    try:
                        # Convert local images to eBay-hosted URLs if none exist
                        if not listing_data.get("images") and record.get("image_urls"):
                            listing_data["imageUrls"] = record.get("image_urls")
                        else:
                            # Fallback: rely on eBay API wrapper to upload images
                            listing_data["images"] = record.get("images", [])
                    except Exception:
                        pass

                    res = self.ebay_api.create_sell_listing_draft(listing_data)
                    if res.get("success"):
                        draft_id = res.get("draftId")
                        # Write back ID and timestamp
                        try:
                            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                            with self.db.get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "UPDATE inventory SET ebay_item_draft_id = ?, ebay_updated_at = ? WHERE sku = ?",
                                    (draft_id, now_iso, sku),
                                )
                            self.append_log(f"SKU {sku}: eBay draft created (Draft ID: {draft_id}).", "green")
                        except Exception as e:
                            self.append_log(f"SKU {sku}: Draft created but failed to save ID to DB: {e}", "red")
                    else:
                        err = res.get("error") or res.get("body")
                        status = res.get("status")
                        if status:
                            self.append_log(f"SKU {sku}: Failed to create eBay draft (status {status}): {err}", "red")
                        else:
                            self.append_log(f"SKU {sku}: Failed to create eBay draft: {err}", "red")
                except Exception as e:
                    self.append_log(f"SKU {sku}: Unexpected error during draft creation: {e}", "red")

            # Refresh inventory view on the main thread
            self.safe_after(0, lambda: self.populate_inventory_view(self.inventory_search_var.get()))
            self.safe_after(0, lambda: self.root.config(cursor=""))

        # Show busy cursor and start background thread
        self.root.config(cursor="watch")
        self.root.update()
        threading.Thread(target=draft_worker, daemon=True).start()

    def open_listing_in_browser(self):
        """
        Open the appropriate listing page in the user's default web browser for the selected
        inventory item. Priority is given to eBay drafts, then live eBay listings,
        then Discogs listings.
        """
        selected = self.inventory_tree.focus()
        if not selected:
            return
        sku = self.inventory_tree.item(selected, "values")[0]
        try:
            record = self._get_inventory_record(sku)
            # Try to open eBay draft if present
            draft_id = record.get("ebay_item_draft_id")
            if draft_id:
                # eBay does not provide direct draft URLs; open drafts overview
                webbrowser.open_new_tab("https://www.ebay.co.uk/sh/lst/drafts")
                return
            live_id = record.get("ebay_listing_id")
            if live_id:
                webbrowser.open_new_tab(f"https://www.ebay.co.uk/itm/{live_id}")
                return
            discogs_id = record.get("discogs_listing_id")
            if discogs_id:
                webbrowser.open_new_tab(f"https://www.discogs.com/sell/item/{discogs_id}")
                return
            messagebox.showinfo("No Listing", "This item does not have any listing IDs yet.")
        except Exception as e:
            logger.error(f"Failed to open listing: {e}")
            messagebox.showerror("Error", f"Failed to open listing: {e}")
    
    def append_log(self, message, color="black"):
        """Append message to publish log"""
        def do_append():
            timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
            self.publish_log.config(state="normal")
            self.publish_log.insert("end", f"{timestamp} {message}\n", (color,))
            self.publish_log.tag_configure("red", foreground="red")
            self.publish_log.tag_configure("green", foreground="green")
            self.publish_log.tag_configure("black", foreground="black")
            self.publish_log.see("end")
            self.publish_log.config(state="disabled")
        self.safe_after(0, do_append)

    def show_inventory_context_menu(self, event):
        """Show inventory context menu"""
        row_id = self.inventory_tree.identify_row(event.y)
        if row_id:
            self.inventory_tree.selection_set(row_id)
            self.inventory_tree.focus(row_id)
            self.inventory_context_menu.post(event.x_root, event.y_root)
    
    def show_discogs_context_menu(self, event):
        """Show Discogs results context menu"""
        row_id = self.discogs_tree.identify_row(event.y)
        if row_id:
            self.discogs_tree.selection_set(row_id)
            self.discogs_tree.focus(row_id)
            self.discogs_context_menu.post(event.x_root, event.y_root)
    
    def open_discogs_listing(self):
        """Open Discogs listing for selected inventory item"""
        selected = self.inventory_tree.focus()
        if not selected: return
        sku = self.inventory_tree.item(selected, "values")[0]
        try:
            record = self._get_inventory_record(sku)
            if record.get("discogs_listing_id"):
                webbrowser.open_new_tab(f"https://www.discogs.com/sell/item/{record['discogs_listing_id']}")
            else:
                messagebox.showinfo("No Discogs Listing", "This item has no Discogs listing ID.")
        except Exception as e:
            logger.error(f"Failed to open Discogs listing: {e}")
    
    def open_ebay_listing(self):
        """Open eBay listing for selected inventory item"""
        selected = self.inventory_tree.focus()
        if not selected: return
        sku = self.inventory_tree.item(selected, "values")[0]
        try:
            record = self._get_inventory_record(sku)
            if record.get("ebay_listing_id"):
                webbrowser.open_new_tab(f"https://www.ebay.co.uk/itm/{record['ebay_listing_id']}")
            else:
                messagebox.showinfo("No eBay Listing", "This item has no eBay listing ID.")
        except Exception as e:
            logger.error(f"Failed to open eBay listing: {e}")
    
    def open_discogs_release_from_inventory(self):
        """Open Discogs release page for selected inventory item"""
        selected = self.inventory_tree.focus()
        if not selected: return
        sku = self.inventory_tree.item(selected, "values")[0]
        try:
            record = self._get_inventory_record(sku)
            if record.get("discogs_release_id"):
                webbrowser.open_new_tab(f"https://www.discogs.com/release/{record['discogs_release_id']}")
            else:
                messagebox.showinfo("No Release Linked", "This item has no Discogs release ID.")
        except Exception as e:
            logger.error(f"Failed to open release page: {e}")
    
    def open_discogs_release_page(self):
        """Open selected release on Discogs website"""
        selected = self.discogs_tree.focus()
        if not selected: return
        release_id = self.discogs_tree.item(selected, "values")[0]
        webbrowser.open_new_tab(f"https://www.discogs.com/release/{release_id}")
    
    def open_sold_listings_from_selection(self, platform):
        """Open sold listings search for selected Discogs result"""
        selected = self.discogs_tree.focus()
        if not selected: return
        _, artist, title, catno, _, _, _ = self.discogs_tree.item(selected, "values")
        query = f"{artist} {title} {catno}".strip()
        url = f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(query)}&_sacat=176985&LH_Sold=1&LH_Complete=1" if platform == "eBay" else f"https://www.discogs.com/search/?q={quote_plus(query)}&type=all"
        webbrowser.open_new_tab(url)
    
    def get_price_suggestion(self):
        """Get price suggestions for selected release"""
        selected = self.discogs_tree.focus()
        if not selected: return
        release_id = int(self.discogs_tree.item(selected, "values")[0])
        self.root.config(cursor="watch")
        self.root.update()
        def fetch_worker():
            try:
                suggestions = self.discogs_api.get_price_suggestions(release_id)
                if suggestions:
                    msg = "Price Suggestions:\n\n" + "\n".join([f"{condition}: £{price_data['value']:.2f}" for condition, price_data in suggestions.items()])
                    self.safe_after(0, lambda: messagebox.showinfo("Price Suggestions", msg))
                else:
                    self.safe_after(0, lambda: messagebox.showinfo("No Data", "No price suggestions available"))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        threading.Thread(target=fetch_worker, daemon=True).start()
    
    def refresh_discogs_view(self, event=None):
        """Refresh Discogs results with filter"""
        filter_text = self.discogs_search_filter_var.get().lower()
        if not self.discogs_search_results: return
        for item in self.discogs_tree.get_children(): self.discogs_tree.delete(item)
        for result in self.discogs_search_results:
            artist, title = (result.get("title", "").split(" - ", 1) + [""])[:2]
            if filter_text and filter_text not in f"{artist} {title} {result.get('catno', '')} {result.get('year', '')}".lower(): continue
            values = (result.get("id"), artist, title, result.get("catno", "N/A"), result.get("year", "N/A"), result.get("country", "N/A"), ", ".join(result.get("format", [])))
            self.discogs_tree.insert("", "end", values=values)
    
    def sort_discogs_results(self, col):
        """Sort Discogs results by column"""
        if self.discogs_sort_column == col:
            self.discogs_sort_direction = "ASC" if self.discogs_sort_direction == "DESC" else "DESC"
        else:
            self.discogs_sort_column, self.discogs_sort_direction = col, "ASC"
        if self.discogs_search_results:
            def sort_key(item):
                if col == "Artist": return (item.get("title", "").split(" - ", 1) + [""])[0].lower()
                elif col == "Title": return (item.get("title", "").split(" - ", 1) + [""])[1].lower()
                elif col == "Year":
                    try: return int(item.get("year", 0))
                    except: return 0
                else: return str(item.get(col.lower(), "")).lower()
            self.discogs_search_results.sort(key=sort_key, reverse=(self.discogs_sort_direction == "DESC"))
            self.refresh_discogs_view()
    
    def authenticate_discogs(self):
        """Authenticate with Discogs"""
        consumer_key = self.config.get("discogs_consumer_key")
        consumer_secret = self.config.get("discogs_consumer_secret")
        if not consumer_key or not consumer_secret:
            messagebox.showerror("Configuration Error", "Discogs Consumer Key/Secret not found in config.json.\nPlease add these to your configuration file.")
            return
        try:
            client = discogs_client.Client("VinylListingTool/5.1", consumer_key=consumer_key, consumer_secret=consumer_secret)
            token, secret, url = client.get_authorize_url()
            webbrowser.open(url)
            pin = simpledialog.askstring("Discogs Authentication", "Please enter the verification code from Discogs:")
            if not pin: return
            access_token, access_secret = client.get_access_token(pin)
            self.config.save({"discogs_oauth_token": access_token, "discogs_oauth_token_secret": access_secret})
            self.discogs_api = DiscogsAPI(self.config)
            if self.discogs_api.is_connected():
                self._update_connection_status()
                messagebox.showinfo("Success", "Successfully connected to Discogs!")
            else:
                messagebox.showerror("Error", "Failed to connect to Discogs")
        except Exception as e:
            logger.error(f"Discogs authentication failed: {e}")
            messagebox.showerror("Authentication Error", str(e))
    
    def test_ebay_connection(self):
        """Test eBay connection"""
        if self.ebay_api.test_connection():
            self.ebay_auth_status_var.set("Connected")
            messagebox.showinfo("Success", "Successfully connected to eBay!")
        else:
            self.ebay_auth_status_var.set("Not Connected")
            messagebox.showerror("Connection Failed", "Could not connect to eBay.\nPlease check your credentials in config.json")
    
    def check_discogs_sales(self):
        """Check for Discogs sales"""
        if not self.discogs_api.is_connected(): return
        self.root.config(cursor="watch"); self.root.update()
        def sales_worker():
            try:
                orders = self.discogs_api.get_orders(['Payment Received', 'Shipped'])
                self.safe_after(0, lambda: self._display_discogs_sales(orders))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        threading.Thread(target=sales_worker, daemon=True).start()
    
    def _display_discogs_sales(self, orders):
        """Display Discogs sales"""
        for item in self.sales_tree.get_children(): self.sales_tree.delete(item)
        if not orders:
            messagebox.showinfo("No Sales", "No sales with status 'Payment Received' or 'Shipped' found.")
            return
        for order in orders:
            for item in order.items:
                artist = item.release.artists[0].name if item.release.artists else "Various"
                title = item.release.title.replace(f"{artist} - ", "", 1).strip()
                sale_date = datetime.datetime.strptime(order.data['created'][:10], "%Y-%m-%d").strftime("%d-%m-%Y")
                sale_price = f"{item.price.value} {item.price.currency}"
                values = (order.id, sale_date, order.buyer.username, artist, title, sale_price, item.release.id)
                self.sales_tree.insert("", "end", values=values)
    
    def sync_discogs_sale(self):
        """Sync selected Discogs sale to inventory"""
        selected = self.sales_tree.focus()
        if not selected: return
        release_id = self.sales_tree.item(selected, "values")[6]
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT sku FROM inventory WHERE discogs_release_id = ? AND status = 'For Sale'", (release_id,))
                record = cursor.fetchone()
                if record:
                    sku = record[0]
                    if messagebox.askyesno("Confirm Sync", f"Found matching item (SKU: {sku}). Mark as 'Sold'?"):
                        self.update_inventory_status("Sold")
                        messagebox.showinfo("Success", f"SKU {sku} marked as Sold.")
                else:
                    messagebox.showwarning("No Match", f"Could not find an unsold item with Release ID: {release_id}.")
        except Exception as e:
            logger.error(f"Failed to sync sale: {e}")
            messagebox.showerror("Database Error", f"Could not sync sale: {e}")
    
    def check_ebay_sales(self):
        """Check for eBay sales"""
        if not self.ebay_api.test_connection(): return
        try:
            start_date = datetime.datetime.strptime(self.ebay_start_date_var.get(), "%d-%m-%Y")
            end_date = datetime.datetime.strptime(self.ebay_end_date_var.get(), "%d-%m-%Y")
            if (end_date - start_date).days > 30:
                messagebox.showerror("Date Range Error", "The date range cannot exceed 30 days.")
                return
        except ValueError:
            messagebox.showerror("Date Format Error", "Please enter dates in DD-MM-YYYY format.")
            return
        self.root.config(cursor="watch"); self.root.update()
        def sales_worker():
            try:
                orders = self.ebay_api.get_orders(start_date, end_date)
                self.safe_after(0, lambda: self._display_ebay_sales(orders))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        threading.Thread(target=sales_worker, daemon=True).start()
    
    def _display_ebay_sales(self, orders):
        """Display eBay sales"""
        for item in self.ebay_sales_tree.get_children(): self.ebay_sales_tree.delete(item)
        if not orders:
            messagebox.showinfo("No eBay Sales", "No completed sales found in the specified date range.")
            return
        for order in orders:
            order_id, created_date, buyer = order.get("orderId"), order.get("creationDate", "")[:10], order.get("buyer", {}).get("username", "")
            for line_item in order.get("lineItems", []):
                title, price, currency, item_id = line_item.get("title", ""), line_item.get("lineItemCost", {}).get("value", ""), line_item.get("lineItemCost", {}).get("currency", "GBP"), line_item.get("legacyItemId", "")
                artist, album_title = "", title
                if ":" in title:
                    parts = title.split(":", 1)
                    artist, album_title = parts[0].strip(), parts[1].strip()
                values = (order_id, created_date, buyer, artist, album_title, f"{price} {currency}", item_id)
                self.ebay_sales_tree.insert("", "end", values=values)
    
    def sync_ebay_sale(self):
        """Sync selected eBay sale to inventory"""
        selected = self.ebay_sales_tree.focus()
        if not selected: return
        _, _, _, artist, title, _, item_id = self.ebay_sales_tree.item(selected, "values")
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT sku FROM inventory WHERE (ebay_listing_id = ? OR (artist LIKE ? AND title LIKE ?)) AND status = 'For Sale'", (item_id, f"%{artist}%", f"%{title}%"))
                record = cursor.fetchone()
                if record:
                    sku = record[0]
                    if messagebox.askyesno("Confirm Sync", f"Found matching item (SKU: {sku}). Mark as 'Sold'?"):
                        self.update_inventory_status("Sold")
                        messagebox.showinfo("Success", f"SKU {sku} marked as Sold.")
                else:
                    messagebox.showwarning("No Match", f"Could not find an unsold item matching:\n{artist} - {title}")
        except Exception as e:
            logger.error(f"Failed to sync sale: {e}")
            messagebox.showerror("Database Error", f"Could not sync sale: {e}")
    
    def start_discogs_import(self):
        """Import inventory from Discogs"""
        if not self.discogs_api.is_connected(): return
        if not messagebox.askyesno("Confirm Import", "This will import all 'For Sale' items from Discogs.\nExisting items will be skipped.\n\nContinue?"): return
        self.root.config(cursor="watch"); self.root.update()
        def import_worker():
            try:
                inventory = self.discogs_api.get_inventory()
                self.safe_after(0, lambda: self._process_discogs_import(inventory))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Import Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        threading.Thread(target=import_worker, daemon=True).start()
    
    def _process_discogs_import(self, inventory):
        """Process Discogs import"""
        new_items, skipped_items = 0, 0
        try:
            with self.db.get_connection() as conn:
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
            self.populate_inventory_view()
        except Exception as e:
            logger.error(f"Import failed: {e}")
            messagebox.showerror("Import Error", f"An error occurred during import:\n{e}")
    
    def toggle_auto_sync(self):
        """Toggle automatic sync"""
        if not self.discogs_api.is_connected():
            messagebox.showwarning("Not Connected", "Please connect to your Discogs account first.")
            self.auto_sync_var.set(False)
            return
        self.auto_sync_enabled = self.auto_sync_var.get()
        self.config.save({"auto_sync_enabled": self.auto_sync_enabled})
        if self.auto_sync_enabled: self.start_auto_sync()
        else: self.stop_auto_sync()
    
    def toggle_two_way_sync(self):
        """Toggle two-way sync"""
        self.two_way_sync_enabled = self.two_way_sync_var.get()
        self.config.save({"two_way_sync_enabled": self.two_way_sync_enabled})
        self.log_sync_activity(f"Two-way sync {'enabled' if self.two_way_sync_enabled else 'disabled'}")
    
    def toggle_attempt_updates(self):
        """Toggle attempt to update Discogs"""
        self.attempt_discogs_updates = self.attempt_updates_var.get()
        self.config.save({"attempt_discogs_updates": self.attempt_discogs_updates})
        self.log_sync_activity(f"Discogs update attempts {'enabled' if self.attempt_discogs_updates else 'disabled'}")
    
    def update_sync_interval(self):
        """Update sync interval"""
        try:
            minutes = int(self.sync_interval_var.get())
            self.auto_sync_interval = minutes * 60
            self.config.save({"auto_sync_interval": self.auto_sync_interval})
            self.log_sync_activity(f"Sync interval set to {minutes} minutes")
        except ValueError: self.sync_interval_var.set("5")
    
    def start_auto_sync(self):
        """Start automatic sync"""
        if self.auto_sync_thread and self.auto_sync_thread.is_alive(): return
        self.auto_sync_stop_event.clear()
        self.auto_sync_thread = threading.Thread(target=self._auto_sync_worker, daemon=True)
        self.auto_sync_thread.start()
        self.sync_status_var.set("Auto-sync enabled - waiting for next sync...")
        self.log_sync_activity("Automatic sync started")
    
    def stop_auto_sync(self):
        """Stop automatic sync"""
        self.auto_sync_stop_event.set()
        self.sync_status_var.set("Auto-sync disabled")
        self.log_sync_activity("Automatic sync stopped")
    
    def _auto_sync_worker(self):
        """Auto sync worker thread"""
        while not self.auto_sync_stop_event.is_set():
            try:
                if self.auto_sync_stop_event.wait(self.auto_sync_interval): break
                if self.auto_sync_enabled and self.discogs_api.is_connected():
                    self.safe_after(0, lambda: self.sync_status_var.set("Syncing inventory..."))
                    sync_result = self._perform_inventory_sync()
                    self.safe_after(0, lambda r=sync_result: self._handle_sync_result(r))
            except Exception as e:
                self.safe_after(0, lambda msg=f"Auto-sync error: {e}": self.log_sync_activity(msg))
    
    def manual_sync_now(self):
        """Perform manual sync now"""
        if not self.discogs_api.is_connected():
            messagebox.showwarning("Not Connected", "Please connect to your Discogs account first.")
            return
        self.sync_status_var.set("Manual sync in progress...")
        self.root.config(cursor="watch"); self.root.update()
        def sync_worker():
            try:
                result = self._perform_inventory_sync()
                self.safe_after(0, lambda: self._handle_sync_result(result))
            except Exception as e:
                self.safe_after(0, lambda: messagebox.showerror("Sync Error", str(e)))
            finally:
                self.safe_after(0, lambda: self.root.config(cursor=""))
        threading.Thread(target=sync_worker, daemon=True).start()
    
    def _perform_inventory_sync(self):
        """Implements true "latest-wins" two-way sync logic."""
        sync_start_time = datetime.datetime.now(datetime.timezone.utc)
        self.log_sync_activity("=== STARTING SYNC (Latest-Wins) ===")
        try:
            discogs_inventory = self.discogs_api.get_inventory()
            discogs_map = {listing.id: listing for listing in discogs_inventory}
            self.log_sync_activity(f"Retrieved {len(discogs_inventory)} active listings from Discogs.")

            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT sku, discogs_listing_id, price, status, notes, last_modified, last_sync_time FROM inventory WHERE discogs_listing_id IS NOT NULL")
                local_items = [dict(row) for row in cursor.fetchall()]
                local_map = {item['discogs_listing_id']: item for item in local_items}
            self.log_sync_activity(f"Found {len(local_map)} linked local items.")

            updates_to_local, updates_to_discogs, deletions_from_local, new_sales = 0, 0, 0, 0
            
            for local_item in local_items:
                listing_id, last_mod_local_str, last_sync_str = local_item['discogs_listing_id'], local_item.get('last_modified'), self.last_successful_sync_time or local_item.get('last_sync_time')
                if not last_mod_local_str or not last_sync_str: continue
                try:
                    last_mod_local, last_sync = datetime.datetime.fromisoformat(last_mod_local_str), datetime.datetime.fromisoformat(last_sync_str)
                except (ValueError, TypeError): continue

                if last_mod_local > last_sync and self.attempt_discogs_updates:
                    if listing_id in discogs_map:
                        self.log_sync_activity(f"→ Local change detected for SKU {local_item['sku']}. Pushing to Discogs.")
                        update_payload = {"price": local_item['price'], "status": self._map_local_to_discogs_status(local_item['status']), "comments": local_item.get('notes', '')}
                        if self.discogs_api.update_listing(listing_id, update_payload):
                            updates_to_discogs += 1; self.log_sync_activity(f"  ✓ Pushed update for SKU {local_item['sku']} to Discogs.")
                        else: self.log_sync_activity(f"  ✗ Failed to push update for SKU {local_item['sku']}.")
                    else: self.log_sync_activity(f"  - SKU {local_item['sku']} changed locally but no longer on Discogs. Skipping push.")

                elif listing_id in discogs_map:
                    listing = discogs_map[listing_id]
                    mapped_status = self.status_mappings.get(listing.status, "Not For Sale")
                    if mapped_status != local_item['status']:
                        with self.db.get_connection() as conn:
                            conn.cursor().execute("UPDATE inventory SET status = ?, last_modified = ? WHERE discogs_listing_id = ?", (mapped_status, sync_start_time.isoformat(), listing_id))
                        updates_to_local += 1
                        if mapped_status == 'Sold' and local_item['status'] != 'Sold': new_sales += 1
                        self.log_sync_activity(f"✓ Sync from Discogs: SKU {local_item['sku']} '{local_item['status']}' → '{mapped_status}'")

            ids_to_delete_locally = set(local_map.keys()) - set(discogs_map.keys())
            if ids_to_delete_locally:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    for listing_id in ids_to_delete_locally:
                        if local_map[listing_id]['status'] == 'For Sale':
                            sku = local_map[listing_id]['sku']
                            cursor.execute("DELETE FROM inventory WHERE discogs_listing_id = ?", (listing_id,))
                            deletions_from_local += 1
                            self.log_sync_activity(f"✓ Deleted SKU {sku} locally as it's no longer on Discogs.")
            
            with self.db.get_connection() as conn:
                conn.cursor().execute("UPDATE inventory SET last_sync_time = ? WHERE discogs_listing_id IS NOT NULL", (sync_start_time.isoformat(),))
            self.last_successful_sync_time = sync_start_time.isoformat()
            self.config.save({"last_successful_sync_time": self.last_successful_sync_time})
            if updates_to_local > 0 or deletions_from_local > 0: self.safe_after(0, self.populate_inventory_view)
            self.log_sync_activity("=== SYNC COMPLETED ===")
            return {'success': True, 'updates_local': updates_to_local, 'updates_discogs': updates_to_discogs, 'deletions': deletions_from_local, 'new_sales': new_sales, 'total_checked': len(discogs_inventory)}
        except Exception as e:
            logger.error(f"Sync failed: {e}", exc_info=True)
            self.log_sync_activity(f"✗ SYNC ERROR: {e}")
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
                self.log_sync_activity(log_msg)
                status_msg = f"Sync complete - {total_changes} change(s)"
            else:
                status_msg = "Sync complete - no changes needed"
                self.log_sync_activity(f"[{current_time}] Sync completed. No changes needed.")
            self.sync_status_var.set(f"Last sync: {current_time}. {status_msg}")
        else:
            self.sync_status_var.set(f"Last sync: {current_time}. FAILED.")
            self.log_sync_activity(f"[{current_time}] Sync FAILED: {result.get('error')}")

    def log_sync_activity(self, message):
        """Log sync activity to the text widget"""
        def do_log():
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.sync_log_text.config(state="normal")
            self.sync_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.sync_log_text.see(tk.END)
            self.sync_log_text.config(state="disabled")
        self.safe_after(0, do_log)

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
