from __future__ import annotations
import base64
import requests, json, logging, sys, os, time, re
from vinyltool.core.logging import setup_logging
logger = setup_logging('ebay')
from vinyltool.core.config import Config

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


    def upsert_offer_and_publish(self, listing_data: dict) -> dict:
        """
        Create or update an offer for the given SKU using Sell Inventory API, then publish it.
        
        CRITICAL: Now includes Inventory Item creation BEFORE offer (this was missing!)
        
        - Forces en-GB headers (fixes 25709)
        - Requires merchantLocationKey + payment/return/fulfillment policy IDs
        - Creates inventory item with full product block first
        - Then creates/updates offer with condition enum
        - Then publishes
        
        Returns: {success: bool, offerId?: str, listingId?: str, error?: str}
        """
        import json
        import logging
        import requests
        import time
        
        logger = logging.getLogger("ebay")
        
        sku = (listing_data or {}).get("sku")
        if not sku:
            logger.error("[upsert] No SKU provided")
            return {"success": False, "error": "Missing SKU"}

        market = self.config.get("marketplace_id", "EBAY_GB")
        payment_id = self.config.get("ebay_payment_policy_id")
        return_id = self.config.get("ebay_return_policy_id")
        fulfillment_id = self.config.get("ebay_shipping_policy_id") or self.config.get("ebay_fulfillment_policy_id")
        mlk = self.config.get("ebay_merchant_location_key", "KIDDERMINSTER_MAIN")
        
        missing = [n for n,v in [("merchantLocationKey", mlk), ("paymentPolicyId", payment_id), ("returnPolicyId", return_id), ("fulfillmentPolicyId", fulfillment_id)] if not v]
        if missing:
            msg = f"Missing config: {', '.join(missing)}"
            logger.error(f"[upsert] {msg}")
            return {"success": False, "error": msg}

        token = self.get_access_token()
        base = f"{self.base_url}/sell/inventory/v1"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": "en-GB",
            "Content-Language": "en-GB",
        }

        # ===== STEP 0: UPLOAD IMAGES TO EBAY IF NEEDED =====
    # Get image paths from listing_data
    local_images = listing_data.get("images") or listing_data.get("image_paths") or []
    # Use uploaded eBay URLs (already set in STEP 0)
    
    # If we have local paths but no eBay URLs, upload them
    if local_images and not ebay_image_urls:
        logger.info(f"[images] SKU {sku}: Uploading {len(local_images)} local images to eBay")
        ebay_image_urls = []
        for img_path in local_images[:12]:  # eBay allows max 12 images
            try:
                if img_path and isinstance(img_path, str):
                    uploaded_url = self.upload_image(img_path, sku)
                    if uploaded_url:
                        ebay_image_urls.append(uploaded_url)
                        logger.info(f"[images] Uploaded: {uploaded_url}")
            except Exception as e:
                logger.warning(f"[images] Failed to upload {img_path}: {e}")
        
        logger.info(f"[images] SKU {sku}: Successfully uploaded {len(ebay_image_urls)} images")
    
    # ===== STEP 1: CREATE/UPDATE INVENTORY ITEM (THIS WAS MISSING!) =====
        category_id = str(listing_data.get("categoryId") or "176985")
        media_cond = listing_data.get("media_condition") or "Very Good"
        sleeve_cond = listing_data.get("sleeve_condition") or "Very Good"
        
        from vinyltool.core.constants import EBAY_INVENTORY_CONDITION_MAP
        condition_enum = EBAY_INVENTORY_CONDITION_MAP.get(media_cond, "USED_GOOD")
        
        description = listing_data.get("description") or "Vinyl LP"
        title = listing_data.get("title") or "Vinyl Record"
        price_val = listing_data.get("price", 0)
        if isinstance(price_val, (int, float)):
            price_str = f"{price_val:.2f}"
        else:
            price_str = str(price_val).strip() if price_val else "9.99"
        
        inventory_item = {
            "condition": condition_enum,
            "product": {
                "title": title[:80],
                "description": description[:3900],
                "aspects": {
                    "Media Condition": [media_cond],
                    "Sleeve Condition": [sleeve_cond],
                    "Format": [listing_data.get("format", "LP") or "LP"],
                    "Artist": [listing_data.get("artist") or "Unknown Artist"],
                    "Release Title": [listing_data.get("release_title") or listing_data.get("title") or "Unknown Album"],
                    "Release Year": [str(listing_data.get("year") or listing_data.get("release_year") or "Unknown")],
                },
                "imageUrls": listing_data.get("imageUrls") or []
            },
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": listing_data.get("quantity", 1),
                    "locationKey": mlk
                }
            }
        }
        
        # Debug: Log what year data we have
        year_val = listing_data.get("year") or listing_data.get("release_year") or ""
        logger.info(f"[inventory] SKU {sku}: year={year_val}, artist={listing_data.get('artist')}, title={listing_data.get('title')}")
        logger.info(f"[inventory] SKU {sku}: Creating with condition={condition_enum}")
        
        try:
            r_inv = requests.put(
                f"{base}/inventory_item/{sku}",
                headers=headers,
                json=inventory_item,
                timeout=60
            )
            logger.info(f"[inventory] SKU {sku}: Response {r_inv.status_code}")
            
            if r_inv.status_code not in (200, 201, 204):
                err = r_inv.text[:200]
                logger.error(f"[inventory] SKU {sku}: FAILED {r_inv.status_code}: {err}")
                return {"success": False, "error": f"Inventory item failed: {err}"}
            
            logger.info(f"[inventory] SKU {sku}: Created successfully")
            
        except Exception as e:
            logger.error(f"[inventory] SKU {sku}: Exception: {e}")
            return {"success": False, "error": f"Inventory exception: {str(e)}"}
        
        time.sleep(1.5)

        # ===== STEP 2: CREATE/UPDATE OFFER =====
        offer_body = {
            "sku": sku,
            "marketplaceId": market,
            "format": "FIXED_PRICE",
            "availableQuantity": listing_data.get("quantity", 1),
            "categoryId": category_id,
            "listingDescription": description,
            "pricingSummary": {"price": {"currency": "GBP", "value": price_str}},
            "merchantLocationKey": mlk,
            "listingPolicies": {
                "paymentPolicyId": payment_id,
                "returnPolicyId": return_id,
                "fulfillmentPolicyId": fulfillment_id,
            },
            "listingDuration": "GTC",
            "quantityLimitPerBuyer": 1,
        }

        logger.info(f"[offer] Upsert payload (sanitized): {json.dumps(offer_body, ensure_ascii=False)}")
        
        try:
            r = requests.get(f"{base}/offer?sku={sku}", headers=headers, timeout=30)
            r.raise_for_status()
            offers = (r.json().get("offers") or [])
            offer_id = None
            if offers:
                o0 = offers[0]
                offer_id = o0.get("offerId") or (o0.get("offer") or {}).get("offerId")
                logger.info(f"[offer] SKU {sku}: Found offer {offer_id}")
        except Exception as e:
            logger.warning(f"[offer] SKU {sku}: Lookup failed: {e}")
            offers = []
            offer_id = None

        try:
            if offer_id:
                logger.info(f"[offer] SKU {sku}: Updating offer {offer_id}")
                pu = requests.put(f"{base}/offer/{offer_id}", headers=headers, json=offer_body, timeout=60)
                if pu.status_code not in (200, 201, 204):
                    logger.error(f"[offer] SKU {sku}: Update failed {pu.status_code}: {pu.text[:200]}")
                    return {"success": False, "error": f"Offer update failed: {pu.text[:200]}"}
                logger.info(f"[offer] SKU {sku}: Updated")
            else:
                logger.info(f"[offer] SKU {sku}: Creating new offer")
                pc = requests.post(f"{base}/offer", headers=headers, json=offer_body, timeout=60)
                if pc.status_code not in (200, 201):
                    logger.error(f"[offer] SKU {sku}: Create failed {pc.status_code}: {pc.text[:200]}")
                    return {"success": False, "error": f"Offer create failed: {pc.text[:200]}"}
                offer_id = pc.json().get("offerId") or (pc.json().get("offer") or {}).get("offerId")
                if not offer_id:
                    logger.error(f"[offer] SKU {sku}: No offerId returned")
                    return {"success": False, "error": "Offer created but no ID"}
                logger.info(f"[offer] SKU {sku}: Created {offer_id}")

        except Exception as e:
            logger.error(f"[offer] SKU {sku}: Exception: {e}")
            return {"success": False, "error": f"Offer exception: {str(e)}"}

        # ===== STEP 3: PUBLISH =====
        logger.info(f"[offer] SKU {sku}: Publishing {offer_id}")
        try:
            pb = requests.post(f"{base}/offer/{offer_id}/publish", headers=headers, timeout=30)
            if pb.status_code not in (200, 201):
                logger.error(f"[offer] SKU {sku}: Publish failed {pb.status_code}: {pb.text[:200]}")
                return {"success": False, "error": f"Publish failed: {pb.text[:200]}"}
            
            listing_id = None
            try:
                listing_id = pb.json().get("listingId")
            except Exception:
                pass

            logger.info(f"[offer] SKU {sku}: Published, listingId={listing_id}")
            res = {"success": True, "offerId": offer_id}
            if listing_id:
                res["listingId"] = listing_id
            return res
            
        except Exception as e:
            logger.error(f"[offer] SKU {sku}: Publish exception: {e}")
            return {"success": False, "error": f"Publish exception: {str(e)}"}

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
            html = _re.sub(r"\\s+", " ", html).strip()
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

    def create_draft_listing(self, listing_data):

        """

        Compatibility wrapper: use Inventory API offer upsert+publish and return a familiar shape.

        """

        res = self.upsert_offer_and_publish(listing_data)

        if res.get("success"):

            return {"success": True, "offerId": res.get("offerId"), "listingId": res.get("listingId")}

        return {"success": False, "error": res.get("error")}


