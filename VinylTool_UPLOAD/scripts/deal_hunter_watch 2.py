#!/usr/bin/env python3
import time, json, sys, argparse
import tkinter as tk
from pathlib import Path
from datetime import datetime, timezone

# project deps
sys.path.insert(0, ".")
from vinyltool.services.ebay import EbayAPI
from vinyltool.services.ebay_search import EbaySearch
from vinyltool.services.discogs import DiscogsAPI
from vinyltool.services.discogs_auto_matcher import DiscogsAutoMatcher
from vinyltool.core.config import load_config

STATE_PATH = Path("profiles/dev/data/dealwatch_state.json")
LOG_PATH   = Path("logs/dealwatch.log")
DISCOVERY  = Path("searches/discovery.yaml")

EBAY_MIN_INTERVAL_S    = 2.0
DISCOGS_MIN_INTERVAL_S = 1.2

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def load_yaml(path: Path):
    import yaml
    return yaml.safe_load(path.read_text("utf-8"))

def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text("utf-8"))
        except Exception:
            pass
    return {"last_seen": {}, "last_run": None}

def polite_call(min_interval_attr: str, min_interval_s: float, func, *a, **kw):
    tnow = time.monotonic()
    last = getattr(polite_call, min_interval_attr, 0.0)
    wait = min_interval_s - (tnow - last)
    if wait > 0:
        time.sleep(wait)
    res = func(*a, **kw)
    setattr(polite_call, min_interval_attr, time.monotonic())
    return res

def compute_profit(item, release_id, fmt, dc, defaults):
    try:
        psug = polite_call("_last_discogs", DISCOGS_MIN_INTERVAL_S,
                           dc.get_price_suggestions, release_id) or {}
    except Exception:
        psug = {}
    # Extract price from Discogs price suggestions
    nm_price = psug.get("Near Mint (NM or M-)")
    vg_price = psug.get("Very Good Plus (VG+)")
    # Ensure we get a float value, not a dict
    if isinstance(nm_price, dict):
        nm_price = nm_price.get("value", 0.0)
    if isinstance(vg_price, dict):
        vg_price = vg_price.get("value", 0.0)
    basis = float(nm_price or vg_price or 0.0)

    buy = float(item.get("total") or 0.0)
    pm = defaults.get("price_model", {}).get(fmt, {})
    out_post = float(pm.get("outbound_postage_gbp", 0))
    mailer   = float(pm.get("mailer_cost_gbp", 0))
    fee_pct  = float(pm.get("fee_pct", 12.8))
    fee_fix  = float(pm.get("fee_fix_gbp", 0.30))

    target_net = max(0.0, basis - (basis * fee_pct/100.0) - fee_fix - out_post - mailer)
    proj   = target_net - buy
    margin = (proj / buy * 100.0) if buy > 0 else 0.0
    return basis, proj, margin, target_net

