from __future__ import annotations
import requests, json, logging, sys, os, time, re
from vinyltool.core.logging import setup_logging
from vinyltool.core.config import Config
import secrets
import urllib.parse
import urllib.request
import json
import datetime

import hmac
import hashlib
import base64
logger = setup_logging('discogs')
from tkinter import messagebox
import discogs_client


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
    
        """Initialize discogs_client.Client from config; supports personal token or OAuth pair."""
    
        cfg = Config().load()
    
        consumer_key = None or ""
    
        consumer_secret = None or ""
    
        user_token = cfg.get("discogs_token") or ""
    
        oauth_token = None or ""
    
        oauth_secret = cfg.get("discogs_oauth_token_secret") or ""
    
        ua = cfg.get("discogs_user_agent") or "VinylTool/1.0"
    
    
    
        try:
    
            if user_token:
    
                # Personal token flow
    
                self.client = discogs_client.Client('GrooveDeck/1.0', user_token=cfg.get('discogs_token'))
    
            elif consumer_key and consumer_secret and oauth_token and oauth_secret:
    
                # OAuth flow
    
                self.client = discogs_client.Client('GrooveDeck/1.0', user_token=cfg.get('discogs_token'))
    
            else:
    
                raise RuntimeError("Missing Discogs credentials (need personal token or (ck, cs, oauth_token, oauth_secret)).")
    
    
    
            me = self.client.identity()
    
            self.connected_username = getattr(me, "username", None)
    
            logger.info(f"Connected to Discogs as: {self.connected_username or 'unknown'}")
    
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
            # Use personal access token for authentication
            token = self.config.get('discogs_token')
            if not token:
                logger.error('No Discogs token found in config')
                return None
            
            url = 'https://api.discogs.com/marketplace/listings'
            headers = {
                'Authorization': f'Discogs token={token}',
                'User-Agent': self.config.get('discogs_user_agent', 'VinylListingTool/5.1'),
                'Content-Type': 'application/json'
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
            token = self.config.get('discogs_token')
            if not token:
                logger.error('No Discogs token found in config')
                return False
            
            url = f'https://api.discogs.com/marketplace/listings/{listing_id}'
            headers = {
                'Authorization': f'Discogs token={token}',
                'User-Agent': self.config.get('discogs_user_agent', 'VinylListingTool/5.1'),
                'Content-Type': 'application/json'
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
        base_string = f"{method}&{urllib.parse.quote(str(url), safe='')}&{urllib.parse.quote(str(param_string), safe='')}"
        signing_key = f"{urllib.parse.quote(str(consumer_secret) if consumer_secret else '', safe='')}&{urllib.parse.quote(str(token_secret) if token_secret else '', safe='')}"
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