# --- appended: robust binder for upsert_offer_and_publish ---
try:
    # Bind to any plausible class name exported by this module
    _eba_cls = None
    for _name in ("EbayAPI", "EBayAPI", "EbayApi", "EBayApi"):
        _eba_cls = globals().get(_name)
        if _eba_cls:
            try:
                setattr(_eba_cls, "upsert_offer_and_publish", _eba_upsert_offer_and_publish)
                break
            except Exception:
                pass
except Exception:
    pass
# --- end robust binder ---


# --- appended: robust Inventory API offer upsert + publish (function) ---
def _eba_upsert_offer_and_publish(self, listing_data: dict) -> dict:
    """
    CLEAN VERSION: Create inventory item, upload images, create offer, then publish.
    Returns: {success: bool, offerId?: str, listingId?: str, error?: str}
    """
    import json, logging, time
    try:
        import requests
    except Exception as e:
        return {"success": False, "error": f"requests import failed: {e}"}

    logger = logging.getLogger("ebay")

    sku = (listing_data or {}).get("sku")
    if not sku:
        return {"success": False, "error": "Missing SKU"}

    # Get config values
    market = self.config.get("marketplace_id", "EBAY_GB")
    payment_id = self.config.get("ebay_payment_policy_id")
    return_id = self.config.get("ebay_return_policy_id")
    fulfillment_id = self.config.get("ebay_shipping_policy_id") or self.config.get("ebay_fulfillment_policy_id")
    mlk = self.config.get("ebay_merchant_location_key")

    # Validate required config
    missing = []
    if not mlk: missing.append("merchantLocationKey")
    if not payment_id: missing.append("paymentPolicyId")
    if not return_id: missing.append("returnPolicyId")
    if not fulfillment_id: missing.append("fulfillmentPolicyId")
    
    if missing:
        msg = f"Missing config: {', '.join(missing)}"
        logger.error(f"[offer] {msg}")
        return {"success": False, "error": msg}

    # Get auth token
    try:
        token = self.get_access_token()
    except Exception as e:
        return {"success": False, "error": f"Auth failed: {e}"}

    base = f"{self.base_url}/sell/inventory/v1"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "en-GB",
        "Content-Language": "en-GB",
    }

    # ===== STEP 0: HANDLE IMAGES =====
    ebay_image_urls = []
    
    # First check if we already have eBay URLs
    existing_urls = listing_data.get("imageUrls") or listing_data.get("image_urls") or []
    if existing_urls:
        ebay_image_urls = list(existing_urls)
        logger.info(f"[images] SKU {sku}: Using {len(ebay_image_urls)} existing eBay URLs")
    else:
        # Check for local images to upload
        local_images = listing_data.get("images") or listing_data.get("image_paths") or []
        if local_images:
            logger.info(f"[images] SKU {sku}: Uploading {len(local_images)} local images")
            for img_path in local_images[:12]:
                try:
                    if img_path and isinstance(img_path, str) and hasattr(self, 'upload_image'):
                        uploaded_url = self.upload_image(img_path, sku)
                        if uploaded_url:
                            ebay_image_urls.append(uploaded_url)
                            logger.info(f"[images] Uploaded: {uploaded_url}")
                except Exception as e:
                    logger.warning(f"[images] Failed to upload {img_path}: {e}")
            
            logger.info(f"[images] SKU {sku}: Successfully uploaded {len(ebay_image_urls)} images")

    # ===== STEP 1: CREATE/UPDATE INVENTORY ITEM =====
    category_id = str(listing_data.get("categoryId") or "176985")
    media_cond = listing_data.get("media_condition") or "Very Good"
    sleeve_cond = listing_data.get("sleeve_condition") or "Very Good"
    
    from vinyltool.core.constants import EBAY_INVENTORY_CONDITION_MAP
    condition_enum = EBAY_INVENTORY_CONDITION_MAP.get(media_cond, "USED_GOOD")
    
    full_html_description = listing_data.get("description") or "Vinyl LP"
    title = listing_data.get("title") or "Vinyl Record"
    
    # Create plain text summary for inventory item (eBay limit: 4000 chars)
    import re as _re
    plain_summary = _re.sub(r'<[^>]+>', ' ', full_html_description)
    plain_summary = _re.sub(r'\s+', ' ', plain_summary).strip()[:3900]
    
    # Build product dict
    product_dict = {
        "title": title[:80],
        "description": plain_summary,
        "aspects": {
            "Media Condition": [media_cond],
            "Sleeve Condition": [sleeve_cond],
            "Format": [listing_data.get("format", "LP") or "LP"],
            "Artist": [listing_data.get("artist") or "Unknown Artist"],
            "Release Title": [listing_data.get("release_title") or listing_data.get("title") or "Unknown Album"],
            "Release Year": [str(listing_data.get("year") or listing_data.get("release_year") or "Unknown")],
        }
    }
    
    # Only add imageUrls if we have them
    if ebay_image_urls:
        product_dict["imageUrls"] = ebay_image_urls
    
    inventory_item = {
            "condition": condition_enum,
        "product": product_dict,
        "availability": {
            "shipToLocationAvailability": {
                "quantity": listing_data.get("quantity", 1)
            }
        }
    }
    
    logger.info(f"[inventory] SKU {sku}: Creating with condition={condition_enum}, images={len(ebay_image_urls)}")
    
    try:
        r_inv = requests.put(
            f"{base}/inventory_item/{sku}",
            headers=headers,
            json=inventory_item,
            timeout=60
        )
        logger.info(f"[inventory] SKU {sku}: Response {r_inv.status_code}")
        
        if r_inv.status_code not in (200, 201, 204):
            err = r_inv.text[:500]
            logger.error(f"[inventory] SKU {sku}: FAILED {r_inv.status_code}: {err}")
            return {"success": False, "error": f"Inventory item failed: {err}"}
        
        logger.info(f"[inventory] SKU {sku}: Created successfully")
        
    except Exception as e:
        logger.error(f"[inventory] SKU {sku}: Exception: {e}")
        return {"success": False, "error": f"Inventory exception: {str(e)}"}
    
    time.sleep(1.5)

    # ===== STEP 2: CREATE/UPDATE OFFER =====
    price = listing_data.get("price")
    if isinstance(price, (int, float)):
        price_val = f"{price:.2f}"
    elif isinstance(price, str) and price.strip():
        price_val = price.strip()
    else:
        price_val = "9.99"

    offer_body = {
        "sku": sku,
        "marketplaceId": market,
        "format": "FIXED_PRICE",
        "availableQuantity": 1,
        "categoryId": category_id,
        "listingDescription": full_html_description,  # Full HTML goes here
        "pricingSummary": {"price": {"currency": "GBP", "value": price_val}},
        "merchantLocationKey": mlk,
        "listingPolicies": {
            "paymentPolicyId": payment_id,
            "returnPolicyId": return_id,
            "fulfillmentPolicyId": fulfillment_id,
        },
        "listingDuration": "GTC",
        "quantityLimitPerBuyer": 1,
    }

    logger.info(f"[offer] Creating/updating offer for SKU {sku}")

    # Look up and DELETE existing offers to start fresh
    offer_id = None
    try:
        r = requests.get(f"{base}/offer?sku={sku}", headers=headers, timeout=30)
        if r.status_code == 200:
            offers = r.json().get("offers") or []
            if offers:
                # Delete all existing offers for this SKU to start fresh
                for old_offer in offers:
                    old_id = old_offer.get("offerId") or (old_offer.get("offer") or {}).get("offerId")
                    if old_id:
                        try:
                            logger.info(f"[offer] Deleting old offer {old_id} for fresh start")
                            requests.delete(f"{base}/offer/{old_id}", headers=headers, timeout=30)
                        except Exception as e:
                            logger.warning(f"[offer] Could not delete {old_id}: {e}")
                # Don't reuse - force creation of new offer
                offer_id = None
    except Exception as e:
        logger.warning(f"[offer] Lookup failed: {e}")

    # Create or update offer
    try:
        if offer_id:
            logger.info(f"[offer] Updating existing offer {offer_id}")
            pu = requests.put(f"{base}/offer/{offer_id}", headers=headers, json=offer_body, timeout=60)
            if pu.status_code not in (200, 201, 204):
                return {"success": False, "error": f"Offer update failed: {pu.status_code} {pu.text}"}
        else:
            logger.info(f"[offer] Creating new offer")
            pc = requests.post(f"{base}/offer", headers=headers, json=offer_body, timeout=60)
            if pc.status_code not in (200, 201):
                return {"success": False, "error": f"Offer create failed: {pc.status_code} {pc.text}"}
            offer_id = pc.json().get("offerId") or (pc.json().get("offer") or {}).get("offerId")
            if not offer_id:
                return {"success": False, "error": "No offerId returned"}
    except Exception as e:
        logger.error(f"[offer] Exception: {e}")
        return {"success": False, "error": f"Offer exception: {str(e)}"}

    # ===== STEP 3: PUBLISH =====
    logger.info(f"[offer] Publishing offer {offer_id}")
    try:
        pb = requests.post(f"{base}/offer/{offer_id}/publish", headers=headers, timeout=30)
        if pb.status_code not in (200, 201):
            return {"success": False, "error": f"Publish failed: {pb.status_code} {pb.text}"}
        
        listing_id = None
        try:
            listing_id = pb.json().get("listingId")
        except Exception:
            pass
        
        logger.info(f"[offer] Published! offerId={offer_id}, listingId={listing_id}")
        res = {"success": True, "offerId": offer_id}
        if listing_id:
            res["listingId"] = listing_id
        return res
    except Exception as e:
        logger.error(f"[offer] Publish exception: {e}")
        return {"success": False, "error": f"Publish exception: {str(e)}"}

# --- end function ---