def one_pass(eb, dc, matcher, min_confidence, verbose, discovery, state):
    print("\n🔍 Scanning eBay for new deals...")
    print("\n🔍 Scanning eBay for new deals...")
    print("\n🔍 Scanning eBay for new deals...")
    defaults = discovery.get("defaults", {})
    searches = discovery.get("searches", [])
    any_found = False

    for s in searches:
        name = s.get("name", "unknown")
        print(f"  📦 Checking: {name}")
        print(f"  📦 Checking: {s['name']}")
        
        
        name   = s["name"]
        fmts   = [f.lower() for f in s.get("formats", ["vinyl"])]
        max_price = s.get("max_price", 9999)
        exclude = [t.lower() for t in (s.get("exclude_terms") or []) + defaults.get("exclude_terms", [])]
        last_key = f"{name}"

        try:
                                items = polite_call("_last_ebay", EBAY_MIN_INTERVAL_S,
                                                    eb.search_active_listings,
                                                    s.get("query", ""),
                                                    limit=20,
                                                    price_cap=s.get("max_price"))
        except Exception as e:
            print(f"⚠️ eBay error for {name}: {e}")
            continue

        last_seen = state["last_seen"].get(last_key)
        new_items = []
        for it in items:
            title = (it.get("title") or "").lower()
            if any(t in title for t in exclude): 
                continue
            if float(it.get("total") or 0) > max_price: 
                continue
            if last_seen and it.get("item_id") == last_seen: 
                break
            new_items.append(it)

        print(f"    📊 After filtering: {len(new_items)} new items (from {len(items)} total)")
        if new_items:
            print(f"    ✅ Found {len(new_items)} new items")
            state["last_seen"][last_key] = new_items[0].get("item_id")
            any_found = True

        for it in new_items:
            for fmt in fmts:
                rid = s.get("discogs_release_id")
                if not rid:
                    # Try auto-matching
                    if matcher:
                        try:
                            match_result = matcher.find_best_match(it, fmt)
                            if match_result:
                                rid, release_data, confidence = match_result
                                if confidence >= min_confidence:
                                    title_short = it.get("title", "")[:50]
                                    print(f"    🎯 Auto-matched ({confidence:.0%}): {title_short}... -> Discogs {rid}")
                                    ebay_url = it.get("view_item_url") or it.get("url") or it.get("item_web_url") or f"https://www.ebay.co.uk/itm/{it.get('item_id', 'unknown')}"
                                    print(f"        🛒 eBay: {ebay_url}")
                                    print(f"        📀 Discogs: https://www.discogs.com/release/{rid}")
                                else:
                                    if verbose:
                                        print(f"    ⚠️ Low confidence ({confidence:.0%}) SKIPPED")
                                    continue
                            else:
                                continue
                        except Exception as e:
                            if verbose:
                                print(f"    ⚠️ Error: {e}")
                            continue
                    else:
                        continue
                basis, proj, margin, target_net = compute_profit(it, rid, fmt, dc, defaults)
                pm = defaults.get("price_model", {}).get(fmt, {})
                min_profit = float(pm.get("min_profit_gbp", 10))
                min_margin = float(pm.get("min_margin_pct", 20))
                if proj >= min_profit and margin >= min_margin:
                    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                    line = (f"{now_utc()} | {name} | [{fmt}] £{proj:.2f} ({margin:.1f}%) "
                            f"on £{float(it.get('total') or 0):.2f} | basis £{basis:.2f} | "
                            f"{it.get('title')} | {it.get('url')}\n")
                    with LOG_PATH.open("a", encoding="utf-8") as f:
                        f.write(line)
                    print(line, end="")

    return any_found

def main(loop_minutes=5, once=False):
    cfg = load_config()
    root = tk.Tk(); root.withdraw()
    try:
        ebay_api = EbayAPI(cfg, root)
    except TypeError:
        ebay_api = EbayAPI(cfg)
    eb = EbaySearch(ebay_api=ebay_api, site="EBAY_GB")
    dc = DiscogsAPI(cfg)

    # Load discovery searches config
    discovery = load_yaml(DISCOVERY)

    # Initialize auto-matcher
    match_settings = discovery.get("settings", {})
    min_confidence = match_settings.get("min_confidence_score", 0.75)
    enable_matching = match_settings.get("enable_auto_matching", True)
    verbose = match_settings.get("verbose_matching", False)
    matcher = DiscogsAutoMatcher(dc, verbose=verbose) if enable_matching else None

    # Load state
    state = load_state()

    # Initialize auto-matcher

    if once:
        one_pass(eb, dc, matcher, min_confidence, verbose, discovery, state)
        state["last_run"] = now_utc()
        save_state(state)
        return

    while True:
        any_found = one_pass(eb, dc, matcher, min_confidence, verbose, discovery, state)
        state["last_run"] = now_utc()
        save_state(state)
        time.sleep(loop_minutes * 60)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=5, help="Loop interval minutes")
    ap.add_argument("--once", action="store_true", help="Run a single pass and exit")
    args = ap.parse_args()
    main(loop_minutes=args.minutes, once=args.once)
