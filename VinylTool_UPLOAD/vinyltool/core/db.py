from __future__ import annotations
import sqlite3, contextlib, logging, os, sys, json, threading, time, re
from contextlib import contextmanager
from pathlib import Path
from vinyltool.core.paths import path_db
from vinyltool.core.config import Config  # may be referenced by the class
from vinyltool.core.logging import setup_logging  # may be referenced by the class
logger = setup_logging('db')

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