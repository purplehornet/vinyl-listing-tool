from __future__ import annotations
import time, json
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode, quote_plus
import urllib.request, urllib.error

EBAY_BROWSE_BASE = "https://api.ebay.com/buy/browse/v1/item_summary/search"

CATEGORY_IDS = {
    "Records": "176985",
    "Cassettes": "176983",
}

BUYING_OPTIONS_MAP = {
    "BIN": ["FIXED_PRICE","BEST_OFFER"],
    "AUCTION": ["AUCTION"],
    "AUCTION_BIN": ["AUCTION","FIXED_PRICE","BEST_OFFER"],
}

class EbaySearch:
    def __init__(self, ebay_api, site: str = "EBAY_GB"):
        self.ebay_api = ebay_api
        self.site = site

    def _request(self, url: str, attempt: int = 0) -> Dict[str, Any]:
        token = self.ebay_api.get_access_token()
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": self.site,
        })
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429,500,502,503,504):
                retry_after = int(e.headers.get("Retry-After","0") or "0")
                wait = retry_after if retry_after > 0 else min(600, 2**attempt)
                time.sleep(wait or 2)
                if attempt < 6:
                    return self._request(url, attempt+1)
            raise

    def _build_filter(self,
                      listing_types: Optional[List[str]],
                      price_cap: Optional[float],
                      categories: Optional[List[str]],
                      country: str) -> str:
        parts = []
        if categories:
            ids = []
            for c in categories:
                cid = CATEGORY_IDS.get(c) or c
                ids.append(cid)
            ids = [i for i in ids if i]
            if ids:
                parts.append(f"categoryIds:{{{','.join(ids)}}}")
        opts = []
        for lt in (listing_types or []):
            opts += BUYING_OPTIONS_MAP.get(lt, [])
        if opts:
            parts.append(f"buyingOptions:{{{','.join(sorted(set(opts)))}}}")
        if price_cap is not None:
            parts.append(f"price:[..{price_cap}]")
        if country:
            parts.append(f"itemLocationCountry:{{{country}}}")
        return " AND ".join(parts)

    def search_active_listings(self,
                               query: str,
                               limit: int = 20,
                               listing_types: Optional[List[str]] = None,
                               sort: str = "newlyListed",
                               price_cap: Optional[float] = None,
                               site: Optional[str] = None,
                               country: str = "GB",
                               categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        site = site or self.site
        sort_param = "creationDate:desc" if sort.lower().startswith("new") else "price"
        filt = self._build_filter(listing_types, price_cap, categories, country)
        params = {
            "q": query,
            "limit": str(max(1, min(100, int(limit)))),
            "sort": sort_param,
            "filter": filt,
        }
        url = EBAY_BROWSE_BASE + "?" + urlencode(params, quote_via=quote_plus)
        data = self._request(url)

        out: List[Dict[str, Any]] = []
        for it in data.get("itemSummaries", []) or []:
            price = _num((it.get("price") or {}).get("value"))
            ship = _num(((it.get("shippingOptions") or [{}])[0].get("shippingCost") or {}).get("value"))
            total = (price or 0.0) + (ship or 0.0)
            out.append({
                "title": it.get("title") or "",
                "price": price,
                "shipping": ship,
                "total": total,
                "currency": (it.get("price") or {}).get("currency") or "GBP",
                "url": it.get("itemWebUrl") or "",
                "item_id": it.get("itemId") or "",
                "seller": ((it.get("seller") or {}).get("username") or ""),
                "seller_fb_pct": _num((it.get("seller") or {}).get("feedbackPercentage")),
                "condition": it.get("condition") or "",
                "start_time": it.get("itemCreationDate") or "",
                "buying_options": it.get("buyingOptions") or [],
            })
        return out

def _num(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0
